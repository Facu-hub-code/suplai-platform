#!/usr/bin/env python3
"""
Calcula índice de rotación y segmentación A/B desde ventas ERP.

Fórmula (por product_code, agregando filas del mes):
  contador     = cantidad de líneas de venta con Cant. Vendida > 0
  cantidad     = sum(Cant. Vendida)
  rotacion_raw = contador / cantidad
  margen_pct   = (sum(Total Ventas Neto) - sum(Total Costo)) / sum(Total Ventas Neto)

Segmentación A/B (100% productos con ventas):
  - Mediana de rotacion_raw y margen_pct
  - A = alta rotación (>= mediana) Y baja rentabilidad (<= mediana margen)
  - B = baja rotación (< mediana) Y alta rentabilidad (> mediana margen)
  - Resto: asignar A si rotacion_pct >= margen_pct else B (desempate)

Salida: CSV preview + opcional UPDATE productos.rotacion_index (normalizado 0-1).

Uso:
  python scripts/el_gigante_ventas/02_indice_rotacion_abc.py --mes marzo
  python scripts/el_gigante_ventas/02_indice_rotacion_abc.py --mes marzo --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import asyncpg

from _common import (
    DEFAULT_INPUT_DIR,
    DEFAULT_SCHEMA,
    SKIP_PRODUCT_CODES,
    add_mes_arg,
    configure_stdout,
    db_url,
    load_catalog_product_codes,
    parse_meses,
    period_slug,
    percentile,
    pooler_url,
    read_ventas_meses,
    tenant_outputs,
    write_csv,
    write_json,
)


def compute_metrics(rows):
    agg: dict[str, dict] = defaultdict(
        lambda: {
            "articulo": "",
            "grupo": "",
            "marca": "",
            "contador": 0,
            "cantidad": 0.0,
            "ventas_neto": Decimal("0"),
            "costo": Decimal("0"),
            "ventas_final": Decimal("0"),
        }
    )

    for row in rows:
        if not row.es_venta_positiva:
            continue
        bucket = agg[row.cod_art]
        bucket["articulo"] = row.articulo or bucket["articulo"]
        bucket["grupo"] = row.grupo or bucket["grupo"]
        bucket["marca"] = row.marca or bucket["marca"]
        bucket["contador"] += 1
        bucket["cantidad"] += row.cant_vendida
        bucket["ventas_neto"] += row.total_ventas_neto
        bucket["costo"] += row.total_costo
        bucket["ventas_final"] += row.total_ventas_final

    metrics = []
    for cod_art, data in sorted(agg.items()):
        cantidad = data["cantidad"]
        ventas_neto = float(data["ventas_neto"])
        costo = float(data["costo"])
        rotacion_raw = data["contador"] / cantidad if cantidad > 0 else 0.0
        margen_pct = (ventas_neto - costo) / ventas_neto if ventas_neto > 0 else 0.0
        metrics.append(
            {
                "product_code": cod_art,
                "articulo": data["articulo"],
                "grupo": data["grupo"],
                "marca": data["marca"],
                "contador": data["contador"],
                "cantidad": round(cantidad, 2),
                "rotacion_raw": round(rotacion_raw, 6),
                "margen_pct": round(margen_pct, 4),
                "ventas_neto": round(ventas_neto, 2),
                "costo": round(costo, 2),
            }
        )
    return metrics


def assign_abc(metrics: list[dict]) -> list[dict]:
    if not metrics:
        return metrics

    rot_values = [m["rotacion_raw"] for m in metrics]
    marg_values = [m["margen_pct"] for m in metrics]
    rot_min, rot_max = min(rot_values), max(rot_values)
    marg_min, marg_max = min(marg_values), max(marg_values)
    rot_med = percentile(rot_values, 0.5)
    marg_med = percentile(marg_values, 0.5)

    out = []
    counts = {"A": 0, "B": 0}
    for m in metrics:
        rot = m["rotacion_raw"]
        marg = m["margen_pct"]
        rot_norm = (rot - rot_min) / (rot_max - rot_min) if rot_max > rot_min else 0.5
        marg_norm = (marg - marg_min) / (marg_max - marg_min) if marg_max > marg_min else 0.5

        if rot >= rot_med and marg <= marg_med:
            clase = "A"
        elif rot < rot_med and marg > marg_med:
            clase = "B"
        else:
            clase = "A" if rot_norm >= marg_norm else "B"

        counts[clase] += 1
        out.append(
            {
                **m,
                "rotacion_index": round(rot_norm, 4),
                "margen_normalizado": round(marg_norm, 4),
                "mediana_rotacion": round(rot_med, 6),
                "mediana_margen": round(marg_med, 4),
                "clase_ab": clase,
                "interpretacion": "alta rotación / baja rentabilidad" if clase == "A" else "baja rotación / alta rentabilidad",
            }
        )
    return out, counts, rot_med, marg_med


async def apply_rotacion(schema: str, rows: list[dict]) -> dict:
    url = db_url()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL")

    conn = await asyncpg.connect(url, statement_cache_size=0)
    updated = 0
    try:
        await conn.execute(f"SET search_path TO {schema}, core, public, extensions")
        for row in rows:
            if row.get("en_catalogo") != "si":
                continue
            result = await conn.execute(
                """
                UPDATE productos
                SET rotacion_index = $1, tipo_venta = $2, updated_at = NOW()
                WHERE product_code = $3 AND COALESCE(is_mock,false)=false
                """,
                row["rotacion_index"],
                row["clase_ab"],
                row["product_code"],
            )
            if result.endswith("1"):
                updated += 1
    finally:
        await conn.close()
    return {"productos_actualizados": updated}


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Índice rotación + segmentación A/B el_gigante")
    parser.add_argument("--esquema", default=DEFAULT_SCHEMA)
    add_mes_arg(parser)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--apply", action="store_true", help="UPDATE productos.rotacion_index en BD")
    args = parser.parse_args()

    meses = parse_meses(args.mes, todos=args.todos)
    periodo = period_slug(meses)
    rows = read_ventas_meses(meses, args.input_dir)
    metrics = compute_metrics(rows)
    classified, counts, rot_med, marg_med = assign_abc(metrics)
    catalog = load_catalog_product_codes(args.esquema)

    preview = []
    for row in classified:
        preview.append(
            {
                **row,
                "en_catalogo": "si" if row["product_code"] in catalog else "no",
            }
        )

    out_dir = tenant_outputs(args.esquema)
    csv_path = out_dir / f"ventas-{periodo}-rotacion-abc-preview.csv"
    summary_path = out_dir / f"ventas-{periodo}-rotacion-abc-resumen.json"

    fieldnames = [
        "product_code",
        "articulo",
        "grupo",
        "marca",
        "contador",
        "cantidad",
        "rotacion_raw",
        "rotacion_index",
        "margen_pct",
        "margen_normalizado",
        "clase_ab",
        "interpretacion",
        "ventas_neto",
        "costo",
        "en_catalogo",
    ]
    write_csv(csv_path, preview, fieldnames)

    summary = {
        "periodo": periodo,
        "meses": meses,
        "formula": {
            "rotacion_raw": "contador / sum(cant_vendida) por product_code",
            "margen_pct": "(sum(ventas_neto) - sum(costo)) / sum(ventas_neto)",
            "rotacion_index": "min-max normalizado de rotacion_raw → productos.rotacion_index",
            "clase_A": "rotacion >= mediana AND margen <= mediana",
            "clase_B": "rotacion < mediana AND margen > mediana; resto por desempate",
        },
        "medianas": {"rotacion_raw": rot_med, "margen_pct": marg_med},
        "productos_con_ventas": len(preview),
        "clase_A": counts["A"],
        "clase_B": counts["B"],
        "pct_A": round(100 * counts["A"] / len(preview), 1) if preview else 0,
        "pct_B": round(100 * counts["B"] / len(preview), 1) if preview else 0,
        "csv_preview": str(csv_path),
        "modo": "apply" if args.apply else "dry-run",
        "nota_rentabilidad": "Sin margen explícito en ERP; se usa (ventas neto - costo) / ventas neto como proxy.",
    }
    write_json(summary_path, summary)

    print(f"[*] Periodo: {periodo} ({', '.join(meses)})")
    print(f"[*] Productos con ventas: {len(preview)} | A={counts['A']} B={counts['B']}")
    print(f"[*] Medianas: rotación={rot_med:.4f}, margen={marg_med:.4f}")
    print(f"[*] Preview: {csv_path}")

    if args.apply:
        stats = asyncio.run(apply_rotacion(args.esquema, preview))
        print(f"[OK] productos.rotacion_index actualizados: {stats['productos_actualizados']}")
    else:
        print("[*] Dry-run. Revisá CSV antes de --apply.")


if __name__ == "__main__":
    main()
