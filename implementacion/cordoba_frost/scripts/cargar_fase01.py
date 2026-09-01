#!/usr/bin/env python3
"""Alta incremental catálogo PRODUCTOS GRAL en schema cordoba_frost.

schema_name = cordoba_frost (confirmado por el implementador: confirmar carga).
Solo Lista General (id=1). is_mock=false. No toca combos de helados ni ENVIO-DOM.
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys
import unicodedata
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "cordoba_frost"  # confirmado: implementador
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
PROD_CSV = OUT / "phase-01-productos-gral.csv"
PRICE_CSV = OUT / "phase-01-lista-precios-1-gral.csv"
LISTA_ID = 1
BATCH = 80


def force_pooler(url: str) -> str:
    url = url.replace(":5432/", ":6543/")
    url = url.replace(":5432@", ":6543@")
    return url


def _load_envs() -> None:
    for path in (
        ROOT.parent / "backend-supabase" / ".env",
        ROOT / ".env",
    ):
        if path.exists():
            load_dotenv(path, override=False)
            print(f"[*] env: {path}")


_load_envs()


def normalizar_alias(alias_raw: str) -> str:
    alias_flat = unicodedata.normalize("NFKD", alias_raw.lower().strip())
    ascii_txt = alias_flat.encode("ascii", "ignore").decode("ascii")
    return "".join(c for c in ascii_txt if c.isalnum())


def truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "t", "yes", "si", "sí"}


async def cargar() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    print(f"[*] tenant destino: {SCHEMA} (productivo, alta incremental PRODUCTOS GRAL)")
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)

    products = list(csv.DictReader(PROD_CSV.open(encoding="utf-8")))
    prices = list(csv.DictReader(PRICE_CSV.open(encoding="utf-8")))
    print(f"[*] Schema={SCHEMA} | productos CSV={len(products)} | precios CSV={len(prices)}")
    if len(products) != 279:
        print(f"[FAIL] Se esperaban 279 filas, hay {len(products)}", file=sys.stderr)
        return 1

    pool = await asyncpg.create_pool(
        db_url,
        min_size=1,
        max_size=2,
        statement_cache_size=0,
    )
    inserted_codes: list[str] = []
    try:
        async with pool.acquire() as conn:
            await conn.execute("SET statement_timeout = 0")
            lista = await conn.fetchrow(
                f"""
                SELECT id, nombre, activa, es_publica
                FROM {SCHEMA}.listas_precios
                WHERE id = $1
                """,
                LISTA_ID,
            )
            if not lista or not lista["activa"] or not lista["es_publica"]:
                print("[FAIL] Lista General (id=1) no está activa y pública", file=sys.stderr)
                return 1

            existing = {
                r["product_code"]
                for r in await conn.fetch(f"SELECT product_code FROM {SCHEMA}.productos")
            }
            to_insert = [p for p in products if p["product_code"].strip() not in existing]
            skipped = [p["product_code"] for p in products if p["product_code"].strip() in existing]
            if skipped:
                print(f"[*] Ya en BD, se omiten: {skipped}")
            print(f"[*] A insertar: {len(to_insert)} (existentes en BD: {len(existing)})")

            products_data = []
            aliases_data = []
            seen_alias: set[tuple[str, str]] = set()
            for p in to_insert:
                code = p["product_code"].strip()
                inserted_codes.append(code)
                umv = (p.get("unidad_minima_de_venta") or "unidad").strip() or "unidad"
                umv_tipo = (p.get("umv_tipo") or "unidad").strip() or "unidad"
                if umv_tipo not in ("unidad", "display"):
                    umv_tipo = "unidad"
                products_data.append(
                    (
                        code,
                        p["nombre"],
                        p.get("descripcion") or None,
                        (p.get("image_url") or "").strip() or None,
                        int(float(p["stock"])) if p.get("stock") else 0,
                        int(float(p["unidades_por_bulto"])) if p.get("unidades_por_bulto") else 1,
                        umv,
                        umv_tipo,
                        float(p["rotacion_index"]) if p.get("rotacion_index") else 0.1,
                        float(p["mental_priority"]) if p.get("mental_priority") else 0.0,
                        truthy(p.get("en_catalogo") or "true"),
                        truthy(p.get("is_mock") or "false"),
                        truthy(p.get("es_pesable") or "false"),
                    )
                )
                for raw in (p.get("aliases") or "").split("|"):
                    raw = raw.strip()
                    if not raw:
                        continue
                    norm = normalizar_alias(raw)
                    if not norm:
                        continue
                    key = (norm, code)
                    if key in seen_alias:
                        continue
                    seen_alias.add(key)
                    aliases_data.append((code, raw, norm, 1.0))

            print(f"[*] Insertando {len(products_data)} productos en {SCHEMA}...")
            for i in range(0, len(products_data), BATCH):
                chunk = products_data[i : i + BATCH]
                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.productos (
                        product_code, nombre, descripcion, image_url, stock, unidades_por_bulto,
                        unidad_minima_de_venta, umv_tipo, cantidad_minima_de_venta,
                        rotacion_index, mental_priority,
                        en_catalogo, is_mock, es_pesable, created_at, updated_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,1,$9,$10,$11,$12,$13, now(), now())
                    """,
                    chunk,
                )
                print(f"    productos {i + 1}–{i + len(chunk)}")

            if aliases_data:
                print(f"[*] Insertando {len(aliases_data)} aliases en {SCHEMA}...")
                for i in range(0, len(aliases_data), BATCH):
                    chunk = aliases_data[i : i + BATCH]
                    await conn.executemany(
                        f"""
                        INSERT INTO {SCHEMA}.productos_aliases (
                            product_code, alias_raw, alias_norm, weight, created_at, updated_at
                        ) VALUES ($1,$2,$3,$4, now(), now())
                        ON CONFLICT (alias_norm, product_code) DO NOTHING
                        """,
                        chunk,
                    )

            price_rows = []
            new_set = set(inserted_codes)
            for row in prices:
                code = row["product_code"].strip()
                if code not in new_set:
                    continue
                price_rows.append(
                    (code, LISTA_ID, float(row["precio_unidad"]), False)
                )
            print(f"[*] Insertando {len(price_rows)} precios lista {LISTA_ID} en {SCHEMA}...")
            for i in range(0, len(price_rows), BATCH):
                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.precios_productos (
                        product_code, lista_precios_id, precio_unidad, is_mock
                    ) VALUES ($1,$2,$3,$4)
                    ON CONFLICT (product_code, lista_precios_id) DO UPDATE SET
                        precio_unidad = EXCLUDED.precio_unidad,
                        is_mock = EXCLUDED.is_mock,
                        updated_at = now()
                    """,
                    price_rows[i : i + BATCH],
                )

            verify = await conn.fetchrow(
                f"""
                SELECT
                  (SELECT COUNT(*) FROM {SCHEMA}.productos) AS productos,
                  (SELECT COUNT(*) FROM {SCHEMA}.productos WHERE product_code = ANY($1::text[])) AS nuevos,
                  (SELECT COUNT(*) FROM {SCHEMA}.precios_productos WHERE product_code = ANY($1::text[])) AS precios_nuevos,
                  (SELECT COUNT(*) FROM {SCHEMA}.productos_aliases WHERE product_code = ANY($1::text[])) AS aliases_nuevos,
                  (SELECT COUNT(*) FROM {SCHEMA}.productos WHERE product_code IN
                    ('COM-HEL-INICIAL','COM-HEL-MEDIO','COM-HEL-PREMIUM','ENVIO-DOM')) AS conservados
                """,
                inserted_codes,
            )
            print(
                f"[VERIFY] productos_total={verify['productos']} nuevos={verify['nuevos']} "
                f"precios_nuevos={verify['precios_nuevos']} aliases_nuevos={verify['aliases_nuevos']} "
                f"helados+envio={verify['conservados']}"
            )
            if verify["nuevos"] != len(inserted_codes):
                print("[FAIL] Conteos de productos nuevos no coinciden", file=sys.stderr)
                return 1
            if verify["precios_nuevos"] != len(inserted_codes):
                print("[FAIL] Faltan precios de lista 1", file=sys.stderr)
                return 1
            if verify["conservados"] != 4:
                print("[WARN] No se encontraron los 3 combos helados + ENVIO-DOM")
    finally:
        await pool.close()

    if not inserted_codes:
        print("[*] Nada nuevo para vectorizar")
        return 0

    backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
    vec_url = f"{backend_url}/{SCHEMA}/productos/vectorize"
    print(f"[*] Vectorize POST {vec_url} ({len(inserted_codes)} codes)...")
    try:
        for i in range(0, len(inserted_codes), 200):
            chunk = inserted_codes[i : i + 200]
            resp = requests.post(vec_url, json=chunk, timeout=120)
            print(f"  … vectorize HTTP {resp.status_code} chunk {i // 200 + 1}: {resp.text[:200]}")
            if resp.status_code != 200:
                print("[WARN] vectorize no devolvió 200")
    except Exception as e:
        print(f"[WARN] vectorize falló: {e}")
    print(f"[SUCCESS] alta catálogo {SCHEMA} ({len(inserted_codes)} SKUs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(cargar()))
