#!/usr/bin/env python3
"""Carga Fase 1 catálogo en schema quimica_vm desde CSVs."""
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

SCHEMA = "quimica_vm"
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
N_LISTAS = 4
BATCH = 80


def _load_envs() -> None:
    for path in (
        ROOT / ".env",
        ROOT.parent / "backend-supabase" / ".env",
        Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
    ):
        if path.exists():
            load_dotenv(path)


_load_envs()


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def normalizar_alias(alias_raw: str) -> str:
    alias_flat = unicodedata.normalize("NFKD", alias_raw.lower().strip())
    ascii_txt = alias_flat.encode("ascii", "ignore").decode("ascii")
    return "".join(c for c in ascii_txt if c.isalnum())


def truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "t", "yes", "si", "sí"}


async def cargar() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)

    products = list(csv.DictReader((OUT / "phase-01-productos.csv").open(encoding="utf-8")))
    print(f"[*] Schema={SCHEMA} | productos CSV={len(products)}")

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        counts = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.productos) AS productos,
              (SELECT COUNT(*) FROM {SCHEMA}.precios_productos) AS precios,
              (SELECT COUNT(*) FROM {SCHEMA}.listas_precios) AS listas,
              (SELECT COUNT(*) FROM {SCHEMA}.productos_aliases) AS aliases
            """
        )
        if counts["productos"] > 0:
            print(
                f"[FAIL] {SCHEMA} ya tiene datos (productos={counts['productos']}, precios={counts['precios']}). Aborto.",
                file=sys.stderr,
            )
            return 1

        await conn.execute(
            f"""
            INSERT INTO {SCHEMA}.listas_precios
              (id, nombre, descripcion, activa, es_publica, is_mock, created_at, updated_at)
            OVERRIDING SYSTEM VALUE
            VALUES
              (1, 'Lista 1', 'Lista revendedor septiembre 2026 (sin IVA)', true, true, false, now(), now()),
              (2, 'Lista 2', 'Lista Minorista Sugerido', true, true, true, now(), now()),
              (3, 'Lista 3', 'Lista Mayorista Especial', true, true, true, now(), now()),
              (4, 'Lista 4', 'Lista Gran Distribuidor', true, true, true, now(), now())
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
            f"SELECT setval(pg_get_serial_sequence('{SCHEMA}.listas_precios', 'id'), {N_LISTAS}, true)"
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
                    truthy(p.get("is_mock") or "false"),
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
                    unidad_minima_de_venta, umv_tipo, rotacion_index, mental_priority,
                    en_catalogo, is_mock, created_at, updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12, now(), now())
                """,
                chunk,
            )

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

        prices_inserted = 0
        for list_id in range(1, N_LISTAS + 1):
            prices_data = []
            with (OUT / f"phase-01-lista-precios-{list_id}.csv").open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    prices_data.append(
                        (
                            row["product_code"].strip(),
                            list_id,
                            float(row["precio_unidad"]),
                            truthy(row.get("is_mock") or "false"),
                        )
                    )
            print(f"[*] Insertando lista {list_id}: {len(prices_data)} precios...")
            for i in range(0, len(prices_data), BATCH):
                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.precios_productos (
                        product_code, lista_precios_id, precio_unidad, is_mock
                    ) VALUES ($1,$2,$3,$4)
                    """,
                    prices_data[i : i + BATCH],
                )
            prices_inserted += len(prices_data)

        verify = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.productos) AS productos,
              (SELECT COUNT(*) FROM {SCHEMA}.listas_precios WHERE activa AND es_publica) AS listas,
              (SELECT COUNT(*) FROM {SCHEMA}.precios_productos) AS precios,
              (SELECT COUNT(*) FROM {SCHEMA}.productos_aliases) AS aliases
            """
        )
        print(
            f"[VERIFY] productos={verify['productos']} listas={verify['listas']} "
            f"precios={verify['precios']} aliases={verify['aliases']} "
            f"(precios_insertados={prices_inserted})"
        )
        if verify["productos"] != len(products) or verify["precios"] != len(products) * N_LISTAS:
            print("[FAIL] Conteos no coinciden con el CSV", file=sys.stderr)
            return 1
    finally:
        await conn.close()

    backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
    vec_url = f"{backend_url}/{SCHEMA}/productos/vectorize"
    print(f"[*] Vectorize POST {vec_url} ({len(product_codes)} codes)...")
    try:
        resp = requests.post(vec_url, json=product_codes, timeout=90)
        print(f"[*] vectorize HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[WARN] vectorize falló: {e}")
    print(f"OK carga catálogo {SCHEMA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(cargar()))
