#!/usr/bin/env python3
"""Asigna categoría a los SKUs de otros proveedores de almaro (sin categoría).

Fuente: Maestro Productos Almaro.xlsx (hoja productos 19092026).
Los SKUs Arcor ya tienen la columna Segmento (corregir_umv_bulto_y_segmento.py, 2026-09-28).
Los de grupo `700 - OTROS PROVEEDORES` figuran en el Excel por Código Secundario y su
Segmento es demasiado grueso (ALMACÉN = yerba + café + Pringles + vinagre). Se usa
Sub Rubro, mapeado a categorías existentes cuando hay equivalente.

Uso:
  python implementacion/almaro/scripts/categorias_otros_proveedores.py          # propuesta CSV
  python implementacion/almaro/scripts/categorias_otros_proveedores.py --apply  # tras 'confirmar categorias almaro'
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
import openpyxl
from dotenv import load_dotenv

SCHEMA = "almaro"
ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parents[1]
XLSX_CANDIDATES = [
    Path("/Users/facundolorenzo/Desktop/Maestro Productos Almaro.xlsx"),
    BASE / "inputs" / "Maestro Productos Almaro.xlsx",
]
CSV_OUT = BASE / "outputs" / "propuesta-categorias-otros-proveedores-20261001.csv"
COL_GRUPO, COL_CODIGO, COL_SECUNDARIO, COL_DESC, COL_SEGMENTO, COL_SUBRUBRO, COL_LINEA = 0, 2, 3, 5, 12, 13, 14
COL_RUBRO = 11

SUBRUBRO_A_CATEGORIA = {
    "YERBA": "YERBA MATE",
    "CAFÉ": "CAFÉ",
    "TE": "TÉ Y MATE COCIDO",
    "MATE COCIDO": "TÉ Y MATE COCIDO",
    "MATE LISTO": "TÉ Y MATE COCIDO",
    "BOTELLA TERMICA": "BAZAR",
    "SHAMPOO": "SHAMPOO",
    "ACONDICIONADOR": "ACONDICIONADOR",
    "OLEO CAPILAR": "ACONDICIONADOR",
    "COLORACION": "COLORACIÓN CAPILAR",
    "CREMAS": "CREMAS",
    "AFEITADORA": "AFEITADORAS",
    "PRESERVATIVO": "PRESERVATIVOS",
    "ALCOHOL": "ALCOHOL",
    "PILAS": "PILAS",
    "ENCENDEDOR": "ENCENDEDORES",
    "ADHESIVO": "ADHESIVOS Y FERRETERÍA",
    "SELLADOR": "ADHESIVOS Y FERRETERÍA",
    "LUBRICANTE MULTIUSO": "ADHESIVOS Y FERRETERÍA",
    "SNACK": "SNACKS DE COPETIN",
    "CEREALES": "CEREALES PARA DESAYUNO",
    "BUDINES": "BUDINES",
    "MAGDALENAS": "BUDINES",
    "BROWNIE": "BUDINES",
    "VAINILLAS": "BIZCOCHOS",
    "RAPIDITAS": "PANIFICADOS",
    "EDULCORANTE": "ENDULZANTES",
    "MIEL": "ENDULZANTES",
    "SALSAS": "ADEREZOS",
    "JUGO DE LIMON": "ADEREZOS",
    "VINAGRES": "VINAGRES Y ACETOS",
    "ACETOS": "VINAGRES Y ACETOS",
    "ARROZ": "ARROZ",
}
BATCH = 80


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def nfc(text) -> str:
    return unicodedata.normalize("NFC", str(text or "").strip())


def cell(row: tuple, idx: int):
    return row[idx] if len(row) > idx else None


def load_excel_por_secundario() -> dict[str, dict]:
    path = next((p for p in XLSX_CANDIDATES if p.exists()), None)
    if path is None:
        raise SystemExit(f"[FAIL] No está el Excel en {XLSX_CANDIDATES}")
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    out: dict[str, dict] = {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        codigo = nfc(cell(row, COL_CODIGO))
        secundario = nfc(cell(row, COL_SECUNDARIO))
        if not secundario or secundario == codigo or secundario in out:
            continue
        out[secundario] = {
            "codigo_excel": codigo,
            "grupo": nfc(cell(row, COL_GRUPO)),
            "descripcion": nfc(cell(row, COL_DESC)),
            "proveedor": nfc(cell(row, COL_RUBRO)),
            "segmento": nfc(cell(row, COL_SEGMENTO)),
            "subrubro": nfc(cell(row, COL_SUBRUBRO)),
            "linea": nfc(cell(row, COL_LINEA)),
        }
    print(f"[*] Excel {path.name}: {len(out)} filas con código secundario")
    return out


async def connect() -> asyncpg.Connection:
    load_dotenv(ROOT.parent / "backend-supabase" / ".env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("[FAIL] Falta SUPABASE_DB_URL")
    return await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)


async def build_proposal(conn: asyncpg.Connection) -> list[dict]:
    excel = load_excel_por_secundario()
    products = await conn.fetch(
        f"""
        SELECT p.product_code, p.nombre, p.stock
        FROM "{SCHEMA}".productos p
        WHERE NOT EXISTS (
          SELECT 1 FROM "{SCHEMA}".product_categories pc WHERE pc.product_code = p.product_code
        )
        ORDER BY p.product_code
        """
    )
    rows = []
    for p in products:
        x = excel.get(p["product_code"])
        categoria = SUBRUBRO_A_CATEGORIA.get(x["subrubro"]) if x else None
        rows.append(
            {
                "product_code": p["product_code"],
                "nombre": p["nombre"],
                "stock": p["stock"],
                "codigo_excel": (x or {}).get("codigo_excel", ""),
                "proveedor": (x or {}).get("proveedor", ""),
                "linea": (x or {}).get("linea", ""),
                "segmento_excel": (x or {}).get("segmento", ""),
                "subrubro_excel": (x or {}).get("subrubro", ""),
                "categoria_propuesta": categoria or "",
                "estado": "ok" if categoria else ("sin_excel" if not x else "subrubro_sin_mapeo"),
            }
        )
    return rows


async def apply(conn: asyncpg.Connection, rows: list[dict]) -> dict:
    existing = await conn.fetch(f'SELECT id, name FROM "{SCHEMA}".categorias')
    by_name = {nfc(r["name"]): r["id"] for r in existing}
    sort_base = await conn.fetchval(f'SELECT COALESCE(MAX(sort_order), 0) FROM "{SCHEMA}".categorias')
    created = []
    for name in sorted({r["categoria_propuesta"] for r in rows}):
        if nfc(name) in by_name:
            continue
        sort_base += 1
        by_name[nfc(name)] = await conn.fetchval(
            f"""
            INSERT INTO "{SCHEMA}".categorias (name, description, parent_id, sort_order, created_at, updated_at)
            VALUES ($1, $2, NULL, $3, now(), now())
            RETURNING id
            """,
            name,
            "Sub Rubro del maestro Almaro (otros proveedores)",
            sort_base,
        )
        created.append(name)
    linked = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        result = await conn.fetch(
            f"""
            INSERT INTO "{SCHEMA}".product_categories (product_code, categoria_id)
            SELECT * FROM unnest($1::text[], $2::int[])
            ON CONFLICT DO NOTHING
            RETURNING product_code
            """,
            [r["product_code"] for r in chunk],
            [by_name[nfc(r["categoria_propuesta"])] for r in chunk],
        )
        linked += len(result)
        print(f"  … lote {i // BATCH + 1} vinculados={len(result)} acumulado={linked}")
    return {"categorias_nuevas": created, "vinculados": linked}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    conn = await connect()
    try:
        rows = await build_proposal(conn)
        CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
        with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["product_code"])
            w.writeheader()
            w.writerows(rows)
        ok = [r for r in rows if r["estado"] == "ok"]
        print(f"[*] sin categoría={len(rows)} estados={dict(Counter(r['estado'] for r in rows))}")
        for name, n in Counter(r["categoria_propuesta"] for r in ok).most_common():
            print(f"    {name:28} {n}")
        print(f"OK propuesta {CSV_OUT.relative_to(ROOT)}")
        if not args.apply or not ok:
            return 0

        print(f"[*] APPLY schema={SCHEMA} productos={len(ok)}")
        stats = await apply(conn, ok)
        left = await conn.fetchval(
            f"""
            SELECT count(*) FROM "{SCHEMA}".productos p
            WHERE NOT EXISTS (SELECT 1 FROM "{SCHEMA}".product_categories pc WHERE pc.product_code = p.product_code)
            """
        )
        sample = await conn.fetch(
            f"""
            SELECT p.product_code, p.nombre, c.name AS categoria
            FROM "{SCHEMA}".productos p
            JOIN "{SCHEMA}".product_categories pc ON pc.product_code = p.product_code
            JOIN "{SCHEMA}".categorias c ON c.id = pc.categoria_id
            WHERE p.product_code IN ('7140022', '7026323', '713H5726300', '7081050', '711927057', '14430')
            ORDER BY p.product_code
            """
        )
        print(f"[VERIFY] {stats} | productos sin categoría={left}")
        for s in sample:
            print(f"  {s['product_code']} {s['nombre'][:36]:36} → {s['categoria']}")
        if stats["vinculados"] != len(ok):
            print(f"[FAIL] vinculados {stats['vinculados']} != {len(ok)}", file=sys.stderr)
            return 1
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
