#!/usr/bin/env python3
"""Funnel + debug Gonzales (Gonzalez Garcia).

Uso:
  python implementacion/gonzales/scripts/funnel_gonzales.py all
  python implementacion/gonzales/scripts/funnel_gonzales.py funnel
  python implementacion/gonzales/scripts/funnel_gonzales.py debug

Pooler 6543, statement_cache_size=0, pool 1–2. Solo lectura.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import ssl
import subprocess
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
OUT_FUNNEL = ROOT / "implementacion" / "gonzales" / "outputs" / "funnel"
OUT_DEBUG = ROOT / "implementacion" / "gonzales" / "outputs" / "pdv-debug"
SCHEMA = "gonzales"
TENANT_ID = "48132ae5-2383-4f3b-86f5-050b2d62a09b"
BACKEND_URL = "https://web-production-f544f.up.railway.app"
WINDOW_BEFORE = timedelta(hours=2)
WINDOW_AFTER = timedelta(hours=48)

PDV_JUAREZ = {"client_id": 243, "nombre": "JUAREZ MARIA SOLEDAD", "phone": "5493513995562"}
PDV_MELGAREJO = {"client_id": 237, "nombre": "MELGAREJO ALAYO OSWALDO CHILDER", "phone": "5493513929320"}

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend-supabase" / ".env")


def phone_match_key(raw: str | None) -> str:
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    return None


def iso(value: Any) -> str:
    dt = parse_ts(value)
    if dt is None:
        if value is None:
            return ""
        if isinstance(value, date):
            return value.isoformat()
        return str(value)
    return dt.isoformat()


def csv_bool(value: bool) -> str:
    return "true" if value else "false"


def json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [json_ready(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    return value


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def db_url() -> str:
    url = (
        os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL / DATABASE_URL en .env")
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    if ":5432@" in url:
        url = url.replace(":5432@", ":6543@")
    return url


def estado_grupo(estado: str | None) -> str:
    value = (estado or "").strip().lower()
    if value in {"confirmado", "descargado"}:
        return "cerrado"
    if value == "abierto":
        return "abierto"
    return value or "desconocido"


def classify_media(*, db_image: bool, db_carousel: bool, meta_kind: str) -> str:
    if db_carousel or meta_kind == "carrusel":
        if db_image or meta_kind in {"header_imagen", "mixto"}:
            return "mixto"
        return "carrusel"
    if db_image or meta_kind == "header_imagen":
        return "header_imagen"
    if meta_kind == "mixto":
        return "mixto"
    return "texto"


def classify_meta_item(item: dict[str, Any] | None) -> str:
    if not item:
        return "desconocido"
    comps = item.get("components") or []
    has_carousel = False
    has_image = False
    for comp in comps:
        if not isinstance(comp, dict):
            continue
        ctype = str(comp.get("type") or "").upper()
        fmt = str(comp.get("format") or "").upper()
        if ctype == "CAROUSEL":
            has_carousel = True
        if ctype == "HEADER" and fmt in {"IMAGE", "VIDEO", "DOCUMENT"}:
            has_image = True
        cards = comp.get("cards")
        if isinstance(cards, list) and cards:
            has_carousel = True
    if has_carousel and has_image:
        return "mixto"
    if has_carousel:
        return "carrusel"
    if has_image:
        return "header_imagen"
    return "texto"


def fetch_meta_template(name: str) -> dict[str, Any] | None:
    url = f"{BACKEND_URL}/{SCHEMA}/plantillas-meta/by-name/{name}"
    try:
        proc = subprocess.run(
            ["curl", "-sS", "--max-time", "30", url],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            if isinstance(data, dict) and data.get("item"):
                return data
            if isinstance(data, dict) and data.get("error"):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    try:
        req = Request(url, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ssl.SSLError):
        return None


SQL_AGENDAS = """
SELECT
  a.id,
  a.activo,
  a.tipo,
  a.dia_semana::text AS dia_semana,
  a.hora_envio::text AS hora_envio,
  a.fecha_programada,
  a.proxima_fecha_envio,
  a.grupo_id,
  g.nombre AS grupo_nombre,
  a.client_id,
  cl.nombre AS client_nombre,
  cl.razon_social AS client_razon_social,
  a.estrategia_id,
  a.origen,
  a.supabase_media_url,
  a.carousel_config,
  a.meta_plantilla_id,
  mp.template_name,
  mp.category,
  mp.media_url AS plantilla_media_url
