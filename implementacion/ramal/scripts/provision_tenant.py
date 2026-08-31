#!/usr/bin/env python3
"""Alta de tenant ramal: clone gonzales + fila en public.distribuidoras + owner.

schema_name = ramal (confirmado por el implementador). Tenant nuevo / vacío (demo).
Sin abrir rama nueva: feat/quimica-vm-catalogo.
"""
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

SCHEMA = "ramal"  # confirmado: implementador
SOURCE = "gonzales"
ADMIN_EMAIL = "admin@ramal.com"
ADMIN_PASSWORD = "Suplai2026"
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
            print(f"[*] env: {path}")
    url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or ""
    url = force_pooler(url)
    if url:
        os.environ["SUPABASE_DB_URL"] = url
        os.environ["SUPABASE_DB_URL_POOLER"] = url


_load_envs()
sys.path.append(str(ROOT / "scripts"))
from sync_tenant_schema_objects import sync_schema  # noqa: E402

_NEXTVAL_RE = re.compile(
    r"""nextval\('(?:(?:"(?P<qschema>[^"]+)")|(?P<schema>[^.]+))\.(?:(?:"(?P<qseq>[^"]+)")|(?P<seq>[^"]+))'::regclass\)""",
    re.I,
)

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


async def fix_sequence_defaults(conn: asyncpg.Connection, new_schema: str, template_schema: str) -> int:
    rows = await conn.fetch(
        """
        SELECT table_name, column_name, column_default
        FROM information_schema.columns
        WHERE table_schema = $1 AND column_default IS NOT NULL
        """,
        new_schema,
    )
    fixed = 0
    for r in rows:
        default = str(r["column_default"] or "")
        m = _NEXTVAL_RE.search(default)
        if not m:
            continue
        seq_schema = (m.group("qschema") or m.group("schema") or "").strip().strip('"').lower()
        seq_name = (m.group("qseq") or m.group("seq") or "").strip().strip('"')
        if seq_schema != template_schema or not seq_name:
            continue
        table, column = r["table_name"], r["column_name"]
        await conn.execute(f'CREATE SEQUENCE IF NOT EXISTS "{new_schema}"."{seq_name}"')
        await conn.execute(
            f'ALTER SEQUENCE "{new_schema}"."{seq_name}" OWNED BY "{new_schema}"."{table}"."{column}"'
        )
        await conn.execute(
            f"""ALTER TABLE "{new_schema}"."{table}" ALTER COLUMN "{column}"
                SET DEFAULT nextval('"{new_schema}"."{seq_name}"'::regclass)"""
        )
        fixed += 1
        print(f"  [+] secuencia {new_schema}.{seq_name} ({table}.{column})")
    return fixed


async def grant_schema(conn: asyncpg.Connection, schema: str) -> None:
    await conn.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO anon, authenticated, service_role')
    await conn.execute(
        f'GRANT ALL ON ALL TABLES IN SCHEMA "{schema}" TO postgres, service_role, anon, authenticated'
    )
    await conn.execute(
        f'GRANT ALL ON ALL SEQUENCES IN SCHEMA "{schema}" TO postgres, service_role, anon, authenticated'
    )
    await conn.execute(
        f'GRANT ALL ON ALL FUNCTIONS IN SCHEMA "{schema}" TO postgres, service_role, anon, authenticated'
    )
    await conn.execute(
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" GRANT ALL ON TABLES TO postgres, service_role, anon, authenticated'
    )
    await conn.execute(
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" GRANT ALL ON SEQUENCES TO postgres, service_role, anon, authenticated'
    )


def create_auth_user() -> str:
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise RuntimeError("Falta SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")
    resp = requests.post(
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
            "user_metadata": {"nombre": "Admin Ramal"},
        },
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"auth admin create user HTTP {resp.status_code}: {resp.text[:400]}")
    user_id = resp.json().get("id")
    if not user_id:
        raise RuntimeError("auth no devolvió id")
    print(f"[*] auth.users creado {ADMIN_EMAIL} id={user_id}")
    return str(user_id)


