"""Aplica la RPC de shift, recorta tickets y corre Field 6.1 para demo."""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV = Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env")
SCHEMA = "demo"


def _load() -> str:
    load_dotenv(ROOT / ".env", override=False)
    if BACKEND_ENV.exists():
        load_dotenv(BACKEND_ENV, override=False)
    raw = os.getenv("SUPABASE_DB_URL") or os.getenv("SUPABASE_DB_URL_POOLER") or ""
    if not raw:
        raise SystemExit("SUPABASE_DB_URL missing")
    return raw.replace(":5432/", ":6543/")


async def prepare() -> None:
    conn = await asyncpg.connect(_load(), statement_cache_size=0)
    try:
        sql = Path(__file__).with_name("shift_fechas.sql").read_text(encoding="utf-8")
        await conn.execute(sql)
        result = await conn.fetchval("SELECT demo.generate_daily_demo_orders()")
        print("[OK] generate:", result)
        result = await conn.fetchval("SELECT demo.shift_sales_demo_dates()")
        print("[OK] shift:", result)
        result = await conn.fetchval("SELECT demo.sanitize_field_task_skus()")
        print("[OK] sanitize skus:", result)
        deleted = await conn.fetchval(
            """
            WITH keep AS (
              (SELECT id FROM demo.ia_tickets WHERE status='open' ORDER BY created_at DESC LIMIT 10)
              UNION
              (SELECT id FROM demo.ia_tickets WHERE status='closed' ORDER BY created_at DESC LIMIT 8)
            )
            DELETE FROM demo.ia_tickets WHERE id NOT IN (SELECT id FROM keep)
            RETURNING 1
            """
        )
        # fetchval on DELETE RETURNING 1 only gets first row; count instead
        n_open = await conn.fetchval("SELECT COUNT(*) FROM demo.ia_tickets WHERE status='open'")
        n_all = await conn.fetchval("SELECT COUNT(*) FROM demo.ia_tickets")
        print(f"[OK] tickets open={n_open} total={n_all}")
        await conn.execute(
            "UPDATE demo.field_tournaments SET estado='CERRADO', updated_at=now() WHERE estado='ACTIVO'"
        )
    finally:
        await conn.close()


def main() -> None:
    os.environ["SUPABASE_DB_URL"] = _load()
    asyncio.run(prepare())
    py = sys.executable
    field = ROOT / "scripts" / "fase-06-1-field"
    steps = [
        [py, str(field / "setup_templates.py"), "--esquema", SCHEMA],
        [py, str(field / "setup_objetivos.py"), "--esquema", SCHEMA, "--limpiar"],
        [py, str(field / "setup_torneo.py"), "--esquema", SCHEMA, "--forzar"],
        [py, str(field / "retrain_ml.py"), "--esquema", SCHEMA],
        [py, str(field / "seed_tareas_historicas.py"), "--esquema", SCHEMA, "--dias", "30"],
        [py, str(field / "trigger_tareas.py"), "--esquema", SCHEMA, "--dias", "6"],
    ]
    for cmd in steps:
        print("\n>>>", " ".join(cmd))
        rc = subprocess.run(cmd, cwd=str(ROOT), env=os.environ.copy())
        if rc.returncode != 0:
            print(f"[WARN] falló {cmd[1]} code={rc.returncode}")


if __name__ == "__main__":
    main()