FROM gonzales.agenda a
LEFT JOIN gonzales.grupos g ON g.id = a.grupo_id
LEFT JOIN gonzales.clients cl ON cl.id = a.client_id
JOIN public.meta_plantillas mp ON mp.id = a.meta_plantilla_id
WHERE a.activo = TRUE
ORDER BY a.id;
"""

SQL_ENVIOS = """
SELECT
  ep.id,
  ep.session_id,
  right(regexp_replace(COALESCE(ep.session_id, ''), '[^0-9]', '', 'g'), 10) AS digits,
  ep.template_name,
  ep.created_at
FROM gonzales.envios_plantillas ep
WHERE length(regexp_replace(COALESCE(ep.session_id, ''), '[^0-9]', '', 'g')) >= 10
ORDER BY ep.created_at, ep.id;
"""

SQL_INBOUND = """
SELECT digits, created_at, session_id, source
FROM (
  SELECT
    right(regexp_replace(COALESCE(session_id, ''), '[^0-9]', '', 'g'), 10) AS digits,
    created_at,
    session_id,
    'n8n'::text AS source
  FROM gonzales.n8n_chat_histories
  WHERE (message->>'type') IN ('human', 'user')
    AND length(regexp_replace(COALESCE(session_id, ''), '[^0-9]', '', 'g')) >= 10
  UNION ALL
  SELECT
    right(regexp_replace(COALESCE(c.session_id, ''), '[^0-9]', '', 'g'), 10) AS digits,
    ce.created_at,
    c.session_id,
    'core'::text AS source
  FROM core.conversations c
  JOIN core.conversation_events ce ON ce.conversation_id = c.id
  WHERE c.schema_name = 'gonzales'
    AND ce.event_type = 'user_message'
    AND length(regexp_replace(COALESCE(c.session_id, ''), '[^0-9]', '', 'g')) >= 10
) m
ORDER BY digits, created_at;
"""

SQL_PEDIDOS = """
SELECT
  p.id AS pedido_id,
  p.cliente_id,
  p.fecha,
  (p.fecha AT TIME ZONE 'America/Argentina/Buenos_Aires') AS fecha_ts,
  LOWER(TRIM(COALESCE(p.estado, ''))) AS estado,
  LOWER(TRIM(COALESCE(p.origen, ''))) AS origen,
  p.total,
  p.notas,
  (p.fecha::time = '00:00:00') AS fecha_medianoche,
  right(regexp_replace(COALESCE(cl.phone_number, ''), '[^0-9]', '', 'g'), 10) AS digits,
  cl.phone_number,
  cl.nombre,
  cl.razon_social
FROM gonzales.pedidos p
JOIN gonzales.clients cl ON cl.id = p.cliente_id
WHERE p.deleted_at IS NULL
ORDER BY p.fecha, p.id;
"""

SQL_CLIENTS_BY_DIGITS = """
SELECT
  cl.id AS client_id,
  cl.nombre,
  cl.razon_social,
  cl.phone_number,
  cl.nombre_de_pila,
  cl.activo_ai,
  right(regexp_replace(COALESCE(cl.phone_number, ''), '[^0-9]', '', 'g'), 10) AS digits
FROM gonzales.clients cl
WHERE length(regexp_replace(COALESCE(cl.phone_number, ''), '[^0-9]', '', 'g')) >= 10
  AND right(regexp_replace(COALESCE(cl.phone_number, ''), '[^0-9]', '', 'g'), 10) = ANY($1::text[]);
