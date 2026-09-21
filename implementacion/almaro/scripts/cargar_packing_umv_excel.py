#!/usr/bin/env python3
"""Aplica packing UMV del maestro Excel en schema almaro. No toca otros schemas.

Uso (tras 'confirmar carga umv excel almaro'):
  python implementacion/almaro/scripts/cargar_packing_umv_excel.py
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "almaro"
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
CSV_IN = OUT / "propuesta-packing-umv-excel-20260921.csv"
CSV_LOG = OUT / "carga-packing-umv-excel-20260921-log.csv"
BATCH = 80


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def _int_or_none(v: str) -> int | None:
    s = (v or "").strip()
    if not s:
        return None
    n = int(float(s))
    return n if n > 0 else None


def load_rows() -> list[dict]:
    rows = []
    with CSV_IN.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            umv = (r["umv_tipo_propuesto"] or "").strip().lower()
            if umv not in {"unidad", "display"}:
                continue
            umv_label = "DISPLAY" if umv == "display" else "UNIDAD"
            cm = _int_or_none(r.get("cantidad_minima_propuesta") or "") or 1
            rows.append(
                {
                    "product_code": r["product_code"].strip(),
                    "umv_tipo": umv,
                    "unidad_minima_de_venta": umv_label,
                    "unidades_por_display": _int_or_none(r.get("unidades_por_display_propuesto") or ""),
                    "displays_por_bulto": _int_or_none(r.get("displays_por_bulto_propuesto") or ""),
                    "unidades_por_bulto": _int_or_none(r.get("unidades_por_bulto_propuesto") or "") or 1,
                    "cantidad_minima_de_venta": cm,
                    "regla": (r.get("regla") or "").strip(),
                }
            )
    return rows


async def main() -> int:
    load_dotenv(ROOT.parent / "backend-supabase" / ".env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)
    rows = load_rows()
    print(f"[*] Schema={SCHEMA} | filas Excel UMV={len(rows)} | fuente={CSV_IN.name}")
    if not rows:
        print("[FAIL] CSV sin filas", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    updated = 0
    missing: list[str] = []
    payload: list[dict] = []
    try:
        await conn.execute("SET statement_timeout = 0;")
        exists = await conn.fetch(
            f'SELECT product_code FROM "{SCHEMA}".productos WHERE product_code = ANY($1::text[])',
            [r["product_code"] for r in rows],
        )
        known = {r["product_code"] for r in exists}
        payload = [r for r in rows if r["product_code"] in known]
        missing = [r["product_code"] for r in rows if r["product_code"] not in known]
        print(f"[*] A aplicar={len(payload)} | SKU ausentes={len(missing)}")

        for i in range(0, len(payload), BATCH):
            chunk = payload[i : i + BATCH]
            records = [
                (
                    r["product_code"],
                    r["umv_tipo"],
                    r["unidad_minima_de_venta"],
                    r["unidades_por_display"],
                    r["displays_por_bulto"],
                    r["unidades_por_bulto"],
                    r["cantidad_minima_de_venta"],
                )
                for r in chunk
            ]
            result = await conn.fetch(
                f"""
                UPDATE "{SCHEMA}".productos AS p SET
                  umv_tipo = v.umv_tipo,
                  unidad_minima_de_venta = v.unidad_minima_de_venta,
                  unidades_por_display = v.unidades_por_display,
                  displays_por_bulto = v.displays_por_bulto,
                  unidades_por_bulto = v.unidades_por_bulto,
                  cantidad_minima_de_venta = v.cantidad_minima_de_venta,
                  caja_semantica = CASE
                    WHEN v.umv_tipo = 'display' THEN 'display'
                    ELSE 'unidad'
                  END,
                  updated_at = now()
                FROM (
                  SELECT *
                  FROM unnest(
                    $1::text[],
                    $2::text[],
                    $3::text[],
                    $4::int[],
                    $5::int[],
                    $6::int[],
                    $7::int[]
                  ) AS t(
                    product_code,
                    umv_tipo,
                    unidad_minima_de_venta,
                    unidades_por_display,
                    displays_por_bulto,
                    unidades_por_bulto,
                    cantidad_minima_de_venta
                  )
                ) AS v
                WHERE p.product_code = v.product_code
                RETURNING p.product_code
                """,
                [r[0] for r in records],
                [r[1] for r in records],
                [r[2] for r in records],
                [r[3] for r in records],
                [r[4] for r in records],
                [r[5] for r in records],
                [r[6] for r in records],
            )
            updated += len(result)
            print(f"  … lote {i // BATCH + 1} actualizados={len(result)} acumulado={updated}")

        sample = await conn.fetch(
            f"""
            SELECT product_code, nombre, umv_tipo, unidad_minima_de_venta,
                   unidades_por_display, displays_por_bulto, unidades_por_bulto,
                   cantidad_minima_de_venta, caja_semantica
            FROM "{SCHEMA}".productos
            WHERE product_code IN ('12901', '15506', '1009', '6408', '11658', '10297', '10006')
            ORDER BY product_code
            """
        )
        print("[VERIFY] muestra:")
        for s in sample:
            print(
                f"  {s['product_code']} {s['nombre'][:36]:36} umv={s['umv_tipo']} "
                f"upd={s['unidades_por_display']} dpb={s['displays_por_bulto']} "
                f"upb={s['unidades_por_bulto']} min={s['cantidad_minima_de_venta']} "
                f"caja={s['caja_semantica']}"
            )

        stats = await conn.fetchrow(
            f"""
            SELECT
              COUNT(*) AS n,
              COUNT(*) FILTER (WHERE umv_tipo = 'display') AS umv_display,
              COUNT(*) FILTER (WHERE umv_tipo = 'unidad') AS umv_unidad,
              COUNT(*) FILTER (WHERE COALESCE(unidades_por_bulto,1) = 1) AS upb_eq_1,
              COUNT(*) FILTER (WHERE unidades_por_display IS NOT NULL) AS con_upd,
              COUNT(*) FILTER (WHERE displays_por_bulto IS NOT NULL) AS con_dpb
            FROM "{SCHEMA}".productos
            """
        )
        print(
            f"[VERIFY] catalogo n={stats['n']} umv_display={stats['umv_display']} "
            f"umv_unidad={stats['umv_unidad']} upb=1:{stats['upb_eq_1']} "
            f"con_upd={stats['con_upd']} con_dpb={stats['con_dpb']}"
        )
    finally:
        await conn.close()

    with CSV_LOG.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "product_code",
                "umv_tipo",
                "unidades_por_display",
                "displays_por_bulto",
                "unidades_por_bulto",
                "cantidad_minima_de_venta",
                "regla",
                "estado",
            ],
        )
        w.writeheader()
        known_codes = {r["product_code"] for r in payload}
        for r in rows:
            w.writerow(
                {
                    "product_code": r["product_code"],
                    "umv_tipo": r["umv_tipo"],
                    "unidades_por_display": r["unidades_por_display"] or "",
                    "displays_por_bulto": r["displays_por_bulto"] or "",
                    "unidades_por_bulto": r["unidades_por_bulto"],
                    "cantidad_minima_de_venta": r["cantidad_minima_de_venta"],
                    "regla": r["regla"],
                    "estado": "omitido_sku_ausente" if r["product_code"] not in known_codes else "actualizado",
                }
            )

    vectorize_codes = [r["product_code"] for r in payload]
    backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
    vec_url = f"{backend_url}/{SCHEMA}/productos/vectorize"
    print(f"[*] Vectorize {len(vectorize_codes)} SKU → {vec_url}")
    scheduled = 0
    try:
        for i in range(0, len(vectorize_codes), 200):
            chunk = vectorize_codes[i : i + 200]
            resp = requests.post(vec_url, json=chunk, timeout=60)
            if resp.status_code == 200:
                scheduled += len(chunk)
                print(f"  … vectorize OK lote {i // 200 + 1}")
            else:
                print(f"[WARN] vectorize HTTP {resp.status_code}: {resp.text[:300]}")
    except Exception as exc:
        print(f"[WARN] vectorize falló: {exc}")

    print(
        f"OK carga UMV Excel {SCHEMA}: actualizados={updated} "
        f"vectorize_encolados≈{scheduled} log={CSV_LOG.name}"
    )
    if missing:
        print(f"[WARN] SKU del CSV no estaban en productos: {missing[:10]}")
    if updated != len(payload):
        print(f"[FAIL] actualizados {updated} != esperados {len(payload)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
