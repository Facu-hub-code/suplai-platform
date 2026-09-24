#!/usr/bin/env python3
"""Cierra huecos operativos de la integración Odoo de Benfresh.

Orden: productos → listas nuevas → clientes nuevos → resolver cola ya vinculada
→ reconciliar pedidos raw → proyectar canónicos.

Uso:
  set -a && source ../../../backend-supabase/.env && set +a
  python implementacion/benfresh/scripts/cerrar_huecos_erp_odoo.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT.parent / "backend-supabase"
OUT = ROOT / "implementacion" / "benfresh" / "outputs"
SCHEMA = "benfresh"

PROMOTE_SKUS = [
    "0693635886929",
    "0693635886950",
    "0693635886967",
    "0693635886981",
    "89090214",
    "89090215",
    "89090216",
]
PRICE_LIST_RAW_IDS = [3937, 6387]  # La Real, Luncheros
QUEUE_ALREADY_LINKED = [
    (1008, 526),
    (43, 527),
    (1100, 535),
    (979, 523),
    (986, 528),
    (1014, 525),
    (1037, 530),
    (1040, 524),
    (1115, 536),
    (973, 521),
    (1024, 529),
    (1045, 531),
]


def _prepare_env() -> None:
    for key in ("SUPABASE_DB_URL", "SUPABASE_DB_URL_POOLER", "DATABASE_URL"):
        val = os.getenv(key) or ""
        if ":5432/" in val:
            os.environ[key] = val.replace(":5432/", ":6543/")


async def _resolve_already_linked() -> dict:
    sys.path.insert(0, str(BACKEND))
    from core.db import get_connection, validate_schema

    conn = await get_connection()
    try:
        schema = await validate_schema(SCHEMA, conn=conn)
        resolved = 0
        for queue_id, client_id in QUEUE_ALREADY_LINKED:
            row = await conn.fetchrow(
                f"""
                UPDATE "{schema}".erp_customer_onboarding_queue
                SET status = 'resuelto',
                    match_status = 'vinculado_existente',
                    resolved_client_id = $2,
                    resolved_at = COALESCE(resolved_at, now()),
                    review_notes = COALESCE(review_notes, 'cierre huecos 2026-09-24: cliente ya existía'),
                    updated_at = now()
                WHERE id = $1 AND status = 'pendiente'
                RETURNING id;
                """,
                queue_id,
                client_id,
            )
            if row:
                resolved += 1
        return {"resolved": resolved, "examined": len(QUEUE_ALREADY_LINKED)}
    finally:
        await conn.close()


async def _mark_catalog(skus: list[str]) -> int:
    sys.path.insert(0, str(BACKEND))
    from core.db import get_connection, validate_schema

    conn = await get_connection()
    try:
        schema = await validate_schema(SCHEMA, conn=conn)
        result = await conn.execute(
            f"""
            UPDATE "{schema}".productos
            SET en_catalogo = true, updated_at = now()
            WHERE product_code = ANY($1::text[])
              AND COALESCE(en_catalogo, false) IS FALSE;
            """,
            skus,
        )
        return int(result.split()[-1]) if result else 0
    finally:
        await conn.close()


async def _run(*, apply: bool) -> dict:
    sys.path.insert(0, str(BACKEND))
    from erp.services.erp_customer_onboarding_service import approve_customers_bulk
    from erp.services.erp_order_projection_service import project_orders_raw
    from erp.services.erp_pricelist_onboarding_service import apply_pricelist_onboarding
    from erp.services.erp_product_promote_service import promote_erp_products_bulk
    from erp.services.erp_sync_service import reconcile_orders_raw_customers

    report: dict = {
        "schema": SCHEMA,
        "apply": apply,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }

    print("[1] Promover SKUs solo-ERP")
    report["products"] = await promote_erp_products_bulk(
        SCHEMA, dry_run=not apply, skus=PROMOTE_SKUS
    )
    print(f"    {report['products']}")
    if apply:
        report["products_en_catalogo"] = await _mark_catalog(PROMOTE_SKUS)
        print(f"    en_catalogo marcados: {report['products_en_catalogo']}")

    print("[2] Onboarding listas La Real + Luncheros")
    lists = []
    for raw_id in PRICE_LIST_RAW_IDS:
        result = await apply_pricelist_onboarding(
            SCHEMA, raw_id, confirm=apply, dry_run=not apply
        )
        lists.append({"raw_id": raw_id, **{k: result.get(k) for k in ("dry_run", "lista_precios_id", "stages")}})
        print(f"    raw {raw_id}: {lists[-1]}")
    report["price_lists"] = lists

    print("[3] Approve clientes nuevos (skip duplicados)")
    report["customers_bulk"] = await approve_customers_bulk(
        SCHEMA,
        dry_run=not apply,
        assign_to_all_sellers=True,
        use_synthetic_for_missing=True,
        skip_duplicates=True,
    )
    print(f"    {report['customers_bulk']}")

    if apply:
        print("[4] Resolver cola ya vinculada")
        report["queue_resolve"] = await _resolve_already_linked()
        print(f"    {report['queue_resolve']}")

        print("[5] Reconciliar cliente_id en erp_orders_raw")
        report["orders_reconcile"] = await reconcile_orders_raw_customers(SCHEMA)
        print(f"    {report['orders_reconcile']}")

    print("[6] Proyectar pedidos ERP → canónicos")
    projection_batches = []
    batches = 3 if apply else 1
    for i in range(1, batches + 1):
        result = await project_orders_raw(
            SCHEMA, dry_run=not apply, limit=2000, log_completion=True
        )
        projection_batches.append(result)
        print(
            f"    batch {i}: outcome={result.get('outcome')} "
            f"examined={result.get('examined')} ready={result.get('ready_to_project')} "
            f"projected={result.get('projected')} already={result.get('already_projected')} "
            f"failed={result.get('failed')}"
        )
        if not apply:
            break
        if int(result.get("projected") or 0) <= 0:
            break
    report["orders_projection"] = projection_batches
    return report


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv(BACKEND / ".env")
    load_dotenv()
    _prepare_env()

    parser = argparse.ArgumentParser(description="Cerrar huecos ERP Odoo Benfresh")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    report = asyncio.run(_run(apply=args.apply))
    stamp = date.today().isoformat()
    suffix = "" if args.apply else "-dry"
    out_path = OUT / f"erp-odoo-huecos-{stamp}{suffix}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[*] Guardado: {out_path}")


if __name__ == "__main__":
    main()
