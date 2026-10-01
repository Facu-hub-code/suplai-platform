#!/usr/bin/env python3
"""Almaro: dejar solo los 50 clientes del Excel piloto WhatsApp (sep-2026).

Pasos (cada uno escribe solo con --confirm almaro):
  plan       CSV de revisión: 50 clientes (lista GEV) + clientes a purgar. Sin escrituras.
  clientes   Crea/actualiza los 50 (teléfono Excel, lista GEV, PDV, ubicación).
  purga      Borra clientes fuera del Excel (salvo mock id 84, dueños de pedidos
             tienda/suplai y quien tenga conversación con el agente) con sus pedidos ERP. Exige create_stub_customers_on_project
             = false efectivo para almaro (PR backend #265 + override por tenant).
  pedidos    Trae pedidos GEV desde --desde solo de los 50 y los proyecta.

Uso:
  cd backend-supabase && source venv/bin/activate
  python ../suplai-platform/implementacion/almaro/scripts/depurar_clientes_piloto_50.py plan
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve()
ALMARO = HERE.parents[1]
PLATFORM = HERE.parents[3]
BACKEND = PLATFORM.parent / "backend-supabase"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

import core.db as core_db  # noqa: E402

core_db._POOL_MAX_SIZE = 2

SCHEMA = "almaro"
EXCEL = Path("/Users/facundolorenzo/Desktop/Listado Prueba WhatsApp - Septiembre 2026.xlsx")
GEV_CLIENTES = ALMARO / "inputs" / "gev-clientes-todos-20261001.json"
STAMP = "20261001"
OUT_CLIENTES = ALMARO / "outputs" / f"propuesta-clientes-piloto-50-{STAMP}.csv"
OUT_PURGA = ALMARO / "outputs" / f"propuesta-purga-clientes-{STAMP}.csv"
OUT_LOG = ALMARO / "outputs" / f"depuracion-clientes-piloto-50-{STAMP}-log.json"
ORIGEN = "excel_prueba_whatsapp_sep2026"
DEFAULT_LISTA = 20  # 06 TRADICIONAL
KEEP_CLIENT_IDS = {84}  # mock Facundo

TABLAS_POR_CLIENT_ID = [
    ("agenda", "client_id"),
    ("client_locations", "client_id"),
    ("client_product_memory", "client_id"),
    ("clientes_aliases", "client_id"),
    ("clientes_etiquetas", "client_id"),
    ("conversations", "client_id"),
    ("ia_tickets", "client_id"),
    ("routes_clients", "client_id"),
    ("vendedores_clientes", "cliente_id"),
    ("field_tasks", "cliente_id"),
    ("items_pedido", "client_id"),
]


def norm_phone(raw) -> tuple[str, str]:
    d = re.sub(r"\D", "", str(raw or ""))
    if d.startswith("54"):
        d = d[2:]
    if d.startswith("9") and len(d) == 11:
        d = d[1:]
    d = d.lstrip("0")
    if len(d) == 12:
        for pos in (2, 3, 4):
            if d[pos : pos + 2] == "15":
                d = d[:pos] + d[pos + 2 :]
                break
    return f"549{d}", "" if len(d) == 10 else f"largo_{len(d)}"


def read_excel() -> list[dict]:
    wb = openpyxl.load_workbook(EXCEL, read_only=True, data_only=True)
    rows = []
    for ws in wb.worksheets:
        for i, r in enumerate(ws.iter_rows(values_only=True)):
            r = list(r) + [None] * 8
            if i == 0 or not r[1]:
                continue
            codigo = str(r[1]).strip()
            phone, flag = norm_phone(r[6])
            rows.append(
                {
                    "hoja": ws.title,
                    "codigo": codigo,
                    "codigo_int": int(codigo),
                    "nombre": re.sub(r"\s*\(\d+\)\s*$", "", str(r[0] or "")).strip(),
                    "direccion": r[2],
                    "lat": r[3],
                    "lng": r[4],
                    "canal": r[5],
                    "celular_raw": r[6],
                    "phone": phone,
                    "phone_flag": flag,
                    "tokin_id": r[7],
                }
            )
    return rows


def gev_by_cuenta() -> dict[str, dict]:
    out = {}
    for c in json.load(GEV_CLIENTES.open(encoding="utf-8")):
        extra = c.get("datos_extra") or {}
        out[str(extra.get("id_cuenta"))] = extra
    return out


async def build_plan(conn) -> tuple[list[dict], list[dict], dict]:
    excel = read_excel()
    gev = gev_by_cuenta()
    codes = [r["codigo_int"] for r in excel]
    listas = {r["erp_list_id"]: r["id"] for r in await conn.fetch(
        f'SELECT id, erp_list_id FROM "{SCHEMA}".listas_precios WHERE erp_list_id IS NOT NULL'
    )}
    vendedores = {r["erp_codigo"]: r["id"] for r in await conn.fetch(
        f'SELECT id, erp_codigo FROM "{SCHEMA}".vendedores WHERE erp_codigo IS NOT NULL'
    )}
    existing = await conn.fetch(
        f"""
        SELECT id, codigo, partner_erp_id, phone_number, lista_precios_id, pdv_id,
               metadata->>'origen' AS origen
        FROM "{SCHEMA}".clients
        WHERE codigo = ANY($1::numeric[]) OR partner_erp_id = ANY($1::bigint[])
        """,
        codes,
    )
    by_code = {}
    for e in existing:
        for k in ("codigo", "partner_erp_id"):
            if e[k] is not None:
                by_code.setdefault(int(e[k]), dict(e))
    keep_ids = {e["id"] for e in by_code.values()}
    phones = await conn.fetch(
        f'SELECT id, phone_number FROM "{SCHEMA}".clients WHERE phone_number = ANY($1::text[])',
        [r["phone"] for r in excel],
    )
    phone_owner = {p["phone_number"]: p["id"] for p in phones}

    seen_phone: dict[str, str] = {}
    plan = []
    for r in excel:
        g = gev.get(r["codigo"]) or {}
        lista_erp = (g.get("lista_precios_erp_id") or "").strip()
        lista_id = listas.get(lista_erp) or DEFAULT_LISTA
        ex = by_code.get(r["codigo_int"])
        owner = phone_owner.get(r["phone"])
        if r["phone"] in seen_phone:
            accion = "omitir_telefono_duplicado_excel"
            nota = f"mismo celular que {seen_phone[r['phone']]}"
        elif owner is not None and (ex is None or owner != ex["id"]) and owner not in keep_ids:
            accion = "omitir_telefono_de_otro_cliente"
            nota = f"telefono ya usado por client_id={owner}"
        elif ex is None:
            accion, nota = "crear", ""
        elif ex["origen"] is None:
            accion, nota = "actualizar_stub_erp", ""
        else:
            accion, nota = "actualizar", ""
        seen_phone.setdefault(r["phone"], r["codigo"])
        plan.append(
            {
                **r,
                "gev_encontrado": "si" if g else "no",
                "lista_erp": lista_erp or "(default)",
                "lista_precios_id": lista_id,
                "vendedor_codigo": g.get("vendedor_codigo") or "",
                "vendedor_nombre": g.get("vendedor_nombre") or "",
                "vendedor_id": vendedores.get(g.get("vendedor_codigo") or "") or "",
                "client_id_actual": ex["id"] if ex else "",
                "phone_actual": ex["phone_number"] if ex else "",
                "lista_actual": ex["lista_precios_id"] if ex else "",
                "pdv_actual": ex["pdv_id"] if ex else "",
                "accion": accion,
                "nota": nota,
            }
        )

    purge = await conn.fetch(
        f"""
        WITH keep AS (
          SELECT unnest($1::int[]) AS id
          UNION SELECT unnest($2::int[])
          UNION SELECT DISTINCT cliente_id FROM "{SCHEMA}".pedidos
                WHERE cliente_id IS NOT NULL AND coalesce(origen, '') <> 'erp'
          UNION SELECT DISTINCT client_id FROM "{SCHEMA}".conversations
        )
        SELECT c.id, c.nombre, c.codigo, c.phone_number, c.is_mock, c.pdv_id,
               c.metadata->>'origen' AS origen,
               (SELECT count(*) FROM "{SCHEMA}".pedidos p WHERE p.cliente_id = c.id) AS pedidos
        FROM "{SCHEMA}".clients c
        WHERE c.id NOT IN (SELECT id FROM keep WHERE id IS NOT NULL)
        ORDER BY c.id
        """,
        sorted(keep_ids),
        sorted(KEEP_CLIENT_IDS),
    )
    purge_rows = [dict(p) for p in purge]
    purge_ids = [p["id"] for p in purge_rows]
    impacto = {"clients": len(purge_ids)}
    for table, col in TABLAS_POR_CLIENT_ID:
        impacto[table] = await conn.fetchval(
            f'SELECT count(*) FROM "{SCHEMA}".{table} WHERE {col}::text = ANY($1::text[])',
            [str(i) for i in purge_ids],
        )
    impacto["pedidos"] = await conn.fetchval(
        f'SELECT count(*) FROM "{SCHEMA}".pedidos WHERE cliente_id = ANY($1::int[])', purge_ids
    )
    impacto["pedidos_no_erp"] = await conn.fetchval(
        f"""SELECT count(*) FROM "{SCHEMA}".pedidos
            WHERE cliente_id = ANY($1::int[]) AND coalesce(origen, '') <> 'erp'""",
        purge_ids,
    )
    impacto["erp_orders_raw"] = await conn.fetchval(
        f"""SELECT count(*) FROM "{SCHEMA}".erp_orders_raw
            WHERE cliente_id = ANY($1::int[])
               OR partner_odoo_id IS NULL
               OR partner_odoo_id <> ALL($2::bigint[])""",
        purge_ids,
        codes,
    )
    return plan, purge_rows, impacto


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["vacio"])
        w.writeheader()
        w.writerows(rows)


def require_confirm(args) -> None:
    if args.confirm != SCHEMA:
        raise SystemExit(f"[STOP] Paso '{args.step}' escribe en schema {SCHEMA}: agregar --confirm {SCHEMA}")


async def step_clientes(conn, plan: list[dict]) -> dict:
    stats = Counter()
    async with conn.transaction():
        for r in plan:
            if r["accion"].startswith("omitir"):
                stats[r["accion"]] += 1
                continue
            meta = {
                "origen": ORIGEN,
                "tokin_id": r["tokin_id"],
                "hoja": r["hoja"],
                "canal": r["canal"],
                "id_cuenta": r["codigo"],
            }
            vend_id = int(r["vendedor_id"]) if r["vendedor_id"] not in ("", None) else None
            pdv_id = int(r["pdv_actual"]) if r["pdv_actual"] not in ("", None) else None
            if pdv_id is None:
                pdv_id = await conn.fetchval(
                    f"""
                    INSERT INTO "{SCHEMA}".puntos_venta (
                      razon_social, codigo, lista_precios_id, direccion,
                      vendedor, vendedor_id, activo_ai, is_mock
                    ) VALUES ($1, $2, $3, $4, $5, $6, true, false)
                    RETURNING id
                    """,
                    r["nombre"], r["codigo_int"], r["lista_precios_id"], r["direccion"],
                    r["vendedor_nombre"] or None, vend_id,
                )
            else:
                await conn.execute(
                    f'UPDATE "{SCHEMA}".puntos_venta SET lista_precios_id = $2 WHERE id = $1',
                    pdv_id, r["lista_precios_id"],
                )
            if r["client_id_actual"] == "":
                client_id = await conn.fetchval(
                    f"""
                    INSERT INTO "{SCHEMA}".clients (
                      phone_number, nombre, razon_social, lista_precios_id, codigo,
                      activo_ai, vendedor, is_primary, is_mock, partner_erp_id, pdv_id, metadata
                    ) VALUES ($1, $2, $2, $3, $4::bigint, true, $5, true, false, $4::bigint, $6, $7::jsonb)
                    RETURNING id
                    """,
                    r["phone"], r["nombre"], r["lista_precios_id"], r["codigo_int"],
                    r["vendedor_nombre"] or None, pdv_id, json.dumps(meta, ensure_ascii=False),
                )
            else:
                client_id = int(r["client_id_actual"])
                await conn.execute(
                    f"""
                    UPDATE "{SCHEMA}".clients
                    SET phone_number = $2, lista_precios_id = $3, activo_ai = true,
                        pdv_id = $4, is_primary = true, partner_erp_id = coalesce(partner_erp_id, $5),
                        vendedor = coalesce($6, vendedor),
                        metadata = coalesce(metadata, '{{}}'::jsonb) || $7::jsonb,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    client_id, r["phone"], r["lista_precios_id"], pdv_id, r["codigo_int"],
                    r["vendedor_nombre"] or None, json.dumps(meta, ensure_ascii=False),
                )
            if r["lat"] not in (None, "") and r["lng"] not in (None, ""):
                has_loc = await conn.fetchval(
                    f'SELECT 1 FROM "{SCHEMA}".client_locations WHERE client_id = $1 LIMIT 1', client_id
                )
                if not has_loc:
                    await conn.execute(
                        f"""
                        INSERT INTO "{SCHEMA}".client_locations (
                          client_id, source, latitude, longitude, location,
                          address_text, name, is_primary, geocode_status, created_by
                        ) VALUES (
                          $1, 'migration', $2, $3,
                          ST_SetSRID(ST_MakePoint($3::float8, $2::float8), 4326),
                          $4, $5, true, 'resolved', 'implementacion-almaro'
                        )
                        """,
                        client_id, float(r["lat"]), float(r["lng"]), r["direccion"], r["nombre"],
                    )
            stats[r["accion"]] += 1
    return dict(stats)


