#!/usr/bin/env python3
"""Exporta catálogo Gonzales (lista ERP_01) → CSVs Fase 1 para almaro.

No escribe en BD. Solo genera outputs en implementacion/almaro/.
"""
from __future__ import annotations

import asyncio
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
INP = Path(__file__).resolve().parents[1] / "inputs"

# Backend sibling repo (credentials); platform .env no tiene DB URL.
load_dotenv(ROOT.parent / "backend-supabase" / ".env")
load_dotenv(ROOT / ".env")

LISTA_FUENTE_ID = 74  # gonzales ERP_01 (pública, ~948 precios)
MULTIPLICADORES = {
    1: ("Lista Base (Público)", 1.00),
    2: ("Lista Minorista Sugerido", 1.15),
    3: ("Lista Mayorista Especial", 0.90),
    4: ("Lista Gran Distribuidor", 0.85),
}

FLUFF = re.compile(
    r"\b(descubre|descubr[ií]|irresistible|delicioso|suave|ideal|perfecto|"
    r"disfruta|cautivar[aá]|atractivo|explosión de sabor|exquisito)\b",
    re.I,
)


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def descripcion_fase1(nombre: str, cat1: str, desc_src: str | None, upb: int | None) -> str:
    """Descripción corta factual; evita fluff de marketing."""
    if desc_src and not FLUFF.search(desc_src):
        words = desc_src.strip().split()
        if 10 <= len(words) <= 25:
            return desc_src.strip().rstrip(".") + "."
    base = (cat1 or "Producto").strip()
    nom = " ".join(nombre.split())
    # Acortar nombre si es muy largo
    if len(nom) > 60:
        nom = nom[:57] + "…"
    extra = f", x{upb} unidades por bulto" if upb and upb > 1 else ""
    text = f"{base}: {nom}{extra}."
    words = text.split()
    if len(words) < 10:
        text = f"{base} de línea Arcor: {nom}, presentación mayorista{extra}."
    return text


