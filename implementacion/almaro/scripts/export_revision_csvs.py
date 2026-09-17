#!/usr/bin/env python3
"""Exporta CSVs de revisión Almaro (decimales sucios + overlap Gonzales/GEV)."""
from __future__ import annotations

import asyncio
import csv
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
SCHEMA = "almaro"


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
    OUT.mkdir(parents=True, exist_ok=True)

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        dirty = await conn.fetch(
            """
            SELECT
              pp.product_code,
              p.nombre,
              lp.id AS lista_precios_id,
              lp.nombre AS lista_nombre,
              lp.erp_list_id,
              pp.precio_unidad::text AS precio_unidad,
              ROUND(pp.precio_unidad::numeric, 2)::text AS precio_redondeado_2
            FROM almaro.precios_productos pp
            JOIN almaro.listas_precios lp ON lp.id = pp.lista_precios_id
            LEFT JOIN almaro.productos p ON p.product_code = pp.product_code
            WHERE lp.erp_list_id IS NOT NULL
              AND pp.precio_unidad <> ROUND(pp.precio_unidad::numeric, 2)
            ORDER BY lp.id, pp.product_code
            """
        )
        dirty_path = OUT / "precios-decimales-sucios.csv"
        with dirty_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "product_code",
                    "nombre",
                    "lista_precios_id",
                    "lista_nombre",
                    "erp_list_id",
                    "precio_unidad",
                    "precio_redondeado_2",
                ],
            )
            w.writeheader()
            for r in dirty:
                w.writerow({k: r[k] if r[k] is not None else "" for k in w.fieldnames})
        print(f"OK {dirty_path.name} filas={len(dirty)}")

        overlap = await conn.fetch(
            """
            SELECT
              a.product_code,
              a.nombre,
              a.is_mock,
              EXISTS (
                SELECT 1 FROM almaro.erp_products_raw r WHERE r.sku = a.product_code
              ) AS en_gev,
              (g.product_code IS NOT NULL) AS en_gonzales,
              a.unidad_minima_de_venta AS almaro_umv,
              a.umv_tipo AS almaro_umv_tipo,
              a.unidades_por_bulto AS almaro_upb,
              g.unidad_minima_de_venta AS gonzales_umv,
              g.umv_tipo AS gonzales_umv_tipo,
              g.unidades_por_bulto AS gonzales_upb,
              CASE
                WHEN a.is_mock
                 AND EXISTS (SELECT 1 FROM almaro.erp_products_raw r WHERE r.sku = a.product_code)
                  THEN 'unmark'
                WHEN a.is_mock THEN 'purga_mock_only'
                WHEN g.product_code IS NOT NULL
                 AND (
                   a.unidad_minima_de_venta IS DISTINCT FROM g.unidad_minima_de_venta
                   OR a.umv_tipo IS DISTINCT FROM g.umv_tipo
                   OR a.unidades_por_bulto IS DISTINCT FROM g.unidades_por_bulto
                   OR a.unidades_por_display IS DISTINCT FROM g.unidades_por_display
                   OR a.displays_por_bulto IS DISTINCT FROM g.displays_por_bulto
                   OR a.caja_semantica IS DISTINCT FROM g.caja_semantica
                 )
                  THEN 'copiar_umv_gev'
                ELSE 'ok'
              END AS accion
            FROM almaro.productos a
            LEFT JOIN gonzales.productos g ON g.product_code = a.product_code
            ORDER BY accion, a.product_code
            """
        )
        overlap_path = OUT / "productos-overlap-decision.csv"
        fields = [
            "product_code",
            "nombre",
            "is_mock",
            "en_gev",
            "en_gonzales",
            "almaro_umv",
            "almaro_umv_tipo",
            "almaro_upb",
            "gonzales_umv",
            "gonzales_umv_tipo",
            "gonzales_upb",
            "accion",
        ]
        with overlap_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            counts: dict[str, int] = {}
            for r in overlap:
                row = {k: r[k] if r[k] is not None else "" for k in fields}
                w.writerow(row)
                counts[str(r["accion"])] = counts.get(str(r["accion"]), 0) + 1
        print(f"OK {overlap_path.name} filas={len(overlap)} counts={counts}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