async def stub_creation_enabled(conn) -> bool:
    val = await conn.fetchval(
        """
        SELECT (COALESCE(p.capabilities, '{}'::jsonb)
                || COALESCE(tp.capabilities_override, '{}'::jsonb))->>'create_stub_customers_on_project'
        FROM public.distribuidoras d
        JOIN core.erp_connector_configs cfg ON cfg.tenant_id = d.id
        JOIN core.erp_connector_profiles p ON p.connector = cfg.connector
        LEFT JOIN core.erp_tenant_profiles tp ON tp.tenant_id = d.id
        WHERE d.schema_name = $1
        """,
        SCHEMA,
    )
    return str(val).lower() == "true"


async def step_purga(conn, purge_rows: list[dict], codes: list[int]) -> dict:
    if await stub_creation_enabled(conn):
        raise SystemExit(
            "[STOP] create_stub_customers_on_project sigue en true para almaro: "
            "desplegar PR backend #265 y cargar el override antes de purgar."
        )
    ids = [p["id"] for p in purge_rows]
    deleted = {}
    async with conn.transaction():
        pedido_ids = [r["id"] for r in await conn.fetch(
            f"""SELECT id FROM "{SCHEMA}".pedidos
                WHERE cliente_id = ANY($1::int[]) AND coalesce(origen, '') = 'erp'""",
            ids,
        )]
        for table, col in [("items_pedido", "pedido_id"), ("field_task_events", "pedido_id")]:
            st = await conn.execute(
                f'DELETE FROM "{SCHEMA}".{table} WHERE {col} = ANY($1::int[])', pedido_ids
            )
            deleted[f"{table}_por_pedido"] = int(st.split()[-1])
        st = await conn.execute(
            f"""DELETE FROM "{SCHEMA}".erp_orders_raw
                WHERE cliente_id = ANY($1::int[]) OR suplai_pedido_id = ANY($2::int[])
                   OR partner_odoo_id IS NULL OR partner_odoo_id <> ALL($3::bigint[])""",
            ids, pedido_ids, codes,
        )
        deleted["erp_orders_raw"] = int(st.split()[-1])
        st = await conn.execute(
            f'DELETE FROM "{SCHEMA}".pedidos WHERE id = ANY($1::int[])', pedido_ids
        )
        deleted["pedidos"] = int(st.split()[-1])
        for table, col in TABLAS_POR_CLIENT_ID:
            st = await conn.execute(
                f'DELETE FROM "{SCHEMA}".{table} WHERE {col}::text = ANY($1::text[])',
                [str(i) for i in ids],
            )
            deleted[table] = int(st.split()[-1])
        pdv_ids = [p["pdv_id"] for p in purge_rows if p["pdv_id"] is not None]
        st = await conn.execute(f'DELETE FROM "{SCHEMA}".clients WHERE id = ANY($1::int[])', ids)
        deleted["clients"] = int(st.split()[-1])
        st = await conn.execute(
            f"""DELETE FROM "{SCHEMA}".puntos_venta pv
                WHERE pv.id = ANY($1::int[])
                  AND NOT EXISTS (SELECT 1 FROM "{SCHEMA}".clients c WHERE c.pdv_id = pv.id)
                  AND NOT EXISTS (SELECT 1 FROM "{SCHEMA}".field_tasks t WHERE t.pdv_id = pv.id)""",
            pdv_ids,
        )
        deleted["puntos_venta"] = int(st.split()[-1])
    return deleted