async def main() -> int:
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)

    OUT.mkdir(parents=True, exist_ok=True)
    INP.mkdir(parents=True, exist_ok=True)

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        rows = await conn.fetch(
            """
            SELECT
              p.product_code,
              p.nombre,
              p.descripcion AS desc_src,
              p.stock,
              p.unidades_por_bulto,
              p.unidad_minima_de_venta,
              p.umv_tipo,
              p.cantidad_minima_de_venta,
              p.rotacion_index,
              p.mental_priority,
              p.image_url,
              p.en_catalogo,
              p.caja_semantica,
              pp.precio_unidad
            FROM gonzales.productos p
            JOIN gonzales.precios_productos pp
              ON pp.product_code = p.product_code
             AND pp.lista_precios_id = $1
            WHERE p.en_catalogo IS TRUE
              AND pp.precio_unidad > 0
            ORDER BY p.product_code
            """,
            LISTA_FUENTE_ID,
        )

        # Categorías por producto (hasta 4 niveles por orden de id/parent)
        cat_rows = await conn.fetch(
            """
            SELECT pc.product_code, c.name, c.parent_id, c.id, c.sort_order
            FROM gonzales.product_categories pc
            JOIN gonzales.categorias c ON c.id = pc.categoria_id
            WHERE pc.product_code = ANY($1::varchar[])
            ORDER BY pc.product_code, c.parent_id NULLS FIRST, c.sort_order, c.id
            """,
            [r["product_code"] for r in rows],
        )
        cats: dict[str, list[str]] = defaultdict(list)
        for cr in cat_rows:
            lst = cats[cr["product_code"]]
            if cr["name"] not in lst and len(lst) < 4:
                lst.append(cr["name"])

        alias_rows = await conn.fetch(
            """
            SELECT product_code, alias_raw
            FROM gonzales.productos_aliases
            WHERE product_code = ANY($1::varchar[])
            ORDER BY product_code, weight DESC NULLS LAST, alias_raw
            """,
            [r["product_code"] for r in rows],
        )
        aliases: dict[str, list[str]] = defaultdict(list)
        for ar in alias_rows:
            raw = (ar["alias_raw"] or "").strip()
            if raw and raw not in aliases[ar["product_code"]]:
                aliases[ar["product_code"]].append(raw)

        # Snapshot de origen
        meta_path = INP / "fuente_gonzales_erp01.txt"
        meta_path.write_text(
            f"fuente_schema=gonzales\n"
            f"lista_precios_id={LISTA_FUENTE_ID}\n"
            f"lista_nombre=ERP_01\n"
            f"productos_exportados={len(rows)}\n"
            f"nota=Clon Arcor para tenant almaro (mock)\n",
            encoding="utf-8",
        )

        prod_path = OUT / "phase-01-productos.csv"
        fieldnames = [
            "product_code",
            "nombre",
            "precio_lista_1",
            "stock",
            "unidades_por_bulto",
            "unidad_minima_de_venta",
            "umv_tipo",
            "categoria_1",
            "categoria_2",
            "categoria_3",
            "categoria_4",
            "aliases",
            "rotacion_index",
            "mental_priority",
            "descripcion",
            "image_url",
            "en_catalogo",
            "is_mock",
            "fuente_hoja",
        ]

        skus: list[str] = []
        precios_base: dict[str, float] = {}

        with prod_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                code = r["product_code"]
                c = cats.get(code, [])
                while len(c) < 4:
                    c.append("")
                precio = float(r["precio_unidad"])
                precios_base[code] = precio
                skus.append(code)
                al = aliases.get(code, [])
                if not al:
                    al = [r["nombre"], code]
                umv = r["unidad_minima_de_venta"]
                if umv is None:
                    umv = "unidad"
                elif isinstance(umv, (int, float)):
                    umv = str(int(umv)) if float(umv).is_integer() else str(umv)
                w.writerow(
                    {
                        "product_code": code,
                        "nombre": r["nombre"],
                        "precio_lista_1": round(precio, 4),
                        "stock": int(r["stock"] or 0),
                        "unidades_por_bulto": int(r["unidades_por_bulto"] or 1),
                        "unidad_minima_de_venta": umv,
                        "umv_tipo": r["umv_tipo"] or "unidad",
                        "categoria_1": c[0],
                        "categoria_2": c[1],
                        "categoria_3": c[2],
                        "categoria_4": c[3],
                        "aliases": "|".join(al[:8]),
                        "rotacion_index": float(r["rotacion_index"] or 0.1),
                        "mental_priority": float(r["mental_priority"] or 0),
                        "descripcion": descripcion_fase1(
                            r["nombre"], c[0], r["desc_src"], r["unidades_por_bulto"]
                        ),
                        "image_url": r["image_url"] or "",
                        "en_catalogo": "true",
                        "is_mock": "true",
                        "fuente_hoja": "gonzales:ERP_01",
                    }
                )

        # Listas de precios 1–4
        for lid, (nombre, mult) in MULTIPLICADORES.items():
            path = OUT / f"phase-01-lista-precios-{lid}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["product_code", "precio_unidad", "is_mock"])
                w.writeheader()
                for code in skus:
                    w.writerow(
                        {
                            "product_code": code,
                            "precio_unidad": round(precios_base[code] * mult, 4),
                            "is_mock": "true",
                        }
                    )

        # Resumen listas (compat template)
        resumen = OUT / "phase-01-listas-precios.csv"
        with resumen.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "lista_precios_id",
                    "nombre",
                    "multiplicador_sobre_lista_1",
                    "product_code",
                    "precio_unidad",
                    "is_mock",
                ],
            )
            w.writeheader()
            for lid, (nombre, mult) in MULTIPLICADORES.items():
                # una fila muestra por lista
                sample = skus[0]
                w.writerow(
                    {
                        "lista_precios_id": lid,
                        "nombre": nombre,
                        "multiplicador_sobre_lista_1": mult,
                        "product_code": sample,
                        "precio_unidad": round(precios_base[sample] * mult, 4),
                        "is_mock": "true",
                    }
                )

        # marca líder aproximada por categoría leaf / nombre
        brand_counts: dict[str, int] = defaultdict(int)
        for r in rows:
            c = cats.get(r["product_code"], [])
            # última categoría suele ser marca (COFLER, MOGUL, ARCOR…)
            brand = c[-1] if c else "ARCOR"
            brand_counts[brand] += 1
        marca = max(brand_counts.items(), key=lambda x: x[1])[0] if brand_counts else "ARCOR"

        print(f"OK productos={len(skus)} marca_lider_candidata={marca}")
        print(f"CSV {prod_path}")
        for lid in MULTIPLICADORES:
            print(f"CSV {OUT / f'phase-01-lista-precios-{lid}.csv'}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
