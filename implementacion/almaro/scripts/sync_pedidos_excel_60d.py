#!/usr/bin/env python3
"""Pull 60 días de GEV y proyecta pedidos de los clientes Excel Oct 2026."""
from __future__ import annotations

import asyncio
import csv
import os
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve()
ALMARO = HERE.parents[1]
PLATFORM = HERE.parents[3]
BACKEND = PLATFORM.parent / "backend-supabase"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

import core.db as core_db  # noqa: E402

core_db._POOL_MAX_SIZE = 2

SCHEMA = "almaro"
PLAN = ALMARO / "outputs" / "propuesta-clientes-whatsapp-20261009.csv"


async def main() -> int:
    from erp.connectors.gev import gev_date_windows
    from erp.services.erp_order_projection_service import project_orders_raw
    from erp.services.erp_sync_service import (
        _resolve_cliente_ids_by_partners,
        _upsert_erp_orders_raw_batch,
        get_connector_for_schema,
    )

    codes = [int(r["codigo_int"]) for r in csv.DictReader(PLAN.open()) if r["accion"] == "crear"]
    print(f"codes={len(codes)}", flush=True)

    print("[1] project existing raw", flush=True)
    for i in range(6):
        projection = await project_orders_raw(SCHEMA, dry_run=False, limit=2000)
        print(
            f"  round {i + 1} projected={projection.get('projected')} "
            f"skipped={projection.get('skipped')} failed={projection.get('failed')}",
            flush=True,
        )
        if int(projection.get("projected") or 0) == 0:
            break

    connector = await get_connector_for_schema(SCHEMA)
    start = date.today() - timedelta(days=60)
    windows = gev_date_windows(start, date.today())
    print(f"[2] pull GEV {start}..{date.today()} windows={len(windows)}", flush=True)
    orders: list[dict] = []
    failed: list[str] = []
    for i, (window_start, window_end) in enumerate(windows, 1):
        for attempt in range(3):
            try:
                batch = await connector._fetch_orders_window(window_start, window_end)
                orders.extend(batch)
                print(f"  [{i}/{len(windows)}] {window_start} {len(batch)}", flush=True)
                break
            except Exception as exc:
                print(
                    f"  [{i}/{len(windows)}] {window_start} fail {attempt + 1} {type(exc).__name__}",
                    flush=True,
                )
                await asyncio.sleep(4)
        else:
            failed.append(window_start.isoformat())

    code_set = set(codes)
    mine = [
        order
        for order in orders
        if (pid := order.get("erp_partner_id") or order.get("partner_odoo_id")) is not None
        and int(pid) in code_set
    ]
    print(f"[3] gev_total={len(orders)} excel={len(mine)} failed={failed}", flush=True)

    conn = await core_db.get_connection()
    try:
        partner_ids = [
            int(order.get("erp_partner_id") or order.get("partner_odoo_id")) for order in mine
        ]
        cliente_by_partner = await _resolve_cliente_ids_by_partners(conn, SCHEMA, partner_ids)
        for i in range(0, len(mine), 200):
            await _upsert_erp_orders_raw_batch(conn, SCHEMA, mine[i : i + 200], cliente_by_partner)
        print(f"[4] upserted={len(mine)} linked={len(cliente_by_partner)}", flush=True)
    finally:
        await conn.close()

    for i in range(6):
        projection = await project_orders_raw(SCHEMA, dry_run=False, limit=2000)
        print(
            f"[5] project {i + 1} projected={projection.get('projected')} "
            f"skipped={projection.get('skipped')}",
            flush=True,
        )
        if int(projection.get("projected") or 0) == 0:
            break

    conn = await core_db.get_connection()
    try:
        row = await conn.fetchrow(
            f"""
            SELECT
              (SELECT count(*) FROM "{SCHEMA}".clients c
               WHERE c.metadata->>'origen'='excel_whatsapp_20261009') AS excel_clients,
              (SELECT count(DISTINCT c.id) FROM "{SCHEMA}".clients c
               JOIN "{SCHEMA}".pedidos p ON p.cliente_id=c.id AND p.deleted_at IS NULL
               WHERE c.metadata->>'origen'='excel_whatsapp_20261009') AS with_orders,
              (SELECT count(*) FROM "{SCHEMA}".pedidos p
               JOIN "{SCHEMA}".clients c ON c.id=p.cliente_id
               WHERE p.deleted_at IS NULL
                 AND c.metadata->>'origen'='excel_whatsapp_20261009') AS pedidos
            """
        )
        print(dict(row), flush=True)
    finally:
        await conn.close()
        await core_db.close_db_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
