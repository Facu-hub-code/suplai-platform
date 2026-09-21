#!/usr/bin/env python3
"""Aplica packing confianza=alta en schema almaro. No toca otros schemas.

Uso (tras 'confirmar carga packing almaro'):
  python implementacion/almaro/scripts/cargar_packing_nombres.py
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
CSV_IN = OUT / "propuesta-packing-unidades-20260921.csv"
CSV_LOG = OUT / "carga-packing-unidades-20260921-log.csv"
BATCH = 80


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def _int_or_none(v: str) -> int | None:
    s = (v or "").strip()
    if not s:
        return None
    n = int(s)
    return n if n > 0 else None


def load_alta_rows() -> list[dict]:
    rows = []
    with CSV_IN.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("confianza") or "").strip().lower() != "alta":
                continue
            umv = (r["umv_tipo_propuesto"] or "").strip().lower()
            if umv not in {"unidad", "display"}:
                continue
            umv_label = (r["unidad_minima_de_venta_propuesta"] or "").strip().upper()
            if umv == "display":
                umv_label = "DISPLAY"
            else:
                umv_label = "UNIDAD"
            rows.append(
                {
                    "product_code": r["product_code"].strip(),
                    "umv_tipo": umv,
                    "unidad_minima_de_venta": umv_label,
                    "unidades_por_display": _int_or_none(r.get("unidades_por_display_propuesto") or ""),
                    "displays_por_bulto": _int_or_none(r.get("displays_por_bulto_propuesto") or ""),
                    "unidades_por_bulto": _int_or_none(r.get("unidades_por_bulto_propuesto") or "") or 1,
                    "accion": r.get("accion") or "",
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
    rows = load_alta_rows()
    print(f"[*] Schema={SCHEMA} | filas confianza alta={len(rows)} | fuente={CSV_IN.name}")
    if not rows:
        print("[FAIL] CSV sin filas alta", file=sys.stderr)
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
                )
                for r in chunk
            ]
            result = await conn.fetch(
                f"""
                UPDATE "{SCHEMA}".productos AS p SET
                  umv_tipo = v.umv_tipo,
                  unidad_minima_de_venta = v.unidad_minima_de_venta,
                  unidades_por_display = COALESCE(v.unidades_por_display, p.unidades_por_display),
                  displays_por_bulto = COALESCE(v.displays_por_bulto, p.displays_por_bulto),
                  unidades_por_bulto = v.unidades_por_bulto,
                  caja_semantica = CASE
                    WHEN v.umv_tipo = 'display' THEN
                      CASE
                        WHEN p.caja_semantica IN ('display', 'bulto', 'ambiguo') THEN p.caja_semantica
                        ELSE 'display'
                      END
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
                    $6::int[]
                  ) AS t(
                    product_code,
                    umv_tipo,
                    unidad_minima_de_venta,
                    unidades_por_display,
                    displays_por_bulto,
                    unidades_por_bulto
                  )
                ) AS v
                WHERE p.product_code = v.product_code
                RETURNING p.product_code,
                          (p.unidades_por_bulto IS DISTINCT FROM v.unidades_por_bulto
                           OR p.umv_tipo IS DISTINCT FROM v.umv_tipo) AS needs_vector
                """,
                [r[0] for r in records],
                [r[1] for r in records],
                [r[2] for r in records],
                [r[3] for r in records],
                [r[4] for r in records],
                [r[5] for r in records],
            )
            # RETURNING sees NEW values so needs_vector would be false. Vectorize all
            # SKUs whose upb or umv changed vs CSV actual: simpler to vectorize the chunk
            # where accion is cargar/copiar or umv changed. We pass all chunk codes
            # whose packing is now in the RAG-relevant fields (upb/umv).
            updated += len(result)
            print(f"  … lote {i // BATCH + 1} actualizados={len(result)} acumulado={updated}")

        sample = await conn.fetch(
            f"""
            SELECT product_code, nombre, umv_tipo, unidad_minima_de_venta,
                   unidades_por_display, displays_por_bulto, unidades_por_bulto, caja_semantica
            FROM "{SCHEMA}".productos
            WHERE product_code IN ('12901', '15506', '1009', '6408')
            ORDER BY product_code
            """
        )
        print("[VERIFY] muestra:")
        for s in sample:
            print(
                f"  {s['product_code']} {s['nombre'][:36]:36} umv={s['umv_tipo']} "
                f"upd={s['unidades_por_display']} dpb={s['displays_por_bulto']} "
                f"upb={s['unidades_por_bulto']} caja={s['caja_semantica']}"
            )

        stats = await conn.fetchrow(
            f"""
            SELECT
              COUNT(*) FILTER (WHERE umv_tipo = 'display') AS umv_display,
              COUNT(*) FILTER (WHERE umv_tipo = 'unidad') AS umv_unidad,
              COUNT(*) FILTER (WHERE COALESCE(unidades_por_bulto,1) = 1) AS upb_eq_1,
              COUNT(*) FILTER (WHERE unidades_por_display IS NOT NULL) AS con_upd,
              COUNT(*) FILTER (WHERE displays_por_bulto IS NOT NULL) AS con_dpb
            FROM "{SCHEMA}".productos
            """
        )
        print(
            f"[VERIFY] catalogo umv_display={stats['umv_display']} umv_unidad={stats['umv_unidad']} "
            f"upb=1:{stats['upb_eq_1']} con_upd={stats['con_upd']} con_dpb={stats['con_dpb']}"
        )
    finally:
        await conn.close()

    vectorize_codes = [
        r["product_code"]
        for r in payload
        if r["accion"] in {"cargar_packing_desde_nombre", "copiar_gonzales_y_completar"}
        or r["umv_tipo"] == "display"
    ]
    # unique preserve
    seen: set[str] = set()
    vectorize_codes = [c for c in vectorize_codes if not (c in seen or seen.add(c))]

    with CSV_LOG.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["product_code", "umv_tipo", "unidades_por_display", "displays_por_bulto", "unidades_por_bulto", "accion", "estado"],
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
                    "accion": r["accion"],
                    "estado": "omitido_sku_ausente" if r["product_code"] not in known_codes else "actualizado",
                }
            )

    backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
    vec_url = f"{backend_url}/{SCHEMA}/productos/vectorize"
    print(f"[*] Vectorize {len(vectorize_codes)} SKU con bulto/UMV nuevo → {vec_url}")
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

    print(f"OK carga packing {SCHEMA}: actualizados={updated} vectorize_encolados≈{scheduled} log={CSV_LOG.name}")
    if missing:
        print(f"[WARN] SKU del CSV no estaban en productos: {missing[:10]}")
    if updated != len(payload):
        print(f"[FAIL] actualizados {updated} != esperados {len(payload)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
