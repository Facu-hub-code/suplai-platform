#!/usr/bin/env python3
"""Proyecta erp_orders_raw → pedidos/items_pedido para Benfresh.

Usa el servicio canónico del backend (misma lógica que
POST /{schema}/erp/orders-raw/project).

Uso:
  set -a && source ../backend-supabase/.env && set +a
  # dry-run:
  python scripts/benfresh/project_erp_orders.py
  # aplicar (puede requerir varias pasadas):
  python scripts/benfresh/project_erp_orders.py --apply
  python scripts/benfresh/project_erp_orders.py --apply --batches 5 --limit 2000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT.parent / "backend-supabase"
OUT = ROOT / "implementacion" / "benfresh" / "outputs"
SCHEMA = "benfresh"


def _prepare_env() -> None:
    # Preferir pooler 6543
    for key in ("SUPABASE_DB_URL", "SUPABASE_DB_URL_POOLER", "DATABASE_URL"):
        val = os.getenv(key) or ""
        if ":5432/" in val:
            os.environ[key] = val.replace(":5432/", ":6543/")


async def _run_batches(*, dry_run: bool, limit: int, batches: int) -> list[dict]:
    sys.path.insert(0, str(BACKEND))
    from erp.services.erp_order_projection_service import project_orders_raw  # noqa: WPS433

    results: list[dict] = []
    for i in range(1, batches + 1):
        print(f"[*] Batch {i}/{batches} dry_run={dry_run} limit={limit}")
        result = await project_orders_raw(
            SCHEMA,
            dry_run=dry_run,
            limit=limit,
            log_completion=True,
        )
        results.append(result)
        print(
            f"  outcome={result.get('outcome')} examined={result.get('examined')} "
            f"ready={result.get('ready_to_project')} projected={result.get('projected')} "
            f"already={result.get('already_projected')} skipped={result.get('skipped')} "
            f"failed={result.get('failed')}"
        )
        issues = result.get("issues") or []
        if issues:
            print("  issues:")
            for issue in issues[:12]:
                print(
                    f"    - {issue.get('code')}: count={issue.get('count')} "
                    f"samples={issue.get('sample_order_refs')} skus={issue.get('sample_skus')}"
                )
        # En dry-run una pasada alcanza; en apply paramos si no proyectó nada nuevo
        if dry_run:
            break
        if int(result.get("projected") or 0) <= 0 and int(result.get("examined") or 0) <= 0:
            break
        if int(result.get("projected") or 0) <= 0 and int(result.get("ready_to_project") or 0) <= 0:
            break
    return results


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    load_dotenv(BACKEND / ".env")
    load_dotenv()
    _prepare_env()

    parser = argparse.ArgumentParser(description="Proyectar pedidos ERP Benfresh")
    parser.add_argument("--apply", action="store_true", help="Escribir pedidos canónicos")
    parser.add_argument("--limit", type=int, default=2000, help="Filas por batch (max 2000)")
    parser.add_argument("--batches", type=int, default=5, help="Máx batches en --apply")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    dry_run = not args.apply
    results = asyncio.run(
        _run_batches(dry_run=dry_run, limit=min(max(args.limit, 1), 2000), batches=args.batches)
    )

    stamp = date.today().isoformat()
    out_path = OUT / f"erp-orders-projection-{stamp}{'-dry' if dry_run else ''}.json"
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"[*] Guardado: {out_path}")
    if dry_run:
        print("[*] Dry-run. Re-ejecutá con --apply para materializar pedidos.")


if __name__ == "__main__":
    main()
