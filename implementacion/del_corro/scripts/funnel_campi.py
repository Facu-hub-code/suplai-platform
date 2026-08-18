#!/usr/bin/env python3
"""Funnel del agente Campi (del_corro): CSVs por fase.

Uso:
  set -a && source ../backend-supabase/.env && set +a
  python implementacion/del_corro/scripts/funnel_campi.py all

Pooler 6543, statement_cache_size=0, pool 1–2 (regla de conexiones).
Solo lectura. No escribe metadata de clientes.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "implementacion" / "del_corro" / "outputs" / "funnel"
SCHEMA = "del_corro"
FRUSTRATION_RE = re.compile(
    r"(no entend|no me entend|incorrect|error|olvidate|no sirve|in[uú]til|"
    r"reclamo|equivoc|no es eso|ya te dije|te lo repet|no funciona|"
    r"p[eé]simo|horrible|qu[eé] carajo|enojad|devoluci[oó]n|nunca lleg|"
    r"no me lleg[oó])",
    re.IGNORECASE,
)
CATALOG_URL_RE = re.compile(r"tienda\.suplaisales\.com", re.IGNORECASE)
STOPWORDS = {
    "de",
    "la",
    "el",
    "los",
    "las",
    "un",
    "una",
    "unos",
    "unas",
    "y",
    "o",
    "u",
    "x",
    "pack",
    "kg",
    "gr",
    "g",
    "ml",
    "lt",
    "l",
    "del",
    "al",
    "en",
    "con",
    "para",
    "por",
    "the",
    "of",
    "a",
    "unid",
    "unidad",
    "unidades",
    "caja",
    "cajas",
}

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend-supabase" / ".env")


# ---------------------------------------------------------------------------
# Helpers puros (testeables sin BD)
# ---------------------------------------------------------------------------


def phone_match_key(raw: str | None) -> str:
    """Normaliza a dígitos; usa últimos 10 si hay al menos 10 (AR)."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) >= 10:
        return digits[-10:]
    return digits


def fold_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def tokenize_product_name(name: str | None) -> list[str]:
    folded = fold_text(name)
    tokens = re.findall(r"[a-z0-9]{2,}", folded)
    return [tok for tok in tokens if tok not in STOPWORDS]


def _token_in_corpus(token: str, folded_corpus: str) -> bool:
    if token in folded_corpus:
        return True
    if len(token) > 4 and token.endswith("s") and token[:-1] in folded_corpus:
        return True
    if len(token) > 4 and (token + "s") in folded_corpus:
        return True
    return False


