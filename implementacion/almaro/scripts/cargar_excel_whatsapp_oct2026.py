#!/usr/bin/env python3
"""Almaro: cargar Excel WhatsApp (Desktop/almaro.xlsx), sync pedidos, grupos ≤150, enviar prueba2.

Pasos (escritura solo con --confirm almaro):
  plan      CSV de revisión. Sin escrituras.
  clientes  Crea/actualiza los del Excel (teléfono, lista GEV, PDV, ubicación).
  pedidos   Pull GEV 180 días + proyecta historial de esos códigos.
  grupos    Grupos explícitos de a 150 por día de visita.
  enviar    Agenda puntual + envío Meta de prueba2 a esos grupos.

Uso:
  cd backend-supabase && source venv/bin/activate
  python ../suplai-platform/implementacion/almaro/scripts/cargar_excel_whatsapp_oct2026.py plan
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

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
EXCEL = ALMARO / "inputs" / "almaro-whatsapp-20261009.xlsx"
GEV_CLIENTES = ALMARO / "inputs" / "gev-clientes-todos-20261001.json"
STAMP = "20261009"
OUT = ALMARO / "outputs"
OUT_PLAN = OUT / f"propuesta-clientes-whatsapp-{STAMP}.csv"
OUT_GRUPOS = OUT / f"grupos-whatsapp-{STAMP}.csv"
OUT_LOG = OUT / f"carga-whatsapp-{STAMP}-log.json"
ORIGEN = "excel_whatsapp_20261009"
DEFAULT_LISTA = 20  # 06 TRADICIONAL
CHUNK = 150
TEMPLATE_NAME = "prueba2"
TEMPLATE_ID = "a4b66f60-7894-4bc8-ace0-a7a0a1eb6fd8"
TZ = ZoneInfo("America/Argentina/Buenos_Aires")
DAY_LABEL = {
    "lunes": "Lunes",
    "martes": "Martes",
    "miercoles": "Miércoles",
    "miércoles": "Miércoles",
    "jueves": "Jueves",
    "viernes": "Viernes",
    "sabado": "Sábado",
    "sábado": "Sábado",
    "domingo": "Domingo",
    "sin_dia": "Sin día",
}


def log(msg: str) -> None:
    print(msg, flush=True)


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
    if not d:
        return "", "vacio"
    return f"549{d}", "" if len(d) == 10 else f"largo_{len(d)}"


def read_excel() -> list[dict]:
    wb = openpyxl.load_workbook(EXCEL, read_only=True, data_only=True)
    rows = []
    for ws in wb.worksheets:
        for i, r in enumerate(ws.iter_rows(values_only=True)):
            r = list(r) + [None] * 9
            if i == 0 or not r[1]:
                continue
            codigo = str(r[1]).strip()
            if not codigo or not re.search(r"\d", codigo):
                continue
            phone, flag = norm_phone(r[7])
            rows.append(
                {
                    "hoja": ws.title,
                    "codigo": codigo,
                    "codigo_int": int(re.sub(r"\D", "", codigo) or 0),
                    "nombre": re.sub(r"\s*\(\d+\)\s*$", "", str(r[0] or "")).strip(),
                    "direccion": str(r[2] or "").strip(),
                    "lat": r[3],
                    "lng": r[4],
                    "canal": r[5],
                    "promedio_u12m": r[6],
                    "celular_raw": r[7],
                    "phone": phone,
                    "phone_flag": flag,
                    "tokin_id": r[8],
                }
            )
    wb.close()
    return rows


def gev_by_cuenta() -> dict[str, dict]:
    out = {}
    if not GEV_CLIENTES.exists():
        return out
    for c in json.load(GEV_CLIENTES.open(encoding="utf-8")):
        extra = c.get("datos_extra") or {}
        for key in (extra.get("id_cuenta"), extra.get("cliente_codigo"), extra.get("odoo_id")):
            if key not in (None, ""):
                out[str(key)] = extra
                out[str(key).lstrip("0") or "0"] = extra
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["vacio"])
        w.writeheader()
        w.writerows(rows)


def require_confirm(args) -> None:
    if args.confirm != SCHEMA:
        raise SystemExit(f"[STOP] Paso '{args.step}' escribe en schema {SCHEMA}: agregar --confirm {SCHEMA}")


def chunks(items: list, n: int):
    for i in range(0, len(items), n):
        yield i // n + 1, items[i : i + n]


def append_log(entry: dict) -> None:
    history = json.loads(OUT_LOG.read_text()) if OUT_LOG.exists() else []
    if not isinstance(history, list):
        history = [history]
    history.append(entry)
    OUT_LOG.write_text(json.dumps(history, ensure_ascii=False, indent=2, default=str))


async def build_plan(conn) -> list[dict]:
    excel = read_excel()
    gev = gev_by_cuenta()
    codes = [r["codigo_int"] for r in excel]
    listas = {
        r["erp_list_id"]: r["id"]
        for r in await conn.fetch(
            f'SELECT id, erp_list_id FROM "{SCHEMA}".listas_precios WHERE erp_list_id IS NOT NULL'
        )
    }
    vendedores = {
        r["erp_codigo"]: r["id"]
        for r in await conn.fetch(
            f'SELECT id, erp_codigo FROM "{SCHEMA}".vendedores WHERE erp_codigo IS NOT NULL'
        )
    }
    existing = await conn.fetch(
        f"""
        SELECT id, codigo, partner_erp_id, phone_number, lista_precios_id, pdv_id,
               dia_de_visita::text AS dia_de_visita, metadata->>'origen' AS origen
        FROM "{SCHEMA}".clients
        WHERE codigo = ANY($1::numeric[]) OR partner_erp_id = ANY($1::bigint[])
        """,
        codes,
    )
    by_code: dict[int, dict] = {}
    for e in existing:
        for k in ("codigo", "partner_erp_id"):
            if e[k] is not None:
                by_code.setdefault(int(e[k]), dict(e))
    phones = await conn.fetch(
        f'SELECT id, phone_number FROM "{SCHEMA}".clients WHERE phone_number = ANY($1::text[])',
        [r["phone"] for r in excel if r["phone"]],
    )
    phone_owner = {p["phone_number"]: p["id"] for p in phones}

    seen_phone: dict[str, str] = {}
    plan = []
    for r in excel:
        g = gev.get(r["codigo"]) or gev.get(str(r["codigo_int"])) or {}
        lista_erp = str(g.get("lista_precios_erp_id") or "").strip()
        lista_id = listas.get(lista_erp) or DEFAULT_LISTA
        ex = by_code.get(r["codigo_int"])
        owner = phone_owner.get(r["phone"]) if r["phone"] else None
        if r["phone_flag"] == "vacio":
            accion, nota = "omitir_sin_telefono", "Excel sin WhatsApp"
        elif r["phone"] in seen_phone:
            accion, nota = "omitir_telefono_duplicado_excel", f"mismo celular que {seen_phone[r['phone']]}"
        elif owner is not None and (ex is None or owner != ex["id"]):
            accion, nota = "omitir_telefono_de_otro_cliente", f"telefono ya usado por client_id={owner}"
        elif ex is None:
            accion, nota = "crear", ""
        elif not ex.get("origen"):
            accion, nota = "actualizar_stub_erp", ""
        else:
            accion, nota = "actualizar", ""
        if r["phone"]:
            seen_phone.setdefault(r["phone"], r["codigo"])
        plan.append(
            {
                **r,
                "gev_encontrado": "si" if g else "no",
                "lista_erp": lista_erp or "(default)",
                "lista_precios_id": lista_id,
                "vendedor_codigo": g.get("vendedor_codigo") or "",
                "vendedor_nombre": g.get("vendedor_nombre") or "",
                "vendedor_id": vendedores.get(str(g.get("vendedor_codigo") or "")) or "",
                "client_id_actual": ex["id"] if ex else "",
                "phone_actual": ex["phone_number"] if ex else "",
                "lista_actual": ex["lista_precios_id"] if ex else "",
                "pdv_actual": ex["pdv_id"] if ex else "",
                "dia_actual": (ex.get("dia_de_visita") if ex else "") or "",
                "accion": accion,
                "nota": nota,
            }
        )
    return plan


async def step_clientes(conn, plan: list[dict]) -> dict:
    stats = Counter()
    async with conn.transaction():
        for r in plan:
            if r["accion"].startswith("omitir"):
                stats[r["accion"]] += 1
                continue
            meta = {
                "origen": ORIGEN,
                "tokin_id": r.get("tokin_id"),
                "hoja": r.get("hoja"),
                "canal": r.get("canal"),
                "promedio_u12m": r.get("promedio_u12m"),
                "id_cuenta": r["codigo"],
            }
            vend_id = int(r["vendedor_id"]) if r["vendedor_id"] not in ("", None) else None
            pdv_id = int(r["pdv_actual"]) if r["pdv_actual"] not in ("", None) else None
            if pdv_id is None:
                existing_pdv = await conn.fetchval(
                    f'SELECT id FROM "{SCHEMA}".puntos_venta WHERE codigo = $1 LIMIT 1',
                    r["codigo_int"],
                )
                pdv_id = int(existing_pdv) if existing_pdv is not None else None
            if pdv_id is None:
                pdv_id = await conn.fetchval(
                    f"""
                    INSERT INTO "{SCHEMA}".puntos_venta (
                      razon_social, codigo, lista_precios_id, direccion,
                      vendedor, vendedor_id, activo_ai, is_mock
                    ) VALUES ($1, $2, $3, $4, $5, $6, true, false)
                    RETURNING id
                    """,
                    r["nombre"],
                    r["codigo_int"],
                    r["lista_precios_id"],
                    r["direccion"] or None,
                    r["vendedor_nombre"] or None,
                    vend_id,
                )
            else:
                await conn.execute(
                    f"""
                    UPDATE "{SCHEMA}".puntos_venta
                    SET lista_precios_id = $2, direccion = COALESCE($3, direccion),
                        vendedor = COALESCE($4, vendedor), vendedor_id = COALESCE($5, vendedor_id),
                        razon_social = $6, updated_at = now()
                    WHERE id = $1
                    """,
                    pdv_id,
                    r["lista_precios_id"],
                    r["direccion"] or None,
                    r["vendedor_nombre"] or None,
                    vend_id,
                    r["nombre"],
                )
            if r["client_id_actual"] == "":
                client_id = await conn.fetchval(
                    f"""
                    INSERT INTO "{SCHEMA}".clients (
                      phone_number, nombre, razon_social, lista_precios_id, codigo,
                      activo_ai, vendedor, is_primary, is_mock, partner_erp_id,
                      pdv_id, metadata, lifecycle
                    ) VALUES ($1, $2, $2, $3, $4::bigint, true, $5, true, false, $4::bigint, $6, $7::jsonb, 'client')
                    RETURNING id
                    """,
                    r["phone"],
                    r["nombre"],
                    r["lista_precios_id"],
                    r["codigo_int"],
                    r["vendedor_nombre"] or None,
                    pdv_id,
                    json.dumps(meta, ensure_ascii=False),
                )
            else:
                client_id = int(r["client_id_actual"])
                await conn.execute(
                    f"""
                    UPDATE "{SCHEMA}".clients
                    SET phone_number = $2, lista_precios_id = $3, activo_ai = true,
                        pdv_id = $4, is_primary = true,
                        partner_erp_id = coalesce(partner_erp_id, $5),
                        codigo = coalesce(codigo, $5),
                        vendedor = coalesce($6, vendedor),
                        nombre = $7, razon_social = $7,
                        metadata = coalesce(metadata, '{{}}'::jsonb) || $8::jsonb,
                        lifecycle = 'client',
                        updated_at = now()
                    WHERE id = $1
                    """,
                    client_id,
                    r["phone"],
                    r["lista_precios_id"],
                    pdv_id,
                    r["codigo_int"],
                    r["vendedor_nombre"] or None,
                    r["nombre"],
                    json.dumps(meta, ensure_ascii=False),
                )
            if vend_id is not None:
                await conn.execute(
                    f"""
                    INSERT INTO "{SCHEMA}".vendedores_clientes (vendedor_id, cliente_id, activo)
                    VALUES ($1, $2, true)
                    ON CONFLICT (vendedor_id, cliente_id) DO UPDATE SET activo = true, updated_at = now()
                    """,
                    vend_id,
                    client_id,
                )
            if r["lat"] not in (None, "") and r["lng"] not in (None, ""):
                has_loc = await conn.fetchval(
                    f'SELECT 1 FROM "{SCHEMA}".client_locations WHERE client_id = $1 LIMIT 1',
                    client_id,
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
                        client_id,
                        float(r["lat"]),
                        float(r["lng"]),
                        r["direccion"] or None,
                        r["nombre"],
                    )
            stats[r["accion"]] += 1
            stats["cargados"] += 1
    return dict(stats)


async def step_pedidos(conn, codes: list[int]) -> dict:
    from erp.services.erp_order_projection_service import project_orders_raw
    from erp.services.erp_sync_service import sync_orders_to_raw

    log("[pedidos] pull GEV últimos 180 días…")
    raw_sync = await sync_orders_to_raw(SCHEMA, days=180, force=False)
    log(f"[pedidos] sync_orders_to_raw={raw_sync}")

    projection_rounds = []
    for i in range(8):
        projection = await project_orders_raw(SCHEMA, dry_run=False, limit=2000)
        summary = {k: projection.get(k) for k in ("outcome", "projected", "failed", "skipped", "message")}
        projection_rounds.append(summary)
        log(f"[pedidos] project round {i + 1}: {summary}")
        if int(projection.get("projected") or 0) == 0:
            break

    hist = await conn.fetchrow(
        f"""
        SELECT
          count(*) FILTER (WHERE c.codigo = ANY($1::numeric[]) OR c.partner_erp_id = ANY($1::bigint[])) AS clientes_excel,
          count(*) FILTER (
            WHERE (c.codigo = ANY($1::numeric[]) OR c.partner_erp_id = ANY($1::bigint[]))
              AND EXISTS (
                SELECT 1 FROM "{SCHEMA}".pedidos p
                WHERE p.cliente_id = c.id AND p.deleted_at IS NULL
              )
          ) AS clientes_con_pedido,
          (
            SELECT count(*) FROM "{SCHEMA}".pedidos p
            JOIN "{SCHEMA}".clients c2 ON c2.id = p.cliente_id
            WHERE p.deleted_at IS NULL
              AND (c2.codigo = ANY($1::numeric[]) OR c2.partner_erp_id = ANY($1::bigint[]))
          ) AS pedidos_excel
        FROM "{SCHEMA}".clients c
        """,
        codes,
    )
    return {
        "sync": raw_sync,
        "projection_rounds": projection_rounds,
        "clientes_excel": hist["clientes_excel"],
        "clientes_con_pedido": hist["clientes_con_pedido"],
        "pedidos_excel": hist["pedidos_excel"],
    }


async def loaded_clients(conn, codes: list[int]) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT id, codigo, partner_erp_id, phone_number, razon_social,
               dia_de_visita::text AS dia, activo_ai, whatsapp_estado
        FROM "{SCHEMA}".clients
        WHERE codigo = ANY($1::numeric[]) OR partner_erp_id = ANY($1::bigint[])
        ORDER BY id
        """,
        codes,
    )
    return [dict(r) for r in rows]


