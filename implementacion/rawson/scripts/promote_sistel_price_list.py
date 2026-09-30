#!/usr/bin/env python3
"""Promueve catálogo Sistel, deja Lista Sistel operativa y elimina listas mock.

    cd backend-supabase
    source venv/bin/activate
    PYTHONPATH=. python ../suplai-platform/implementacion/rawson/scripts/promote_sistel_price_list.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parents[3]
TENANT_DIR = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PLATFORM_ROOT.parent / "backend-supabase"
SCHEMA = "rawson"
MOCK_LIST_IDS = (1, 2, 3, 4)


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


async def _reassign_and_drop_mock(sistel_lista_id: int) -> dict:
    from core.db import get_connection, validate_schema

    conn = await get_connection()
    try:
        schema = await validate_schema(SCHEMA, conn=conn)
        await conn.execute(
            f'UPDATE "{schema}".clients SET lista_precios_id = $1 WHERE lista_precios_id = ANY($2::int[])',
            sistel_lista_id,
            list(MOCK_LIST_IDS),
        )
        clients_n = await conn.fetchval(
            f'SELECT count(*) FROM "{schema}".clients WHERE lista_precios_id = $1',
            sistel_lista_id,
        )
        await conn.execute(
            f'UPDATE "{schema}".puntos_venta SET lista_precios_id = $1 WHERE lista_precios_id = ANY($2::int[])',
            sistel_lista_id,
            list(MOCK_LIST_IDS),
        )
        await conn.execute(
            f'UPDATE "{schema}".promociones_semanales SET lista_precios_id = $1 WHERE lista_precios_id = ANY($2::int[])',
            sistel_lista_id,
            list(MOCK_LIST_IDS),
        )
        await conn.execute(
            f'UPDATE "{schema}".productos SET en_catalogo = false WHERE is_mock = true',
        )
        deleted_prices_status = await conn.execute(
            f'DELETE FROM "{schema}".precios_productos WHERE lista_precios_id = ANY($1::int[])',
            list(MOCK_LIST_IDS),
        )
        remaining_mock_prices = await conn.fetchval(
            f'SELECT count(*) FROM "{schema}".precios_productos WHERE lista_precios_id = ANY($1::int[])',
            list(MOCK_LIST_IDS),
        )
        deleted_lists_status = await conn.execute(
            f'DELETE FROM "{schema}".listas_precios WHERE id = ANY($1::int[]) AND is_mock = true',
            list(MOCK_LIST_IDS),
        )
        await conn.execute(
            f"""
            UPDATE "{schema}".listas_precios
            SET es_publica = false, activa = false, updated_at = now()
            WHERE id = 5 AND erp_list_id IS NULL
            """
        )
        await conn.execute(
            f"""
            UPDATE "{schema}".listas_precios
            SET es_publica = true, activa = true, updated_at = now()
            WHERE id = $1
            """,
            sistel_lista_id,
        )
        lists = await conn.fetch(
            f"""
            SELECT id, nombre, es_publica, is_mock, activa, erp_list_id
            FROM "{schema}".listas_precios
            ORDER BY id
            """
        )
        prices = await conn.fetchval(
            f'SELECT count(*) FROM "{schema}".precios_productos WHERE lista_precios_id = $1',
            sistel_lista_id,
        )
        return {
            "clients_on_sistel": int(clients_n or 0),
            "deleted_prices": deleted_prices_status,
            "deleted_lists": deleted_lists_status,
            "remaining_mock_prices": int(remaining_mock_prices or 0),
            "sistel_prices": int(prices or 0),
            "lists": [dict(r) for r in lists],
        }
    finally:
        await conn.close()


async def main() -> None:
    from erp.services.erp_product_promote_service import promote_erp_products_bulk
    from erp.services.erp_sync_service import link_price_list_raw, sync_prices_from_raw

    preview = await promote_erp_products_bulk(SCHEMA, dry_run=True)
    print(f"[promote dry_run] pending={preview.get('pending')} sample={preview.get('sample')}")

    promoted = await promote_erp_products_bulk(SCHEMA, dry_run=False)
    print(
        f"[promote] created={promoted.get('created')} vectorized={promoted.get('vectorized')} "
        f"errors={len(promoted.get('errors') or [])}"
    )
    if promoted.get("errors"):
        print(f"[promote] error sample={promoted['errors'][:3]}")

    linked = await link_price_list_raw(SCHEMA, 1, create_new=True, nombre="Lista Sistel")
    print(f"[link] {linked}")
    sistel_id = int(linked["lista_precios_id"])

    synced = await sync_prices_from_raw(SCHEMA, lista_precios_id=sistel_id)
    print(f"[sync-prices] {synced}")

    cleanup = await _reassign_and_drop_mock(sistel_id)
    print(f"[cleanup] {cleanup}")


if __name__ == "__main__":
    asyncio.run(main())
