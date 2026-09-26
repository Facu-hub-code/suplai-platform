#!/usr/bin/env python3
"""Aplica la taxonomía aprobada en categorias/product_categories de abmauri."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA = "abmauri"
EXPECTED_PRODUCTS = 182
BATCH = 80
HERE = Path(__file__).resolve()
TENANT_ROOT = HERE.parents[1]
PLATFORM_ROOT = HERE.parents[3]
BACKEND_ROOT = Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase")
PROPOSAL = TENANT_ROOT / "outputs" / "phase-01-1-propuesta-categorias.json"


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def load_env() -> None:
    for path in (BACKEND_ROOT / ".env", PLATFORM_ROOT / ".env"):
        if path.exists():
            load_dotenv(path, override=False)
    url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or ""
    if url:
        pooler_url = force_pooler(url)
        os.environ["SUPABASE_DB_URL_POOLER"] = pooler_url
        os.environ["SUPABASE_DB_URL"] = pooler_url


load_env()
sys.path.insert(0, str(BACKEND_ROOT))
from utils.vectorizacion_categorias import rebuild_categoria_documents  # noqa: E402


async def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    data = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    products = data.get("products") or []
    if data.get("schema") != SCHEMA or len(products) != EXPECTED_PRODUCTS:
        print(
            f"[FAIL] Propuesta inválida: schema={data.get('schema')} productos={len(products)}",
            file=sys.stderr,
        )
        return 1

    product_codes: list[str] = []
    for item in products:
        code = str(item.get("product_code") or "").strip()
        tags = item.get("tags") or {}
        if not code or set(tags) != {"1", "2", "3", "4"}:
            print(f"[FAIL] Producto/tags inválidos: {item}", file=sys.stderr)
            return 1
        product_codes.append(code)
    if len(set(product_codes)) != EXPECTED_PRODUCTS:
        print("[FAIL] La propuesta contiene códigos duplicados", file=sys.stderr)
        return 1

    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(force_pooler(db_url), statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        before = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.categorias) AS categorias,
              (SELECT COUNT(*) FROM {SCHEMA}.product_categories) AS asignaciones,
              (SELECT COUNT(*) FROM {SCHEMA}.category_documents) AS documentos
            """
        )
        if before["categorias"] or before["asignaciones"]:
            print(f"[FAIL] La taxonomía destino no está vacía: {dict(before)}", file=sys.stderr)
            return 1

        existing_rows = await conn.fetch(
            f"SELECT product_code FROM {SCHEMA}.productos WHERE product_code = ANY($1::text[])",
            product_codes,
        )
        existing = {str(row["product_code"]) for row in existing_rows}
        missing = sorted(set(product_codes) - existing)
        if missing:
            print(f"[FAIL] Faltan {len(missing)} productos en BD: {missing[:10]}", file=sys.stderr)
            return 1

        category_cache: dict[tuple[str, int | None], int] = {}
        assignments: set[tuple[str, int]] = set()
        async with conn.transaction():
            for item in products:
                parent_id: int | None = None
                for level in ("1", "2", "3", "4"):
                    name = " ".join(str(item["tags"][level]).split())
                    key = (name.casefold(), parent_id)
                    category_id = category_cache.get(key)
                    if category_id is None:
                        category_id = await conn.fetchval(
                            f"""
                            INSERT INTO {SCHEMA}.categorias (
                                name, description, parent_id, sort_order,
                                created_at, updated_at
                            )
                            VALUES ($1, $2, $3, 0, now(), now())
                            RETURNING id
                            """,
                            name,
                            f"Nivel {level} de la taxonomía comercial de AB Mauri.",
                            parent_id,
                        )
                        category_cache[key] = int(category_id)
                    assignments.add((str(item["product_code"]), int(category_id)))
                    parent_id = int(category_id)

            assignment_rows = sorted(assignments)
            for index in range(0, len(assignment_rows), BATCH):
                await conn.executemany(
                    f"""
                    INSERT INTO {SCHEMA}.product_categories (product_code, categoria_id)
                    VALUES ($1, $2)
                    ON CONFLICT (product_code, categoria_id) DO NOTHING
                    """,
                    assignment_rows[index : index + BATCH],
                )

        category_count = await conn.fetchval(f"SELECT COUNT(*) FROM {SCHEMA}.categorias")
        assignment_count = await conn.fetchval(
            f"SELECT COUNT(*) FROM {SCHEMA}.product_categories"
        )
        assigned_products = await conn.fetchval(
            f"SELECT COUNT(DISTINCT product_code) FROM {SCHEMA}.product_categories"
        )
        print(
            f"[VERIFY] categorias={category_count} asignaciones={assignment_count} "
            f"productos={assigned_products}"
        )
        if assigned_products != EXPECTED_PRODUCTS or assignment_count != EXPECTED_PRODUCTS * 4:
            print("[FAIL] Los conteos de taxonomía no coinciden", file=sys.stderr)
            return 1

        rag_result = await rebuild_categoria_documents(
            SCHEMA,
            conn,
            include_parent_id=True,
            batch_size=20,
        )
        print(f"[RAG] {rag_result}")
        print("[SUCCESS] Taxonomía aplicada en categorias/product_categories")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