async def step_grupos(conn, codes: list[int]) -> dict:
    clients = await loaded_clients(conn, codes)
    sendable = [
        c
        for c in clients
        if c["phone_number"]
        and c["activo_ai"] is not False
        and str(c.get("whatsapp_estado") or "") != "no_existente"
    ]
    by_day: dict[str, list[dict]] = defaultdict(list)
    for c in sendable:
        dia = (c.get("dia") or "").strip().lower() or "sin_dia"
        by_day[dia].append(c)

    old = await conn.fetch(
        f"""
        SELECT id FROM "{SCHEMA}".grupos
        WHERE nombre LIKE 'WhatsApp Oct 2026%'
        """
    )
    if old:
        old_ids = [r["id"] for r in old]
        await conn.execute(
            f'DELETE FROM "{SCHEMA}".agenda WHERE grupo_id = ANY($1::int[]) AND enviado_at IS NULL',
            old_ids,
        )
        await conn.execute(f'DELETE FROM "{SCHEMA}".grupos WHERE id = ANY($1::int[])', old_ids)

    created = []
    for dia in sorted(by_day):
        rows = by_day[dia]
        label = DAY_LABEL.get(dia, dia.title())
        total_parts = (len(rows) + CHUNK - 1) // CHUNK
        for part, chunk_rows in chunks(rows, CHUNK):
            cids = [int(r["id"]) for r in chunk_rows]
            nombre = f"WhatsApp Oct 2026 - {label}"
            if total_parts > 1:
                nombre = f"{nombre} {part}/{total_parts}"
            dias_visita = None if dia == "sin_dia" else [dia]
            gid = await conn.fetchval(
                f"""
                INSERT INTO "{SCHEMA}".grupos
                    (nombre, activo_ai, dias_visita, client_ids)
                VALUES ($1, true, $2::core.dia_de_visita_enum[], $3::int[])
                RETURNING id
                """,
                nombre,
                dias_visita,
                cids,
            )
            created.append(
                {
                    "grupo_id": int(gid),
                    "nombre": nombre,
                    "dia": dia,
                    "part": part,
                    "total_parts": total_parts,
                    "clientes": len(cids),
                }
            )
            log(f"[grupos] {gid} {nombre} ({len(cids)})")
    write_csv(OUT_GRUPOS, created or [{"vacio": 1}])
    return {
        "clientes_sendable": len(sendable),
        "day_dist": {k: len(v) for k, v in by_day.items()},
        "grupos": created,
    }


