#!/usr/bin/env python3
"""Scrape image URLs from Campi (Tienda Propio / Centralo) and fill del_corro.productos.image_url.

Source: https://www.distribuidoracampi.com.ar/search
API: propio-bff.centraldeofertas.com.ar /search-module/product-displays

By default only updates rows where image_url is null/blank.
Dry-run is the default; pass --apply to write.

Usage:
  set -a && source ../backend-supabase/.env && set +a
  python scripts/del_corro_catalogo/scrape_campi_images.py
  python scripts/del_corro_catalogo/scrape_campi_images.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

# macOS / Python.org: a veces falla la cadena de certificados locales.
_SSL_CTX = ssl._create_unverified_context()

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "implementacion" / "del_corro" / "outputs"
SCHEMA = "del_corro"
SITE_URL = "https://www.distribuidoracampi.com.ar/search"
API_BASE = "https://propio-bff.centraldeofertas.com.ar/api/search-module/product-displays"
UA = "Mozilla/5.0 (compatible; SuplaiCampiImageSync/1.0)"

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend-supabase" / ".env")


def _db_url() -> str:
    url = (
        os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL / DATABASE_URL en .env")
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    return url


def _http_json(url: str, headers: dict[str, str], timeout: float = 45.0) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return json.load(resp)


def fetch_site_token() -> str:
    html = urllib.request.urlopen(
        urllib.request.Request(SITE_URL, headers={"User-Agent": UA}),
        timeout=45,
        context=_SSL_CTX,
    ).read().decode("utf-8", errors="replace")
    m = re.search(r"__NEXT_DATA__[^\>]*>(.*?)</script>", html)
    if not m:
        raise SystemExit("No se encontró __NEXT_DATA__ en la web de Campi")
    data = json.loads(m.group(1))
    token = data.get("props", {}).get("pageProps", {}).get("token")
    if not token or not isinstance(token, str):
        raise SystemExit("pageProps.token ausente en la web de Campi")
    return token


def scrape_campi_images(token: str, sleep_s: float = 0.15) -> dict[str, str]:
    """Return map externalProductId -> image URL (absolute, no query)."""
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Origin": "https://www.distribuidoracampi.com.ar",
        "Referer": SITE_URL,
        "x-site": token,
    }
    mapping: dict[str, str] = {}
    page: int | None = 1
    pages = 0
    while page is not None:
        qs = urllib.parse.urlencode({"page": page})
        url = f"{API_BASE}?{qs}"
        try:
            data = _http_json(url, headers)
        except urllib.error.HTTPError as e:
            body = e.read()[:300]
            raise SystemExit(f"API HTTP {e.code} page={page}: {body!r}") from e
        items = data.get("productDisplays") or []
        for item in items:
            code = str(item.get("externalProductId") or "").strip()
            image = str(item.get("image") or "").strip().split("?", 1)[0]
            if not code or not image:
                continue
            if image.startswith("//"):
                image = "https:" + image
            mapping[code] = image
        pages += 1
        nxt = data.get("nextPage")
        page = int(nxt) if nxt is not None else None
        if sleep_s and page is not None:
            time.sleep(sleep_s)
        if pages % 25 == 0:
            print(f"  … páginas={pages} códigos únicos={len(mapping)}")
    print(f"[*] Scrape OK: {pages} páginas, {len(mapping)} productos con imagen")
    return mapping


async def apply_updates(
    mapping: dict[str, str],
    *,
    apply: bool,
    only_missing: bool,
    limit: int | None,
) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "campi_images_match_report.json"

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        rows = await conn.fetch(
            f"""
            SELECT product_code, nombre, image_url
            FROM {SCHEMA}.productos
            ORDER BY product_code
            """
        )
        missing = [
            r
            for r in rows
            if not (r["image_url"] or "").strip()
        ]
        print(f"[*] BD: {len(rows)} productos, {len(missing)} sin image_url")

        candidates: list[tuple[str, str, str | None]] = []
        for r in rows:
            code = str(r["product_code"]).strip()
            img = mapping.get(code)
            if not img:
                continue
            current = (r["image_url"] or "").strip() or None
            if only_missing and current:
                continue
            if current == img:
                continue
            candidates.append((code, img, current))

        if limit is not None:
            candidates = candidates[:limit]

        matched_codes = {c for c, _, _ in candidates}
        scrape_only = sorted(set(mapping) - {str(r["product_code"]).strip() for r in rows})
        db_missing_unmatched = [
            str(r["product_code"]).strip()
            for r in missing
            if str(r["product_code"]).strip() not in mapping
        ]

        report = {
            "scraped": len(mapping),
            "db_total": len(rows),
            "db_missing": len(missing),
            "to_update": len(candidates),
            "only_missing": only_missing,
            "apply": apply,
            "sample_updates": [
                {"product_code": c, "new_image_url": n, "old_image_url": o}
                for c, n, o in candidates[:20]
            ],
            "missing_not_on_campi_site_sample": db_missing_unmatched[:40],
            "missing_not_on_campi_site_count": len(db_missing_unmatched),
            "campi_codes_not_in_db_count": len(scrape_only),
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[*] A actualizar: {len(candidates)} (only_missing={only_missing})")
        print(f"[*] Sin match en web Campi (entre missing): {len(db_missing_unmatched)}")
        print(f"[*] Reporte: {report_path}")

        if not apply:
            print("[*] Dry-run: no se escribió en BD. Usá --apply para guardar.")
            return

        updated = 0
        async with conn.transaction():
            for code, img, _old in candidates:
                if only_missing:
                    result = await conn.execute(
                        f"""
                        UPDATE {SCHEMA}.productos
                        SET image_url = $1, updated_at = now()
                        WHERE product_code = $2
                          AND (image_url IS NULL OR btrim(image_url) = '')
                        """,
                        img,
                        code,
                    )
                else:
                    result = await conn.execute(
                        f"""
                        UPDATE {SCHEMA}.productos
                        SET image_url = $1, updated_at = now()
                        WHERE product_code = $2
                        """,
                        img,
                        code,
                    )
                if result.endswith("1"):
                    updated += 1
        print(f"[*] UPDATE aplicados: {updated}")
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Completar image_url desde web Campi")
    parser.add_argument("--apply", action="store_true", help="Escribir en BD (default: dry-run)")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="También sobrescribir image_url ya poblados",
    )
    parser.add_argument("--limit", type=int, default=None, help="Máximo de updates (prueba)")
    parser.add_argument("--sleep", type=float, default=0.12, help="Pausa entre páginas API")
    args = parser.parse_args()

    print("[*] Obteniendo token de sitio Campi…")
    token = fetch_site_token()
    print("[*] Scrapeando catálogo Campi vía API…")
    mapping = scrape_campi_images(token, sleep_s=args.sleep)
    map_path = OUT / "campi_images_by_code.json"
    OUT.mkdir(parents=True, exist_ok=True)
    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[*] Mapa guardado: {map_path}")

    asyncio.run(
        apply_updates(
            mapping,
            apply=args.apply,
            only_missing=not args.overwrite,
            limit=args.limit,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