async def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    print(f"[*] tenant destino: {SCHEMA} (nuevo / vacío, demo)")
    print(f"[*] template: {SOURCE}")

    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        existing = await conn.fetchrow(
            "SELECT id, schema_name, nombre FROM public.distribuidoras WHERE schema_name = $1",
            SCHEMA,
        )
        if existing:
            print(f"[FAIL] Ya existe public.distribuidoras schema_name={SCHEMA} id={existing['id']}", file=sys.stderr)
            return 1
        schema_exists = await conn.fetchval(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = $1", SCHEMA
        )
        if schema_exists:
            n_prod = await conn.fetchval(f'SELECT COUNT(*) FROM "{SCHEMA}".productos')
            n_cli = await conn.fetchval(f'SELECT COUNT(*) FROM "{SCHEMA}".clients')
            if n_prod or n_cli:
                print(f"[FAIL] Schema {SCHEMA} ya tiene datos (productos={n_prod}, clients={n_cli})", file=sys.stderr)
                return 1
    finally:
        await conn.close()

    await sync_schema(source=SOURCE, target=SCHEMA)

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        n_tables = await conn.fetchval(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = $1 AND table_type = 'BASE TABLE'
            """,
            SCHEMA,
        )
        print(f"[*] Tablas en {SCHEMA}: {n_tables}")
        if n_tables < 50:
            print(f"[FAIL] Clone incompleto ({n_tables} tablas). Aborto.", file=sys.stderr)
            return 1

        n_prod = await conn.fetchval(f'SELECT COUNT(*) FROM "{SCHEMA}".productos')
        n_cli = await conn.fetchval(f'SELECT COUNT(*) FROM "{SCHEMA}".clients')
        print(f"[*] Conteos vacíos: productos={n_prod} clients={n_cli}")
        if n_prod or n_cli:
            print("[FAIL] El schema clonado no está vacío.", file=sys.stderr)
            return 1

        has_mock = await conn.fetchval(
            """
            SELECT EXISTS(
              SELECT 1 FROM information_schema.columns
              WHERE table_schema = $1 AND table_name = 'productos' AND column_name = 'is_mock'
            )
            """,
            SCHEMA,
        )
        print(f"[*] is_mock en {SCHEMA}.productos: {bool(has_mock)}")
        fixed = await fix_sequence_defaults(conn, SCHEMA, SOURCE)
        print(f"[*] Secuencias reescritas: {fixed}")
        await grant_schema(conn, SCHEMA)

        tenant_id = uuid4()
        metadata = {
            "ciudad_base": "San Pedro, Jujuy, Argentina",
            "origen_implementacion": "fase-00-preflight",
            "modo": "demo",
        }
        row = await conn.fetchrow(
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
            "Distribuidora El Ramal",
            "Distribuidora El Ramal",
            SCHEMA,
            json.dumps(metadata, ensure_ascii=False),
            "Ramal",
            json.dumps(SELLER_TOOLS_OFF),
        )
        print(f"[*] INSERT public.distribuidoras schema_name={SCHEMA} id={row['id']}")

        user_id = create_auth_user()
        await conn.execute(
            """
            INSERT INTO public.profiles (id, distribuidora_id, nombre, role, is_whatsapp_subscribed)
            VALUES ($1, $2, $3, 'owner', false)
            ON CONFLICT (id) DO UPDATE
            SET distribuidora_id = EXCLUDED.distribuidora_id,
                nombre = EXCLUDED.nombre,
                role = EXCLUDED.role
            """,
            user_id,
            str(tenant_id),
            "Admin Ramal",
        )
        print(f"[*] profile owner {ADMIN_EMAIL} -> {SCHEMA}")

        project = await conn.fetchrow(
            """
            INSERT INTO public.implementation_projects (distribuidora_id, started_at, current_milestone)
            VALUES ($1, $2, 'agentic_implementation')
            ON CONFLICT (distribuidora_id) DO NOTHING
            RETURNING id, started_at
            """,
            str(tenant_id),
            row["created_at"],
        )
        if project:
            await conn.execute(
                """
                INSERT INTO public.implementation_project_milestone_log
                    (project_id, milestone_code, entered_at, entered_by)
                VALUES ($1, 'agentic_implementation', $2, NULL)
                ON CONFLICT (project_id, milestone_code) DO NOTHING
                """,
                str(project["id"]),
                project["started_at"],
            )
            print(f"[*] Proyecto de implementación id={project['id']}")

        verify = await conn.fetchrow(
            "SELECT id, schema_name, nombre, activa FROM public.distribuidoras WHERE schema_name = $1",
            SCHEMA,
        )
        print(f"[SUCCESS] tenant {verify['schema_name']} id={verify['id']} activa={verify['activa']}")
        print(f"[SUCCESS] login backoffice {ADMIN_EMAIL}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
