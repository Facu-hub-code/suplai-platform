#!/usr/bin/env python3
"""Corrige UMV bulto y categoría (segmento Excel) en schema almaro.

Fuente: productos 19092026.xls
- UM de Ventas = BU y el precio ya es el del bulto → unidad_minima_de_venta = BULTO
- Columna Segmento → categoría del producto

Uso:
  python implementacion/almaro/scripts/corregir_umv_bulto_y_segmento.py
  python implementacion/almaro/scripts/corregir_umv_bulto_y_segmento.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import asyncpg
import xlrd
from dotenv import load_dotenv

SCHEMA = "almaro"
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
XLS_CANDIDATES = [
    Path("/Users/facundolorenzo/Desktop/productos 19092026.xls"),
    Path(__file__).resolve().parents[1] / "inputs" / "productos 19092026.xls",
]
CSV_UMV = OUT / "propuesta-umv-bulto-20260928.csv"
CSV_SEG = OUT / "propuesta-segmento-20260928.csv"
BATCH = 80


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def norm_code(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        if value != value:
            return ""
        if value == int(value):
            return str(int(value))
        value = str(value)
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def repair_enie(text: str) -> str:
    """El xls perdió la eñe y la guardó como '?'. El resto de acentos sí está."""
    return (
        text.replace("BA?AD", "BAÑAD")
        .replace("Ba?ad", "Bañad")
        .replace("NI?O", "NIÑO")
        .replace("Ni?o", "Niño")
        .replace("SE?OR", "SEÑOR")
        .replace("A?O", "AÑO")
    )


def clean_segmento(value) -> str:
    text = repair_enie(str(value or "")).strip()
    text = " ".join(text.split())
    return text


def as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return int(round(number))


def load_excel() -> dict[str, dict]:
    path = next((p for p in XLS_CANDIDATES if p.exists()), None)
    if path is None:
        raise SystemExit(f"[FAIL] No está el Excel en {XLS_CANDIDATES}")
    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_index(0)
    rows: dict[str, dict] = {}
    dupes = 0
    for index in range(1, sheet.nrows):
        code = norm_code(sheet.cell_value(index, 2))
        if not code:
            continue
        if code in rows:
            dupes += 1
            continue
        rows[code] = {
            "product_code": code,
            "descripcion": str(sheet.cell_value(index, 5) or "").strip(),
            "division": str(sheet.cell_value(index, 10) or "").strip(),
            "rubro": str(sheet.cell_value(index, 11) or "").strip(),
            "segmento": clean_segmento(sheet.cell_value(index, 12)),
            "um_ventas": str(sheet.cell_value(index, 50) or "").strip().upper(),
            "cant_min": as_int(sheet.cell_value(index, 51)) or 0,
            "um_precio": str(sheet.cell_value(index, 53) or "").strip().upper(),
            "bu_un": as_int(sheet.cell_value(index, 55)) or 0,
            "bu_di": as_int(sheet.cell_value(index, 59)) or 0,
            "di_un": as_int(sheet.cell_value(index, 60)) or 0,
        }
    print(f"[*] Excel {path.name} filas_unicas={len(rows)} duplicados_codigo={dupes}")
    return rows


def index_excel(rows: dict[str, dict]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for code in rows:
        keys = {code, code.lstrip("0") or "0"}
        for key in keys:
            index.setdefault(key, []).append(code)
    return index


def match_excel(product_code: str, index: dict[str, list[str]], rows: dict[str, dict]) -> dict | None:
    for key in (product_code, product_code.lstrip("0") or "0"):
        hits = index.get(key) or []
        if len(hits) == 1:
            return rows[hits[0]]
        exact = [hit for hit in hits if hit == product_code]
        if len(exact) == 1:
            return rows[exact[0]]
    return None


# Por encima de este importe en lista TRADICIONAL, el número de GEV es el
# bulto (helado 16x62 g ~ $37.000). Por debajo, el precio es la unidad y el
# mínimo ya obliga a llevar el bulto: no se reetiqueta para no mentir el precio.
PRECIO_BULTO_DESDE = 8000


def bulto_decision(excel: dict, current_min: int, precio) -> tuple[str, int, str]:
    """Devuelve (accion, minimo_propuesto, motivo).

    El precio de GEV está en la UM de precio. Si esa UM ya es el bulto
    (precio BU, precio UN con un solo ítem por bulto, o un importe de bulto),
    la tienda dice BULTO y el mínimo es 1 bulto, no N unidades internas.
    """
    if excel["um_ventas"] != "BU":
        return "sin_cambio", current_min, "um_ventas_no_es_bulto"
    if excel["um_precio"] == "DI":
        return "revisar", current_min, "precio_en_display"
    minimo = excel["cant_min"] if excel["cant_min"] > 0 else 1
    if excel["um_precio"] == "BU" or excel["bu_un"] <= 1:
        return "bulto", minimo, "precio_es_el_bulto"
    try:
        importe = float(precio) if precio is not None else 0
    except (TypeError, ValueError):
        importe = 0
    if importe >= PRECIO_BULTO_DESDE:
        return "bulto", minimo, "importe_de_bulto"
    return "revisar", current_min, f"precio_unidad_bu_un_{excel['bu_un']}"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


async def fetch_products(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(
        f"""
        SELECT p.product_code, p.nombre, p.unidad_minima_de_venta, p.umv_tipo,
               p.caja_semantica, p.cantidad_minima_de_venta, p.unidades_por_bulto,
               p.en_catalogo,
               (
                 SELECT pp.precio_unidad
                 FROM "{SCHEMA}".precios_productos pp
                 WHERE pp.product_code = p.product_code AND pp.lista_precios_id = 20
                 LIMIT 1
               ) AS precio_tradicional
        FROM "{SCHEMA}".productos p
        ORDER BY p.product_code
        """
    )


async def apply_bulto(conn: asyncpg.Connection, rows: list[dict]) -> int:
    updated = 0
    for start in range(0, len(rows), BATCH):
        chunk = rows[start : start + BATCH]
        result = await conn.fetch(
            f"""
            UPDATE "{SCHEMA}".productos AS p SET
              unidad_minima_de_venta = 'BULTO',
              caja_semantica = 'bulto',
              umv_tipo = 'unidad',
              cantidad_minima_de_venta = v.minimo,
              updated_at = now()
            FROM (
              SELECT * FROM unnest($1::text[], $2::int[]) AS t(product_code, minimo)
            ) AS v
            WHERE p.product_code = v.product_code
            RETURNING p.product_code
            """,
            [row["product_code"] for row in chunk],
            [int(row["minimo_propuesto"]) for row in chunk],
        )
        updated += len(result)
        print(f"  … bulto lote {start // BATCH + 1} actualizados={len(result)} acumulado={updated}")
    return updated


async def apply_segmento(conn: asyncpg.Connection, rows: list[dict]) -> dict:
    names = sorted({row["segmento"] for row in rows})
    existing = await conn.fetch(f'SELECT id, name FROM "{SCHEMA}".categorias')
    by_name = {}
    for record in existing:
        key = unicodedata.normalize("NFC", (record["name"] or "").strip())
        by_name.setdefault(key, record["id"])

    created = 0
    for offset, name in enumerate(names, start=1):
        key = unicodedata.normalize("NFC", name)
        if key in by_name:
            continue
        new_id = await conn.fetchval(
            f"""
            INSERT INTO "{SCHEMA}".categorias (name, description, parent_id, sort_order, created_at, updated_at)
            VALUES ($1, $2, NULL, $3, now(), now())
            RETURNING id
            """,
            name,
            "Segmento del maestro Excel Almaro (productos 19092026)",
            offset,
        )
        by_name[key] = new_id
        created += 1

    codes = [row["product_code"] for row in rows]
    await conn.execute(
        f'DELETE FROM "{SCHEMA}".product_categories WHERE product_code = ANY($1::text[])',
        codes,
    )
    linked = 0
    for start in range(0, len(rows), BATCH):
        chunk = rows[start : start + BATCH]
        ids = [by_name[unicodedata.normalize("NFC", row["segmento"])] for row in chunk]
        await conn.execute(
            f"""
            INSERT INTO "{SCHEMA}".product_categories (product_code, categoria_id)
            SELECT * FROM unnest($1::text[], $2::int[])
            ON CONFLICT DO NOTHING
            """,
            [row["product_code"] for row in chunk],
            ids,
        )
        linked += len(chunk)
        print(f"  … segmento lote {start // BATCH + 1} vinculados={len(chunk)} acumulado={linked}")

    docs_exist = await conn.fetchval(
        """
        SELECT EXISTS (
          SELECT 1 FROM information_schema.tables
          WHERE table_schema = $1 AND table_name = 'category_documents'
        )
        """,
        SCHEMA,
    )
    deleted = 0
    if docs_exist:
        col = await conn.fetchval(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = 'category_documents'
              AND column_name IN ('categoria_id', 'category_id')
            LIMIT 1
            """,
            SCHEMA,
        )
        if col:
            await conn.execute(
                f"""
                DELETE FROM "{SCHEMA}".category_documents d
                WHERE d.{col} IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM "{SCHEMA}".product_categories pc
                    WHERE pc.categoria_id = d.{col}
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM "{SCHEMA}".categorias ch
                    WHERE ch.parent_id = d.{col} AND ch.id <> d.{col}
                  )
                """
            )
    deleted = 0
    while True:
        batch_deleted = await conn.fetchval(
            f"""
            WITH gone AS (
              DELETE FROM "{SCHEMA}".categorias c
              WHERE NOT EXISTS (
                SELECT 1 FROM "{SCHEMA}".product_categories pc WHERE pc.categoria_id = c.id
              )
              AND NOT EXISTS (
                SELECT 1 FROM "{SCHEMA}".categorias ch
                WHERE ch.parent_id = c.id AND ch.id <> c.id
              )
              RETURNING 1
            )
            SELECT COUNT(*) FROM gone
            """
        )
        batch_deleted = int(batch_deleted or 0)
        deleted += batch_deleted
        if batch_deleted == 0:
            break
    return {"categorias_nuevas": created, "productos": linked, "categorias_vacias_borradas": deleted}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    load_dotenv(ROOT.parent / "backend-supabase" / ".env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER", file=sys.stderr)
        return 1

    excel_rows = load_excel()
    excel_index = index_excel(excel_rows)
    weird = sorted({row["segmento"] for row in excel_rows.values() if "?" in row["segmento"]})
    if weird:
        print("[*] Segmentos que siguen con '?':", weird)

    conn = await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0;")
        products = await fetch_products(conn)
        umv_out: list[dict] = []
        seg_out: list[dict] = []
        buckets = Counter()
        sin_excel = 0
        sin_segmento = 0
        for product in products:
            excel = match_excel(product["product_code"], excel_index, excel_rows)
            if excel is None:
                sin_excel += 1
                continue
            current_min = int(product["cantidad_minima_de_venta"] or 1)
            action, minimo, motivo = bulto_decision(excel, current_min, product["precio_tradicional"])
            label = (product["unidad_minima_de_venta"] or "").strip().upper()
            caja = (product["caja_semantica"] or "").strip().lower()
            cambia = action == "bulto" and (label != "BULTO" or caja != "bulto" or current_min != minimo)
            if action == "bulto":
                buckets["bulto_candidato"] += 1
                if cambia:
                    buckets["bulto_a_corregir"] += 1
            elif action == "revisar":
                buckets["bulto_revisar"] += 1
            if action in {"bulto", "revisar"}:
                umv_out.append(
                    {
                        "product_code": product["product_code"],
                        "nombre": product["nombre"],
                        "en_catalogo": product["en_catalogo"],
                        "um_ventas": excel["um_ventas"],
                        "um_precio": excel["um_precio"],
                        "bu_un": excel["bu_un"],
                        "cant_min_excel": excel["cant_min"],
                        "umv_actual": product["unidad_minima_de_venta"],
                        "minimo_actual": current_min,
                        "caja_actual": product["caja_semantica"] or "",
                        "precio_tradicional": product["precio_tradicional"],
                        "accion": action if cambia or action == "revisar" else "ya_bulto",
                        "minimo_propuesto": minimo if action == "bulto" else current_min,
                        "motivo": motivo,
                    }
                )
            segmento = excel["segmento"]
            if segmento:
                seg_out.append(
                    {
                        "product_code": product["product_code"],
                        "nombre": product["nombre"],
                        "segmento": segmento,
                        "division": excel["division"],
                        "rubro": excel["rubro"],
                    }
                )
            else:
                sin_segmento += 1

        write_csv(
            CSV_UMV,
            [
                "product_code",
                "nombre",
                "en_catalogo",
                "um_ventas",
                "um_precio",
                "bu_un",
                "cant_min_excel",
                "umv_actual",
                "minimo_actual",
                "caja_actual",
                "precio_tradicional",
                "accion",
                "minimo_propuesto",
                "motivo",
            ],
            umv_out,
        )
        write_csv(
            CSV_SEG,
            ["product_code", "nombre", "segmento", "division", "rubro"],
            seg_out,
        )
        print(
            f"[*] Catálogo={len(products)} sin_excel={sin_excel} "
            f"con_segmento={len(seg_out)} sin_segmento={sin_segmento}"
        )
        print(f"[*] UMV {dict(buckets)} filas_csv={len(umv_out)}")
        print(f"[*] Segmentos distintos a cargar={len({row['segmento'] for row in seg_out})}")
        print(f"[*] CSV {CSV_UMV.name} y {CSV_SEG.name}")

        if not args.apply:
            print("[*] Dry-run. Para escribir en almaro: --apply")
            return 0

        bulto_rows = [row for row in umv_out if row["accion"] == "bulto"]
        print(f"[*] APPLY schema={SCHEMA} bulto={len(bulto_rows)} segmento={len(seg_out)}")
        updated = await apply_bulto(conn, bulto_rows)
        seg_stats = await apply_segmento(conn, seg_out)
        verify = await conn.fetchrow(
            f"""
            SELECT
              COUNT(*) FILTER (WHERE unidad_minima_de_venta = 'BULTO') AS bulto,
              COUNT(*) FILTER (
                WHERE product_code IN ('15285','15286','15287')
              ) AS helados_foto
            FROM "{SCHEMA}".productos
            """
        )
        helados = await conn.fetch(
            f"""
            SELECT p.product_code, p.unidad_minima_de_venta, p.cantidad_minima_de_venta,
                   p.caja_semantica, c.name AS categoria
            FROM "{SCHEMA}".productos p
            LEFT JOIN "{SCHEMA}".product_categories pc ON pc.product_code = p.product_code
            LEFT JOIN "{SCHEMA}".categorias c ON c.id = pc.categoria_id
            WHERE p.product_code IN ('15285','15286','15287')
            ORDER BY p.product_code
            """
        )
        print(f"[VERIFY] etiqueta BULTO={verify['bulto']} updates_bulto={updated} segmento={seg_stats}")
        for row in helados:
            print(
                f"  {row['product_code']} umv={row['unidad_minima_de_venta']} "
                f"min={row['cantidad_minima_de_venta']} caja={row['caja_semantica']} cat={row['categoria']}"
            )
        if updated != len(bulto_rows):
            print(f"[FAIL] bulto actualizados {updated} != {len(bulto_rows)}", file=sys.stderr)
            return 1
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
