"""
preparar_insights.py
====================
Genera el CSV deterministico de Fase 8 (insights / notificaciones) para un
schema dado.

Uso:
    python scripts/fase-08-insights/preparar_insights.py --esquema <schema>

Config opcional en `implementacion/{schema}/config.json` bajo `fase_08`:
    {
      "total_tickets": 18,
      "open_ratio": 0.6,
      "open_quality": 3,
      "open_logistics": 3,
      "fecha_base": "2026-06-16",
      "hora_base": 11,
      "minuto_base": 15
    }
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from itertools import cycle

from _common import (
    DEFAULT_CLOSED_DAYS,
    DEFAULT_OPEN_DAYS,
    DEFAULT_OPEN_LOGISTICS,
    DEFAULT_OPEN_QUALITY,
    DEFAULT_OPEN_RATIO,
    DEFAULT_TOTAL_TICKETS,
    client_display_name,
    deterministic_ticket_prefix,
    format_dt,
    group_items_by_order,
    latest_order_for_client,
    load_catalog_products,
    load_clients,
    load_items,
    load_orders,
    load_phase07_messages,
    load_phase07_summary,
    load_promotions,
    load_tenant_context,
    normalize_text,
    order_items_lines,
    parse_int,
    sanitize_schema_name,
    ticket_created_at,
    ticket_ref,
    write_csv_rows,
)


if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


COMPLAINT_KEYWORDS = (
    "reclamo",
    "demora",
    "demoro",
    "falto",
    "faltante",
    "no llego",
    "llego roto",
    "roto",
    "derramo",
    "factura",
    "precio",
    "apellido",
    "cuit",
    "encargado",
)


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def resolve_base_dt(ctx: dict[str, object]) -> datetime:
    cfg = ctx.get("fase_08", {}) if isinstance(ctx, dict) else {}
    fecha_raw = cfg.get("fecha_base") if isinstance(cfg, dict) else None
    hora = parse_int(cfg.get("hora_base") if isinstance(cfg, dict) else None, 11)
    minuto = parse_int(cfg.get("minuto_base") if isinstance(cfg, dict) else None, 15)

    if fecha_raw:
        base_day = date.fromisoformat(str(fecha_raw))
    else:
        base_day = date.today()
    return datetime(base_day.year, base_day.month, base_day.day, hora, minuto, 0)


def resolve_brand_product(products: list[dict], brand: str) -> dict | None:
    brand_norm = normalize_text(brand)
    if not brand_norm:
        return None

    matches = []
    for product in products:
        haystack = " ".join(
            [
                normalize_text(product.get("nombre", "")),
                normalize_text(product.get("aliases", "")),
                normalize_text(product.get("descripcion", "")),
            ]
        )
        if brand_norm in haystack:
            matches.append(product)

    if not matches:
        return None
    matches.sort(key=lambda p: (-p.get("rotacion_index", 0.0), p.get("product_code", "")))
    return matches[0]


def complaint_signals(messages: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    by_phone: dict[str, dict[str, str]] = {}
    for row in messages:
        phone = row.get("client_phone") or row.get("session_id") or ""
        if not phone:
            continue
        sender = normalize_text(row.get("sender_type") or row.get("type") or "")
        if sender != "human":
            continue
        text = (row.get("message") or row.get("content") or "").strip()
        text_norm = normalize_text(text)
        score = sum(1 for keyword in COMPLAINT_KEYWORDS if keyword in text_norm)
        if score <= 0:
            continue
        current = by_phone.get(phone)
        if current is None or score > int(current.get("score", "0")):
            by_phone[phone] = {
                "score": str(score),
                "text": text,
            }
    return by_phone


def phase07_client_pool(
    clients: list[dict],
    summary_rows: list[dict[str, str]],
    message_rows: list[dict[str, str]],
) -> list[dict]:
    summary_by_phone = {row.get("client_phone", ""): row for row in summary_rows if row.get("client_phone")}
    complaint_by_phone = complaint_signals(message_rows)
    clients_by_phone = {client["cliente_phone"]: client for client in clients}

    ranked: list[dict] = []
    seen = set()

    for phone in sorted(complaint_by_phone):
        client = clients_by_phone.get(phone)
        if not client:
            continue
        row = summary_by_phone.get(phone, {})
        ranked.append(
            {
                **client,
                "_priority": 0,
                "_complaint_text": complaint_by_phone[phone]["text"],
                "_live_feed": row.get("live_feed", "false"),
                "_is_unread": row.get("is_unread", "false"),
            }
        )
        seen.add(phone)

    for row in sorted(summary_rows, key=lambda r: (r.get("live_feed", "false") != "true", r.get("client_phone", ""))):
        phone = row.get("client_phone", "")
        client = clients_by_phone.get(phone)
        if not client or phone in seen:
            continue
        ranked.append(
            {
                **client,
                "_priority": 1 if row.get("live_feed", "false") == "true" else 2,
                "_complaint_text": "",
                "_live_feed": row.get("live_feed", "false"),
                "_is_unread": row.get("is_unread", "false"),
            }
        )
        seen.add(phone)

    for client in clients:
        phone = client["cliente_phone"]
        if phone in seen:
            continue
        ranked.append(
            {
                **client,
                "_priority": 3,
                "_complaint_text": "",
                "_live_feed": "false",
                "_is_unread": "false",
            }
        )

    ranked.sort(key=lambda row: (row["_priority"], row["cliente_codigo"], row["cliente_phone"]))
    return ranked


def build_category_sequences(total_tickets: int, open_count: int, cfg: dict[str, object]) -> tuple[list[str], list[str]]:
    open_quality = clamp(parse_int(cfg.get("open_quality"), DEFAULT_OPEN_QUALITY), 0, open_count)
    open_logistics = clamp(parse_int(cfg.get("open_logistics"), DEFAULT_OPEN_LOGISTICS), 0, max(open_count - open_quality, 0))

    open_categories: list[str] = []
    open_categories.extend(["Calidad"] * open_quality)
    open_categories.extend(["Logistica"] * open_logistics)
    open_fill = cycle(["Comercial", "Administracion"])
    while len(open_categories) < open_count:
        open_categories.append(next(open_fill))

    closed_count = max(total_tickets - open_count, 0)
    closed_categories: list[str] = []
    closed_fill = cycle(["Administracion", "Comercial", "Logistica", "Calidad"])
    while len(closed_categories) < closed_count:
        closed_categories.append(next(closed_fill))

    return open_categories, closed_categories


def build_ticket_texts(
    categoria: str,
    client: dict,
    product_label: str,
    order_ref: str,
) -> tuple[str, str]:
    client_name = client_display_name(client)
    if categoria == "Calidad":
        description = f"Reclamo por {product_label} con entrega en mal estado o faltante parcial."
        message = f"Hola, me llego {product_label} en mal estado y quiero hacer el reclamo."
        return description, message
    if categoria == "Logistica":
        description = f"Demora en la entrega del pedido {order_ref} de {product_label}."
        message = f"Buen dia, sigo esperando el pedido {order_ref} de {product_label} y no llego."
        return description, message
    if categoria == "Comercial":
        return (
            f"Pide hablar con el encargado comercial por la cuenta de {client_name}.",
            "",
        )
    return (
        f"Solicita corregir datos administrativos de {client_name} en el sistema.",
        "",
    )


def product_label_for_client(
    client: dict,
    orders: list[dict],
    items_by_order: dict[str, list[dict]],
    brand_product: dict | None,
    catalog_products: list[dict],
) -> str:
    latest_order = latest_order_for_client(orders, client["cliente_phone"], open_only=False)
    if latest_order:
        labels = order_items_lines(latest_order["pedido_ref"], items_by_order, limit=2)
        if labels:
            return labels[0]
        if latest_order.get("pedido_ref"):
            return latest_order["pedido_ref"]

    if brand_product:
        return brand_product.get("nombre") or brand_product.get("product_code") or "producto"
    if catalog_products:
        return catalog_products[0].get("nombre") or catalog_products[0].get("product_code") or "producto"
    return "producto"


def build_rows(schema: str) -> list[dict[str, object]]:
    ctx = load_tenant_context(schema)
    cfg = dict(ctx.get("fase_08", {}))
    total_tickets = clamp(parse_int(cfg.get("total_tickets"), DEFAULT_TOTAL_TICKETS), 15, 20)
    open_ratio = float(cfg.get("open_ratio", DEFAULT_OPEN_RATIO))
    open_count = clamp(round(total_tickets * open_ratio), 1, total_tickets - 1)

    clients = load_clients(schema)
    if not clients:
        raise SystemExit("[FAIL] No se encontraron clientes para la fase 8.")

    summary_rows = load_phase07_summary(schema)
    message_rows = load_phase07_messages(schema)
    orders = load_orders(schema)
    items = load_items(schema)
    items_by_order = group_items_by_order(items)
    products = load_catalog_products(schema)
    promotions = load_promotions(schema)
    _ = promotions  # Cargado por consistencia reutilizable entre esquemas.

    brand_name = str(ctx.get("manifest", {}).get("marca_lider", "") or "")
    brand_product = resolve_brand_product(products, brand_name)
    client_pool = phase07_client_pool(clients, summary_rows, message_rows)

    open_categories, closed_categories = build_category_sequences(total_tickets, open_count, cfg)
    status_seq = ["open"] * open_count + ["closed"] * (total_tickets - open_count)

    prefix = parse_int(cfg.get("ticket_prefix"), deterministic_ticket_prefix(schema))
    base_dt = resolve_base_dt(ctx)
    rows: list[dict[str, object]] = []

    complaint_slots = [idx for idx, (status, cat) in enumerate(zip(status_seq, open_categories + closed_categories)) if status == "open" and cat in {"Calidad", "Logistica"}]
    complaint_clients = [row for row in client_pool if row.get("_complaint_text")]
    if len(complaint_clients) < len(complaint_slots):
        complaint_clients.extend([row for row in client_pool if row not in complaint_clients])

    client_cursor = 0
    complaint_cursor = 0

    combined_categories = open_categories + closed_categories
    for index, (status, categoria) in enumerate(zip(status_seq, combined_categories)):
        if status == "open" and categoria in {"Calidad", "Logistica"} and complaint_cursor < len(complaint_clients):
            client = complaint_clients[complaint_cursor]
            complaint_cursor += 1
        else:
            while client_cursor < len(client_pool):
                candidate = client_pool[client_cursor]
                client_cursor += 1
                if status == "open" and categoria in {"Calidad", "Logistica"} and candidate in complaint_clients[:complaint_cursor]:
                    continue
                client = candidate
                break
            else:
                client = client_pool[index % len(client_pool)]

        order = latest_order_for_client(orders, client["cliente_phone"], open_only=False)
        order_ref = order["pedido_ref"] if order else f"PEDIDO-{index + 1:03d}"
        product_label = product_label_for_client(client, orders, items_by_order, brand_product, products)
        description, incoming = build_ticket_texts(categoria, client, product_label, order_ref)

        created_at = ticket_created_at(base_dt, status == "open", index)
        closed_at = None if status == "open" else created_at + timedelta(hours=4 + (index % 36))

        rows.append(
            {
                "ticket_ref": ticket_ref(prefix, index),
                "categoria": categoria,
                "status": status,
                "description": description,
                "client_phone": client["cliente_phone"],
                "mensaje_cruzado_incoming": incoming if status == "open" and categoria in {"Calidad", "Logistica"} else "",
                "created_at": format_dt(created_at),
                "closed_at": format_dt(closed_at) if closed_at else "",
                "is_mock": "true",
            }
        )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera el CSV de insights mock de Fase 8.")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant (ej: al_fuego)")
    args = parser.parse_args()

    schema = sanitize_schema_name(args.esquema)
    ctx = load_tenant_context(schema)
    rows = build_rows(schema)
    out_path = ctx["paths"]["outputs"] / "phase-08-notificaciones.csv"

    write_csv_rows(
        out_path,
        rows,
        [
            "ticket_ref",
            "categoria",
            "status",
            "description",
            "client_phone",
            "mensaje_cruzado_incoming",
            "created_at",
            "closed_at",
            "is_mock",
        ],
    )

    open_count = sum(1 for row in rows if row["status"] == "open")
    cross_count = sum(1 for row in rows if row["mensaje_cruzado_incoming"])
    print(f"[*] CSV generado: {out_path}")
    print(f"[*] Tickets totales: {len(rows)}")
    print(f"[*] Tickets open:    {open_count}")
    print(f"[*] Cross messages:   {cross_count}")
    print("[*] Siguiente paso:")
    print(f"    python scripts/fase-08-insights/cargar_insights.py --esquema {schema}")


if __name__ == "__main__":
    main()
