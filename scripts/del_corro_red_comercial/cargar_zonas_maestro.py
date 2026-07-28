#!/usr/bin/env python3
"""Carga vendedores + geo_zones (anillo clientes) + asignación PdV/clientes para Campi (del_corro).

Lee CSVs en implementacion/del_corro/outputs/:
  - phase-04-vendedores-real.csv
  - phase-04-zonas-real.csv
  - phase-04-clientes-zona.csv

Reutiliza vendedor con codigo_ruta=5 (Roberto). Mantiene Facundo sin ruta.
Elimina zonas existentes del tenant antes de insertar las nuevas.

Uso:
  set -a && source ../backend-supabase/.env && set +a
  python scripts/del_corro_red_comercial/cargar_zonas_maestro.py
"""

from __future__ import annotations

import asyncio
import csv
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "implementacion" / "del_corro" / "outputs"
SCHEMA = "del_corro"

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend-supabase" / ".env")


def _db_url() -> str:
    url = (
        os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL / DATABASE_URL en .env")
    # Forzar pooler 6543 si viene 5432
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    return url


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


async def main() -> int:
    vendedores = _read_csv(OUT / "phase-04-vendedores-real.csv")
    zonas = _read_csv(OUT / "phase-04-zonas-real.csv")
    clientes = _read_csv(OUT / "phase-04-clientes-zona.csv")

    print(f"[*] vendedores={len(vendedores)} zonas={len(zonas)} asignaciones={len(clientes)}")
    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        await conn.execute(f"SET search_path TO {SCHEMA}, core, public, extensions")

        async with conn.transaction():
            # 1) Desasignar PdV de zonas viejas
            n = await conn.fetchval(
                f"""
                WITH u AS (
                  UPDATE {SCHEMA}.puntos_venta
                  SET geo_zone_id = NULL,
                      geo_zone_asignacion = 'auto',
                      geo_zone_asignado_at = NULL,
                      updated_at = NOW()
                  WHERE geo_zone_id IS NOT NULL
                  RETURNING 1
                )
                SELECT COUNT(*) FROM u
                """
            )
            print(f"[*] PdV desasignados: {n}")

            # 2) Borrar vínculos y zonas existentes
            await conn.execute(f"DELETE FROM {SCHEMA}.vendedor_geo_zones")
            deleted_zones = await conn.fetchval(
                f"WITH d AS (DELETE FROM {SCHEMA}.geo_zones RETURNING 1) SELECT COUNT(*) FROM d"
            )
            print(f"[*] Zonas eliminadas: {deleted_zones}")

            # 3) Upsert vendedores por codigo_ruta (reusa V5 / Roberto)
            codigo_to_vid: dict[str, int] = {}
            for row in vendedores:
                codigo = str(row["codigo_ruta"]).strip()
                existing = await conn.fetchrow(
                    f"""
                    SELECT id, nombre FROM {SCHEMA}.vendedores
                    WHERE codigo_ruta = $1
                    LIMIT 1
                    """,
                    codigo,
                )
                if existing:
                    await conn.execute(
                        f"""
                        UPDATE {SCHEMA}.vendedores
                        SET activo = true,
                            is_mock = false,
                            updated_at = NOW()
                        WHERE id = $1
                        """,
                        int(existing["id"]),
                    )
                    codigo_to_vid[codigo] = int(existing["id"])
                    print(f"  reuse vendedor codigo={codigo} id={existing['id']} nombre={existing['nombre']}")
                else:
                    # telefono NOT NULL en del_corro.vendedores — placeholder único por ruta
                    phone = (row.get("telefono") or "").strip() or f"5493519{int(codigo):04d}"
                    email = (row.get("email") or "").strip() or None
                    vid = await conn.fetchval(
                        f"""
                        INSERT INTO {SCHEMA}.vendedores
                          (nombre, telefono, email, activo, codigo_ruta, is_mock)
                        VALUES ($1, $2, $3, true, $4, false)
                        RETURNING id
                        """,
                        row["nombre"].strip(),
                        phone,
                        email,
                        codigo,
                    )
                    codigo_to_vid[codigo] = int(vid)
                    print(f"  insert vendedor codigo={codigo} id={vid} tel={phone}")

            # 4) Insertar zonas con geometría
            zona_to_id: dict[str, int] = {}
            for z in zonas:
                codigo_zona = str(z["codigo_zona"]).strip()
                vend_codigo = str(z["vendedor_codigo"]).strip()
                vid = codigo_to_vid[vend_codigo]
                wkt = (z.get("geometry_wkt") or "").strip()
                if not wkt:
                    raise RuntimeError(f"Zona {codigo_zona} sin geometry_wkt")
                zid = await conn.fetchval(
                    f"""
                    INSERT INTO {SCHEMA}.geo_zones (
                      name, zone_type, description, color, geometry,
                      active, metadata, dia_visita, dias_visita, codigo_ruta,
                      vendedor_principal_id, is_mock
                    )
                    VALUES (
                      $1, $2, $3, $4,
                      ST_SetSRID(ST_GeomFromText($5), 4326),
                      true,
                      $6::jsonb,
                      $7::dia_de_visita_enum,
                      ARRAY[$7::dia_de_visita_enum],
                      $8,
                      $9,
                      false
                    )
                    RETURNING id
                    """,
                    z["nombre"],
                    z["zone_type"],
                    z["description"],
                    z["color"],
                    wkt,
                    f'{{"erp_zona":{codigo_zona},"source":"maestro_clientes_2026-02-21"}}',
                    z["dia_visita"],
                    vend_codigo,
                    vid,
                )
                zona_to_id[codigo_zona] = int(zid)
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.vendedor_geo_zones (vendedor_id, geo_zone_id, activo, is_mock)
                    VALUES ($1, $2, true, false)
                    ON CONFLICT (vendedor_id, geo_zone_id) DO UPDATE
                      SET activo = true, updated_at = NOW()
                    """,
                    vid,
                    int(zid),
                )
            print(f"[*] Zonas insertadas: {len(zona_to_id)}")

            # 5) Asignar clientes → PdV → zona + día + vendedor_clientes (bulk)
            vids = list(codigo_to_vid.values())
            deleted_vc = await conn.fetchval(
                f"""
                WITH d AS (
                  DELETE FROM {SCHEMA}.vendedores_clientes
                  WHERE vendedor_id = ANY($1::int[])
                  RETURNING 1
                )
                SELECT COUNT(*) FROM d
                """,
                vids,
            )
            print(f"[*] vendedores_clientes borrados (rutas): {deleted_vc}")

            await conn.execute(
                """
                CREATE TEMP TABLE _campi_zona_map (
                  codigo_cliente numeric NOT NULL,
                  geo_zone_id bigint NOT NULL,
                  vendedor_id int NOT NULL,
                  vendedor_codigo text NOT NULL,
                  dia_visita text NOT NULL
                ) ON COMMIT DROP
                """
            )
            map_rows: list[tuple] = []
            for row in clientes:
                codigo_zona = str(row["codigo_zona"]).strip()
                vend_codigo = str(row["vendedor_codigo"]).strip()
                map_rows.append(
                    (
                        int(row["codigo_cliente"]),
                        zona_to_id[codigo_zona],
                        codigo_to_vid[vend_codigo],
                        vend_codigo,
                        row["dia_visita"],
                    )
                )
            await conn.copy_records_to_table(
                "_campi_zona_map",
                records=map_rows,
                columns=[
                    "codigo_cliente",
                    "geo_zone_id",
                    "vendedor_id",
                    "vendedor_codigo",
                    "dia_visita",
                ],
            )

            assigned_pdv = await conn.fetchval(
                f"""
                WITH matched AS (
                  SELECT c.id AS client_id, c.pdv_id, m.*
                  FROM _campi_zona_map m
                  JOIN {SCHEMA}.clients c ON c.codigo = m.codigo_cliente
                  WHERE c.pdv_id IS NOT NULL
                ),
                upd_pv AS (
                  UPDATE {SCHEMA}.puntos_venta pv
                  SET geo_zone_id = matched.geo_zone_id,
                      vendedor_id = matched.vendedor_id,
                      dia_de_visita = matched.dia_visita::dia_de_visita_enum,
                      geo_zone_asignacion = 'manual',
                      geo_zone_asignado_at = NOW(),
                      updated_at = NOW()
                  FROM matched
                  WHERE pv.id = matched.pdv_id
                  RETURNING pv.id
                )
                SELECT COUNT(*) FROM upd_pv
                """
            )
            assigned_cli = await conn.fetchval(
                f"""
                WITH matched AS (
                  SELECT c.id AS client_id, m.vendedor_codigo, m.dia_visita
                  FROM _campi_zona_map m
                  JOIN {SCHEMA}.clients c ON c.codigo = m.codigo_cliente
                ),
                upd AS (
                  UPDATE {SCHEMA}.clients c
                  SET dia_de_visita = matched.dia_visita::dia_de_visita_enum,
                      vendedor = matched.vendedor_codigo,
                      updated_at = NOW()
                  FROM matched
                  WHERE c.id = matched.client_id
                  RETURNING c.id
                )
                SELECT COUNT(*) FROM upd
                """
            )
            inserted_vc = await conn.fetchval(
                f"""
                WITH matched AS (
                  SELECT c.id AS client_id, m.vendedor_id
                  FROM _campi_zona_map m
                  JOIN {SCHEMA}.clients c ON c.codigo = m.codigo_cliente
                ),
                ins AS (
                  INSERT INTO {SCHEMA}.vendedores_clientes (vendedor_id, cliente_id)
                  SELECT DISTINCT matched.vendedor_id, matched.client_id
                  FROM matched
                  ON CONFLICT DO NOTHING
                  RETURNING 1
                )
                SELECT COUNT(*) FROM ins
                """
            )
            missing_client = await conn.fetchval(
                f"""
                SELECT COUNT(*)
                FROM _campi_zona_map m
                LEFT JOIN {SCHEMA}.clients c ON c.codigo = m.codigo_cliente
                WHERE c.id IS NULL
                """
            )
            missing_pdv = await conn.fetchval(
                f"""
                SELECT COUNT(*)
                FROM _campi_zona_map m
                JOIN {SCHEMA}.clients c ON c.codigo = m.codigo_cliente
                WHERE c.pdv_id IS NULL
                """
            )
            print(f"[*] PdV asignados: {assigned_pdv}")
            print(f"[*] Clients actualizados: {assigned_cli}")
            print(f"[*] Cartera insertada: {inserted_vc}")
            print(f"[*] Sin match codigo en BD: {missing_client}")
            print(f"[*] Sin pdv_id: {missing_pdv}")

        # Verificación
        summary = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.vendedores WHERE codigo_ruta IS NOT NULL AND activo) AS vendedores_ruta,
              (SELECT COUNT(*) FROM {SCHEMA}.geo_zones WHERE active) AS zonas_activas,
              (SELECT COUNT(*) FROM {SCHEMA}.vendedor_geo_zones WHERE activo) AS vinculos,
              (SELECT COUNT(*) FROM {SCHEMA}.puntos_venta WHERE geo_zone_id IS NOT NULL) AS pdv_con_zona,
              (SELECT COUNT(*) FROM {SCHEMA}.vendedores_clientes) AS cartera
            """
        )
        print("[OK] summary:", dict(summary))
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
