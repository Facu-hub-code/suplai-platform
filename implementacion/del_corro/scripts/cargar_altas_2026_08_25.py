#!/usr/bin/env python3
"""Alta puntual Campi (del_corro): 9 SKUs desde outputs/altas-2026-08-25.

Pooler 6543, statement_cache_size=0, pool 1–2.
No inserta 02061/2061 (ya existe).
"""
from __future__ import annotations

import asyncio
import csv
import os
import unicodedata
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "implementacion" / "del_corro" / "outputs" / "altas-2026-08-25"
SCHEMA = "del_corro"
CODES = (
    "5060",
    "5061",
    "101001",
    "1015062",
    "1090073",
    "1090076",
    "10100167",
    "10500072",
    "10500081",
)

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend-supabase" / ".env")


def db_url() -> str:
    url = (
        os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL / DATABASE_URL en .env")
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    if ":5432@" in url:
        url = url.replace(":5432@", ":6543@")
    return url


def _alias_norm(raw: str) -> str:
    text = (raw or "").strip().lower()
    if not text:
        return ""
    no_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in no_accents if ch.isalnum())


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


async def main() -> None:
    productos = _read_csv(OUT / "phase-01-productos.csv")
    if [r["product_code"] for r in productos] != list(CODES):
        raise SystemExit("CSV de productos no coincide con los 9 SKUs esperados")

    price_rows: list[dict[str, str]] = []
    for name in (
        "phase-01-lista-precios-1.csv",
        "phase-01-lista-precios-2.csv",
        "phase-01-lista-precios-3.csv",
        "phase-01-lista-precios-4.csv",
        "phase-01-lista-precios-7.csv",
    ):
        price_rows.extend(_read_csv(OUT / name))

    tag_rows = _read_csv(OUT / "phase-01-tags.csv")

    pool = await asyncpg.create_pool(
        db_url(),
        min_size=1,
        max_size=2,
        statement_cache_size=0,
    )
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetch(
                    f"""
                    SELECT product_code
                    FROM {SCHEMA}.productos
                    WHERE product_code = ANY($1::text[])
                    """,
                    list(CODES),
                )
                if existing:
                    codes = ", ".join(r["product_code"] for r in existing)
                    raise SystemExit(f"Ya existen en catálogo: {codes}")

                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.productos (
                        product_code, nombre, stock, unidades_por_bulto,
                        unidad_minima_de_venta, umv_tipo, cantidad_minima_de_venta,
                        descripcion, rotacion_index, mental_priority,
                        en_catalogo, is_mock, es_pesable
                    )
                    VALUES (
                        $1, $2, $3, $4,
                        $5, $6, 1,
                        $7, $8, $9,
                        true, false, false
                    )
                    """,
                    [
                        (
                            r["product_code"],
                            r["nombre"],
                            int(float(r["stock"])),
                            int(r["unidades_por_bulto"]),
                            r["unidad_minima_de_venta"],
                            r["umv_tipo"],
                            r["descripcion"],
                            float(r["rotacion_index"]),
                            float(r["mental_priority"] or 0),
                        )
                        for r in productos
                    ],
                )

                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.precios_productos (
                        product_code, lista_precios_id, precio_unidad, is_mock
                    )
                    VALUES ($1, $2, $3, false)
                    """,
                    [
                        (
                            r["product_code"],
                            int(r["lista_precios_id"]),
                            float(r["precio_unidad"]),
                        )
                        for r in price_rows
                        if float(r["precio_unidad"]) > 0
                    ],
                )

                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.product_tags (product_code, tag_id)
                    SELECT $1, t.id
                    FROM {SCHEMA}.tags t
                    WHERE t.name = $2
                    """,
                    [(r["product_code"], r["tag"]) for r in tag_rows],
                )

                alias_tuples: list[tuple[str, str, str]] = []
                for r in productos:
                    for raw in (r.get("aliases") or "").split("|"):
                        raw = raw.strip()
                        norm = _alias_norm(raw)
                        if raw and norm:
                            alias_tuples.append((norm, raw, r["product_code"]))
                if alias_tuples:
                    await conn.executemany(
                        f"""
                        INSERT INTO {SCHEMA}.productos_aliases (
                            alias_norm, alias_raw, product_code, weight
                        )
                        VALUES ($1, $2, $3, 1)
                        ON CONFLICT (product_code, alias_norm) DO NOTHING
                        """,
                        alias_tuples,
                    )

            verify = await conn.fetch(
                f"""
                SELECT
                  p.product_code,
                  p.nombre,
                  p.stock,
                  p.unidades_por_bulto,
                  p.en_catalogo,
                  (SELECT COUNT(*) FROM {SCHEMA}.precios_productos pp
                   WHERE pp.product_code = p.product_code) AS n_precios,
                  (SELECT COUNT(*) FROM {SCHEMA}.product_tags pt
                   WHERE pt.product_code = p.product_code) AS n_tags
                FROM {SCHEMA}.productos p
                WHERE p.product_code = ANY($1::text[])
                ORDER BY p.product_code
                """,
                list(CODES),
            )
            for row in verify:
                print(
                    f"{row['product_code']}\tprecios={row['n_precios']}\t"
                    f"tags={row['n_tags']}\tstock={row['stock']}\t{row['nombre']}"
                )
            print(f"OK insertados={len(verify)}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
