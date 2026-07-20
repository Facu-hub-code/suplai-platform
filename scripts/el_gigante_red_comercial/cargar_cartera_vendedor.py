#!/usr/bin/env python3
"""
Carga cartera preparada de un vendedor + actualiza geometría de sus zonas.

  python scripts/el_gigante_red_comercial/cargar_cartera_vendedor.py --vendedor Ivan
  python scripts/el_gigante_red_comercial/cargar_cartera_vendedor.py --vendedor Fernando

Si el codigo ERP ya existe en clients (cualquier vendedor), se omite.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import unicodedata
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
load_dotenv()

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

VENDOR_SLUG = {
    "Ivan": "ivan",
    "Fernando": "fernando",
    "Diego": "diego",
    "Javier": "javier",
    "Enrique": "enrique",
}

# Colores placeholder por zona nueva (Enrique no tenía geo_zones)
ZONE_COLORS = {
    "7 de Noviembre": "#e67e22",
    "Juan Manuel de Rosas": "#2980b9",
    "San Agustin": "#8e44ad",
    "Laguna Siam": "#16a085",
    "2 de Abril": "#c0392b",
    "San Miguel": "#27ae60",
    "Fontana": "#11214f",
    "Guadalupe": "#3498db",
    "Terminal": "#9b59b6",
    "Parque Urbano": "#1abc9c",
    "Centro 2": "#f39c12",
    "Mariano Moreno": "#d35400",
    "Don Bosco": "#2c3e50",
}


def _pooler_url(url: str) -> str:
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


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower()).strip("-")
    return s or "zona"


def _parse_dias(raw: str) -> list[str]:
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    canon = {"miercoles": "miércoles", "miércoles": "miércoles", "sabado": "sábado", "sábado": "sábado"}
    out = []
    for p in parts:
        p = p.lower()
        out.append(canon.get(p, p))
    return out or ["lunes"]


async def main_async(esquema: str, vendedor: str) -> None:
    db_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("Falta SUPABASE_DB_URL")
    db_url = _pooler_url(db_url)

    slug = VENDOR_SLUG[vendedor]
    base = ROOT / "implementacion" / esquema
    ccsv = base / "outputs" / f"phase-04-clientes-{slug}-all.csv"
    if not ccsv.exists():
        raise SystemExit(f"Falta {ccsv}. Corré preparar_cartera_vendedor.py --vendedor {vendedor}")

    clients = list(csv.DictReader(ccsv.open(encoding="utf-8")))
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute(f"SET search_path TO {esquema}, core, public, extensions")

        vid = await conn.fetchval(
            """
            SELECT id FROM vendedores
            WHERE nombre ILIKE $1 AND COALESCE(is_mock,false)=false
            ORDER BY id LIMIT 1
            """,
            vendedor,
        )
        if not vid:
            raise SystemExit(f"No está {vendedor} en vendedores")

        zone_rows = await conn.fetch(
            """
            SELECT id, name FROM geo_zones
            WHERE vendedor_principal_id = $1 AND COALESCE(is_mock,false)=false
            """,
            vid,
        )
        zone_by_name = {r["name"].strip().lower(): int(r["id"]) for r in zone_rows}

        # Crear / actualizar geometrías de zonas presentes en el CSV
        zonas_en_csv = {c.get("zona_nombre", "").strip() for c in clients if c.get("zona_nombre")}
        for zona in sorted(zonas_en_csv):
            sample = next(c for c in clients if c.get("zona_nombre", "").strip().lower() == zona.lower())
            dias = _parse_dias(sample.get("dias_zona") or sample.get("dia_de_visita") or "lunes")
            wkt_file = base / "outputs" / f"phase-04-zona-{_slug(zona)}-polygon.wkt"
            wkt = wkt_file.read_text(encoding="utf-8").strip() if wkt_file.exists() else ""
            color = ZONE_COLORS.get(zona, "#39FF14")
            codigo_ruta = f"RUTA-{_slug(zona).upper()[:12]}"
            zid = zone_by_name.get(zona.lower())

            if not zid:
                if not wkt:
                    print(f"  ! no puedo crear zona {zona} sin WKT")
                    continue
                zid = int(
                    await conn.fetchval(
                        """
                        INSERT INTO geo_zones
                          (name, zone_type, description, color, geometry, active, metadata,
                           dia_visita, dias_visita, codigo_ruta, vendedor_principal_id, is_mock)
                        VALUES (
                          $1, 'route', $2, $3,
                          ST_Multi(ST_SetSRID(ST_GeomFromEWKT($4), 4326)),
                          true, '{}'::jsonb,
                          $5::core.dia_de_visita_enum,
                          $6::core.dia_de_visita_enum[],
                          $7, $8, false
                        )
                        RETURNING id
                        """,
                        zona,
                        f"Ruta {vendedor}",
                        color,
                        wkt,
                        dias[0],
                        dias,
                        codigo_ruta,
                        vid,
                    )
                )
                zone_by_name[zona.lower()] = zid
                await conn.execute(
                    """
                    INSERT INTO vendedor_geo_zones (vendedor_id, geo_zone_id, activo)
                    VALUES ($1, $2, true)
                    ON CONFLICT (vendedor_id, geo_zone_id) DO UPDATE SET activo = true
                    """,
                    vid,
                    zid,
                )
                print(f"  + zona {zona} id={zid} dias={dias} (creada)")
            elif wkt:
                await conn.execute(
                    """
                    UPDATE geo_zones SET
                      geometry = ST_Multi(ST_SetSRID(ST_GeomFromEWKT($2), 4326)),
                      dias_visita = $3::core.dia_de_visita_enum[],
                      dia_visita = $4::core.dia_de_visita_enum,
                      is_mock = false,
                      updated_at = now()
                    WHERE id = $1
                    """,
                    zid,
                    wkt,
                    dias,
                    dias[0],
                )
                print(f"  ~ zona {zona} id={zid} dias={dias}")
            else:
                await conn.execute(
                    """
                    UPDATE geo_zones SET
                      dias_visita = $2::core.dia_de_visita_enum[],
                      dia_visita = $3::core.dia_de_visita_enum,
                      is_mock = false,
                      updated_at = now()
                    WHERE id = $1
                    """,
                    zid,
                    dias,
                    dias[0],
                )
                print(f"  ~ zona {zona} id={zid} dias={dias} (sin WKT)")

        existing_codigos = {
            float(r["codigo"])
            for r in await conn.fetch(
                "SELECT codigo FROM clients WHERE codigo IS NOT NULL AND COALESCE(is_mock,false)=false"
            )
        }
        print(f"[*] Codigos ERP ya en BD: {len(existing_codigos)}")
        print(f"[*] Cargando {len(clients)} filas {vendedor}…")

        loaded = skipped_dup = skipped_zone = errors = 0
        seen_batch: set[float] = set()

        for c in clients:
            zona = (c.get("zona_nombre") or "").strip()
            zid = zone_by_name.get(zona.lower())
            if not zid:
                skipped_zone += 1
                continue

            try:
                codigo_num = float(c["codigo"])
            except Exception:
                errors += 1
                continue

            if codigo_num in existing_codigos or codigo_num in seen_batch:
                skipped_dup += 1
                continue
            seen_batch.add(codigo_num)

            lat = c.get("lat") or None
            lng = c.get("lng") or None
            lat_f = float(lat) if lat not in (None, "", "None") else None
            lng_f = float(lng) if lng not in (None, "", "None") else None
            phone = re.sub(r"\D", "", c.get("phone_number") or "")
            if phone and not phone.startswith("549"):
                phone = "549" + phone.lstrip("0")
            if not phone:
                phone = f"5493700{int(codigo_num):07d}"[-13:]

            # phone clash → unique placeholder
            if await conn.fetchval("SELECT id FROM clients WHERE phone_number=$1", phone):
                phone = f"5493709{int(codigo_num):07d}"[-13:]

            dia_v = c.get("dia_de_visita") or "lunes"
            dia_e = c.get("dia_de_entrega") or "martes"
            partner_erp = int(codigo_num)

            pdv_id = await conn.fetchval(
                """
                INSERT INTO puntos_venta
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
                dia_v,
                dia_e,
                c.get("domicilio") or "",
                vid,
                zid,
            )
            cliente_id = await conn.fetchval(
                """
                INSERT INTO clients
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
                dia_v,
                dia_e,
                c.get("domicilio") or "",
                c.get("cuit") or None,
                vendedor,
                pdv_id,
                partner_erp,
            )
            await conn.execute(
                """
                INSERT INTO vendedores_clientes (vendedor_id, cliente_id, activo)
                VALUES ($1, $2, true)
                ON CONFLICT (vendedor_id, cliente_id) DO UPDATE SET activo = true
                """,
                vid,
                cliente_id,
            )
            if lat_f is not None and lng_f is not None:
                await conn.execute(
                    """
                    INSERT INTO client_locations
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
            existing_codigos.add(codigo_num)
            loaded += 1

        resumen = await conn.fetchrow(
            """
            SELECT json_build_object(
              'clients', (SELECT COUNT(*) FROM clients WHERE COALESCE(is_mock,false)=false AND vendedor ILIKE $1),
              'pdv', (SELECT COUNT(*) FROM puntos_venta WHERE vendedor_id=$2 AND COALESCE(is_mock,false)=false),
              'por_zona', (
                SELECT json_object_agg(gz.name, cnt)
                FROM (
                  SELECT geo_zone_id, COUNT(*) AS cnt FROM puntos_venta
                  WHERE vendedor_id=$2 AND COALESCE(is_mock,false)=false
                  GROUP BY geo_zone_id
                ) t JOIN geo_zones gz ON gz.id=t.geo_zone_id
              )
            ) AS r
            """,
            vendedor,
            vid,
        )
        print(
            f"✅ {vendedor}: nuevos={loaded} dup_erp_omitidos={skipped_dup} "
            f"sin_zona={skipped_zone} errores={errors}"
        )
        print(resumen["r"])
    finally:
        await conn.close()


def main() -> None:
    import asyncio

    ap = argparse.ArgumentParser()
    ap.add_argument("--esquema", default="el_gigante")
    ap.add_argument("--vendedor", required=True, choices=sorted(VENDOR_SLUG.keys()))
    args = ap.parse_args()
    asyncio.run(main_async(args.esquema, args.vendedor))


if __name__ == "__main__":
    main()
