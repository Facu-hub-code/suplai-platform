#!/usr/bin/env python3
"""
Carga red comercial real el_gigante (is_mock=false).

Orden: vendedores → geo_zones (dias_visita) → vendedor_geo_zones
       → (opcional) clientes Diego/San Francisco + PDV + links + locations.

Uso:
  python scripts/el_gigante_red_comercial/cargar_red_real.py --esquema el_gigante
  python scripts/el_gigante_red_comercial/cargar_red_real.py --esquema el_gigante --con-clientes
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

import asyncpg
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
load_dotenv()

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


def _pooler_url(url: str) -> str:
    # Prefer transaction pooler 6543
    if ":5432/" in url:
        return url.replace(":5432/", ":6543/")
    return url



def _geocode_status(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if s in ("resolved", "excel", "nominatim", "ok"):
        return "resolved"
    if s in ("pending", "not_required", "failed"):
        return s
    if s in ("nominatim_zero", "request_denied", "zero_results"):
        return "failed"
    return "resolved" if s else "pending"

def _parse_dias(raw: str) -> list[str]:
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    canon = {
        "miercoles": "miércoles",
        "miércoles": "miércoles",
        "sabado": "sábado",
        "sábado": "sábado",
    }
    out = []
    for p in parts:
        p = p.lower()
        out.append(canon.get(p, p))
    return out or ["lunes"]


async def main_async(esquema: str, con_clientes: bool) -> None:
    db_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("Falta SUPABASE_DB_URL en .env")
    db_url = _pooler_url(db_url)

    base = ROOT / "implementacion" / esquema
    vcsv = base / "outputs" / "phase-04-vendedores-real.csv"
    zcsv = base / "outputs" / "phase-04-zonas-real.csv"
    ccsv = base / "outputs" / "phase-04-clientes-diego-san-francisco.csv"
    for p in (vcsv, zcsv):
        if not p.exists():
            raise SystemExit(f"Falta {p}. Corré preparar_vendedores_zonas.py primero.")

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute(f"SET search_path TO {esquema}, core, public, extensions")

        # Vendedores upsert by codigo_ruta / nombre
        vendedores = list(csv.DictReader(vcsv.open(encoding="utf-8")))
        vendedor_ids: list[int] = []
        print(f"[*] Upsert {len(vendedores)} vendedores...")
        for v in vendedores:
            row = await conn.fetchrow(
                f"""
                SELECT id FROM {esquema}.vendedores
                WHERE codigo_ruta = $1 OR nombre = $2
                ORDER BY id LIMIT 1
                """,
                v["codigo_ruta"],
                v["nombre"],
            )
            if row:
                await conn.execute(
                    f"""
                    UPDATE {esquema}.vendedores
                    SET telefono=$2, email=$3, codigo_ruta=$4, is_mock=false, activo=true, updated_at=now()
                    WHERE id=$1
                    """,
                    int(row["id"]),
                    v["telefono"],
                    v["email"],
                    v["codigo_ruta"],
                )
                vid = int(row["id"])
            else:
                vid = int(
                    await conn.fetchval(
                        f"""
                        INSERT INTO {esquema}.vendedores
                          (nombre, telefono, email, zona, codigo_ruta, activo, is_mock)
                        VALUES ($1, $2, $3, $4, $5, true, false)
                        RETURNING id
                        """,
                        v["nombre"],
                        v["telefono"],
                        v["email"],
                        v.get("zona") or None,
                        v["codigo_ruta"],
                    )
                )
            vendedor_ids.append(vid)
            print(f"  + {v['nombre']} id={vid}")

        # Zonas
        zonas = list(csv.DictReader(zcsv.open(encoding="utf-8")))
        print(f"[*] Upsert {len(zonas)} geo_zones...")
        zone_ids: dict[tuple[int, str], int] = {}
        for z in zonas:
            vidx = int(z["vendedor_idx"])
            vid = vendedor_ids[vidx]
            dias = _parse_dias(z.get("dias_visita") or z.get("dia_visita") or "lunes")
            primary = dias[0]
            wkt = z.get("geometry_wkt") or ""
            existing = await conn.fetchrow(
                f"""
                SELECT id FROM {esquema}.geo_zones
                WHERE name = $1 AND vendedor_principal_id = $2
                LIMIT 1
                """,
                z["nombre"],
                vid,
            )
            if existing:
                zid = int(existing["id"])
                await conn.execute(
                    f"""
                    UPDATE {esquema}.geo_zones SET
                      zone_type = $2,
                      dia_visita = $3::core.dia_de_visita_enum,
                      dias_visita = $4::core.dia_de_visita_enum[],
                      codigo_ruta = $5,
                      color = $6,
                      geometry = CASE WHEN $7 = '' THEN geometry
                        ELSE ST_Multi(ST_SetSRID(ST_GeomFromEWKT($7), 4326)) END,
                      active = true,
                      is_mock = false,
                      updated_at = now()
                    WHERE id = $1
                    """,
                    zid,
                    z.get("zone_type") or "route",
                    primary,
                    dias,
                    z.get("codigo_ruta"),
                    z.get("color") or "#39FF14",
                    wkt,
                )
            else:
                zid = int(
                    await conn.fetchval(
                        f"""
                        INSERT INTO {esquema}.geo_zones
                          (name, zone_type, description, color, geometry, active, metadata,
                           dia_visita, dias_visita, codigo_ruta, vendedor_principal_id, is_mock)
                        VALUES (
                          $1, $2, $3, $4,
                          ST_Multi(ST_SetSRID(ST_GeomFromEWKT($5), 4326)),
                          true, '{{}}'::jsonb,
                          $6::core.dia_de_visita_enum,
                          $7::core.dia_de_visita_enum[],
                          $8, $9, false
                        )
                        RETURNING id
                        """,
                        z["nombre"],
                        z.get("zone_type") or "route",
                        f"Ruta {z.get('codigo_ruta')}",
                        z.get("color") or "#39FF14",
                        wkt,
                        primary,
                        dias,
                        z.get("codigo_ruta"),
                        vid,
                    )
                )
            zone_ids[(vidx, z["nombre"].strip().lower())] = zid
            await conn.execute(
                f"""
                INSERT INTO {esquema}.vendedor_geo_zones (vendedor_id, geo_zone_id, activo)
                VALUES ($1, $2, true)
                ON CONFLICT (vendedor_id, geo_zone_id) DO UPDATE SET activo = true
                """,
                vid,
                zid,
            )
            print(f"  + zona {z['nombre']} dias={dias} id={zid}")

        if not con_clientes:
            print("[*] Sin --con-clientes: solo vendedores/zonas.")
            return

        if not ccsv.exists():
            raise SystemExit(f"Falta {ccsv}. Corré geocode_y_poligono_zona.py")

        diego_idx = next(i for i, v in enumerate(vendedores) if v["nombre"].strip().lower() == "diego")
        diego_id = vendedor_ids[diego_idx]
        zid_sf = zone_ids.get((diego_idx, "san francisco"))
        if not zid_sf:
            raise SystemExit("No encontré zona San Francisco para Diego")

        clients = list(csv.DictReader(ccsv.open(encoding="utf-8")))
        print(f"[*] Cargando {len(clients)} clientes San Francisco → Diego...")
        loaded = 0
        skipped = 0
        for c in clients:
            lat = c.get("lat") or None
            lng = c.get("lng") or None
            lat_f = float(lat) if lat not in (None, "", "None") else None
            lng_f = float(lng) if lng not in (None, "", "None") else None
            phone = re.sub(r"\D", "", c.get("phone_number") or "")
            if phone and not phone.startswith("549"):
                phone = "549" + phone.lstrip("0")
            if not phone:
                phone = f"5493700{int(float(c['codigo'])):07d}"[-13:]

            codigo_num = None
            try:
                codigo_num = float(c["codigo"])
            except Exception:
                pass

            existing_cli = await conn.fetchval(
                f"""
                SELECT id FROM {esquema}.clients
                WHERE is_mock = false AND (
                  (codigo IS NOT NULL AND codigo = $1)
                  OR phone_number = $2
                )
                ORDER BY id LIMIT 1
                """,
                codigo_num,
                phone,
            )
            if existing_cli:
                skipped += 1
                continue

            pdv_id = await conn.fetchval(
                f"""
                INSERT INTO {esquema}.puntos_venta
                  (razon_social, codigo, lista_precios_id, dia_de_visita, dia_de_entrega,
                   direccion, vendedor_id, geo_zone_id, geo_zone_asignacion, is_mock)
                VALUES (
                  $1, $2, $3,
                  $4::core.dia_de_visita_enum,
                  $5::core.dia_de_entrega_enum,
                  $6, $7, $8, 'manual', false
                )
                RETURNING id
                """,
                c.get("razon_social") or c.get("nombre"),
                codigo_num,
                int(c.get("lista_precios_id") or 1),
                c.get("dia_de_visita") or "lunes",
                c.get("dia_de_entrega") or "martes",
                c.get("domicilio") or "",
                diego_id,
                zid_sf,
            )

            partner_erp = None
            try:
                partner_erp = int(float(c["codigo"]))
            except Exception:
                pass

            cliente_id = await conn.fetchval(
                f"""
                INSERT INTO {esquema}.clients
                  (phone_number, nombre, razon_social, lista_precios_id, codigo,
                   dia_de_visita, dia_de_entrega, direccion, cuit, vendedor,
                   pdv_id, is_primary, activo_ai, is_mock, partner_erp_id)
                VALUES (
                  $1, $2, $3, $4, $5,
                  $6::core.dia_de_visita_enum,
                  $7::core.dia_de_entrega_enum,
                  $8, $9, $10,
                  $11, true, true, false, $12
                )
                RETURNING id
                """,
                phone,
                c.get("nombre") or c.get("razon_social"),
                c.get("razon_social"),
                int(c.get("lista_precios_id") or 1),
                codigo_num,
                c.get("dia_de_visita") or "lunes",
                c.get("dia_de_entrega") or "martes",
                c.get("domicilio") or "",
                c.get("cuit") or None,
                "Diego",
                pdv_id,
                partner_erp,
            )

            await conn.execute(
                f"""
                INSERT INTO {esquema}.vendedores_clientes (vendedor_id, cliente_id, activo)
                VALUES ($1, $2, true)
                ON CONFLICT (vendedor_id, cliente_id) DO UPDATE SET activo = true
                """,
                diego_id,
                cliente_id,
            )

            if lat_f is not None and lng_f is not None:
                await conn.execute(
                    f"""
                    INSERT INTO {esquema}.client_locations
                      (client_id, source, address_text, latitude, longitude, location,
                       geocode_status, is_primary, created_by)
                    VALUES (
                      $1, 'migration', $2, $3, $4,
                      ST_SetSRID(ST_MakePoint($4::float8, $3::float8), 4326),
                      $5, true, 'agent'
                    )
                    """,
                    cliente_id,
                    c.get("domicilio") or "",
                    lat_f,
                    lng_f,
                    _geocode_status(c.get("geocode_status")),
                )
            loaded += 1

        print(f"✅ Clientes cargados: {loaded} (omitidos existentes: {skipped})")
        counts = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {esquema}.vendedores WHERE is_mock = false) AS vendedores,
              (SELECT COUNT(*) FROM {esquema}.geo_zones WHERE is_mock = false) AS zonas,
              (SELECT COUNT(*) FROM {esquema}.clients WHERE is_mock = false) AS clients
            """
        )
        print(dict(counts))
    finally:
        await conn.close()


def main() -> None:
    import asyncio

    ap = argparse.ArgumentParser()
    ap.add_argument("--esquema", default="el_gigante")
    ap.add_argument("--con-clientes", action="store_true")
    args = ap.parse_args()
    asyncio.run(main_async(args.esquema, args.con_clientes))


if __name__ == "__main__":
    main()
