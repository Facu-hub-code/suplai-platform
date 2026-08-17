"""
cargar_insights.py
==================
Carga el CSV de Fase 8 en ia_tickets y replica los mensajes cruzados en
core.conversation_events (spec 013).

Uso:
    python scripts/fase-08-insights/cargar_insights.py --esquema <schema>

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
from datetime import timedelta
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

from _common import (
    format_dt,
    load_tenant_context,
    parse_bool,
    parse_dt,
    sanitize_schema_name,
    tenant_paths,
)

load_dotenv()

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


def table_name(schema: str, table: str) -> str:
    return f"{schema}.{table}"


async def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


async def get_columns(conn: asyncpg.Connection, schema: str, table: str) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position
        """,
        schema,
        table,
    )
    return [row["column_name"] for row in rows]


async def get_column_types(conn: asyncpg.Connection, schema: str, table: str) -> dict[str, str]:
    rows = await conn.fetch(
        """
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        """,
        schema,
        table,
    )
    return {row["column_name"]: f"{row['data_type']}:{row['udt_name']}" for row in rows}


def pick_column(columns: list[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def is_textual_type(type_name: str | None) -> bool:
    if not type_name:
        return False
    type_name = type_name.lower()
    return any(token in type_name for token in ["text", "character varying", "character", "uuid", "json"])


def resolve_client_identifier(column_type: str | None, client_id: int, client_phone: str) -> object:
    return client_phone if is_textual_type(column_type) else client_id


def build_insert_sql(schema: str, table: str, columns: list[str], values: dict[str, object]) -> tuple[str, list[object]]:
    insert_columns = [col for col in columns if col in values and values[col] is not None]
    if not insert_columns:
        raise ValueError(f"No hay columnas para insertar en {table_name(schema, table)}")
    placeholders = ", ".join(f"${idx}" for idx in range(1, len(insert_columns) + 1))
    sql = f"INSERT INTO {table_name(schema, table)} ({', '.join(insert_columns)}) VALUES ({placeholders}) RETURNING id"
    params = [values[col] for col in insert_columns]
    return sql, params


def choose_ticket_table(columns_by_table: dict[str, list[str]]) -> str:
    if "ia_tickets" in columns_by_table:
        return "ia_tickets"
    if "tickets" in columns_by_table:
        return "tickets"
    raise SystemExit("[FAIL] No se encontro ni ia_tickets ni tickets en el schema.")


async def main_async(esquema: str) -> None:
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("[FAIL] SUPABASE_DB_URL no esta configurada en .env")

    esquema = sanitize_schema_name(esquema)
    ctx = load_tenant_context(esquema)
    rows_path = tenant_paths(esquema)["outputs"] / "phase-08-notificaciones.csv"
    if not rows_path.exists():
        raise SystemExit(f"[FAIL] No se encontro el CSV de fase 8: {rows_path}")

    rows = await load_rows(rows_path)
    if not rows:
        raise SystemExit("[FAIL] El CSV de fase 8 esta vacio.")

    # Pooler 6543: cache de sentencias desactivado (regla supabase-mcp-connections).
    conn = None
    for attempt in range(5):
        try:
            conn = await asyncpg.connect(db_url, statement_cache_size=0)
            break
        except Exception as exc:
            if attempt == 4:
                raise
            await asyncio.sleep(2 * (attempt + 1))
            
    try:
        await conn.execute(f"SET search_path TO {esquema}, core, public, extensions")

        # spec 013: los mensajes cruzados van a core.conversation_events, no a n8n.
        tenant_id = await conn.fetchval(
            "SELECT id FROM public.distribuidoras WHERE schema_name = $1 LIMIT 1",
            esquema,
        )
        if tenant_id is None:
            raise SystemExit(f"[FAIL] No se encontro distribuidora para schema '{esquema}'.")

        ticket_table_candidates = {}
        for table in ("ia_tickets", "tickets"):
            cols = await get_columns(conn, esquema, table)
            if cols:
                ticket_table_candidates[table] = cols
        ticket_table = choose_ticket_table(ticket_table_candidates)
        ticket_cols = ticket_table_candidates[ticket_table]
        ticket_types = await get_column_types(conn, esquema, ticket_table)

        ticket_client_col = pick_column(ticket_cols, ["client_id", "client_phone"])
        ticket_desc_col = pick_column(ticket_cols, ["description", "detalle", "description_text"])
        ticket_status_col = pick_column(ticket_cols, ["status", "estado"])
        ticket_created_col = pick_column(ticket_cols, ["created_at", "fecha_creacion"])
        ticket_closed_col = pick_column(ticket_cols, ["closed_at", "cerrado_at", "resolved_at"])
        ticket_mock_col = pick_column(ticket_cols, ["is_mock"])
        if not all([ticket_client_col, ticket_desc_col, ticket_status_col, ticket_created_col, ticket_mock_col]):
            raise SystemExit(
                f"[FAIL] La tabla {table_name(esquema, ticket_table)} no tiene las columnas minimas requeridas."
            )

        ticket_client_type = ticket_types.get(ticket_client_col)

        print(f"[*] Leyendo {len(rows)} tickets del CSV...")
        print(f"[*] Tabla tickets detectada: {ticket_table}")
        print(f"[*] Estructura real tickets: {', '.join(ticket_cols)}")
        print("[*] Chat cruzado destino (spec 013): core.conversation_events")

        await conn.execute("BEGIN")
        try:
            deleted_tickets = await conn.execute(
                f"DELETE FROM {table_name(esquema, ticket_table)} WHERE is_mock = true"
            )
            deleted_chats = await conn.execute(
                """
                DELETE FROM core.conversation_events
                WHERE tenant_id = $1
                  AND event_payload->>'origin' = 'fase-08-insights'
                """,
                tenant_id,
            )
            await conn.execute("COMMIT")
            print(f"[*] Limpieza previa fase 8: {deleted_tickets} / {deleted_chats}")
        except Exception:
            await conn.execute("ROLLBACK")
            raise

        client_phone_to_id: dict[str, int] = {}
        client_id_rows = await conn.fetch(f"SELECT id, phone_number FROM {table_name(esquema, 'clients')}")
        for row in client_id_rows:
            client_phone_to_id[row["phone_number"]] = row["id"]

        conversation_cache: dict[str, int] = {}

        # Pre-seed all sessions for chat history in bulk
        chat_sessions = list({row.get("client_phone", "") for row in rows if row.get("client_phone")})
        if chat_sessions:
            await conn.executemany(
                """
                INSERT INTO core.conversations (tenant_id, schema_name, session_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (tenant_id, session_id)
                DO UPDATE SET updated_at = now(), schema_name = EXCLUDED.schema_name
                """,
                [(tenant_id, esquema, s) for s in chat_sessions],
            )

        session_rows = await conn.fetch(
            "SELECT session_id, id FROM core.conversations WHERE tenant_id = $1 AND schema_name = $2",
            tenant_id,
            esquema,
        )
        conversation_cache: dict[str, int] = {r["session_id"]: r["id"] for r in session_rows}

        inserted_tickets = 0
        inserted_chats = 0
        
        ticket_sql_template = None
        ticket_params_list = []
        chat_events_list = []

        for row in rows:
            client_phone = row.get("client_phone", "")
            client_id = client_phone_to_id.get(client_phone)
            if client_id is None:
                raise SystemExit(f"[FAIL] No se encontro el cliente con phone_number={client_phone!r} en {esquema}.clients")
            ticket_client_value = resolve_client_identifier(ticket_client_type, client_id, client_phone)

            created_at = parse_dt(row["created_at"])
            closed_at_raw = row.get("closed_at", "")
            closed_at = parse_dt(closed_at_raw) if closed_at_raw else None
            status = (row.get("status") or "").strip().lower()
            if status not in {"open", "closed"}:
                raise SystemExit(f"[FAIL] status invalido en CSV de fase 8: {status!r}")

            target_cols = [ticket_client_col, ticket_desc_col, ticket_status_col, ticket_created_col, ticket_mock_col]
            if ticket_closed_col:
                target_cols.append(ticket_closed_col)

            if ticket_sql_template is None:
                placeholders = ", ".join(f"${idx+1}" for idx in range(len(target_cols)))
                ticket_sql_template = f"INSERT INTO {table_name(esquema, ticket_table)} ({', '.join(target_cols)}) VALUES ({placeholders})"

            params = [ticket_client_value, row.get("description", ""), status, created_at, parse_bool(row.get("is_mock", "true"))]
            if ticket_closed_col:
                params.append(closed_at)
            ticket_params_list.append(params)
            inserted_tickets += 1

            incoming = row.get("mensaje_cruzado_incoming", "").strip()
            if incoming and client_phone in conversation_cache:
                categoria = row.get("categoria", "")
                ticket_ref = row.get("ticket_ref", "")
                conv_id = conversation_cache[client_phone]

                # 1. Incoming human message
                human_payload = {
                    "text": incoming,
                    "is_mock": True,
                    "origin": "fase-08-insights",
                    "sender_type": "human",
                    "session_id": client_phone,
                    "client_phone": client_phone,
                    "ticket_ref": ticket_ref,
                    "categoria": categoria,
                    "status": status,
                }
                chat_events_list.append((
                    tenant_id,
                    conv_id,
                    f"mock-fase08-{client_phone}-human-{ticket_ref}",
                    "user_message",
                    json.dumps(human_payload, ensure_ascii=False),
                    created_at + timedelta(minutes=15),
                ))
                inserted_chats += 1

                # 2. Outgoing AI message
                if categoria == "Calidad":
                    ai_reply = f"Hola, disculpas por el inconveniente. Registré tu reclamo por la calidad del producto con el ticket {ticket_ref}. Un asesor se contactará a la brevedad."
                elif categoria == "Logistica":
                    ai_reply = f"Hola, lamento la demora con tu pedido. Ya generé un ticket de reclamo a logística con la referencia {ticket_ref} para agilizar la entrega. Te mantendremos informado."
                else:
                    ai_reply = f"Hola, recibí tu mensaje. Generé un ticket de soporte con la referencia {ticket_ref} para dar seguimiento a tu caso. Un asesor se comunicará pronto."

                ai_payload = {
                    "text": ai_reply,
                    "is_mock": True,
                    "origin": "fase-08-insights",
                    "sender_type": "ai",
                    "session_id": client_phone,
                    "client_phone": client_phone,
                    "ticket_ref": ticket_ref,
                    "categoria": categoria,
                    "status": status,
                }
                chat_events_list.append((
                    tenant_id,
                    conv_id,
                    f"mock-fase08-{client_phone}-ai-{ticket_ref}",
                    "assistant_message",
                    json.dumps(ai_payload, ensure_ascii=False),
                    created_at + timedelta(minutes=16),
                ))
                inserted_chats += 1

        if ticket_sql_template and ticket_params_list:
            await conn.executemany(ticket_sql_template, ticket_params_list)

        if chat_events_list:
            await conn.executemany(
                """
                INSERT INTO core.conversation_events
                (tenant_id, conversation_id, request_id, event_type, event_payload, created_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                """,
                chat_events_list,
            )

        total_tickets = await conn.fetchval(
            f"SELECT COUNT(*) FROM {table_name(esquema, ticket_table)} WHERE is_mock = true"
        )
        open_tickets = await conn.fetchval(
            f"SELECT COUNT(*) FROM {table_name(esquema, ticket_table)} WHERE is_mock = true AND lower({ticket_status_col}) = 'open'"
        )
        total_chats = await conn.fetchval(
            """
            SELECT COUNT(*) FROM core.conversation_events
            WHERE tenant_id = $1
              AND event_payload->>'origin' = 'fase-08-insights'
            """,
            tenant_id,
        )

        print("\n" + "=" * 72)
        print("VERIFICACION FASE 8 - INSIGHTS")
        print("=" * 72)
        print(f"  Tickets insertados:   {inserted_tickets}")
        print(f"  Tickets mock totales: {total_tickets}")
        print(f"  Tickets open:         {open_tickets}")
        print(f"  Chats cruzados:       {inserted_chats}")
        print(f"  Chats mock fase 8:    {total_chats}")
        print("=" * 72)
        cross_rows = [row for row in rows if row.get("mensaje_cruzado_incoming")]
        if len(cross_rows) < 3:
            print("[WARN] Hay menos de 3 tickets abiertos con mensaje cruzado.")

    except Exception as exc:
        print(f"[FAIL] Error durante la carga de insights: {exc}")
        raise
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga los insights mock de la Fase 8.")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant (ej: al_fuego)")
    args = parser.parse_args()
    asyncio.run(main_async(args.esquema))


if __name__ == "__main__":
    main()
