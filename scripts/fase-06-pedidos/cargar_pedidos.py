"""
cargar_pedidos.py
=================
Carga los CSV de Fase 6 en la base de datos del tenant.

El script es reutilizable por esquema:
  - limpia primero los pedidos mock previos
  - inserta pedidos
  - inserta items_pedido
  - recalcula totales
  - verifica los conteos finales

Uso:
    python scripts/fase-06-pedidos/cargar_pedidos.py --esquema <nombre_esquema>

Variables de entorno requeridas:
    SUPABASE_DB_URL
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

from _common import money, parse_bool, parse_dt, parse_int, sanitize_schema_name, tenant_paths

load_dotenv()

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


def table_name(schema: str, table: str) -> str:
    return f"{schema}.{table}"


async def get_columns(conn: asyncpg.Connection, schema: str, table: str) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position
        """,
        schema,
        table,
    )
    return [row["column_name"] for row in rows]


async def get_column_types(conn: asyncpg.Connection, schema: str, table: str) -> dict[str, str]:
    rows = await conn.fetch(
        """
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        """,
        schema,
        table,
    )
    return {
        row["column_name"]: f"{row['data_type']}:{row['udt_name']}"
        for row in rows
    }


def pick_column(columns: list[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def is_textual_type(type_name: str | None) -> bool:
    if not type_name:
        return False
    type_name = type_name.lower()
    return any(token in type_name for token in ["text", "character varying", "character", "uuid", "json"])


def resolve_client_identifier(column_type: str | None, client_id: int, client_phone: str) -> object:
    if is_textual_type(column_type):
        return client_phone
    return client_id


def build_insert_sql(schema: str, table: str, columns: list[str], values: dict[str, object]) -> tuple[str, list[object]]:
    insert_columns = [col for col in columns if col in values and values[col] is not None]
    if not insert_columns:
        raise ValueError(f"No hay columnas para insertar en {table_name(schema, table)}")
    placeholders = ", ".join(f"${idx}" for idx in range(1, len(insert_columns) + 1))
    sql = f"INSERT INTO {table_name(schema, table)} ({', '.join(insert_columns)}) VALUES ({placeholders}) RETURNING id"
    params = [values[col] for col in insert_columns]
    return sql, params


async def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


async def main_async(esquema: str) -> None:
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("[FAIL] SUPABASE_DB_URL no esta configurada en .env")

    esquema = sanitize_schema_name(esquema)
    paths = tenant_paths(esquema)
    orders_path = paths["outputs"] / "phase-06-pedidos.csv"
    items_path = paths["outputs"] / "phase-06-items-pedido.csv"

    if not orders_path.exists():
        raise SystemExit(f"[FAIL] No se encontro el CSV de pedidos: {orders_path}")
    if not items_path.exists():
        raise SystemExit(f"[FAIL] No se encontro el CSV de items: {items_path}")

    orders = await load_csv_rows(orders_path)
    items = await load_csv_rows(items_path)
    if not orders:
        raise SystemExit("[FAIL] El CSV de pedidos esta vacio.")
    if not items:
        raise SystemExit("[FAIL] El CSV de items esta vacio.")

    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(f"SET search_path TO {esquema}, core, public, extensions")

        pedidos_cols = await get_columns(conn, esquema, "pedidos")
        items_cols = await get_columns(conn, esquema, "items_pedido")
        pedidos_types = await get_column_types(conn, esquema, "pedidos")
        items_types = await get_column_types(conn, esquema, "items_pedido")

        pedido_fk_col = pick_column(pedidos_cols, ["cliente_id", "client_id"])
        if not pedido_fk_col:
            raise SystemExit(f"[FAIL] No se encontro una FK de cliente en {table_name(esquema, 'pedidos')} (cliente_id/client_id).")
        pedido_fk_type = pedidos_types.get(pedido_fk_col)

        fecha_col = pick_column(pedidos_cols, ["fecha", "fecha_pedido", "created_at"])
        estado_col = pick_column(pedidos_cols, ["estado", "status"])
        total_col = pick_column(pedidos_cols, ["total"])
        notas_col = pick_column(pedidos_cols, ["notas", "nota", "description"])
        mock_col = pick_column(pedidos_cols, ["is_mock"])
        abierto_col = pick_column(pedidos_cols, ["es_pedido_abierto", "is_pedido_abierto"])
        pedido_ref_col = pick_column(pedidos_cols, ["pedido_ref", "ref", "codigo_externo"])
        items_col = pick_column(pedidos_cols, ["items", "line_items", "detalle_items"])
        erp_ref_col = pick_column(pedidos_cols, ["erp_reference_id", "external_reference_id"])
        sync_metadata_col = pick_column(pedidos_cols, ["sync_metadata", "metadata"])
        updated_at_col = pick_column(pedidos_cols, ["updated_at"])
        created_at_col = pick_column(pedidos_cols, ["created_at"])
        for required_name, required_col in [
            ("estado", estado_col),
            ("total", total_col),
            ("notas", notas_col),
            ("is_mock", mock_col),
        ]:
            if not required_col:
                raise SystemExit(
                    f"[FAIL] La tabla {table_name(esquema, 'pedidos')} no tiene la columna requerida '{required_name}'."
                )

        item_fk_col = pick_column(items_cols, ["pedido_id"])
        if not item_fk_col:
            raise SystemExit(f"[FAIL] No se encontro pedido_id en {table_name(esquema, 'items_pedido')}.")
        item_product_col = pick_column(items_cols, ["product_code", "producto_code", "codigo_producto"])
        if not item_product_col:
            raise SystemExit(f"[FAIL] No se encontro una columna de producto en {table_name(esquema, 'items_pedido')}.")
        item_qty_col = pick_column(items_cols, ["cantidad_solicitada", "cantidad", "qty"])
        item_price_col = pick_column(items_cols, ["precio_unitario", "precio", "precio_lista"])
        if not item_qty_col or not item_price_col:
            raise SystemExit(
                f"[FAIL] La tabla {table_name(esquema, 'items_pedido')} debe tener cantidad_solicitada/cantidad y precio_unitario/precio."
            )
        item_lista_col = pick_column(items_cols, ["lista_precios", "lista_precios_id"])
        item_notes_col = pick_column(items_cols, ["notas", "nota", "description"])
        item_mock_col = pick_column(items_cols, ["is_mock"])
        item_client_col = pick_column(items_cols, ["cliente_id", "client_id"])
        item_client_type = items_types.get(item_client_col) if item_client_col else None
        item_date_col = pick_column(items_cols, ["fecha", "fecha_pedido", "created_at"])
        item_updated_at_col = pick_column(items_cols, ["updated_at"])

        print(f"[*] Leyendo {len(orders)} pedidos y {len(items)} items del CSV...")
        print(f"[*] Columnas pedidos detectadas: {', '.join(pedidos_cols[:10])}{'...' if len(pedidos_cols) > 10 else ''}")
        print(f"[*] Columnas items detectadas:   {', '.join(items_cols[:10])}{'...' if len(items_cols) > 10 else ''}")

        await conn.execute("BEGIN")
        try:
            deleted_items = await conn.execute(
                f"""
                DELETE FROM {table_name(esquema, 'items_pedido')}
                WHERE is_mock = true
                  AND pedido_id IN (
                      SELECT id
                      FROM {table_name(esquema, 'pedidos')}
                      WHERE is_mock = true
                        AND (
                            (sync_metadata IS NOT NULL AND sync_metadata->>'source' = 'fase-06-pedidos')
                            OR erp_reference_id LIKE 'P-%'
                        )
                  )
                """
            )
            deleted_orders = await conn.execute(
                f"""
                DELETE FROM {table_name(esquema, 'pedidos')}
                WHERE is_mock = true
                  AND (
                      (sync_metadata IS NOT NULL AND sync_metadata->>'source' = 'fase-06-pedidos')
                      OR erp_reference_id LIKE 'P-%'
                  )
                """
            )
            await conn.execute("COMMIT")
            print(f"[*] Limpieza previa fase 6: {deleted_items} / {deleted_orders}")
        except Exception:
            await conn.execute("ROLLBACK")
            raise

        client_phone_to_id: dict[str, int] = {}
        for row in await conn.fetch(f"SELECT id, phone_number FROM {table_name(esquema, 'clients')}"):
            client_phone_to_id[row["phone_number"]] = row["id"]

        order_ref_to_db_id: dict[str, int] = {}
        order_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        items_by_order_ref: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in items:
            pedido_ref = row["pedido_ref"]
            items_by_order_ref[pedido_ref].append(
                {
                    "product_code": row.get("product_code"),
                    "nombre": row.get("nombre"),
                    "cantidad_solicitada": parse_int(row.get("cantidad_solicitada"), 0),
                    "precio_unitario": str(money(row.get("precio_unitario"))),
                    "lista_precios_id": parse_int(row.get("lista_precios_id"), 0),
                    "notas": row.get("notas", ""),
                    "promo_aplicada": parse_bool(row.get("promo_aplicada", "false")),
                }
            )

        for row in orders:
            pedido_ref = row["pedido_ref"]
            cliente_phone = row.get("cliente_phone", "")
            client_id = client_phone_to_id.get(cliente_phone)
            if client_id is None:
                raise SystemExit(f"[FAIL] No se encontro el cliente con phone_number={cliente_phone!r} en {esquema}.clients")
            client_fk_value = resolve_client_identifier(pedido_fk_type, client_id, cliente_phone)

            fecha = parse_dt(row["fecha"])
            estado = row["estado"]
            total = money(row["total"])
            notas = row.get("notas", "")
            is_mock = parse_bool(row.get("is_mock", "true"))
            es_abierto = parse_bool(row.get("es_pedido_abierto", "false"))

            values: dict[str, object] = {
                pedido_fk_col: client_fk_value,
                estado_col: estado,
                total_col: total,
                notas_col: notas,
                mock_col: is_mock,
            }
            if abierto_col:
                values[abierto_col] = es_abierto
            if items_col:
                values[items_col] = json.dumps(items_by_order_ref.get(pedido_ref, []), ensure_ascii=False)
            if erp_ref_col:
                values[erp_ref_col] = pedido_ref
            if sync_metadata_col:
                values[sync_metadata_col] = json.dumps(
                    {
                        "source": "fase-06-pedidos",
                        "pedido_ref": pedido_ref,
                        "cliente_phone": cliente_phone,
                        "items_count": len(items_by_order_ref.get(pedido_ref, [])),
                    },
                    ensure_ascii=False,
                )
            if fecha_col:
                values[fecha_col] = fecha
            if created_at_col:
                values[created_at_col] = fecha
            if updated_at_col:
                values[updated_at_col] = fecha
            if pedido_ref_col:
                values[pedido_ref_col] = pedido_ref

            sql, params = build_insert_sql(esquema, "pedidos", pedidos_cols, values)
            pedido_db_id = await conn.fetchval(sql, *params)
            order_ref_to_db_id[pedido_ref] = pedido_db_id
            order_totals[pedido_ref] = Decimal("0")

        inserted_items = 0
        for row in items:
            pedido_ref = row["pedido_ref"]
            pedido_id = order_ref_to_db_id.get(pedido_ref)
            if pedido_id is None:
                raise SystemExit(f"[FAIL] No se pudo resolver pedido_ref={pedido_ref!r} para items_pedido.")

            cliente_phone = row.get("cliente_phone", "")
            client_id = client_phone_to_id.get(cliente_phone)
            if client_id is None:
                raise SystemExit(f"[FAIL] No se encontro el cliente del item phone_number={cliente_phone!r}")

            cantidad = int(float(row["cantidad_solicitada"]))
            precio_unitario = money(row["precio_unitario"])
            lista_precios_id = parse_int(row.get("lista_precios_id"), 0)
            notas = row.get("notas", "")
            is_mock = parse_bool(row.get("is_mock", "true"))
            fecha = parse_dt(next((o["fecha"] for o in orders if o["pedido_ref"] == pedido_ref), row.get("fecha", "2026-06-16 00:00:00")))
            item_client_value = resolve_client_identifier(item_client_type, client_id, cliente_phone) if item_client_col else None

            values: dict[str, object] = {
                item_fk_col: pedido_id,
                item_product_col: row["product_code"],
                item_qty_col: cantidad,
                item_price_col: precio_unitario,
                item_notes_col: notas,
                item_mock_col: is_mock,
            }
            if item_lista_col:
                values[item_lista_col] = str(lista_precios_id) if is_textual_type(items_types.get(item_lista_col)) else lista_precios_id
            if item_client_col:
                values[item_client_col] = item_client_value
            if item_date_col:
                values[item_date_col] = fecha
            if item_updated_at_col:
                values[item_updated_at_col] = fecha

            sql, params = build_insert_sql(esquema, "items_pedido", items_cols, values)
            await conn.fetchval(sql, *params)
            inserted_items += 1
            order_totals[pedido_ref] += money(precio_unitario * cantidad)

        # Recalcular y actualizar totales para asegurar consistencia.
        for pedido_ref, pedido_id in order_ref_to_db_id.items():
            total = money(order_totals[pedido_ref])
            await conn.execute(
                f"UPDATE {table_name(esquema, 'pedidos')} SET {total_col} = $1 WHERE id = $2",
                total,
                pedido_id,
            )

        open_condition = f"{abierto_col} = true" if abierto_col else f"{estado_col} IN ('abierto', 'pendiente')"
        pedidos_open_count = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM {table_name(esquema, 'pedidos')}
            WHERE {open_condition}
              AND {mock_col} = true
              AND (
                  (sync_metadata IS NOT NULL AND sync_metadata->>'source' = 'fase-06-pedidos')
                  OR erp_reference_id LIKE 'P-%'
              )
            """
        )
        pedidos_total_count = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM {table_name(esquema, 'pedidos')}
            WHERE is_mock = true
              AND (
                  (sync_metadata IS NOT NULL AND sync_metadata->>'source' = 'fase-06-pedidos')
                  OR erp_reference_id LIKE 'P-%'
              )
            """
        )
        items_total_count = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM {table_name(esquema, 'items_pedido')}
            WHERE is_mock = true
              AND pedido_id IN (
                  SELECT id
                  FROM {table_name(esquema, 'pedidos')}
                  WHERE is_mock = true
                    AND (
                        (sync_metadata IS NOT NULL AND sync_metadata->>'source' = 'fase-06-pedidos')
                        OR erp_reference_id LIKE 'P-%'
                    )
              )
            """
        )

        print("\n" + "=" * 72)
        print("VERIFICACION FASE 6 - PEDIDOS")
        print("=" * 72)
        print(f"  Pedidos cargados:     {pedidos_total_count}")
        print(f"  Pedidos abiertos:     {pedidos_open_count}")
        print(f"  Items cargados:       {items_total_count}")
        print(f"  Items procesados CSV: {inserted_items}")
        print("=" * 72)

        sample_rows = await conn.fetch(
            f"""
            SELECT id, {pedido_fk_col} AS client_id, {estado_col} AS estado, {total_col} AS total
            FROM {table_name(esquema, 'pedidos')}
            WHERE {mock_col} = true
            ORDER BY id ASC
            LIMIT 3
            """
        )
        for row in sample_rows:
            print(f"  id={row['id']} | client_id={row['client_id']} | estado={row['estado']} | total={row['total']}")

        if int(pedidos_open_count or 0) not in {6, 7}:
            print("[WARN] La cantidad de pedidos abiertos no es 6 o 7. Revisar configuracion.")

    except Exception as exc:
        print(f"[FAIL] Error durante la carga de pedidos: {exc}")
        raise
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga los pedidos mock de la Fase 6.")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant (ej: al_fuego)")
    args = parser.parse_args()
    asyncio.run(main_async(args.esquema))


if __name__ == "__main__":
    main()
