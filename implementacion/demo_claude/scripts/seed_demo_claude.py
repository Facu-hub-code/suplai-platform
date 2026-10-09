#!/usr/bin/env python3
"""Crea o regenera demo_claude: estructura de del_corro + recorte anonimizado.

schema_name confirmado: demo_claude
Origen: del_corro (solo estructura comercial). Los clientes se anonimizan.
No copia conversaciones, tickets ni envíos.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "demo_claude"
SOURCE = "del_corro"
ADMIN_EMAIL = "reviewer@demo-claude.suplaisales.com"
ADMIN_PASSWORD = "Suplai2026"
CLIENT_LIMIT = 50
HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
BACKEND = ROOT.parent / "backend-supabase"
OUT = HERE.parents[1] / "outputs"


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def _load_envs() -> None:
    for path in (BACKEND / ".env", ROOT / ".env"):
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
    return fixed


async def grant_schema(conn: asyncpg.Connection, schema: str) -> None:
    await conn.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO anon, authenticated, service_role')
    await conn.execute(
        f'GRANT ALL ON ALL TABLES IN SCHEMA "{schema}" TO postgres, service_role, anon, authenticated'
    )
    await conn.execute(
        f'GRANT ALL ON ALL SEQUENCES IN SCHEMA "{schema}" TO postgres, service_role, anon, authenticated'
    )
    await conn.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO mcp_connector')
    await conn.execute(
        f'GRANT SELECT ON "{schema}".pedidos, "{schema}".items_pedido, "{schema}".clients TO mcp_connector'
    )


def create_or_get_auth_user() -> str:
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise RuntimeError("Falta SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")
    listed = requests.get(
        f"{url}/auth/v1/admin/users",
        headers={"Authorization": f"Bearer {key}", "apikey": key},
        params={"page": 1, "per_page": 200},
        timeout=30,
    )
    if listed.status_code == 200:
        for user in listed.json().get("users") or []:
            if (user.get("email") or "").lower() == ADMIN_EMAIL:
                print(f"[*] auth.users ya existe {ADMIN_EMAIL} id={user.get('id')}")
                return str(user["id"])
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
            "user_metadata": {"nombre": "Revisor Claude"},
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


async def copy_anonymized(conn: asyncpg.Connection) -> dict[str, int]:
    print(f"[*] schema_name confirmado para escritura: {SCHEMA}")
    await conn.execute(f'TRUNCATE TABLE "{SCHEMA}".items_pedido, "{SCHEMA}".pedidos, "{SCHEMA}".clients RESTART IDENTITY CASCADE')
    for extra in ("productos", "listas_precios"):
        exists = await conn.fetchval(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = $1 AND table_name = $2
            """,
            SCHEMA,
            extra,
        )
        if exists:
            await conn.execute(f'TRUNCATE TABLE "{SCHEMA}"."{extra}" RESTART IDENTITY CASCADE')

    await conn.execute(
        f"""
        INSERT INTO "{SCHEMA}".listas_precios
        SELECT * FROM "{SOURCE}".listas_precios
        """
    )
    await conn.execute(
        f"""
        INSERT INTO "{SCHEMA}".productos
        SELECT * FROM "{SOURCE}".productos
        """
    )
    await conn.execute(
        f"""
        INSERT INTO "{SCHEMA}".clients (
            id, phone_number, nombre, razon_social, lista_precios_id, codigo,
            activo_ai, dia_de_visita, dia_de_entrega, activo_en_sistema_desde,
            datos_personales, cuit, vendedor, email, etiqueta, lifecycle,
            is_mock, metadata, created_at, updated_at
        )
        SELECT
            c.id,
            '5491100' || lpad((row_number() OVER (ORDER BY c.id))::text, 7, '0'),
            'Almacén Demo ' || (row_number() OVER (ORDER BY c.id)),
            'Razón Demo ' || (row_number() OVER (ORDER BY c.id)),
            c.lista_precios_id,
            c.codigo,
            true,
            c.dia_de_visita,
            c.dia_de_entrega,
            c.activo_en_sistema_desde,
            '{{}}'::jsonb,
            NULL,
            'Vendedor Demo',
            'cliente' || (row_number() OVER (ORDER BY c.id)) || '@demo-claude.example',
            c.etiqueta,
            COALESCE(c.lifecycle, 'client'),
            true,
            jsonb_build_object('origen', 'demo_claude', 'anonimizado', true),
            now(),
            now()
        FROM "{SOURCE}".clients c
        WHERE c.id IN (
            SELECT cliente_id FROM "{SOURCE}".pedidos
            WHERE deleted_at IS NULL AND cliente_id IS NOT NULL
            GROUP BY cliente_id
            ORDER BY count(*) DESC
            LIMIT {CLIENT_LIMIT}
        )
        """
    )
    await conn.execute(
        f"""
        INSERT INTO "{SCHEMA}".pedidos (
            id, cliente_id, fecha, items, total, estado, notas,
            erp_reference_id, is_mock, origen, updated_at, deleted_at, order_reference
        )
        SELECT
            p.id, p.cliente_id, p.fecha, '[]'::jsonb, p.total, p.estado, NULL,
            NULL, true, COALESCE(p.origen, 'erp'), p.updated_at, NULL, p.order_reference
        FROM "{SOURCE}".pedidos p
        WHERE p.deleted_at IS NULL
          AND p.cliente_id IN (SELECT id FROM "{SCHEMA}".clients)
        """
    )
    await conn.execute(
        f"""
        INSERT INTO "{SCHEMA}".items_pedido (
            id, client_id, product_code, precio_unitario, lista_precios,
            fecha_pedido, nombre, cantidad_solicitada, pedido_id, is_mock
        )
        SELECT
            i.id, i.client_id, i.product_code, i.precio_unitario, i.lista_precios,
            i.fecha_pedido, i.nombre, i.cantidad_solicitada, i.pedido_id, true
        FROM "{SOURCE}".items_pedido i
        WHERE i.pedido_id IN (SELECT id FROM "{SCHEMA}".pedidos)
        """
    )
    max_fecha = await conn.fetchval(f'SELECT max(fecha)::date FROM "{SCHEMA}".pedidos')
    if max_fecha:
        delta = date.today() - max_fecha
        days = delta.days
        if days:
            await conn.execute(
                f'UPDATE "{SCHEMA}".pedidos SET fecha = fecha + ($1 * interval \'1 day\')',
                days,
            )
            await conn.execute(
                f'UPDATE "{SCHEMA}".items_pedido SET fecha_pedido = fecha_pedido + $1::int',
                days,
            )
            print(f"[*] Fechas desplazadas {days} días para que 'este mes' tenga datos")
    counts = {
        "clients": await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}".clients'),
        "pedidos": await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}".pedidos'),
        "items": await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}".items_pedido'),
        "productos": await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}".productos'),
        "estados": await conn.fetchval(f'SELECT count(DISTINCT estado) FROM "{SCHEMA}".pedidos'),
    }
    return {k: int(v or 0) for k, v in counts.items()}


