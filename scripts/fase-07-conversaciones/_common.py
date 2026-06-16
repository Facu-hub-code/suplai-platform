from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import yaml


BASE_DIR = Path("implementacion")
OUTPUT_DIR_NAME = "outputs"
DEFAULT_ACTIVE_CLIENTS = 12
DEFAULT_COMPLAINT_CLIENTS = 4
DEFAULT_HISTORIC_MIN_MESSAGES = 3
DEFAULT_HISTORIC_MAX_MESSAGES = 4
DEFAULT_ACTIVE_MIN_MESSAGES = 4
DEFAULT_ACTIVE_MAX_MESSAGES = 5
DEFAULT_COMPLAINT_MIN_MESSAGES = 5
DEFAULT_COMPLAINT_MAX_MESSAGES = 5
DEFAULT_HUMAN_REPLY_SECONDS = (45, 120)
DEFAULT_AI_REPLY_SECONDS = (30, 90)
DEFAULT_ARCHIVE_DAYS = (1, 2)
DEFAULT_ACTIVE_HOURS = (0, 12)


def sanitize_schema_name(schema: str) -> str:
    if not schema or not all(c.isalnum() or c == "_" for c in schema):
        raise ValueError(f"Nombre de esquema invalido: {schema!r}")
    return schema


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"No se encontro el archivo CSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def seed_from_text(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def stable_rng(*parts: Any) -> random.Random:
    joined = "|".join("" if p is None else str(p) for p in parts)
    return random.Random(seed_from_text(joined))


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def tenant_paths(schema: str) -> dict[str, Path]:
    base = BASE_DIR / schema
    return {
        "base": base,
        "manifest": base / "manifest.yaml",
        "config": base / "config.json",
        "outputs": base / OUTPUT_DIR_NAME,
    }


def load_tenant_context(schema: str) -> dict[str, Any]:
    schema = sanitize_schema_name(schema)
    paths = tenant_paths(schema)
    manifest = read_yaml(paths["manifest"])
    config = read_json(paths["config"])
    phase_cfg = config.get("fase_07", {}) if isinstance(config, dict) else {}
    return {
        "schema": schema,
        "paths": paths,
        "manifest": manifest,
        "config": config,
        "fase_07": phase_cfg if isinstance(phase_cfg, dict) else {},
    }


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def parse_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value)))
    except Exception:
        return default


def parse_dt(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Fecha vacia")
    if "T" in raw:
        return datetime.fromisoformat(raw)
    if len(raw) == 10:
        return datetime.fromisoformat(f"{raw} 00:00:00")
    return datetime.fromisoformat(raw)


def format_dt(dt: datetime) -> str:
    return dt.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def load_clients(schema: str) -> list[dict[str, Any]]:
    paths = tenant_paths(schema)
    phase4 = read_csv_rows(paths["outputs"] / "phase-04-clientes.csv")
    flags_path = paths["outputs"] / "phase-05-clientes-flags.csv"
    flags = read_csv_rows(flags_path) if flags_path.exists() else []
    flags_by_phone = {row.get("phone_number", ""): row for row in flags if row.get("phone_number")}

    clients: list[dict[str, Any]] = []
    for row in phase4:
        phone = row.get("phone_number", "")
        flag = flags_by_phone.get(phone, {})
        clients.append(
            {
                "cliente_phone": phone,
                "cliente_codigo": parse_int(flag.get("codigo_erp", row.get("codigo", 0)), 0),
                "cliente_razon_social": row.get("razon_social", ""),
                "cliente_nombre": row.get("nombre") or row.get("nombre_contacto") or row.get("razon_social", ""),
                "lista_precios_id": parse_int(row.get("lista_precios_id"), 1),
                "vendedor_nombre": row.get("vendedor_nombre", ""),
                "zona_idx": parse_int(row.get("zona_idx"), 0),
                "vendedor_idx": parse_int(row.get("vendedor_idx"), 0),
                "is_prospect": parse_bool(flag.get("is_prospect", "false")),
                "whatsapp_estado": flag.get("whatsapp_estado", ""),
                "whatsapp_validado_at": flag.get("whatsapp_validado_at", ""),
            }
        )
    clients.sort(key=lambda c: (c["cliente_codigo"], c["cliente_phone"]))
    return clients


def load_orders(schema: str) -> list[dict[str, Any]]:
    rows = read_csv_rows(tenant_paths(schema)["outputs"] / "phase-06-pedidos.csv")
    orders: list[dict[str, Any]] = []
    for row in rows:
        orders.append(
            {
                "pedido_ref": row.get("pedido_ref", ""),
                "cliente_phone": row.get("cliente_phone", ""),
                "cliente_codigo": parse_int(row.get("cliente_codigo"), 0),
                "cliente_razon_social": row.get("cliente_razon_social", ""),
                "fecha": parse_dt(row.get("fecha", "2026-01-01 00:00:00")),
                "estado": row.get("estado", ""),
                "total": row.get("total", "0"),
                "notas": row.get("notas", ""),
                "is_mock": parse_bool(row.get("is_mock", "true")),
                "es_pedido_abierto": parse_bool(row.get("es_pedido_abierto", "false")),
                "lista_precios_id": parse_int(row.get("lista_precios_id"), 0),
            }
        )
    return orders


def load_items(schema: str) -> list[dict[str, Any]]:
    rows = read_csv_rows(tenant_paths(schema)["outputs"] / "phase-06-items-pedido.csv")
    items: list[dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "pedido_ref": row.get("pedido_ref", ""),
                "cliente_phone": row.get("cliente_phone", ""),
                "cliente_codigo": parse_int(row.get("cliente_codigo"), 0),
                "product_code": row.get("product_code", ""),
                "nombre": row.get("nombre", ""),
                "cantidad_solicitada": parse_int(row.get("cantidad_solicitada"), 1),
                "precio_unitario": row.get("precio_unitario", "0"),
                "lista_precios_id": parse_int(row.get("lista_precios_id"), 0),
                "notas": row.get("notas", ""),
                "is_mock": parse_bool(row.get("is_mock", "true")),
                "es_pedido_abierto": parse_bool(row.get("es_pedido_abierto", "false")),
                "promo_aplicada": parse_bool(row.get("promo_aplicada", "false")),
            }
        )
    return items


