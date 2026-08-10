#!/usr/bin/env python3
"""Carga imágenes de productos dimer desde sitios de marca / Serper.

Prioridad:
  1) Mapeo directo McCain (mccain.com.ar — NO dimerltda.cl)
  2) Serper/SerpAPI con preferencia de dominios de marca y exclusión de WordPress Dimer

Uso:
  set -a && source ../backend-supabase/.env && set +a
  # también necesita SERPER_API_KEY (platform/.env)
  python scripts/dimer/cargar_imagenes_marcas.py --limit 10
  python scripts/dimer/cargar_imagenes_marcas.py --apply
  python scripts/dimer/cargar_imagenes_marcas.py --only-mccain --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import asyncpg
import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCHEMA = "dimer"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "implementacion" / "dimer" / "outputs"
BUCKET = "products-dimer"

# Imágenes oficiales / renders McCain Argentina (foodservice-adjacent retail renders)
MCCAIN_IMAGES = {
    "smiles": "https://mccain.com.ar/wp-content/uploads/2026/03/RENDER-MC-CAIN-GOLAZO_13032626_0001_RENDER-MC-CAIN-SMILES-400G.png",
    "crinkle": "https://mccain.com.ar/wp-content/uploads/2024/01/Crinkle.png",
    "tradicional": "https://mccain.com.ar/wp-content/uploads/2024/01/Clasicas_Trad.png",
    "corte_fino": "https://mccain.com.ar/wp-content/uploads/2025/01/NUEVOS_0001_RENDER-MCCAIN-AIR-FRYER-FINITAS_041124.png",
    "surecrisp": "https://mccain.com.ar/wp-content/uploads/2025/01/NUEVOS_0000_TRUCA-MC-CAIN-CRISPERS.png",
    "fast_food": "https://mccain.com.ar/wp-content/uploads/2024/01/Clasicas_Trad-1.4k.png",
    "duquesas": "https://mccain.com.ar/wp-content/uploads/2024/01/Noisette_Clasicas-12k.png",
}

EXCLUDE_DOMAINS = {
    "dimerltda.cl",
    "www.dimerltda.cl",
    "placehold.co",
    "via.placeholder.com",
}

PREFERRED_DOMAINS = (
    "mccain.com.ar",
    "mccain.com",
    "mccainfoodservice.com",
    "mccaincalatin.com",
    "minutoverde.cl",
    "savory.cl",
    "unilever.com",
    "unileverfoodsolutions",
    "sadia.com",
    "brf.com",
)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _db_url() -> str:
    url = (os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "").strip()
    if not url:
        raise SystemExit("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL")
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    return url


def needs_image(url: str | None) -> bool:
    u = (url or "").strip().lower()
    if not u:
        return True
    return any(x in u for x in ("placehold", "placeholder", "via.placeholder"))


def mccain_direct_url(nombre: str) -> str | None:
    n = nombre.upper()
    if "MCCAIN" not in n and "MC CAIN" not in n:
        return None
    if "SMILES" in n:
        return MCCAIN_IMAGES["smiles"]
    if "CRINKLE" in n:
        return MCCAIN_IMAGES["crinkle"]
    if "SURECRISP" in n or "SURE CRISP" in n:
        return MCCAIN_IMAGES["surecrisp"]
    if "FAST FOOD" in n:
        return MCCAIN_IMAGES["fast_food"]
    if "DUQUES" in n:
        return MCCAIN_IMAGES["duquesas"]
    if "CORTE FINO" in n or "7MM" in n:
        return MCCAIN_IMAGES["corte_fino"]
    if "CORTE" in n or "TRADICIONAL" in n or "CASERO" in n or "9MM" in n or "12MM" in n:
        return MCCAIN_IMAGES["tradicional"]
    return MCCAIN_IMAGES["tradicional"]


def clean_search_name(nombre: str) -> str:
    n = re.sub(r"\([^)]*\)", " ", nombre)
    n = re.sub(r"\d+\s*[Xx×]\s*[\d,\.]+(?:\s*KG)?", " ", n, flags=re.I)
    n = re.sub(r"\b\d+[Mm]{2}\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def brand_boost_query(nombre: str) -> str:
    n = clean_search_name(nombre)
    low = n.lower()
    if "mccain" in low or "mc cain" in low:
        return f"{n} producto site:mccain.com.ar OR site:mccain.com"
    if "minuto verde" in low or "m.verde" in low:
        return f"{n} congelado site:minutoverde.cl"
    if "savory" in low:
        return f"{n} helado savory"
    if "sadia" in low:
        return f"{n} sadia producto"
    return f"{n} producto congelado Chile"


def domain_ok(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if any(host == d or host.endswith("." + d) for d in EXCLUDE_DOMAINS):
        return False
    return True


def prefer_score(url: str) -> int:
    host = (urlparse(url).hostname or "").lower()
    for i, pref in enumerate(PREFERRED_DOMAINS):
        if pref in host:
            return 100 - i
    return 0


def search_images(query: str, serper_key: str | None, serpapi_key: str | None, provider: str) -> list[str]:
    urls: list[str] = []
    if provider == "serper" and serper_key:
        r = requests.post(
            "https://google.serper.dev/images",
            headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
            json={"q": query, "gl": "cl", "hl": "es", "num": 8},
            timeout=15,
            verify=False,
        )
        if r.status_code == 200:
            for item in r.json().get("images", []) or []:
                u = item.get("imageUrl") or item.get("imageUrl")
                if u:
                    urls.append(u)
        else:
            print(f"  -> Serper HTTP {r.status_code}: {r.text[:120]}")
    elif serpapi_key:
        r = requests.get(
            "https://serpapi.com/search",
            params={
                "engine": "google_images",
                "q": query,
                "api_key": serpapi_key,
                "gl": "cl",
                "hl": "es",
                "num": 8,
            },
            timeout=20,
            verify=False,
        )
        if r.status_code == 200:
            for item in r.json().get("images_results", []) or []:
                u = item.get("original")
                if u:
                    urls.append(u)
        else:
            print(f"  -> SerpAPI HTTP {r.status_code}: {r.text[:120]}")
    # filtrar + rankear
    filtered = [u for u in urls if u and not u.startswith("data:") and domain_ok(u)]
    filtered.sort(key=prefer_score, reverse=True)
    return filtered


def ensure_bucket(supabase_url: str, supabase_key: str, bucket: str) -> None:
    r = requests.post(
        f"{supabase_url.rstrip('/')}/storage/v1/bucket",
        headers={
            "Authorization": f"Bearer {supabase_key}",
            "apikey": supabase_key,
            "Content-Type": "application/json",
        },
        json={"id": bucket, "name": bucket, "public": True},
        timeout=20,
        verify=False,
    )
    if r.status_code in (200, 201):
        print(f"[*] Bucket '{bucket}' creado.")
    elif r.status_code == 400 or "already exists" in (r.text or "").lower():
        print(f"[*] Bucket '{bucket}' OK.")
    else:
        print(f"[WARN] bucket: {r.status_code} {r.text[:160]}")


def download_and_upload(
    src_url: str,
    product_code: str,
    supabase_url: str,
    supabase_key: str,
    bucket: str,
) -> str | None:
    try:
        # Algunos resultados vienen con host percent-encoded (rompe DNS).
        src_url = unquote(src_url.strip())
        parsed = urlparse(src_url)
        if not parsed.scheme or not parsed.hostname or "%" in parsed.hostname:
            return None
        r = requests.get(
            src_url,
            timeout=20,
            verify=False,
            headers={"User-Agent": UA, "Accept": "image/*,*/*"},
        )
        if r.status_code != 200 or not r.content or len(r.content) < 1500:
            return None
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "html" in ctype:
            return None
        ext = "jpg"
        if "png" in ctype or src_url.lower().endswith(".png"):
            ext = "png"
        elif "webp" in ctype or src_url.lower().endswith(".webp"):
            ext = "webp"
        elif "jpeg" in ctype or "jpg" in ctype:
            ext = "jpg"
        filename = f"{product_code}.{ext}"
        upload = requests.post(
            f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{filename}",
            headers={
                "Authorization": f"Bearer {supabase_key}",
                "apikey": supabase_key,
                "Content-Type": ctype or f"image/{ext}",
                "x-upsert": "true",
            },
            data=r.content,
            timeout=30,
            verify=False,
        )
        if upload.status_code not in (200, 201):
            print(f"  -> upload FAIL {upload.status_code}: {upload.text[:120]}")
            return None
        return f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket}/{filename}"
    except Exception as exc:
        print(f"  -> download/upload skip: {exc}")
        return None


async def main() -> None:
    load_dotenv(ROOT / ".env")
    load_dotenv(Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"))
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only-mccain", action="store_true")
    parser.add_argument("--forzar", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.25)
    args = parser.parse_args()

    supabase_url = (os.getenv("SUPABASE_URL") or "").strip()
    supabase_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    serper_key = (os.getenv("SERPER_API_KEY") or "").strip() or None
    serpapi_key = (os.getenv("SERPAPI_API_KEY") or "").strip() or None
    provider = (os.getenv("SEARCH_PROVIDER") or "serper").strip().lower()
    if provider not in ("serper", "serpapi"):
        provider = "serper" if serper_key else "serpapi"

    if not supabase_url or not supabase_key:
        raise SystemExit("[FAIL] Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")
    if not serper_key and not serpapi_key and not args.only_mccain:
        raise SystemExit("[FAIL] Falta SERPER_API_KEY o SERPAPI_API_KEY")

    ensure_bucket(supabase_url, supabase_key, BUCKET)

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        products = await conn.fetch(
            f"""
            SELECT product_code, nombre, image_url
            FROM {SCHEMA}.productos
            ORDER BY product_code
            """
        )
    finally:
        await conn.close()

    todo = []
    for p in products:
        if args.only_mccain and "MCCAIN" not in (p["nombre"] or "").upper():
            continue
        if args.forzar or needs_image(p["image_url"]):
            todo.append(p)
    if args.limit:
        todo = todo[: args.limit]

    print(f"[*] Productos a enriquecer: {len(todo)} (provider={provider})")
    mappings: dict[str, str] = {}
    report = []

    async def apply_one(code: str, public_url: str) -> None:
        """Reconnect per write — evita ConnectionDoesNotExist en corridas largas."""
        c = await asyncpg.connect(_db_url(), statement_cache_size=0)
        try:
            await c.execute(
                f"""
                UPDATE {SCHEMA}.productos
                SET image_url = $1, updated_at = now()
                WHERE product_code = $2
                """,
                public_url,
                code,
            )
        finally:
            await c.close()

    for i, p in enumerate(todo, 1):
        code = p["product_code"]
        name = p["nombre"]
        print(f"[{i}/{len(todo)}] {code} | {name}")

        candidates: list[str] = []
        direct = mccain_direct_url(name)
        source = "none"
        if direct:
            candidates.append(direct)
            source = "mccain.com.ar"

        if not args.only_mccain or not candidates:
            q = brand_boost_query(name)
            found = search_images(q, serper_key, serpapi_key, provider)
            for u in found:
                if u not in candidates:
                    candidates.append(u)
            if found and source == "none":
                source = "serper"

        public_url = None
        used_src = None
        for src in candidates[:6]:
            print(f"  try {src[:90]}")
            public_url = download_and_upload(src, code, supabase_url, supabase_key, BUCKET)
            if public_url:
                used_src = src
                break

        if public_url:
            mappings[code] = public_url
            print(f"  OK ({source}) → {public_url}")
            if args.apply:
                try:
                    await apply_one(code, public_url)
                except Exception as exc:
                    print(f"  -> DB update retry: {exc}")
                    await asyncio.sleep(1)
                    await apply_one(code, public_url)
        else:
            print("  FAIL sin imagen")

        report.append(
            {
                "product_code": code,
                "nombre": name,
                "source": source,
                "src_url": used_src or "",
                "image_url": public_url or "",
                "ok": bool(public_url),
            }
        )
        time.sleep(args.sleep)

    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "phase-01-imagenes-marcas.csv"
    # append-friendly: rewrite full report of this run
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["product_code", "nombre", "source", "src_url", "image_url", "ok"],
        )
        w.writeheader()
        w.writerows(report)
    print(f"[*] CSV {csv_path} ({sum(1 for r in report if r['ok'])}/{len(report)} OK)")

    if not args.apply:
        print("[*] Dry-run. Usá --apply para actualizar dimer.productos")
        return

    if mappings:
        local_csv = OUT / "phase-01-productos.csv"
        if local_csv.exists():
            rows = []
            with local_csv.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames or []
                for row in reader:
                    if row.get("product_code") in mappings:
                        row["image_url"] = mappings[row["product_code"]]
                    rows.append(row)
            with local_csv.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            print("[*] CSV catálogo sincronizado")

        backend = (os.getenv("BACKEND_URL") or "https://web-production-f544f.up.railway.app").rstrip("/")
        try:
            resp = requests.post(
                f"{backend}/{SCHEMA}/productos/vectorize",
                json=list(mappings.keys()),
                timeout=30,
                verify=False,
            )
            print(f"[*] vectorize HTTP {resp.status_code}")
        except Exception as exc:
            print(f"[WARN] vectorize: {exc}")

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        left = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM {SCHEMA}.productos
            WHERE image_url IS NULL OR image_url ILIKE '%placehold%'
            """
        )
    finally:
        await conn.close()
    print(f"[*] Placeholders restantes: {left}")
    print(f"[*] Imágenes aplicadas en esta corrida: {len(mappings)}")


if __name__ == "__main__":
    asyncio.run(main())
