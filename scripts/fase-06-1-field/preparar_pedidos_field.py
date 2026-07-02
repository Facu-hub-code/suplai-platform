"""
preparar_pedidos_field.py
=========================
Genera pedidos históricos enriquecidos (Jun 2025 – May 2026) para alimentar el
modelo de ML (co-ocurrencia + frecuencia de reposición) de Suplai Field.

Diseño:
  - Backbone histórico  (Jun 2025 – Feb 2026): 6-8 pedidos por cliente, con los
    mismos top-2 SKUs repitiéndose en intervalos de ~20-40 días → el ML detecta
    avg_interval_days personalizado (necesita ≥3 compras del mismo producto).
  - Ventana reciente    (Abr–May 2026): 2-3 pedidos adicionales por cliente en
    estado 'confirmado' → empuja pedidos_90d > 3 (threshold de REPOSICION_HABITO).
  - 20% de clientes quedan "inactivos" (último pedido en Oct 2025) → REACTIVAR_CLIENTE.
  - 80% de clientes con pedidos en Feb 2026 → MEJORAR_MIX_RENTABLE.

Uso:
    python scripts/fase-06-1-field/preparar_pedidos_field.py --esquema <schema>

Salida:
    implementacion/<schema>/outputs/phase-06-1-pedidos-field.csv
    implementacion/<schema>/outputs/phase-06-1-items-pedido-field.csv
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "fase-06-pedidos"))

from _common_field import (
    create_conn,
    get_all_active_vendedores,
    get_top_products,
    load_all_clients_by_vendedor,
    load_all_prices,
    lookup_price,
    money,
    parse_float,
    parse_int,
    sanitize_schema_name,
    tenant_paths,
    write_csv_rows,
)

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BACKBONE_START = date(2025, 6, 1)
BACKBONE_END   = date(2026, 2, 28)
RECENT_START   = date(2026, 4, 1)
RECENT_END     = date(2026, 5, 20)

BACKBONE_ORDERS_PER_CLIENT   = 7    # pedidos en el período largo
RECENT_ORDERS_PER_CLIENT     = 3    # pedidos adicionales en ventana de 90 días
INACTIVE_CLIENT_RATIO        = 0.20 # 20% de clientes → su último pedido cae en Oct 2025

ORDER_REF_PREFIX = "PF-"  # Distingue de los pedidos de F6 (P-)


# ---------------------------------------------------------------------------
# Helpers de generación
# ---------------------------------------------------------------------------

def _seeded(schema: str, *parts: Any) -> random.Random:
    seed_str = "|".join(str(p) for p in [schema, *parts])
    import hashlib
    digest = hashlib.sha256(seed_str.encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _random_date_in(rng: random.Random, start: date, end: date) -> date:
    span = (end - start).days
    return start + timedelta(days=rng.randint(0, max(span, 0)))


def _datetime_for(d: date, rng: random.Random) -> str:
    hour = rng.randint(8, 18)
    minute = rng.randint(0, 59)
    return datetime(d.year, d.month, d.day, hour, minute, 0).strftime("%Y-%m-%d %H:%M:%S")


def _generate_backbone_dates(
    rng: random.Random,
    n: int,
    start: date,
    end: date,
    inactive: bool,
) -> list[date]:
    """Genera `n` fechas con intervalos de 20-40 días entre cada una."""
    if inactive:
        # Último pedido en Oct 2025 → cliente inactivo al momento de hoy (Jun 2026)
        end = date(2025, 10, 31)

    span = (end - start).days
    if span < n * 15:
        # Si el rango es muy corto, distribuir uniformemente
        step = max(span // n, 1)
        dates = [start + timedelta(days=i * step) for i in range(n)]
    else:
        interval_days = span // n
        dates = []
        cursor = start
        for i in range(n):
            jitter = rng.randint(-5, 5)
            d = cursor + timedelta(days=jitter)
            d = max(start, min(d, end))
            dates.append(d)
            cursor += timedelta(days=interval_days)

    return sorted(set(dates))[:n]


def _generate_recent_dates(rng: random.Random, n: int) -> list[date]:
    """Genera `n` fechas en la ventana reciente (Abr-May 2026)."""
    dates: list[date] = []
    used: set[date] = set()
    attempts = 0
    while len(dates) < n and attempts < 50:
        d = _random_date_in(rng, RECENT_START, RECENT_END)
        if d not in used:
            used.add(d)
            dates.append(d)
        attempts += 1
    return sorted(dates)


def _pick_top_n(products: list[dict], n: int) -> list[dict]:
    """Selecciona los top-n productos ya ordenados por rotacion_index."""
    return products[:n] if len(products) >= n else products


# ---------------------------------------------------------------------------
# Generación principal
# ---------------------------------------------------------------------------

async def generate(schema: str) -> None:
    conn = await create_conn()
    try:
        # 1. Obtener clientes de todos los vendedores activos
        vendedores = await get_all_active_vendedores(conn, schema)
        if not vendedores:
            raise SystemExit(f"[FAIL] No hay vendedores activos en {schema}.")

        # Cargar todos los clientes de todos los vendedores en 1 sola query
        clients_by_vendor = await load_all_clients_by_vendedor(conn, schema)
        clients_all: list[dict] = []
        seen_ids: set[int] = set()
        for v in vendedores:
            for c in clients_by_vendor.get(int(v["id"]), []):
                if c["id"] not in seen_ids:
                    seen_ids.add(c["id"])
                    c["_vendedor_id"] = v["id"]
                    clients_all.append(c)

        if not clients_all:
            raise SystemExit(f"[FAIL] No hay clientes en cartera en {schema}.")

        # 2. Obtener top productos del catálogo
        products = await get_top_products(conn, schema, limit=30)
        if not products:
            raise SystemExit(f"[FAIL] No hay productos en {schema}.")
            
        all_prices = await load_all_prices(conn, schema)

        top_anchor   = _pick_top_n(products, 5)   # Top 5 → productos "habituales"
        rest_catalog = products[5:20]              # Los siguientes → productos ocasionales

        # 3. Generar pedidos
        orders_rows: list[dict] = []
        items_rows:  list[dict] = []
        order_idx = 1
        inactive_cutoff = int(len(clients_all) * INACTIVE_CLIENT_RATIO)

        for ci, client in enumerate(clients_all):
            cid      = client["id"]
            phone    = client.get("phone_number", "")
            lista_id = parse_int(client.get("lista_precios_id"), 1)
            inactive = ci < inactive_cutoff   # Los primeros 20% son inactivos

            rng_client = _seeded(schema, "backbone", cid)

            # Selección de SKUs "ancla" para este cliente (aparecerán repetidamente)
            anchor_products = rng_client.sample(top_anchor, min(2, len(top_anchor)))

            # — — — Backbone histórico — — —
            backbone_dates = _generate_backbone_dates(
                rng_client, BACKBONE_ORDERS_PER_CLIENT, BACKBONE_START, BACKBONE_END, inactive
            )
            for d in backbone_dates:
                ref  = f"{ORDER_REF_PREFIX}{order_idx:06d}"
                ts   = _datetime_for(d, rng_client)
                estado = "confirmado"

                # Ítems: al menos un SKU ancla + 1-2 ocasionales
                n_occasional = rng_client.randint(0, 2)
                occasional   = rng_client.sample(rest_catalog, min(n_occasional, len(rest_catalog)))
                chosen_prods = anchor_products + occasional

                order_total  = Decimal("0")
                for prod in chosen_prods:
                    qty   = rng_client.randint(1, 4)
                    price = lookup_price(all_prices, prod["product_code"], lista_id)
                    subtotal = money(price * qty)
                    order_total += subtotal
                    items_rows.append(
                        {
                            "pedido_ref":         ref,
                            "product_code":       prod["product_code"],
                            "nombre":             prod.get("nombre", ""),
                            "cantidad_solicitada": qty,
                            "precio_unitario":    str(price),
                            "lista_precios_id":   lista_id,
                            "notas":              f"Pedido histórico field mock ({d.isoformat()})",
                            "is_mock":            "true",
                            "cliente_phone":      phone,
                        }
                    )

                orders_rows.append(
                    {
                        "pedido_ref":      ref,
                        "cliente_phone":   phone,
                        "fecha":           ts,
                        "estado":          estado,
                        "total":           str(money(order_total)),
                        "notas":           "Pedido histórico field mock",
                        "is_mock":         "true",
                        "es_pedido_abierto": "false",
                        "source":          "fase-06-1-field-backbone",
                    }
                )
                order_idx += 1

            # — — — Ventana reciente (solo clientes activos) — — —
            if not inactive:
                rng_recent = _seeded(schema, "recent", cid)
                recent_dates = _generate_recent_dates(rng_recent, RECENT_ORDERS_PER_CLIENT)
                for d in recent_dates:
                    ref  = f"{ORDER_REF_PREFIX}{order_idx:06d}"
                    ts   = _datetime_for(d, rng_recent)
                    chosen_prods = rng_recent.sample(top_anchor, min(2, len(top_anchor)))

                    order_total = Decimal("0")
                    for prod in chosen_prods:
                        qty   = rng_recent.randint(1, 3)
                        price = lookup_price(all_prices, prod["product_code"], lista_id)
                        subtotal = money(price * qty)
                        order_total += subtotal
                        items_rows.append(
                            {
                                "pedido_ref":         ref,
                                "product_code":       prod["product_code"],
                                "nombre":             prod.get("nombre", ""),
                                "cantidad_solicitada": qty,
                                "precio_unitario":    str(price),
                                "lista_precios_id":   lista_id,
                                "notas":              f"Pedido reciente field mock ({d.isoformat()})",
                                "is_mock":            "true",
                                "cliente_phone":      phone,
                            }
                        )

                    orders_rows.append(
                        {
                            "pedido_ref":      ref,
                            "cliente_phone":   phone,
                            "fecha":           ts,
                            "estado":          "confirmado",
                            "total":           str(money(order_total)),
                            "notas":           "Pedido reciente field mock",
                            "is_mock":         "true",
                            "es_pedido_abierto": "false",
                            "source":          "fase-06-1-field-recent",
                        }
                    )
                    order_idx += 1

    finally:
        await conn.close()

    # 4. Escribir CSVs
    paths = tenant_paths(schema)
    orders_path = paths["outputs"] / "phase-06-1-pedidos-field.csv"
    items_path  = paths["outputs"] / "phase-06-1-items-pedido-field.csv"

    order_fields = [
        "pedido_ref", "cliente_phone", "fecha", "estado", "total",
        "notas", "is_mock", "es_pedido_abierto", "source",
    ]
    item_fields = [
        "pedido_ref", "product_code", "nombre", "cantidad_solicitada",
        "precio_unitario", "lista_precios_id", "notas", "is_mock", "cliente_phone",
    ]

    write_csv_rows(orders_path, orders_rows, order_fields)
    write_csv_rows(items_path,  items_rows,  item_fields)

    n_clientes   = len(clients_all)
    n_inactivos  = inactive_cutoff
    n_activos    = n_clientes - n_inactivos

    print(f"\n{'='*60}")
    print("PREPARACIÓN FASE 6.1 — PEDIDOS FIELD")
    print(f"{'='*60}")
    print(f"  Clientes procesados:    {n_clientes}")
    print(f"  Clientes inactivos (~{INACTIVE_CLIENT_RATIO*100:.0f}%): {n_inactivos}")
    print(f"  Clientes activos:       {n_activos}")
    print(f"  Pedidos generados:      {len(orders_rows)}")
    print(f"  Items generados:        {len(items_rows)}")
    print(f"  CSV pedidos:  {orders_path}")
    print(f"  CSV items:    {items_path}")
    print(f"{'='*60}")
    print("\nRevisá los CSVs y ejecutá: python cargar_pedidos_field.py --esquema " + schema)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera pedidos históricos para Suplai Field (Fase 6.1).")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant (ej: demo)")
    args = parser.parse_args()
    asyncio.run(generate(sanitize_schema_name(args.esquema)))


if __name__ == "__main__":
    main()
