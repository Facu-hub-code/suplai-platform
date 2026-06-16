"""
preparar_conversaciones.py
==========================
Genera el resumen CSV de Fase 7 y el detalle de mensajes mock por esquema.

Inputs:
  - implementacion/{esquema}/outputs/phase-04-clientes.csv
  - implementacion/{esquema}/outputs/phase-05-clientes-flags.csv
  - implementacion/{esquema}/outputs/phase-06-pedidos.csv
  - implementacion/{esquema}/outputs/phase-06-items-pedido.csv

Outputs:
  - implementacion/{esquema}/outputs/phase-07-conversaciones-resumen.csv
  - implementacion/{esquema}/outputs/phase-07-mensajes.csv

Configuracion opcional en implementacion/{esquema}/config.json:
  "fase_07": {
    "clientes_live_feed": 12,
    "clientes_quejas": 4,
    "fecha_base": "2026-06-16"
  }
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from _common import (
    DEFAULT_ACTIVE_HOURS,
    DEFAULT_ARCHIVE_DAYS,
    DEFAULT_COMPLAINT_CLIENTS,
    DEFAULT_HISTORIC_MAX_MESSAGES,
    DEFAULT_HISTORIC_MIN_MESSAGES,
    build_conversation_messages,
    client_display_name,
    format_dt,
    group_items_by_order,
    latest_order_for_client,
    load_clients,
    load_orders,
    load_items,
    load_tenant_context,
    parse_int,
    read_csv_rows,
    split_clients_for_live_feed,
    summary_row,
    tenant_paths,
    write_csv_rows,
)


if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


def build_phase07(schema: str) -> tuple[list[dict], list[dict]]:
    ctx = load_tenant_context(schema)
    cfg = dict(ctx.get("fase_07", {}))
    clients = load_clients(schema)
    orders = load_orders(schema)
    items = load_items(schema)
    items_by_order = group_items_by_order(items)

    active_clients, complaint_clients = split_clients_for_live_feed(clients, orders, cfg)
    active_phones = {c["cliente_phone"] for c in active_clients}
    complaint_phones = {c["cliente_phone"] for c in complaint_clients}

    fecha_base_raw = cfg.get("fecha_base")
    if fecha_base_raw:
        fecha_base = datetime.fromisoformat(f"{fecha_base_raw} 12:00:00") if len(fecha_base_raw) == 10 else datetime.fromisoformat(fecha_base_raw)
    else:
        fecha_base = datetime.now()

    summaries: list[dict] = []
    messages_rows: list[dict] = []

    for idx, client in enumerate(clients):
        is_active = client["cliente_phone"] in active_phones
        is_complaint = client["cliente_phone"] in complaint_phones
        order = latest_order_for_client(orders, client["cliente_phone"], open_only=is_active)
        if not order:
            order = latest_order_for_client(orders, client["cliente_phone"], open_only=False)

        item_names = []
        if order:
            item_names = [item.get("nombre") or item.get("product_code") or "" for item in items_by_order.get(order["pedido_ref"], []) if item.get("nombre") or item.get("product_code")]
            if not item_names and order.get("pedido_ref"):
                item_names = [item.get("nombre") for item in items_by_order.get(order["pedido_ref"], [])[:2] if item.get("nombre")]

        if is_active:
            hour_offset = parse_int(cfg.get("active_max_hours", DEFAULT_ACTIVE_HOURS[1]), DEFAULT_ACTIVE_HOURS[1])
            base_dt = fecha_base - timedelta(hours=(idx % max(hour_offset, 1)))
        else:
            archive_days = cfg.get("archive_days", list(DEFAULT_ARCHIVE_DAYS))
            if not isinstance(archive_days, list) or len(archive_days) < 2:
                archive_days = list(DEFAULT_ARCHIVE_DAYS)
            day_offset = archive_days[idx % len(archive_days)]
            base_dt = fecha_base - timedelta(days=int(day_offset), hours=(idx % 5))

        messages = build_conversation_messages(
            client=client,
            order=order,
            item_names=item_names[:2],
            is_active=is_active,
            is_complaint=is_complaint,
            base_dt=base_dt,
            cfg=cfg,
        )

        # Ajuste fino para que los clientes activos queden con live_feed/unread y
        # el resto archivado; el último mensaje siempre queda en AI por diseño.
        summaries.append(
            summary_row(
                client,
                messages,
                live_feed=is_active,
                is_unread=is_active,
            )
        )

        for msg in messages:
            messages_rows.append(
                {
                    "client_phone": client["cliente_phone"],
                    "session_id": client["cliente_phone"],
                    "sender_type": msg["sender_type"],
                    "type": msg["sender_type"],
                    "message": msg["message"],
                    "content": msg["message"],
                    "created_at": format_dt(msg["created_at"]),
                    "is_mock": "true",
                }
            )

    summaries.sort(key=lambda r: (r["live_feed"] != "true", r["client_phone"]))
    messages_rows.sort(key=lambda r: (r["client_phone"], r["created_at"]))
    return summaries, messages_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera conversaciones mock deterministas para Fase 7.")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant (ej: al_fuego)")
    parser.add_argument("--clientes-live-feed", type=int, default=None, help="Cantidad de clientes live_feed")
    parser.add_argument("--clientes-quejas", type=int, default=None, help="Cantidad de clientes con reclamos")
    parser.add_argument("--fecha-base", default=None, help="Fecha base para timestamps (YYYY-MM-DD o ISO)")
    args = parser.parse_args()

    ctx = load_tenant_context(args.esquema)
    schema = ctx["schema"]
    cfg = dict(ctx.get("fase_07", {}))
    if args.clientes_live_feed is not None:
        cfg["clientes_live_feed"] = args.clientes_live_feed
    if args.clientes_quejas is not None:
        cfg["clientes_quejas"] = args.clientes_quejas
    if args.fecha_base:
        cfg["fecha_base"] = args.fecha_base

    summaries, messages_rows = build_phase07(schema)

    output_dir = ctx["paths"]["outputs"]
    summary_path = output_dir / "phase-07-conversaciones-resumen.csv"
    messages_path = output_dir / "phase-07-mensajes.csv"

    write_csv_rows(
        summary_path,
        summaries,
        ["client_phone", "cantidad_mensajes", "ultimo_mensaje_at", "is_unread", "live_feed", "is_mock"],
    )
    write_csv_rows(
        messages_path,
        messages_rows,
        ["client_phone", "session_id", "sender_type", "type", "message", "content", "created_at", "is_mock"],
    )

    live_count = sum(1 for row in summaries if row["live_feed"] == "true")
    unread_count = sum(1 for row in summaries if row["is_unread"] == "true")
    print(f"[*] CSV generado: {summary_path}")
    print(f"[*] CSV generado: {messages_path}")
    print(f"[*] Clientes live_feed: {live_count}")
    print(f"[*] Clientes unread:    {unread_count}")
    print(f"[*] Mensajes totales:   {len(messages_rows)}")
    print("[*] Siguiente paso:")
    print(f"    python scripts/fase-07-conversaciones/cargar_conversaciones.py --esquema {schema}")


if __name__ == "__main__":
    main()

