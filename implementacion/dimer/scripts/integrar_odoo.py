#!/usr/bin/env python3
"""Integra Odoo de Dimer (sociedad DIMER S.A., company_id=1) al tenant dimer.

No commitea secretos. Reusa erp.credentials ya cifradas y les agrega company_id.

Uso:
  set -a && source ../../../backend-supabase/.env && set +a
  python implementacion/dimer/scripts/integrar_odoo.py --apply --steps creds,lists,clients,products,prices,stock
  python implementacion/dimer/scripts/integrar_odoo.py --apply --steps recent_buyers,orders,recent_buyers,project --orders-days 30
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT.parent / "backend-supabase"
OUT = ROOT / "implementacion" / "dimer" / "outputs"
SCHEMA = "dimer"
COMPANY_ID = 1
OTHER_COMPANY_LIST_IDS = {"2", "3"}


def _prepare_env() -> None:
    env_path = BACKEND / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path)
    for key in ("SUPABASE_DB_URL", "SUPABASE_DB_URL_POOLER", "DATABASE_URL"):
        val = os.getenv(key) or ""
        if ":5432/" in val:
            os.environ[key] = val.replace(":5432/", ":6543/")


def _backend_path() -> None:
    sys.path.insert(0, str(BACKEND))


async def step_creds() -> dict:
    from erp.services.erp_sync_service import get_connector_for_schema, save_erp_config

    connector = await get_connector_for_schema(SCHEMA)
    if not connector:
        raise RuntimeError("No hay conector Odoo guardado para dimer")
    creds = dict(connector.credentials or {})
    creds["company_id"] = COMPANY_ID
    creds["compute_formula_prices"] = True
    creds.setdefault("username", "admin")
    creds.setdefault("db", "portizm-dimerltda-main-24257253")
    await save_erp_config(
        SCHEMA,
        connector="odoo",
        base_url="https://dimerltda.odoo.com",
        credentials=creds,
        sync_frequency="6h",
        push_orders_enabled=True,
    )
    return {
        "company_id": COMPANY_ID,
        "username": creds.get("username"),
        "db": creds.get("db"),
        "compute_formula_prices": True,
    }


async def step_lists() -> dict:
    from core.db import get_connection, validate_schema
    from erp.services.erp_sync_service import link_price_list_raw, load_price_lists_to_raw

    pulled = await load_price_lists_to_raw(SCHEMA)
    conn = await get_connection()
    created = 0
    dismissed = 0
    already = 0
    try:
        schema = await validate_schema(SCHEMA, conn=conn)
        rows = await conn.fetch(
            f"""
            SELECT r.id, r.erp_list_id, r.nombre, lp.id AS suplai_id
            FROM "{schema}".erp_price_lists_raw r
            LEFT JOIN "{schema}".listas_precios lp ON lp.erp_list_id = r.erp_list_id
            ORDER BY r.nombre;
            """
        )
        other_ids = [int(r["id"]) for r in rows if str(r["erp_list_id"]) in OTHER_COMPANY_LIST_IDS]
        if other_ids:
            result = await conn.execute(
                f"""
                UPDATE "{schema}".erp_price_lists_raw
                SET review_status = 'dismissed', reviewed_at = now(), updated_at = now()
                WHERE id = ANY($1::bigint[])
                  AND COALESCE(review_status, '') IS DISTINCT FROM 'dismissed';
                """,
                other_ids,
            )
            dismissed = int(result.split()[-1]) if result else 0
    finally:
        await conn.close()

    for row in rows:
        if str(row["erp_list_id"]) in OTHER_COMPANY_LIST_IDS:
            continue
        if row["suplai_id"]:
            already += 1
            continue
        linked = await link_price_list_raw(SCHEMA, int(row["id"]), create_new=True)
        if linked.get("action") == "created":
            created += 1
        else:
            already += 1
    return {"pulled": pulled, "created": created, "already_linked": already, "dismissed_other_company": dismissed}


async def step_products(*, apply: bool) -> dict:
    from erp.services.erp_product_promote_service import promote_erp_products_bulk
    from erp.services.erp_sync_service import load_products_to_raw

    pulled = await load_products_to_raw(SCHEMA)
    promo = await promote_erp_products_bulk(SCHEMA, dry_run=not apply)
    return {"pulled": pulled, "promote": promo}


async def step_prices() -> dict:
    from erp.services.erp_sync_service import load_prices_to_raw, sync_prices_from_raw

    raw = await load_prices_to_raw(SCHEMA)
    synced = await sync_prices_from_raw(SCHEMA)
    return {"raw": raw, "synced": synced}


async def step_stock() -> dict:
    from erp.services.erp_sync_service import sync_stock_for_schema

    updated, skipped = await sync_stock_for_schema(SCHEMA)
    return {"updated": updated, "skipped": skipped}


async def step_clients() -> dict:
    from core.db import get_connection, validate_schema
    from erp.services.erp_customer_onboarding_service import sync_customers_to_raw
    from erp.services.erp_sync_service import reconcile_customer_price_lists

    pulled = await sync_customers_to_raw(SCHEMA)
    conn = await get_connection()
    try:
        schema = await validate_schema(SCHEMA, conn=conn)
        linked = await conn.fetchrow(
            f"""
            WITH norm AS (
              SELECT partner_odoo_id,
                     regexp_replace(upper(vat), '[^0-9K]', '', 'g') AS vat_key
              FROM "{schema}".erp_customers_raw
              WHERE vat IS NOT NULL AND btrim(vat) <> ''
            ),
            cli AS (
              SELECT id,
                     regexp_replace(upper(cuit), '[^0-9K]', '', 'g') AS vat_key
              FROM "{schema}".clients
              WHERE cuit IS NOT NULL AND btrim(cuit) <> ''
            ),
            uniq AS (
              SELECT vat_key FROM norm GROUP BY 1 HAVING count(*) = 1
              INTERSECT
              SELECT vat_key FROM cli GROUP BY 1 HAVING count(*) = 1
            ),
            upd AS (
              UPDATE "{schema}".clients c
              SET partner_odoo_id = n.partner_odoo_id,
                  partner_erp_id = n.partner_odoo_id,
                  updated_at = now()
              FROM norm n
              JOIN uniq u ON u.vat_key = n.vat_key
              WHERE regexp_replace(upper(c.cuit), '[^0-9K]', '', 'g') = n.vat_key
                AND c.partner_odoo_id IS NULL
              RETURNING c.id
            )
            SELECT count(*)::int AS linked FROM upd;
            """
        )
        resolved = await conn.fetchrow(
            f"""
            WITH upd AS (
              UPDATE "{schema}".erp_customer_onboarding_queue q
              SET status = 'resuelto',
                  match_status = 'vinculado_existente',
                  resolved_client_id = c.id,
                  resolved_at = COALESCE(q.resolved_at, now()),
                  review_notes = COALESCE(q.review_notes, 'match RUT Odoo 2026-09-29'),
                  updated_at = now()
              FROM "{schema}".clients c
              WHERE c.partner_odoo_id = q.partner_odoo_id
                AND q.status = 'pendiente'
              RETURNING q.id
            )
            SELECT count(*)::int AS resolved FROM upd;
            """
        )
    finally:
        await conn.close()
    reconcile = await reconcile_customer_price_lists(SCHEMA, dry_run=False)
    return {
        "pulled": pulled,
        "linked_by_rut": int((linked or {}).get("linked") or 0),
        "queue_resolved": int((resolved or {}).get("resolved") or 0),
        "reconcile": reconcile,
    }


async def step_recent_buyers() -> dict:
    """Alta/link solo de partners Odoo que ya aparecen en pedidos espejo de dimer."""
    from core.db import get_connection, validate_schema
    from erp.services.erp_customer_onboarding_service import (
        approve_customers_bulk,
        link_queue_item,
    )
    from erp.services.erp_sync_service import reconcile_orders_raw_customers

    conn = await get_connection()
    try:
        schema = await validate_schema(SCHEMA, conn=conn)
        rows = await conn.fetch(
            f"""
            SELECT DISTINCT q.id AS queue_id, q.partner_odoo_id, q.match_status, q.suggested_client_id
            FROM "{schema}".erp_orders_raw e
            JOIN "{schema}".erp_customer_onboarding_queue q
              ON q.partner_odoo_id = e.partner_odoo_id
            WHERE e.cliente_id IS NULL
              AND e.partner_odoo_id IS NOT NULL
              AND q.status IN ('pendiente', 'en_revision');
            """
        )
    finally:
        await conn.close()

    to_link = [r for r in rows if r["match_status"] == "posible_duplicado" and r["suggested_client_id"]]
    to_create = [int(r["partner_odoo_id"]) for r in rows if r["match_status"] != "posible_duplicado"]
    linked = 0
    link_errors: list[dict] = []
    for idx, row in enumerate(to_link, start=1):
        try:
            await link_queue_item(SCHEMA, int(row["queue_id"]), int(row["suggested_client_id"]))
            linked += 1
        except Exception as exc:
            link_errors.append(
                {
                    "queue_id": int(row["queue_id"]),
                    "partner_odoo_id": int(row["partner_odoo_id"]),
                    "error": str(exc),
                }
            )
        if idx % 50 == 0 or idx == len(to_link):
            print(f"recent_buyers link {idx}/{len(to_link)}", flush=True)

    created_batches: list[dict] = []
    chunk = 100
    for start in range(0, len(to_create), chunk):
        part = to_create[start : start + chunk]
        print(f"recent_buyers approve {start + 1}-{start + len(part)}/{len(to_create)}", flush=True)
        created_batches.append(
            await approve_customers_bulk(
                SCHEMA,
                dry_run=False,
                assign_to_all_sellers=False,
                use_synthetic_for_missing=True,
                skip_duplicates=True,
                partner_odoo_ids=part,
            )
        )

    reconcile = await reconcile_orders_raw_customers(SCHEMA)
    return {
        "unmatched_partners": len(rows),
        "linked_duplicates": linked,
        "link_errors": link_errors[:20],
        "link_error_count": len(link_errors),
        "to_create": len(to_create),
        "approve": created_batches,
        "reconcile": reconcile,
    }


async def step_orders(*, days: int) -> dict:
    """Baja N días aunque ya haya habido un sync reciente (el job 6h sí es incremental)."""
    from core.db import get_connection
    from erp.services.erp_sync_service import sync_orders_to_raw

    conn = await get_connection()
    try:
        await conn.execute(
            """
            UPDATE core.erp_connector_configs c
            SET orders_last_sync_at = timezone('utc', now()) - ($2::int * interval '1 day')
            FROM public.distribuidoras d
            WHERE d.id = c.tenant_id
              AND d.schema_name = $1;
            """,
            SCHEMA,
            max(int(days), 1) + 1,
        )
    finally:
        await conn.close()
    return await sync_orders_to_raw(SCHEMA, days=days)


async def step_project() -> dict:
    from erp.services.erp_order_projection_service import project_orders_raw
    from erp.services.erp_sync_service import reconcile_orders_raw_customers

    reconcile = await reconcile_orders_raw_customers(SCHEMA)
    batches: list[dict] = []
    while True:
        projected = await project_orders_raw(SCHEMA, dry_run=False, limit=2000)
        batches.append(projected)
        if int(projected.get("projected") or 0) <= 0:
            break
    return {"reconcile": reconcile, "batches": batches}


async def _run(*, apply: bool, steps: list[str], orders_days: int) -> dict:
    _prepare_env()
    _backend_path()
    report: dict = {
        "schema": SCHEMA,
        "company_id": COMPANY_ID,
        "apply": apply,
        "steps": steps,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    runners = {
        "creds": step_creds,
        "lists": step_lists,
        "products": lambda: step_products(apply=apply),
        "prices": step_prices,
        "stock": step_stock,
        "clients": step_clients,
        "recent_buyers": step_recent_buyers,
        "orders": lambda: step_orders(days=orders_days),
        "project": step_project,
    }
    if not apply:
        report["note"] = "dry-run: solo creds/lists/clients/prices/stock/orders escriben si --apply"
        return report
    for name in steps:
        fn = runners[name]
        report[name] = await fn()
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Integrar Odoo DIMER S.A. en tenant dimer")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--steps",
        default="creds,lists,clients,products,prices,stock",
        help="Pasos separados por coma",
    )
    parser.add_argument("--orders-days", type=int, default=7)
    args = parser.parse_args()
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    report = asyncio.run(_run(apply=args.apply, steps=steps, orders_days=args.orders_days))
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = OUT / f"erp-odoo-dimer-{stamp}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"\ninforme: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