def group_items_by_order(items: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[item["pedido_ref"]].append(item)
    return grouped


def split_clients_for_live_feed(clients: list[dict[str, Any]], orders: list[dict[str, Any]], cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active_count = parse_int(cfg.get("clientes_live_feed"), DEFAULT_ACTIVE_CLIENTS)
    active_count = max(10, min(active_count, len(clients)))
    complaint_count = parse_int(cfg.get("clientes_quejas"), DEFAULT_COMPLAINT_CLIENTS)
    complaint_count = max(3, min(complaint_count, active_count))

    open_client_phones = []
    seen = set()
    for order in orders:
        if order["es_pedido_abierto"] and order["cliente_phone"] not in seen:
            open_client_phones.append(order["cliente_phone"])
            seen.add(order["cliente_phone"])

    priority = []
    by_phone = {c["cliente_phone"]: c for c in clients}
    for phone in open_client_phones:
        client = by_phone.get(phone)
        if client:
            priority.append(client)

    for client in clients:
        if client["cliente_phone"] not in seen:
            priority.append(client)
            seen.add(client["cliente_phone"])

    active_clients = priority[:active_count]
    complaint_clients = active_clients[:complaint_count]
    return active_clients, complaint_clients


def latest_order_for_client(orders: list[dict[str, Any]], client_phone: str, open_only: bool = False) -> dict[str, Any] | None:
    matches = [o for o in orders if o["cliente_phone"] == client_phone and (o["es_pedido_abierto"] or not open_only)]
    if not matches:
        return None
    matches.sort(key=lambda o: (o["fecha"], o["pedido_ref"]))
    return matches[-1]


def sample_products_from_order(order_ref: str, items_by_order: dict[str, list[dict[str, Any]]], limit: int = 2) -> list[str]:
    items = items_by_order.get(order_ref, [])
    names = []
    for item in items:
        name = item.get("nombre") or item.get("product_code") or ""
        if name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def client_display_name(client: dict[str, Any]) -> str:
    return client.get("cliente_razon_social") or client.get("cliente_nombre") or client.get("cliente_phone") or "cliente"


def pick_complaint_theme(index: int) -> str:
    themes = [
        "demora en la entrega",
        "producto faltante",
        "error de facturacion",
        "producto roto o derramado",
        "precio distinto al acordado",
    ]
    return themes[index % len(themes)]


def build_conversation_messages(
    client: dict[str, Any],
    order: dict[str, Any] | None,
    item_names: list[str],
    is_active: bool,
    is_complaint: bool,
    base_dt: datetime,
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    rng = stable_rng("phase-07", client["cliente_phone"], order["pedido_ref"] if order else "sin-pedido")
    messages: list[dict[str, Any]] = []
    ai_delays = cfg.get("ai_reply_seconds", list(DEFAULT_AI_REPLY_SECONDS))
    human_delays = cfg.get("human_reply_seconds", list(DEFAULT_HUMAN_REPLY_SECONDS))
    if not isinstance(ai_delays, list):
        ai_delays = list(DEFAULT_AI_REPLY_SECONDS)
    if not isinstance(human_delays, list):
        human_delays = list(DEFAULT_HUMAN_REPLY_SECONDS)

    def shift(current: datetime, low: int, high: int) -> datetime:
        return current + timedelta(seconds=rng.randint(low, high))

    product_hint = item_names[0] if item_names else "tu pedido"
    order_total = order["total"] if order else "0"
    opener = f"Hola {client_display_name(client)}, te escribo por {product_hint}."
    if order and order["es_pedido_abierto"]:
        opener = f"Hola {client_display_name(client)}, vi que tenes un pedido abierto por {product_hint} y queria ayudarte a cerrarlo."
    elif order:
        opener = f"Hola {client_display_name(client)}, paso a revisar tu pedido {order['pedido_ref']} de {product_hint}."

    messages.append(
        {
            "sender_type": "ai",
            "message": opener,
            "created_at": base_dt,
        }
    )

    human1 = "Buen dia, decime."
    if order and order["es_pedido_abierto"]:
        human1 = f"Buen dia, pasame detalle de ese pedido por favor."
    elif order:
        human1 = f"Buen dia, eso fue lo que pedimos el otro dia?"
    if is_complaint:
        human1 = f"Hola, queria hacer un reclamo por {pick_complaint_theme(rng.randint(0, 10))}."

    messages.append(
        {
            "sender_type": "human",
            "message": human1,
            "created_at": shift(base_dt, human_delays[0], human_delays[-1]),
        }
    )

    if is_complaint:
        ai2 = f"Gracias por avisarnos. Ya tomo el caso por {pick_complaint_theme(rng.randint(0, 10))} y lo escalo para revision."
    elif order and order["es_pedido_abierto"]:
        ai2 = f"Te confirmo que el pedido {order['pedido_ref']} sigue en curso por un total de {order_total}. Si queres te lo dejo cerrado hoy."
    elif order:
        ai2 = f"Te confirmo que el pedido {order['pedido_ref']} fue registrado correctamente por {order_total}."
    else:
        ai2 = "Te puedo ayudar a revisar el catalogo o armar un pedido cuando quieras."
    messages.append(
        {
            "sender_type": "ai",
            "message": ai2,
            "created_at": shift(messages[-1]["created_at"], ai_delays[0], ai_delays[-1]),
        }
    )

    if is_complaint or is_active:
        human2 = "Perfecto, gracias."
        if is_complaint:
            human2 = "Dale, quedo atento."
        elif order and order["es_pedido_abierto"]:
            human2 = "Dale, mandamelo asi."
        messages.append(
            {
                "sender_type": "human",
                "message": human2,
                "created_at": shift(messages[-1]["created_at"], human_delays[0], human_delays[-1]),
            }
        )

    closing = "Quedo atento por cualquier otra duda. Gracias."
    if is_complaint:
        closing = "Ya quedo registrado. Te aviso apenas tengamos respuesta."
    elif order and order["es_pedido_abierto"]:
        closing = "Genial, te lo dejo confirmado y en preparacion."
    messages.append(
        {
            "sender_type": "ai",
            "message": closing,
            "created_at": shift(messages[-1]["created_at"], ai_delays[0], ai_delays[-1]),
        }
    )
    return messages


def summary_row(client: dict[str, Any], messages: list[dict[str, Any]], live_feed: bool, is_unread: bool) -> dict[str, Any]:
    return {
        "client_phone": client["cliente_phone"],
        "cantidad_mensajes": len(messages),
        "ultimo_mensaje_at": format_dt(messages[-1]["created_at"]),
        "is_unread": str(bool(is_unread)).lower(),
        "live_feed": str(bool(live_feed)).lower(),
        "is_mock": "true",
    }

