#!/usr/bin/env python3
"""Alta de tenant benavidez: schema + clone gonzales + fila en public.distribuidoras.

Confirmado por el implementador: schema_name = benavidez, tenant nuevo / vacío.
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
from dotenv import load_dotenv

SCHEMA = "benavidez"  # confirmado: implementador + manifest
SOURCE = "gonzales"
ROOT = Path(__file__).resolve().parents[3]

load_dotenv(ROOT.parent / "backend-supabase" / ".env")
load_dotenv(ROOT / ".env")

sys.path.append(str(ROOT / "scripts"))
from sync_tenant_schema_objects import sync_schema  # noqa: E402


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


_NEXTVAL_RE = re.compile(
    r"""nextval\('(?:(?:"(?P<qschema>[^"]+)")|(?P<schema>[^.]+))\.(?:(?:"(?P<qseq>[^"]+)")|(?P<seq>[^"]+))'::regclass\)""",
    re.IGNORECASE,
)


async def fix_sequence_defaults(conn: asyncpg.Connection, new_schema: str, template_schema: str) -> int:
    rows = await conn.fetch(
        """
        SELECT table_name, column_name, column_default
        FROM information_schema.columns
        WHERE table_schema = $1
          AND column_default IS NOT NULL
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
        table = r["table_name"]
        column = r["column_name"]
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


async def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    print(f"[*] tenant destino: {SCHEMA} (nuevo / vacío)")
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
        print(f"[*] GRANT USAGE/ALL aplicado a schema {SCHEMA}")

        tenant_id = uuid4()
        metadata = {
            "ciudad_base": "Córdoba Capital, Córdoba, Argentina",
            "sitio_web": "https://especiasbenavidez.com/",
            "origen_implementacion": "fase-00-preflight",
        }
        row = await conn.fetchrow(
            """
            INSERT INTO public.distribuidoras (
                id, nombre, razon_social, cuit, schema_name, activa,
                metadata, calendar_country_code, default_lista_precios,
                tools_habilitadas, created_at, updated_at
            )
            VALUES (
                $1, $2, $3, $4, $5, true,
                $6::jsonb, 'AR', 1,
                '{}'::jsonb, now(), now()
            )
            RETURNING id, schema_name, nombre, activa, created_at
            """,
            str(tenant_id),
            "Especias Benavidez",
            "Máquinas y Condimentos SAS",
            "30-71762974-0",
            SCHEMA,
            json.dumps(metadata, ensure_ascii=False),
        )
        print(f"[*] INSERT public.distribuidoras schema_name={SCHEMA} id={row['id']}")

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
            """
            SELECT id, schema_name, nombre, activa
            FROM public.distribuidoras
            WHERE schema_name = $1
            """,
            SCHEMA,
        )
        print(f"[SUCCESS] tenant {verify['schema_name']} id={verify['id']} activa={verify['activa']}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
