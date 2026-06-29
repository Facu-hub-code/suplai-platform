"""
setup_objetivos.py
==================
Crea 2 objetivos comerciales en field_objetivos:
  1. SKU único: el producto de mayor rotacion_index del catálogo.
     Meta: 100 unidades. Período: hoy → hoy+30 días.
  2. Grupo marca líder: top-5 SKUs de la marca líder del manifest.
     Meta: 500 unidades. Período: hoy-15 días → hoy+45 días
     (para que ya muestre progreso con los pedidos recién cargados).

Uso:
    python scripts/fase-06-1-field/setup_objetivos.py --esquema <schema>
    python scripts/fase-06-1-field/setup_objetivos.py --esquema <schema> --limpiar
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common_field import (
    create_conn,
    get_top_products,
    load_manifest,
    sanitize_schema_name,
    tenant_paths,
    write_csv_rows,
)

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


async def get_brand_top_products(
    conn, schema: str, brand: str, limit: int = 5
) -> list[dict]:
    """Top SKUs que contienen la marca en su nombre."""
    import unicodedata

    def norm(t: str) -> str:
        t = unicodedata.normalize("NFKD", t or "")
        return "".join(c for c in t if not unicodedata.combining(c)).lower()

    brand_norm = norm(brand)
    all_prods  = await get_top_products(conn, schema, limit=50)
    matched    = [p for p in all_prods if brand_norm in norm(p.get("nombre", ""))]
    return matched[:limit] if matched else all_prods[:limit]


async def table_exists(conn, schema: str, table: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM information_schema.tables WHERE table_schema=$1 AND table_name=$2 LIMIT 1",
        schema, table,
    )
    return row is not None


async def setup(schema: str, limpiar: bool) -> None:
    manifest     = load_manifest(schema)
    marca_lider  = manifest.get("marca_lider", "")

    conn = await create_conn()
    try:
        if not await table_exists(conn, schema, "field_objetivos"):
            raise SystemExit(
                f"[FAIL] Tabla field_objetivos no encontrada en schema '{schema}'.\n"
                "Verificar que Suplai Field esté migrado (SQL 56+)."
            )

        if limpiar:
            await conn.execute(f'DELETE FROM "{schema}".field_objetivo_skus')
            await conn.execute(f'DELETE FROM "{schema}".field_objetivos')
            print(f"[*] Objetivos anteriores eliminados.")

        today     = date.today()
        # 1 sola query para todos los productos que necesitamos
        top_prods = await get_top_products(conn, schema, limit=30)
        if not top_prods:
            raise SystemExit("[FAIL] No hay productos en el catálogo.")

        # Filtrar marca líder en Python (sin segunda query a la BD)
        if marca_lider:
            brand_prods = await get_brand_top_products(conn, schema, marca_lider, limit=5)
        else:
            brand_prods = top_prods[1:6]

        # --- Objetivo 1: SKU único (top rotación) ---
        top_sku   = top_prods[0]["product_code"]
        top_name  = top_prods[0].get("nombre", top_sku)
        obj1_inicio = today
        obj1_fin    = today + timedelta(days=30)

        row1 = await conn.fetchrow(
            f"""
            INSERT INTO "{schema}".field_objetivos
              (nombre, descripcion, tipo, meta_unidades, fecha_inicio, fecha_fin, activo, grupo_ref)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            RETURNING id;
            """,
            f"Meta mensual — {top_name[:40]}",
            f"Objetivo de venta del SKU estrella: {top_name}",
            "sku",
            100.0,
            obj1_inicio,
            obj1_fin,
            True,
            json.dumps({"source": "manual", "product_codes": [top_sku]}),
        )
        obj1_id = int(row1["id"])

        # --- Objetivo 2: Grupo marca líder ---
        brand_codes = [p["product_code"] for p in brand_prods]
        brand_names = [p.get("nombre", p["product_code"]) for p in brand_prods]
        brand_label = marca_lider or "Marca principal"
        obj2_inicio = today - timedelta(days=15)
        obj2_fin    = today + timedelta(days=45)

        row2 = await conn.fetchrow(
            f"""
            INSERT INTO "{schema}".field_objetivos
              (nombre, descripcion, tipo, meta_unidades, fecha_inicio, fecha_fin, activo, grupo_ref)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            RETURNING id;
            """,
            f"Impulso {brand_label} — Q3 2026",
            f"Venta de la línea {brand_label} en los próximos 45 días",
            "grupo_sku",
            500.0,
            obj2_inicio,
            obj2_fin,
            True,
            json.dumps({"source": "manual", "brand": brand_label, "product_codes": brand_codes}),
        )
        obj2_id = int(row2["id"])

        # Batch INSERT de todos los SKUs de ambos objetivos en 1 executemany
        sku_rows = [(obj1_id, top_sku)] + [(obj2_id, code) for code in brand_codes]
        await conn.executemany(
            f'INSERT INTO "{schema}".field_objetivo_skus (objetivo_id, product_code) '
            f'VALUES ($1, $2) ON CONFLICT DO NOTHING',
            sku_rows,
        )

        # Verificación
        count = await conn.fetchval(f'SELECT COUNT(*) FROM "{schema}".field_objetivos WHERE activo=true')

        # CSV output
        rows_csv = [
            {
                "objetivo_id": obj1_id,
                "nombre": f"Meta mensual — {top_name[:40]}",
                "tipo": "sku",
                "meta_unidades": 100,
                "product_codes": top_sku,
                "fecha_inicio": obj1_inicio.isoformat(),
                "fecha_fin":    obj1_fin.isoformat(),
            },
            {
                "objetivo_id": obj2_id,
                "nombre": f"Impulso {brand_label} — Q3 2026",
                "tipo": "grupo_sku",
                "meta_unidades": 500,
                "product_codes": ",".join(brand_codes),
                "fecha_inicio": obj2_inicio.isoformat(),
                "fecha_fin":    obj2_fin.isoformat(),
            },
        ]
        paths = tenant_paths(schema)
        csv_path = paths["outputs"] / "phase-06-1-objetivos.csv"
        write_csv_rows(csv_path, rows_csv, list(rows_csv[0].keys()))

        print(f"\n{'='*60}")
        print("SETUP FIELD OBJETIVOS")
        print(f"{'='*60}")
        print(f"  Objetivo 1: {top_name[:45]} ({obj1_inicio} → {obj1_fin}) — meta 100 u.")
        print(f"  Objetivo 2: {brand_label} ({obj2_inicio} → {obj2_fin}) — meta 500 u.")
        print(f"  SKUs grupo:  {', '.join(brand_names[:3])}{'...' if len(brand_names) > 3 else ''}")
        print(f"  Activos en BD: {count}")
        print(f"  CSV: {csv_path}")
        print(f"{'='*60}")

    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea objetivos comerciales para Suplai Field.")
    parser.add_argument("--esquema", required=True)
    parser.add_argument("--limpiar", action="store_true", help="Elimina objetivos existentes antes de crear.")
    args = parser.parse_args()
    asyncio.run(setup(sanitize_schema_name(args.esquema), args.limpiar))


if __name__ == "__main__":
    main()
