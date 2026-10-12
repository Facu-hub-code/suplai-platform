#!/usr/bin/env python3
"""Da de alta en almaro los SKUs de Navidad que están en la API y no en el catálogo.

Misma convención que el resto de Navidad: la descripción nombra la temporada
y hay un alias que termina en «navidad». Copia el precio del espejo ERP.

No toca otros schemas. Sin --apply solo escribe el CSV.

Uso:
  python implementacion/almaro/scripts/cargar_navidad_faltantes.py
  python implementacion/almaro/scripts/cargar_navidad_faltantes.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import sys
import unicodedata
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA = "almaro"
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
CSV_OUT = OUT / "alta-navidad-faltantes-20261012.csv"

# En la API y fuera del catálogo, pero no son Navidad.
EXCLUIR = {
    "14537",  # tallarín Arcor
    "14617",  # polenta Noel
    "9837",  # choclo Noel
    "501502",  # corazón Bon o Bon, stock 0
    "7444362",  # caja castillo/calabaza
    "15161",  # gomitas fantasmas
    "14751",  # mini tubito sandía
    "15018",  # masticable ácido
}

CAT_HARINAS = 1844
CAT_CHOCOLATES = 1842
CAT_GOLOSINAS = 1843
CAT_TURRON = 1868
CAT_CAJAS = 1791

PACK_3 = re.compile(r"(\d{1,4})\s*[xX]\s*(\d{1,4})\s*[xX]\s*(\d{1,4})")
# 18X215G → 18 unidades. 100gx35 → 35 unidades.
PACK_COUNT_FIRST = re.compile(r"(\d{1,4})\s*[xX]\s*(\d{1,4})", re.I)
PACK_COUNT_SECOND = re.compile(
    r"(\d{1,4}(?:[.,]\d+)?)\s*(?:G|GR|GRS|KG|ML)\s*[xX]\s*(\d{1,4})\b",
    re.I,
)


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def normalizar_alias(alias_raw: str) -> str:
    flat = unicodedata.normalize("NFKD", alias_raw.lower().strip())
    return "".join(c for c in flat if ("a" <= c <= "z") or ("0" <= c <= "9"))


def packing(nombre: str) -> tuple[int, str]:
    m3 = PACK_3.search(nombre or "")
    if m3:
        displays, unidades = int(m3.group(1)), int(m3.group(2))
        total = displays * unidades
        return total, (
            f"Se vende por unidad. El bulto trae {displays} displays de {unidades} unidades."
        )
    second = PACK_COUNT_SECOND.search(nombre or "")
    if second:
        unidades = int(second.group(2))
        if unidades > 1:
            return unidades, f"Se vende por unidad. El bulto trae {unidades} unidades."
    first = PACK_COUNT_FIRST.search(nombre or "")
    if first:
        unidades = int(first.group(1))
        if unidades > 1:
            return unidades, f"Se vende por unidad. El bulto trae {unidades} unidades."
    return 1, "Se vende por unidad."


def nombre_legible(nombre: str) -> str:
    s = " " + (nombre or "").upper() + " "
    s = s.replace("?", "Ñ")
    swaps = (
        (r"CONF\.?\s*MANI", "CONFITURA DE MANÍ"),
        (r"GARRAP\.?\s*ALM", "GARRAPIÑADA DE ALMENDRAS"),
        (r"GARRAPIÑADA|GARRAPIÑA|GARRAPIÑ|GARRAP\.?", "GARRAPIÑADA"),
        (r"\bPD\b", "PAN DULCE"),
        (r"CAJA DE NAVIDAD", "CAJA DE NAVIDAD"),
        (r"ALM\s*/\s*|ALM/", "ALMENDRAS "),
        (r"C/FRUTAS|C/FRUTA|C/FTA|C/FRUT", "CON FRUTA"),
        (r"SIN FRUTA|SIN FTA", "SIN FRUTA"),
        (r"C/CHIPS", "CON CHIPS"),
        (r"C/CH\s*LECH|C/CHO\s*LECH", "CON CHOCOLATE CON LECHE"),
        (r"C/CHOCOL\.?|C/CHOCOL|C/CHOC\.?|C/CH\b", "CON CHOCOLATE"),
        (r"CH\s*BCO|CHO\.?\s*BCO|CHOCOL\s*BCO|CHBCO", "CHOCOLATE BLANCO"),
        (r"CH\.?\s*LECH|CHO\.?\s*LECH", "CHOCOLATE CON LECHE"),
        (r"\bBCO\b", "BLANCO"),
        (r"\bARC\.?\b", "ARCOR"),
        (r"\bAG\b", "ÁGUILA"),
        (r"G\s*SNAV|GSNAV|SNAV", " "),
        (r"-NAV\b|\bNAV\b", " "),
        (r"\bGRS\b|\bGR\b", " "),
        (r"[./]", " "),
        (r"\s+", " "),
    )
    for pattern, repl in swaps:
        s = re.sub(pattern, repl, s)
    s = " ".join(s.split()).strip(" -*")
    s = re.sub(r"\s+C$", "", s)
    if s.upper().startswith("CAJA DE ") and "NAVIDAD" not in s.upper():
        s = "CAJA DE NAVIDAD " + s[8:]
    if not s:
        s = (nombre or "").strip()
    text = s[:1].upper() + s[1:].lower()
    return text.replace("ñ", "ñ")


def descripcion(nombre: str, venta: str) -> str:
    legible = nombre_legible(nombre)
    text = f"{venta} {legible}. Producto de Navidad, temporada navideña."
    text = re.sub(r"\s+", " ", text).strip()
    return text[:240]


def alias_de(nombre: str) -> str:
    legible = nombre_legible(nombre).lower()
    legible = re.sub(r"\b(de|la|el|los|las|unidades|displays)\b", " ", legible)
    legible = re.sub(r"[^a-z0-9áéíóúñx ]", " ", legible)
    legible = re.sub(r"\s+", " ", legible).strip()
    if "navidad" not in legible:
        legible = f"{legible} navidad".strip()
    return legible[:120]


def categoria(nombre: str) -> tuple[int, str, bool]:
    n = (nombre or "").upper()
    if "CAJA" in n:
        return CAT_CAJAS, "ACCESORIOS VENTA", False
    if "TURRON" in n or "CROCANTE" in n:
        return CAT_TURRON, "TURRON OBLEA", True
    if any(k in n for k in ("BUDIN", "PAN DULCE")) or re.search(r"\bPD\b", n):
        return CAT_HARINAS, "NAVIDAD HARINAS", True
    golosina_seca = any(k in n for k in ("GARRAP", "MANI", "CONF.", "CUBANITO", "BOTA", "MOGUL"))
    chocolate = any(
        k in n
        for k in (
            "CHOC",
            "CHOCOL",
            "C/CH",
            "COFL",
            "AGUILA",
            "AG ",
            "ROCKLET",
            "BON O BON",
            "POST",
            "DUBAI",
            "PISTACHO",
            "VOCACION",
            "VOCACIÓN",
            "LENT",
            "BLOCK",
            "CRISP",
            "CRUNCHY",
        )
    )
    if golosina_seca and not chocolate:
        return CAT_GOLOSINAS, "NAVIDAD GOLOSINAS", True
    if chocolate or any(k in n for k in ("ALMEND", "PASAS", "AVELL")):
        return CAT_CHOCOLATES, "NAVIDAD CHOCOLATES", True
    return CAT_GOLOSINAS, "NAVIDAD GOLOSINAS", True


async def connect() -> asyncpg.Connection:
    load_dotenv(ROOT.parent / "backend-supabase" / ".env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or ""
    if not db_url or ":5432/" in db_url:
        raise SystemExit("[FAIL] Falta SUPABASE_DB_URL_POOLER en el puerto 6543")
    return await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)


async def cargar(*, apply: bool) -> int:
    conn = await connect()
    try:
        rows = await conn.fetch(
            f"""
            SELECT r.sku, r.nombre, COALESCE(r.cantidad, 0)::int AS stock
            FROM {SCHEMA}.erp_products_raw r
            WHERE NOT EXISTS (
                SELECT 1 FROM {SCHEMA}.productos p WHERE p.product_code = r.sku
            )
            ORDER BY r.sku
            """
        )
        planes = []
        for row in rows:
            sku = str(row["sku"])
            if sku in EXCLUIR:
                continue
            nombre = (row["nombre"] or sku).strip()
            upb, venta = packing(nombre)
            cat_id, cat_nombre, en_catalogo = categoria(nombre)
            alias = alias_de(nombre)
            planes.append(
                {
                    "sku": sku,
                    "nombre": nombre,
                    "stock": int(row["stock"] or 0),
                    "upb": upb,
                    "descripcion": descripcion(nombre, venta),
                    "alias_raw": alias,
                    "alias_norm": normalizar_alias(alias),
                    "categoria_id": cat_id,
                    "categoria": cat_nombre,
                    "en_catalogo": en_catalogo,
                }
            )
        if not planes:
            print("[*] No hay SKUs de Navidad pendientes.")
            return 0

        precios = await conn.fetch(
            f"""
            SELECT DISTINCT ON (r.product_sku, lp.id)
                   r.product_sku, lp.id AS lista_id, r.erp_price
            FROM {SCHEMA}.erp_prices_raw r
            JOIN {SCHEMA}.listas_precios lp ON lp.erp_list_id = r.erp_list_id
            WHERE r.product_sku = ANY($1::text[])
              AND r.erp_price IS NOT NULL
              AND r.erp_price > 0
            ORDER BY r.product_sku, lp.id, r.updated_at DESC NULLS LAST
            """,
            [p["sku"] for p in planes],
        )
        precio_por_sku: dict[str, list[tuple[int, float]]] = {}
        for pr in precios:
            precio_por_sku.setdefault(str(pr["product_sku"]), []).append(
                (int(pr["lista_id"]), float(pr["erp_price"]))
            )

        OUT.mkdir(parents=True, exist_ok=True)
        with CSV_OUT.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "sku",
                    "nombre",
                    "descripcion",
                    "alias",
                    "categoria",
                    "en_catalogo",
                    "unidades_por_bulto",
                    "stock",
                    "listas_con_precio",
                ],
            )
            writer.writeheader()
            for p in planes:
                writer.writerow(
                    {
                        "sku": p["sku"],
                        "nombre": p["nombre"],
                        "descripcion": p["descripcion"],
                        "alias": p["alias_raw"],
                        "categoria": p["categoria"],
                        "en_catalogo": "si" if p["en_catalogo"] else "no",
                        "unidades_por_bulto": p["upb"],
                        "stock": p["stock"],
                        "listas_con_precio": len(precio_por_sku.get(p["sku"], [])),
                    }
                )
        print(f"[*] CSV {CSV_OUT} filas={len(planes)}")
        sin_precio = [p["sku"] for p in planes if not precio_por_sku.get(p["sku"])]
        if sin_precio:
            print(f"[!] Sin precio: {sin_precio}")

        if not apply:
            print("[*] Dry-run. Para escribir en almaro: --apply")
            return 0

        async with conn.transaction():
            for p in planes:
                inserted = await conn.fetchrow(
                    f"""
                    INSERT INTO {SCHEMA}.productos (
                        product_code, nombre, stock, unidades_por_bulto, umv_tipo,
                        cantidad_minima_de_venta, descripcion, rotacion_index,
                        unidad_minima_de_venta, mental_priority, es_pesable,
                        en_catalogo, is_mock
                    )
                    VALUES ($1, $2, $3, $4, 'unidad', 1, $5, 0, 'UNIDAD', 0, false, $6, false)
                    ON CONFLICT (product_code) DO NOTHING
                    RETURNING product_code
                    """,
                    p["sku"],
                    p["nombre"],
                    p["stock"],
                    p["upb"],
                    p["descripcion"],
                    p["en_catalogo"],
                )
                if not inserted:
                    continue
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.productos_aliases (
                        product_code, alias_raw, alias_norm, weight, created_at, updated_at
                    )
                    VALUES ($1, $2, $3, 1, now(), now())
                    ON CONFLICT DO NOTHING
                    """,
                    p["sku"],
                    p["alias_raw"],
                    p["alias_norm"],
                )
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.product_categories (product_code, categoria_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    p["sku"],
                    p["categoria_id"],
                )
                for lista_id, precio in precio_por_sku.get(p["sku"], []):
                    await conn.execute(
                        f"""
                        INSERT INTO {SCHEMA}.precios_productos (
                            product_code, lista_precios_id, precio_unidad, is_mock
                        )
                        VALUES ($1, $2, $3, false)
                        ON CONFLICT (product_code, lista_precios_id)
                        DO UPDATE SET precio_unidad = EXCLUDED.precio_unidad, updated_at = now()
                        """,
                        p["sku"],
                        lista_id,
                        precio,
                    )
        print(f"[ok] schema {SCHEMA}: {len(planes)} productos de Navidad")
        return [p["sku"] for p in planes]
    finally:
        await conn.close()


async def vectorizar(skus: list[str]) -> None:
    sys.path.insert(0, str(ROOT.parent / "backend-supabase"))
    from core.db import close_db_pool
    from utils.vectorizacion_productos import upsert_documento_producto

    sem = asyncio.Semaphore(2)

    async def one(sku: str) -> None:
        async with sem:
            await upsert_documento_producto(SCHEMA, sku)

    await asyncio.gather(*(one(sku) for sku in skus))
    await close_db_pool()
    print(f"[ok] vectorizados {len(skus)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    skus = asyncio.run(cargar(apply=args.apply))
    if args.apply and skus:
        asyncio.run(vectorizar(skus))


if __name__ == "__main__":
    main()