async def step_pedidos(conn, codes: list[int], desde: date) -> dict:
    from erp.services.erp_order_projection_service import project_orders_raw
    from erp.services.erp_sync_service import (
        _resolve_cliente_ids_by_partners,
        _upsert_erp_orders_raw_batch,
        get_connector_for_schema,
    )

    pendientes_ajenos = await conn.fetchval(
        f"""SELECT count(*) FROM "{SCHEMA}".erp_orders_raw
            WHERE suplai_pedido_id IS NULL
              AND (partner_odoo_id IS NULL OR partner_odoo_id <> ALL($1::bigint[]))""",
        codes,
    )
    if pendientes_ajenos and await stub_creation_enabled(conn):
        raise SystemExit(
            f"[STOP] {pendientes_ajenos} pedidos raw pendientes de clientes fuera del Excel: "
            "proyectar ahora crearía clientes stub. Correr 'purga' primero."
        )
    connector = await get_connector_for_schema(SCHEMA)
    orders: list[dict] = []
    failed_days: list[str] = []
    day = desde
    while day <= date.today():
        for attempt in range(3):
            try:
                batch = await connector._fetch_orders_window(day, day)
                orders.extend(batch)
                print(f"[pedidos] {day} {len(batch)}", flush=True)
                break
            except Exception as exc:
                print(f"[pedidos] {day} intento {attempt + 1} {type(exc).__name__}", flush=True)
                await asyncio.sleep(5)
        else:
            failed_days.append(day.isoformat())
        day = date.fromordinal(day.toordinal() + 1)
    code_set = set(codes)
    mine = [
        o for o in orders
        if (pid := o.get("erp_partner_id") or o.get("partner_odoo_id")) is not None
        and int(pid) in code_set
    ]
    snap = ALMARO / "inputs" / f"gev-pedidos-piloto-50-{desde:%Y%m%d}-{STAMP}.json"
    snap.write_text(json.dumps(mine, ensure_ascii=False, default=str), encoding="utf-8")
    partner_ids = [int(o.get("erp_partner_id") or o.get("partner_odoo_id")) for o in mine]
    cliente_by_partner = await _resolve_cliente_ids_by_partners(conn, SCHEMA, partner_ids)
    for i in range(0, len(mine), 200):
        await _upsert_erp_orders_raw_batch(conn, SCHEMA, mine[i : i + 200], cliente_by_partner)
    projection = await project_orders_raw(SCHEMA, dry_run=False, limit=2000)
    return {
        "dias_fallidos": failed_days,
        "gev_orders_total": len(orders),
        "gev_orders_piloto": len(mine),
        "clientes_con_pedidos": len(set(partner_ids)),
        "projection": {k: projection.get(k) for k in ("outcome", "projected", "failed", "skipped", "message")},
        "snapshot": str(snap.relative_to(PLATFORM)),
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["plan", "clientes", "purga", "pedidos"])
    ap.add_argument("--confirm", default="")
    ap.add_argument("--desde", default="2026-08-18")
    args = ap.parse_args()

    log: dict = {"step": args.step, "at": datetime.now().isoformat(timespec="seconds"), "schema": SCHEMA}
    conn = await core_db.get_connection()
    try:
        plan, purge_rows, impacto = await build_plan(conn)
        codes = [r["codigo_int"] for r in plan]
        if args.step == "plan":
            write_csv(OUT_CLIENTES, plan)
            write_csv(OUT_PURGA, purge_rows)
            log["acciones"] = dict(Counter(r["accion"] for r in plan))
            log["listas"] = dict(Counter(f'{r["lista_erp"]}->{r["lista_precios_id"]}' for r in plan))
            log["phone_flags"] = dict(Counter(r["phone_flag"] or "ok" for r in plan))
            log["impacto_purga"] = impacto
            log["stub_creation_enabled"] = await stub_creation_enabled(conn)
            log["csv"] = [str(OUT_CLIENTES.relative_to(PLATFORM)), str(OUT_PURGA.relative_to(PLATFORM))]
        else:
            require_confirm(args)
            if args.step == "clientes":
                log["resultado"] = await step_clientes(conn, plan)
            elif args.step == "purga":
                log["resultado"] = await step_purga(conn, purge_rows, codes)
            else:
                log["resultado"] = await step_pedidos(conn, codes, date.fromisoformat(args.desde))
            log["clients_total"] = await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}".clients')
            history = json.loads(OUT_LOG.read_text()) if OUT_LOG.exists() else []
            history.append(log)
            OUT_LOG.write_text(json.dumps(history, ensure_ascii=False, indent=2, default=str))
        print(json.dumps(log, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        await conn.close()
        await core_db.close_db_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
