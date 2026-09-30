#!/usr/bin/env python3
"""Fallback local si MCP bloquea DROP SCHEMA.

schema_name origen = distribuidora_saffadi (confirmado).
Destino WhatsApp = kiki_market.
Pooler 6543, statement_cache_size=0, min_size=1, max_size=2.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SAFFADI_SCHEMA = "distribuidora_saffadi"
SAFFADI_ID = "99e26d8d-81c6-4c10-904d-5d3d942714fb"
KIKI_SCHEMA = "kiki_market"
KIKI_ID = "7fa7dee6-1aaa-48d1-b60c-46803820f0c1"
PHONE = 5493582430647
PROJECT_ID = "bc21723e-d43c-464f-a6c6-01d17d1084e6"
AUTH_IDS = (
    "12cc3c7f-2b5d-4d9f-bd42-296098b6ec8b",
    "5dcb710c-4139-4445-bc11-90a8e2cd66bf",
    "3212ff8f-8ca7-4f03-ad67-8bdc6a3dfa0f",
)
HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def _load_envs() -> None:
    for path in (
        Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
        ROOT.parent / "backend-supabase" / ".env",
        ROOT / ".env",
    ):
        if path.exists():
            load_dotenv(path, override=False)


async def run(apply: bool) -> None:
    _load_envs()
    url = force_pooler(os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "")
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL_POOLER")

    sql_path = HERE.parents[1] / "outputs" / "offboard.sql"
    statements = [
        s.strip()
        for s in sql_path.read_text(encoding="utf-8").split(";")
        if s.strip() and not s.strip().startswith("--")
    ]

    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        if not apply:
            print(f"[dry-run] {len(statements)} statements from {sql_path}")
            for i, stmt in enumerate(statements, 1):
                print(f"--- {i} ---\n{stmt[:200]}")
            return
        for i, stmt in enumerate(statements, 1):
            print(f"[*] {i}/{len(statements)} {stmt.splitlines()[0][:80]}")
            await conn.execute(stmt)
        print("[ok] offboard aplicado")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
