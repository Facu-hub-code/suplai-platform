#!/usr/bin/env python3
"""Provisiona el tenant vacío abmauri, su distribuidora y owner de backoffice."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "abmauri"
SOURCE = "gonzales"
ADMIN_EMAIL = "admin@abmauri.com"
ADMIN_PASSWORD = "Suplai2026"
HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]

SELLER_TOOLS_OFF = {
    "ping": False,
    "seller_help": False,
    "list_seller_clients": False,
    "clear_seller_context": False,
    "edit_order_for_client": False,
    "create_order_for_client": False,
    "resolve_free_text_order": False,
    "confirm_order_for_client": False,
    "get_seller_client_details": False,
    "get_seller_selected_client": False,
    "set_seller_selected_client": False,
    "suggest_order_boost_for_client": False,
    "get_open_order_status_for_client": False,
}

_NEXTVAL_RE = re.compile(
    r"""nextval\('(?:(?:"(?P<qschema>[^"]+)")|(?P<schema>[^.]+))\."""
    r"""(?:(?:"(?P<qseq>[^"]+)")|(?P<seq>[^"]+))'::regclass\)""",
    re.I,
)


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def load_env() -> None:
    for path in (
        Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
        ROOT / ".env",
    ):
        if path.exists():
            load_dotenv(path, override=False)
    url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or ""
    if url:
        pooler_url = force_pooler(url)
        os.environ["SUPABASE_DB_URL_POOLER"] = pooler_url
        os.environ["SUPABASE_DB_URL"] = pooler_url


load_env()
sys.path.append(str(ROOT / "scripts"))
from sync_tenant_schema_objects import sync_schema  # noqa: E402


async def fix_sequence_defaults(conn: asyncpg.Connection) -> int:
    rows = await conn.fetch(
        """
        SELECT table_name, column_name, column_default
        FROM information_schema.columns
        WHERE table_schema = $1 AND column_default IS NOT NULL
        """,
        SCHEMA,
    )
    fixed = 0
    for row in rows:
        match = _NEXTVAL_RE.search(str(row["column_default"] or ""))
        if not match:
            continue
        sequence_schema = (match.group("qschema") or match.group("schema") or "").strip('"').lower()
        sequence_name = (match.group("qseq") or match.group("seq") or "").strip('"')
        if sequence_schema != SOURCE or not sequence_name:
            continue
        table, column = row["table_name"], row["column_name"]
        await conn.execute(f'CREATE SEQUENCE IF NOT EXISTS "{SCHEMA}"."{sequence_name}"')
        await conn.execute(
            f'ALTER SEQUENCE "{SCHEMA}"."{sequence_name}" '
            f'OWNED BY "{SCHEMA}"."{table}"."{column}"'
        )
        await conn.execute(
            f"""ALTER TABLE "{SCHEMA}"."{table}" ALTER COLUMN "{column}"
            SET DEFAULT nextval('"{SCHEMA}"."{sequence_name}"'::regclass)"""
        )
        fixed += 1
    return fixed


async def grant_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(f'GRANT USAGE ON SCHEMA "{SCHEMA}" TO anon, authenticated, service_role')
    await conn.execute(
        f'GRANT ALL ON ALL TABLES IN SCHEMA "{SCHEMA}" '
        "TO postgres, service_role, anon, authenticated"
    )
    await conn.execute(
        f'GRANT ALL ON ALL SEQUENCES IN SCHEMA "{SCHEMA}" '
        "TO postgres, service_role, anon, authenticated"
    )
    await conn.execute(
        f'GRANT ALL ON ALL FUNCTIONS IN SCHEMA "{SCHEMA}" '
        "TO postgres, service_role, anon, authenticated"
    )
    await conn.execute(
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{SCHEMA}" '
        "GRANT ALL ON TABLES TO postgres, service_role, anon, authenticated"
    )
    await conn.execute(
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{SCHEMA}" '
        "GRANT ALL ON SEQUENCES TO postgres, service_role, anon, authenticated"
    )


