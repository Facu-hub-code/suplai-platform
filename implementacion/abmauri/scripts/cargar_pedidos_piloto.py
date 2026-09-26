#!/usr/bin/env python3
"""Carga pedidos piloto AB Mauri por lotes y en una única transacción."""
from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA = "abmauri"
EXPECTED_ORDERS = 22470
EXPECTED_ITEMS = 66568
EXPECTED_OPEN = 7
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


def chunks(rows: list[dict[str, object]], size: int = BATCH):
    for index in range(0, len(rows), size):
        yield index, rows[index : index + size]


load_env()


async def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    orders = read_csv("phase-06-pedidos.csv")
    items = read_csv("phase-06-items-pedido.csv")
    if len(orders) != EXPECTED_ORDERS or len(items) != EXPECTED_ITEMS:
        print(
            f"[FAIL] Conteos CSV inválidos: pedidos={len(orders)} items={len(items)}",
            file=sys.stderr,
        )
        return 1
    if sum(row["es_pedido_abierto"] == "True" for row in orders) != EXPECTED_OPEN:
        print("[FAIL] La cantidad de pedidos abiertos no coincide", file=sys.stderr)
        return 1

    items_by_order: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in items:
        items_by_order[item["pedido_ref"]].append(
            {
                "product_code": item["product_code"],
                "nombre": item["nombre"],
                "cantidad_solicitada": int(item["cantidad_solicitada"]),
                "precio_unitario": item["precio_unitario"],
                "lista_precios_id": int(item["lista_precios_id"]),
                "notas": item["notas"],
                "promo_aplicada": False,
            }
        )
    if set(items_by_order) != {row["pedido_ref"] for row in orders}:
        print("[FAIL] Pedidos e ítems no tienen las mismas referencias", file=sys.stderr)
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
              (SELECT COUNT(*) FROM {SCHEMA}.pedidos) AS pedidos,
              (SELECT COUNT(*) FROM {SCHEMA}.items_pedido) AS items
            """
        )
        if before["pedidos"] or before["items"]:
            print(f"[FAIL] Tablas de pedidos no vacías: {dict(before)}", file=sys.stderr)
            return 1

        client_rows = await conn.fetch(
            f"SELECT id, phone_number FROM {SCHEMA}.clients"
        )
        client_ids = {
            str(row["phone_number"]): int(row["id"]) for row in client_rows
        }
        missing_phones = sorted(
            {row["cliente_phone"] for row in orders} - set(client_ids)
        )
        if missing_phones:
            print(f"[FAIL] Clientes faltantes: {missing_phones[:10]}", file=sys.stderr)
            return 1

        order_ids: dict[str, int] = {}
        async with conn.transaction():
            for index, batch in chunks(orders):
                returned = await conn.fetch(
                    f"""
                    INSERT INTO {SCHEMA}.pedidos (
                        cliente_id, fecha, items, total, estado, notas,
                        erp_reference_id, sync_metadata, is_mock, origen,
                        updated_at, order_reference
                    )
                    SELECT cliente_id, fecha, items_text::jsonb, total, estado,
                           notas, erp_ref, metadata_text::jsonb, true,
                           'pilot_internal', now(), order_ref
                    FROM UNNEST(
                        $1::integer[], $2::timestamp[], $3::text[],
                        $4::numeric[], $5::text[], $6::text[],
                        $7::text[], $8::text[], $9::text[]
                    ) AS x(
                        cliente_id,fecha,items_text,total,estado,notas,
                        erp_ref,metadata_text,order_ref
                    )
                    RETURNING id, order_reference
                    """,
                    [client_ids[row["cliente_phone"]] for row in batch],
                    [datetime.fromisoformat(row["fecha"]) for row in batch],
                    [
                        json.dumps(items_by_order[row["pedido_ref"]], ensure_ascii=False)
                        for row in batch
                    ],
                    [Decimal(row["total"]) for row in batch],
                    [row["estado"] for row in batch],
                    [row["notas"] for row in batch],
                    [row["pedido_ref"] for row in batch],
                    [
                        json.dumps(
                            {
                                "source": "fase-06-pedidos",
                                "source_year": 2026,
                                "source_comprobante": row["source_comprobante"],
                                "source_factura": row["source_factura"],
                                "source_cliente_codigo": row[
                                    "source_cliente_codigo"
                                ],
                                "quantity_rule": "1_por_sku_unico",
                                "pilot_internal": True,
                                "open_order": row["es_pedido_abierto"] == "True",
                            },
                            ensure_ascii=False,
                        )
                        for row in batch
                    ],
                    [row["pedido_ref"] for row in batch],
                )
                order_ids.update(
                    {
                        str(row["order_reference"]): int(row["id"])
                        for row in returned
                    }
                )
                if (index + len(batch)) % 2000 < BATCH:
                    print(f"    pedidos={index + len(batch)}/{EXPECTED_ORDERS}")

            item_payload: list[dict[str, object]] = [
                {
                    "client_id": row["cliente_phone"],
                    "product_code": row["product_code"],
                    "precio_unitario": Decimal(row["precio_unitario"]),
                    "lista_precios": row["lista_precios_id"],
                    "fecha_pedido": date.fromisoformat(row["fecha_pedido"]),
                    "notas": row["notas"],
                    "nombre": row["nombre"],
                    "cantidad": Decimal(row["cantidad_solicitada"]),
                    "pedido_id": order_ids[row["pedido_ref"]],
                }
                for row in items
            ]
            for index, batch in chunks(item_payload):
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.items_pedido (
                        client_id, product_code, precio_unitario,
                        lista_precios, fecha_pedido, notas, nombre,
                        cantidad_solicitada, pedido_id, is_mock
                    )
                    SELECT client_id, product_code, precio_unitario,
                           lista_precios, fecha_pedido, notas, nombre,
                           cantidad, pedido_id, true
                    FROM UNNEST(
                        $1::text[], $2::text[], $3::numeric[], $4::text[],
                        $5::date[], $6::text[], $7::text[], $8::numeric[],
                        $9::integer[]
                    ) AS x(
                        client_id,product_code,precio_unitario,lista_precios,
                        fecha_pedido,notas,nombre,cantidad,pedido_id
                    )
                    """,
                    [str(row["client_id"]) for row in batch],
                    [str(row["product_code"]) for row in batch],
                    [row["precio_unitario"] for row in batch],
                    [str(row["lista_precios"]) for row in batch],
                    [row["fecha_pedido"] for row in batch],
                    [str(row["notas"]) for row in batch],
                    [str(row["nombre"]) for row in batch],
                    [row["cantidad"] for row in batch],
                    [int(row["pedido_id"]) for row in batch],
                )
                if (index + len(batch)) % 5000 < BATCH:
                    print(f"    items={index + len(batch)}/{EXPECTED_ITEMS}")

            verify = await conn.fetchrow(
                f"""
                SELECT
                  (SELECT COUNT(*) FROM {SCHEMA}.pedidos) AS pedidos,
                  (SELECT COUNT(*) FROM {SCHEMA}.items_pedido) AS items,
                  (SELECT COUNT(*) FROM {SCHEMA}.pedidos
                   WHERE estado='pendiente'
                     AND order_reference LIKE 'PILOTO-OPEN-%') AS abiertos,
                  (
                    SELECT COUNT(*)
                    FROM {SCHEMA}.pedidos p
                    JOIN (
                      SELECT pedido_id,
                             SUM(cantidad_solicitada * precio_unitario) AS total_items
                      FROM {SCHEMA}.items_pedido
                      GROUP BY pedido_id
                    ) i ON i.pedido_id=p.id
                    WHERE p.total <> i.total_items
                  ) AS totales_inconsistentes
                """
            )
            print(f"[VERIFY] {dict(verify)}")
            if (
                verify["pedidos"] != EXPECTED_ORDERS
                or verify["items"] != EXPECTED_ITEMS
                or verify["abiertos"] != EXPECTED_OPEN
                or verify["totales_inconsistentes"] != 0
            ):
                raise RuntimeError(f"Verificación fallida: {dict(verify)}")

        print("[SUCCESS] Pedidos piloto cargados")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
