#!/usr/bin/env python3
"""Aplica la vista previa aprobada de enriquecimiento para abmauri."""
from __future__ import annotations

import asyncio
import csv
import os
import sys
import unicodedata
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "abmauri"
EXPECTED = 182
BATCH = 80
HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
PLATFORM_ROOT = HERE.parents[3]
PREVIEW = ROOT / "outputs" / "vista_previa_enriquecimiento.csv"


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def normalize_alias(value: str) -> str:
    flat = unicodedata.normalize("NFKD", value.lower().strip())
    ascii_text = flat.encode("ascii", "ignore").decode("ascii")
    return "".join(character for character in ascii_text if character.isalnum())


def load_env() -> None:
    for path in (
        Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
        PLATFORM_ROOT / ".env",
    ):
        if path.exists():
            load_dotenv(path, override=False)
    url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or ""
    if url:
        pooler_url = force_pooler(url)
        os.environ["SUPABASE_DB_URL_POOLER"] = pooler_url
        os.environ["SUPABASE_DB_URL"] = pooler_url


load_env()


async def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    with PREVIEW.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if (row.get("accion") or "ACTUALIZAR").upper() in {"ACTUALIZAR", "UPDATE"}
        ]
    if len(rows) != EXPECTED:
        print(f"[FAIL] Se esperaban {EXPECTED} filas aprobadas y hay {len(rows)}", file=sys.stderr)
        return 1

    descriptions: list[tuple[str, str]] = []
    aliases: set[tuple[str, str, str, float]] = set()
    for row in rows:
        code = row["codigo_producto"].strip()
        description = row["descripcion_mejorada"].strip()
        if not code or not description:
            print(f"[FAIL] Fila incompleta para {code}", file=sys.stderr)
            return 1
        descriptions.append((description, code))
        for raw in row["alias_propuestos"].split("|"):
            raw = raw.strip()
            norm = normalize_alias(raw)
            if raw and norm:
                aliases.add((norm, raw, code, 1.0))

    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        existing = await conn.fetchval(
            f"""
            SELECT COUNT(*) FROM {SCHEMA}.productos
            WHERE product_code = ANY($1::text[])
            """,
            [code for _, code in descriptions],
        )
        if existing != EXPECTED:
            print(f"[FAIL] Solo existen {existing}/{EXPECTED} productos", file=sys.stderr)
            return 1

        aliases_before = await conn.fetchval(
            f"SELECT COUNT(*) FROM {SCHEMA}.productos_aliases"
        )
        alias_rows = sorted(aliases)
        async with conn.transaction():
            for index in range(0, len(descriptions), BATCH):
                await conn.executemany(
                    f"""
                    UPDATE {SCHEMA}.productos
                    SET descripcion=$1, updated_at=now()
                    WHERE product_code=$2
                    """,
                    descriptions[index : index + BATCH],
                )
            for index in range(0, len(alias_rows), BATCH):
                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.productos_aliases (
                        alias_norm, alias_raw, product_code, weight,
                        created_at, updated_at
                    )
                    VALUES ($1,$2,$3,$4,now(),now())
                    ON CONFLICT (alias_norm, product_code) DO UPDATE
                    SET alias_raw=EXCLUDED.alias_raw,
                        weight=EXCLUDED.weight,
                        updated_at=now()
                    """,
                    alias_rows[index : index + BATCH],
                )

        loaded = {
            str(row["product_code"]): str(row["descripcion"])
            for row in await conn.fetch(
                f"""
                SELECT product_code, descripcion FROM {SCHEMA}.productos
                WHERE product_code = ANY($1::text[])
                """,
                [code for _, code in descriptions],
            )
        }
        expected = {code: description for description, code in descriptions}
        mismatches = [code for code, description in expected.items() if loaded.get(code) != description]
        aliases_after = await conn.fetchval(
            f"SELECT COUNT(*) FROM {SCHEMA}.productos_aliases"
        )
        products_with_aliases = await conn.fetchval(
            f"SELECT COUNT(DISTINCT product_code) FROM {SCHEMA}.productos_aliases"
        )
        print(
            f"[VERIFY] descripciones={len(loaded)} aliases_before={aliases_before} "
            f"aliases_after={aliases_after} productos_con_alias={products_with_aliases}"
        )
        if mismatches or len(loaded) != EXPECTED or products_with_aliases != EXPECTED:
            print(
                f"[FAIL] Verificación inconsistente: mismatches={mismatches[:10]}",
                file=sys.stderr,
            )
            return 1
    finally:
        await conn.close()

    backend = os.getenv(
        "BACKEND_URL", "https://web-production-f544f.up.railway.app"
    ).rstrip("/")
    codes = [code for _, code in descriptions]
    try:
        response = requests.post(
            f"{backend}/{SCHEMA}/productos/vectorize",
            json=codes,
            timeout=120,
        )
        print(f"[VECTORIZE] HTTP {response.status_code}: {response.text[:400]}")
        if response.status_code != 200:
            print("[WARN] Enriquecimiento aplicado; vectorización no confirmada")
    except requests.RequestException as error:
        print(f"[WARN] Enriquecimiento aplicado; vectorización falló: {error}")

    print(f"[SUCCESS] Enriquecimiento aplicado a {EXPECTED} productos")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