def create_auth_user() -> str:
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise RuntimeError("Falta SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")
    response = requests.post(
        f"{url}/auth/v1/admin/users",
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": "application/json",
        },
        json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "email_confirm": True,
            "user_metadata": {"nombre": "Admin AB Mauri"},
        },
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Supabase Auth create user HTTP {response.status_code}: {response.text[:400]}"
        )
    user_id = response.json().get("id")
    if not user_id:
        raise RuntimeError("Supabase Auth no devolvió id")
    return str(user_id)


async def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        tenant_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM public.distribuidoras WHERE schema_name = $1)",
            SCHEMA,
        )
        schema_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = $1)",
            SCHEMA,
        )
        if tenant_exists or schema_exists:
            print(
                f"[FAIL] Estado no vacío: tenant_exists={tenant_exists}, "
                f"schema_exists={schema_exists}",
                file=sys.stderr,
            )
            return 1
    finally:
        await conn.close()

    await sync_schema(source=SOURCE, target=SCHEMA)

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        table_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = $1 AND table_type = 'BASE TABLE'
            """,
            SCHEMA,
        )
        product_count = await conn.fetchval(f'SELECT COUNT(*) FROM "{SCHEMA}".productos')
        client_count = await conn.fetchval(f'SELECT COUNT(*) FROM "{SCHEMA}".clients')
        if table_count < 50 or product_count or client_count:
            print(
                f"[FAIL] Clone inválido: tables={table_count}, productos={product_count}, "
                f"clients={client_count}",
                file=sys.stderr,
            )
            return 1

        fixed_sequences = await fix_sequence_defaults(conn)
        await grant_schema(conn)
        tenant_id = uuid4()
        metadata = {
            "ciudad_base": "Ciudad de Buenos Aires, Argentina",
            "hq": {
                "label": "Mariscal Antonio José de Sucre 632, CABA",
                "latitude": -34.5530,
                "longitude": -58.4364,
            },
            "marca_comercial": "AB Mauri",
            "marca_lider": "Calsa",
            "sitio_web": "https://www.calsa.com.ar",
            "origen_implementacion": "fase-00-preflight",
            "modo": "demo",
        }

        async with conn.transaction():
            tenant = await conn.fetchrow(
                """
                INSERT INTO public.distribuidoras (
                    id, nombre, razon_social, schema_name, activa,
                    metadata, calendar_country_code, default_lista_precios,
                    brand_name, tools_habilitadas, created_at, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, true,
                    $5::jsonb, 'AR', 1,
                    $6, $7::jsonb, now(), now()
                )
                RETURNING id, schema_name, nombre, activa, created_at
                """,
                str(tenant_id),
                "AB Mauri",
                "AB Mauri Hispanoamérica",
                SCHEMA,
                json.dumps(metadata, ensure_ascii=False),
                "AB Mauri",
                json.dumps(SELLER_TOOLS_OFF),
            )

            user_id = create_auth_user()
            await conn.execute(
                """
                INSERT INTO public.profiles (
                    id, distribuidora_id, nombre, role, is_whatsapp_subscribed
                )
                VALUES ($1, $2, $3, 'owner', false)
                """,
                user_id,
                str(tenant_id),
                "Admin AB Mauri",
            )
            project = await conn.fetchrow(
                """
                INSERT INTO public.implementation_projects (
                    distribuidora_id, started_at, current_milestone
                )
                VALUES ($1, $2, 'agentic_implementation')
                RETURNING id, started_at
                """,
                str(tenant_id),
                tenant["created_at"],
            )
            await conn.execute(
                """
                INSERT INTO public.implementation_project_milestone_log (
                    project_id, milestone_code, entered_at, entered_by
                )
                VALUES ($1, 'agentic_implementation', $2, NULL)
                ON CONFLICT (project_id, milestone_code) DO NOTHING
                """,
                str(project["id"]),
                project["started_at"],
            )

        has_mock = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = $1
                  AND table_name = 'productos'
                  AND column_name = 'is_mock'
            )
            """,
            SCHEMA,
        )
        print(
            f"[SUCCESS] tenant={tenant['schema_name']} id={tenant['id']} "
            f"tables={table_count} productos={product_count} clients={client_count} "
            f"is_mock={has_mock} fixed_sequences={fixed_sequences}"
        )
        print(f"[SUCCESS] owner={ADMIN_EMAIL}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