async def step_enviar(conn, grupos: list[dict]) -> dict:
    from services.agenda_sender import (
        _client_body_param,
        _get_template_info_from_meta,
        _get_tenant_secrets_for_send,
        _normalize_phone,
        _save_envio_plantilla,
        _unpack_template_meta,
    )
    from services.whatsapp_send import send_template_message

    if not grupos:
        return {"ok": False, "error": "sin grupos"}

    tenant_id, token, phone_id, waba_id = await _get_tenant_secrets_for_send(SCHEMA)
    if not token or not phone_id:
        raise SystemExit("[STOP] Faltan secretos WhatsApp de almaro")
    language_code, _body, template_status = _unpack_template_meta(
        await _get_template_info_from_meta(token, waba_id, TEMPLATE_NAME)
    )
    log(f"[enviar] plantilla={TEMPLATE_NAME} lang={language_code} status={template_status}")
    if template_status and template_status != "APPROVED":
        raise SystemExit(f"[STOP] prueba2 no está APPROVED (status={template_status})")

    now = datetime.now(TZ)
    slot_minutes = (now.hour * 60 + now.minute) // 30 * 30
    hora = time(slot_minutes // 60, slot_minutes % 30 and slot_minutes % 60 or 0, 0)
    if slot_minutes % 30 == 0:
        hora = time(slot_minutes // 60, slot_minutes % 60, 0)

    results = []
    for g in grupos:
        agenda_id = await conn.fetchval(
            f"""
            INSERT INTO "{SCHEMA}".agenda (
              grupo_id, meta_plantilla_id, tipo, hora_envio,
              fecha_programada, dynamic_params, activo, origen
            ) VALUES ($1, $2::uuid, 'puntual', $3::time, $4::date, '[]'::jsonb, true, $5)
            RETURNING id
            """,
            g["grupo_id"],
            TEMPLATE_ID,
            hora,
            now.date(),
            ORIGEN,
        )
        clientes = await conn.fetch(
            f"""
            SELECT c.id, c.phone_number, c.nombre, c.nombre_de_pila, c.razon_social, c.vendedor
            FROM "{SCHEMA}".clients c
            JOIN "{SCHEMA}".grupos g ON c.id = ANY(g.client_ids)
            WHERE g.id = $1
              AND c.activo_ai IS NOT false
              AND c.whatsapp_estado IS DISTINCT FROM 'no_existente'
            ORDER BY c.id
            """,
            g["grupo_id"],
        )
        ok_n = 0
        fail_n = 0
        skipped = 0
        errors: list[dict] = []
        for cli in clientes:
            to_phone = _normalize_phone(cli["phone_number"])
            if not to_phone:
                skipped += 1
                continue
            body_params = [_client_body_param(dict(cli), "nombre")]
            send_ok, extra = await send_template_message(
                phone_id,
                token,
                to_phone,
                TEMPLATE_NAME,
                language_code,
                body_params,
                return_message_id=True,
                schema=SCHEMA,
            )
            if send_ok:
                ok_n += 1
                wamid = extra if isinstance(extra, str) else None
                await _save_envio_plantilla(
                    SCHEMA, to_phone, TEMPLATE_NAME, provider_message_id=wamid
                )
            else:
                fail_n += 1
                if len(errors) < 8:
                    errors.append({"client_id": cli["id"], "error": str(extra)[:240]})
            await asyncio.sleep(0.05)
        if ok_n >= 1:
            await conn.execute(
                f'UPDATE "{SCHEMA}".agenda SET enviado_at = now() WHERE id = $1',
                agenda_id,
            )
        results.append(
            {
                "grupo_id": g["grupo_id"],
                "agenda_id": int(agenda_id),
                "nombre": g["nombre"],
                "destinatarios": len(clientes),
                "ok": ok_n,
                "fail": fail_n,
                "skipped": skipped,
                "errors": errors,
            }
        )
        log(f"[enviar] {g['nombre']} ok={ok_n} fail={fail_n} skip={skipped}")
    return {
        "template_status": template_status,
        "language": language_code,
        "hora": hora.isoformat(),
        "agendas": results,
        "ok_total": sum(r["ok"] for r in results),
        "fail_total": sum(r["fail"] for r in results),
    }


async def probe_gev_keys() -> list[str]:
    try:
        from erp.services.erp_sync_service import get_connector_for_schema

        connector = await get_connector_for_schema(SCHEMA)
        rows = await connector._get("/clientes/getClientes/?id_vendedor=1463", log_endpoint="getClientes")
        first = next((r for r in rows if isinstance(r, dict)), None)
        return sorted(first.keys()) if first else []
    except Exception as exc:
        return [f"probe_error:{type(exc).__name__}"]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["plan", "clientes", "pedidos", "grupos", "enviar", "all"])
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()

    entry: dict = {
        "step": args.step,
        "at": datetime.now().isoformat(timespec="seconds"),
        "schema": SCHEMA,
    }
    conn = await core_db.get_connection()
    try:
        plan = await build_plan(conn)
        codes = [r["codigo_int"] for r in plan]
        if args.step == "plan":
            write_csv(OUT_PLAN, plan)
            entry["acciones"] = dict(Counter(r["accion"] for r in plan))
            entry["gev"] = dict(Counter(r["gev_encontrado"] for r in plan))
            entry["phone_flags"] = dict(Counter(r["phone_flag"] or "ok" for r in plan))
            entry["dia_actual"] = dict(Counter(r["dia_actual"] or "null" for r in plan))
            entry["csv"] = str(OUT_PLAN.relative_to(PLATFORM))
            entry["gev_getClientes_keys"] = await probe_gev_keys()
            print(json.dumps(entry, ensure_ascii=False, indent=2, default=str))
            return 0

        require_confirm(args)
        steps = ["clientes", "pedidos", "grupos", "enviar"] if args.step == "all" else [args.step]
        for step in steps:
            log(f"=== {step} schema={SCHEMA} ===")
            if step == "clientes":
                entry["clientes"] = await step_clientes(conn, plan)
            elif step == "pedidos":
                entry["pedidos"] = await step_pedidos(conn, codes)
            elif step == "grupos":
                entry["grupos"] = await step_grupos(conn, codes)
            else:
                grupos = (entry.get("grupos") or {}).get("grupos")
                if not grupos:
                    ginfo = await step_grupos(conn, codes)
                    entry["grupos"] = ginfo
                    grupos = ginfo["grupos"]
                entry["enviar"] = await step_enviar(conn, grupos)
            entry["clients_total"] = await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}".clients')
        append_log(entry)
        print(json.dumps(entry, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        await conn.close()
        await core_db.close_db_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