async def ensure_lifecycle(conn: asyncpg.Connection) -> None:
    sys.path.append(str(BACKEND))
    from core.tenancy import install_clients_lifecycle_objects

    await install_clients_lifecycle_objects(conn, SCHEMA)


async def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    print(f"[*] origen estructural: {SOURCE} (recorte anonimizado, no copia PII)")
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)

    await sync_schema(source=SOURCE, target=SCHEMA)

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        fixed = await fix_sequence_defaults(conn, SCHEMA, SOURCE)
        print(f"[*] Secuencias reescritas: {fixed}")
        await grant_schema(conn, SCHEMA)
        counts = await copy_anonymized(conn)
        print(f"[*] Copiados: {counts}")
        if counts["clients"] < 40 or counts["pedidos"] < 1:
            print("[FAIL] Recorte insuficiente.", file=sys.stderr)
            return 1
        try:
            await ensure_lifecycle(conn)
            print("[*] Vistas de lifecycle instaladas")
        except Exception as exc:
            print(f"[WARN] lifecycle: {exc}")

        existing = await conn.fetchrow(
            "SELECT id FROM public.distribuidoras WHERE schema_name = $1", SCHEMA
        )
        tenant_id = str(existing["id"]) if existing else str(uuid4())
        metadata = {
            "ciudad_base": "Córdoba capital, Córdoba, Argentina",
            "marca_comercial": "Demo Claude",
            "origen_implementacion": "directorio-claude",
            "modo": "demo",
        }
        if existing:
            await conn.execute(
                """
                UPDATE public.distribuidoras
                SET nombre = $2, razon_social = $3, activa = true,
                    metadata = $4::jsonb, brand_name = $5, updated_at = now()
                WHERE schema_name = $1
                """,
                SCHEMA,
                "Demo Claude",
                "Demo Claude (revisores)",
                json.dumps(metadata, ensure_ascii=False),
                "Demo Claude",
            )
        else:
            await conn.execute(
                """
                INSERT INTO public.distribuidoras (
                    id, nombre, razon_social, schema_name, activa,
                    metadata, calendar_country_code, brand_name, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, true, $5::jsonb, 'AR', $6, now(), now()
                )
                """,
                tenant_id,
                "Demo Claude",
                "Demo Claude (revisores)",
                SCHEMA,
                json.dumps(metadata, ensure_ascii=False),
                "Demo Claude",
            )
        print(f"[*] public.distribuidoras schema_name={SCHEMA} id={tenant_id}")

        user_id = create_or_get_auth_user()
        await conn.execute(
            """
            INSERT INTO public.profiles (id, distribuidora_id, nombre, role, is_whatsapp_subscribed)
            VALUES ($1, $2, $3, 'gerente', false)
            ON CONFLICT (id) DO UPDATE
            SET distribuidora_id = EXCLUDED.distribuidora_id,
                nombre = EXCLUDED.nombre,
                role = EXCLUDED.role
            """,
            user_id,
            tenant_id,
            "Revisor Claude",
        )
        print(f"[*] profile gerente {ADMIN_EMAIL} -> {SCHEMA}")

        periodo = await conn.fetchrow(
            f"""
            SELECT min(fecha)::date AS desde, max(fecha)::date AS hasta,
                   count(*) AS pedidos
            FROM "{SCHEMA}".pedidos
            """
        )
        OUT.mkdir(parents=True, exist_ok=True)
        creds = OUT / "reviewer-credentials.local.md"
        creds.write_text(
            f"""# Credenciales revisor Claude — NO COMMITEAR

Email: {ADMIN_EMAIL}
Contraseña: {ADMIN_PASSWORD}
Rol: gerente
Distribuidora: Demo Claude (`{SCHEMA}`)
Tenant id: {tenant_id}
Usuario id: {user_id}
Pedidos: {counts['pedidos']} entre {periodo['desde']} y {periodo['hasta']}
Clientes anonimizados: {counts['clients']}
Generado: {datetime.now(timezone.utc).isoformat()}
""",
            encoding="utf-8",
        )
        print(f"[SUCCESS] credenciales en {creds}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
