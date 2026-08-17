#!/usr/bin/env python3
"""Scrape product images from benfreshfood.com and match top-100 ordered SKUs.

Hotlinks absolute URLs into benfresh.productos.image_url (no Storage upload).

Uso:
  set -a && source ../backend-supabase/.env && set +a
  python scripts/benfresh/scrape_benfresh_images.py
  python scripts/benfresh/scrape_benfresh_images.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import ssl
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

import asyncpg
from dotenv import load_dotenv

_SSL_CTX = ssl._create_unverified_context()

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "implementacion" / "benfresh" / "outputs"
SCHEMA = "benfresh"
SITE_URL = "https://www.benfreshfood.com"
SITE_BASE = "https://www.benfreshfood.com/"
UA = "Mozilla/5.0 (compatible; SuplaiBenfreshImageSync/1.0)"
TOP_N = 100
MIN_SCORE = 0.28
MIN_SHARED_LONG_TOKENS = 1
STOPWORDS = frozenset(
    {
        "frozen",
        "iqf",
        "bag",
        "box",
        "cut",
        "with",
        "and",
        "the",
        "benfresh",
        "organic",
        "seeds",
        "slices",
        "slice",
        "mix",
        "blend",
        "long",
        "grain",
        "parboiled",
        "sweet",
        "plantain",
        "maracuya",
        "lbs",
        "lb",
        "oz",
        "kg",
    }
)
# product keyword → preferred site stem substring
ALIASES: dict[str, str] = {
    "sweetcorn": "sweet_corn",
    "sweet corn": "sweet_corn",
    "fajita": "fajita",
    "broccoli": "broccoli",
    "california": "california",
    "cauliflower": "califlower",
    "califlower": "califlower",
    "mamey": "mamey",
    "strawberry": "strawberr",
    "strawberries": "strawberr",
    "blueberry": "blueberr",
    "blueberries": "blueberr",
    "pineapple": "pineapple",
    "spinach": "spinach",
    "butternut": "butternut",
    "celery": "celery",
    "banana": "banana",
    "papaya": "papaya",
    "franui": "franui",
    "raspberry": "franui",
    "raspberries": "franui",
    "peas and carrot": "peas_and_carrot",
    "peas & carrot": "peas_and_carrot",
}

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend-supabase" / ".env")

CSV_FIELDS = [
    "product_code",
    "nombre",
    "qty",
    "qty_rank",
    "matched_url",
    "matched_file",
    "score",
    "status",
    "image_url_prev",
]


def _db_url() -> str:
    url = (
        os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL / DATABASE_URL")
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    return url


def _tokens(text: str) -> set[str]:
    raw = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    out = set()
    for t in raw.split():
        if len(t) < 3:
            continue
        if t.isdigit():
            continue
        if t in STOPWORDS:
            continue
        out.add(t)
    return out


def _alias_hit(product_name: str, img_stem: str) -> float:
    name = (product_name or "").lower()
    stem = (img_stem or "").lower()
    for needle, prefer in ALIASES.items():
        if needle in name and prefer in stem:
            return 0.55
    return 0.0


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    return len(inter) / len(union)


def _shared_long(a: set[str], b: set[str]) -> int:
    return sum(1 for t in (a & b) if len(t) >= 4)


def fetch_site_product_images() -> list[dict[str, str]]:
    req = urllib.request.Request(SITE_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45, context=_SSL_CTX) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    paths = re.findall(
        r"(?:src|data-src)=[\"']([^\"']*assets/images/product/[^\"']+\.(?:jpg|jpeg|png|webp))",
        html,
        flags=re.I,
    )
    # Also catch bare relative paths in case attributes differ
    paths += re.findall(
        r"(assets/images/product/[^\"'\s>]+\.(?:jpg|jpeg|png|webp))",
        html,
        flags=re.I,
    )

    by_stem: dict[str, dict[str, str]] = {}
    for path in paths:
        path = path.strip()
        if not path:
            continue
        url = urljoin(SITE_BASE, path)
        filename = path.rsplit("/", 1)[-1]
        stem = re.sub(r"\.(jpg|jpeg|png|webp)$", "", filename, flags=re.I)
        is_dorso = "dorso" in stem.lower()
        is_frente = "frente" in stem.lower()
        key = re.sub(r"[_-]?(frente|dorso)$", "", stem, flags=re.I).lower()
        prev = by_stem.get(key)
        if prev is None:
            by_stem[key] = {
                "url": url,
                "file": filename,
                "stem": stem,
                "prefer": "frente" if is_frente else ("dorso" if is_dorso else "plain"),
            }
            continue
        # Prefer frente over dorso/plain; plain over dorso
        rank = {"frente": 2, "plain": 1, "dorso": 0}
        new_pref = "frente" if is_frente else ("dorso" if is_dorso else "plain")
        if rank[new_pref] > rank[prev["prefer"]]:
            by_stem[key] = {
                "url": url,
                "file": filename,
                "stem": stem,
                "prefer": new_pref,
            }

    return list(by_stem.values())


def best_match(
    product_name: str, site_images: list[dict[str, str]], used_urls: set[str]
) -> tuple[dict[str, str] | None, float]:
    ptoks = _tokens(product_name)
    best: dict[str, str] | None = None
    best_score = 0.0
    for img in site_images:
        if img["url"] in used_urls:
            continue
        itoks = _tokens(img["stem"].replace("_", " ").replace("-", " "))
        score = max(_jaccard(ptoks, itoks), _alias_hit(product_name, img["stem"]))
        shared = _shared_long(ptoks, itoks)
        # containment boost: distinctive product token appears in stem
        for t in ptoks:
            if len(t) >= 5 and t in img["stem"].lower().replace("-", "").replace("_", ""):
                score = max(score, 0.5)
                break
        if score < MIN_SCORE and shared < MIN_SHARED_LONG_TOKENS:
            continue
        adj = score + 0.05 * shared
        if adj > best_score:
            best_score = adj
            best = img
    return best, best_score


async def main(apply: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "image_matches.csv"

    print("[*] Scraping", SITE_URL)
    site_images = fetch_site_product_images()
    print(f"[*] Site product images (deduped): {len(site_images)}")

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        top = await conn.fetch(
            f"""
            SELECT p.product_code, p.nombre, p.image_url,
                   SUM(ip.cantidad_solicitada)::float AS qty
            FROM {SCHEMA}.items_pedido ip
            JOIN {SCHEMA}.productos p ON p.product_code = ip.product_code
            WHERE COALESCE(ip.is_mock, false) = false
              AND COALESCE(p.is_mock, false) = false
            GROUP BY p.product_code, p.nombre, p.image_url
            ORDER BY qty DESC NULLS LAST
            LIMIT $1
            """,
            TOP_N,
        )
        if not top:
            # Fallback: top by catalog / nombre if no order history
            top = await conn.fetch(
                f"""
                SELECT product_code, nombre, image_url, 0::float AS qty
                FROM {SCHEMA}.productos
                WHERE COALESCE(is_mock, false) = false
                  AND COALESCE(en_catalogo, true) = true
                ORDER BY nombre
                LIMIT $1
                """,
                TOP_N,
            )
            print("[*] items_pedido vacío/sin qty: fallback catálogo")

        report: list[dict[str, object]] = []
        updates: list[tuple[str, str]] = []
        used_urls: set[str] = set()

        for rank, row in enumerate(top, start=1):
            code = row["product_code"]
            nombre = row["nombre"] or ""
            prev = row["image_url"] or ""
            match, score = best_match(nombre, site_images, used_urls)
            if match is None:
                report.append(
                    {
                        "product_code": code,
                        "nombre": nombre,
                        "qty": row["qty"],
                        "qty_rank": rank,
                        "matched_url": "",
                        "matched_file": "",
                        "score": 0,
                        "status": "unmatched",
                        "image_url_prev": prev,
                    }
                )
                continue

            used_urls.add(match["url"])
            has_img = bool(prev and str(prev).strip())
            status = "matched_skip_has_image" if has_img else "matched_apply"
            report.append(
                {
                    "product_code": code,
                    "nombre": nombre,
                    "qty": row["qty"],
                    "qty_rank": rank,
                    "matched_url": match["url"],
                    "matched_file": match["file"],
                    "score": round(score, 3),
                    "status": status,
                    "image_url_prev": prev,
                }
            )
            if status == "matched_apply":
                updates.append((str(code), match["url"]))

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            w.writerows(report)

        matched = sum(1 for r in report if str(r["status"]).startswith("matched"))
        print(
            f"[*] top={len(report)} matched={matched} "
            f"to_apply={len(updates)} unmatched={len(report) - matched} csv={csv_path}"
        )
        if not apply:
            print("[*] Dry-run: no writes. Pass --apply to update.")
            return

        updated = 0
        async with conn.transaction():
            for code, url in updates:
                result = await conn.execute(
                    f"""
                    UPDATE {SCHEMA}.productos
                    SET image_url = $1, updated_at = now()
                    WHERE product_code = $2
                      AND (image_url IS NULL OR btrim(image_url) = '')
                    """,
                    url,
                    code,
                )
                if result.endswith("1"):
                    updated += 1
        print(f"[*] apply updated={updated}")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
