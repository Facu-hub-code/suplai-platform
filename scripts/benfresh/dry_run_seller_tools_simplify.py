#!/usr/bin/env python3
"""
Dry-run: renombre editorial (español) + propuesta de bloqueo de tools vendedor Benfresh.

Uso:
  # Solo propuesta (sin DB)
  python3 scripts/benfresh/dry_run_seller_tools_simplify.py

  # Con lectura de BD (pooler 6543) — no escribe salvo --apply
  DATABASE_URL=... python3 scripts/benfresh/dry_run_seller_tools_simplify.py --from-db

  # Aplicar (requiere confirmación explícita)
  DATABASE_URL=... python3 scripts/benfresh/dry_run_seller_tools_simplify.py --from-db --apply --i-understand

Salidas:
  implementacion/benfresh/outputs/seller-tools-rename-dry-run.json
  implementacion/benfresh/outputs/seller-tools-block-dry-run.json
  implementacion/benfresh/outputs/seller-tools-simplify.sql  (solo si --from-db o --write-sql)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "implementacion" / "benfresh" / "outputs"
CATALOG_META = (
    ROOT.parent / "backend-supabase" / "services" / "agent_tools_catalog_meta.json"
)

SCHEMA = "benfresh"
LOOKBACK_DAYS = 45

# Nombres en español para canvas / admin (tool_name técnico no cambia).
SELLER_DISPLAY_NAMES_ES: dict[str, str] = {
    "ping": "Prueba de conexión",
    "search_products": "Buscar productos",
    "search_products_by_category": "Buscar por categoría",
    "get_product_by_code": "Producto por código",
    "create_distributor_ticket": "Crear ticket de soporte",
    "manage_contact_agenda": "Preferencias de contacto",
    "load_seller_order_text": "Cargar pedido por texto",
    "list_seller_clients": "Listar mis clientes",
    "get_seller_client_details": "Ver detalle del cliente",
    "set_seller_selected_client": "Elegir cliente",
    "get_seller_selected_client": "Cliente seleccionado",
    "get_open_order_status_for_client": "Pedido abierto del cliente",
    "edit_order_for_client": "Editar pedido del cliente",
    "confirm_order_for_client": "Confirmar pedido del cliente",
    "suggest_order_boost_for_client": "Sugerir productos al pedido",
    "clear_seller_context": "Limpiar contexto",
    "seller_help": "Ayuda del vendedor",
    "seller_catalog_query": "Consulta de catálogo",
    "seller_promo_pricing_query": "Consulta de precios y promos",
    "seller_my_metrics": "Mis métricas",
    "seller_client_query": "Consulta de cliente",
    "seller_orders_query": "Consulta de pedidos",
    "get_seller_daily_route": "Ruta del día",
    "get_seller_tasks": "Mis tareas",
    "get_seller_progress": "Mi progreso",
    "get_seller_client_summary": "Resumen de cliente (Field)",
    "check_order_sync_status": "Estado de sync del pedido",
    "get_field_app_link": "Link de Suplai Field",
}

# Short descriptions for hover (canvas).
SELLER_SHORT_ES: dict[str, str] = {
    "ping": "Responde un eco para verificar que el agente está vivo.",
    "search_products": "Busca productos del catálogo por texto (nombre, marca, etc.).",
    "search_products_by_category": "Lista productos filtrando por categoría.",
    "get_product_by_code": "Trae un producto exacto por SKU/código.",
    "create_distributor_ticket": "Abre un ticket humano en la distribuidora.",
    "manage_contact_agenda": "Guarda preferencias de horario/contacto del chat.",
    "load_seller_order_text": "Interpreta un pedido en texto libre y lo carga al cliente.",
    "list_seller_clients": "Lista la cartera de clientes del vendedor.",
    "get_seller_client_details": "Muestra ficha del cliente y lo deja seleccionado.",
    "set_seller_selected_client": "Fija el cliente sobre el que se opera el pedido.",
    "get_seller_selected_client": "Indica qué cliente está seleccionado ahora.",
    "get_open_order_status_for_client": "Resume el pedido abierto del cliente seleccionado.",
    "edit_order_for_client": "Agrega/edita líneas del pedido del cliente.",
    "confirm_order_for_client": "Confirma el pedido del cliente vía Field/sistema.",
    "suggest_order_boost_for_client": "Sugiere ítems para subir el monto del pedido.",
    "clear_seller_context": "Borra cliente seleccionado e historial de sesión.",
    "seller_help": "Manual corto de uso del agente vendedor.",
    "seller_catalog_query": "Consulta stock/precio/novedades sin armar pedido (opt-in).",
    "seller_promo_pricing_query": "Consulta promos y lista de precios del cliente (opt-in).",
    "seller_my_metrics": "Métricas del vendedor (opt-in).",
    "seller_client_query": "Consultas sobre un cliente de la cartera (opt-in).",
    "seller_orders_query": "Consultas sobre pedidos del vendedor (opt-in).",
    "get_seller_daily_route": "Ruta y visitas del día (Field).",
    "get_seller_tasks": "Tareas Field del vendedor.",
    "get_seller_progress": "Progreso/puntos Field.",
    "get_seller_client_summary": "Resumen Field de un cliente.",
    "check_order_sync_status": "Si el pedido ya sincronizó con el ERP/Field.",
    "get_field_app_link": "Envía el link de la app Field.",
}

# Opt-in: ya están apagadas salvo true explícito — no hace falta bloquear.
OPT_IN = frozenset(
    {
        "seller_catalog_query",
        "seller_promo_pricing_query",
        "seller_client_query",
        "seller_my_metrics",
        "seller_orders_query",
    }
)

# Propuesta de bloqueo adicional en Benfresh (legacy ON por defecto, 0 usos en 45d).
PROPOSE_BLOCK_IF_ZERO: frozenset[str] = frozenset(
    {
        "get_product_by_code",
        "get_seller_selected_client",
        "check_order_sync_status",
        # Field — ya suelen estar false; se reafirman
        "get_seller_daily_route",
        "get_seller_tasks",
        "get_seller_progress",
        "get_seller_client_summary",
        "get_field_app_link",
        # Ruido / no usados en Benfresh
        "ping",
        "clear_seller_context",
        "seller_help",
        "list_seller_clients",
        "suggest_order_boost_for_client",
        "create_distributor_ticket",
        "manage_contact_agenda",
        "search_products_by_category",
    }
)

# Núcleo operativo visto en uso (45d) — no tocar.
KEEP_ON = frozenset(
    {
        "load_seller_order_text",
        "set_seller_selected_client",
        "edit_order_for_client",
        "confirm_order_for_client",
        "get_open_order_status_for_client",
        "get_seller_client_details",
        "search_products",
    }
)


def _seller_tools_from_catalog() -> list[str]:
    if not CATALOG_META.exists():
        return sorted(SELLER_DISPLAY_NAMES_ES)
    meta = json.loads(CATALOG_META.read_text(encoding="utf-8"))
    names = [
        name
        for name, row in meta.items()
        if isinstance(row, dict) and "seller" in (row.get("agent_groups") or [])
    ]
    return sorted(names)


def _normalize_db_url(url: str) -> str:
    """Fuerza pooler 6543 si alguien pasa 5432."""
    parsed = urlparse(url)
    if parsed.port == 5432:
        netloc = parsed.netloc.replace(":5432", ":6543")
        return urlunparse(parsed._replace(netloc=netloc))
    return url


def build_rename_plan(current: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for tool in _seller_tools_from_catalog():
        proposed = SELLER_DISPLAY_NAMES_ES.get(tool)
        if not proposed:
            continue
        cur = (current or {}).get(tool) or {}
        old_name = cur.get("display_name")
        old_short = cur.get("short_description")
        new_short = SELLER_SHORT_ES.get(tool)
        plan.append(
            {
                "tool_name": tool,
                "display_name": {"from": old_name, "to": proposed, "changed": old_name != proposed},
                "short_description": {
                    "from": old_short,
                    "to": new_short,
                    "changed": (old_short or "") != (new_short or ""),
                },
                "in_editorial_table": tool in (current or {}),
            }
        )
    return plan


def build_block_plan(
    *,
    usage: dict[str, int],
    habilitadas: dict[str, bool],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tool in _seller_tools_from_catalog():
        calls = int(usage.get(tool, 0))
        currently_false = habilitadas.get(tool) is False
        opt_in = tool in OPT_IN
        keep = tool in KEEP_ON
        propose_block = (
            not keep
            and not opt_in
            and tool in PROPOSE_BLOCK_IF_ZERO
            and calls == 0
            and not currently_false
        )
        rows.append(
            {
                "tool_name": tool,
                "calls_45d": calls,
                "opt_in": opt_in,
                "keep_core": keep,
                "already_blocked": currently_false,
                "propose_set_false": propose_block,
                "reason": (
                    "núcleo en uso — no tocar"
                    if keep
                    else "opt-in (ya off salvo true)"
                    if opt_in
                    else "ya false en tools_habilitadas"
                    if currently_false
                    else "0 llamadas en 45d — proponer bloquear"
                    if propose_block
                    else "sin acción (fuera de lista de bloqueo o con uso)"
                ),
            }
        )
    return sorted(rows, key=lambda r: (-r["calls_45d"], r["tool_name"]))


def render_sql(rename_plan: list[dict[str, Any]], block_plan: list[dict[str, Any]]) -> str:
    lines = [
        f"-- Benfresh seller tools simplify — generado {datetime.now(timezone.utc).isoformat()}",
        "-- DRY RUN / revisar antes de aplicar. display_name es global (core.agent_tools).",
        "",
        "BEGIN;",
        "",
        "-- 1) Editorial global (nombres canvas)",
    ]
    for row in rename_plan:
        if not row["display_name"]["changed"] and not row["short_description"]["changed"]:
            continue
        name = row["tool_name"]
        dn = row["display_name"]["to"].replace("'", "''")
        sd = (row["short_description"]["to"] or "").replace("'", "''")
        if row["in_editorial_table"]:
            lines.append(
                f"UPDATE core.agent_tools SET display_name = '{dn}', "
                f"short_description = '{sd}', updated_at = NOW() "
                f"WHERE tool_name = '{name}';"
            )
        else:
            lines.append(
                f"INSERT INTO core.agent_tools (tool_name, display_name, category, short_description, status, sort_order)\n"
                f"VALUES ('{name}', '{dn}', 'vendedor', '{sd}', 'active', 100)\n"
                f"ON CONFLICT (tool_name) DO UPDATE SET\n"
                f"  display_name = EXCLUDED.display_name,\n"
                f"  short_description = EXCLUDED.short_description,\n"
                f"  updated_at = NOW();"
            )
    lines += ["", "-- 2) Bloqueos runtime solo Benfresh (tools_habilitadas)"]
    patches = [r["tool_name"] for r in block_plan if r["propose_set_false"]]
    if patches:
        # Merge JSON keys to false
        obj = {k: False for k in patches}
        payload = json.dumps(obj, ensure_ascii=False).replace("'", "''")
        lines.append(
            "UPDATE public.distribuidoras\n"
            f"SET tools_habilitadas = COALESCE(tools_habilitadas, '{{}}'::jsonb) || '{payload}'::jsonb\n"
            f"WHERE schema_name = '{SCHEMA}';"
        )
    else:
        lines.append("-- (nada nuevo para bloquear)")
    lines += ["", "COMMIT;", ""]
    return "\n".join(lines)


async def fetch_from_db(database_url: str) -> tuple[dict[str, dict[str, Any]], dict[str, bool], dict[str, int]]:
    import asyncpg

    url = _normalize_db_url(database_url)
    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        editorial_rows = await conn.fetch(
            """
            SELECT tool_name, display_name, short_description
            FROM core.agent_tools
            """
        )
        editorial = {
            str(r["tool_name"]): {
                "display_name": r["display_name"],
                "short_description": r["short_description"],
            }
            for r in editorial_rows
        }

        hab_row = await conn.fetchrow(
            "SELECT tools_habilitadas FROM public.distribuidoras WHERE schema_name = $1",
            SCHEMA,
        )
        hab_raw = hab_row["tools_habilitadas"] if hab_row else {}
        if isinstance(hab_raw, str):
            hab_raw = json.loads(hab_raw)
        habilitadas = {
            str(k): bool(v) for k, v in (hab_raw or {}).items() if isinstance(v, bool)
        }

        tenant_id = await conn.fetchval(
            "SELECT id FROM public.distribuidoras WHERE schema_name = $1", SCHEMA
        )
        usage: dict[str, int] = {}
        if tenant_id:
            rows = await conn.fetch(
                f"""
                WITH combined AS (
                  SELECT event_payload->>'tool_name' AS tool_name
                  FROM core.conversation_events
                  WHERE tenant_id = $1
                    AND created_at > NOW() - INTERVAL '{LOOKBACK_DAYS} days'
                    AND event_payload ? 'tool_name'
                  UNION ALL
                  SELECT tool_name
                  FROM core.agent_tool_executions
                  WHERE tenant_id = $1
                    AND created_at > NOW() - INTERVAL '{LOOKBACK_DAYS} days'
                )
                SELECT tool_name, COUNT(*)::int AS n
                FROM combined
                WHERE tool_name IS NOT NULL
                GROUP BY 1
                """,
                tenant_id,
            )
            usage = {str(r["tool_name"]): int(r["n"]) for r in rows}
        return editorial, habilitadas, usage
    finally:
        await conn.close()


async def apply_sql(database_url: str, sql: str) -> None:
    import asyncpg

    url = _normalize_db_url(database_url)
    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-db", action="store_true", help="Leer editorial/uso/flags desde Supabase")
    parser.add_argument("--write-sql", action="store_true", help="Escribir .sql aunque no haya DB")
    parser.add_argument("--apply", action="store_true", help="Ejecutar el SQL (peligroso)")
    parser.add_argument(
        "--i-understand",
        action="store_true",
        help="Confirmación obligatoria junto a --apply",
    )
    parser.add_argument(
        "--usage-json",
        type=Path,
        help="JSON opcional {tool_name: calls} si no hay --from-db",
    )
    parser.add_argument(
        "--habilitadas-json",
        type=Path,
        help="JSON opcional tools_habilitadas actual del tenant",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    editorial: dict[str, dict[str, Any]] | None = None
    habilitadas: dict[str, bool] = {}
    usage: dict[str, int] = {}

    if args.usage_json and args.usage_json.exists():
        usage = {str(k): int(v) for k, v in json.loads(args.usage_json.read_text()).items()}
    if args.habilitadas_json and args.habilitadas_json.exists():
        raw = json.loads(args.habilitadas_json.read_text())
        habilitadas = {str(k): bool(v) for k, v in raw.items() if isinstance(v, bool)}

    if args.from_db:
        db_url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
        if not db_url:
            print("Falta DATABASE_URL / SUPABASE_DB_URL", file=sys.stderr)
            return 2
        editorial, habilitadas, usage = asyncio.run(fetch_from_db(db_url))

    rename_plan = build_rename_plan(editorial)
    block_plan = build_block_plan(usage=usage, habilitadas=habilitadas)

    rename_path = OUT_DIR / "seller-tools-rename-dry-run.json"
    block_path = OUT_DIR / "seller-tools-block-dry-run.json"
    rename_path.write_text(json.dumps(rename_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    block_path.write_text(json.dumps(block_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    changed_names = sum(1 for r in rename_plan if r["display_name"]["changed"] or not r["in_editorial_table"])
    propose_blocks = [r for r in block_plan if r["propose_set_false"]]

    print(f"Schema: {SCHEMA}")
    print(f"Seller tools en catálogo: {len(rename_plan)}")
    print(f"Renombres / altas editoriales a revisar: {changed_names}")
    print(f"Bloqueos nuevos propuestos: {len(propose_blocks)}")
    print()
    print("=== Uso (si hay datos) — top ===")
    for r in block_plan[:12]:
        print(f"  {r['calls_45d']:4d}  {r['tool_name']:40s}  {r['reason']}")
    print()
    print("=== Propuesta BLOQUEAR (set false) ===")
    if not propose_blocks:
        print("  (ninguna — ya bloqueadas, opt-in, o sin datos de uso)")
    for r in propose_blocks:
        print(f"  - {r['tool_name']}")
    print()
    print("=== Renombres (muestra) ===")
    for r in rename_plan[:10]:
        fr = r["display_name"]["from"] or "∅"
        print(f"  {r['tool_name']}: {fr} → {r['display_name']['to']}")
    if len(rename_plan) > 10:
        print(f"  … +{len(rename_plan) - 10} más (ver JSON)")

    sql = render_sql(rename_plan, block_plan)
    if args.from_db or args.write_sql or args.apply:
        sql_path = OUT_DIR / "seller-tools-simplify.sql"
        sql_path.write_text(sql, encoding="utf-8")
        print(f"\nSQL escrito en {sql_path.relative_to(ROOT)}")

    print(f"\nJSON: {rename_path.relative_to(ROOT)}")
    print(f"JSON: {block_path.relative_to(ROOT)}")

    if args.apply:
        if not args.i_understand:
            print("\nAbortado: --apply requiere --i-understand", file=sys.stderr)
            return 3
        db_url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
        if not db_url:
            print("Falta DATABASE_URL", file=sys.stderr)
            return 2
        asyncio.run(apply_sql(db_url, sql))
        print("\nAPPLY OK")
    else:
        print("\nDRY RUN — no se escribió en BD. Para aplicar: --from-db --apply --i-understand")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
