#!/usr/bin/env python3
"""DEV-125 — carga en tandas las imágenes propuestas en outputs/phase-01-imagenes-propuesta.csv.

Por cada fila: baja la imagen de la tienda, la sube a Supabase Storage
(`products-esekau/{product_code}.{ext}`) y deja `esekau.productos.image_url` con la URL pública.
Solo toca productos que hoy no tienen imagen (salvo `--forzar`).

Sin `--apply` es un ensayo: baja la imagen y valida, pero no sube ni escribe.

Uso (lo corre la sesión padre con el ok de Faka):
  set -a && source ../backend-supabase/.env && set +a     # SUPABASE_DB_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
  python implementacion/esekau/scripts/cargar_imagenes.py --tanda 1               # ensayo
  python implementacion/esekau/scripts/cargar_imagenes.py --tanda 1 --apply       # combos, primeros 100
  python implementacion/esekau/scripts/cargar_imagenes.py --tanda 2 --apply       # ...
  python implementacion/esekau/scripts/cargar_imagenes.py --confianza alta --tanda 1 --apply

Las tandas son de `--tamano` filas (100 por defecto) en el orden del CSV: combos primero.
Deja un log por tanda en outputs/phase-01-imagenes-carga-tanda-{n}.csv.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path

import asyncpg
import requests

SCHEMA = "esekau"
BUCKET = f"products-{SCHEMA}"
ROOT = Path(__file__).resolve().parents[1]
PROPUESTA = ROOT / "outputs" / "phase-01-imagenes-propuesta.csv"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
EXT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}


def db_url() -> str:
    url = (os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "").strip()
    if not url:
        sys.exit("[FAIL] Falta SUPABASE_DB_URL")
    return url.replace(":5432/", ":6543/")


def bajar(url: str) -> tuple[bytes, str] | None:
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "image/*"}, timeout=30)
    ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if r.status_code != 200 or ctype not in EXT or len(r.content) < 2000:
        return None
    return r.content, ctype


def asegurar_bucket(base: str, key: str) -> None:
    r = requests.post(
        f"{base}/storage/v1/bucket",
        headers={"Authorization": f"Bearer {key}", "apikey": key},
        json={"id": BUCKET, "name": BUCKET, "public": True},
        timeout=20,
    )
    if r.status_code not in (200, 201) and "already exists" not in r.text.lower():
        sys.exit(f"[FAIL] bucket {BUCKET}: {r.status_code} {r.text[:200]}")


def subir(base: str, key: str, code: str, contenido: bytes, ctype: str) -> str | None:
    nombre = f"{code}.{EXT[ctype]}"
    r = requests.post(
        f"{base}/storage/v1/object/{BUCKET}/{nombre}",
        headers={"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": ctype, "x-upsert": "true"},
        data=contenido,
        timeout=60,
    )
    if r.status_code not in (200, 201):
        print(f"  upload {r.status_code}: {r.text[:160]}")
        return None
    return f"{base}/storage/v1/object/public/{BUCKET}/{nombre}"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tanda", type=int, required=True, help="número de tanda, desde 1")
    ap.add_argument("--tamano", type=int, default=100)
    ap.add_argument("--confianza", choices=["alta", "media"], default="media",
                    help="mínima confianza a cargar (media incluye alta)")
    ap.add_argument("--apply", action="store_true", help="subir a Storage y escribir en la BD")
    ap.add_argument("--forzar", action="store_true", help="pisar productos que ya tienen imagen")
    args = ap.parse_args()

    filas = [r for r in csv.DictReader(PROPUESTA.open(encoding="utf-8"))
             if args.confianza == "media" or r["confianza"] == "alta"]
    tanda = filas[(args.tanda - 1) * args.tamano: args.tanda * args.tamano]
    if not tanda:
        sys.exit(f"[FAIL] La tanda {args.tanda} está vacía ({len(filas)} filas en total)")
    print(f"[*] Tanda {args.tanda}: {len(tanda)} de {len(filas)} filas | apply={args.apply}")

    base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if args.apply and (not base or not key):
        sys.exit("[FAIL] Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")

    conn = await asyncpg.connect(db_url(), statement_cache_size=0)
    try:
        actuales = {
            r["product_code"]: r["image_url"]
            for r in await conn.fetch(
                f"SELECT product_code, image_url FROM {SCHEMA}.productos WHERE product_code = ANY($1::text[])",
                [f["product_code"] for f in tanda],
            )
        }
        if args.apply:
            asegurar_bucket(base, key)
        log = []
        for f in tanda:
            code = f["product_code"]
            estado = ""
            if code not in actuales:
                estado = "no_existe_en_bd"
            elif (actuales[code] or "").strip() and not args.forzar:
                estado = "ya_tiene_imagen"
            else:
                img = bajar(f["image_url"])
                if not img:
                    estado = "descarga_fallida"
                elif not args.apply:
                    estado = "ok_ensayo"
                else:
                    publica = subir(base, key, code, *img)
                    if not publica:
                        estado = "upload_fallido"
                    else:
                        await conn.execute(
                            f"UPDATE {SCHEMA}.productos SET image_url = $1, updated_at = now() "
                            f"WHERE product_code = $2 AND (coalesce(image_url, '') = '' OR $3)",
                            publica, code, args.forzar,
                        )
                        estado = "cargada"
                        f = {**f, "image_url_storage": publica}
            print(f"  {code} {f['nombre'][:50]} → {estado}")
            log.append({"product_code": code, "nombre": f["nombre"], "estado": estado,
                        "image_url_fuente": f["image_url"], "image_url_storage": f.get("image_url_storage", "")})
    finally:
        await conn.close()

    out = ROOT / "outputs" / f"phase-01-imagenes-carga-tanda-{args.tanda}.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(log[0]))
        w.writeheader()
        w.writerows(log)
    resumen: dict[str, int] = {}
    for r in log:
        resumen[r["estado"]] = resumen.get(r["estado"], 0) + 1
    print(f"[*] {resumen} → {out.name}")


if __name__ == "__main__":
    asyncio.run(main())
