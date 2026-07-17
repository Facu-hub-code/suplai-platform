#!/usr/bin/env python3
"""
Carga carteras Diego (phase-04-clientes-diego-all.csv) + actualiza geometría de zonas.

  python scripts/el_gigante_red_comercial/cargar_cartera_diego.py --esquema el_gigante
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


async def main_async(esquema: str) -> None:
    db_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("Falta SUPABASE_DB_URL")
    db_url = _pooler_url(db_url)

    base = ROOT / "implementacion" / esquema
    ccsv = base / "outputs" / "phase-04-clientes-diego-all.csv"
    zcsv = base / "outputs" / "phase-04-zonas-real.csv"
    if not ccsv.exists():
        raise SystemExit(f"Falta {ccsv}. Corré preparar_cartera_diego.py")

    clients = list(csv.DictReader(ccsv.open(encoding="utf-8")))
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute(f"SET search_path TO {esquema}, core, public, extensions")

        diego_id = await conn.fetchval(
            """
            SELECT id FROM vendedores
            WHERE nombre ILIKE 'Diego' AND COALESCE(is_mock,false)=false
            ORDER BY id LIMIT 1
            """
        )
        if not diego_id:
            raise SystemExit("No está Diego en vendedores — corré cargar_red_real.py primero")

        # Map zone name → id (Diego)
        zone_rows = await conn.fetch(
            """
            SELECT id, name FROM geo_zones
            WHERE vendedor_principal_id = $1 AND COALESCE(is_mock,false)=false
            """,
            diego_id,
        )
        zone_by_name = {r["name"].strip().lower(): int(r["id"]) for r in zone_rows}

        # Patch geometries + dias from zonas-real / wkt files
        if zcsv.exists():
            for z in csv.DictReader(zcsv.open(encoding="utf-8")):
                if int(z.get("vendedor_idx") or -1) != 0:
                    continue
                name = z["nombre"].strip()
                zid = zone_by_name.get(name.lower())
                if not zid:
                    print(f"  ! zona no en BD: {name}")
                    continue
                dias = _parse_dias(z.get("dias_visita") or z.get("dia_visita") or "lunes")
                wkt = (z.get("geometry_wkt") or "").strip()
                wkt_file = base / "outputs" / f"phase-04-zona-{_slug(name)}-polygon.wkt"
                if wkt_file.exists():
                    wkt = wkt_file.read_text(encoding="utf-8").strip()
                if wkt:
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
                print(f"  ~ zona {name} id={zid} dias={dias}")

        print(f"[*] Cargando {len(clients)} filas Diego…")
        loaded = updated = skipped = 0
        errors = 0

        for c in clients:
            zona = (c.get("zona_nombre") or "").strip()
            zid = zone_by_name.get(zona.lower())
            if not zid:
                print(f"  ! sin zona '{zona}' para codigo={c.get('codigo')}")
                errors += 1
                continue

            lat = c.get("lat") or None
            lng = c.get("lng") or None
            lat_f = float(lat) if lat not in (None, "", "None") else None
            lng_f = float(lng) if lng not in (None, "", "None") else None
            phone = re.sub(r"\D", "", c.get("phone_number") or "")
            if phone and not phone.startswith("549"):
                phone = "549" + phone.lstrip("0")
            codigo_num = None
            try:
                codigo_num = float(c["codigo"])
            except Exception:
                pass
            if not phone:
                phone = f"5493700{int(codigo_num or 0):07d}"[-13:]

            existing = await conn.fetchrow(
                """
                SELECT id, pdv_id FROM clients
                WHERE COALESCE(is_mock,false)=false AND (
                  (codigo IS NOT NULL AND codigo = $1)
                  OR phone_number = $2
                )
                ORDER BY id LIMIT 1
                """,
                codigo_num,
                phone,
            )

            partner_erp = None
            try:
                partner_erp = int(float(c["codigo"]))
            except Exception:
                pass

            dia_v = c.get("dia_de_visita") or "lunes"
            dia_e = c.get("dia_de_entrega") or "martes"

            if existing:
                cliente_id = int(existing["id"])
                pdv_id = existing["pdv_id"]
                if pdv_id:
                    await conn.execute(
                        """
                        UPDATE puntos_venta SET
                          geo_zone_id=$2, vendedor_id=$3,
                          dia_de_visita=$4::core.dia_de_visita_enum,
                          dia_de_entrega=$5::core.dia_de_entrega_enum,
                          direccion=$6, is_mock=false, updated_at=now()
                        WHERE id=$1
                        """,
                        int(pdv_id),
                        zid,
                        diego_id,
                        dia_v,
                        dia_e,
                        c.get("domicilio") or "",
                    )
                await conn.execute(
                    """
                    UPDATE clients SET
                      vendedor='Diego', pdv_id=COALESCE(pdv_id, $2),
                      dia_de_visita=$3::core.dia_de_visita_enum,
                      dia_de_entrega=$4::core.dia_de_entrega_enum,
                      direccion=$5, is_mock=false
                    WHERE id=$1
                    """,
                    cliente_id,
                    pdv_id,
                    dia_v,
                    dia_e,
                    c.get("domicilio") or "",
                )
                updated += 1
            else:
                # phone unique clash → suffix
                clash = await conn.fetchval("SELECT id FROM clients WHERE phone_number=$1", phone)
                if clash:
                    phone = f"5493709{int(codigo_num or 0):07d}"[-13:]

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
                    diego_id,
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
                      $8, $9, 'Diego',
                      $10, true, true, false, $11
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
                    pdv_id,
                    partner_erp,
                )
                loaded += 1

            await conn.execute(
                """
                INSERT INTO vendedores_clientes (vendedor_id, cliente_id, activo)
                VALUES ($1, $2, true)
                ON CONFLICT (vendedor_id, cliente_id) DO UPDATE SET activo = true
                """,
                diego_id,
                cliente_id,
            )

            if lat_f is not None and lng_f is not None:
                loc = await conn.fetchval(
                    "SELECT id FROM client_locations WHERE client_id=$1 AND is_primary=true ORDER BY id LIMIT 1",
                    cliente_id,
                )
                status = _geocode_status(c.get("geocode_status"))
                addr = c.get("domicilio") or ""
                if loc:
                    await conn.execute(
                        """
                        UPDATE client_locations SET
                          address_text=$2, latitude=$3, longitude=$4,
                          location=ST_SetSRID(ST_MakePoint($4::float8, $3::float8), 4326),
                          geocode_status=$5, updated_at=now()
                        WHERE id=$1
                        """,
                        loc,
                        addr,
                        lat_f,
                        lng_f,
                        status,
                    )
                else:
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
                        addr,
                        lat_f,
                        lng_f,
                        status,
                    )

        resumen = await conn.fetchrow(
            """
            SELECT json_build_object(
              'clients_diego', (SELECT COUNT(*) FROM clients WHERE COALESCE(is_mock,false)=false AND vendedor ILIKE 'Diego'),
              'pdv_diego', (SELECT COUNT(*) FROM puntos_venta WHERE vendedor_id=$1 AND COALESCE(is_mock,false)=false),
              'vc_diego', (SELECT COUNT(*) FROM vendedores_clientes WHERE vendedor_id=$1 AND activo),
              'locs', (
                SELECT COUNT(*) FROM client_locations cl
                JOIN clients c ON c.id=cl.client_id
                WHERE COALESCE(c.is_mock,false)=false AND c.vendedor ILIKE 'Diego'
              ),
              'por_zona', (
                SELECT json_object_agg(gz.name, cnt)
                FROM (
                  SELECT pv.geo_zone_id, COUNT(*) AS cnt
                  FROM puntos_venta pv
                  WHERE pv.vendedor_id=$1 AND COALESCE(pv.is_mock,false)=false
                  GROUP BY pv.geo_zone_id
                ) t
                JOIN geo_zones gz ON gz.id = t.geo_zone_id
              )
            ) AS r
            """,
            diego_id,
        )
        print(f"✅ nuevos={loaded} actualizados={updated} errores_zona={errors}")
        print(resumen["r"])
    finally:
        await conn.close()


def main() -> None:
    import asyncio

    ap = argparse.ArgumentParser()
    ap.add_argument("--esquema", default="el_gigante")
    args = ap.parse_args()
    asyncio.run(main_async(args.esquema))


if __name__ == "__main__":
    main()
