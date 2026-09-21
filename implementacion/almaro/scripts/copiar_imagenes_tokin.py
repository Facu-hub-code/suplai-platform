#!/usr/bin/env python3
"""Busca productos en Tokin (VTEX) y copia image_url a almaro y gonzales.

Match estricto por productReference ARC-10{codigo}. Solo completa image_url vacío.
No pisa fotos existentes.

Uso:
  python implementacion/almaro/scripts/copiar_imagenes_tokin.py
  python implementacion/almaro/scripts/copiar_imagenes_tokin.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
ALMARO_OUT = ROOT / "implementacion" / "almaro" / "outputs"
GONZALES_OUT = ROOT / "implementacion" / "gonzales" / "outputs"
SCHEMAS = ("almaro", "gonzales")
SEARCH_URL = "https://tokin.vtexcommercestable.com.br/api/io/_v/api/intelligent-search/product_search"
UA = "Mozilla/5.0 (compatible; SuplaiTokinImageSync/1.0)"
_SSL_CTX = ssl._create_unverified_context()
WORKERS = 8
RETRIES = 3
CATEGORIES = (
    "alimentos",
    "golosinas",
    "chocolates",
    "galletitas",
    "snacks",
    "helados",
    "bebidas",
    "halloween",
    "suplementos",
    "hogar",
    "barras-de-cereal",
)

load_dotenv(ROOT.parent / "backend-supabase" / ".env")
load_dotenv(ROOT / ".env", override=False)


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def db_url() -> str:
    url = (
        os.getenv("SUPABASE_DB_URL_POOLER")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL")
    return force_pooler(url)


def is_blank(url: str | None) -> bool:
    return not (url or "").strip()


def is_tokin(url: str | None) -> bool:
    return "tokin.vtexassets.com" in (url or "").lower()


def arcor_keys(code: str) -> list[str]:
    raw = (code or "").strip()
    digits = raw.lstrip("0") or "0"
    keys: list[str] = []
    for body in (f"10{raw}", f"10{digits}", f"10{digits.zfill(5)}", raw, digits):
        ref = body if body.upper().startswith("ARC-") else f"ARC-{body}"
        if ref not in keys:
            keys.append(ref)
    return keys


def pick_image(product: dict) -> str | None:
    candidates: list[str] = []
    for item in product.get("items") or []:
        for img in item.get("images") or []:
            url = (img.get("imageUrl") or "").strip()
            if url:
                candidates.append(url.split("?")[0] + (("?" + url.split("?", 1)[1]) if "?" in url else ""))
    if not candidates:
        return None
    for url in candidates:
        lower = url.lower()
        if "detail" in lower or "-un-1" in lower:
            return url
    return candidates[0]


def http_json(url: str) -> dict:
    last_err: Exception | None = None
    for attempt in range(6):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45, context=_SSL_CTX) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            last_err = err
            if err.code in {429, 500, 502, 503, 504}:
                time.sleep(1.2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            last_err = err
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"Tokin HTTP fail {url}: {last_err}")


def scrape_tokin_catalog() -> list[dict]:
    """Dump productos reales (sin Combos) paginando departamentos."""
    seen: dict[str, dict] = {}
    for cat in CATEGORIES:
        page = 1
        while True:
            qs = urllib.parse.urlencode({"count": 50, "page": page})
            data = http_json(f"{SEARCH_URL}/category-1/{urllib.parse.quote(cat)}?{qs}")
            products = data.get("products") or []
            if not products:
                break
            for product in products:
                if str(product.get("brand") or "").strip().upper() == "COMBOS":
                    continue
                ref = str(product.get("productReference") or "").strip()
                image = pick_image(product)
                if not ref or not image:
                    continue
                seen[ref] = {
                    "tokin_ref": ref,
                    "tokin_name": product.get("productName") or "",
                    "tokin_brand": product.get("brand") or "",
                    "image_url": image,
                    "category": cat,
                }
            total = int(data.get("recordsFiltered") or 0)
            if page * 50 >= total or page >= 50:
                break
            page += 1
            time.sleep(0.15)
        print(f"  … categoría {cat}: acumulados={len(seen)}")
    return list(seen.values())


def index_catalog(items: list[dict]) -> dict[str, dict]:
    """Mapa código interno / ARC-ref → producto Tokin."""
    index: dict[str, dict] = {}
    for item in items:
        ref = item["tokin_ref"]
        keys = {ref.upper(), ref}
        if ref.upper().startswith("ARC-"):
            digits = ref.split("-", 1)[-1]
            keys.add(digits)
            keys.add(digits.lstrip("0") or "0")
            if digits.startswith("10") and len(digits) >= 6:
                rest = digits[2:]
                keys.add(rest)
                keys.add(rest.lstrip("0") or "0")
        for key in keys:
            index.setdefault(key, item)
    return index


def match_from_index(code: str, index: dict[str, dict]) -> dict:
    raw = (code or "").strip()
    candidates = [raw, raw.lstrip("0") or "0", *arcor_keys(raw)]
    if raw.isdigit() or raw.lstrip("0").isdigit():
        body = raw.lstrip("0") or "0"
        candidates.extend([f"10{raw}", f"10{body}", f"10{body.zfill(5)}"])
    for key in candidates:
        item = index.get(key) or index.get(key.upper())
        if not item:
            continue
        return {
            "status": "matched",
            "source": "tokin_catalog",
            "query": key,
            "tokin_ref": item["tokin_ref"],
            "tokin_name": item["tokin_name"],
            "tokin_brand": item["tokin_brand"],
            "image_url": item["image_url"],
        }
    return {"status": "miss", "source": "tokin_catalog", "query": arcor_keys(raw)[0]}


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "schema",
        "product_code",
        "nombre",
        "status",
        "source",
        "query",
        "tokin_ref",
        "tokin_name",
        "tokin_brand",
        "image_url",
        "image_url_prev",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Escribir image_url en BD")
    parser.add_argument("--limit", type=int, default=0, help="Máximo de SKUs a buscar en Tokin")
    args = parser.parse_args()

    print("[*] Tenants: almaro y gonzales")
    print("[*] Path: implementacion/almaro/ y implementacion/gonzales/ (sin rama)")

    conn = await asyncpg.connect(db_url(), statement_cache_size=0)
    try:
        catalog: dict[str, list] = {}
        for schema in SCHEMAS:
            catalog[schema] = await conn.fetch(
                f"""
                SELECT product_code, nombre, image_url
                FROM {schema}.productos
                ORDER BY product_code
                """
            )
    finally:
        await conn.close()

    by_code: dict[str, dict[str, dict]] = {s: {} for s in SCHEMAS}
    for schema, rows in catalog.items():
        for row in rows:
            by_code[schema][str(row["product_code"]).strip()] = {
                "nombre": row["nombre"],
                "image_url": (row["image_url"] or "").strip() or None,
            }

    sibling_images: dict[str, str] = {}
    for schema in SCHEMAS:
        for code, info in by_code[schema].items():
            if is_tokin(info["image_url"]):
                sibling_images.setdefault(code, info["image_url"])

    to_search: list[str] = []
    planned: dict[str, list[dict]] = {s: [] for s in SCHEMAS}

    for schema in SCHEMAS:
        for code, info in by_code[schema].items():
            if not is_blank(info["image_url"]):
                continue
            row = {
                "schema": schema,
                "product_code": code,
                "nombre": info["nombre"],
                "status": "pending",
                "source": "",
                "query": "",
                "tokin_ref": "",
                "tokin_name": "",
                "tokin_brand": "",
                "image_url": "",
                "image_url_prev": info["image_url"] or "",
            }
            if code in sibling_images:
                row.update(
                    {
                        "status": "matched",
                        "source": "sibling_tokin",
                        "image_url": sibling_images[code],
                    }
                )
            planned[schema].append(row)
            if row["status"] == "pending" and code not in to_search:
                to_search.append(code)

    if args.limit:
        to_search = to_search[: args.limit]

    print(f"[*] Almaro sin imagen: {len(planned['almaro'])}")
    print(f"[*] Gonzales sin imagen: {len(planned['gonzales'])}")
    print(f"[*] SKUs a cruzar con catálogo Tokin: {len(to_search)}")

    print("[*] Descargando catálogo Tokin por categoría (sin Combos)...")
    catalog_items = scrape_tokin_catalog()
    catalog_path = ALMARO_OUT / "tokin-catalogo.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog_items, ensure_ascii=False, indent=2), encoding="utf-8")
    index = index_catalog(catalog_items)
    print(f"[*] Catálogo Tokin: {len(catalog_items)} productos, {len(index)} claves")

    found: dict[str, dict] = {}
    misses = 0
    errors = 0
    for code in to_search:
        result = match_from_index(code, index)
        if result.get("status") == "matched":
            found[code] = result
        else:
            misses += 1

    reports: dict[str, list[dict]] = {s: [] for s in SCHEMAS}
    apply_rows: dict[str, list[tuple[str, str]]] = {s: [] for s in SCHEMAS}
    for schema in SCHEMAS:
        for row in planned[schema]:
            if row["status"] != "matched":
                hit = found.get(row["product_code"])
                if hit:
                    row.update(
                        {
                            "status": "matched",
                            "source": hit.get("source") or "tokin_api",
                            "query": hit.get("query") or "",
                            "tokin_ref": hit.get("tokin_ref") or "",
                            "tokin_name": hit.get("tokin_name") or "",
                            "tokin_brand": hit.get("tokin_brand") or "",
                            "image_url": hit.get("image_url") or "",
                        }
                    )
                else:
                    row["status"] = "miss"
                    row["source"] = "tokin_catalog"
                    row["query"] = arcor_keys(row["product_code"])[0]
            reports[schema].append(row)
            if row["status"] == "matched" and row["image_url"]:
                apply_rows[schema].append((row["image_url"], row["product_code"]))

    stamp = time.strftime("%Y%m%d")
    almaro_csv = ALMARO_OUT / f"tokin-imagenes-{stamp}.csv"
    gonzales_csv = GONZALES_OUT / f"tokin-imagenes-{stamp}.csv"
    write_csv(almaro_csv, reports["almaro"])
    write_csv(gonzales_csv, reports["gonzales"])

    summary = {
        "apply": bool(args.apply),
        "tokin_catalog_size": len(catalog_items),
        "tokin_searched": len(to_search),
        "tokin_matched_skus": len(found),
        "tokin_miss": misses,
        "tokin_errors": errors,
        "almaro": {
            "missing_before": len(planned["almaro"]),
            "to_update": len(apply_rows["almaro"]),
            "miss": sum(1 for r in reports["almaro"] if r["status"] != "matched"),
            "csv": str(almaro_csv),
        },
        "gonzales": {
            "missing_before": len(planned["gonzales"]),
            "to_update": len(apply_rows["gonzales"]),
            "miss": sum(1 for r in reports["gonzales"] if r["status"] != "matched"),
            "csv": str(gonzales_csv),
        },
    }
    summary_path = ALMARO_OUT / f"tokin-imagenes-{stamp}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.apply:
        print("[*] Dry-run: no se escribió en BD. Usá --apply para guardar.")
        return 0

    print("[*] Schema almaro y schema gonzales — UPDATE image_url solo si está vacío")
    conn = await asyncpg.connect(db_url(), statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0;")
        for schema in SCHEMAS:
            updated = 0
            batch = apply_rows[schema]
            for i in range(0, len(batch), 80):
                chunk = batch[i : i + 80]
                async with conn.transaction():
                    for image_url, code in chunk:
                        result = await conn.execute(
                            f"""
                            UPDATE {schema}.productos
                            SET image_url = $1, updated_at = now()
                            WHERE product_code = $2
                              AND (image_url IS NULL OR btrim(image_url) = '')
                            """,
                            image_url,
                            code,
                        )
                        if result.endswith("1"):
                            updated += 1
            remaining = await conn.fetchval(
                f"""
                SELECT COUNT(*) FROM {schema}.productos
                WHERE image_url IS NULL OR btrim(image_url) = ''
                """
            )
            sample = await conn.fetch(
                f"""
                SELECT product_code, nombre, LEFT(image_url, 90) AS img
                FROM {schema}.productos
                WHERE image_url ILIKE '%tokin.vtexassets%'
                ORDER BY updated_at DESC
                LIMIT 3
                """
            )
            print(f"[OK] {schema}: actualizados={updated} siguen_sin_imagen={remaining}")
            for s in sample:
                print(f"     {s['product_code']} {s['nombre'][:40]} → {s['img']}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
