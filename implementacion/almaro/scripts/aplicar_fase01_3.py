#!/usr/bin/env python3
"""Aplica identidad/contexto Maro sin pisar reglas_negocio ni el teléfono 379."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "implementacion/almaro/outputs/phase-01-3-prompt-config.json"
SCHEMA = "almaro"
PHONE = "5493795151208"


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


async def main() -> int:
    load_dotenv(ROOT.parent / "backend-supabase/.env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        before = await conn.fetchrow(
            """
            SELECT agent_phone_number::text AS phone,
                   (reglas_negocio ? 'cross_upsell') AS has_cross
            FROM public.distribuidoras WHERE schema_name = $1
            """,
            SCHEMA,
        )
        print(f"[*] Antes: phone={before['phone']} cross_upsell={before['has_cross']}")

        await conn.execute(
            """
            UPDATE public.distribuidoras
            SET identidad = $1,
                contexto = $2,
                updated_at = NOW()
            WHERE schema_name = $3
            """,
            cfg["identidad"],
            cfg["contexto"],
            SCHEMA,
        )

        after = await conn.fetchrow(
            """
            SELECT LEFT(identidad, 40) AS id_preview,
                   agent_phone_number::text AS phone,
                   (reglas_negocio ? 'cross_upsell') AS has_cross,
                   (identidad ILIKE 'Sos Maro%') AS es_maro
            FROM public.distribuidoras WHERE schema_name = $1
            """,
            SCHEMA,
        )
        print(f"OK identidad={after['id_preview']!r} phone={after['phone']} maro={after['es_maro']} cross={after['has_cross']}")
        if after["phone"] != PHONE:
            print("[FAIL] El teléfono cambió.")
            return 1
        if not after["es_maro"] or not after["has_cross"]:
            print("[FAIL] Prompt o reglas no quedaron como se esperaba.")
            return 1
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
