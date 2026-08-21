#!/usr/bin/env python3
"""Carga Fase 1 catálogo demo en schema rawson desde CSVs."""
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

SCHEMA = "rawson"  # confirmado dos veces: implementador + manifest
HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
OUT = HERE.parents[1] / "outputs"
N_LISTAS = 4
BATCH = 80


def _load_envs() -> None:
    candidates = [
        ROOT / ".env",
        ROOT.parent / "backend-supabase" / ".env",
        ROOT.parents[2] / "backend-supabase" / ".env" if len(ROOT.parents) >= 2 else None,
        Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
    ]
    for path in candidates:
        if path and path.exists():
            load_dotenv(path)


_load_envs()


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def normalizar_alias(alias_raw: str) -> str:
    alias_lower = alias_raw.lower().strip()
    alias_flat = unicodedata.normalize("NFKD", alias_lower)
    return "".join(c for c in alias_flat if ("a" <= c <= "z") or ("0" <= c <= "9"))


def truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "t", "yes", "si", "sí"}


async def cargar() -> int:
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)

    products_csv = OUT / "phase-01-productos.csv"
    if not products_csv.exists():
        print(f"[FAIL] No existe {products_csv}", file=sys.stderr)
        return 1

    products = list(csv.DictReader(products_csv.open(encoding="utf-8")))
    print(f"[*] Schema={SCHEMA} | productos CSV={len(products)}")

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0;")

        counts = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.productos) AS productos,
              (SELECT COUNT(*) FROM {SCHEMA}.precios_productos) AS precios
            """
        )
        if counts["productos"] > 0 or counts["precios"] > 0:
            print(
                f"[FAIL] {SCHEMA} ya tiene datos (productos={counts['productos']}, precios={counts['precios']}). Aborto.",
                file=sys.stderr,
            )
            return 1

        print("[*] Insertando 4 listas de precios (activa+es_publica) en rawson...")
        await conn.execute(
            f"""
            INSERT INTO {SCHEMA}.listas_precios
              (id, nombre, descripcion, activa, es_publica, is_mock, created_at, updated_at)
            OVERRIDING SYSTEM VALUE
            VALUES
              (1, 'Lista Base (Público)', 'Precio web / mostrador', true, true, true, now(), now()),
              (2, 'Lista Minorista Sugerido', 'Minorista +15%%', true, true, true, now(), now()),
              (3, 'Lista Mayorista Especial', 'Mayorista -10%%', true, true, true, now(), now()),
              (4, 'Lista Gran Distribuidor', 'Gran distribuidor -15%%', true, true, true, now(), now())
            ON CONFLICT (id) DO UPDATE SET
              nombre = EXCLUDED.nombre,
              descripcion = EXCLUDED.descripcion,
              activa = EXCLUDED.activa,
              es_publica = EXCLUDED.es_publica,
              is_mock = EXCLUDED.is_mock,
              updated_at = now()
            """
        )
        await conn.execute(
            f"SELECT setval(pg_get_serial_sequence('{SCHEMA}.listas_precios', 'id'), 4, true)"
        )

        products_data = []
        aliases_data = []
        product_codes: list[str] = []
        seen_alias: set[tuple[str, str]] = set()

        for p in products:
            code = p["product_code"].strip()
            product_codes.append(code)
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
                    truthy(p.get("is_mock") or "true"),
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

        print(f"[*] Insertando {len(products_data)} productos en rawson...")
        for i in range(0, len(products_data), BATCH):
            chunk = products_data[i : i + BATCH]
            await conn.executemany(
                f"""
                INSERT INTO {SCHEMA}.productos (
                    product_code, nombre, descripcion, image_url, stock, unidades_por_bulto,
                    unidad_minima_de_venta, umv_tipo, rotacion_index, mental_priority,
                    en_catalogo, is_mock, created_at, updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12, now(), now())
                """,
                chunk,
            )

        if aliases_data:
            print(f"[*] Insertando {len(aliases_data)} aliases en rawson...")
            for i in range(0, len(aliases_data), BATCH):
                chunk = aliases_data[i : i + BATCH]
                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.productos_aliases (
                        product_code, alias_raw, alias_norm, weight, created_at, updated_at
                    ) VALUES ($1,$2,$3,$4, now(), now())
                    ON CONFLICT (product_code, alias_norm) DO NOTHING
                    """,
                    chunk,
                )

        prices_inserted = 0
        for list_id in range(1, N_LISTAS + 1):
            price_csv = OUT / f"phase-01-lista-precios-{list_id}.csv"
            if not price_csv.exists():
                print(f"[FAIL] Falta {price_csv}", file=sys.stderr)
                return 1
            prices_data = []
            with price_csv.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    prices_data.append(
                        (
                            row["product_code"].strip(),
                            list_id,
                            float(row["precio_unidad"]),
                            truthy(row.get("is_mock") or "true"),
                        )
                    )
            print(f"[*] Insertando lista {list_id} en rawson: {len(prices_data)} precios...")
            for i in range(0, len(prices_data), BATCH):
                chunk = prices_data[i : i + BATCH]
                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.precios_productos (
                        product_code, lista_precios_id, precio_unidad, is_mock
                    ) VALUES ($1,$2,$3,$4)
                    """,
                    chunk,
                )
            prices_inserted += len(prices_data)

        verify = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.productos) AS productos,
              (SELECT COUNT(*) FROM {SCHEMA}.listas_precios) AS listas,
              (SELECT COUNT(*) FROM {SCHEMA}.precios_productos) AS precios,
              (SELECT COUNT(*) FROM {SCHEMA}.productos_aliases) AS aliases
            """
        )
        sample = await conn.fetch(
            f"""
            SELECT p.product_code, p.nombre, pp.lista_precios_id, pp.precio_unidad
            FROM {SCHEMA}.productos p
            JOIN {SCHEMA}.precios_productos pp ON pp.product_code = p.product_code
            WHERE pp.lista_precios_id = 1
            ORDER BY p.product_code
            LIMIT 3
            """
        )
        print(
            f"[VERIFY] productos={verify['productos']} listas={verify['listas']} "
            f"precios={verify['precios']} aliases={verify['aliases']} "
            f"(precios_insertados={prices_inserted})"
        )
        for s in sample:
            print(f"  sample {s['product_code']} | {s['nombre'][:40]} | L{s['lista_precios_id']}={s['precio_unidad']}")

        if verify["productos"] != len(products):
            print(f"[FAIL] Conteo productos {verify['productos']} != CSV {len(products)}", file=sys.stderr)
            return 1
        expected_prices = len(products) * N_LISTAS
        if verify["precios"] != expected_prices:
            print(f"[FAIL] Conteo precios {verify['precios']} != esperado {expected_prices}", file=sys.stderr)
            return 1
        if verify["listas"] != N_LISTAS:
            print(f"[FAIL] Conteo listas {verify['listas']} != {N_LISTAS}", file=sys.stderr)
            return 1

    finally:
        await conn.close()

    backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
    vec_url = f"{backend_url}/{SCHEMA}/productos/vectorize"
    print(f"[*] Vectorize POST {vec_url} ({len(product_codes)} codes)...")
    try:
        resp = requests.post(vec_url, json=product_codes, timeout=60)
        if resp.status_code == 200:
            print(f"  … vectorize OK ({resp.text[:160]})")
        else:
            print(f"[WARN] vectorize HTTP {resp.status_code}: {resp.text[:300]}")
    except Exception as e:
        print(f"[WARN] vectorize falló: {e}")

    print("OK carga catálogo rawson completada")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(cargar()))
