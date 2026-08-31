#!/usr/bin/env python3
"""Reconstruye dinamic.category_documents (RAG de categorías). Schema confirmado: dinamic."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA = "dinamic"
ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT.parent / "backend-supabase"

load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(BACKEND_ROOT))


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


async def main() -> int:
    from utils.vectorizacion_categorias import rebuild_categoria_documents  # type: ignore

    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)
    print(f"[*] schema_name confirmado: {SCHEMA}", flush=True)
    print("[*] Reconstruyendo RAG de categorías (category_documents)...", flush=True)
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        result = await rebuild_categoria_documents(SCHEMA, conn, batch_size=20)
    finally:
        await conn.close()
    print(f"[+] RAG: {result}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
