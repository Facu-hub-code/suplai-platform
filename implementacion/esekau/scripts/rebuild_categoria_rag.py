#!/usr/bin/env python3
"""Copia tags → categorias en esekau y reconstruye RAG.

schema_name = esekau (confirmado). Equivale a populate-from-tags + rebuild.
Evita el HTTP 500 de categoria_ids en el endpoint de prod.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA = "esekau"
ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT.parent / "backend-supabase"

load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(BACKEND_ROOT))


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


async def populate(conn: asyncpg.Connection) -> tuple[int, int]:
    inserted = await conn.fetch(
        f"""
        INSERT INTO {SCHEMA}.categorias (id, name, description, parent_id, sort_order, image_url, created_at, updated_at)
        SELECT t.id, t.name, t.description, NULL, 0, NULL, now(), now()
        FROM {SCHEMA}.tags t
        ON CONFLICT (id) DO UPDATE
            SET name        = EXCLUDED.name,
                description = EXCLUDED.description,
                updated_at  = now()
        RETURNING id
        """
    )
    await conn.execute(
        f"""
        UPDATE {SCHEMA}.categorias c
        SET parent_id = t.parent_id
        FROM {SCHEMA}.tags t
        WHERE c.id = t.id
          AND t.parent_id IS NOT NULL
        """
    )
    assignments = await conn.fetch(
        f"""
        INSERT INTO {SCHEMA}.product_categories (product_code, categoria_id)
        SELECT pt.product_code, pt.tag_id
        FROM {SCHEMA}.product_tags pt
        WHERE EXISTS (
            SELECT 1 FROM {SCHEMA}.categorias c WHERE c.id = pt.tag_id
        )
        ON CONFLICT (product_code, categoria_id) DO NOTHING
        RETURNING product_code
        """
    )
    await conn.execute(
        f"""
        SELECT setval(
            pg_get_serial_sequence('{SCHEMA}.categorias', 'id'),
            COALESCE((SELECT MAX(id) FROM {SCHEMA}.categorias), 1) + 1000
        )
        """
    )
    return len(inserted), len(assignments)


async def main() -> int:
    from utils.vectorizacion_categorias import rebuild_categoria_documents  # type: ignore

    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)
    print(f"[*] schema_name confirmado: {SCHEMA}", flush=True)

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        upserted, copied = await populate(conn)
        print(f"[+] categorias upsert={upserted} asignaciones={copied}", flush=True)
        print("[*] Reconstruyendo RAG de categorías...", flush=True)
        result = await rebuild_categoria_documents(SCHEMA, conn, batch_size=20)
        print(f"[+] RAG: {result}", flush=True)
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
