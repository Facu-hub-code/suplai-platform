#!/usr/bin/env python3
"""Carga histórica de comprobantes Campi (del_corro), 20.06 al 20.09.2026.

Continúa el criterio del registro ya cargado (ene–abr 2026):
  - un pedido por comprobante
  - tipos FAA, FAB, PEX, NPX, NPA, NPB
  - sin notas de crédito (NCA/NCB) ni DEX
  - precio unitario = neto
  - notas e ítems con el mismo texto histórico
  - sync_metadata.comprobante + fuente de este lote

Uso:
  python implementacion/del_corro/scripts/cargar_pedidos_comprobantes_2026_06_20.py
  python implementacion/del_corro/scripts/cargar_pedidos_comprobantes_2026_06_20.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import asyncpg
import openpyxl
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "implementacion" / "del_corro" / "outputs" / "pedidos-comprobantes-2026-06-20-al-2026-09-20"
SCHEMA = "del_corro"
FUENTE = "detalle-comprobantes-2026-06-20-al-2026-09-20"
NOTA = "Insertado manualmente del registro historico"
DEFAULT_XLSX = Path("/Users/facundolorenzo/Downloads/Detalle de comprobantes  20.06 al 20.09.xlsx")
DOC_OK = {"FAA", "FAB", "PEX", "NPX", "NPA", "NPB"}
Q2 = Decimal("0.01")

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend-supabase" / ".env")


def db_url() -> str:
    url = (
        os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL / DATABASE_URL en .env")
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    if ":5432@" in url:
        url = url.replace(":5432@", ":6543@")
    return url


def money(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value)).quantize(Q2, rounding=ROUND_HALF_UP)


def as_code(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text or None


def as_qty(value) -> Decimal | None:
    if value is None or value == "":
        return None
    qty = Decimal(str(value))
    if qty == 0:
        return None
    return qty


def prefix_of(comprobante: str) -> str:
    return comprobante[:3].upper()


def read_excel(path: Path) -> tuple[dict[str, dict], dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    header = list(next(rows_iter))
    idx = {name: i for i, name in enumerate(header)}
    required = ["Cliente", "Fecha", "Comprobante", "Art", "Cantidad", "articulo", "neto", "cod_ven"]
    missing = [name for name in required if name not in idx]
    if missing:
        raise SystemExit(f"Faltan columnas en el Excel: {missing}")

    orders: dict[str, dict] = {}
    stats = {
        "filas": 0,
        "filas_tipo_excluido": 0,
        "filas_qty_cero": 0,
        "filas_sin_neto": 0,
        "prefijos_excluidos": defaultdict(int),
        "prefijos_incluidos": defaultdict(int),
    }

    for row in rows_iter:
        if row is None or all(cell is None for cell in row):
            continue
        stats["filas"] += 1
        comprobante = as_code(row[idx["Comprobante"]])
        if not comprobante:
            continue
        pref = prefix_of(comprobante)
        if pref not in DOC_OK:
            stats["filas_tipo_excluido"] += 1
            stats["prefijos_excluidos"][pref] += 1
            continue
        qty = as_qty(row[idx["Cantidad"]])
        if qty is None:
            stats["filas_qty_cero"] += 1
            continue
        unit = money(row[idx["neto"]])
        if unit is None:
            stats["filas_sin_neto"] += 1
            continue

        fecha = row[idx["Fecha"]]
        if isinstance(fecha, datetime):
            fecha = fecha.date()
        if not isinstance(fecha, date):
            raise SystemExit(f"Fecha inválida en {comprobante}: {fecha!r}")

        order = orders.get(comprobante)
        if order is None:
            order = {
                "comprobante": comprobante,
                "prefijo": pref,
                "cliente_codigo": as_code(row[idx["Cliente"]]),
                "fecha": fecha,
                "cod_ven": as_code(row[idx["cod_ven"]]),
                "razon_social": (row[idx["Razon_Social"]] or "") if "Razon_Social" in idx else "",
                "items": [],
            }
            orders[comprobante] = order
        stats["prefijos_incluidos"][pref] += 1
        order["items"].append(
            {
                "product_code": as_code(row[idx["Art"]]) or "",
                "nombre_excel": str(row[idx["articulo"]] or "").strip(),
                "cantidad": qty,
                "precio_unitario": unit,
            }
        )

    wb.close()
    stats["prefijos_excluidos"] = dict(stats["prefijos_excluidos"])
    stats["prefijos_incluidos"] = dict(stats["prefijos_incluidos"])
    return orders, stats


async def load_lookups(conn: asyncpg.Connection) -> tuple[dict, dict, set]:
    client_rows = await conn.fetch(
        f"""
        SELECT DISTINCT ON (codigo)
            codigo::text AS codigo,
            id,
            lista_precios_id
        FROM {SCHEMA}.clients
        WHERE codigo IS NOT NULL
        ORDER BY codigo,
            (
                SELECT COUNT(*)
                FROM {SCHEMA}.pedidos p
                WHERE p.cliente_id = {SCHEMA}.clients.id
                  AND p.deleted_at IS NULL
            ) DESC,
            is_primary DESC NULLS LAST,
            id ASC
        """
    )
    clients = {row["codigo"]: {"id": row["id"], "lista": row["lista_precios_id"]} for row in client_rows}
    product_rows = await conn.fetch(
        f"SELECT product_code, nombre FROM {SCHEMA}.productos"
    )
    products = {row["product_code"]: row["nombre"] for row in product_rows}
    existing_rows = await conn.fetch(
        f"""
        SELECT sync_metadata->>'comprobante' AS comprobante
        FROM {SCHEMA}.pedidos
        WHERE deleted_at IS NULL
          AND sync_metadata ? 'comprobante'
        """
    )
    existing = {row["comprobante"] for row in existing_rows if row["comprobante"]}
    return clients, products, existing


def classify(orders: dict[str, dict], clients: dict, products: dict, existing: set) -> dict:
    ready = []
    sin_cliente = []
    ya_cargados = []
    productos_faltantes = defaultdict(lambda: {"nombre": "", "lineas": 0, "comprobantes": set()})
    for comprobante, order in orders.items():
        if comprobante in existing:
            ya_cargados.append(comprobante)
            continue
        client = clients.get(order["cliente_codigo"] or "")
        if not client:
            sin_cliente.append(order)
            continue
        total = Decimal("0")
        items = []
        for item in order["items"]:
            code = item["product_code"]
            nombre = products.get(code) or item["nombre_excel"] or code
            if code not in products:
                bucket = productos_faltantes[code]
                bucket["nombre"] = item["nombre_excel"]
                bucket["lineas"] += 1
                bucket["comprobantes"].add(comprobante)
            line = (item["precio_unitario"] * item["cantidad"]).quantize(Q2, rounding=ROUND_HALF_UP)
            total += line
            items.append({**item, "nombre": nombre, "en_catalogo": code in products})
        ready.append(
            {
                **order,
                "cliente_id": client["id"],
                "items": items,
                "total": total.quantize(Q2, rounding=ROUND_HALF_UP),
            }
        )
    return {
        "ready": ready,
        "sin_cliente": sin_cliente,
        "ya_cargados": ya_cargados,
        "productos_faltantes": productos_faltantes,
    }


def write_reports(excel_stats: dict, classified: dict) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    ready = classified["ready"]
    with (OUT / "pedidos.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "comprobante",
                "prefijo",
                "cliente_codigo",
                "cliente_id",
                "fecha",
                "cod_ven",
                "razon_social",
                "n_items",
                "total",
            ],
        )
        writer.writeheader()
        for order in ready:
            writer.writerow(
                {
                    "comprobante": order["comprobante"],
                    "prefijo": order["prefijo"],
                    "cliente_codigo": order["cliente_codigo"],
                    "cliente_id": order["cliente_id"],
                    "fecha": order["fecha"].isoformat(),
                    "cod_ven": order["cod_ven"] or "",
                    "razon_social": order["razon_social"],
                    "n_items": len(order["items"]),
                    "total": f"{order['total']:.2f}",
                }
            )

    with (OUT / "omitidos-sin-cliente.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["comprobante", "cliente_codigo", "razon_social", "fecha", "n_items"],
        )
        writer.writeheader()
        for order in classified["sin_cliente"]:
            writer.writerow(
                {
                    "comprobante": order["comprobante"],
                    "cliente_codigo": order["cliente_codigo"],
                    "razon_social": order["razon_social"],
                    "fecha": order["fecha"].isoformat(),
                    "n_items": len(order["items"]),
                }
            )

    with (OUT / "productos-no-en-catalogo.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["product_code", "nombre_excel", "lineas", "comprobantes"],
        )
        writer.writeheader()
        for code, bucket in sorted(
            classified["productos_faltantes"].items(),
            key=lambda pair: pair[1]["lineas"],
            reverse=True,
        ):
            writer.writerow(
                {
                    "product_code": code,
                    "nombre_excel": bucket["nombre"],
                    "lineas": bucket["lineas"],
                    "comprobantes": len(bucket["comprobantes"]),
                }
            )

    fechas = [order["fecha"] for order in ready]
    resumen = {
        "schema": SCHEMA,
        "fuente": FUENTE,
        "filas_excel": excel_stats["filas"],
        "filas_tipo_excluido": excel_stats["filas_tipo_excluido"],
        "filas_qty_cero": excel_stats["filas_qty_cero"],
        "filas_sin_neto": excel_stats["filas_sin_neto"],
        "prefijos_incluidos": excel_stats["prefijos_incluidos"],
        "prefijos_excluidos": excel_stats["prefijos_excluidos"],
        "comprobantes_excel_incluidos": len(classified["ready"])
        + len(classified["sin_cliente"])
        + len(classified["ya_cargados"]),
        "listos": len(ready),
        "items_listos": sum(len(order["items"]) for order in ready),
        "sin_cliente": len(classified["sin_cliente"]),
        "ya_cargados": len(classified["ya_cargados"]),
        "skus_fuera_de_catalogo": len(classified["productos_faltantes"]),
        "lineas_sku_fuera_de_catalogo": sum(
            bucket["lineas"] for bucket in classified["productos_faltantes"].values()
        ),
        "total": f"{sum((order['total'] for order in ready), Decimal('0')):.2f}",
        "fecha_min": min(fechas).isoformat() if fechas else None,
        "fecha_max": max(fechas).isoformat() if fechas else None,
    }
    (OUT / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumen


async def apply(conn: asyncpg.Connection, ready: list[dict]) -> tuple[int, int]:
    inserted_orders = 0
    inserted_items = 0
    batch = 200
    for start in range(0, len(ready), batch):
        chunk = ready[start : start + batch]
        async with conn.transaction():
            rows = await conn.fetch(
                f"""
                INSERT INTO {SCHEMA}.pedidos (
                    cliente_id, fecha, items, total, estado, notas, sync_metadata, is_mock, origen
                )
                SELECT
                    u.cliente_id,
                    u.fecha,
                    '[]'::jsonb,
                    u.total,
                    'confirmado',
                    $5,
                    jsonb_build_object(
                        'comprobante', u.comprobante,
                        'fuente', $6::text,
                        'cod_ven', u.cod_ven
                    ),
                    false,
                    'erp'
                FROM unnest($1::int[], $2::timestamp[], $3::numeric[], $4::text[], $7::text[])
                    AS u(cliente_id, fecha, total, comprobante, cod_ven)
                RETURNING id, sync_metadata->>'comprobante' AS comprobante
                """,
                [order["cliente_id"] for order in chunk],
                [datetime.combine(order["fecha"], datetime.min.time()) for order in chunk],
                [order["total"] for order in chunk],
                [order["comprobante"] for order in chunk],
                NOTA,
                FUENTE,
                [order["cod_ven"] or "" for order in chunk],
            )
            id_by_comp = {row["comprobante"]: row["id"] for row in rows}
            item_pedido = []
            item_client = []
            item_code = []
            item_price = []
            item_fecha = []
            item_nombre = []
            item_qty = []
            for order in chunk:
                pedido_id = id_by_comp[order["comprobante"]]
                for item in order["items"]:
                    item_pedido.append(pedido_id)
                    item_client.append(order["cliente_codigo"])
                    item_code.append(item["product_code"])
                    item_price.append(item["precio_unitario"])
                    item_fecha.append(order["fecha"])
                    item_nombre.append(item["nombre"])
                    item_qty.append(item["cantidad"])
            if item_pedido:
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.items_pedido (
                        pedido_id, client_id, product_code, precio_unitario, fecha_pedido,
                        notas, nombre, cantidad_solicitada, is_mock
                    )
                    SELECT
                        u.pedido_id,
                        u.client_id,
                        u.product_code,
                        u.precio_unitario,
                        u.fecha_pedido,
                        $8,
                        u.nombre,
                        u.cantidad,
                        false
                    FROM unnest(
                        $1::int[], $2::varchar[], $3::varchar[], $4::numeric[],
                        $5::date[], $6::text[], $7::numeric[]
                    ) AS u(pedido_id, client_id, product_code, precio_unitario, fecha_pedido, nombre, cantidad)
                    """,
                    item_pedido,
                    item_client,
                    item_code,
                    item_price,
                    item_fecha,
                    item_nombre,
                    item_qty,
                    NOTA,
                )
            inserted_orders += len(rows)
            inserted_items += len(item_pedido)
        print(f"  lote {start + len(chunk)}/{len(ready)} pedidos", flush=True)
    return inserted_orders, inserted_items


