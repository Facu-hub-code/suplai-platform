#!/usr/bin/env python3
"""Carga clientes piloto Almaro (teléfonos únicos del Excel) con lista GEV."""
from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
CSV_IN = OUT / "phase-04-clientes-piloto.csv"
SCHEMA = "almaro"
DEFAULT_LISTA = 20  # TRADICIONAL


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


async def main() -> int:
    load_dotenv(ROOT.parent / "backend-supabase" / ".env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)

    rows = list(csv.DictReader(CSV_IN.open(encoding="utf-8")))
    codes = [r["codigo"] for r in rows]
    codes_int = [r["codigo_int"] for r in rows]

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute(
            "ALTER TABLE almaro.clients ALTER COLUMN lista_precios_id SET DEFAULT 20"
        )
        await conn.execute(
            "ALTER TABLE almaro.puntos_venta ALTER COLUMN lista_precios_id SET DEFAULT 20"
        )

        gev = await conn.fetch(
            """
            SELECT
              r.raw_payload #>> '{extra,id_cuenta}' AS id_cuenta,
              r.raw_payload #>> '{extra,cliente_codigo}' AS cliente_codigo,
              r.raw_payload #>> '{extra,lista_precios_erp_id}' AS lista_erp,
              r.raw_payload #>> '{extra,vendedor_codigo}' AS vendedor_codigo,
              r.raw_payload #>> '{extra,vendedor_nombre}' AS vendedor_nombre,
              lp.id AS lista_precios_id,
              v.id AS vendedor_id
            FROM almaro.erp_customers_raw r
            LEFT JOIN almaro.listas_precios lp
              ON lp.erp_list_id = r.raw_payload #>> '{extra,lista_precios_erp_id}'
            LEFT JOIN almaro.vendedores v
              ON v.erp_codigo = r.raw_payload #>> '{extra,vendedor_codigo}'
            WHERE r.raw_payload #>> '{extra,id_cuenta}' = ANY($1::text[])
               OR r.raw_payload #>> '{extra,cliente_codigo}' = ANY($2::text[])
            """,
            codes,
            codes_int,
        )
        by_cuenta = {str(r["id_cuenta"]): r for r in gev}
        by_codigo = {str(r["cliente_codigo"]): r for r in gev}

        loaded = []
        async with conn.transaction():
            for row in rows:
                match = by_cuenta.get(row["codigo"]) or by_codigo.get(row["codigo_int"])
                if not match:
                    print(f"[FAIL] sin match GEV codigo={row['codigo']}")
                    return 1
                lista_id = int(match["lista_precios_id"] or DEFAULT_LISTA)
                vend_id = int(match["vendedor_id"]) if match["vendedor_id"] is not None else None
                vend_name = match["vendedor_nombre"]
                codigo_num = int(row["codigo_int"])
                lat = float(row["lat"]) if row.get("lat") not in (None, "") else None
                lng = float(row["lng"]) if row.get("lng") not in (None, "") else None
                meta = {
                    "origen": "excel_prueba_whatsapp_sep2026",
                    "tokin_id": row.get("tokin_id"),
                    "hoja": row.get("hoja"),
                    "canal": row.get("canal"),
                    "id_cuenta": row["codigo"],
                }
                pdv_id = await conn.fetchval(
                    """
                    INSERT INTO almaro.puntos_venta (
                      razon_social, codigo, lista_precios_id, direccion,
                      vendedor, vendedor_id, activo_ai, is_mock
                    ) VALUES ($1, $2, $3, $4, $5, $6, true, false)
                    RETURNING id
                    """,
                    row["nombre"],
                    codigo_num,
                    lista_id,
                    row["direccion"],
                    vend_name,
                    vend_id,
                )
                client_id = await conn.fetchval(
                    """
                    INSERT INTO almaro.clients (
                      phone_number, nombre, razon_social, lista_precios_id, codigo,
                      activo_ai, vendedor, is_primary, is_mock, partner_erp_id,
                      pdv_id, metadata
                    ) VALUES ($1, $2, $3, $4, $5, true, $6, true, false, $7, $8, $9::jsonb)
                    RETURNING id
                    """,
                    row["phone"],
                    row["nombre"],
                    row["nombre"],
                    lista_id,
                    codigo_num,
                    vend_name,
                    codigo_num,
                    pdv_id,
                    json.dumps(meta, ensure_ascii=False),
                )
                if lat is not None and lng is not None:
                    await conn.execute(
                        """
                        INSERT INTO almaro.client_locations (
                          client_id, source, latitude, longitude, location,
                          address_text, name, is_primary, geocode_status, created_by
                        ) VALUES (
                          $1, 'migration', $2, $3,
                          ST_SetSRID(ST_MakePoint($3::float8, $2::float8), 4326),
                          $4, $5, true, 'resolved', 'implementacion-almaro'
                        )
                        """,
                        client_id,
                        lat,
                        lng,
                        row["direccion"],
                        row["nombre"],
                    )
                loaded.append(
                    {
                        **row,
                        "client_id": client_id,
                        "pdv_id": pdv_id,
                        "lista_precios_id": lista_id,
                        "lista_erp": match["lista_erp"],
                        "vendedor": vend_name,
                        "vendedor_id": vend_id,
                    }
                )

        out_fields = list(rows[0].keys()) + [
            "client_id",
            "pdv_id",
            "lista_precios_id",
            "lista_erp",
            "vendedor",
            "vendedor_id",
        ]
        with CSV_IN.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=out_fields)
            w.writeheader()
            for r in loaded:
                w.writerow({k: r.get(k, "") for k in out_fields})

        n = await conn.fetchval("SELECT COUNT(*) FROM almaro.clients")
        sample = await conn.fetch(
            """
            SELECT id, phone_number, razon_social, codigo, lista_precios_id, vendedor
            FROM almaro.clients ORDER BY id LIMIT 3
            """
        )
        print(f"OK cargados={len(loaded)} clients_total={n}")
        for s in sample:
            print(f"  sample {s['id']} {s['razon_social'][:40]} lista={s['lista_precios_id']} tel=...{str(s['phone_number'])[-4:]}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
