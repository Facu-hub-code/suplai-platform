#!/usr/bin/env python3
"""Carga la Fase 1 aprobada del piloto interno AB Mauri."""
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

SCHEMA = "abmauri"
EXPECTED = 182
BATCH = 80
HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
OUT = HERE.parents[1] / "outputs"


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def load_env() -> None:
    for path in (
        Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
        ROOT / ".env",
    ):
        if path.exists():
            load_dotenv(path, override=False)
    url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or ""
    if url:
        pooler_url = force_pooler(url)
        os.environ["SUPABASE_DB_URL_POOLER"] = pooler_url
        os.environ["SUPABASE_DB_URL"] = pooler_url


def truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "t", "yes", "si", "sí"}


def normalized_alias(value: str) -> str:
    flat = unicodedata.normalize("NFKD", value.lower().strip())
    ascii_text = flat.encode("ascii", "ignore").decode("ascii")
    return "".join(character for character in ascii_text if character.isalnum())


def read_csv(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


load_env()


async def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1

    products = read_csv("phase-01-productos.csv")
    prices = read_csv("phase-01-lista-precios-1.csv")
    if len(products) != EXPECTED or len(prices) != EXPECTED:
        print(
            f"[FAIL] Conteo CSV inesperado: productos={len(products)} precios={len(prices)}",
            file=sys.stderr,
        )
        return 1
    if any(truthy(row["is_mock"]) for row in products):
        print("[FAIL] Los productos reales no pueden tener is_mock=true", file=sys.stderr)
        return 1
    if any(not truthy(row["is_mock"]) for row in prices):
        print("[FAIL] Los precios del piloto deben tener is_mock=true", file=sys.stderr)
        return 1

    product_rows: list[tuple[object, ...]] = []
    alias_rows: list[tuple[object, ...]] = []
    seen_aliases: set[tuple[str, str]] = set()
    product_codes: list[str] = []
    for row in products:
        code = row["product_code"].strip()
        product_codes.append(code)
        product_rows.append(
            (
                code,
                row["nombre"].strip(),
                row["descripcion"].strip() or None,
                row["image_url"].strip() or None,
                int(float(row["stock"])),
                int(float(row["unidades_por_bulto"])),
                row["unidad_minima_de_venta"].strip() or "unidad",
                row["umv_tipo"].strip() or "unidad",
                float(row["rotacion_index"]),
                float(row["mental_priority"]),
                truthy(row["en_catalogo"]),
                False,
            )
        )
        for raw in row["aliases"].split("|"):
            raw = raw.strip()
            norm = normalized_alias(raw)
            key = (norm, code)
            if not norm or key in seen_aliases:
                continue
            seen_aliases.add(key)
            alias_rows.append((code, raw, norm, 1.0))

    price_rows = [
        (
            row["product_code"].strip(),
            1,
            float(row["precio_unidad"]),
            True,
        )
        for row in prices
    ]
    if set(product_codes) != {row[0] for row in price_rows}:
        print("[FAIL] Los códigos de productos y precios no coinciden", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        before = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.productos) AS productos,
              (SELECT COUNT(*) FROM {SCHEMA}.listas_precios) AS listas,
              (SELECT COUNT(*) FROM {SCHEMA}.precios_productos) AS precios,
              (SELECT COUNT(*) FROM {SCHEMA}.productos_aliases) AS aliases
            """
        )
        if any(before[key] for key in ("productos", "listas", "precios", "aliases")):
            print(f"[FAIL] El catálogo destino no está vacío: {dict(before)}", file=sys.stderr)
            return 1

        async with conn.transaction():
            await conn.execute(
                f"""
                INSERT INTO {SCHEMA}.listas_precios (
                    id, nombre, descripcion, activa, es_publica, is_mock,
                    created_at, updated_at
                )
                OVERRIDING SYSTEM VALUE
                VALUES (
                    1,
                    'Piloto interno - precios estimados',
                    'Referencias web y fallback determinístico; reemplazar antes de producción',
                    true, true, true, now(), now()
                )
                """
            )

            for index in range(0, len(product_rows), BATCH):
                chunk = product_rows[index : index + BATCH]
                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.productos (
                        product_code, nombre, descripcion, image_url, stock,
                        unidades_por_bulto, unidad_minima_de_venta, umv_tipo,
                        rotacion_index, mental_priority, en_catalogo, is_mock,
                        created_at, updated_at
                    )
                    VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,now(),now()
                    )
                    """,
                    chunk,
                )
                print(f"    productos {index + 1}-{index + len(chunk)}")

            for index in range(0, len(alias_rows), BATCH):
                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.productos_aliases (
                        product_code, alias_raw, alias_norm, weight,
                        created_at, updated_at
                    )
                    VALUES ($1,$2,$3,$4,now(),now())
                    ON CONFLICT (alias_norm, product_code) DO NOTHING
                    """,
                    alias_rows[index : index + BATCH],
                )

            for index in range(0, len(price_rows), BATCH):
                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.precios_productos (
                        product_code, lista_precios_id, precio_unidad, is_mock
                    )
                    VALUES ($1,$2,$3,$4)
                    """,
                    price_rows[index : index + BATCH],
                )
                print(f"    precios {index + 1}-{index + len(price_rows[index:index + BATCH])}")

        after = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.productos) AS productos,
              (SELECT COUNT(*) FROM {SCHEMA}.listas_precios
               WHERE activa AND es_publica AND is_mock) AS listas,
              (SELECT COUNT(*) FROM {SCHEMA}.precios_productos
               WHERE is_mock) AS precios,
              (SELECT COUNT(*) FROM {SCHEMA}.productos_aliases) AS aliases
            """
        )
        print(f"[VERIFY] {dict(after)}")
        if after["productos"] != EXPECTED or after["listas"] != 1 or after["precios"] != EXPECTED:
            print("[FAIL] Los conteos cargados no coinciden con los CSV", file=sys.stderr)
            return 1
    finally:
        await conn.close()

    backend = os.getenv(
        "BACKEND_URL", "https://web-production-f544f.up.railway.app"
    ).rstrip("/")
    vectorize_url = f"{backend}/{SCHEMA}/productos/vectorize"
    try:
        response = requests.post(vectorize_url, json=product_codes, timeout=120)
        print(f"[VECTORIZE] HTTP {response.status_code}: {response.text[:400]}")
        if response.status_code != 200:
            print("[WARN] Catálogo cargado, vectorización no confirmada")
    except requests.RequestException as error:
        print(f"[WARN] Catálogo cargado, vectorización falló: {error}")

    print(f"[SUCCESS] Fase 1 cargada en {SCHEMA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
