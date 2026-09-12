#!/usr/bin/env python3
"""Ronda 2: match agresivo (nombre único / código especial) + zonas depósito/robot.

Solo PDVs que siguen sin geo_zone_id. No toca los 442 de la ronda 1.

  python implementacion/del_corro/scripts/corregir_zona_dia_warning_r2.py
  python implementacion/del_corro/scripts/corregir_zona_dia_warning_r2.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import openpyxl
from dotenv import load_dotenv
from shapely.geometry import MultiPoint, MultiPolygon, Point

SCHEMA = "del_corro"
ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "implementacion" / "del_corro" / "outputs" / "correccion-zona-dia-2026-09-12"
DEFAULT_XLSX = Path("/Users/facundolorenzo/Desktop/M. de clientes 08.09.xlsx")

DAY_BY_LAST_DIGIT = {1: "lunes", 2: "martes", 3: "miercoles", 4: "jueves", 5: "viernes", 6: "sabado"}
DAY_LABEL = {
    "lunes": "Lunes",
    "martes": "Martes",
    "miercoles": "Miércoles",
    "jueves": "Jueves",
    "viernes": "Viernes",
    "sabado": "Sábado",
}
STOP = {"de", "del", "la", "las", "los", "el", "y", "sa", "srl", "sas", "suc"}
WEAK = {
    "despensa", "kiosco", "mini", "max", "maxi", "mercado", "mercadito",
    "minimercado", "minimarket", "autoservicio", "distribuidora", "super",
    "supermercado", "supermercados", "multimarket", "almacen", "tienda",
}
INTERNAL_NAMES = {
    "facundo lorenzo",
    "carlos dottori",
    "jorge burkle",
    "lucas del corro",
    "mariano miles",
    "franca perricone",
}
VENDEDORES_EXTRA = {
    14: "FAERMAN, David",
    23: "vacante",
    30: "FARIAS, Javier",
    40: "GARCIA, Jesus",
    99: "Deposito",
    101: "Punto de venta 1",
    102: "Punto de venta 2",
    888: "Axum Robot",
}
ZONE_COLORS = {
    14: "#1ABC9C",
    23: "#95A5A6",
    30: "#16A085",
    40: "#7F8C8D",
    99: "#BDC3C7",
    101: "#9B59B6",
    102: "#9B59B6",
    888: "#2C3E50",
}

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend-supabase" / ".env")


def _db_url() -> str:
    url = (os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL")
    return url.replace(":5432/", ":6543/")


def fold(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower().replace("ñ", "n")
    return text


def tokens(value) -> list[str]:
    text = re.sub(r"[^a-z0-9 ]", " ", fold(value))
    return [t for t in text.split() if t not in STOP and len(t) >= 3]


def strong(toks: list[str]) -> list[str]:
    return [t for t in toks if t not in WEAK]


def as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def dia_from_zona(zona: int | None) -> str:
    if zona is None:
        return "lunes"
    return DAY_BY_LAST_DIGIT.get(zona % 10, "lunes")


def venid_for_zona(zona: int, excel_venid: int | None) -> int:
    if excel_venid:
        return excel_venid
    if 8881 <= zona <= 8885:
        return 888
    if zona in {98, 99}:
        return 99
    if zona in {1010}:
        return 101
    if zona in {1020}:
        return 102
    return zona // 10


def hull_wkt(points: list[tuple[float, float]]) -> str:
    uniq = []
    seen = set()
    for lng, lat in points:
        key = (round(lng, 6), round(lat, 6))
        if key in seen or not (-75 <= lng <= -50 and -45 <= lat <= -20):
            continue
        seen.add(key)
        uniq.append((lng, lat))
    if not uniq:
        uniq = [(-64.188776, -31.420083)]
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
    return geom.wkt


def load_excel(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Datos"]
    header = None
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            header = [str(c).strip() if c else "" for c in row]
            continue
        raw = dict(zip(header, row))
        rec = {
            "codigo": as_int(raw.get("Codigo")),
            "zona": as_int(raw.get("zona")) if raw.get("zona") not in (None, "") else None,
            "venid": as_int(raw.get("venid")),
            "razon": str(raw.get("razon_social") or "").strip(),
            "fantasia": str(raw.get("fantasia") or "").strip(),
        }
        rows.append(rec)
    return rows


def build_indexes(excel: list[dict]):
    by_code = {}
    by_name = defaultdict(list)
    by_sorted = defaultdict(list)
    for rec in excel:
        if rec["codigo"] is not None:
            by_code[rec["codigo"]] = rec
        for label in (rec["razon"], rec["fantasia"]):
            toks = tokens(label)
            if len(toks) >= 2 and strong(toks):
                by_name[" ".join(toks)].append(rec)
                by_sorted[" ".join(sorted(toks))].append(rec)

    def uniq(idx):
        return {k: v[0] for k, v in idx.items() if len({x["codigo"] for x in v}) == 1}

    return by_code, uniq(by_name), uniq(by_sorted)


def is_internal(razon: str) -> bool:
    return " ".join(tokens(razon)) in INTERNAL_NAMES


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--xlsx", default=str(DEFAULT_XLSX))
    args = parser.parse_args()

    print(f"[*] tenant={SCHEMA} r2 apply={args.apply}")
    excel = load_excel(Path(args.xlsx))
    by_code, u_name, u_sorted = build_indexes(excel)

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        await conn.execute(f"SET search_path TO {SCHEMA}, core, public, extensions")
        warning = await conn.fetch(
            """
            SELECT DISTINCT ON (pv.id)
              pv.id AS pdv_id, pv.codigo, pv.razon_social, pv.dia_de_visita::text AS pdv_dia,
              c.id AS client_id, c.nombre
            FROM del_corro.puntos_venta pv
            LEFT JOIN del_corro.clients c ON c.pdv_id = pv.id AND COALESCE(c.is_primary, true)
            WHERE pv.geo_zone_id IS NULL
            ORDER BY pv.id, c.id
            """
        )
        zones = await conn.fetch(
            """
            SELECT id, name, codigo_ruta, dia_visita::text AS dia_visita,
                   vendedor_principal_id, metadata
            FROM del_corro.geo_zones WHERE active
            """
        )
        zona_to_zone = {}
        for z in zones:
            meta = z["metadata"] or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            erp = as_int(meta.get("erp_zona"))
            if erp is not None:
                zona_to_zone[erp] = z
        ruta_to_vid = {
            str(v["codigo_ruta"]): int(v["id"])
            for v in await conn.fetch("SELECT id, codigo_ruta FROM del_corro.vendedores WHERE codigo_ruta IS NOT NULL")
        }
        gps_rows = await conn.fetch(
            """
            SELECT pv.id AS pdv_id, cl.longitude, cl.latitude
            FROM del_corro.puntos_venta pv
            JOIN del_corro.clients c ON c.pdv_id = pv.id
            JOIN del_corro.client_locations cl ON cl.client_id = c.id
            WHERE pv.geo_zone_id IS NULL AND cl.latitude IS NOT NULL
            """
        )
        gps_by_pdv = defaultdict(list)
        for g in gps_rows:
            gps_by_pdv[int(g["pdv_id"])].append((float(g["longitude"]), float(g["latitude"])))

        assignable = []
        skipped = []
        create_pts = defaultdict(list)
        create_meta = {}

        for row in warning:
            razon = row["razon_social"] or ""
            if is_internal(razon):
                skipped.append({"pdv_id": row["pdv_id"], "razon_social": razon, "motivo": "interno_equipo"})
                continue
            code = as_int(row["codigo"]) if as_int(row["codigo"]) not in (0, None) else None
            rec = None
            via = ""
            if code and code in by_code:
                rec = by_code[code]
                via = "codigo"
            if rec is None:
                cands = []
                for src in (razon, row["nombre"]):
                    toks = tokens(src)
                    if len(toks) < 2 or not strong(toks):
                        continue
                    key = " ".join(toks)
                    skey = " ".join(sorted(toks))
                    if key in u_name:
                        cands.append(u_name[key])
                    elif skey in u_sorted:
                        cands.append(u_sorted[skey])
                if len({c["codigo"] for c in cands}) == 1:
                    rec = cands[0]
                    via = "nombre_unico"
            if rec is None or rec["zona"] is None:
                skipped.append(
                    {
                        "pdv_id": row["pdv_id"],
                        "razon_social": razon,
                        "motivo": "sin_match_estricto" if rec is None else "maestro_sin_zona",
                    }
                )
                continue
            zona = rec["zona"]
            dia = dia_from_zona(zona)
            venid = venid_for_zona(zona, rec["venid"])
            item = {
                "pdv_id": int(row["pdv_id"]),
                "client_id": int(row["client_id"]) if row["client_id"] is not None else "",
                "razon_social": razon,
                "match_via": via,
                "codigo_excel": rec["codigo"],
                "zona_erp": zona,
                "dia_visita": dia,
                "venid": venid,
                "razon_excel": rec["razon"],
            }
            existing = zona_to_zone.get(zona)
            if existing:
                item.update(
                    {
                        "accion": "asignar_existente",
                        "geo_zone_id": int(existing["id"]),
                        "vendedor_id": int(existing["vendedor_principal_id"])
                        if existing["vendedor_principal_id"]
                        else "",
                        "vendedor_codigo": existing["codigo_ruta"] or str(venid),
                    }
                )
            else:
                item.update({"accion": "crear_zona_y_asignar", "geo_zone_id": "", "vendedor_id": "", "vendedor_codigo": str(venid)})
                create_pts[zona].extend(gps_by_pdv.get(int(row["pdv_id"]), []))
                create_meta[zona] = {"dia": dia, "venid": venid}
            assignable.append(item)

        write_csv(
            OUT_DIR / "r2_asignables.csv",
            assignable,
            ["pdv_id", "client_id", "razon_social", "match_via", "codigo_excel", "zona_erp", "dia_visita", "accion", "venid"],
        )
        write_csv(OUT_DIR / "r2_omitidos.csv", skipped, ["pdv_id", "razon_social", "motivo"])
        n_exist = sum(1 for r in assignable if r["accion"] == "asignar_existente")
        n_new = sum(1 for r in assignable if r["accion"] == "crear_zona_y_asignar")
        print(f"[*] restantes={len(warning)} asignables={len(assignable)} exist={n_exist} nuevas={n_new} omitidos={len(skipped)}")
        print("[*] zonas a crear", sorted(create_meta.items()))

        if not args.apply:
            print(f"[dry-run] CSVs en {OUT_DIR}")
            return 0

        print(f"[APPLY] schema={SCHEMA} ronda 2")
        async with conn.transaction():
            for ruta, nombre in VENDEDORES_EXTRA.items():
                key = str(ruta)
                if key in ruta_to_vid:
                    continue
                if ruta not in {m["venid"] for m in create_meta.values()}:
                    continue
                vid = await conn.fetchval(
                    """
                    INSERT INTO del_corro.vendedores (nombre, telefono, activo, codigo_ruta, is_mock)
                    VALUES ($1, $2, true, $3, false)
                    RETURNING id
                    """,
                    nombre,
                    f"5493519{ruta:04d}",
                    key,
                )
                ruta_to_vid[key] = int(vid)
                print(f"  + vendedor {ruta} id={vid} {nombre}")

            zona_ids = {z: int(rec["id"]) for z, rec in zona_to_zone.items()}
            for zona, meta in sorted(create_meta.items()):
                if zona in zona_ids:
                    continue
                vid = ruta_to_vid.get(str(meta["venid"]))
                if not vid:
                    print(f"  ! zona {zona} sin vendedor {meta['venid']}")
                    continue
                pts = create_pts.get(zona) or [(-64.188776, -31.420083)]
                wkt = hull_wkt(pts)
                dia = meta["dia"]
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
                      true, $5::jsonb,
                      $6::core.dia_de_visita_enum,
                      ARRAY[$6::core.dia_de_visita_enum],
                      $7, $8, false
                    )
                    RETURNING id
                    """,
                    f"Zona {zona} (V{meta['venid']} - {DAY_LABEL[dia]})",
                    f"Ruta ERP zona {zona}. Alta r2 2026-09-12 (maestro + warning).",
                    ZONE_COLORS.get(meta["venid"], "#34495E"),
                    wkt,
                    json.dumps({"erp_zona": zona, "source": "maestro_clientes_2026-09-08", "round": 2}),
                    dia,
                    str(meta["venid"]),
                    vid,
                )
                zona_ids[zona] = int(zid)
                await conn.execute(
                    """
                    INSERT INTO del_corro.vendedor_geo_zones (vendedor_id, geo_zone_id, activo, is_mock)
                    VALUES ($1, $2, true, false)
                    ON CONFLICT (vendedor_id, geo_zone_id) DO UPDATE SET activo = true, updated_at = NOW()
                    """,
                    vid,
                    int(zid),
                )
                print(f"  + zona {zona} id={zid} vid={vid}")

            await conn.execute(
                """
                CREATE TEMP TABLE _fix_r2 (
                  pdv_id int NOT NULL,
                  geo_zone_id bigint NOT NULL,
                  vendedor_id int,
                  vendedor_codigo text,
                  dia_visita text NOT NULL
                ) ON COMMIT DROP
                """
            )
            map_rows = []
            applied = []
            for rec in assignable:
                zid = zona_ids.get(int(rec["zona_erp"]))
                if not zid:
                    skipped.append({**rec, "motivo": "zona_sin_crear"})
                    continue
                vid = rec.get("vendedor_id") or ruta_to_vid.get(str(rec["venid"]))
                vcod = rec.get("vendedor_codigo") or str(rec["venid"])
                map_rows.append(
                    (rec["pdv_id"], int(zid), int(vid) if vid else None, str(vcod) if vcod else None, rec["dia_visita"])
                )
                applied.append({**rec, "geo_zone_id": int(zid)})

            await conn.copy_records_to_table(
                "_fix_r2",
                records=map_rows,
                columns=["pdv_id", "geo_zone_id", "vendedor_id", "vendedor_codigo", "dia_visita"],
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
                  FROM _fix_r2 m WHERE pv.id = m.pdv_id
                  RETURNING 1
                ) SELECT COUNT(*) FROM u
                """
            )
            n_cli = await conn.fetchval(
                """
                WITH u AS (
                  UPDATE del_corro.clients c
                  SET dia_de_visita = m.dia_visita::core.dia_de_visita_enum,
                      vendedor = COALESCE(m.vendedor_codigo, c.vendedor),
                      updated_at = NOW()
                  FROM _fix_r2 m WHERE c.pdv_id = m.pdv_id
                  RETURNING 1
                ) SELECT COUNT(*) FROM u
                """
            )
            n_cartera = await conn.fetchval(
                """
                WITH ins AS (
                  INSERT INTO del_corro.vendedores_clientes (vendedor_id, cliente_id)
                  SELECT DISTINCT m.vendedor_id, c.id
                  FROM _fix_r2 m
                  JOIN del_corro.clients c ON c.pdv_id = m.pdv_id
                  WHERE m.vendedor_id IS NOT NULL
                  ON CONFLICT DO NOTHING
                  RETURNING 1
                ) SELECT COUNT(*) FROM ins
                """
            )

        after = await conn.fetchrow(
            """
            SELECT COUNT(*) FILTER (WHERE geo_zone_id IS NULL) AS pdv_sin_zona,
                   COUNT(*) FILTER (WHERE geo_zone_id IS NULL OR dia_de_visita IS NULL) AS pdv_warning
            FROM del_corro.puntos_venta
            """
        )
        write_csv(OUT_DIR / "r2_aplicados.csv", applied, ["pdv_id", "razon_social", "match_via", "zona_erp", "dia_visita", "geo_zone_id"])
        summary = {
            "schema": SCHEMA,
            "round": 2,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "pdv_updated": int(n_pdv),
            "clients_updated": int(n_cli),
            "cartera_inserted": int(n_cartera),
            "omitidos": len(skipped),
            "after": dict(after),
        }
        (OUT_DIR / "r2_resumen.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("[OK]", json.dumps(summary, ensure_ascii=False))
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
