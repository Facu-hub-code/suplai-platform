#!/usr/bin/env python3
"""Connecta rawson a Sistel y carga el espejo (misma ruta que /erp/connect + load-*).

Requiere el venv del backend y su .env (Fernet + pooler 6543):

    cd backend-supabase
    source venv/bin/activate
    PYTHONPATH=. python ../suplai-platform/implementacion/rawson/scripts/connect_and_load_sistel.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parents[3]
TENANT_DIR = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PLATFORM_ROOT.parent / "backend-supabase"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip().strip("'\""))


_load_dotenv(TENANT_DIR / ".env")
_load_dotenv(BACKEND_ROOT / ".env")
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

SCHEMA = "rawson"
BASE_URL = os.environ.get("SISTEL_BASE_URL", "http://asp12.selfip.net:3448").rstrip("/")
CREDENTIALS = {
    "username": os.environ.get("SISTEL_USER", "SuplaiSales"),
    "password": os.environ.get("SISTEL_PASS", ""),
}


async def main() -> None:
    if not CREDENTIALS["password"]:
        raise SystemExit("Falta SISTEL_PASS en implementacion/rawson/.env")

    from erp.connectors.sistel import SistelConnector
    from erp.services.erp_customer_onboarding_service import sync_customers_to_raw
    from erp.services.erp_sync_service import (
        load_price_lists_to_raw,
        load_prices_to_raw,
        load_products_to_raw,
        save_erp_config,
        sync_orders_to_raw,
    )

    connector = SistelConnector(base_url=BASE_URL, credentials=CREDENTIALS)
    products = await connector.fetch_products()
    print(f"[smoke] fetch_products={len(products)}")
    if not products:
        raise SystemExit("Sistel no devolvió productos — aborto connect")
    sample = next((p for p in products if p.get("sku") == "23144"), products[0])
    print(f"[smoke] muestra sku={sample['sku']} nombre={sample['nombre']}")

    await save_erp_config(
        SCHEMA,
        connector="sistel",
        base_url=BASE_URL,
        credentials=CREDENTIALS,
        sync_frequency="6h",
        push_orders_enabled=False,
    )
    print("[connect] config guardada")

    products_raw = await load_products_to_raw(SCHEMA)
    print(f"[load-products] {products_raw}")

    lists_raw = await load_price_lists_to_raw(SCHEMA)
    print(f"[load-price-lists] {lists_raw}")

    prices_raw = await load_prices_to_raw(SCHEMA)
    print(f"[load-prices] {prices_raw}")

    customers_raw = await sync_customers_to_raw(SCHEMA)
    print(f"[load-customers] {customers_raw}")

    orders_raw = await sync_orders_to_raw(SCHEMA, days=365, force=True)
    print(f"[sync-orders] {orders_raw}")


if __name__ == "__main__":
    asyncio.run(main())