async def verify(conn: asyncpg.Connection) -> dict:
    row = await conn.fetchrow(
        f"""
        SELECT
            COUNT(*) AS pedidos,
            COALESCE(SUM(p.total), 0) AS total,
            MIN(p.fecha) AS fecha_min,
            MAX(p.fecha) AS fecha_max,
            (
                SELECT COUNT(*)
                FROM {SCHEMA}.items_pedido i
                JOIN {SCHEMA}.pedidos p2 ON p2.id = i.pedido_id
                WHERE p2.sync_metadata->>'fuente' = $1
            ) AS items
        FROM {SCHEMA}.pedidos p
        WHERE p.deleted_at IS NULL
          AND p.sync_metadata->>'fuente' = $1
        """,
        FUENTE,
    )
    return {
        "pedidos": row["pedidos"],
        "items": row["items"],
        "total": f"{row['total']:.2f}",
        "fecha_min": row["fecha_min"].date().isoformat() if row["fecha_min"] else None,
        "fecha_max": row["fecha_max"].date().isoformat() if row["fecha_max"] else None,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    args = parser.parse_args()
    if not args.xlsx.exists():
        raise SystemExit(f"No existe el Excel: {args.xlsx}")

    print(f"schema={SCHEMA} leyendo {args.xlsx.name}", flush=True)
    orders, excel_stats = read_excel(args.xlsx)
    conn = await asyncpg.connect(db_url(), statement_cache_size=0, command_timeout=120)
    try:
        clients, products, existing = await load_lookups(conn)
        classified = classify(orders, clients, products, existing)
        resumen = write_reports(excel_stats, classified)
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
        if not args.apply:
            print("Dry-run. No se escribió en la base.")
            return
        if resumen["listos"] == 0:
            print("Nada para insertar.")
            return
        print(f"INSERT en {SCHEMA}.pedidos / {SCHEMA}.items_pedido", flush=True)
        n_orders, n_items = await apply(conn, classified["ready"])
        check = await verify(conn)
        print(json.dumps({"insertados_pedidos": n_orders, "insertados_items": n_items, "verificacion": check}, ensure_ascii=False, indent=2))
        if check["pedidos"] != n_orders or check["items"] != n_items:
            raise SystemExit("La verificación no coincide con lo insertado.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
