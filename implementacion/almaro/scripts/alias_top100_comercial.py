#!/usr/bin/env python3
"""Alias y descripción comercial del top 100 de Almaro.

El nombre de ERP no siempre es el que pide el kiosco. "Chocolate block" no
está en COFLER BLOCK 8x20x38G, y "turrones" no matchea "turron". Esos huecos
salen del ranking de producción (2026-10-20).

Sin --apply solo escribe el CSV. Con --apply inserta aliases, antepone la
frase a la descripción y deja los caso.json del E2E.

Uso:
  python implementacion/almaro/scripts/alias_top100_comercial.py
  python implementacion/almaro/scripts/alias_top100_comercial.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import unicodedata
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA = "almaro"
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
CASOS = Path(__file__).resolve().parents[1] / "casos-reales" / "casos"
CRUCE = OUT / "top100-cruce-catalogo-20261020.csv"
PROPUESTA = OUT / "top100-alias-comercial-20261020.csv"

# Frase que la gente dice y que el nombre de ERP no contiene.
HABLADO = {
    "5312": "chocolate block",
    "4013": "turrones",
}

STOP = {
    "de", "del", "la", "el", "los", "las", "y", "o", "en", "con", "para",
    "por", "un", "una", "unos", "unas",
}
PACK = re.compile(
    r"\b\d{1,4}\s*[xX×]\s*\d{1,4}(?:\s*[xX×]\s*\d{1,4})?(?:\s*[xX×]\s*\d{1,4})?",
)
TAIL = re.compile(r"\b\d{1,4}(?:[.,]\d+)?\s*(?:g|gr|grs|kg|ml|u)\b", re.I)


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def fold(value: str) -> str:
    flat = unicodedata.normalize("NFKD", value or "")
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return flat.lower()


def alias_norm(value: str) -> str:
    return "".join(c for c in fold(value) if c.isalnum())


def tokens(value: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for tok in re.findall(r"[a-z0-9]+", fold(value)):
        if len(tok) < 4 or tok in STOP or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def hablado_desde_nombre(nombre: str) -> str:
    s = PACK.sub(" ", nombre or "")
    s = TAIL.sub(" ", s)
    s = re.sub(r"[^0-9a-zA-ZáéíóúüñÁÉÍÓÚÜÑ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def frase(codigo: str, nombre: str) -> str:
    return HABLADO.get(codigo) or hablado_desde_nombre(nombre)


def cubre(token: str, nombre: str, normas: list[str]) -> bool:
    if token in fold(nombre):
        return True
    return any(token in norma for norma in normas)


async def connect() -> asyncpg.Connection:
    load_dotenv(ROOT.parent / "backend-supabase" / ".env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or ""
    if not db_url or ":5432/" in db_url:
        raise SystemExit("[FAIL] Falta SUPABASE_DB_URL_POOLER en el puerto 6543")
    return await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)


def leer_cruce() -> list[dict[str, str]]:
    with CRUCE.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def escribir_casos(filas: list[dict[str, str]]) -> None:
    for fila in filas:
        if fila["accion_alias"] == "no-existe":
            continue
        orden = int(fila["orden"])
        codigo = fila["codigo"]
        slug = re.sub(r"[^a-z0-9]+", "-", fold(fila["frase"]))[:40].strip("-")
        case_dir = CASOS / f"top100-{orden:03d}-{slug}"
        case_dir.mkdir(parents=True, exist_ok=True)
        mensaje = f"Cuánto sale {fila['frase']}"
        spec = {
            "name": f"[Top 100] {fila['frase']}",
            "slug": case_dir.name,
            "sequential_order": 100 + orden,
            "message": mensaje,
            "expected_tools": [],
            "expected_tools_any": ["search_products"],
            "expected_skus": [codigo],
            "expected_behavior": (
                f"Tiene que buscar con search_products y ofrecer el código {codigo} "
                f"({fila['nombre']}) o un hermano de la misma línea con stock. "
                "No debe cotizar una marca distinta."
            ),
            "tags": ["top100", "busqueda"],
        }
        (case_dir / "caso.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (case_dir / "mensaje.txt").write_text(mensaje + "\n", encoding="utf-8")


async def main(*, apply: bool) -> None:
    filas_csv = leer_cruce()
    conn = await connect()
    try:
        codigos = [r["codigo"] for r in filas_csv if r.get("existe") == "True"]
        alias_rows = await conn.fetch(
            f"""
            SELECT product_code, alias_norm
            FROM {SCHEMA}.productos_aliases
            WHERE product_code = ANY($1::text[])
            """,
            codigos,
        )
        por_codigo: dict[str, list[str]] = {}
        for row in alias_rows:
            por_codigo.setdefault(row["product_code"], []).append(row["alias_norm"] or "")

        propuesta: list[dict[str, str]] = []
        for src in filas_csv:
            codigo = src["codigo"]
            if src.get("existe") != "True":
                propuesta.append({
                    "orden": src["orden"],
                    "codigo": codigo,
                    "frase": "",
                    "nombre": src.get("producto_excel") or "",
                    "accion_alias": "no-existe",
                    "accion_descripcion": "no-existe",
                    "motivo": "No está en GEV ni en productos",
                })
                continue
            nombre = src.get("nombre") or ""
            descripcion = src.get("descripcion") or ""
            frase_q = frase(codigo, nombre)
            normas = por_codigo.get(codigo, [])
            faltan = [t for t in tokens(frase_q) if not cubre(t, nombre, normas)]
            en_texto = fold(nombre + " " + descripcion)
            faltan_texto = [t for t in tokens(frase_q) if t not in en_texto]
            norma = alias_norm(frase_q)
            ya = norma in normas
            accion_alias = "alta" if faltan and norma and not ya else "ya-cubre"
            accion_desc = "anteponer" if faltan_texto else "ya-cubre"
            nueva = descripcion
            if accion_desc == "anteponer":
                titulo = frase_q[:1].upper() + frase_q[1:]
                nueva = f"{titulo}. {descripcion}".strip()
            propuesta.append({
                "orden": src["orden"],
                "codigo": codigo,
                "frase": frase_q,
                "nombre": nombre,
                "accion_alias": accion_alias,
                "alias_raw": frase_q if accion_alias == "alta" else "",
                "accion_descripcion": accion_desc,
                "descripcion_nueva": nueva if accion_desc == "anteponer" else "",
                "motivo": " ".join(faltan) if faltan else "",
            })

        with PROPUESTA.open("w", newline="", encoding="utf-8") as f:
            fields = [
                "orden", "codigo", "frase", "nombre", "accion_alias", "alias_raw",
                "accion_descripcion", "descripcion_nueva", "motivo",
            ]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(propuesta)
        altas = [p for p in propuesta if p["accion_alias"] == "alta"]
        descs = [p for p in propuesta if p["accion_descripcion"] == "anteponer"]
        print(f"[*] propuesta {PROPUESTA.name}: alias {len(altas)}, descripciones {len(descs)}")

        escribir_casos(propuesta)
        print(f"[*] casos E2E en {CASOS}")

        if not apply:
            print("[*] sin --apply, no se escribió la base")
            return

        for p in altas:
            await conn.execute(
                f"""
                INSERT INTO {SCHEMA}.productos_aliases
                  (alias_norm, alias_raw, product_code, weight, created_at, updated_at)
                VALUES ($1, $2, $3, 1, now(), now())
                ON CONFLICT (alias_norm, product_code) DO NOTHING
                """,
                alias_norm(p["alias_raw"]),
                p["alias_raw"],
                p["codigo"],
            )
        for p in descs:
            await conn.execute(
                f"""
                UPDATE {SCHEMA}.productos
                SET descripcion = $2, updated_at = now()
                WHERE product_code = $1
                """,
                p["codigo"],
                p["descripcion_nueva"],
            )
        print(f"[*] aplicados alias {len(altas)}, descripciones {len(descs)}")
        print("VECTORIZAR " + ",".join(p["codigo"] for p in descs))
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
