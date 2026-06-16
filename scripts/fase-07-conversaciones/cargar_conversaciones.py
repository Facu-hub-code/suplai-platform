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

    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(f"SET search_path TO {esquema}, core, public, extensions")
        print(f"[*] Leyendo {len(rows)} mensajes del CSV...")
        print("[*] Estructura real detectada: session_id, message(jsonb), created_at, is_mock")

        await conn.execute("BEGIN")
        try:
            deleted = await conn.execute(f"DELETE FROM {table_name(esquema, 'n8n_chat_histories')} WHERE is_mock = true")
            await conn.execute("COMMIT")
            print(f"[*] Limpieza previa chat mock: {deleted}")
        except Exception:
            await conn.execute("ROLLBACK")
            raise

        inserted = 0
        for row in rows:
            session_id = row["session_id"] or row["client_phone"]
            sender_type = row["sender_type"] or row["type"]
            message = row["message"] or row["content"]
            created_at = parse_dt(row["created_at"])
            is_mock = parse_bool(row.get("is_mock", "true"))

            payload = {
                "sender_type": sender_type,
                "type": sender_type,
                "message": message,
                "content": message,
                "created_at": format_dt(created_at),
                "is_mock": is_mock,
                "session_id": session_id,
                "client_phone": row.get("client_phone", session_id),
            }

            await conn.execute(
                f"""
                INSERT INTO {table_name(esquema, 'n8n_chat_histories')}
                (session_id, message, created_at, is_mock)
                VALUES ($1, $2::jsonb, $3, $4)
                """,
                session_id,
                json.dumps(payload, ensure_ascii=False),
                created_at,
                is_mock,
            )
            inserted += 1

        total_rows = await conn.fetchval(
            f"SELECT COUNT(*) FROM {table_name(esquema, 'n8n_chat_histories')} WHERE is_mock = true"
        )
        sessions = await conn.fetchval(
            f"SELECT COUNT(DISTINCT session_id) FROM {table_name(esquema, 'n8n_chat_histories')} WHERE is_mock = true"
        )

        rows_last = await conn.fetch(
            f"""
            SELECT t.session_id, t.message, t.created_at
            FROM {table_name(esquema, 'n8n_chat_histories')} t
            JOIN (
                SELECT session_id, MAX(created_at) AS max_created_at
                FROM {table_name(esquema, 'n8n_chat_histories')}
                WHERE is_mock = true
                GROUP BY session_id
            ) m
            ON m.session_id = t.session_id AND m.max_created_at = t.created_at
            WHERE t.is_mock = true
            ORDER BY t.session_id
            """
        )

        human_last = []
        for row in rows_last:
            msg = row["message"]
            if isinstance(msg, dict):
                sender = str(msg.get("sender_type") or msg.get("type") or "").lower()
                if sender == "human":
                    human_last.append(row)

        print("\n" + "=" * 72)
        print("VERIFICACION FASE 7 - CONVERSACIONES")
        print("=" * 72)
        print(f"  Mensajes insertados:  {inserted}")
        print(f"  Mensajes mock totales:{total_rows}")
        print(f"  Sesiones mock:        {sessions}")
        print(f"  Ultimo mensaje human: {len(human_last)}")
        print("=" * 72)
        if human_last:
            print("[WARN] Hay conversaciones cuyo ultimo mensaje sigue siendo human. Revisar generacion.")

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
