#!/usr/bin/env python3
"""Comprimir pack shots WEB FOTOS de Benfresh, subir a Storage y asignar a SKUs.

Tenant: benfresh
Fuente: Desktop/FOTOS PRODUCTOS BENFRESH/WEB FOTOS
Bucket: products-benfresh
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv
from PIL import Image

SCHEMA = "benfresh"
BUCKET = "products-benfresh"
SRC_DIR = Path("/Users/facundolorenzo/Desktop/FOTOS PRODUCTOS BENFRESH/WEB FOTOS")
ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "implementacion" / "benfresh" / "outputs" / "fotos-web"
MATCH_CSV = ROOT / "implementacion" / "benfresh" / "outputs" / "fotos-web-match.csv"
MAX_EDGE = 1600
JPEG_QUALITY = 82
CACHE_BUST = "20260901"

Image.MAX_IMAGE_PIXELS = None

# slug -> predicado sobre nombre lowercased. Una foto cubre todas las presentaciones
# de esa línea (3 lb / 22 lb), sin mezclar blends ni variantes distintas.
RULES: list[tuple[str, str, callable]] = [
    ("3COLORDICED-PWB.png", "3-color-diced", lambda n: ("3 color" in n and "dice" in n) or n.startswith("pepper 3 color 10x10")),
    ("3COLORSLICED-PWB.png", "3-color-sliced", lambda n: "3 color" in n and "slice" in n),
    ("3VEGETABLES-PWB.png", "3-vegetables", lambda n: n.startswith("3 vegetables")),
    ("4VEGETABLES-PWB.png", "4-vegetables", lambda n: n.startswith("4 vegetables")),
    ("BABY CARROT-PWB.png", "baby-carrot", lambda n: "baby carrot" in n),
    ("BROCOLLI FLORET-PWB.png", "broccoli-floret", lambda n: n.startswith("broccoli")),
    ("BUTTERNUT-PWB.png", "butternut", lambda n: "butternut" in n),
    ("CALIFLOWER-PWB.png", "cauliflower", lambda n: n.startswith("cauliflower") or n.startswith("califlower")),
    ("CALIFORNIA-PWB.png", "california-blend", lambda n: n.startswith("california")),
    ("CARROT DICED-PWB.png", "carrot-diced", lambda n: "carrot" in n and "dice" in n and "baby" not in n and "peas" not in n),
    ("FAJITA STRIPS-PWB.png", "fajita", lambda n: "fajita" in n),
    ("GREEN BEANS-PWB.png", "green-beans", lambda n: "green beans" in n and "cut" in n and "french" not in n),
    ("GREEN PEAS-PWB.png", "green-peas", lambda n: n.startswith("green peas")),
    ("GREEN PEPPER-PWB.png", "green-pepper", lambda n: "green pepper" in n and "red" not in n),
    ("PAPAYA-PWB.png", "papaya", lambda n: "papaya" in n),
    ("PEAS & CARROT-PWB.png", "peas-carrot", lambda n: "peas" in n and "carrot" in n and "3 vegetables" not in n and "4 vegetables" not in n),
    ("PLATANO MADURO-PWB.png", "platano-maduro", lambda n: "platano" in n or "plantain" in n),
    ("POTATO WEDGES-PWB.png", "potato-wedges", lambda n: "potato wedges" in n and "sweet" not in n),
    ("RED PEPPER-PWB.png", "red-pepper", lambda n: "red pepper" in n and "green" not in n and "3 color" not in n),
]

CATEGORY_SLUGS = {
    "Frozen Fruits": "papaya",
    "Frozen Vegetables": "green-beans",
    "Blends & Mixes": "4-vegetables",
}


def _db_url() -> str:
    url = (
        os.getenv("SUPABASE_DB_URL_POOLER")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL")
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    return url


def _slug_safe(code: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", code).strip("-")


def compress(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "sips",
                "-Z",
                str(MAX_EDGE),
                "-s",
                "format",
                "jpeg",
                "-s",
                "formatOptions",
                str(JPEG_QUALITY),
                str(src),
                "--out",
                str(dest),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        if dest.exists() and dest.stat().st_size > 800:
            return
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
        im.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)


def upload_jpeg(supabase_url: str, supabase_key: str, dest_name: str, path: Path) -> str:
    object_path = f"web/{dest_name}.jpg"
    upload_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}"
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "apikey": supabase_key,
        "Content-Type": "image/jpeg",
        "x-upsert": "true",
    }
    with path.open("rb") as fh:
        resp = requests.post(upload_url, headers=headers, data=fh, timeout=120)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"upload {object_path}: HTTP {resp.status_code} {resp.text[:200]}")
    return f"{supabase_url.rstrip('/')}/storage/v1/object/public/{BUCKET}/{object_path}?v={CACHE_BUST}"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Subir a Storage y UPDATE benfresh")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    load_dotenv(Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"))

    if not SRC_DIR.is_dir():
        raise SystemExit(f"No existe {SRC_DIR}")

    conn = await asyncpg.connect(
        _db_url(),
        statement_cache_size=0,
        timeout=30,
    )
    try:
        products = await conn.fetch(
            f"""
            SELECT product_code, nombre, en_catalogo, image_url
            FROM {SCHEMA}.productos
            ORDER BY nombre
            """
        )
        categories = await conn.fetch(
            f"SELECT id, name, image_url FROM {SCHEMA}.categorias ORDER BY sort_order"
        )

        assigned: dict[str, str] = {}
        rows: list[dict] = []
        for filename, slug, pred in RULES:
            src = SRC_DIR / filename
            hits = [p for p in products if pred((p["nombre"] or "").lower())]
            catalog_hits = [p for p in hits if p["en_catalogo"]]
            for p in hits:
                if p["product_code"] in assigned:
                    rows.append(
                        {
                            "archivo": filename,
                            "slug": slug,
                            "product_code": p["product_code"],
                            "nombre": p["nombre"],
                            "en_catalogo": p["en_catalogo"],
                            "status": "skip_already_assigned",
                            "image_url_prev": p["image_url"] or "",
                        }
                    )
                    continue
                assigned[p["product_code"]] = slug
                rows.append(
                    {
                        "archivo": filename,
                        "slug": slug,
                        "product_code": p["product_code"],
                        "nombre": p["nombre"],
                        "en_catalogo": p["en_catalogo"],
                        "status": "match" if p["en_catalogo"] else "match_off_catalog",
                        "image_url_prev": p["image_url"] or "",
                    }
                )
            print(f"{filename:28} -> {slug:20} catalog={len(catalog_hits):2} total={len(hits):2}")
            if not catalog_hits:
                print(f"  WARN: ningún SKU de catálogo para {filename}")

        MATCH_CSV.parent.mkdir(parents=True, exist_ok=True)
        with MATCH_CSV.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(
                fh,
                fieldnames=[
                    "archivo",
                    "slug",
                    "product_code",
                    "nombre",
                    "en_catalogo",
                    "status",
                    "image_url_prev",
                    "image_url_new",
                ],
            )
            w.writeheader()
            for r in rows:
                r.setdefault("image_url_new", "")
                w.writerow(r)

        catalog_n = sum(1 for r in rows if r["status"] == "match")
        print(f"\nSKU catálogo a actualizar: {catalog_n}")
        print(f"CSV: {MATCH_CSV}")

        if not args.apply:
            print("Dry-run. Pasá --apply para comprimir, subir y UPDATE benfresh.productos / categorias.")
            return

        supabase_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        if not supabase_url or not supabase_key:
            raise SystemExit("Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")

        slug_urls: dict[str, str] = {}
        for filename, slug, _pred in RULES:
            src = SRC_DIR / filename
            if not src.exists():
                print(f"SKIP missing {src}")
                continue
            dest = OUT_DIR / f"{slug}.jpg"
            print(f"compress {filename} -> {dest.name} ({src.stat().st_size / 1e6:.1f} MB)")
            compress(src, dest)
            print(f"  jpeg {dest.stat().st_size / 1e3:.0f} KB")
            slug_urls[slug] = upload_jpeg(supabase_url, supabase_key, slug, dest)
            print(f"  uploaded {slug_urls[slug]}")

        updates = []
        for r in rows:
            if r["status"] not in ("match", "match_off_catalog"):
                continue
            url = slug_urls.get(r["slug"])
            if not url:
                continue
            r["image_url_new"] = url
            if r["status"] == "match":
                updates.append((url, r["product_code"]))

        await conn.execute("SET statement_timeout = 0")
        await conn.executemany(
            f"""
            UPDATE {SCHEMA}.productos
            SET image_url = $1, updated_at = now()
            WHERE product_code = $2
            """,
            updates,
        )
        print(f"UPDATE {SCHEMA}.productos: {len(updates)} filas")

        cat_updates = []
        for cat in categories:
            slug = CATEGORY_SLUGS.get(cat["name"])
            if not slug or slug not in slug_urls:
                continue
            cat_updates.append((slug_urls[slug], cat["id"]))
        if cat_updates:
            await conn.executemany(
                f"""
                UPDATE {SCHEMA}.categorias
                SET image_url = $1, updated_at = now()
                WHERE id = $2
                """,
                cat_updates,
            )
            print(f"UPDATE {SCHEMA}.categorias: {len(cat_updates)} filas")

        with MATCH_CSV.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(
                fh,
                fieldnames=[
                    "archivo",
                    "slug",
                    "product_code",
                    "nombre",
                    "en_catalogo",
                    "status",
                    "image_url_prev",
                    "image_url_new",
                ],
            )
            w.writeheader()
            w.writerows(rows)

        n_prod = await conn.fetchval(
            f"SELECT count(*) FROM {SCHEMA}.productos WHERE en_catalogo AND image_url LIKE '%/web/%'"
        )
        n_cat = await conn.fetchval(
            f"SELECT count(*) FROM {SCHEMA}.categorias WHERE image_url IS NOT NULL AND btrim(image_url) <> ''"
        )
        print(f"OK {datetime.now(timezone.utc).isoformat()} catalog_with_web_foto={n_prod} categorias_con_foto={n_cat}")
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
