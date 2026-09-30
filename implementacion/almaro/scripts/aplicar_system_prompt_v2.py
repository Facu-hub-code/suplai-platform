#!/usr/bin/env python3
"""Sube phase-01-3-system-prompt-v2.md a public.distribuidoras.system_prompt (solo almaro)."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
TENANT_DIR = ROOT / "implementacion/almaro"
PROMPT_FILE = TENANT_DIR / "outputs/phase-01-3-system-prompt-v2.md"
SCHEMA = "almaro"


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expected-md5",
        help="md5 del system_prompt actual en BD; si no coincide, no se escribe.",
    )
    args = parser.parse_args()

    load_dotenv(ROOT.parent / "backend-supabase/.env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL", file=sys.stderr)
        return 1
    new_prompt = PROMPT_FILE.read_text(encoding="utf-8")

    conn = await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)
    try:
        current = await conn.fetchval(
            "SELECT system_prompt FROM public.distribuidoras WHERE schema_name = $1", SCHEMA
        )
        current_md5 = hashlib.md5((current or "").encode("utf-8")).hexdigest()
        if args.expected_md5 and current_md5 != args.expected_md5:
            print(f"[FAIL] El prompt en BD cambió (md5={current_md5}). Revisar antes de pisarlo.")
            return 1
        if current == new_prompt:
            print("[*] Sin cambios.")
            return 0

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = TENANT_DIR / f"outputs/system-prompt-backup-{stamp}.md"
        backup.write_text(current or "", encoding="utf-8")
        print(f"[*] Backup: {backup.relative_to(ROOT)}")

        await conn.execute(
            "UPDATE public.distribuidoras SET system_prompt = $1, updated_at = NOW() WHERE schema_name = $2",
            new_prompt,
            SCHEMA,
        )
        after = await conn.fetchrow(
            """
            SELECT length(system_prompt) AS len,
                   (system_prompt LIKE '%## Marcas que no vendemos%') AS has_marcas,
                   metadata->>'use_new_system_prompt' AS flag
            FROM public.distribuidoras WHERE schema_name = $1
            """,
            SCHEMA,
        )
        print(f"OK len={after['len']} marcas={after['has_marcas']} use_new_system_prompt={after['flag']}")
        return 0 if after["has_marcas"] else 1
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
