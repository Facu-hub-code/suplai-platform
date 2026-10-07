#!/usr/bin/env python3
"""Carga los 239 clientes de Aguilar sobre catálogo/zonas ya presentes en esekau."""
from __future__ import annotations

import asyncio
import csv
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA = "esekau"
OUT = Path(__file__).resolve().parents[1] / "outputs"
ROOT = Path(__file__).resolve().parents[3]


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


for path in (
    Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
    ROOT.parent / "backend-supabase" / ".env",
    ROOT / ".env",
):
    if path.exists():
        load_dotenv(path, override=False)


async def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    db_url = force_pooler(os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "")
    clientes = list(csv.DictReader((OUT / "phase-04-clientes.csv").open(encoding="utf-8")))
    vendedores = list(csv.DictReader((OUT / "phase-04-vendedores.csv").open(encoding="utf-8")))
    vrow = vendedores[0]
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        await conn.execute(f"SET search_path TO {SCHEMA}, core, public, extensions")
        await conn.execute(f"DELETE FROM {SCHEMA}.client_locations")
        await conn.execute(f"DELETE FROM {SCHEMA}.vendedores_clientes")
        await conn.execute(f"DELETE FROM {SCHEMA}.clients")
        await conn.execute(f"DELETE FROM {SCHEMA}.puntos_venta")
        vendedor_id = await conn.fetchval(
            f"SELECT id FROM {SCHEMA}.vendedores WHERE NOT is_mock ORDER BY id LIMIT 1"
        )
        zona_ids = {
            r["codigo_ruta"]: r["id"]
            for r in await conn.fetch(f"SELECT id, codigo_ruta FROM {SCHEMA}.geo_zones WHERE NOT is_mock")
        }
        print(f"[*] vendedor_id={vendedor_id} zonas={zona_ids} clientes={len(clientes)}")
        for i, row in enumerate(clientes, 1):
            codigo = int(float(row["cliente_codigo"]))
            geo_zone_id = zona_ids[row["zona_codigo"]]
            pdv_id = await conn.fetchval(
                f"""
                INSERT INTO {SCHEMA}.puntos_venta
                    (razon_social, codigo, lista_precios_id, dia_de_visita,
                     direccion, vendedor, vendedor_id, geo_zone_id, activo_ai, is_mock)
                VALUES ($1,$2,$3,$4::core.dia_de_visita_enum,$5,$6,$7,$8,true,false)
                RETURNING id
                """,
                row["razon_social"],
                codigo,
                1,
                row["dia_de_visita"],
                row.get("direccion") or "",
                vrow["nombre"],
                vendedor_id,
                geo_zone_id,
            )
            cliente_id = await conn.fetchval(
                f"""
                INSERT INTO {SCHEMA}.clients
                    (phone_number, nombre, razon_social, lista_precios_id, codigo,
                     dia_de_visita, vendedor, pdv_id, activo_ai, is_mock,
                     lifecycle, origen_alta, is_primary, etiqueta)
                VALUES ($1,$2,$3,$4,$5,$6::core.dia_de_visita_enum,$7,$8,true,false,
                        'client','erp',true,$9)
                RETURNING id
                """,
                row["phone_number"],
                row["nombre"],
                row["razon_social"],
                1,
                codigo,
                row["dia_de_visita"],
                vrow["nombre"],
                pdv_id,
                row.get("categoria_pg") or None,
            )
            await conn.execute(
                f"INSERT INTO {SCHEMA}.vendedores_clientes (vendedor_id, cliente_id, activo) VALUES ($1,$2,true)",
                vendedor_id,
                cliente_id,
            )
            await conn.execute(
                f"""
                INSERT INTO {SCHEMA}.client_locations
                    (client_id, source, latitude, longitude, location,
                     address_text, geocode_status, is_primary, created_by)
                VALUES (
                    $1, 'backoffice', $2, $3,
                    extensions.ST_SetSRID(extensions.ST_MakePoint($3, $2), 4326),
                    $4, 'not_required', true, 'implementacion'
                )
                """,
                cliente_id,
                float(row["lat"]),
                float(row["lng"]),
                row.get("direccion") or "",
            )
            if i % 40 == 0 or i == len(clientes):
                print(f"    clientes {i}/{len(clientes)}")
        verify = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.clients WHERE lifecycle='client' AND NOT is_mock) AS clients,
              (SELECT COUNT(*) FROM {SCHEMA}.puntos_venta) AS pdv,
              (SELECT COUNT(*) FROM {SCHEMA}.client_locations) AS locs,
              (SELECT COUNT(*) FROM {SCHEMA}.vendedores_clientes) AS vinculos
            """
        )
        print(f"[VERIFY] {dict(verify)}")
        if verify["clients"] != 239 or verify["locs"] != 239:
            print("[FAIL] conteos clientes")
            return 1
    finally:
        await conn.close()
    print(f"[SUCCESS] cartera {SCHEMA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
