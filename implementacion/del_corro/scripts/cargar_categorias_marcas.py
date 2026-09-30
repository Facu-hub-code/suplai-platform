#!/usr/bin/env python3
"""Reemplaza la taxonomía de tienda de del_corro por Categoría web → Marca.

Origen (Excel del cliente):
  - Productos_categorias_web.xlsx: Codigo, Descripcion, Categoria web
  - Productos-en-mi-Tienda-*.xlsx:  Codigo, Marca, Descripcion

La tienda filtra por pertenencia directa en product_categories, así que cada
producto se asigna a su categoría (nivel 1) y a su marca (nivel 2).

Uso:
  python cargar_categorias_marcas.py            # dry-run: CSV + resumen
  python cargar_categorias_marcas.py --apply    # escribe en del_corro
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT.parent / "backend-supabase"
OUT = ROOT / "implementacion" / "del_corro" / "outputs" / "categorias-marcas-2026-09-30"
SCHEMA = "del_corro"
BATCH = 80

CAT_XLSX = Path.home() / "Downloads" / "Productos_categorias_web.xlsx"
MARCA_XLSX = Path.home() / "Downloads" / "Productos-en-mi-Tienda-2026-07-29.xlsx"

CATEGORIA_ORDEN = [
    "Almacén",
    "Chocolates y Alfajores",
    "Golosinas",
    "Galletitas y Snacks",
    "Panificados",
    "Lácteos",
    "Bebidas",
    "Limpieza",
    "Perfumería y Varios",
    "Mascotas",
    "Farmacia",
    "Tabaquería",
]

# Productos sin categoría web: mismo criterio que usó el cliente en su Excel.
# Orden importa: "chocolate con leche" tiene que caer antes que "leche".
REGLAS_CATEGORIA = [
    ("Tabaquería", ("cigarrillo",)),
    ("Almacén", ("jugo en polvo", "chocolate en polvo", "capsulas dolce gusto", "capsulas nespresso", "edulcorante", "ketchup", "mostaza",
                 "salsa", "arvejas", "choclo", "lentejas", "macarrones", "cafe ", "mayonesa", "premezcla")),
    ("Galletitas y Snacks", ("galletitas",)),
    ("Panificados", ("tostadas de arroz", "tostaditas de arroz", "budin")),
    ("Golosinas", ("mantecol",)),
    ("Chocolates y Alfajores", ("alfajor", "bombon", "chocolate", "chocolatin", "colmenita", "bocadito")),
    ("Lácteos", ("queso", "quesabores", "crema de leche", "dulce de leche", "manteca", "leche")),
    ("Bebidas", ("agua", "gaseosa", "soda", "bebida", "cerveza", "fernet", "aqualoe")),
    ("Limpieza", ("jabon blanco", "detergente", "insecticida", "promopack sedile", "limp. ")),
    ("Perfumería y Varios", ("jabon", "crema dental", "afeitar", "curitas", "repelente", "adhesivo")),
    ("Farmacia", ("comprimido", "capsula", "sobre", "ibuprofeno", "paracetamol", "diclofenac", "omeprazol",
                  "sildenafil", "amoxicilina", "migral", "tafirol", "sertal", "alikal", "uvasal", "vick",
                  "aspirin", "buscapina", "novalgina", "qura")),
]

# Combos, servicios y logística no se ofrecen por filtro aunque aparezcan por nombre.
EXCLUIR_FILTROS = ("combo", "servicio", "transporte", "almacenamiento", "carga/descarga", "kit ", "descuentos",
                   "articulo libre", "bandeo", "bolson", "menu saludable", "exhibidor")

MARCAS_TABACO = ("Boxer", "CJ", "Dolchester", "Euro", "Kiel", "Liverpool", "Milenio", "Pablo Emilio",
                 "Red Point", "Ruta 66")

# Misma marca escrita distinto en el Excel → nombre único en la tienda.
MARCA_ALIAS = {
    "si-diet": "Si Diet",
    "mama cocina": "Mamá Cocina",
    "ricomas": "Ricomás",
    "la veneziana": "Veneziana",
    "molino canuelas": "Cañuelas",
    "dolca": "Nescafé Dolca",
}


def _fold(value: str) -> str:
    n = unicodedata.normalize("NFKD", value or "")
    return " ".join("".join(c for c in n if not unicodedata.combining(c)).lower().split())


def _read(path: Path) -> list[tuple]:
    ws = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    return list(ws.iter_rows(values_only=True))[1:]


def _code(v) -> str:
    return str(v).strip() if v is not None else ""


def load_excels() -> tuple[dict[str, str], dict[str, str]]:
    categorias = {}
    for code, _desc, cat in _read(CAT_XLSX):
        if _code(code) and cat:
            categorias[_code(code)] = " ".join(str(cat).split())

    raw_marcas = {}
    for code, marca, _desc in _read(MARCA_XLSX):
        if _code(code) and marca:
            raw_marcas[_code(code)] = " ".join(str(marca).split())

    spellings: dict[str, Counter] = defaultdict(Counter)
    for m in raw_marcas.values():
        spellings[_fold(m)][m] += 1
    canonical = {k: c.most_common(1)[0][0] for k, c in spellings.items()}

    marcas = {}
    for code, m in raw_marcas.items():
        key = _fold(m)
        marcas[code] = MARCA_ALIAS.get(key) or canonical[key]
    return categorias, marcas


def _prepare_env() -> None:
    env_path = BACKEND / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path)
    for key in ("SUPABASE_DB_URL", "SUPABASE_DB_URL_POOLER", "DATABASE_URL"):
        val = os.getenv(key) or ""
        if ":5432/" in val:
            os.environ[key] = val.replace(":5432/", ":6543/")


def _db_url() -> str:
    url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL") or ""
    return url.replace(":5432/", ":6543/")


async def load_products(conn) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT p.product_code, p.nombre, COALESCE(p.en_catalogo, false) AS en_catalogo,
               EXISTS (
                 SELECT 1 FROM "{SCHEMA}".precios_productos pp
                 JOIN "{SCHEMA}".listas_precios lp ON lp.id = pp.lista_precios_id
                 WHERE pp.product_code = p.product_code AND lp.activa AND lp.es_publica
                   AND COALESCE(pp.precio_unidad, 0) > 0
               ) AS con_precio
        FROM "{SCHEMA}".productos p
        ORDER BY p.nombre
        """
    )
    return [dict(r) for r in rows]


