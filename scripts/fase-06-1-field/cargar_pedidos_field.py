"""
cargar_pedidos_field.py
=======================
Carga los pedidos históricos de Fase 6.1 (field backbone) a la base de datos.

Estrategia batch:
  - pedidos → INSERT con UNNEST (1 round-trip para todos los pedidos)
  - items   → executemany en lote (pipelined, ~10x más rápido que queries individuales)
  - totales → UPDATE masivo con UNNEST (1 round-trip)

Uso:
    python scripts/fase-06-1-field/cargar_pedidos_field.py --esquema <schema>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg

sys.path.insert(0, str(Path(__file__).parent))

from _common_field import (
    create_conn,
    money,
    parse_int,
    read_csv_rows,
    sanitize_schema_name,
    tenant_paths,
)

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

SOURCES = ("fase-06-1-field-backbone", "fase-06-1-field-recent")


async def get_cols(conn: asyncpg.Connection, schema: str, table: str) -> list[str]:
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=$1 AND table_name=$2 ORDER BY ordinal_position",
        schema, table,
    )
    return [r["column_name"] for r in rows]


def pick(*candidates: str, pool: list[str]) -> str | None:
    return next((c for c in candidates if c in pool), None)


async def cleanup_previous(conn: asyncpg.Connection, schema: str) -> None:
    await conn.execute(
        f"""
        DELETE FROM "{schema}".items_pedido
        WHERE is_mock = true
          AND pedido_id IN (
            SELECT id FROM "{schema}".pedidos
            WHERE is_mock = true
              AND sync_metadata->>'source' = ANY($1::text[])
          )
        """,
        list(SOURCES),
    )
    await conn.execute(
        f"""
        DELETE FROM "{schema}".pedidos
        WHERE is_mock = true
          AND sync_metadata->>'source' = ANY($1::text[])
        """,
        list(SOURCES),
    )


async def main_async(schema: str) -> None:
    paths       = tenant_paths(schema)
    orders_path = paths["outputs"] / "phase-06-1-pedidos-field.csv"
    items_path  = paths["outputs"] / "phase-06-1-items-pedido-field.csv"

    if not orders_path.exists():
        raise SystemExit(f"[FAIL] No encontré CSV: {orders_path}\nEjecutá preparar_pedidos_field.py primero.")
    if not items_path.exists():
        raise SystemExit(f"[FAIL] No encontré CSV: {items_path}")

    orders = read_csv_rows(orders_path)
    items  = read_csv_rows(items_path)
    if not orders:
        raise SystemExit("[FAIL] CSV de pedidos vacío.")

    conn = await create_conn()
    try:
        ped_cols  = await get_cols(conn, schema, "pedidos")
        item_cols = await get_cols(conn, schema, "items_pedido")

        # Columnas de pedidos que usamos
        ped_fk    = pick("cliente_id", "client_id",        pool=ped_cols)
        ped_fecha = pick("fecha", "fecha_pedido",           pool=ped_cols)
        ped_est   = pick("estado", "status",                pool=ped_cols)
        ped_tot   = pick("total",                           pool=ped_cols)
        ped_not   = pick("notas", "nota",                   pool=ped_cols)
        ped_mock  = pick("is_mock",                         pool=ped_cols)
        ped_sync  = pick("sync_metadata", "metadata",       pool=ped_cols)
        ped_ref   = pick("erp_reference_id",                pool=ped_cols)
        ped_items = pick("items", "line_items",             pool=ped_cols)

        if not all([ped_fk, ped_est, ped_tot, ped_mock]):
            raise SystemExit("[FAIL] Columnas requeridas faltantes en pedidos.")

        # Columnas de items
        it_fk     = pick("pedido_id",                           pool=item_cols)
        it_prod   = pick("product_code",                        pool=item_cols)
        it_qty    = pick("cantidad_solicitada", "cantidad",      pool=item_cols)
        it_price  = pick("precio_unitario", "precio",           pool=item_cols)
        it_nota   = pick("notas", "nota",                       pool=item_cols)
        it_mock   = pick("is_mock",                             pool=item_cols)
        it_lista  = pick("lista_precios", "lista_precios_id",   pool=item_cols)
        it_date   = pick("fecha_pedido", "fecha", "created_at", pool=item_cols)

        if not all([it_fk, it_prod, it_qty, it_price]):
            raise SystemExit("[FAIL] Columnas requeridas faltantes en items_pedido.")

        # Mapeo phone → client_id
        phone_to_id: dict[str, int] = {
            r["phone_number"]: r["id"]
            for r in await conn.fetch(f'SELECT id, phone_number FROM "{schema}".clients')
        }

        # Agrupar items por pedido_ref y pre-indexar fecha por ref
        items_by_ref: dict[str, list[dict]] = defaultdict(list)
        for item in items:
            items_by_ref[item["pedido_ref"]].append(item)

        fecha_by_ref: dict[str, datetime] = {
            r["pedido_ref"]: datetime.fromisoformat(r["fecha"]) for r in orders
        }

        # -----------------------------------------------------------------------
        # Limpiar carga previa
        # -----------------------------------------------------------------------
        await cleanup_previous(conn, schema)
        print(f"[*] Limpieza previa OK.")
        print(f"[*] Insertando {len(orders)} pedidos en batch...")

        # -----------------------------------------------------------------------
        # Batch INSERT pedidos usando executemany → recuperar IDs por erp_reference_id
        # -----------------------------------------------------------------------
        # Primero armamos las columnas fijas y sus valores
        insert_cols = [c for c in [ped_fk, ped_est, ped_tot, ped_mock, ped_not, ped_fecha, ped_sync, ped_ref, ped_items] if c]
        placeholders = ", ".join(f"${i+1}" for i in range(len(insert_cols)))
        insert_sql = f'INSERT INTO "{schema}".pedidos ({", ".join(insert_cols)}) VALUES ({placeholders})'

        batch_params: list[tuple] = []
        refs_in_order: list[str] = []

        for row in orders:
            ref   = row["pedido_ref"]
            phone = row.get("cliente_phone", "")
            cid   = phone_to_id.get(phone)
            if cid is None:
                print(f"[WARN] Cliente no encontrado phone={phone!r}, saltando {ref}.")
                continue

            source = row.get("source", "fase-06-1-field-backbone")
            fecha  = datetime.fromisoformat(row["fecha"])
            estado = row.get("estado", "confirmado")
            total  = money(row.get("total", "0"))
            notas  = row.get("notas", "")

            items_for_ref = [
                {
                    "product_code": it.get("product_code"),
                    "nombre": it.get("nombre"),
                    "cantidad_solicitada": parse_int(it.get("cantidad_solicitada"), 1),
                    "precio_unitario": str(money(it.get("precio_unitario", "0"))),
                    "lista_precios_id": parse_int(it.get("lista_precios_id"), 1),
                    "notas": it.get("notas", ""),
                }
                for it in items_by_ref.get(ref, [])
            ]

            vals: dict[str, Any] = {
                ped_fk:   cid,
                ped_est:  estado,
                ped_tot:  total,
                ped_mock: True,
            }
            if ped_not:   vals[ped_not]   = notas
            if ped_fecha: vals[ped_fecha] = fecha
            if ped_sync:  vals[ped_sync]  = json.dumps({"source": source, "pedido_ref": ref})
            if ped_ref:   vals[ped_ref]   = ref
            if ped_items: vals[ped_items] = json.dumps(items_for_ref, ensure_ascii=False)

            batch_params.append(tuple(vals[c] for c in insert_cols if c in vals))
            refs_in_order.append(ref)

        # executemany es pipelined en asyncpg → mucho más rápido que N fetchval individuales
        await conn.executemany(insert_sql, batch_params)

        # Recuperar IDs de los pedidos recién insertados (1 sola query)
        inserted_rows = await conn.fetch(
            f'SELECT id, erp_reference_id FROM "{schema}".pedidos '
            f'WHERE is_mock = true AND erp_reference_id = ANY($1)',
            refs_in_order,
        )
        ref_to_id = {r["erp_reference_id"]: r["id"] for r in inserted_rows}
        print(f"[*] {len(ref_to_id)} pedidos insertados. Insertando {len(items)} items en batch...")

        # -----------------------------------------------------------------------
        # Batch INSERT items_pedido con executemany
        # -----------------------------------------------------------------------
        item_insert_cols = [c for c in [it_fk, it_prod, it_qty, it_price, it_mock, it_nota, it_lista, it_date] if c]
        item_ph  = ", ".join(f"${i+1}" for i in range(len(item_insert_cols)))
        item_sql = f'INSERT INTO "{schema}".items_pedido ({", ".join(item_insert_cols)}) VALUES ({item_ph})'

        item_batch: list[tuple] = []
        totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))

        for item in items:
            ref = item["pedido_ref"]
            if ref not in ref_to_id:
                continue
            ped_id    = ref_to_id[ref]
            qty       = parse_int(item.get("cantidad_solicitada", "1"), 1)
            price     = money(item.get("precio_unitario", "0"))
            lista_id  = parse_int(item.get("lista_precios_id", "1"), 1)
            notas     = item.get("notas", "")
            prod      = item.get("product_code", "")

            fecha_order = fecha_by_ref.get(ref, datetime.now())

            iv: dict[str, Any] = {
                it_fk:    ped_id,
                it_prod:  prod,
                it_qty:   qty,
                it_price: price,
                it_mock:  True,
            }
            if it_nota:  iv[it_nota]  = notas
            if it_lista: iv[it_lista] = str(lista_id)
            if it_date:  iv[it_date]  = fecha_order

            item_batch.append(tuple(iv[c] for c in item_insert_cols if c in iv))
            totals[ped_id] += money(price * qty)

        await conn.executemany(item_sql, item_batch)
        print(f"[*] {len(item_batch)} items insertados. Actualizando totales...")

        # -----------------------------------------------------------------------
        # UPDATE totales con UNNEST (1 sola query)
        # -----------------------------------------------------------------------
        if totals and ped_tot:
            ids_list    = list(totals.keys())
            totals_list = [float(totals[i]) for i in ids_list]
            await conn.execute(
                f"""
                UPDATE "{schema}".pedidos AS p
                SET {ped_tot} = t.total
                FROM UNNEST($1::int[], $2::numeric[]) AS t(id, total)
                WHERE p.id = t.id
                """,
                ids_list,
                totals_list,
            )

        # -----------------------------------------------------------------------
        # Verificación final
        # -----------------------------------------------------------------------
        total_ped = await conn.fetchval(
            f'SELECT COUNT(*) FROM "{schema}".pedidos '
            f'WHERE is_mock = true AND sync_metadata->>\'source\' = ANY($1::text[])',
            list(SOURCES),
        )
        total_it = await conn.fetchval(
            f'SELECT COUNT(*) FROM "{schema}".items_pedido '
            f'WHERE is_mock = true AND pedido_id IN ('
            f'  SELECT id FROM "{schema}".pedidos WHERE is_mock = true AND sync_metadata->>\'source\' = ANY($1::text[])'
            f')',
            list(SOURCES),
        )

        print(f"\n{'='*60}")
        print("CARGA FASE 6.1 — PEDIDOS FIELD")
        print(f"{'='*60}")
        print(f"  Pedidos en BD:  {total_ped}")
        print(f"  Items en BD:    {total_it}")
        print(f"{'='*60}")

    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga pedidos históricos de Fase 6.1 a la BD.")
    parser.add_argument("--esquema", required=True)
    args = parser.parse_args()
    asyncio.run(main_async(sanitize_schema_name(args.esquema)))


if __name__ == "__main__":
    main()
