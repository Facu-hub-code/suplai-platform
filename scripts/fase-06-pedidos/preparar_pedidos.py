"""
preparar_pedidos.py
===================
Genera los CSV de Fase 6 (pedidos historicos + pedidos abiertos) de forma
determinista y reutilizable por esquema.

Entradas:
  - implementacion/{esquema}/manifest.yaml
  - implementacion/{esquema}/config.json (opcional)
  - implementacion/{esquema}/outputs/phase-04-clientes.csv
  - implementacion/{esquema}/outputs/phase-05-clientes-flags.csv
  - implementacion/{esquema}/outputs/phase-01-productos.csv
  - implementacion/{esquema}/outputs/phase-01-listas-precios.csv
  - implementacion/{esquema}/outputs/phase-02-promociones.csv (opcional)

Salidas:
  - implementacion/{esquema}/outputs/phase-06-pedidos.csv
  - implementacion/{esquema}/outputs/phase-06-items-pedido.csv

La configuracion personalizable se puede definir en config.json bajo la clave
"fase_06":
  {
    "historicos_por_cliente": 3,
    "abiertos": 7,
    "historicos_inicio": "2026-03-01",
    "historicos_fin": "2026-05-31",
    "fecha_abiertos": "2026-06-16"
  }
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from _common import (
    as_money_str,
    apply_promo_price,
    build_item_note,
    build_order_note,
    format_dt,
    load_catalog_products,
    load_merged_clients,
    load_prices,
    load_promotions,
    load_tenant_context,
    money,
    open_timestamp,
    order_reference,
    pick_products_for_order,
    resolve_brand_leader_product,
    stable_rng,
    write_csv_rows,
    DEFAULT_HISTORIC_PER_CLIENT,
    DEFAULT_OPEN_ORDERS,
    DEFAULT_HISTORIC_STATUSES,
    DEFAULT_OPEN_STATUS_PRIORITY,
    historic_timestamp,
    parse_int,
)


if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


def build_historic_orders(schema: str, clients: list[dict], products: list[dict], prices: dict, cfg: dict) -> tuple[list[dict], list[dict]]:
    rows_orders: list[dict] = []
    rows_items: list[dict] = []
    per_client = max(parse_int(cfg.get("historicos_por_cliente"), DEFAULT_HISTORIC_PER_CLIENT), 1)
    order_idx = 1

    for client_idx, client in enumerate(clients):
        for repetition in range(per_client):
            rng = stable_rng(schema, "historico", client["cliente_phone"], repetition)
            num_items = min(len(products), max(1, rng.randint(1, 4)))
            selected_products = pick_products_for_order(products, rng, num_items)
            order_dt = historic_timestamp(client_idx, repetition, cfg)
            estado = DEFAULT_HISTORIC_STATUSES[(client_idx + repetition) % len(DEFAULT_HISTORIC_STATUSES)]

            item_rows_for_order: list[dict] = []
            total = Decimal("0")
            for item_idx, product in enumerate(selected_products):
                qty = max(1, rng.randint(1, 5))
                list_price = prices.get(product["product_code"], {}).get(client["lista_precios_id"], product["precio_lista_1"])
                unit_price = money(list_price)
                line_total = money(unit_price * qty)
                total += line_total

                item_rows_for_order.append(
                    {
                        "pedido_ref": order_reference(order_idx),
                        "cliente_phone": client["cliente_phone"],
                        "cliente_codigo": client["cliente_codigo"],
                        "product_code": product["product_code"],
                        "nombre": product["nombre"],
                        "cantidad_solicitada": qty,
                        "precio_unitario": as_money_str(unit_price),
                        "lista_precios_id": client["lista_precios_id"],
                        "notas": build_item_note(product, qty),
                        "is_mock": "true",
                        "es_pedido_abierto": "false",
                        "promo_aplicada": "false",
                    }
                )

            rows_items.extend(item_rows_for_order)
            rows_orders.append(
                {
                    "pedido_ref": order_reference(order_idx),
                    "cliente_codigo": client["cliente_codigo"],
                    "cliente_phone": client["cliente_phone"],
                    "cliente_razon_social": client["cliente_razon_social"],
                    "fecha": format_dt(order_dt),
                    "estado": estado,
                    "total": as_money_str(total),
                    "notas": build_order_note(False, client_label=client["cliente_razon_social"]),
                    "is_mock": "true",
                    "es_pedido_abierto": "false",
                    "lista_precios_id": client["lista_precios_id"],
                }
            )
            order_idx += 1

    return rows_orders, rows_items


def build_open_orders(
    schema: str,
    clients: list[dict],
    products: list[dict],
    prices: dict,
    promos: dict,
    cfg: dict,
    open_orders_count: int,
) -> tuple[list[dict], list[dict]]:
    rows_orders: list[dict] = []
    rows_items: list[dict] = []

    open_clients = [c for c in clients if not c["is_prospect"]]
    if not open_clients:
        open_clients = list(clients)

    brand = load_tenant_context(schema)["manifest"].get("marca_lider", "")
    brand_product = resolve_brand_leader_product(products, brand)
    promo_anchor = None
    if brand_product:
        matching_promos = [p for (code, _lista), p in promos.items() if code == brand_product["product_code"] and p.get("activa")]
        if matching_promos:
            matching_promos.sort(key=lambda p: (p["lista_precios_id"], p["promo_id"]))
            promo_anchor = brand_product, matching_promos[0]

    anchor_client = None
    if promo_anchor:
        _, promo = promo_anchor
        for client in open_clients:
            if client["lista_precios_id"] == promo["lista_precios_id"]:
                anchor_client = client
                break
    if anchor_client is None:
        anchor_client = open_clients[0]

    chosen_clients = [anchor_client]
    for client in open_clients:
        if client["cliente_phone"] == anchor_client["cliente_phone"]:
            continue
        chosen_clients.append(client)
        if len(chosen_clients) >= open_orders_count:
            break
    chosen_clients = chosen_clients[:open_orders_count]

    order_idx_base = len(clients) * max(parse_int(cfg.get("historicos_por_cliente"), DEFAULT_HISTORIC_PER_CLIENT), 1) + 1

    for offset, client in enumerate(chosen_clients):
        rng = stable_rng(schema, "abierto", client["cliente_phone"], offset)
        estado = DEFAULT_OPEN_STATUS_PRIORITY[offset % len(DEFAULT_OPEN_STATUS_PRIORITY)]
        order_dt = open_timestamp(cfg, offset)
        num_items = min(len(products), max(1, rng.randint(1, 4)))

        item_rows_for_order: list[dict] = []
        total = Decimal("0")

        if offset == 0 and promo_anchor:
            brand_product, promo = promo_anchor
            promo_qty = max(1, promo.get("min_qty_umv", 1))
            base_price = prices.get(brand_product["product_code"], {}).get(client["lista_precios_id"], brand_product["precio_lista_1"])
            unit_price = apply_promo_price(base_price, promo, promo_qty)
            total += money(unit_price * promo_qty)
            item_rows_for_order.append(
                {
                    "pedido_ref": order_reference(order_idx_base + offset),
                    "cliente_phone": client["cliente_phone"],
                    "cliente_codigo": client["cliente_codigo"],
                    "product_code": brand_product["product_code"],
                    "nombre": brand_product["nombre"],
                    "cantidad_solicitada": promo_qty,
                    "precio_unitario": as_money_str(unit_price),
                    "lista_precios_id": client["lista_precios_id"],
                    "notas": build_item_note(brand_product, promo_qty) + " - promo fase 2",
                    "is_mock": "true",
                    "es_pedido_abierto": "true",
                    "promo_aplicada": "true",
                }
            )

            exclude = {brand_product["product_code"]}
            remaining = max(num_items - 1, 0)
            if remaining:
                extra_products = pick_products_for_order(products, rng, remaining, exclude=exclude)
                for product in extra_products:
                    qty = max(1, rng.randint(1, 5))
                    list_price = prices.get(product["product_code"], {}).get(client["lista_precios_id"], product["precio_lista_1"])
                    unit_price = money(list_price)
                    total += money(unit_price * qty)
                    item_rows_for_order.append(
                        {
                            "pedido_ref": order_reference(order_idx_base + offset),
                            "cliente_phone": client["cliente_phone"],
                            "cliente_codigo": client["cliente_codigo"],
                            "product_code": product["product_code"],
                            "nombre": product["nombre"],
                            "cantidad_solicitada": qty,
                            "precio_unitario": as_money_str(unit_price),
                            "lista_precios_id": client["lista_precios_id"],
                            "notas": build_item_note(product, qty),
                            "is_mock": "true",
                            "es_pedido_abierto": "true",
                            "promo_aplicada": "false",
                        }
                    )
        else:
            selected_products = pick_products_for_order(products, rng, num_items)
            for product in selected_products:
                qty = max(1, rng.randint(1, 5))
                list_price = prices.get(product["product_code"], {}).get(client["lista_precios_id"], product["precio_lista_1"])
                unit_price = money(list_price)
                total += money(unit_price * qty)
                item_rows_for_order.append(
                    {
                        "pedido_ref": order_reference(order_idx_base + offset),
                        "cliente_phone": client["cliente_phone"],
                        "cliente_codigo": client["cliente_codigo"],
                        "product_code": product["product_code"],
                        "nombre": product["nombre"],
                        "cantidad_solicitada": qty,
                        "precio_unitario": as_money_str(unit_price),
                        "lista_precios_id": client["lista_precios_id"],
                        "notas": build_item_note(product, qty),
                        "is_mock": "true",
                        "es_pedido_abierto": "true",
                        "promo_aplicada": "false",
                    }
                )

        rows_items.extend(item_rows_for_order)
        rows_orders.append(
            {
                "pedido_ref": order_reference(order_idx_base + offset),
                "cliente_codigo": client["cliente_codigo"],
                "cliente_phone": client["cliente_phone"],
                "cliente_razon_social": client["cliente_razon_social"],
                "fecha": format_dt(order_dt),
                "estado": estado,
                "total": as_money_str(total),
                "notas": build_order_note(True, promo_label="promo Fase 2" if offset == 0 and promo_anchor else "", client_label=client["cliente_razon_social"]),
                "is_mock": "true",
                "es_pedido_abierto": "true",
                "lista_precios_id": client["lista_precios_id"],
            }
        )

    return rows_orders, rows_items


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera los CSV de pedidos mock para Fase 6.")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant (ej: al_fuego)")
    parser.add_argument("--historicos-por-cliente", type=int, default=None, help="Cantidad de pedidos historicos por cliente")
    parser.add_argument("--abiertos", type=int, default=None, help="Cantidad de pedidos abiertos a generar")
    parser.add_argument("--fecha-abiertos", default=None, help="Fecha para los pedidos abiertos (YYYY-MM-DD)")
    parser.add_argument("--historicos-inicio", default=None, help="Fecha inicio del rango historico (YYYY-MM-DD)")
    parser.add_argument("--historicos-fin", default=None, help="Fecha fin del rango historico (YYYY-MM-DD)")
    args = parser.parse_args()

    ctx = load_tenant_context(args.esquema)
    schema = ctx["schema"]
    cfg = dict(ctx.get("fase_06", {}))
    if args.historicos_por_cliente is not None:
        cfg["historicos_por_cliente"] = args.historicos_por_cliente
    if args.abiertos is not None:
        cfg["abiertos"] = args.abiertos
    if args.fecha_abiertos:
        cfg["fecha_abiertos"] = args.fecha_abiertos
    if args.historicos_inicio:
        cfg["historicos_inicio"] = args.historicos_inicio
    if args.historicos_fin:
        cfg["historicos_fin"] = args.historicos_fin

    clients = load_merged_clients(schema)
    if not clients:
        raise SystemExit("[FAIL] No se encontraron clientes en phase-04 / phase-05.")

    products = [p for p in load_catalog_products(schema) if p["is_mock"]]
    if not products:
        raise SystemExit("[FAIL] No se encontraron productos mock en phase-01-productos.csv.")

    prices = load_prices(schema)
    promos = load_promotions(schema)

    open_clients_count = len([c for c in clients if not c["is_prospect"]]) or len(clients)
    open_count = parse_int(cfg.get("abiertos"), DEFAULT_OPEN_ORDERS)
    open_count = min(max(open_count, 6), open_clients_count)

    orders_hist, items_hist = build_historic_orders(schema, clients, products, prices, cfg)
    orders_open, items_open = build_open_orders(schema, clients, products, prices, promos, cfg, open_count)

    orders_rows = orders_hist + orders_open
    items_rows = items_hist + items_open

    output_dir = ctx["paths"]["outputs"]
    orders_path = output_dir / "phase-06-pedidos.csv"
    items_path = output_dir / "phase-06-items-pedido.csv"

    write_csv_rows(
        orders_path,
        orders_rows,
        [
            "pedido_ref",
            "cliente_codigo",
            "cliente_phone",
            "cliente_razon_social",
            "fecha",
            "estado",
            "total",
            "notas",
            "is_mock",
            "es_pedido_abierto",
            "lista_precios_id",
        ],
    )
    write_csv_rows(
        items_path,
        items_rows,
        [
            "pedido_ref",
            "cliente_phone",
            "cliente_codigo",
            "product_code",
            "nombre",
            "cantidad_solicitada",
            "precio_unitario",
            "lista_precios_id",
            "notas",
            "is_mock",
            "es_pedido_abierto",
            "promo_aplicada",
        ],
    )

    open_orders_count = sum(1 for row in orders_rows if row["es_pedido_abierto"] == "true")
    print(f"[*] CSV generado: {orders_path}")
    print(f"[*] CSV generado: {items_path}")
    print(f"[*] Pedidos historicos: {len(orders_hist)}")
    print(f"[*] Pedidos abiertos:    {open_orders_count}")
    print(f"[*] Lineas de items:     {len(items_rows)}")
    print("[*] Siguiente paso:")
    print(f"    python scripts/fase-06-pedidos/cargar_pedidos.py --esquema {schema}")


if __name__ == "__main__":
    main()