def infer_categoria(nombre: str) -> str | None:
    n = _fold(nombre)
    if any(k in n for k in EXCLUIR_FILTROS):
        return None
    for categoria, needles in REGLAS_CATEGORIA:
        if any(k in n for k in needles):
            return categoria
    return None


def infer_marca(nombre: str, conocidas: list[str]) -> str | None:
    words = f" {re.sub(r'[^a-z0-9]+', ' ', _fold(nombre))} "
    for marca in conocidas:
        if f" {re.sub(r'[^a-z0-9]+', ' ', _fold(marca)).strip()} " in words:
            return marca
    return None


def build_proposal(products: list[dict], categorias: dict[str, str], marcas: dict[str, str]) -> list[dict]:
    # Marcas cortas ("Pop", "Fun", "Eco") matchean palabras sueltas del nombre.
    conocidas = sorted(
        {m for m in marcas.values() if len(m) >= 4} | set(MARCAS_TABACO),
        key=len,
        reverse=True,
    )
    items = []
    for p in products:
        code = p["product_code"]
        cat = categorias.get(code)
        marca = marcas.get(code)
        origen = "excel"
        if not cat:
            cat = infer_categoria(p["nombre"])
            origen = "inferida" if cat else ""
        origen_marca = "excel" if marca else ""
        if cat and not marca:
            marca = infer_marca(p["nombre"], conocidas)
            origen_marca = "inferida" if marca else ""
        items.append(
            {
                "product_code": code,
                "nombre": p["nombre"],
                "en_catalogo": p["en_catalogo"],
                "visible_tienda": p["en_catalogo"] and p["con_precio"],
                "categoria": cat or "",
                "marca": marca or "",
                "origen_categoria": origen,
                "origen_marca": origen_marca,
            }
        )
    return items