"""

SQL_COUNTS = """
SELECT
  (SELECT COUNT(*) FROM gonzales.clients) AS n_clients,
  (SELECT COUNT(*) FROM gonzales.agenda WHERE activo) AS n_agendas_activas,
  (SELECT COUNT(*) FROM gonzales.envios_plantillas) AS n_envios,
  (SELECT COUNT(DISTINCT session_id) FROM gonzales.envios_plantillas) AS n_envios_sessions,
  (SELECT COUNT(*) FROM gonzales.pedidos WHERE deleted_at IS NULL) AS n_pedidos;
"""

SQL_TIMELINE = """
SELECT created_at, digits, session_id, actor, content, source
FROM (
  SELECT
    h.created_at,
    right(regexp_replace(COALESCE(h.session_id, ''), '[^0-9]', '', 'g'), 10) AS digits,
    h.session_id,
    COALESCE(h.message->>'type', 'unknown') AS actor,
    COALESCE(h.message->>'content', h.message::text) AS content,
    'n8n'::text AS source
  FROM gonzales.n8n_chat_histories h
  WHERE right(regexp_replace(COALESCE(h.session_id, ''), '[^0-9]', '', 'g'), 10) = ANY($1::text[])
  UNION ALL
  SELECT
    ce.created_at,
    right(regexp_replace(COALESCE(c.session_id, ''), '[^0-9]', '', 'g'), 10),
    c.session_id,
    ce.event_type,
    COALESCE(
      ce.event_payload->>'text',
      ce.event_payload->>'transcription',
      ce.event_payload->>'content',
      ce.event_payload::text
    ),
    'core'::text
  FROM core.conversations c
  JOIN core.conversation_events ce ON ce.conversation_id = c.id
  WHERE c.schema_name = 'gonzales'
    AND ce.event_type IN (
      'user_message', 'assistant_message', 'outbound_message', 'template_sent'
    )
    AND right(regexp_replace(COALESCE(c.session_id, ''), '[^0-9]', '', 'g'), 10) = ANY($1::text[])
) t
ORDER BY created_at;
"""

SQL_TOOLS = """
SELECT
  r.id,
  r.created_at,
  r.tool_name,
  r.status,
  r.latency_ms,
  r.error_summary,
  r.args_json,
  r.invocation_id,
  t.request_id,
  t.session_id,
  right(regexp_replace(COALESCE(t.session_id, ''), '[^0-9]', '', 'g'), 10) AS digits
FROM core.agent_tool_runs r
JOIN core.agent_turns t ON t.id = r.turn_id
WHERE t.schema_name = 'gonzales'
  AND right(regexp_replace(COALESCE(t.session_id, ''), '[^0-9]', '', 'g'), 10) = ANY($1::text[])
ORDER BY r.created_at;
"""

SQL_ITEMS = """
SELECT
  pedido_id,
  product_code,
  nombre,
  cantidad_solicitada,
  precio_unitario,
  notas
FROM gonzales.items_pedido
WHERE pedido_id = ANY($1::int[])
ORDER BY pedido_id, id;
"""

SQL_PRODUCTOS = """
SELECT
  product_code,
  nombre,
  unidades_por_bulto,
  unidad_minima_de_venta,
  cantidad_minima_de_venta,
  umv_tipo,
  tipo_venta,
  descripcion
FROM gonzales.productos
WHERE nombre ILIKE '%membrillo%'
   OR product_code = ANY($1::text[]);
"""

SQL_PEDIDOS_PDV = """
SELECT
  p.id AS pedido_id,
  p.cliente_id,
  p.fecha,
  p.estado,
  p.total,
  p.origen,
  p.notas,
  p.deleted_at
