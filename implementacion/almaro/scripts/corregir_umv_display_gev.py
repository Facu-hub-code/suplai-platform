#!/usr/bin/env python3
"""Corrige a UMV display los SKUs de almaro que GEV vende por display.

Caso: la carga del 21-sep (`cargar_packing_umv_excel.py`) leyó `UM Precio Sugerido`
del Excel y dejó como `unidad` (mínimo = unidades del display) SKUs que GEV vende
por display. El precio GEV es del display (ej. 14430 jugo $5.581 = display de 18),
así que el agente cotizaba "por unidad" y multiplicaba por el mínimo.

Fuente: API GEV `getArticulos` y `getDetallePrecios` (snapshots en inputs/gev-*-20261001.json).
  UNIDAD_VENTA = DI → umv display; CANTIDAD_UNIDADES_UNIDAD_VENTA = unidades del display.
Solo toca SKUs hoy `umv_tipo = unidad` con UNIDAD_VENTA = DI. No toca otros schemas.

Quedan fuera (`incluir=no`), para revisar aparte:
  - precio GEV sin actualizar desde VIGENCIA_MIN: códigos viejos con precio de unidad
    (ej. chicle a $79 el "display" de 120).
  - display a menos de PRECIO_DISPLAY_MIN (lista 05 KIPP).

Uso:
  python implementacion/almaro/scripts/corregir_umv_display_gev.py          # propuesta CSV
  python implementacion/almaro/scripts/corregir_umv_display_gev.py --apply  # tras 'confirmar umv display almaro'
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "almaro"
ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parents[1]
GEV_ARTICULOS = BASE / "inputs" / "gev-articulos-20261001.json"
GEV_PRECIOS = BASE / "inputs" / "gev-precios-20261001.json"
VIGENCIA_MIN = "20250601"
VIGENCIA_IGNORAR_LISTAS = {"CASA"}
PRECIO_DISPLAY_MIN = 500.0
EXCEL_CSV = BASE / "inputs" / "productos-19092026-umv.csv"
CSV_OUT = BASE / "outputs" / "propuesta-umv-display-gev-20261001.csv"
CSV_LOG = BASE / "outputs" / "carga-umv-display-gev-20261001-log.csv"
BATCH = 80


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def _int(v) -> int | None:
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def load_gev() -> dict[str, dict]:
    rows = json.loads(GEV_ARTICULOS.read_text(encoding="utf-8"))
    return {str(r.get("CODIGO_ARTICULO") or "").strip(): r for r in rows if r.get("CODIGO_ARTICULO")}


def load_vigencias() -> dict[str, str]:
    """Última FECHA_INICIO_VIGENCIA (YYYYMMDD) por SKU, sin la lista CASA.

    CASA tiene fecha 20260901 en todos los SKUs aunque el precio sea de 2023.
    """
    out: dict[str, str] = {}
    for r in json.loads(GEV_PRECIOS.read_text(encoding="utf-8")):
        if str(r.get("ID_LISTA_PRECIO") or "").strip() in VIGENCIA_IGNORAR_LISTAS:
            continue
        code = str(r.get("CODIGO_ARTICULO") or "").strip()
        fecha = str(r.get("FECHA_INICIO_VIGENCIA") or "").strip()
        if code and fecha > out.get(code, ""):
            out[code] = fecha
    return out


def load_excel_bu_di() -> dict[str, int]:
    out: dict[str, int] = {}
    with EXCEL_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            code = (r.get("codigo") or "").strip()
            n = _int(r.get("bu_di"))
            if code and n and code not in out:
                out[code] = n
    return out


async def connect() -> asyncpg.Connection:
    load_dotenv(ROOT.parent / "backend-supabase" / ".env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("[FAIL] Falta SUPABASE_DB_URL")
    return await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)


async def build_proposal(conn: asyncpg.Connection) -> tuple[list[dict], Counter]:
    gev = load_gev()
    vigencias = load_vigencias()
    bu_di = load_excel_bu_di()
    products = await conn.fetch(
        f"""
        SELECT p.product_code, p.nombre, p.en_catalogo, p.umv_tipo, p.unidad_minima_de_venta,
               p.unidades_por_display, p.displays_por_bulto, p.unidades_por_bulto,
               p.cantidad_minima_de_venta, p.caja_semantica,
               (SELECT pp.precio_unidad FROM "{SCHEMA}".precios_productos pp
                 WHERE pp.product_code = p.product_code AND pp.lista_precios_id = 11) AS precio_kipp
        FROM "{SCHEMA}".productos p
        """
    )
    stats: Counter = Counter()
    rows: list[dict] = []
    for p in products:
        g = gev.get(p["product_code"])
        uv = str((g or {}).get("UNIDAD_VENTA") or "").strip().upper()
        stats[f"gev_{uv or 'sin_articulo'}__umv_{p['umv_tipo']}"] += 1
        if uv != "DI" or p["umv_tipo"] != "unidad":
            continue
        upd = _int(g.get("CANTIDAD_UNIDADES_UNIDAD_VENTA")) or p["unidades_por_display"]
        dpb = p["displays_por_bulto"] or bu_di.get(p["product_code"])
        vigencia = vigencias.get(p["product_code"], "")
        precio = float(p["precio_kipp"] or 0)
        if vigencia < VIGENCIA_MIN:
            motivo = "precio_gev_desactualizado"
        elif precio < PRECIO_DISPLAY_MIN:
            motivo = "precio_display_bajo"
        else:
            motivo = ""
        rows.append(
            {
                "incluir": "no" if motivo else "si",
                "motivo": motivo,
                "gev_vigencia_precio": vigencia,
                "gev_stock": g.get("STOCK"),
                "product_code": p["product_code"],
                "nombre": p["nombre"],
                "gev_descripcion": str(g.get("DESCRIPCION_ARTICULO") or "").strip(),
                "gev_unidad_venta": uv,
                "gev_unidades_display": g.get("CANTIDAD_UNIDADES_UNIDAD_VENTA"),
                "gev_unidad_minima_venta": g.get("UNIDAD_MINIMA_VENTA"),
                "en_catalogo": p["en_catalogo"],
                "precio_kipp_display": round(float(p["precio_kipp"]), 2) if p["precio_kipp"] else "",
                "umv_tipo_actual": p["umv_tipo"],
                "unidades_por_display_actual": p["unidades_por_display"] or "",
                "displays_por_bulto_actual": p["displays_por_bulto"] or "",
                "unidades_por_bulto_actual": p["unidades_por_bulto"] or "",
                "cantidad_minima_actual": p["cantidad_minima_de_venta"] or "",
                "caja_semantica_actual": p["caja_semantica"] or "",
                "umv_tipo_propuesto": "display",
                "unidad_minima_de_venta_propuesta": "DISPLAY",
                "unidades_por_display_propuesto": upd if upd and upd > 1 else "",
                "displays_por_bulto_propuesto": dpb or "",
                "unidades_por_bulto_propuesto": dpb or 1,
                "cantidad_minima_propuesta": 1,
                "caja_semantica_propuesta": "display",
            }
        )
    rows.sort(key=lambda r: (r["incluir"] != "si", not r["en_catalogo"], r["product_code"]))
    return rows, stats


async def apply(conn: asyncpg.Connection, rows: list[dict]) -> int:
    updated = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        result = await conn.fetch(
            f"""
            UPDATE "{SCHEMA}".productos AS p SET
              umv_tipo = 'display',
              unidad_minima_de_venta = 'DISPLAY',
              unidades_por_display = v.upd,
              displays_por_bulto = v.dpb,
              unidades_por_bulto = v.upb,
              cantidad_minima_de_venta = 1,
              caja_semantica = 'display',
              updated_at = now()
            FROM unnest($1::text[], $2::int[], $3::int[], $4::int[]) AS v(product_code, upd, dpb, upb)
            WHERE p.product_code = v.product_code AND p.umv_tipo = 'unidad'
            RETURNING p.product_code
            """,
            [r["product_code"] for r in chunk],
            [r["unidades_por_display_propuesto"] or None for r in chunk],
            [r["displays_por_bulto_propuesto"] or None for r in chunk],
            [r["unidades_por_bulto_propuesto"] for r in chunk],
        )
        updated += len(result)
        print(f"  … lote {i // BATCH + 1} actualizados={len(result)} acumulado={updated}")

    sample = await conn.fetch(
        f"""
        SELECT product_code, nombre, umv_tipo, unidades_por_display, displays_por_bulto,
               unidades_por_bulto, cantidad_minima_de_venta, caja_semantica
        FROM "{SCHEMA}".productos
        WHERE product_code IN ('14430', '13056', '6408', '1104', '1009', '12901')
        ORDER BY product_code
        """
    )
    print("[VERIFY] muestra:")
    for s in sample:
        print(
            f"  {s['product_code']} {s['nombre'][:36]:36} umv={s['umv_tipo']} "
            f"upd={s['unidades_por_display']} dpb={s['displays_por_bulto']} "
            f"upb={s['unidades_por_bulto']} min={s['cantidad_minima_de_venta']} caja={s['caja_semantica']}"
        )
    left = await conn.fetchval(
        f"""SELECT count(*) FROM "{SCHEMA}".productos
            WHERE umv_tipo = 'unidad' AND product_code = ANY($1::text[])""",
        [r["product_code"] for r in rows],
    )
    print(f"[VERIFY] SKUs propuestos que siguen en unidad: {left}")
    return updated


def vectorize(codes: list[str]) -> int:
    backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
    vec_url = f"{backend_url}/{SCHEMA}/productos/vectorize"
    print(f"[*] Vectorize {len(codes)} SKU → {vec_url}")
    scheduled = 0
    for i in range(0, len(codes), 200):
        chunk = codes[i : i + 200]
        try:
            resp = requests.post(vec_url, json=chunk, timeout=60)
        except Exception as exc:
            print(f"[WARN] vectorize falló: {exc}")
            continue
        if resp.status_code == 200:
            scheduled += len(chunk)
        else:
            print(f"[WARN] vectorize HTTP {resp.status_code}: {resp.text[:300]}")
    return scheduled


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    conn = await connect()
    try:
        rows, stats = await build_proposal(conn)
        print(f"[*] Schema={SCHEMA} | GEV={GEV_ARTICULOS.name}")
        for key, n in sorted(stats.items()):
            print(f"    {key:32} {n}")
        if not rows:
            return 0
        with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        excluded = [r for r in rows if r["incluir"] != "si"]
        rows = [r for r in rows if r["incluir"] == "si"]
        print(
            f"[*] DI cargados como unidad={len(rows) + len(excluded)} | a corregir={len(rows)} "
            f"(en catálogo={sum(1 for r in rows if r['en_catalogo'])}, "
            f"sin displays_por_bulto={sum(1 for r in rows if not r['displays_por_bulto_propuesto'])}) "
            f"| fuera={dict(Counter(r['motivo'] for r in excluded))}"
        )
        print(f"OK propuesta {CSV_OUT.relative_to(ROOT)}")
        if not args.apply or not rows:
            return 0
        updated = await apply(conn, rows)
    finally:
        await conn.close()

    with CSV_LOG.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["product_code", "umv_tipo", "unidades_por_display", "displays_por_bulto", "unidades_por_bulto", "cantidad_minima_de_venta"])
        for r in rows:
            w.writerow([r["product_code"], "display", r["unidades_por_display_propuesto"], r["displays_por_bulto_propuesto"], r["unidades_por_bulto_propuesto"], 1])
    scheduled = vectorize([r["product_code"] for r in rows])
    print(f"OK carga UMV display {SCHEMA}: actualizados={updated} vectorize≈{scheduled} log={CSV_LOG.name}")
    if updated != len(rows):
        print(f"[FAIL] actualizados {updated} != esperados {len(rows)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