def write_outputs(items: list[dict], categorias: dict[str, str], marcas: dict[str, str], db_codes: set[str]) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "phase-01-1-categorias-marcas.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(items[0].keys()))
        w.writeheader()
        w.writerows(items)

    no_en_db = sorted((set(categorias) | set(marcas)) - db_codes)
    with (OUT / "codigos-excel-sin-producto.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["product_code", "categoria_web", "marca"])
        for c in no_en_db:
            w.writerow([c, categorias.get(c, ""), marcas.get(c, "")])

    visibles = [i for i in items if i["visible_tienda"]]
    resumen = {
        "productos_db": len(items),
        "visibles_tienda": len(visibles),
        "con_categoria": sum(1 for i in items if i["categoria"]),
        "con_marca": sum(1 for i in items if i["marca"]),
        "visibles_sin_categoria": sum(1 for i in visibles if not i["categoria"]),
        "visibles_sin_marca": sum(1 for i in visibles if not i["marca"]),
        "categoria_inferida": sum(1 for i in items if i["origen_categoria"] == "inferida"),
        "marca_sin_categoria": sum(1 for i in items if i["marca"] and not i["categoria"]),
        "codigos_excel_sin_producto": len(no_en_db),
        "por_categoria": dict(Counter(i["categoria"] or "(sin categoría)" for i in items).most_common()),
        "marcas_distintas": len({i["marca"] for i in items if i["marca"]}),
    }
    (OUT / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumen


async def _category_id(conn, cache: dict, name: str, parent_id: int | None, sort_order: int, nivel: str) -> int:
    key = (name.casefold(), parent_id)
    if key in cache:
        return cache[key]
    cid = await conn.fetchval(
        f"""SELECT id FROM "{SCHEMA}".categorias
            WHERE lower(name) = $1 AND parent_id IS NOT DISTINCT FROM $2
            ORDER BY id LIMIT 1""",
        name.casefold(),
        parent_id,
    )
    if cid is None:
        cid = await conn.fetchval(
            f"""INSERT INTO "{SCHEMA}".categorias (name, description, parent_id, sort_order, created_at, updated_at)
                VALUES ($1, $2, $3, $4, now(), now()) RETURNING id""",
            name,
            nivel,
            parent_id,
            sort_order,
        )
    else:
        await conn.execute(
            f"""UPDATE "{SCHEMA}".categorias SET sort_order = $2, description = $3, updated_at = now() WHERE id = $1""",
            cid,
            sort_order,
            nivel,
        )
    cache[key] = int(cid)
    return int(cid)


async def apply(conn, items: list[dict]) -> dict:
    cache: dict = {}
    assignments: list[tuple[str, int]] = []
    used: set[int] = set()

    async with conn.transaction():
        # Raíces con parent_id apuntando a sí mismas o a ids inexistentes rompen el borrado de huérfanas.
        await conn.execute(f'UPDATE "{SCHEMA}".categorias SET parent_id = NULL WHERE parent_id = id')
        await conn.execute(f'DELETE FROM "{SCHEMA}".product_categories')

        for item in items:
            if not item["categoria"]:
                continue
            orden = CATEGORIA_ORDEN.index(item["categoria"]) if item["categoria"] in CATEGORIA_ORDEN else 99
            cat_id = await _category_id(conn, cache, item["categoria"], None, orden, "Categoría web")
            used.add(cat_id)
            assignments.append((item["product_code"], cat_id))
            if item["marca"]:
                marca_id = await _category_id(conn, cache, item["marca"], cat_id, 0, "Marca")
                used.add(marca_id)
                assignments.append((item["product_code"], marca_id))

        for i in range(0, len(assignments), BATCH):
            await conn.executemany(
                f"""INSERT INTO "{SCHEMA}".product_categories (product_code, categoria_id)
                    VALUES ($1, $2) ON CONFLICT (product_code, categoria_id) DO NOTHING""",
                assignments[i : i + BATCH],
            )

        # Un solo DELETE: la FK parent_id se valida al final de la sentencia, no fila por fila.
        borradas = await conn.execute(
            f'DELETE FROM "{SCHEMA}".categorias WHERE id <> ALL($1::int[])',
            list(used),
        )

    return {
        "categorias": int(await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}".categorias')),
        "raices": int(await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}".categorias WHERE parent_id IS NULL')),
        "asignaciones": int(await conn.fetchval(f'SELECT count(*) FROM "{SCHEMA}".product_categories')),
        "productos_con_cat": int(
            await conn.fetchval(f'SELECT count(DISTINCT product_code) FROM "{SCHEMA}".product_categories')
        ),
        "categorias_viejas_borradas": int(borradas.split()[-1]),
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    categorias, marcas = load_excels()
    _prepare_env()
    import asyncpg

    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        products = await load_products(conn)
        items = build_proposal(products, categorias, marcas)
        resumen = write_outputs(items, categorias, marcas, {p["product_code"] for p in products})
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
        print(f"salida: {OUT}")
        if not args.apply:
            print("dry-run: pasá --apply para escribir en del_corro")
            return 0
        stats = await apply(conn, items)
        print(json.dumps({"apply": stats}, ensure_ascii=False, indent=2))
    finally:
        await conn.close()

    if args.apply:
        sys.path.insert(0, str(BACKEND))
        os.chdir(BACKEND)
        from utils.vectorizacion_categorias import rebuild_categoria_rag

        await rebuild_categoria_rag(SCHEMA)
        print("RAG de categorías reconstruido")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
