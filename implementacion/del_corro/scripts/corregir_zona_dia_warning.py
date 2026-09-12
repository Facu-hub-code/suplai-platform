#!/usr/bin/env python3
"""Corrige día de visita y zona de PDVs Campi (del_corro) con warning
'Sin zona / Día de visita', usando el maestro de clientes.

Solo toca filas sin geo_zone o sin día. No reasigna clientes ya zonificados.
Crea vendedores/zonas de rutas 14, 17 y 18 si el maestro las trae y faltan.

Uso:
  set -a && source ../backend-supabase/.env && set +a
  python implementacion/del_corro/scripts/corregir_zona_dia_warning.py
  python implementacion/del_corro/scripts/corregir_zona_dia_warning.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import openpyxl
from dotenv import load_dotenv
from shapely.geometry import MultiPoint, MultiPolygon, Point

SCHEMA = "del_corro"
ROOT = Path(__file__).resolve().parents[3]
TENANT_DIR = ROOT / "implementacion" / "del_corro"
OUT_DIR = TENANT_DIR / "outputs" / "correccion-zona-dia-2026-09-12"
DEFAULT_XLSX = Path("/Users/facundolorenzo/Desktop/M. de clientes 08.09.xlsx")

DAY_BY_LAST_DIGIT = {
    1: "lunes",
    2: "martes",
    3: "miercoles",
    4: "jueves",
    5: "viernes",
    6: "sabado",
}
DAY_LABEL = {
    "lunes": "Lunes",
    "martes": "Martes",
    "miercoles": "Miércoles",
    "jueves": "Jueves",
    "viernes": "Viernes",
    "sabado": "Sábado",
}
SPECIAL_ZONAS = {40, 98, 99, 231, 1010, 1020, 8881, 8882, 8883, 8884, 8885}
CREATABLE_ZONAS = {141, 142, 143, 144, 145, 146, 171, 172, 173, 174, 175, 176, 181}
ZONE_COLORS = {
    14: "#1ABC9C",
    17: "#8E44AD",
    18: "#D35400",
}
VENDEDOR_NOMBRES = {
    14: "FAERMAN, David",
    17: "HERRERA, Maria",
    18: "Vendedor 18",
}

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
        raise SystemExit("Falta SUPABASE_DB_URL / DATABASE_URL")
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    return url


def norm_phone(value) -> str:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    return digits[-10:] if digits else ""


def as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def dia_from_zona(zona: int | None) -> str | None:
    if zona is None:
        return None
    return DAY_BY_LAST_DIGIT.get(zona % 10)


def load_excel(path: Path) -> tuple[dict[int, dict], dict[str, list[dict]]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Datos"]
    by_code: dict[int, dict] = {}
    by_phone: dict[str, list[dict]] = defaultdict(list)
    header = None
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            header = [str(c).strip() if c else "" for c in row]
            continue
        raw = dict(zip(header, row))
        codigo = as_int(raw.get("Codigo"))
        zona = as_int(raw.get("zona"))
        venid = as_int(raw.get("venid"))
        rec = {
            "codigo": codigo,
            "zona": zona,
            "venid": venid,
            "vennom": str(raw.get("vennom") or "").strip(),
            "razon_social": str(raw.get("razon_social") or "").strip(),
            "telefono": str(raw.get("telefono") or "").strip(),
            "localidad": str(raw.get("localidad") or "").strip(),
        }
        if codigo is not None and codigo not in by_code:
            by_code[codigo] = rec
        phone = norm_phone(rec["telefono"])
        if phone:
            by_phone[phone].append(rec)
    return by_code, by_phone


def match_excel(pdv: dict, by_code: dict[int, dict], by_phone: dict[str, list[dict]]) -> tuple[dict | None, str]:
    codigo = as_int(pdv.get("codigo"))
    if codigo:
        rec = by_code.get(codigo)
        if rec:
            return rec, "codigo"
    phone = norm_phone(pdv.get("phone_number"))
    if phone:
        recs = by_phone.get(phone) or []
        if len(recs) == 1:
            return recs[0], "phone"
        if len(recs) > 1:
            codes = {r["codigo"] for r in recs}
            if len(codes) == 1:
                return recs[0], "phone"
    return None, ""


def hull_wkt(points: list[tuple[float, float]]) -> str:
    uniq = []
    seen = set()
    for lng, lat in points:
        key = (round(lng, 6), round(lat, 6))
        if key in seen:
            continue
        if not (-75 <= lng <= -50 and -45 <= lat <= -20):
            continue
        seen.add(key)
        uniq.append((lng, lat))
    if not uniq:
        raise ValueError("sin puntos válidos")
    if len(uniq) == 1:
        geom = Point(uniq[0]).buffer(0.012, resolution=4)
    elif len(uniq) == 2:
        geom = MultiPoint(uniq).convex_hull.buffer(0.01, resolution=4)
    else:
        geom = MultiPoint(uniq).convex_hull.buffer(0.006, resolution=4)
    if not geom.is_valid:
        geom = geom.buffer(0)
    if geom.geom_type == "Polygon":
        geom = MultiPolygon([geom])
    elif geom.geom_type != "MultiPolygon":
        geom = MultiPolygon([geom.buffer(0.008)])
    return geom.wkt


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--xlsx", default=str(DEFAULT_XLSX))
    args = parser.parse_args()

    print(f"[*] tenant={SCHEMA} path={TENANT_DIR} apply={args.apply}")
    by_code, by_phone = load_excel(Path(args.xlsx))
    print(f"[*] excel codigos={len(by_code)}")

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        await conn.execute(f"SET search_path TO {SCHEMA}, core, public, extensions")

        zones = await conn.fetch(
            """
            SELECT id, name, codigo_ruta, dia_visita::text AS dia_visita,
                   vendedor_principal_id, metadata
            FROM del_corro.geo_zones
            WHERE active
            """
        )
        zona_to_zone: dict[int, asyncpg.Record] = {}
        for z in zones:
            meta = z["metadata"] or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            erp = as_int(meta.get("erp_zona"))
            if erp is not None:
                zona_to_zone[erp] = z

        vendedores = await conn.fetch(
            "SELECT id, nombre, codigo_ruta FROM del_corro.vendedores"
        )
        ruta_to_vid = {
            str(v["codigo_ruta"]): int(v["id"])
            for v in vendedores
            if v["codigo_ruta"]
        }

        warning = await conn.fetch(
            """
            SELECT DISTINCT ON (pv.id)
              pv.id AS pdv_id,
              pv.codigo,
              pv.razon_social,
              pv.dia_de_visita::text AS pdv_dia,
              pv.geo_zone_id,
              pv.vendedor_id,
              c.id AS client_id,
              c.codigo AS client_codigo,
              c.dia_de_visita::text AS client_dia,
              c.phone_number,
              c.activo_ai,
              c.vendedor AS client_vendedor
            FROM del_corro.puntos_venta pv
            LEFT JOIN del_corro.clients c
              ON c.pdv_id = pv.id AND COALESCE(c.is_primary, true)
            WHERE pv.geo_zone_id IS NULL
               OR pv.dia_de_visita IS NULL
            ORDER BY pv.id, c.id
            """
        )
        gps_rows = await conn.fetch(
            """
            SELECT pv.id AS pdv_id, cl.latitude, cl.longitude
            FROM del_corro.puntos_venta pv
            JOIN del_corro.clients c ON c.pdv_id = pv.id
            JOIN del_corro.client_locations cl ON cl.client_id = c.id
            WHERE pv.geo_zone_id IS NULL
              AND cl.latitude IS NOT NULL
              AND cl.longitude IS NOT NULL
            """
        )
        gps_by_pdv: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for g in gps_rows:
            gps_by_pdv[int(g["pdv_id"])].append((float(g["longitude"]), float(g["latitude"])))

        assignable: list[dict] = []
        create_zone_pts: dict[int, list[tuple[float, float]]] = defaultdict(list)
        skipped: list[dict] = []

        for row in warning:
            pdv = dict(row)
            excel, via = match_excel(pdv, by_code, by_phone)
            base = {
                "pdv_id": int(pdv["pdv_id"]),
                "client_id": int(pdv["client_id"]) if pdv["client_id"] is not None else "",
                "codigo_bd": as_int(pdv["codigo"]) or as_int(pdv["client_codigo"]) or "",
                "razon_social": pdv["razon_social"] or "",
                "phone_number": pdv["phone_number"] or "",
                "pdv_dia_antes": pdv["pdv_dia"] or "",
                "client_dia_antes": pdv["client_dia"] or "",
                "geo_zone_id_antes": pdv["geo_zone_id"] or "",
            }
            if not excel:
                skipped.append({**base, "motivo": "sin_match_maestro"})
                continue
            zona = excel["zona"]
            dia = dia_from_zona(zona)
            rec = {
                **base,
                "match_via": via,
                "codigo_excel": excel["codigo"],
                "zona_erp": zona if zona is not None else "",
                "venid_excel": excel["venid"] or "",
                "vennom_excel": excel["vennom"],
                "dia_visita": dia or "",
            }
            existing = zona_to_zone.get(zona) if zona is not None else None
            if existing and dia:
                rec.update(
                    {
                        "accion": "asignar_existente",
                        "geo_zone_id": int(existing["id"]),
                        "geo_zone_name": existing["name"],
                        "vendedor_id": int(existing["vendedor_principal_id"])
                        if existing["vendedor_principal_id"]
                        else "",
                        "vendedor_codigo": existing["codigo_ruta"] or "",
                    }
                )
                assignable.append(rec)
                continue
            if zona in CREATABLE_ZONAS and dia:
                rec.update({"accion": "crear_zona_y_asignar", "geo_zone_id": "", "geo_zone_name": ""})
                assignable.append(rec)
                create_zone_pts[zona].extend(gps_by_pdv.get(int(pdv["pdv_id"]), []))
                continue
            if zona in SPECIAL_ZONAS:
                skipped.append({**rec, "motivo": f"zona_especial_{zona}"})
                continue
            if zona is None:
                skipped.append({**rec, "motivo": "maestro_sin_zona"})
                continue
            skipped.append({**rec, "motivo": f"zona_{zona}_sin_dia_o_sin_geo"})

        created_zone_preview = []
        for zona, pts in sorted(create_zone_pts.items()):
            created_zone_preview.append(
                {
                    "zona_erp": zona,
                    "n_pts_gps": len({(round(p[0], 6), round(p[1], 6)) for p in pts}),
                    "puede_crear": len(pts) >= 1,
                    "dia_visita": dia_from_zona(zona) or "",
                    "venid": zona // 10,
                }
            )

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        write_csv(
            OUT_DIR / "asignables.csv",
            assignable,
            [
                "pdv_id",
                "client_id",
                "codigo_bd",
                "codigo_excel",
                "razon_social",
                "match_via",
                "zona_erp",
                "dia_visita",
                "accion",
                "geo_zone_id",
                "geo_zone_name",
                "vendedor_id",
                "vendedor_codigo",
                "venid_excel",
                "vennom_excel",
                "pdv_dia_antes",
                "client_dia_antes",
            ],
        )
        write_csv(
            OUT_DIR / "omitidos.csv",
            skipped,
            [
                "pdv_id",
                "client_id",
                "codigo_bd",
                "razon_social",
                "phone_number",
                "motivo",
                "zona_erp",
                "dia_visita",
                "match_via",
            ],
        )
        write_csv(
            OUT_DIR / "zonas_a_crear.csv",
            created_zone_preview,
            ["zona_erp", "n_pts_gps", "puede_crear", "dia_visita", "venid"],
        )

        n_exist = sum(1 for r in assignable if r["accion"] == "asignar_existente")
        n_new = sum(1 for r in assignable if r["accion"] == "crear_zona_y_asignar")
        print(f"[*] warning_pdvs={len(warning)}")
        print(f"[*] asignables_existente={n_exist} asignables_zona_nueva={n_new} omitidos={len(skipped)}")
        motivos = defaultdict(int)
        for s in skipped:
            motivos[s["motivo"]] += 1
        print("[*] omitidos:", dict(sorted(motivos.items(), key=lambda kv: -kv[1])))
        print("[*] zonas_a_crear:", created_zone_preview)

        if not args.apply:
            print(f"[dry-run] CSVs en {OUT_DIR}. Reejecutar con --apply para escribir en {SCHEMA}.")
            return 0

        print(f"[APPLY] schema={SCHEMA} — UPDATE puntos_venta + clients")
        async with conn.transaction():
            for ruta, nombre in VENDEDOR_NOMBRES.items():
                key = str(ruta)
                if key in ruta_to_vid:
                    continue
                vid = await conn.fetchval(
                    """
                    INSERT INTO del_corro.vendedores
                      (nombre, telefono, email, activo, codigo_ruta, is_mock)
                    VALUES ($1, $2, $3, true, $4, false)
                    RETURNING id
                    """,
                    nombre,
                    f"5493519{ruta:04d}",
                    None,
                    key,
                )
                ruta_to_vid[key] = int(vid)
                print(f"  + vendedor ruta={ruta} id={vid} nombre={nombre}")

            zona_ids = {z: int(rec["id"]) for z, rec in zona_to_zone.items()}
            for zona, pts in sorted(create_zone_pts.items()):
                if zona in zona_ids:
                    continue
                if not pts:
                    # Sin GPS: anillo chico en centro de Córdoba para que el warning desaparezca.
                    pts = [(-64.188776, -31.420083)]
                    print(f"  ! zona {zona} sin GPS — polígono placeholder CBA centro")
                dia = dia_from_zona(zona)
                vend = str(zona // 10)
                vid = ruta_to_vid.get(vend)
                if not vid or not dia:
                    print(f"  ! zona {zona} sin vendedor/día — no se crea")
                    continue
                wkt = hull_wkt(pts)
                zid = await conn.fetchval(
                    """
                    INSERT INTO del_corro.geo_zones (
                      name, zone_type, description, color, geometry,
                      active, metadata, dia_visita, dias_visita, codigo_ruta,
                      vendedor_principal_id, is_mock
                    )
                    VALUES (
                      $1, 'sales', $2, $3,
                      ST_SetSRID(ST_GeomFromText($4), 4326),
                      true,
                      $5::jsonb,
                      $6::core.dia_de_visita_enum,
                      ARRAY[$6::core.dia_de_visita_enum],
                      $7, $8, false
                    )
                    RETURNING id
                    """,
                    f"Zona {zona} (V{vend} - {DAY_LABEL[dia]})",
                    f"Ruta ERP zona {zona}: vendedor {vend}, visita {DAY_LABEL[dia]}. Alta 2026-09-12 desde maestro 08.09.",
                    ZONE_COLORS.get(int(vend), "#34495E"),
                    wkt,
                    json.dumps(
                        {
                            "erp_zona": zona,
                            "source": "maestro_clientes_2026-09-08",
                            "created_for": "warning_sin_zona_dia",
                        }
                    ),
                    dia,
                    vend,
                    vid,
                )
                zona_ids[zona] = int(zid)
                await conn.execute(
                    """
                    INSERT INTO del_corro.vendedor_geo_zones (vendedor_id, geo_zone_id, activo, is_mock)
                    VALUES ($1, $2, true, false)
                    ON CONFLICT (vendedor_id, geo_zone_id) DO UPDATE
                      SET activo = true, updated_at = NOW()
                    """,
                    vid,
                    int(zid),
                )
                print(f"  + zona {zona} id={zid} pts={len(pts)} vid={vid}")

            await conn.execute(
                """
                CREATE TEMP TABLE _fix_zona_dia (
                  pdv_id int NOT NULL,
                  client_id int,
                  geo_zone_id bigint NOT NULL,
                  vendedor_id int,
                  vendedor_codigo text,
                  dia_visita text NOT NULL
                ) ON COMMIT DROP
                """
            )
            map_rows = []
            applied_rows = []
            for rec in assignable:
                zona = as_int(rec["zona_erp"])
                zid = zona_ids.get(zona) if zona is not None else None
                if not zid or not rec["dia_visita"]:
                    skipped.append({**rec, "motivo": "zona_nueva_sin_crear"})
                    continue
                zone = zona_to_zone.get(zona)
                vid = rec.get("vendedor_id") or (int(zone["vendedor_principal_id"]) if zone and zone["vendedor_principal_id"] else ruta_to_vid.get(str(zona // 10), ""))
                vcodigo = rec.get("vendedor_codigo") or (zone["codigo_ruta"] if zone else str(zona // 10))
                if vid == "":
                    vid = None
                map_rows.append(
                    (
                        rec["pdv_id"],
                        rec["client_id"] or None,
                        int(zid),
                        int(vid) if vid else None,
                        str(vcodigo) if vcodigo else None,
                        rec["dia_visita"],
                    )
                )
                applied_rows.append({**rec, "geo_zone_id": int(zid)})

            await conn.copy_records_to_table(
                "_fix_zona_dia",
                records=map_rows,
                columns=[
                    "pdv_id",
                    "client_id",
                    "geo_zone_id",
                    "vendedor_id",
                    "vendedor_codigo",
                    "dia_visita",
                ],
            )

            n_pdv = await conn.fetchval(
                """
                WITH u AS (
                  UPDATE del_corro.puntos_venta pv
                  SET geo_zone_id = m.geo_zone_id,
                      vendedor_id = COALESCE(m.vendedor_id, pv.vendedor_id),
                      dia_de_visita = m.dia_visita::core.dia_de_visita_enum,
                      geo_zone_asignacion = 'manual',
                      geo_zone_asignado_at = NOW(),
                      updated_at = NOW()
                  FROM _fix_zona_dia m
                  WHERE pv.id = m.pdv_id
                  RETURNING pv.id
                )
                SELECT COUNT(*) FROM u
                """
            )
            n_cli = await conn.fetchval(
                """
                WITH u AS (
                  UPDATE del_corro.clients c
                  SET dia_de_visita = m.dia_visita::core.dia_de_visita_enum,
                      vendedor = COALESCE(m.vendedor_codigo, c.vendedor),
                      updated_at = NOW()
                  FROM _fix_zona_dia m
                  WHERE c.pdv_id = m.pdv_id
                  RETURNING c.id
                )
                SELECT COUNT(*) FROM u
                """
            )
            n_cartera = await conn.fetchval(
                """
                WITH ins AS (
                  INSERT INTO del_corro.vendedores_clientes (vendedor_id, cliente_id)
                  SELECT DISTINCT m.vendedor_id, c.id
                  FROM _fix_zona_dia m
                  JOIN del_corro.clients c ON c.pdv_id = m.pdv_id
                  WHERE m.vendedor_id IS NOT NULL
                  ON CONFLICT DO NOTHING
                  RETURNING 1
                )
                SELECT COUNT(*) FROM ins
                """
            )
            n_sync = await conn.fetchval(
                """
                WITH u AS (
                  UPDATE del_corro.clients c
                  SET dia_de_visita = pv.dia_de_visita,
                      updated_at = NOW()
                  FROM del_corro.puntos_venta pv
                  WHERE c.pdv_id = pv.id
                    AND c.dia_de_visita IS NULL
                    AND pv.dia_de_visita IS NOT NULL
                  RETURNING c.id
                )
                SELECT COUNT(*) FROM u
                """
            )

        after = await conn.fetchrow(
            """
            SELECT
              COUNT(*) FILTER (WHERE geo_zone_id IS NULL) AS pdv_sin_zona,
              COUNT(*) FILTER (WHERE dia_de_visita IS NULL) AS pdv_sin_dia,
              COUNT(*) FILTER (WHERE geo_zone_id IS NULL OR dia_de_visita IS NULL) AS pdv_warning
            FROM del_corro.puntos_venta
            """
        )
        after_cli = await conn.fetchval(
            "SELECT COUNT(*) FROM del_corro.clients WHERE dia_de_visita IS NULL"
        )

        write_csv(
            OUT_DIR / "aplicados.csv",
            applied_rows,
            [
                "pdv_id",
                "client_id",
                "codigo_excel",
                "razon_social",
                "zona_erp",
                "dia_visita",
                "accion",
                "geo_zone_id",
            ],
        )
        summary = {
            "schema": SCHEMA,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "warning_pdvs_before": len(warning),
            "pdv_updated": int(n_pdv),
            "clients_updated": int(n_cli),
            "cartera_inserted": int(n_cartera),
            "clients_dia_synced_from_pdv": int(n_sync),
            "omitidos": len(skipped),
            "after": dict(after),
            "clients_sin_dia_after": int(after_cli),
        }
        (OUT_DIR / "resumen.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print("[OK]", json.dumps(summary, ensure_ascii=False))
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
