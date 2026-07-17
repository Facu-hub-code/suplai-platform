#!/usr/bin/env python3
"""
Prepara y opcionalmente carga pedidos + items_pedido desde ventas ERP.

Granularidad:
  - 1 pedido por (cliente ERP, mes) con fecha sintética (p.ej. 2026-03-15)
  - items agregados por product_code dentro del pedido

Solo filas con Cant. Vendida > 0 y códigos matcheables.
Por defecto dry-run → CSV preview. --apply inserta con is_mock=false.

Uso:
  python scripts/el_gigante_ventas/03_cargar_items_pedidos.py
  python scripts/el_gigante_ventas/03_cargar_items_pedidos.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import asyncpg

from _common import (
    DEFAULT_INPUT_DIR,
    DEFAULT_SCHEMA,
    add_mes_arg,
    configure_stdout,
    db_url,
    excel_path_for_mes,
    fecha_pedido_for_mes,
    fetch_db_codes,
    load_catalog_product_codes,
    load_client_codes_from_outputs,
    parse_meses,
    period_slug,
    pooler_url,
    read_ventas_excel,
    tenant_outputs,
    to_decimal,
    write_csv,
    write_json,
)


def build_pedidos(rows, mes: str, catalog: set[str], client_codes: set[str]):
    fecha = fecha_pedido_for_mes(mes)
    fecha_dt = datetime.combine(fecha, datetime.min.time())

    pedidos: dict[str, dict] = {}
    items_acc: dict[str, dict[str, dict]] = defaultdict(dict)
    skipped = {"sin_venta": 0, "producto": 0, "cliente": 0}

    for row in rows:
        if row.cant_vendida <= 0:
            skipped["sin_venta"] += 1
            continue
        if row.cod_art not in catalog:
            skipped["producto"] += 1
            continue
        if row.ccliente not in client_codes:
            skipped["cliente"] += 1
            continue

        pedido_ref = f"ERP-{mes.upper()}-{row.ccliente}"
        if pedido_ref not in pedidos:
            pedidos[pedido_ref] = {
                "pedido_ref": pedido_ref,
                "mes": mes,
                "cliente_codigo": row.ccliente,
                "cliente_nombre": row.cliente,
                "vendedor": row.vendedor,
                "ruta": row.ruta,
                "fecha": fecha_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "estado": "entregado",
                "is_mock": "false",
                "origen": f"ventas-erp-{mes}",
            }

        item_key = row.cod_art
        bucket = items_acc[pedido_ref].setdefault(
            item_key,
            {
                "pedido_ref": pedido_ref,
                "mes": mes,
                "cliente_codigo": row.ccliente,
                "product_code": row.cod_art,
                "nombre": row.articulo,
                "cantidad_solicitada": 0.0,
                "ventas_neto": Decimal("0"),
                "cantidad_lineas": 0,
                "is_mock": "false",
            },
        )
        bucket["cantidad_solicitada"] += row.cant_vendida
        bucket["ventas_neto"] += row.total_ventas_neto
        bucket["cantidad_lineas"] += 1

    order_rows = []
    item_rows = []
    for pedido_ref, meta in sorted(pedidos.items()):
        total = Decimal("0")
        for pcode, item in sorted(items_acc[pedido_ref].items()):
            qty = item["cantidad_solicitada"]
            ventas = item["ventas_neto"]
            unit = (ventas / Decimal(str(qty))).quantize(Decimal("0.01")) if qty > 0 else Decimal("0")
            line_total = unit * Decimal(str(qty))
            total += line_total
            item_rows.append(
                {
                    "pedido_ref": pedido_ref,
                    "mes": item["mes"],
                    "cliente_codigo": item["cliente_codigo"],
                    "product_code": item["product_code"],
                    "nombre": item["nombre"],
                    "cantidad_solicitada": round(qty, 2),
                    "precio_unitario": str(unit),
                    "line_total": str(line_total.quantize(Decimal("0.01"))),
                    "cantidad_lineas_origen": item["cantidad_lineas"],
                    "is_mock": "false",
                }
            )
        order_rows.append({**meta, "total": str(total.quantize(Decimal("0.01"))), "items_count": len(items_acc[pedido_ref])})

    return order_rows, item_rows, skipped


def _items_json_for_order(pedido_ref: str, item_rows: list[dict]) -> str:
    payload = []
    for item in item_rows:
        if item["pedido_ref"] != pedido_ref:
            continue
        payload.append(
            {
                "product_code": item["product_code"],
                "nombre": item["nombre"],
                "cantidad_solicitada": item["cantidad_solicitada"],
                "precio_unitario": item["precio_unitario"],
            }
        )
    return json.dumps(payload, ensure_ascii=False)


PEDIDO_BATCH = 250
ITEM_BATCH = 500


def _chunked(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


async def _insert_pedidos_batch(conn: asyncpg.Connection, batch: list[tuple[dict, int]]) -> list[tuple[str, int]]:
    if not batch:
        return []

    values_sql: list[str] = []
    params: list[object] = []
    for idx, (order, client_id) in enumerate(batch):
        base = idx * 9
        values_sql.append(
            f"(${base + 1}, ${base + 2}, ${base + 3}, ${base + 4}, ${base + 5}, "
            f"${base + 6}, ${base + 7}::jsonb, ${base + 8}::jsonb, false, ${base + 9}, NOW())"
        )
        mes = order.get("mes") or "marzo"
        params.extend(
            [
                client_id,
                datetime.strptime(order["fecha"], "%Y-%m-%d %H:%M:%S"),
                to_decimal(order["total"]),
                order["estado"],
                f"Venta ERP {mes} — {order.get('cliente_nombre', '')}",
                order["pedido_ref"],
                json.dumps(
                    {
                        "source": f"ventas-erp-{mes}",
                        "vendedor": order.get("vendedor"),
                        "ruta": order.get("ruta"),
                        "cliente_codigo": order["cliente_codigo"],
                    },
                    ensure_ascii=False,
                ),
                _items_json_for_order(order["pedido_ref"], order.get("_order_items", [])),
                order["origen"],
            ]
        )

    rows = await conn.fetch(
        f"""
        INSERT INTO pedidos (
            cliente_id, fecha, total, estado, notas, erp_reference_id,
            sync_metadata, items, is_mock, origen, updated_at
        ) VALUES {", ".join(values_sql)}
        RETURNING id, erp_reference_id
        """,
        *params,
    )
    return [(str(r["erp_reference_id"]), int(r["id"])) for r in rows]


async def apply_pedidos(schema: str, orders: list[dict], items: list[dict]) -> dict:
    url = db_url()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL")

    items_by_ref: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        items_by_ref[item["pedido_ref"]].append(item)

    conn = await asyncpg.connect(url, statement_cache_size=0)
    stats = {
        "pedidos_insertados": 0,
        "items_insertados": 0,
        "clientes_no_encontrados": 0,
        "pedidos_existentes": 0,
        "pedidos_sin_items_previos": 0,
    }
    try:
        await conn.execute(f"SET search_path TO {schema}, core, public, extensions")

        codigo_to_client = {
            str(int(float(r["codigo"]))): r["id"]
            for r in await conn.fetch(
                "SELECT id, codigo FROM clients WHERE COALESCE(is_mock,false)=false AND codigo IS NOT NULL"
            )
        }

        refs_needed = [order["pedido_ref"] for order in orders]
        existing_rows = await conn.fetch(
            "SELECT id, erp_reference_id FROM pedidos WHERE erp_reference_id = ANY($1::text[])",
            refs_needed,
        )
        ref_to_id: dict[str, int] = {str(r["erp_reference_id"]): int(r["id"]) for r in existing_rows}

        pending_orders: list[tuple[dict, int]] = []
        for order in orders:
            pedido_ref = order["pedido_ref"]
            if pedido_ref in ref_to_id:
                stats["pedidos_existentes"] += 1
                continue
            client_id = codigo_to_client.get(order["cliente_codigo"])
            if not client_id:
                stats["clientes_no_encontrados"] += 1
                continue
            order_copy = dict(order)
            order_copy["_order_items"] = items_by_ref.get(pedido_ref, [])
            pending_orders.append((order_copy, client_id))

        print(f"[*] Pedidos existentes: {stats['pedidos_existentes']} | nuevos: {len(pending_orders)}")
        for batch_idx, batch in enumerate(_chunked(pending_orders, PEDIDO_BATCH), start=1):
            inserted = await _insert_pedidos_batch(conn, batch)
            for pedido_ref, pedido_id in inserted:
                ref_to_id[pedido_ref] = pedido_id
            stats["pedidos_insertados"] += len(inserted)
            print(f"[*] Pedidos batch {batch_idx}: +{len(inserted)} (total nuevos {stats['pedidos_insertados']})")

        pedido_ids = list(ref_to_id.values())
        pedidos_con_items = {
            int(r["pedido_id"])
            for r in await conn.fetch(
                "SELECT DISTINCT pedido_id FROM items_pedido WHERE pedido_id = ANY($1::int[])",
                pedido_ids,
            )
        }

        fecha_by_ref = {o["pedido_ref"]: o["fecha"] for o in orders}
        item_records: list[tuple] = []
        refs_con_items = set()
        for item in items:
            pedido_ref = item["pedido_ref"]
            pedido_id = ref_to_id.get(pedido_ref)
            if not pedido_id or pedido_id in pedidos_con_items:
                continue
            client_id = codigo_to_client.get(item["cliente_codigo"])
            if not client_id:
                continue
            refs_con_items.add(pedido_ref)
            fecha_str = fecha_by_ref.get(pedido_ref, orders[0]["fecha"] if orders else "")
            fecha_val = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S").date()
            item_records.append(
                (
                    pedido_id,
                    str(client_id),
                    item["product_code"],
                    item["nombre"],
                    item["cantidad_solicitada"],
                    to_decimal(item["precio_unitario"]),
                    fecha_val,
                )
            )

        stats["pedidos_sin_items_previos"] = len(refs_con_items)
        print(f"[*] Items a insertar: {len(item_records)} en {len(refs_con_items)} pedidos")

        insert_items_sql = """
            INSERT INTO items_pedido (
                pedido_id, client_id, product_code, nombre,
                cantidad_solicitada, precio_unitario, fecha_pedido, is_mock
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, false)
        """
        for batch_idx, batch in enumerate(_chunked(item_records, ITEM_BATCH), start=1):
            await conn.executemany(insert_items_sql, batch)
            stats["items_insertados"] += len(batch)
            print(f"[*] Items batch {batch_idx}: +{len(batch)} (total {stats['items_insertados']})")
    finally:
        await conn.close()
    return stats


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Cargar pedidos desde ventas ERP el_gigante")
    parser.add_argument("--esquema", default=DEFAULT_SCHEMA)
    add_mes_arg(parser)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--apply", action="store_true", help="INSERT pedidos/items en BD")
    args = parser.parse_args()

    meses = parse_meses(args.mes, todos=args.todos)
    periodo = period_slug(meses)

    catalog = load_catalog_product_codes(args.esquema)
    db_products, db_clients = asyncio.run(fetch_db_codes(args.esquema))
    catalog = {c for c in (catalog | db_products) if c not in {"80000"}}
    client_codes = load_client_codes_from_outputs(args.esquema) | db_clients

    orders: list[dict] = []
    items: list[dict] = []
    skipped_total = {"sin_venta": 0, "producto": 0, "cliente": 0}
    for mes in meses:
        path = excel_path_for_mes(mes, args.input_dir)
        rows = read_ventas_excel(path)
        o, i, skipped = build_pedidos(rows, mes, catalog, client_codes)
        orders.extend(o)
        items.extend(i)
        for key, val in skipped.items():
            skipped_total[key] += val

    out_dir = tenant_outputs(args.esquema)
    orders_csv = out_dir / f"ventas-{periodo}-pedidos-preview.csv"
    items_csv = out_dir / f"ventas-{periodo}-items-preview.csv"
    summary_path = out_dir / f"ventas-{periodo}-pedidos-resumen.json"

    write_csv(
        orders_csv,
        orders,
        [
            "pedido_ref",
            "mes",
            "cliente_codigo",
            "cliente_nombre",
            "vendedor",
            "ruta",
            "fecha",
            "estado",
            "total",
            "items_count",
            "is_mock",
            "origen",
        ],
    )
    write_csv(
        items_csv,
        items,
        [
            "pedido_ref",
            "mes",
            "cliente_codigo",
            "product_code",
            "nombre",
            "cantidad_solicitada",
            "precio_unitario",
            "line_total",
            "cantidad_lineas_origen",
            "is_mock",
        ],
    )

    filas_excel = sum(
        len(read_ventas_excel(excel_path_for_mes(m, args.input_dir))) for m in meses
    )
    summary = {
        "periodo": periodo,
        "meses": meses,
        "fechas_sinteticas": {m: str(fecha_pedido_for_mes(m)) for m in meses},
        "filas_excel": filas_excel,
        "pedidos_preview": len(orders),
        "items_preview": len(items),
        "skipped": skipped_total,
        "catalogo_productos": len(catalog),
        "clientes_conocidos": len(client_codes),
        "csv_pedidos": str(orders_csv),
        "csv_items": str(items_csv),
        "modo": "apply" if args.apply else "dry-run",
    }
    write_json(summary_path, summary)

    print(f"[*] Periodo: {periodo} ({', '.join(meses)}) — {filas_excel} filas Excel")
    print(f"[*] Pedidos preview: {len(orders)} | Items: {len(items)}")
    print(f"[*] Omitidas: {skipped_total}")
    print(f"[*] Preview: {orders_csv}")

    if args.apply:
        print("[!] Insertando pedidos reales (is_mock=false)...")
        stats = asyncio.run(apply_pedidos(args.esquema, orders, items))
        print(
            f"[OK] Pedidos nuevos: {stats['pedidos_insertados']} | "
            f"Items: {stats['items_insertados']} | Existentes: {stats['pedidos_existentes']} | "
            f"Pedidos con items cargados: {stats['pedidos_sin_items_previos']}"
        )
        if stats["clientes_no_encontrados"]:
            print(f"[WARN] Clientes sin match en BD: {stats['clientes_no_encontrados']}")
    else:
        print("[*] Dry-run. Revisá CSVs antes de --apply.")


if __name__ == "__main__":
    main()
