#!/usr/bin/env python3
"""
Etiqueta productos con GRUPO / MARCA / PROVEEDOR del Excel de ventas ERP.

Genera tags comerciales (prefijo Línea/Marca/Proveedor) y mapeos product_tags.
Por defecto dry-run → CSV preview en implementacion/el_gigante/outputs/.

Uso:
  python scripts/el_gigante_ventas/01_etiquetar_productos.py --mes marzo
  python scripts/el_gigante_ventas/01_etiquetar_productos.py --mes marzo --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

import asyncpg

from _common import (
    DEFAULT_INPUT_DIR,
    DEFAULT_SCHEMA,
    add_mes_arg,
    configure_stdout,
    db_url,
    load_catalog_product_codes,
    parse_meses,
    period_slug,
    pooler_url,
    read_ventas_meses,
    tag_name,
    tenant_outputs,
    write_csv,
    write_json,
)


def aggregate_product_tags(rows):
    """Un CodArt → valores más frecuentes de grupo/marca/proveedor."""
    by_code: dict[str, dict[str, Counter]] = {}
    for row in rows:
        if not row.cod_art:
            continue
        bucket = by_code.setdefault(row.cod_art, {"grupo": Counter(), "marca": Counter(), "proveedor": Counter()})
        if row.grupo:
            bucket["grupo"][row.grupo] += 1
        if row.marca:
            bucket["marca"][row.marca] += 1
        if row.proveedor:
            bucket["proveedor"][row.proveedor] += 1

    result = []
    for cod_art, counters in sorted(by_code.items()):
        grupo = counters["grupo"].most_common(1)[0][0] if counters["grupo"] else ""
        marca = counters["marca"].most_common(1)[0][0] if counters["marca"] else ""
        proveedor = counters["proveedor"].most_common(1)[0][0] if counters["proveedor"] else ""
        result.append(
            {
                "product_code": cod_art,
                "grupo": grupo,
                "marca": marca,
                "proveedor": proveedor,
                "tag_linea": tag_name("grupo", grupo),
                "tag_marca": tag_name("marca", marca),
                "tag_proveedor": tag_name("proveedor", proveedor),
            }
        )
    return result


async def apply_tags(schema: str, preview_rows: list[dict]) -> dict:
    url = db_url()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL")

    conn = await asyncpg.connect(url, statement_cache_size=0)
    stats = {"tags_created": 0, "tags_existing": 0, "mappings_inserted": 0, "products_updated": 0}
    try:
        await conn.execute(f"SET search_path TO {schema}, core, public, extensions")

        db_products = {
            r["product_code"]: r["id"]
            for r in await conn.fetch(
                "SELECT id, product_code FROM productos WHERE COALESCE(is_mock,false)=false"
            )
        }

        tag_names = set()
        for row in preview_rows:
            for key in ("tag_linea", "tag_marca", "tag_proveedor"):
                if row.get(key):
                    tag_names.add(row[key])

        name_to_id: dict[str, int] = {}
        for name in sorted(tag_names):
            existing = await conn.fetchval("SELECT id FROM tags WHERE name = $1", name)
            if existing:
                name_to_id[name] = existing
                stats["tags_existing"] += 1
            else:
                tid = await conn.fetchval(
                    "INSERT INTO tags (name, description) VALUES ($1, $2) RETURNING id",
                    name,
                    "Tag comercial ERP (ventas x artículo)",
                )
                name_to_id[name] = tid
                stats["tags_created"] += 1

        for row in preview_rows:
            pcode = row["product_code"]
            if pcode not in db_products:
                continue
            stats["products_updated"] += 1
            for key in ("tag_linea", "tag_marca", "tag_proveedor"):
                tname = row.get(key)
                if not tname:
                    continue
                tag_id = name_to_id[tname]
                await conn.execute(
                    """
                    INSERT INTO product_tags (product_code, tag_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    pcode,
                    tag_id,
                )
                stats["mappings_inserted"] += 1
    finally:
        await conn.close()
    return stats


def main() -> None:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Etiquetar productos el_gigante desde ventas ERP")
    parser.add_argument("--esquema", default=DEFAULT_SCHEMA)
    add_mes_arg(parser)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--apply", action="store_true", help="Escribir tags en BD (requiere confirmación explícita)")
    args = parser.parse_args()

    meses = parse_meses(args.mes, todos=args.todos)
    periodo = period_slug(meses)
    rows = read_ventas_meses(meses, args.input_dir)
    aggregated = aggregate_product_tags(rows)
    catalog = load_catalog_product_codes(args.esquema)

    preview = []
    for item in aggregated:
        in_catalog = item["product_code"] in catalog
        preview.append(
            {
                **item,
                "en_catalogo": "si" if in_catalog else "no",
                "accion": "aplicar" if in_catalog else "omitir_no_catalogo",
            }
        )

    out_dir = tenant_outputs(args.esquema)
    csv_path = out_dir / f"ventas-{periodo}-etiquetas-preview.csv"
    summary_path = out_dir / f"ventas-{periodo}-etiquetas-resumen.json"

    fieldnames = [
        "product_code",
        "grupo",
        "marca",
        "proveedor",
        "tag_linea",
        "tag_marca",
        "tag_proveedor",
        "en_catalogo",
        "accion",
    ]
    write_csv(csv_path, preview, fieldnames)

    aplicables = [r for r in preview if r["en_catalogo"] == "si"]
    summary = {
        "periodo": periodo,
        "meses": meses,
        "filas_excel": len(rows),
        "productos_unicos_excel": len(aggregated),
        "productos_en_catalogo": len(aplicables),
        "productos_fuera_catalogo": len(preview) - len(aplicables),
        "tags_unicos": len({t for r in preview for t in (r["tag_linea"], r["tag_marca"], r["tag_proveedor"]) if t}),
        "csv_preview": str(csv_path),
        "modo": "apply" if args.apply else "dry-run",
    }
    write_json(summary_path, summary)

    print(f"[*] Periodo: {periodo} ({', '.join(meses)})")
    print(f"[*] Productos únicos: {len(aggregated)} | En catálogo: {len(aplicables)}")
    print(f"[*] Preview: {csv_path}")
    print(f"[*] Resumen: {summary_path}")

    if args.apply:
        print("[!] Aplicando tags comerciales en BD...")
        stats = asyncio.run(apply_tags(args.esquema, aplicables))
        print(f"[OK] Tags creados: {stats['tags_created']}, existentes: {stats['tags_existing']}")
        print(f"[OK] Mapeos product_tags: {stats['mappings_inserted']} | Productos: {stats['products_updated']}")
    else:
        print("[*] Dry-run (default). Revisá el CSV y corré con --apply para cargar.")


if __name__ == "__main__":
    main()
