#!/usr/bin/env python3
"""Carga la red comercial aprobada del piloto interno AB Mauri."""
from __future__ import annotations

import asyncio
import csv
import os
import sys
from decimal import Decimal
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA = "abmauri"
EXPECTED_CLIENTS = 16554
EXPECTED_SELLERS = 10
BATCH = 100
HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
PLATFORM_ROOT = HERE.parents[3]
OUT = ROOT / "outputs"


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def load_env() -> None:
    for path in (
        Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
        PLATFORM_ROOT / ".env",
    ):
        if path.exists():
            load_dotenv(path, override=False)
    url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or ""
    if url:
        pooler = force_pooler(url)
        os.environ["SUPABASE_DB_URL_POOLER"] = pooler
        os.environ["SUPABASE_DB_URL"] = pooler


def read_csv(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def chunks(rows: list[dict[str, str]], size: int = BATCH):
    for index in range(0, len(rows), size):
        yield index, rows[index : index + size]


load_env()


async def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    sellers = read_csv("phase-04-vendedores.csv")
    clients = read_csv("phase-04-clientes.csv")
    price_lists = read_csv("phase-04-listas-precios-piloto.csv")
    prices = read_csv("phase-04-precios-piloto.csv")
    if (
        len(sellers) != EXPECTED_SELLERS
        or len(clients) != EXPECTED_CLIENTS
        or len(price_lists) != 3
        or len(prices) != 546
    ):
        print(
            f"[FAIL] Conteos CSV inválidos: vendedores={len(sellers)} "
            f"clientes={len(clients)} listas={len(price_lists)} precios={len(prices)}",
            file=sys.stderr,
        )
        return 1
    if len({row["phone_number"] for row in clients}) != EXPECTED_CLIENTS:
        print("[FAIL] Los teléfonos sintéticos no son únicos", file=sys.stderr)
        return 1

    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        before = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.clients) AS clients,
              (SELECT COUNT(*) FROM {SCHEMA}.vendedores) AS vendedores,
              (SELECT COUNT(*) FROM {SCHEMA}.puntos_venta) AS puntos,
              (SELECT COUNT(*) FROM {SCHEMA}.vendedores_clientes) AS asignaciones,
              (SELECT COUNT(*) FROM {SCHEMA}.client_locations) AS locations
            """
        )
        if any(before.values()):
            print(f"[FAIL] La red comercial destino no está vacía: {dict(before)}", file=sys.stderr)
            return 1

        seller_ids: dict[str, int] = {}
        point_ids: dict[str, int] = {}
        client_ids: dict[str, int] = {}

        async with conn.transaction():
            for row in price_lists:
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.listas_precios (
                        id, nombre, descripcion, activa, es_publica, is_mock,
                        created_at, updated_at
                    )
                    VALUES ($1,$2,$3,true,true,true,now(),now())
                    ON CONFLICT (id) DO UPDATE
                    SET nombre=EXCLUDED.nombre,
                        descripcion=EXCLUDED.descripcion,
                        activa=true,
                        es_publica=true,
                        is_mock=true,
                        updated_at=now()
                    """,
                    int(row["id"]),
                    row["nombre"],
                    row["descripcion"],
                )
            await conn.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('{SCHEMA}.listas_precios','id'),
                    (SELECT MAX(id) FROM {SCHEMA}.listas_precios),
                    true
                )
                """
            )

            for _, batch in chunks(prices):
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.precios_productos (
                        product_code, lista_precios_id, precio_unidad, is_mock
                    )
                    SELECT * FROM UNNEST(
                        $1::text[], $2::integer[], $3::numeric[], $4::boolean[]
                    )
                    ON CONFLICT (product_code, lista_precios_id) DO UPDATE
                    SET precio_unidad=EXCLUDED.precio_unidad,
                        is_mock=EXCLUDED.is_mock,
                        updated_at=now()
                    """,
                    [row["product_code"] for row in batch],
                    [int(row["lista_precios_id"]) for row in batch],
                    [Decimal(row["precio_unidad"]) for row in batch],
                    [True] * len(batch),
                )

            seller_rows = await conn.fetch(
                f"""
                INSERT INTO {SCHEMA}.vendedores (
                    nombre, telefono, email, activo, is_mock, erp_codigo,
                    created_at, updated_at
                )
                SELECT nombre, telefono, email, true, true, seller_ref, now(), now()
                FROM UNNEST(
                    $1::text[], $2::text[], $3::text[], $4::text[]
                ) AS x(nombre,telefono,email,seller_ref)
                RETURNING id, erp_codigo
                """,
                [row["nombre"] for row in sellers],
                [row["telefono"] for row in sellers],
                [row["email"] for row in sellers],
                [row["seller_ref"] for row in sellers],
            )
            seller_ids = {
                str(row["erp_codigo"]): int(row["id"]) for row in seller_rows
            }

            for index, batch in chunks(clients):
                returned = await conn.fetch(
                    f"""
                    INSERT INTO {SCHEMA}.puntos_venta (
                        razon_social, codigo, lista_precios_id, cuit, direccion,
                        email, vendedor, vendedor_id, activo_ai, is_mock,
                        created_at, updated_at
                    )
                    SELECT razon_social, codigo, lista_id, cuit, direccion,
                           email, vendedor, vendedor_id, true, true, now(), now()
                    FROM UNNEST(
                        $1::text[], $2::numeric[], $3::integer[], $4::text[],
                        $5::text[], $6::text[], $7::text[], $8::integer[]
                    ) AS x(
                        razon_social,codigo,lista_id,cuit,direccion,email,
                        vendedor,vendedor_id
                    )
                    RETURNING id, codigo
                    """,
                    [row["razon_social"] for row in batch],
                    [Decimal(row["client_code"]) for row in batch],
                    [int(row["lista_precios_id"]) for row in batch],
                    [row["cuit"] or None for row in batch],
                    [row["direccion"] or None for row in batch],
                    [row["email"] or None for row in batch],
                    [row["seller_nombre"] for row in batch],
                    [seller_ids[row["seller_ref"]] for row in batch],
                )
                point_ids.update(
                    {
                        str(int(row["codigo"])): int(row["id"])
                        for row in returned
                    }
                )
                if (index + len(batch)) % 2000 < BATCH:
                    print(f"    puntos_venta={index + len(batch)}/{EXPECTED_CLIENTS}")

            for index, batch in chunks(clients):
                returned = await conn.fetch(
                    f"""
                    INSERT INTO {SCHEMA}.clients (
                        phone_number, nombre, razon_social, lista_precios_id,
                        codigo, activo_ai, cuit, email, vendedor, pdv_id,
                        is_primary, is_mock, metadata, created_at, updated_at
                    )
                    SELECT phone, nombre, razon_social, lista_id, codigo, true,
                           cuit, email, vendedor, pdv_id, true, true,
                           metadata_text::jsonb, now(), now()
                    FROM UNNEST(
                        $1::text[], $2::text[], $3::text[], $4::integer[],
                        $5::numeric[], $6::text[], $7::text[], $8::text[],
                        $9::integer[], $10::text[]
                    ) AS x(
                        phone,nombre,razon_social,lista_id,codigo,cuit,email,
                        vendedor,pdv_id,metadata_text
                    )
                    RETURNING id, phone_number
                    """,
                    [row["phone_number"] for row in batch],
                    [row["nombre_fantasia"] or None for row in batch],
                    [row["razon_social"] for row in batch],
                    [int(row["lista_precios_id"]) for row in batch],
                    [Decimal(row["client_code"]) for row in batch],
                    [row["cuit"] or None for row in batch],
                    [row["email"] or None for row in batch],
                    [row["seller_nombre"] for row in batch],
                    [point_ids[row["client_code"]] for row in batch],
                    [row["metadata_json"] for row in batch],
                )
                client_ids.update(
                    {
                        str(row["phone_number"]): int(row["id"])
                        for row in returned
                    }
                )
                if (index + len(batch)) % 2000 < BATCH:
                    print(f"    clients={index + len(batch)}/{EXPECTED_CLIENTS}")

            association_rows = [
                {
                    "vendedor_id": seller_ids[row["seller_ref"]],
                    "cliente_id": client_ids[row["phone_number"]],
                }
                for row in clients
            ]
            for index, batch in chunks(association_rows):
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.vendedores_clientes (
                        vendedor_id, cliente_id, activo, created_at, updated_at
                    )
                    SELECT vendedor_id, cliente_id, true, now(), now()
                    FROM UNNEST($1::integer[], $2::integer[])
                    AS x(vendedor_id,cliente_id)
                    ON CONFLICT (vendedor_id,cliente_id) DO NOTHING
                    """,
                    [row["vendedor_id"] for row in batch],
                    [row["cliente_id"] for row in batch],
                )

            location_source = [
                row for row in clients if (row["direccion"] or "").strip()
            ]
            for index, batch in chunks(location_source):
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.client_locations (
                        client_id, source, address_text, name, geocode_status,
                        is_primary, raw_payload, created_by, created_at, updated_at
                    )
                    SELECT client_id, 'migration', address_text, name, 'pending',
                           true, '{{"pilot_internal":true}}'::jsonb,
                           'migration', now(), now()
                    FROM UNNEST($1::integer[], $2::text[], $3::text[])
                    AS x(client_id,address_text,name)
                    """,
                    [client_ids[row["phone_number"]] for row in batch],
                    [row["direccion"] for row in batch],
                    [row["nombre_fantasia"] or row["razon_social"] for row in batch],
                )

        after = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.clients) AS clients,
              (SELECT COUNT(*) FROM {SCHEMA}.vendedores) AS vendedores,
              (SELECT COUNT(*) FROM {SCHEMA}.puntos_venta) AS puntos,
              (SELECT COUNT(*) FROM {SCHEMA}.vendedores_clientes) AS asignaciones,
              (SELECT COUNT(*) FROM {SCHEMA}.client_locations) AS locations,
              (SELECT COUNT(*) FROM {SCHEMA}.listas_precios) AS listas,
              (SELECT COUNT(*) FROM {SCHEMA}.precios_productos) AS precios
            """
        )
        print(f"[VERIFY] {dict(after)}")
        if (
            after["clients"] != EXPECTED_CLIENTS
            or after["vendedores"] != EXPECTED_SELLERS
            or after["puntos"] != EXPECTED_CLIENTS
            or after["asignaciones"] != EXPECTED_CLIENTS
            or after["listas"] != 3
            or after["precios"] != 546
        ):
            print("[FAIL] Los conteos cargados no coinciden", file=sys.stderr)
            return 1
        print("[SUCCESS] Red comercial del piloto cargada")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
