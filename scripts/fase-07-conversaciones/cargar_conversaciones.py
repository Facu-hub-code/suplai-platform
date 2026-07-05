"""
cargar_conversaciones.py
=======================
Carga el historial mock de Fase 7 en n8n_chat_histories.

Uso:
    python scripts/fase-07-conversaciones/cargar_conversaciones.py --esquema <nombre_esquema>

Variables de entorno requeridas:
    SUPABASE_DB_URL
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

from _common import format_dt, load_tenant_context, parse_bool, parse_dt, sanitize_schema_name, tenant_paths

load_dotenv()

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


def table_name(schema: str, table: str) -> str:
    return f"{schema}.{table}"


async def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


async def main_async(esquema: str) -> None:
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("[FAIL] SUPABASE_DB_URL no esta configurada en .env")

    esquema = sanitize_schema_name(esquema)
    ctx = load_tenant_context(esquema)
    paths = tenant_paths(esquema)
    messages_path = paths["outputs"] / "phase-07-mensajes.csv"
    if not messages_path.exists():
        raise SystemExit(f"[FAIL] No se encontro el CSV de mensajes: {messages_path}")

    rows = await load_rows(messages_path)
    if not rows:
        raise SystemExit("[FAIL] El CSV de mensajes esta vacio.")

    # Pooler 6543: cache de sentencias desactivado (regla supabase-mcp-connections).
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        print(f"[*] Leyendo {len(rows)} mensajes del CSV...")
        print("[*] Destino canonico (spec 013): core.conversations + core.conversation_events")

        tenant_id = await conn.fetchval(
            "SELECT id FROM public.distribuidoras WHERE schema_name = $1 LIMIT 1",
            esquema,
        )
        if tenant_id is None:
            raise SystemExit(f"[FAIL] No se encontro distribuidora para schema '{esquema}'.")

        # Limpieza previa de eventos mock (idempotente).
        deleted = await conn.execute(
            """
            DELETE FROM core.conversation_events
            WHERE tenant_id = $1
              AND event_payload->>'is_mock' = 'true'
            """,
            tenant_id,
        )
        print(f"[*] Limpieza previa eventos mock (core): {deleted}")

        conversation_cache: dict[str, int] = {}
        last_event_per_session: dict[str, tuple] = {}

        async def get_conversation_id(session: str) -> int:
            cached = conversation_cache.get(session)
            if cached is not None:
                return cached
            conv_id = await conn.fetchval(
                """
                INSERT INTO core.conversations (tenant_id, schema_name, session_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (tenant_id, session_id)
                DO UPDATE SET updated_at = now(), schema_name = EXCLUDED.schema_name
                RETURNING id
                """,
                tenant_id,
                esquema,
                session,
            )
            conversation_cache[session] = int(conv_id)
            return int(conv_id)

        inserted = 0
        for idx, row in enumerate(rows):
            session_id = row["session_id"] or row["client_phone"]
            sender_type = (row["sender_type"] or row["type"] or "").lower()
            message = row["message"] or row["content"]
            created_at = parse_dt(row["created_at"])
            is_mock = parse_bool(row.get("is_mock", "true"))

            event_type = "user_message" if sender_type in ("human", "user", "cliente") else "assistant_message"

            payload = {
                "text": message,
                "is_mock": is_mock,
                "source": "mock_fase07",
                "sender_type": sender_type,
                "client_phone": row.get("client_phone", session_id),
            }

            conversation_id = await get_conversation_id(session_id)
            await conn.execute(
                """
                INSERT INTO core.conversation_events
                (tenant_id, conversation_id, request_id, event_type, event_payload, created_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                """,
                tenant_id,
                conversation_id,
                f"mock-fase07-{session_id}-{idx}",
                event_type,
                json.dumps(payload, ensure_ascii=False),
                created_at,
            )
            inserted += 1

            prev = last_event_per_session.get(session_id)
            if prev is None or created_at >= prev[0]:
                last_event_per_session[session_id] = (created_at, event_type)

        total_rows = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM core.conversation_events
            WHERE tenant_id = $1 AND event_payload->>'is_mock' = 'true'
            """,
            tenant_id,
        )
        sessions = len(conversation_cache)
        human_last = [s for s, (_, et) in last_event_per_session.items() if et == "user_message"]

        print("\n" + "=" * 72)
        print("VERIFICACION FASE 7 - CONVERSACIONES (core)")
        print("=" * 72)
        print(f"  Eventos insertados:   {inserted}")
        print(f"  Eventos mock totales: {total_rows}")
        print(f"  Sesiones mock:        {sessions}")
        print(f"  Ultimo mensaje human: {len(human_last)}")
        print("=" * 72)
        if human_last:
            print("[WARN] Hay conversaciones cuyo ultimo evento sigue siendo user_message. Revisar generacion.")

    except Exception as exc:
        print(f"[FAIL] Error durante la carga de conversaciones: {exc}")
        raise
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga conversaciones mock de Fase 7.")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant (ej: al_fuego)")
    args = parser.parse_args()
    asyncio.run(main_async(args.esquema))


if __name__ == "__main__":
    main()