def message_text(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    parts.append(str(part.get("text") or part.get("content") or ""))
            return " ".join(p for p in parts if p)
        text = message.get("text")
        if isinstance(text, str):
            return text
        return json.dumps(message, ensure_ascii=False)
    return str(message)


def line_mentioned_in_corpus(product_code: str | None, nombre: str | None, corpus: str) -> bool:
    folded = fold_text(corpus)
    code = str(product_code or "").strip()
    if len(code) >= 3 and fold_text(code) in folded:
        return True
    tokens = tokenize_product_name(nombre)
    if not tokens:
        return False
    if len(tokens) == 1:
        return len(tokens[0]) >= 5 and tokens[0] in folded
    hits = sum(1 for tok in tokens if _token_in_corpus(tok, folded))
    return hits >= min(2, len(tokens))


def match_ratio_for_lines(lines: list[dict[str, Any]], corpus: str) -> tuple[float, list[str], list[str]]:
    if not lines:
        return 0.0, [], []
    matched: list[str] = []
    unmatched: list[str] = []
    for line in lines:
        code = str(line.get("product_code") or "").strip()
        nombre = str(line.get("nombre") or "").strip()
        label = code or nombre or "?"
        if line_mentioned_in_corpus(code, nombre, corpus):
            matched.append(label)
        else:
            unmatched.append(label)
    return len(matched) / len(lines), matched, unmatched


def estado_grupo(estado: str | None) -> str:
    value = (estado or "").strip().lower()
    if value in {"confirmado", "descargado"}:
        return "cerrado"
    if value == "abierto":
        return "abierto"
    return value or "desconocido"


def motivo_exclusion(*, origen: str, tiene_inbound: bool, en_ventana: bool, fecha_medianoche: bool) -> str:
    if (origen or "").strip().lower() == "erp":
        return "origen_erp"
    if fecha_medianoche:
        return "carga_historica_sin_hora"
    if not tiene_inbound:
        return "sin_conversacion"
    if not en_ventana:
        return "fuera_de_ventana"
    return ""


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
        return "" if value is None else str(value)
    return dt.isoformat()


def csv_bool(value: bool) -> str:
    return "true" if value else "false"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


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


def _json_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def metadata_keys(raw: Any) -> str:
    meta = _json_or_empty(raw)
    return ",".join(sorted(meta.keys()))


# ---------------------------------------------------------------------------
# SQL (consultas consolidadas, sin loops por cliente)
# ---------------------------------------------------------------------------

SQL_PEDIDOS = """
WITH inbound AS (
  SELECT
    right(regexp_replace(COALESCE(session_id, ''), '[^0-9]', '', 'g'), 10) AS digits,
    created_at
  FROM del_corro.n8n_chat_histories
  WHERE (message->>'type') IN ('human', 'user')
    AND length(regexp_replace(COALESCE(session_id, ''), '[^0-9]', '', 'g')) >= 10
  UNION ALL
  SELECT
    right(regexp_replace(COALESCE(c.session_id, ''), '[^0-9]', '', 'g'), 10) AS digits,
    ce.created_at
  FROM core.conversations c
  JOIN core.conversation_events ce ON ce.conversation_id = c.id
  WHERE c.schema_name = 'del_corro'
    AND ce.event_type = 'user_message'
    AND length(regexp_replace(COALESCE(c.session_id, ''), '[^0-9]', '', 'g')) >= 10
),
ped AS (
  SELECT
    p.id,
    p.cliente_id,
    p.fecha,
    (p.fecha AT TIME ZONE 'America/Argentina/Buenos_Aires') AS fecha_ts,
    LOWER(TRIM(COALESCE(p.estado, ''))) AS estado,
    LOWER(TRIM(COALESCE(p.origen, ''))) AS origen,
    p.total,
    p.notas,
    right(regexp_replace(COALESCE(cl.phone_number, ''), '[^0-9]', '', 'g'), 10) AS digits,
    cl.phone_number
  FROM del_corro.pedidos p
  JOIN del_corro.clients cl ON cl.id = p.cliente_id
  WHERE p.deleted_at IS NULL
),
flags AS (
  SELECT
    ped.id,
    bool_or(TRUE) FILTER (WHERE inbound.digits IS NOT NULL) AS tiene_inbound,
    bool_or(
      inbound.created_at IS NOT NULL
      AND ped.fecha_ts >= inbound.created_at - INTERVAL '2 hours'
      AND ped.fecha_ts < inbound.created_at + INTERVAL '24 hours'
    ) AS en_ventana_24h,
    bool_or(
      inbound.created_at IS NOT NULL
      AND ped.fecha_ts >= inbound.created_at - INTERVAL '2 hours'
      AND ped.fecha_ts < inbound.created_at + INTERVAL '48 hours'
    ) AS en_ventana_48h,
    bool_or(
      inbound.created_at IS NOT NULL
      AND ped.fecha_ts >= inbound.created_at - INTERVAL '2 hours'
      AND ped.fecha_ts < inbound.created_at + INTERVAL '7 days'
    ) AS en_ventana_7d
  FROM ped
  LEFT JOIN inbound ON inbound.digits = ped.digits
  GROUP BY ped.id
)
SELECT
  ped.id AS pedido_id,
  ped.cliente_id,
  ped.fecha,
  ped.fecha_ts,
  ped.estado,
  ped.origen,
  ped.total,
  ped.notas,
  ped.digits,
    ped.phone_number,
    (ped.fecha::time = '00:00:00') AS fecha_medianoche,
  COALESCE(flags.tiene_inbound, FALSE) AS tiene_inbound,
  COALESCE(flags.en_ventana_24h, FALSE) AS en_ventana_24h,
  COALESCE(flags.en_ventana_48h, FALSE) AS en_ventana_48h,
  COALESCE(flags.en_ventana_7d, FALSE) AS en_ventana_7d
FROM ped
LEFT JOIN flags ON flags.id = ped.id
ORDER BY ped.fecha_ts, ped.id;
"""

SQL_CONTACTS = """
SELECT
  cl.id AS client_id,
  cl.codigo,
  cl.razon_social,
  cl.nombre,
  cl.nombre_de_pila,
  cl.phone_number,
  cl.whatsapp_nombre,
  cl.whatsapp_estado::text AS whatsapp_estado,
  cl.email,
  cl.direccion,
  cl.cuit,
  cl.etiqueta,
  cl.client_rfm_class,
  cl.activo_ai,
  cl.dia_de_visita::text AS dia_de_visita,
  cl.dia_de_entrega::text AS dia_de_entrega,
  cl.metadata,
  pv.vendedor,
  v.nombre AS vendedor_nombre,
  gz.name AS zona,
  pv.geo_zone_id
FROM del_corro.clients cl
LEFT JOIN del_corro.puntos_venta pv ON pv.id = cl.pdv_id
LEFT JOIN del_corro.geo_zones gz ON gz.id = pv.geo_zone_id
LEFT JOIN del_corro.vendedores v ON v.id = pv.vendedor_id
WHERE cl.id = ANY($1::int[]);
"""

SQL_ITEMS = """
SELECT
  pedido_id,
  product_code,
  nombre,
  cantidad_solicitada
FROM del_corro.items_pedido
WHERE pedido_id = ANY($1::int[])
ORDER BY pedido_id, id;
"""

SQL_MESSAGES = """
SELECT digits, created_at, msg_type, content
FROM (
  SELECT
    right(regexp_replace(COALESCE(session_id, ''), '[^0-9]', '', 'g'), 10) AS digits,
    created_at,
    COALESCE(message->>'type', 'unknown') AS msg_type,
    COALESCE(message->>'content', message::text) AS content
  FROM del_corro.n8n_chat_histories
  WHERE length(regexp_replace(COALESCE(session_id, ''), '[^0-9]', '', 'g')) >= 10
    AND right(regexp_replace(COALESCE(session_id, ''), '[^0-9]', '', 'g'), 10) = ANY($1::text[])
  UNION ALL
  SELECT
    right(regexp_replace(COALESCE(c.session_id, ''), '[^0-9]', '', 'g'), 10) AS digits,
    ce.created_at,
    ce.event_type AS msg_type,
    COALESCE(ce.event_payload->>'text', ce.event_payload->>'transcription', ce.event_payload::text) AS content
  FROM core.conversations c
  JOIN core.conversation_events ce ON ce.conversation_id = c.id
  WHERE c.schema_name = 'del_corro'
    AND ce.event_type IN (
      'user_message', 'assistant_message', 'outbound_message', 'catalog_search_snapshot'
    )
    AND length(regexp_replace(COALESCE(c.session_id, ''), '[^0-9]', '', 'g')) >= 10
    AND right(regexp_replace(COALESCE(c.session_id, ''), '[^0-9]', '', 'g'), 10) = ANY($1::text[])
) m
ORDER BY digits, created_at;
"""

SQL_HSM = """
WITH envios AS (
  SELECT
    ep.id,
    ep.session_id,
    right(regexp_replace(COALESCE(ep.session_id, ''), '[^0-9]', '', 'g'), 10) AS digits,
    ep.template_name,
    ep.created_at,
    LEAST(
      ep.created_at + INTERVAL '48 hours',
      COALESCE(
        (
          SELECT MIN(ep2.created_at)
          FROM del_corro.envios_plantillas ep2
          WHERE ep2.session_id = ep.session_id
            AND ep2.created_at > ep.created_at
        ),
        ep.created_at + INTERVAL '48 hours'
      )
    ) AS fin_ventana
  FROM del_corro.envios_plantillas ep
  WHERE length(regexp_replace(COALESCE(ep.session_id, ''), '[^0-9]', '', 'g')) >= 10
),
replies AS (
  SELECT
    e.id AS envio_id,
    e.session_id,
    e.digits,
    e.template_name,
    e.created_at AS envio_at,
    MIN(h.created_at) AS reply_at
  FROM envios e
  JOIN del_corro.n8n_chat_histories h
    ON h.session_id = e.session_id
   AND (h.message->>'type') IN ('human', 'user')
   AND h.created_at > e.created_at
   AND h.created_at < e.fin_ventana
  GROUP BY e.id, e.session_id, e.digits, e.template_name, e.created_at
  UNION
  SELECT
    e.id,
    e.session_id,
    e.digits,
    e.template_name,
    e.created_at,
    MIN(ce.created_at)
  FROM envios e
  JOIN core.conversations c
    ON c.schema_name = 'del_corro'
   AND c.session_id = e.session_id
  JOIN core.conversation_events ce
    ON ce.conversation_id = c.id
   AND ce.event_type = 'user_message'
   AND ce.created_at > e.created_at
   AND ce.created_at < e.fin_ventana
  GROUP BY e.id, e.session_id, e.digits, e.template_name, e.created_at
)
SELECT DISTINCT ON (r.envio_id)
  r.envio_id,
  r.digits,
  r.session_id,
  r.template_name,
  r.envio_at,
  r.reply_at,
  cl.id AS client_id,
  cl.razon_social,
  cl.nombre
FROM replies r
LEFT JOIN del_corro.clients cl
  ON right(regexp_replace(COALESCE(cl.phone_number, ''), '[^0-9]', '', 'g'), 10) = r.digits
ORDER BY r.envio_id, r.reply_at;
"""

SQL_TICKETS = """
SELECT
  id,
  created_at,
  description,
  client_id,
  status,
  closed_at
FROM del_corro.ia_tickets;
"""

SQL_BASE_COUNTS = """
SELECT
  (SELECT COUNT(*) FROM del_corro.clients) AS n_clients,
  (SELECT COUNT(DISTINCT session_id) FROM del_corro.envios_plantillas) AS n_envios_sessions,
  (SELECT COUNT(*) FROM del_corro.envios_plantillas) AS n_envios,
  (
    SELECT COUNT(DISTINCT ep.session_id)
    FROM del_corro.envios_plantillas ep
    WHERE EXISTS (
      SELECT 1
      FROM del_corro.n8n_chat_histories h
      WHERE h.session_id = ep.session_id
        AND (h.message->>'type') IN ('human', 'user')
        AND h.created_at > ep.created_at
        AND h.created_at < ep.created_at + INTERVAL '48 hours'
    )
  ) AS n_hsm_sessions_n8n_48h;
"""


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _in_window(msg_at: datetime, order_at: datetime, before_h: int = 48, after_h: int = 48) -> bool:
    return (order_at - timedelta(hours=before_h)) <= msg_at < (order_at + timedelta(hours=after_h))


def classify_canal(origen: str, corpus: str) -> tuple[str, bool]:
    has_url = bool(CATALOG_URL_RE.search(corpus or ""))
    if (origen or "").lower() == "tienda" or has_url:
        return "tienda", has_url
    return "chat", has_url


def pick_qa_sample(attributed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tienda = [r for r in attributed if r["canal"] == "tienda"]
    chat = [r for r in attributed if r["canal"] == "chat"]
    chat_sorted = sorted(chat, key=lambda r: float(r.get("match_ratio") or 0), reverse=True)
    high = chat_sorted[:5]
    low = list(reversed(chat_sorted[-5:])) if len(chat_sorted) >= 5 else chat_sorted
    # Deterministic: sort tienda by pedido_id
    tienda_pick = sorted(tienda, key=lambda r: int(r["pedido_id"]))[:5]
    sample = []
    for row in tienda_pick:
        sample.append({**row, "qa_bucket": "tienda"})
    for row in high:
        sample.append({**row, "qa_bucket": "chat_match_alto"})
    for row in low:
        if row["pedido_id"] not in {s["pedido_id"] for s in sample}:
            sample.append({**row, "qa_bucket": "chat_match_bajo"})
    return sample[:15]


async def load_rows(conn: asyncpg.Connection) -> dict[str, Any]:
    print("[*] pedidos + inbound flags")
    pedidos = [dict(r) for r in await conn.fetch(SQL_PEDIDOS)]
    print(f"    n_pedidos={len(pedidos)}")

    attributed = [
        p
        for p in pedidos
        if p.get("en_ventana_48h") and not p.get("fecha_medianoche") and str(p.get("origen") or "") != "erp"
    ]
    attr_ids = [int(p["pedido_id"]) for p in attributed]
    attr_clients = sorted({int(p["cliente_id"]) for p in attributed})
    attr_digits = sorted({p["digits"] for p in attributed if p.get("digits")})

    print("[*] contactos / items / mensajes / hsm / tickets")
    contacts = [dict(r) for r in await conn.fetch(SQL_CONTACTS, attr_clients)] if attr_clients else []
    items = [dict(r) for r in await conn.fetch(SQL_ITEMS, attr_ids)] if attr_ids else []
    messages = [dict(r) for r in await conn.fetch(SQL_MESSAGES, attr_digits)] if attr_digits else []
    hsm = [dict(r) for r in await conn.fetch(SQL_HSM)]
    tickets = [dict(r) for r in await conn.fetch(SQL_TICKETS)]
    base = dict(await conn.fetchrow(SQL_BASE_COUNTS))
    return {
        "pedidos": pedidos,
        "attributed": attributed,
        "contacts": contacts,
        "items": items,
        "messages": messages,
        "hsm": hsm,
        "tickets": tickets,
        "base": base,
    }


def index_items(items: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in items:
        pid = int(row["pedido_id"])
        out[pid].append(row)
    return out


def index_messages(messages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in messages:
        out[str(row["digits"])].append(row)
    return out


def corpus_for_order(msgs: list[dict[str, Any]], order_at: datetime) -> tuple[str, str, bool]:
    chunks: list[str] = []
    human_chunks: list[str] = []
    has_snapshot = False
    seen: set[tuple] = set()
    for msg in msgs:
        created = parse_ts(msg.get("created_at"))
        if created is None or order_at is None:
            continue
        if not _in_window(created, order_at):
            continue
        text = message_text(msg.get("content"))
        msg_type = str(msg.get("msg_type") or "")
        dedupe_key = (int(created.timestamp()) // 5, msg_type, text[:120])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        if msg_type == "catalog_search_snapshot":
            has_snapshot = True
        chunks.append(text)
        if msg_type in {"human", "user", "user_message"}:
            human_chunks.append(text)
    return " \n ".join(chunks), " \n ".join(human_chunks), has_snapshot


def build_fase0(pedidos: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for ped in pedidos:
        inbound = bool(ped.get("tiene_inbound"))
        win48 = bool(ped.get("en_ventana_48h"))
        origen = str(ped.get("origen") or "")
        midnight = bool(ped.get("fecha_medianoche"))
        atribuido = win48 and origen != "erp" and not midnight
        rows.append(
            {
                "pedido_id": ped["pedido_id"],
                "cliente_id": ped["cliente_id"],
                "fecha": iso(ped.get("fecha_ts") or ped.get("fecha")),
                "estado": ped.get("estado") or "",
                "origen": origen,
                "total": ped.get("total") if ped.get("total") is not None else "",
                "tiene_inbound": csv_bool(inbound),
                "fecha_medianoche": csv_bool(midnight),
                "en_ventana_24h": csv_bool(bool(ped.get("en_ventana_24h"))),
                "en_ventana_48h": csv_bool(win48),
                "en_ventana_7d": csv_bool(bool(ped.get("en_ventana_7d"))),
                "atribuido_48h": csv_bool(atribuido),
                "motivo_exclusion": motivo_exclusion(
                    origen=origen,
                    tiene_inbound=inbound,
                    en_ventana=win48,
                    fecha_medianoche=midnight,
                ),
            }
        )

    resumen_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "n": 0,
            "n_con_inbound": 0,
            "n_atribuidos_48h": 0,
            "n_abiertos": 0,
            "n_cerrados": 0,
        }
    )
    for ped in pedidos:
        origen = str(ped.get("origen") or "(none)")
        bucket = resumen_map[origen]
        bucket["n"] += 1
        if ped.get("tiene_inbound"):
            bucket["n_con_inbound"] += 1
        if ped.get("en_ventana_48h") and not ped.get("fecha_medianoche"):
            bucket["n_atribuidos_48h"] += 1
            grupo = estado_grupo(ped.get("estado"))
            if grupo == "abierto":
                bucket["n_abiertos"] += 1
            elif grupo == "cerrado":
                bucket["n_cerrados"] += 1
    resumen = [
        {"origen": origen, **counts}
        for origen, counts in sorted(resumen_map.items(), key=lambda kv: -kv[1]["n"])
    ]

    sensibilidad = []
    for label, flag in (("24h", "en_ventana_24h"), ("48h", "en_ventana_48h"), ("7d", "en_ventana_7d")):
        subset = [
            p
            for p in pedidos
            if p.get(flag) and str(p.get("origen") or "") != "erp" and not p.get("fecha_medianoche")
        ]
        clientes = {p["cliente_id"] for p in subset}
        sensibilidad.append(
            {
                "ventana": label,
                "n_pedidos": len(subset),
                "n_cerrados": sum(1 for p in subset if estado_grupo(p.get("estado")) == "cerrado"),
                "n_abiertos": sum(1 for p in subset if estado_grupo(p.get("estado")) == "abierto"),
                "n_clientes": len(clientes),
                "n_tienda_origen": sum(1 for p in subset if str(p.get("origen") or "") == "tienda"),
            }
        )
    return rows, resumen, sensibilidad


def enrich_attributed(
    attributed: list[dict[str, Any]],
    items_by_pid: dict[int, list[dict[str, Any]]],
    msgs_by_digits: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for ped in attributed:
        order_at = parse_ts(ped.get("fecha_ts") or ped.get("fecha"))
        if order_at is None:
            continue
        digits = str(ped.get("digits") or "")
        msgs = msgs_by_digits.get(digits, [])
        corpus, human_corpus, has_snapshot = corpus_for_order(msgs, order_at)
        canal, has_url = classify_canal(str(ped.get("origen") or ""), corpus)
        lines = items_by_pid.get(int(ped["pedido_id"]), [])
        if canal == "tienda":
            ratio, matched, unmatched = 0.0, [], []
            match_na = "catalogo_ui"
        else:
            # Solo texto del cliente: el listado del agente infla match_ratio.
            ratio, matched, unmatched = match_ratio_for_lines(lines, human_corpus)
            match_na = ""
        grupo = estado_grupo(ped.get("estado"))
        enriched.append(
            {
                **ped,
                "canal": canal,
                "tiene_url_catalogo": has_url,
                "tiene_catalog_search": has_snapshot,
                "estado_grupo": grupo,
                "n_items": len(lines),
                "match_ratio": round(ratio, 4),
                "match_na": match_na,
                "skus_matched": "|".join(matched),
                "skus_unmatched": "|".join(unmatched),
                "excerpt_humano": human_corpus[:500].replace("\n", " ").strip(),
                "n_matched": len(matched),
            }
        )
    return enriched


def build_fase1(
    enriched: list[dict[str, Any]],
    contacts: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    pedidos_rows = []
    for row in enriched:
        pedidos_rows.append(
            {
                "pedido_id": row["pedido_id"],
                "cliente_id": row["cliente_id"],
                "fecha": iso(row.get("fecha_ts") or row.get("fecha")),
                "estado": row.get("estado") or "",
                "estado_grupo": row["estado_grupo"],
                "origen": row.get("origen") or "",
                "canal": row["canal"],
                "total": row.get("total") if row.get("total") is not None else "",
                "n_items": row["n_items"],
                "tiene_url_catalogo": csv_bool(bool(row["tiene_url_catalogo"])),
                "tiene_catalog_search": csv_bool(bool(row["tiene_catalog_search"])),
                "match_ratio": row["match_ratio"] if row["match_na"] == "" else "",
                "match_na": row["match_na"],
                "phone_number": row.get("phone_number") or "",
            }
        )

    abiertos = [r for r in pedidos_rows if r["estado_grupo"] == "abierto"]
    cerrados = [r for r in pedidos_rows if r["estado_grupo"] == "cerrado"]

    contact_rows = []
    for cl in contacts:
        contact_rows.append(
            {
                "client_id": cl["client_id"],
                "codigo": cl.get("codigo") if cl.get("codigo") is not None else "",
                "razon_social": cl.get("razon_social") or "",
                "nombre": cl.get("nombre") or "",
                "nombre_de_pila": cl.get("nombre_de_pila") or "",
                "phone_number": cl.get("phone_number") or "",
                "whatsapp_nombre": cl.get("whatsapp_nombre") or "",
                "whatsapp_estado": cl.get("whatsapp_estado") or "",
                "email": cl.get("email") or "",
                "direccion": cl.get("direccion") or "",
                "cuit": cl.get("cuit") or "",
                "etiqueta": cl.get("etiqueta") or "",
                "client_rfm_class": cl.get("client_rfm_class") or "",
                "activo_ai": csv_bool(bool(cl.get("activo_ai"))),
                "vendedor": cl.get("vendedor_nombre") or cl.get("vendedor") or "",
                "zona": cl.get("zona") or "",
                "dia_de_visita": cl.get("dia_de_visita") or "",
                "dia_de_entrega": cl.get("dia_de_entrega") or "",
                "metadata_keys": metadata_keys(cl.get("metadata")),
            }
        )

    by_client: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        by_client[int(row["cliente_id"])].append(row)

    contacts_by_id = {int(c["client_id"]): c for c in contacts}
    repetidores = []
    for client_id, orders in by_client.items():
        closed = [o for o in orders if o["estado_grupo"] == "cerrado"]
        if len(closed) < 2:
            continue
        closed_sorted = sorted(closed, key=lambda o: parse_ts(o.get("fecha_ts")) or datetime.min.replace(tzinfo=timezone.utc))
        canales = sorted({o["canal"] for o in closed_sorted})
        totals = [float(o["total"]) for o in closed_sorted if o.get("total") is not None]
        cl = contacts_by_id.get(client_id, {})
        repetidores.append(
            {
                "client_id": client_id,
                "razon_social": cl.get("razon_social") or cl.get("nombre") or "",
                "n_cerrados": len(closed_sorted),
                "n_abiertos": sum(1 for o in orders if o["estado_grupo"] == "abierto"),
                "primer_pedido": iso(closed_sorted[0].get("fecha_ts")),
                "ultimo_pedido": iso(closed_sorted[-1].get("fecha_ts")),
                "total_acumulado": round(sum(totals), 2) if totals else "",
                "canal_mixto": csv_bool(len(canales) > 1),
                "canales": "|".join(canales),
            }
        )
    repetidores.sort(key=lambda r: (-int(r["n_cerrados"]), str(r["razon_social"])))

    productos = []
    for row in enriched:
        productos.append(
            {
                "pedido_id": row["pedido_id"],
                "cliente_id": row["cliente_id"],
                "canal": row["canal"],
                "n_lineas": row["n_items"],
                "n_matched": row["n_matched"] if row["match_na"] == "" else "",
                "match_ratio": row["match_ratio"] if row["match_na"] == "" else "",
                "match_na": row["match_na"],
                "skus_matched": row["skus_matched"],
                "skus_unmatched": row["skus_unmatched"],
                "excerpt_humano": row["excerpt_humano"],
            }
        )

    qa = pick_qa_sample(enriched)
    qa_rows = []
    for row in qa:
        qa_rows.append(
            {
                "qa_bucket": row["qa_bucket"],
                "pedido_id": row["pedido_id"],
                "cliente_id": row["cliente_id"],
                "fecha": iso(row.get("fecha_ts")),
                "canal": row["canal"],
                "origen": row.get("origen") or "",
                "estado": row.get("estado") or "",
                "match_ratio": row["match_ratio"] if row["match_na"] == "" else "",
                "match_na": row["match_na"],
                "n_items": row["n_items"],
                "tiene_url_catalogo": csv_bool(bool(row["tiene_url_catalogo"])),
                "excerpt_humano": row["excerpt_humano"],
                "phone_number": row.get("phone_number") or "",
            }
        )

    return {
        "pedidos": pedidos_rows,
        "abiertos": abiertos,
        "cerrados": cerrados,
        "contactos": contact_rows,
        "repetidores": repetidores,
        "productos": productos,
        "qa": qa_rows,
    }


def ticket_client_ids(tickets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in tickets:
        raw = str(t.get("client_id") or "").strip()
        if raw:
            by[raw].append(t)
    return by


def frustration_hits(msgs: list[dict[str, Any]]) -> int:
    n = 0
    for msg in msgs:
        msg_type = str(msg.get("msg_type") or "")
        if msg_type not in {"human", "user", "user_message"}:
            continue
        if FRUSTRATION_RE.search(message_text(msg.get("content"))):
            n += 1
    return n


def build_fase2(
    hsm: list[dict[str, Any]],
    enriched: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tickets: list[dict[str, Any]],
    contacts: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    msgs_by_digits = index_messages(messages)
    orders_by_client: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        orders_by_client[int(row["cliente_id"])].append(row)

    tickets_by_client = ticket_client_ids(tickets)
    contacts_by_id = {int(c["client_id"]): c for c in contacts}

    by_digits: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in hsm:
        by_digits[str(row["digits"])].append(row)

    replied_rows = []
    cerrado_rows = []
    abierto_rows = []
    sin_pedido_rows = []
    problemas = []

    for digits, envios in sorted(by_digits.items()):
        envios_sorted = sorted(envios, key=lambda r: parse_ts(r.get("envio_at")) or datetime.min.replace(tzinfo=timezone.utc))
        first = envios_sorted[0]
        last = envios_sorted[-1]
        client_id = first.get("client_id")
        client_id_int = int(client_id) if client_id is not None else None
        orders = orders_by_client.get(client_id_int, []) if client_id_int else []
        has_closed = any(o["estado_grupo"] == "cerrado" for o in orders)
        has_open = any(o["estado_grupo"] == "abierto" for o in orders)
        if has_closed:
            conversion = "cerrado"
        elif has_open:
            conversion = "abierto"
        else:
            conversion = "sin_pedido"

        tix = []
        if client_id_int is not None:
            tix = tickets_by_client.get(str(client_id_int), [])
        n_frust = frustration_hits(msgs_by_digits.get(digits, []))
        abandono = has_open and not has_closed
        had_problem = bool(tix) or n_frust > 0 or abandono or conversion == "sin_pedido"
        problem_tags = []
        if abandono:
            problem_tags.append("abandono_carrito")
        if tix:
            problem_tags.append("ticket")
        if n_frust:
            problem_tags.append("frustracion")
        if conversion == "sin_pedido":
            problem_tags.append("respuesta_sin_pedido")

        cl = contacts_by_id.get(client_id_int or -1, {})
        razon = first.get("razon_social") or first.get("nombre") or cl.get("razon_social") or ""
        row = {
            "client_id": client_id_int if client_id_int is not None else "",
            "phone_number": first.get("session_id") or "",
            "razon_social": razon,
            "n_envios_con_respuesta": len(envios_sorted),
            "first_reply_at": iso(first.get("reply_at")),
            "last_reply_at": iso(last.get("reply_at")),
            "first_template": first.get("template_name") or "",
            "last_template": last.get("template_name") or "",
            "conversion_best": conversion,
            "n_pedidos_atribuidos": len(orders),
            "n_cerrados": sum(1 for o in orders if o["estado_grupo"] == "cerrado"),
            "n_abiertos": sum(1 for o in orders if o["estado_grupo"] == "abierto"),
            "tuvo_problema": csv_bool(had_problem),
            "n_tickets": len(tix),
            "n_frustracion": n_frust,
            "abandono_carrito": csv_bool(abandono),
        }
        replied_rows.append(row)
        if conversion == "cerrado":
            cerrado_rows.append(row)
        elif conversion == "abierto":
            abierto_rows.append(row)
        else:
            sin_pedido_rows.append(row)
        if had_problem and conversion != "cerrado":
            problemas.append(
                {
                    **row,
                    "tags": "|".join(problem_tags),
                    "ticket_status": "|".join(
                        sorted({str(t.get("status") or "") for t in tix if t.get("status")})
                    ),
                }
            )

    return {
        "replied": replied_rows,
        "cerrado": cerrado_rows,
        "abierto": abierto_rows,
        "sin_pedido": sin_pedido_rows,
        "problemas": problemas,
    }


def build_resumen(
    base: dict[str, Any],
    pedidos: list[dict[str, Any]],
    fase1: dict[str, list[dict[str, Any]]],
    fase2: dict[str, list[dict[str, Any]]],
    sensibilidad: list[dict[str, Any]],
) -> dict[str, Any]:
    enriched_like = fase1["pedidos"]
    n_chat = sum(1 for r in enriched_like if r["canal"] == "chat")
    n_tienda = sum(1 for r in enriched_like if r["canal"] == "tienda")
    n_clients_attr = len({r["cliente_id"] for r in enriched_like})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema": SCHEMA,
        "n_clients": int(base.get("n_clients") or 0),
        "n_envios": int(base.get("n_envios") or 0),
        "n_envios_sessions": int(base.get("n_envios_sessions") or 0),
        "n_pedidos_total": len(pedidos),
        "n_pedidos_atribuidos_48h": len(enriched_like),
        "n_cerrados": len(fase1["cerrados"]),
        "n_abiertos": len(fase1["abiertos"]),
        "n_clientes_atribuidos": n_clients_attr,
        "n_canal_chat": n_chat,
        "n_canal_tienda": n_tienda,
        "n_repetidores": len(fase1["repetidores"]),
        "n_hsm_respondieron": len(fase2["replied"]),
        "n_hsm_sessions_n8n_48h": int(base.get("n_hsm_sessions_n8n_48h") or 0),
        "n_hsm_cerrado": len(fase2["cerrado"]),
        "n_hsm_abierto": len(fase2["abierto"]),
        "n_hsm_sin_pedido": len(fase2["sin_pedido"]),
        "n_hsm_problemas": len(fase2["problemas"]),
        "sensibilidad": sensibilidad,
        "nota_metadata": "clients.metadata.agent_journey no se escribe en esta entrega",
    }


async def run(cmd: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pool = await asyncpg.create_pool(
        db_url(),
        min_size=1,
        max_size=2,
        statement_cache_size=0,
    )
    try:
        async with pool.acquire() as conn:
            data = await load_rows(conn)
    finally:
        await pool.close()

    pedidos = data["pedidos"]
    fase0_rows, resumen_origen, sensibilidad = build_fase0(pedidos)
    items_by_pid = index_items(data["items"])
    msgs_by_digits = index_messages(data["messages"])
    enriched = enrich_attributed(data["attributed"], items_by_pid, msgs_by_digits)
    fase1 = build_fase1(enriched, data["contacts"])
    fase2 = build_fase2(data["hsm"], enriched, data["messages"], data["tickets"], data["contacts"])
    resumen = build_resumen(data["base"], pedidos, fase1, fase2, sensibilidad)

    do_all = cmd == "all"
    if do_all or cmd == "fase0":
        write_csv(
            OUT / "00_pedidos_fuera_agente.csv",
            fase0_rows,
            [
                "pedido_id",
                "cliente_id",
                "fecha",
                "estado",
                "origen",
                "total",
                "tiene_inbound",
                "fecha_medianoche",
                "en_ventana_24h",
                "en_ventana_48h",
                "en_ventana_7d",
                "atribuido_48h",
                "motivo_exclusion",
            ],
        )
        write_csv(
            OUT / "00_resumen_origen.csv",
            resumen_origen,
            ["origen", "n", "n_con_inbound", "n_atribuidos_48h", "n_abiertos", "n_cerrados"],
        )
        write_csv(
            OUT / "00_sensibilidad_ventana.csv",
            sensibilidad,
            ["ventana", "n_pedidos", "n_cerrados", "n_abiertos", "n_clientes", "n_tienda_origen"],
        )
        print(f"[ok] fase0 → {OUT}")

    if do_all or cmd == "fase1":
        write_csv(
            OUT / "01_pedidos_agente.csv",
            fase1["pedidos"],
            [
                "pedido_id",
                "cliente_id",
                "fecha",
                "estado",
                "estado_grupo",
                "origen",
                "canal",
                "total",
                "n_items",
                "tiene_url_catalogo",
                "tiene_catalog_search",
                "match_ratio",
                "match_na",
                "phone_number",
            ],
        )
        write_csv(
            OUT / "01_pedidos_abiertos.csv",
            fase1["abiertos"],
            [
                "pedido_id",
                "cliente_id",
                "fecha",
                "estado",
                "origen",
                "canal",
                "total",
                "n_items",
                "phone_number",
            ],
        )
        write_csv(
            OUT / "01_pedidos_cerrados.csv",
            fase1["cerrados"],
            [
                "pedido_id",
                "cliente_id",
                "fecha",
                "estado",
                "origen",
                "canal",
                "total",
                "n_items",
                "phone_number",
            ],
        )
        write_csv(
            OUT / "01_contactos.csv",
            fase1["contactos"],
            [
                "client_id",
                "codigo",
                "razon_social",
                "nombre",
                "nombre_de_pila",
                "phone_number",
                "whatsapp_nombre",
                "whatsapp_estado",
                "email",
                "direccion",
                "cuit",
                "etiqueta",
                "client_rfm_class",
                "activo_ai",
                "vendedor",
                "zona",
                "dia_de_visita",
                "dia_de_entrega",
                "metadata_keys",
            ],
        )
        write_csv(
            OUT / "01_repetidores.csv",
            fase1["repetidores"],
            [
                "client_id",
                "razon_social",
                "n_cerrados",
                "n_abiertos",
                "primer_pedido",
                "ultimo_pedido",
                "total_acumulado",
                "canal_mixto",
                "canales",
            ],
        )
        write_csv(
            OUT / "01_productos_vs_mensajes.csv",
            fase1["productos"],
            [
                "pedido_id",
                "cliente_id",
                "canal",
                "n_lineas",
                "n_matched",
                "match_ratio",
                "match_na",
                "skus_matched",
                "skus_unmatched",
                "excerpt_humano",
            ],
        )
        write_csv(
            OUT / "01_qa_sample.csv",
            fase1["qa"],
            [
                "qa_bucket",
                "pedido_id",
                "cliente_id",
                "fecha",
                "canal",
                "origen",
                "estado",
                "match_ratio",
                "match_na",
                "n_items",
                "tiene_url_catalogo",
                "excerpt_humano",
                "phone_number",
            ],
        )
        print(f"[ok] fase1 pedidos={len(fase1['pedidos'])} repetidores={len(fase1['repetidores'])}")

    if do_all or cmd == "fase2":
        fields_reply = [
            "client_id",
            "phone_number",
            "razon_social",
            "n_envios_con_respuesta",
            "first_reply_at",
            "last_reply_at",
            "first_template",
            "last_template",
            "conversion_best",
            "n_pedidos_atribuidos",
            "n_cerrados",
            "n_abiertos",
            "tuvo_problema",
            "n_tickets",
            "n_frustracion",
            "abandono_carrito",
        ]
        write_csv(OUT / "02_respondieron_post_hsm.csv", fase2["replied"], fields_reply)
        write_csv(OUT / "02_reply_cerrado.csv", fase2["cerrado"], fields_reply)
        write_csv(OUT / "02_reply_abierto.csv", fase2["abierto"], fields_reply)
        write_csv(OUT / "02_reply_sin_pedido.csv", fase2["sin_pedido"], fields_reply)
        write_csv(
            OUT / "02_problemas.csv",
            fase2["problemas"],
            fields_reply + ["tags", "ticket_status"],
        )
        print(
            f"[ok] fase2 respondieron={len(fase2['replied'])} "
            f"cerrado={len(fase2['cerrado'])} abierto={len(fase2['abierto'])} "
            f"sin_pedido={len(fase2['sin_pedido'])}"
        )

    (OUT / "99_resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in resumen.items() if k != "sensibilidad"}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Funnel agente Campi (del_corro)")
    parser.add_argument(
        "cmd",
        nargs="?",
        default="all",
        choices=["all", "fase0", "fase1", "fase2"],
    )
    args = parser.parse_args()
    return asyncio.run(run(args.cmd))


if __name__ == "__main__":
    raise SystemExit(main())