FROM gonzales.pedidos p
WHERE p.cliente_id = ANY($1::int[])
ORDER BY p.fecha, p.id;
"""

SQL_ENVIOS_PDV = """
SELECT id, session_id, template_name, created_at
FROM gonzales.envios_plantillas
WHERE right(regexp_replace(COALESCE(session_id, ''), '[^0-9]', '', 'g'), 10) = ANY($1::text[])
ORDER BY created_at;
"""


def _carousel_len(raw: Any) -> int:
    if isinstance(raw, list):
        return len(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return len(parsed) if isinstance(parsed, list) else 0
        except json.JSONDecodeError:
            return 0
    return 0


async def load_funnel(conn: asyncpg.Connection) -> dict[str, Any]:
    agendas = [dict(r) for r in await conn.fetch(SQL_AGENDAS)]
    envios = [dict(r) for r in await conn.fetch(SQL_ENVIOS)]
    inbound = [dict(r) for r in await conn.fetch(SQL_INBOUND)]
    pedidos = [dict(r) for r in await conn.fetch(SQL_PEDIDOS)]
    digits = sorted({e["digits"] for e in envios if e.get("digits")})
    clients = [dict(r) for r in await conn.fetch(SQL_CLIENTS_BY_DIGITS, digits)] if digits else []
    counts = dict(await conn.fetchrow(SQL_COUNTS))
    return {
        "agendas": agendas,
        "envios": envios,
        "inbound": inbound,
        "pedidos": pedidos,
        "clients": clients,
        "counts": counts,
    }


def enrich_agendas(agendas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    today = date.today()
    meta_cache: dict[str, dict[str, Any] | None] = {}
    rows: list[dict[str, Any]] = []
    for a in agendas:
        name = str(a.get("template_name") or "")
        if name not in meta_cache:
            print(f"    meta by-name {name}")
            meta_cache[name] = fetch_meta_template(name)
        payload = meta_cache[name] or {}
        item = payload.get("item") if isinstance(payload, dict) else None
        meta_kind = classify_meta_item(item if isinstance(item, dict) else None)
        meta_status = item.get("status") if isinstance(item, dict) else ""
        db_image = bool(a.get("supabase_media_url") or a.get("plantilla_media_url"))
        db_carousel = _carousel_len(a.get("carousel_config")) > 0
        media_kind = classify_media(db_image=db_image, db_carousel=db_carousel, meta_kind=meta_kind)
        fecha = a.get("fecha_programada")
        puntual_vencida = bool(a.get("tipo") == "puntual" and fecha and fecha < today)
        rows.append(
            {
                "agenda_id": a["id"],
                "tipo": a.get("tipo") or "",
                "dia_semana": a.get("dia_semana") or "",
                "hora_envio": a.get("hora_envio") or "",
                "fecha_programada": iso(fecha),
                "puntual_vencida": csv_bool(puntual_vencida),
                "grupo_id": a.get("grupo_id") or "",
                "grupo_nombre": a.get("grupo_nombre") or "",
                "client_id": a.get("client_id") or "",
                "client_nombre": a.get("client_nombre") or a.get("client_razon_social") or "",
                "estrategia_id": a.get("estrategia_id") or "",
                "origen": a.get("origen") or "",
                "alcance": "uno_a_uno" if a.get("estrategia_id") else "grupo",
                "template_name": name,
                "category": a.get("category") or "",
                "db_tiene_imagen": csv_bool(db_image),
                "db_carousel_cards": _carousel_len(a.get("carousel_config")),
                "meta_status": meta_status or "",
                "meta_kind": meta_kind,
                "media_kind": media_kind,
            }
        )
    n_grupo = sum(1 for r in rows if r["alcance"] == "grupo")
    n_11 = sum(1 for r in rows if r["alcance"] == "uno_a_uno")
    n_vencidas = sum(1 for r in rows if r["puntual_vencida"] == "true")
    n_recurrente = sum(1 for r in rows if r["tipo"] == "recurrente")
    templates = sorted({r["template_name"] for r in rows})
    media_counts: dict[str, int] = defaultdict(int)
    for r in rows:
        media_counts[r["media_kind"]] += 1
    resumen = {
        "agendas_activas": len(rows),
        "de_grupo": n_grupo,
        "uno_a_uno": n_11,
        "recurrentes": n_recurrente,
        "puntuales_vencidas": n_vencidas,
        "plantillas_distintas": templates,
        "media_kind_counts": dict(media_counts),
    }
    return rows, resumen


def build_funnel(
    envios: list[dict[str, Any]],
    inbound: list[dict[str, Any]],
    pedidos: list[dict[str, Any]],
    clients: list[dict[str, Any]],
) -> dict[str, Any]:
    inbound_by_digits: dict[str, list[datetime]] = defaultdict(list)
    for row in inbound:
        dt = parse_ts(row.get("created_at"))
        digits = row.get("digits")
        if dt and digits:
            inbound_by_digits[str(digits)].append(dt)
    for times in inbound_by_digits.values():
        times.sort()

    envios_rows = []
    first_envio: dict[str, datetime] = {}
    envios_by_digits: dict[str, list[datetime]] = defaultdict(list)
    for e in envios:
        dt = parse_ts(e.get("created_at"))
        digits = str(e.get("digits") or "")
        envios_rows.append(
            {
                "envio_id": e["id"],
                "session_id": e.get("session_id") or "",
                "digits": digits,
                "template_name": e.get("template_name") or "",
                "created_at": iso(dt),
            }
        )
        if dt and digits:
            envios_by_digits[digits].append(dt)
            if digits not in first_envio or dt < first_envio[digits]:
                first_envio[digits] = dt

    clients_by_digits: dict[str, dict[str, Any]] = {}
    for cl in clients:
        clients_by_digits[str(cl["digits"])] = cl

    attributed: list[dict[str, Any]] = []
    for p in pedidos:
        digits = str(p.get("digits") or "")
        order_at = parse_ts(p.get("fecha_ts") or p.get("fecha"))
        origen = str(p.get("origen") or "")
        midnight = bool(p.get("fecha_medianoche"))
        times = inbound_by_digits.get(digits) or []
        en_ventana = False
        if order_at and times and not midnight and origen != "erp":
            en_ventana = any(
                (msg_at - WINDOW_BEFORE) <= order_at < (msg_at + WINDOW_AFTER) for msg_at in times
            )
        row = {
            "pedido_id": p["pedido_id"],
            "cliente_id": p["cliente_id"],
            "fecha": iso(order_at),
            "estado": p.get("estado") or "",
            "estado_grupo": estado_grupo(p.get("estado")),
            "origen": origen,
            "total": str(p.get("total") if p.get("total") is not None else ""),
            "digits": digits,
            "nombre": p.get("nombre") or p.get("razon_social") or "",
            "fecha_medianoche": csv_bool(midnight),
            "atribuido": csv_bool(en_ventana),
        }
        if en_ventana:
            attributed.append(row)

    attr_by_digits: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in attributed:
        attr_by_digits[row["digits"]].append(row)

    funnel_rows = []
    n_nunca = n_interact_no = n_compro = 0
    for digits, first_at in sorted(first_envio.items()):
        times = inbound_by_digits.get(digits) or []
        replied = any(t > first_at for t in times)
        orders = attr_by_digits.get(digits) or []
        closed = [o for o in orders if o["estado_grupo"] == "cerrado"]
        if closed:
            bucket = "compro_al_menos_una"
            n_compro += 1
        elif replied:
            bucket = "interactuo_sin_compra"
            n_interact_no += 1
        else:
            bucket = "nunca_contesto"
            n_nunca += 1
        cl = clients_by_digits.get(digits) or {}
        n_env = len(envios_by_digits.get(digits) or [])
        funnel_rows.append(
            {
                "digits": digits,
                "phone_number": cl.get("phone_number") or "",
                "client_id": cl.get("client_id") or "",
                "nombre": cl.get("nombre") or cl.get("razon_social") or "",
                "n_envios": n_env,
                "primer_envio": iso(first_at),
                "respondio_despues_envio": csv_bool(replied),
                "n_pedidos_atribuidos": len(orders),
                "n_pedidos_cerrados": len(closed),
                "bucket": bucket,
            }
        )

    return {
        "envios_rows": envios_rows,
        "funnel_rows": funnel_rows,
        "attributed": attributed,
        "counts": {
            "telefonos_contactados": len(first_envio),
            "nunca_contesto": n_nunca,
            "interactuo_sin_compra": n_interact_no,
            "compro_al_menos_una": n_compro,
            "pedidos_atribuidos": len(attributed),
            "pedidos_cerrados": sum(1 for r in attributed if r["estado_grupo"] == "cerrado"),
            "pedidos_abiertos": sum(1 for r in attributed if r["estado_grupo"] == "abierto"),
        },
    }


def clip(text: Any, n: int = 400) -> str:
    value = str(text or "").replace("\n", " ").strip()
    if len(value) <= n:
        return value
    return value[: n - 1] + "…"


async def load_debug(conn: asyncpg.Connection) -> dict[str, Any]:
    phones = [PDV_JUAREZ["phone"], PDV_MELGAREJO["phone"]]
    digits = [phone_match_key(p) for p in phones]
    client_ids = [PDV_JUAREZ["client_id"], PDV_MELGAREJO["client_id"]]
    timeline = [dict(r) for r in await conn.fetch(SQL_TIMELINE, digits)]
    tools = [dict(r) for r in await conn.fetch(SQL_TOOLS, digits)]
    pedidos = [dict(r) for r in await conn.fetch(SQL_PEDIDOS_PDV, client_ids)]
    pedido_ids = [int(p["pedido_id"]) for p in pedidos]
    items = [dict(r) for r in await conn.fetch(SQL_ITEMS, pedido_ids)] if pedido_ids else []
    codes = [str(i.get("product_code") or "") for i in items if i.get("product_code")]
    productos = [dict(r) for r in await conn.fetch(SQL_PRODUCTOS, codes)]
    envios = [dict(r) for r in await conn.fetch(SQL_ENVIOS_PDV, digits)]
    return {
        "timeline": timeline,
        "tools": tools,
        "pedidos": pedidos,
        "items": items,
        "productos": productos,
        "envios": envios,
    }


def rows_for_digits(rows: list[dict[str, Any]], phone: str) -> list[dict[str, Any]]:
    key = phone_match_key(phone)
    out = []
    for row in rows:
        digits = str(row.get("digits") or phone_match_key(str(row.get("session_id") or "")))
        if digits == key:
            out.append(row)
    return out


def build_debug_exports(data: dict[str, Any]) -> dict[str, Any]:
    def timeline_csv(phone: str) -> list[dict[str, Any]]:
        rows = []
        for t in rows_for_digits(data["timeline"], phone):
            rows.append(
                {
                    "created_at": iso(t.get("created_at")),
                    "source": t.get("source") or "",
                    "actor": t.get("actor") or "",
                    "session_id": t.get("session_id") or "",
                    "content": clip(t.get("content"), 600),
                }
            )
        return rows

    def tools_csv(phone: str) -> list[dict[str, Any]]:
        rows = []
        for t in rows_for_digits(data["tools"], phone):
            args = t.get("args_json")
            if not isinstance(args, (dict, list, str)):
                args = {}
            rows.append(
                {
                    "created_at": iso(t.get("created_at")),
                    "tool_name": t.get("tool_name") or "",
                    "status": t.get("status") or "",
                    "latency_ms": t.get("latency_ms") if t.get("latency_ms") is not None else "",
                    "error_summary": t.get("error_summary") or "",
                    "request_id": t.get("request_id") or "",
                    "args_json": json.dumps(json_ready(args), ensure_ascii=False),
                }
            )
        return rows

    juarez_timeline = timeline_csv(PDV_JUAREZ["phone"])
    melga_timeline = timeline_csv(PDV_MELGAREJO["phone"])
    juarez_tools = tools_csv(PDV_JUAREZ["phone"])
    melga_tools = tools_csv(PDV_MELGAREJO["phone"])

    items_rows = []
    for it in data["items"]:
        items_rows.append(
            {
                "pedido_id": it.get("pedido_id"),
                "product_code": it.get("product_code") or "",
                "nombre": it.get("nombre") or "",
                "cantidad_solicitada": it.get("cantidad_solicitada"),
                "precio_unitario": it.get("precio_unitario"),
                "notas": it.get("notas") or "",
            }
        )
    pedidos_rows = []
    for p in data["pedidos"]:
        pedidos_rows.append(
            {
                "pedido_id": p.get("pedido_id"),
                "cliente_id": p.get("cliente_id"),
                "fecha": iso(p.get("fecha")),
                "estado": p.get("estado") or "",
                "total": str(p.get("total") if p.get("total") is not None else ""),
                "origen": p.get("origen") or "",
                "notas": p.get("notas") or "",
                "deleted_at": iso(p.get("deleted_at")),
            }
        )
    envios_rows = []
    for e in data["envios"]:
        envios_rows.append(
            {
                "id": e.get("id"),
                "session_id": e.get("session_id") or "",
                "template_name": e.get("template_name") or "",
                "created_at": iso(e.get("created_at")),
            }
        )
    productos_rows = []
    for p in data["productos"]:
        productos_rows.append({k: ("" if v is None else v) for k, v in p.items()})

    return {
        "juarez_timeline": juarez_timeline,
        "melgarejo_timeline": melga_timeline,
        "juarez_tools": juarez_tools,
        "melgarejo_tools": melga_tools,
        "items": items_rows,
        "pedidos": pedidos_rows,
        "envios": envios_rows,
        "productos": productos_rows,
        "raw_tools": data["tools"],
        "raw_timeline": data["timeline"],
    }


async def run(cmd: str) -> int:
    pool = await asyncpg.create_pool(
        db_url(),
        min_size=1,
        max_size=2,
        statement_cache_size=0,
    )
    try:
        async with pool.acquire() as conn:
            funnel_data = None
            debug_data = None
            if cmd in {"all", "funnel"}:
                print("[*] agendas / envios / inbound / pedidos")
                funnel_data = await load_funnel(conn)
            if cmd in {"all", "debug"}:
                print("[*] timeline / tools / items PDV")
                debug_data = await load_debug(conn)
    finally:
        await pool.close()

    if funnel_data is not None:
        print("[*] clasificar plantillas Meta")
        agenda_rows, agenda_resumen = enrich_agendas(funnel_data["agendas"])
        funnel = build_funnel(
            funnel_data["envios"],
            funnel_data["inbound"],
            funnel_data["pedidos"],
            funnel_data["clients"],
        )
        write_csv(
            OUT_FUNNEL / "00_agendas.csv",
            agenda_rows,
            [
                "agenda_id",
                "tipo",
                "dia_semana",
                "hora_envio",
                "fecha_programada",
                "puntual_vencida",
                "alcance",
                "grupo_id",
                "grupo_nombre",
                "client_id",
                "client_nombre",
                "estrategia_id",
                "origen",
                "template_name",
                "category",
                "db_tiene_imagen",
                "db_carousel_cards",
                "meta_status",
                "meta_kind",
                "media_kind",
            ],
        )
        write_json(OUT_FUNNEL / "00_agendas_resumen.json", agenda_resumen)
        write_csv(
            OUT_FUNNEL / "01_envios.csv",
            funnel["envios_rows"],
            ["envio_id", "session_id", "digits", "template_name", "created_at"],
        )
        write_csv(
            OUT_FUNNEL / "02_clientes_funnel.csv",
            funnel["funnel_rows"],
            [
                "digits",
                "phone_number",
                "client_id",
                "nombre",
                "n_envios",
                "primer_envio",
                "respondio_despues_envio",
                "n_pedidos_atribuidos",
                "n_pedidos_cerrados",
                "bucket",
            ],
        )
        write_csv(
            OUT_FUNNEL / "02_pedidos_atribuidos.csv",
            funnel["attributed"],
            [
                "pedido_id",
                "cliente_id",
                "fecha",
                "estado",
                "estado_grupo",
                "origen",
                "total",
                "digits",
                "nombre",
                "fecha_medianoche",
                "atribuido",
            ],
        )
        resumen = {
            "tenant": SCHEMA,
            "tenant_id": TENANT_ID,
            "ventana": "historico_envios",
            "atribucion": "inbound humano, -2h/+48h, sin medianoche, origen!=erp",
            "base": json_ready(funnel_data["counts"]),
            "agendas": agenda_resumen,
            "funnel": funnel["counts"],
            "nota_metadata": "clients.metadata no se escribe en esta entrega",
        }
        write_json(OUT_FUNNEL / "99_resumen.json", resumen)
        print(f"[ok] funnel → {OUT_FUNNEL}")
        print(json.dumps(json_ready(resumen["funnel"]), ensure_ascii=False))
        print(json.dumps(json_ready(agenda_resumen), ensure_ascii=False))

    if debug_data is not None:
        exports = build_debug_exports(debug_data)
        write_csv(
            OUT_DEBUG / "juarez_timeline.csv",
            exports["juarez_timeline"],
            ["created_at", "source", "actor", "session_id", "content"],
        )
        write_csv(
            OUT_DEBUG / "melgarejo_timeline.csv",
            exports["melgarejo_timeline"],
            ["created_at", "source", "actor", "session_id", "content"],
        )
        write_csv(
            OUT_DEBUG / "juarez_tools.csv",
            exports["juarez_tools"],
            ["created_at", "tool_name", "status", "latency_ms", "error_summary", "request_id", "args_json"],
        )
        write_csv(
            OUT_DEBUG / "melgarejo_tools.csv",
            exports["melgarejo_tools"],
            ["created_at", "tool_name", "status", "latency_ms", "error_summary", "request_id", "args_json"],
        )
        write_csv(
            OUT_DEBUG / "pedidos.csv",
            exports["pedidos"],
            ["pedido_id", "cliente_id", "fecha", "estado", "total", "origen", "notas", "deleted_at"],
        )
        write_csv(
            OUT_DEBUG / "items.csv",
            exports["items"],
            ["pedido_id", "product_code", "nombre", "cantidad_solicitada", "precio_unitario", "notas"],
        )
        write_csv(
            OUT_DEBUG / "envios.csv",
            exports["envios"],
            ["id", "session_id", "template_name", "created_at"],
        )
        write_csv(
            OUT_DEBUG / "productos_membrillo.csv",
            exports["productos"],
            [
                "product_code",
                "nombre",
                "unidades_por_bulto",
                "unidad_minima_de_venta",
                "cantidad_minima_de_venta",
                "umv_tipo",
                "tipo_venta",
                "descripcion",
            ],
        )
        write_json(
            OUT_DEBUG / "99_raw.json",
            {
                "juarez": PDV_JUAREZ,
                "melgarejo": PDV_MELGAREJO,
                "n_juarez_msgs": len(exports["juarez_timeline"]),
                "n_melgarejo_msgs": len(exports["melgarejo_timeline"]),
                "n_juarez_tools": len(exports["juarez_tools"]),
                "n_melgarejo_tools": len(exports["melgarejo_tools"]),
            },
        )
        print(f"[ok] debug → {OUT_DEBUG}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", nargs="?", default="all", choices=["all", "funnel", "debug"])
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.cmd)))


if __name__ == "__main__":
    main()
