#!/usr/bin/env python3
"""Fase 10 — PURGE MOCK rawson. Solo filas is_mock (+ hijos que bloquean FK).

    cd backend-supabase
    source venv/bin/activate
    PYTHONPATH=. python ../suplai-platform/implementacion/rawson/scripts/purga_mock.py
"""

from __future__ import annotations

import asyncio
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parents[3]
TENANT_DIR = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PLATFORM_ROOT.parent / "backend-supabase"
SCHEMA = "rawson"
TENANT_ID = "cba04456-bd69-434c-b257-9e8fcf12b144"
OUT = TENANT_DIR / "outputs" / "phase-10-purga-log.csv"


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


def _n(status: str) -> int:
    try:
        return int(str(status).split()[-1])
    except (TypeError, ValueError, IndexError):
        return 0


async def main() -> None:
    from core.db import get_connection, validate_schema

    log: list[dict] = []
    conn = await get_connection()
    try:
        schema = await validate_schema(SCHEMA, conn=conn)
        if schema != SCHEMA:
            raise SystemExit(f"schema inesperado: {schema}")

        async def run(tabla: str, sql: str, *args: object, notes: str = "") -> int:
            try:
                deleted = _n(await conn.execute(sql, *args))
                log.append({"tabla": tabla, "filas_borradas": deleted, "ok": "true", "notes": notes})
                print(f"[ok] {tabla} deleted={deleted} {notes}")
                return deleted
            except Exception as exc:
                log.append({"tabla": tabla, "filas_borradas": 0, "ok": "false", "notes": str(exc)})
                print(f"[fail] {tabla} {exc}")
                raise

        await run(
            "rawson.items_pedido",
            f'DELETE FROM "{schema}".items_pedido WHERE is_mock = true',
        )
        await run(
            "rawson.items_pedido",
            f"""
            DELETE FROM "{schema}".items_pedido
            WHERE pedido_id IN (
                SELECT id FROM "{schema}".pedidos
                WHERE is_mock = true
                   OR cliente_id IN (SELECT id FROM "{schema}".clients WHERE is_mock = true)
            )
            """,
            notes="hijos de pedidos mock o cliente mock",
        )
        await run(
            "core.conversation_events",
            """
            DELETE FROM core.conversation_events
            WHERE tenant_id = $1::uuid
              AND event_payload->>'is_mock' = 'true'
            """,
            TENANT_ID,
        )
        await run(
            "core.conversations",
            """
            DELETE FROM core.conversations c
            WHERE c.tenant_id = $1::uuid
              AND NOT EXISTS (
                  SELECT 1 FROM core.conversation_events e
                  WHERE e.conversation_id = c.id
              )
            """,
            TENANT_ID,
            notes="conversaciones demo sin eventos restantes",
        )
        await run(
            "rawson.pedidos",
            f'DELETE FROM "{schema}".pedidos WHERE is_mock = true',
        )
        await run(
            "rawson.pedidos",
            f"""
            DELETE FROM "{schema}".pedidos
            WHERE cliente_id IN (SELECT id FROM "{schema}".clients WHERE is_mock = true)
            """,
            notes="pedidos de clientes mock (is_mock=false)",
        )
        await run(
            "rawson.ia_tickets",
            f'DELETE FROM "{schema}".ia_tickets WHERE is_mock = true',
        )
        await run(
            "rawson.ia_tickets",
            f"""
            DELETE FROM "{schema}".ia_tickets
            WHERE client_id IN (
                SELECT id::text FROM "{schema}".clients WHERE is_mock = true
                UNION
                SELECT phone_number FROM "{schema}".clients
                WHERE is_mock = true AND phone_number IS NOT NULL
            )
            """,
            notes="tickets operativos de clientes mock",
        )
        await run(
            "rawson.vendedor_geo_zones",
            f'DELETE FROM "{schema}".vendedor_geo_zones WHERE is_mock = true',
        )
        await run(
            "rawson.puntos_venta",
            f'DELETE FROM "{schema}".puntos_venta WHERE is_mock = true',
        )
        await run(
            "rawson.client_operating_profiles",
            f"""
            DELETE FROM "{schema}".client_operating_profiles
            WHERE client_id IN (SELECT id FROM "{schema}".clients WHERE is_mock = true)
            """,
            notes="hijos de clients mock",
        )
        await run(
            "rawson.cliente_producto_favorito",
            f"""
            DELETE FROM "{schema}".cliente_producto_favorito
            WHERE cliente_id IN (SELECT id FROM "{schema}".clients WHERE is_mock = true)
               OR product_code IN (SELECT product_code FROM "{schema}".productos WHERE is_mock = true)
            """,
            notes="hijos mock",
        )
        await run(
            "rawson.client_locations",
            f"""
            DELETE FROM "{schema}".client_locations
            WHERE client_id IN (SELECT id FROM "{schema}".clients WHERE is_mock = true)
            """,
            notes="hijos de clients mock",
        )
        await run(
            "rawson.clientes_aliases",
            f"""
            DELETE FROM "{schema}".clientes_aliases
            WHERE client_id IN (SELECT id FROM "{schema}".clients WHERE is_mock = true)
            """,
            notes="hijos de clients mock",
        )
        await run(
            "rawson.clients",
            f'DELETE FROM "{schema}".clients WHERE is_mock = true',
        )
        await run(
            "rawson.geo_zones",
            f'DELETE FROM "{schema}".geo_zones WHERE is_mock = true',
        )
        await run(
            "rawson.vendedores",
            f'DELETE FROM "{schema}".vendedores WHERE is_mock = true',
        )
        await run(
            "rawson.promociones_semanales",
            f'DELETE FROM "{schema}".promociones_semanales WHERE is_mock = true',
        )
        await run(
            "rawson.precios_productos",
            f'DELETE FROM "{schema}".precios_productos WHERE is_mock = true',
        )
        await run(
            "rawson.product_tags",
            f"""
            DELETE FROM "{schema}".product_tags
            WHERE product_code IN (SELECT product_code FROM "{schema}".productos WHERE is_mock = true)
            """,
            notes="tags de productos mock",
        )
        await run(
            "rawson.productos_aliases",
            f"""
            DELETE FROM "{schema}".productos_aliases
            WHERE product_code IN (SELECT product_code FROM "{schema}".productos WHERE is_mock = true)
            """,
        )
        await run(
            "rawson.documents",
            f"""
            DELETE FROM "{schema}".documents
            WHERE metadata->>'product_code' IN (
                SELECT product_code FROM "{schema}".productos WHERE is_mock = true
            )
            """,
            notes="vectores de productos mock",
        )
        await run(
            "rawson.productos",
            f'DELETE FROM "{schema}".productos WHERE is_mock = true',
        )
        await run(
            "public.tenant_cross_sell_mappings",
            """
            DELETE FROM public.tenant_cross_sell_mappings
            WHERE tenant_id = $1::uuid AND is_mock = true
            """,
            TENANT_ID,
        )
        await run(
            "public.tenant_up_sell_mappings",
            """
            DELETE FROM public.tenant_up_sell_mappings
            WHERE tenant_id = $1::uuid AND is_mock = true
            """,
            TENANT_ID,
        )

        verify = {
            "productos_mock": await conn.fetchval(
                f'SELECT count(*) FROM "{schema}".productos WHERE is_mock = true'
            ),
            "productos_reales": await conn.fetchval(
                f'SELECT count(*) FROM "{schema}".productos WHERE is_mock = false'
            ),
            "productos_con_foto": await conn.fetchval(
                f"""
                SELECT count(*) FROM "{schema}".productos
                WHERE is_mock = false AND image_url IS NOT NULL AND length(trim(image_url)) > 0
                """
            ),
            "clients": await conn.fetchval(f'SELECT count(*) FROM "{schema}".clients'),
            "pedidos": await conn.fetchval(f'SELECT count(*) FROM "{schema}".pedidos'),
            "items_pedido": await conn.fetchval(f'SELECT count(*) FROM "{schema}".items_pedido'),
            "ia_tickets": await conn.fetchval(f'SELECT count(*) FROM "{schema}".ia_tickets'),
            "precios": await conn.fetchval(f'SELECT count(*) FROM "{schema}".precios_productos'),
            "listas": await conn.fetchval(f'SELECT count(*) FROM "{schema}".listas_precios'),
        }
        print(f"[verify] {verify}")
        if int(verify["productos_mock"] or 0) != 0:
            raise SystemExit("quedaron productos mock")
        if int(verify["clients"] or 0) != 0:
            raise SystemExit("quedaron clients")
    finally:
        await conn.close()

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["tabla", "filas_borradas", "ok", "notes"])
        writer.writeheader()
        writer.writerows(log)
        writer.writerow(
            {
                "tabla": "_verify",
                "filas_borradas": 0,
                "ok": "true",
                "notes": str(verify),
            }
        )
    print(f"[log] {OUT} at={datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
