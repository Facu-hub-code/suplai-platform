#!/usr/bin/env python3
"""Reescribe descripciones de almaro para que el agente no mezcle display y bulto.

El texto «x12 unidades por bulto» (y equivalentes) hace que el modelo lea el
bulto como contenido del display. La descripción nueva dice primero cómo se
vende y después, en otra frase, qué trae el bulto.

Toca solo:
  - umv_tipo = display
  - unidad_minima_de_venta = BULTO
  - descripciones que dicen «unidades por bulto»

No escribe otros schemas. Sin --apply solo genera el CSV.

Uso:
  python implementacion/almaro/scripts/corregir_descripciones_unidades.py
  python implementacion/almaro/scripts/corregir_descripciones_unidades.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "almaro"
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
CSV_OUT = OUT / "propuesta-descripciones-unidades-20261001.csv"
BATCH = 80
# get_product_by_code recorta el detalle a 250 caracteres.
MAX_LEN = 240


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def gt1(value) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 1 else None


def packing_sentence(
    umv_tipo: str | None,
    unidad_minima: str | None,
    upd,
    dpb,
    upb,
) -> str:
    label = (unidad_minima or "").strip().upper()
    umv = (umv_tipo or "").strip().lower()
    upd_n, dpb_n, upb_n = gt1(upd), gt1(dpb), gt1(upb)

    if label == "BULTO":
        if upb_n:
            return f"Se vende por bulto de {upb_n} unidades."
        return "Se vende por bulto."

    if umv == "display":
        bits = ["Se vende por display."]
        if upd_n:
            bits.append(f"Cada display trae {upd_n} unidades.")
        bulto = dpb_n or upb_n
        if bulto:
            bits.append(f"El bulto trae {bulto} displays.")
        return " ".join(bits)

    bits = ["Se vende por unidad."]
    if upd_n:
        bits.append(f"El display trae {upd_n} unidades.")
    if dpb_n and upb_n:
        bits.append(f"El bulto trae {dpb_n} displays ({upb_n} unidades).")
    elif dpb_n:
        bits.append(f"El bulto trae {dpb_n} displays.")
    elif upb_n:
        bits.append(f"El bulto trae {upb_n} unidades.")
    if not upd_n:
        bits.append("No viene en display.")
    return " ".join(bits)


def nueva_descripcion(nombre: str, sentence: str) -> str:
    nom = " ".join((nombre or "").split()).rstrip(".")
    text = f"{sentence} {nom}."
    if len(text) <= MAX_LEN:
        return text
    room = MAX_LEN - len(sentence) - 2
    if room < 12:
        return sentence[:MAX_LEN]
    return f"{sentence} {nom[: room - 1].rstrip()}."


def en_alcance(row) -> bool:
    desc = (row["descripcion"] or "").lower()
    if (row["umv_tipo"] or "").strip().lower() == "display":
        return True
    if (row["unidad_minima_de_venta"] or "").strip().upper() == "BULTO":
        return True
    return "unidades por bulto" in desc


async def connect() -> asyncpg.Connection:
    load_dotenv(ROOT.parent / "backend-supabase" / ".env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("[FAIL] Falta SUPABASE_DB_URL")
    return await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)


async def load_rows(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT product_code, nombre, descripcion, umv_tipo, unidad_minima_de_venta,
               unidades_por_display, displays_por_bulto, unidades_por_bulto
        FROM "{SCHEMA}".productos
        ORDER BY product_code
        """
    )
    out: list[dict] = []
    for row in rows:
        if not en_alcance(row):
            continue
        sentence = packing_sentence(
            row["umv_tipo"],
            row["unidad_minima_de_venta"],
            row["unidades_por_display"],
            row["displays_por_bulto"],
            row["unidades_por_bulto"],
        )
        nueva = nueva_descripcion(row["nombre"] or "", sentence)
        actual = (row["descripcion"] or "").strip()
        if nueva == actual:
            continue
        out.append(
            {
                "product_code": row["product_code"],
                "nombre": row["nombre"] or "",
                "umv_tipo": row["umv_tipo"] or "",
                "unidad_minima_de_venta": row["unidad_minima_de_venta"] or "",
                "unidades_por_display": row["unidades_por_display"] or "",
                "displays_por_bulto": row["displays_por_bulto"] or "",
                "unidades_por_bulto": row["unidades_por_bulto"] or "",
                "descripcion_actual": actual,
                "descripcion_nueva": nueva,
            }
        )
    return out


async def apply(conn: asyncpg.Connection, rows: list[dict]) -> int:
    updated = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        result = await conn.fetch(
            f"""
            UPDATE "{SCHEMA}".productos AS p
            SET descripcion = v.descripcion, updated_at = now()
            FROM unnest($1::text[], $2::text[]) AS v(product_code, descripcion)
            WHERE p.product_code = v.product_code
            RETURNING p.product_code
            """,
            [r["product_code"] for r in chunk],
            [r["descripcion_nueva"] for r in chunk],
        )
        updated += len(result)
        print(f"  … lote {i // BATCH + 1} actualizados={len(result)} acumulado={updated}")
    return updated


def vectorize(codes: list[str]) -> int:
    backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
    vec_url = f"{backend_url}/{SCHEMA}/productos/vectorize"
    print(f"[*] Vectorize {len(codes)} SKU → {vec_url}")
    scheduled = 0
    for i in range(0, len(codes), 200):
        chunk = codes[i : i + 200]
        try:
            resp = requests.post(vec_url, json=chunk, timeout=60)
        except Exception as exc:
            print(f"[WARN] vectorize falló: {exc}")
            continue
        if resp.status_code == 200:
            scheduled += len(chunk)
        else:
            print(f"[WARN] vectorize HTTP {resp.status_code}: {resp.text[:300]}")
    return scheduled


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    print(f"[*] Tenant {SCHEMA} | path implementacion/{SCHEMA}/")
    conn = await connect()
    try:
        rows = await load_rows(conn)
        OUT.mkdir(parents=True, exist_ok=True)
        if rows:
            with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        print(f"[*] A corregir: {len(rows)} | CSV {CSV_OUT.name}")
        for sample in ("14429", "12901", "11658", "0102", "10116"):
            hit = next((r for r in rows if r["product_code"] == sample), None)
            if hit:
                print(f"  {sample} → {hit['descripcion_nueva']}")
        if not args.apply:
            return 0
        if not rows:
            return 0
        print(f"[*] UPDATE {SCHEMA}.productos.descripcion")
        updated = await apply(conn, rows)
        check = await conn.fetch(
            f"""
            SELECT product_code, descripcion
            FROM "{SCHEMA}".productos
            WHERE product_code = ANY($1::text[])
            ORDER BY product_code
            """,
            ["14429", "14430", "12901", "0102", "10116"],
        )
        print("[VERIFY]")
        for row in check:
            print(f"  {row['product_code']} {row['descripcion']}")
    finally:
        await conn.close()

    if args.apply and rows:
        scheduled = vectorize([r["product_code"] for r in rows])
        print(f"OK descripciones {SCHEMA}: actualizados={updated} vectorize≈{scheduled}")
        if updated != len(rows):
            print(f"[FAIL] actualizados {updated} != esperados {len(rows)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
