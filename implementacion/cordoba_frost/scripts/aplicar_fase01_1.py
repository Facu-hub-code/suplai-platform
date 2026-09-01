#!/usr/bin/env python3
"""Fase 1.1 cordoba_frost: propone taxonomía 4 niveles. Aplicar solo con --apply."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "cordoba_frost"
ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT.parent / "backend-supabase"
OUT = Path(__file__).resolve().parents[1] / "outputs"
OUTPUT_JSON = OUT / "phase-01-1-propuesta-categorias.json"
CHECKPOINT_JSON = OUT / "phase-01-1-propuesta-categorias.partial.json"
CHUNK = 80
APPLY_CHUNK = 80
MAX_RETRIES = 4
SKIP_CODES = {"ENVIO-DOM"}

load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(ROOT / ".env")

BACKEND = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")

FROST_TAXONOMY_PROMPT = """Rol: Arquitecto de Información para distribución B2B de panadería congelada, helados e insumos de heladería (Córdoba Frost, Córdoba, Argentina).
Clasificá cada producto en 4 niveles.

Nivel 1 (Departamento) — usá SOLO estos valores:
  Panificados, Helados, Insumos, Congelados, Sin TACC, Combos

Nivel 2 (Categoría): familia comercial.
  Panificados: Panadería, Bizcochería, Pastelería, Medialunas y facturas.
  Helados: Palitos de crema, Palitos de agua, Helados en vaso, Baldes 10 L, Baldes chicos, Postres helados, Tortas heladas, Productos AFA.
  Insumos: Descartables, Comestibles, Salsas, Equipamiento.
  Congelados: Rebozados, Medallones, Papas, Frutas, Pizzas y empanadas, Hamburguesas.
  Sin TACC: Panificados sin TACC, Pizzas sin TACC, Otros sin TACC.
  Combos: Combos de panadería, Combos de helados, Combos de hamburguesas.

Nivel 3 (Subcategoría): clase más específica (ej. Chipá, Criollo hojaldre, Palito bombón, Helado en vaso 330 cc, Papa bastón, Pizza muzzarella).

Nivel 4 (Tipo de producto): genérico, SIN marca, SIN peso y SIN tamaño (ej. Baguettín, Medialuna, Palito de crema, Balde de helado, Cono pasta, Salsa de chocolate).

Reglas:
- Combos (nombre o pack armado de varios productos) → Combos.
- Envases, vasos pasta, conos, cucuruchos, servilletas, salsas, rocklets, maní, obleas → Insumos.
- Palitos, vasos, baldes, postres, tortas heladas, AFA → Helados.
- Rebozados, milanesas, medallones, papas, frutas, pizzas, hamburguesas, bifes → Congelados (salvo Sin TACC).
- Productos marcados SIN TACC / sin gluten → Sin TACC.
- Evitá Varios/General si hay clasificación clara.
Respondé SOLO un JSON array con objetos {"product_code","tags":{"1","2","3","4"}}.
"""


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/").replace(":5432@", ":6543@")


async def load_products() -> list[dict[str, str]]:
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("Falta SUPABASE_DB_URL")
    db_url = force_pooler(db_url)
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        rows = await conn.fetch(
            f"""
            SELECT product_code, nombre
            FROM {SCHEMA}.productos
            WHERE en_catalogo IS TRUE
              AND TRIM(COALESCE(nombre, '')) <> ''
              AND product_code <> ALL($1::text[])
            ORDER BY product_code
            """,
            list(SKIP_CODES),
        )
        return [{"product_code": r["product_code"], "nombre": r["nombre"]} for r in rows]
    finally:
        await conn.close()


def load_checkpoint() -> dict[str, dict]:
    if not CHECKPOINT_JSON.exists():
        return {}
    data = json.loads(CHECKPOINT_JSON.read_text(encoding="utf-8"))
    products = data.get("products") or []
    return {p["product_code"]: p for p in products if p.get("product_code")}


def save_checkpoint(products_by_code: dict[str, dict]) -> None:
    payload = {"schema": SCHEMA, "products": list(products_by_code.values())}
    CHECKPOINT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


async def propose_chunk(chunk: list[dict[str, str]]) -> list[dict]:
    sys.path.insert(0, str(BACKEND_ROOT))
    from utils.taxonomy_proposal import propose_taxonomy  # type: ignore

    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await propose_taxonomy(chunk, FROST_TAXONOMY_PROMPT, batch_size=40)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = attempt * 5
            print(f"[WARN] chunk falló intento {attempt}/{MAX_RETRIES}: {exc}. Reintento en {wait}s", flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError(f"chunk agotó reintentos: {last_err}") from last_err


def _merge_proposed(by_code: dict[str, dict], part: list[dict], source: list[dict[str, str]]) -> None:
    names = {p["product_code"]: p["nombre"] for p in source}
    for item in part:
        code = item.get("product_code")
        if not code:
            continue
        tags = item.get("tags") or {}
        by_code[code] = {
            "product_code": code,
            "nombre": item.get("nombre") or names.get(code, ""),
            "tags": {
                "1": str(tags.get("1") or "").strip(),
                "2": str(tags.get("2") or "").strip(),
                "3": str(tags.get("3") or "").strip(),
                "4": str(tags.get("4") or "").strip(),
            },
        }


async def propose_local(products: list[dict[str, str]]) -> list[dict]:
    by_code = load_checkpoint()
    if by_code:
        print(f"[*] Reanudando checkpoint con {len(by_code)} productos ya propuestos", flush=True)

    total = len(products)
    for i in range(0, total, CHUNK):
        chunk = products[i : i + CHUNK]
        pending = [p for p in chunk if p["product_code"] not in by_code]
        if not pending:
            print(f"  … propuesta {min(i + CHUNK, total)}/{total} (skip)", flush=True)
            continue
        print(f"  … propuesta {min(i + CHUNK, total)}/{total} (+{len(pending)})", flush=True)
        part = await propose_chunk(pending)
        _merge_proposed(by_code, part, pending)
        missing = [p for p in pending if p["product_code"] not in by_code]
        if missing:
            print(f"  … reintento {len(missing)} SKUs sin parsear", flush=True)
            part2 = await propose_chunk(missing)
            _merge_proposed(by_code, part2, missing)
        save_checkpoint(by_code)

    return [by_code[p["product_code"]] for p in products if p["product_code"] in by_code]


def print_summary(proposed: list[dict]) -> None:
    l1 = Counter((p.get("tags") or {}).get("1") or "(vacío)" for p in proposed)
    print("[*] Nivel 1:")
    for name, n in l1.most_common():
        print(f"    {n:4d}  {name}")
    print("[*] Muestra:")
    for p in proposed[:8]:
        t = p.get("tags") or {}
        print(f"    {p['product_code']}: {t.get('1')} > {t.get('2')} > {t.get('3')} > {t.get('4')}")


def apply_tags(products: list[dict]) -> None:
    url = f"{BACKEND}/{SCHEMA}/tags/apply-proposed-taxonomy"
    for i in range(0, len(products), APPLY_CHUNK):
        chunk = products[i : i + APPLY_CHUNK]
        print(f"  … apply tags {min(i + APPLY_CHUNK, len(products))}/{len(products)}")
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(url, json={"products": chunk}, timeout=600)
                if resp.status_code == 200:
                    print(f"      OK {resp.text[:180]}", flush=True)
                    break
                last_err = RuntimeError(f"apply HTTP {resp.status_code}: {resp.text[:400]}")
            except requests.RequestException as exc:
                last_err = exc
            time.sleep(attempt * 3)
        else:
            raise RuntimeError(f"apply chunk falló: {last_err}") from last_err


def populate_categorias() -> None:
    url = f"{BACKEND}/{SCHEMA}/categorias/populate-from-tags"
    resp = requests.post(url, timeout=600)
    if resp.status_code == 200:
        print(f"[+] populate-from-tags: {resp.text[:400]}", flush=True)
        return
    print(f"[WARN] populate-from-tags HTTP {resp.status_code}: {resp.text[:500]}", flush=True)
    if resp.status_code != 500:
        raise RuntimeError(f"populate HTTP {resp.status_code}: {resp.text[:500]}")


async def rebuild_rag() -> None:
    sys.path.insert(0, str(BACKEND_ROOT))
    from utils.vectorizacion_categorias import rebuild_categoria_documents  # type: ignore

    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("Falta SUPABASE_DB_URL")
    db_url = force_pooler(db_url)
    print("[*] Reconstruyendo RAG de categorías...", flush=True)
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        result = await rebuild_categoria_documents(SCHEMA, conn, batch_size=20)
    finally:
        await conn.close()
    print(f"[+] RAG: {result}", flush=True)


async def populate_local() -> None:
    """Copia tags → categorias reusando (name, parent) para no chocar con Combos/Helados viejos."""
    db_url = force_pooler(os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "")
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        tags = await conn.fetch(
            f"SELECT id, name, parent_id, description FROM {SCHEMA}.tags ORDER BY id"
        )
        children: dict[int | None, list] = {}
        for t in tags:
            children.setdefault(t["parent_id"], []).append(t)

        tag_to_cat: dict[int, int] = {}
        created = 0
        reused = 0

        queue = list(children.get(None, []))
        i = 0
        while i < len(queue):
            t = queue[i]
            parent_cat = tag_to_cat.get(t["parent_id"]) if t["parent_id"] else None
            existing = await conn.fetchrow(
                f"""
                SELECT id FROM {SCHEMA}.categorias
                WHERE name = $1 AND parent_id IS NOT DISTINCT FROM $2
                """,
                t["name"],
                parent_cat,
            )
            if existing:
                cat_id = int(existing["id"])
                reused += 1
            else:
                id_taken = await conn.fetchval(
                    f"SELECT 1 FROM {SCHEMA}.categorias WHERE id = $1", t["id"]
                )
                if id_taken:
                    cat_id = int(
                        await conn.fetchval(
                            f"""
                            INSERT INTO {SCHEMA}.categorias
                              (name, description, parent_id, sort_order, created_at, updated_at)
                            VALUES ($1, $2, $3, 0, now(), now())
                            RETURNING id
                            """,
                            t["name"],
                            t["description"],
                            parent_cat,
                        )
                    )
                else:
                    await conn.execute(
                        f"""
                        INSERT INTO {SCHEMA}.categorias
                          (id, name, description, parent_id, sort_order, created_at, updated_at)
                        OVERRIDING SYSTEM VALUE
                        VALUES ($1, $2, $3, $4, 0, now(), now())
                        """,
                        t["id"],
                        t["name"],
                        t["description"],
                        parent_cat,
                    )
                    cat_id = int(t["id"])
                created += 1
            tag_to_cat[int(t["id"])] = cat_id
            queue.extend(children.get(t["id"], []))
            i += 1

        pairs = await conn.fetch(
            f"SELECT product_code, tag_id FROM {SCHEMA}.product_tags"
        )
        rows = []
        for r in pairs:
            cat_id = tag_to_cat.get(int(r["tag_id"]))
            if cat_id:
                rows.append((r["product_code"], cat_id))
        inserted_pc = 0
        for j in range(0, len(rows), 80):
            chunk = rows[j : j + 80]
            res = await conn.executemany(
                f"""
                INSERT INTO {SCHEMA}.product_categories (product_code, categoria_id)
                VALUES ($1, $2)
                ON CONFLICT (product_code, categoria_id) DO NOTHING
                """,
                chunk,
            )
            inserted_pc += len(chunk)

        mapped_ids = list(set(tag_to_cat.values()))
        deleted = await conn.execute(
            f"""
            DELETE FROM {SCHEMA}.product_categories pc
            WHERE pc.product_code IN (SELECT DISTINCT product_code FROM {SCHEMA}.product_tags)
              AND NOT (pc.categoria_id = ANY($1::int[]))
            """,
            mapped_ids,
        )
        await conn.execute(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{SCHEMA}.categorias', 'id'),
                COALESCE((SELECT MAX(id) FROM {SCHEMA}.categorias), 1) + 1000
            )
            """
        )
        print(
            f"[+] categorias merge created={created} reused={reused} "
            f"pc_rows={inserted_pc} stale={deleted}",
            flush=True,
        )
        result = await rebuild_categoria_documents_safe(conn)
        print(f"[+] RAG: {result}", flush=True)
    finally:
        await conn.close()


async def rebuild_categoria_documents_safe(conn):
    sys.path.insert(0, str(BACKEND_ROOT))
    from utils.vectorizacion_categorias import rebuild_categoria_documents  # type: ignore

    return await rebuild_categoria_documents(SCHEMA, conn, batch_size=20)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplica tags + categorias (solo tras confirmar)")
    parser.add_argument(
        "--merge-categorias",
        action="store_true",
        help="Solo copia tags→categorias (tags ya aplicados)",
    )
    args = parser.parse_args()

    print(f"[*] schema_name confirmado: {SCHEMA}")

    if args.merge_categorias:
        asyncio.run(populate_local())
        print(f"OK Fase 1.1 {SCHEMA} categorias merge")
        return 0

    products = asyncio.run(load_products())
    print(f"[*] Fase 1.1 — schema={SCHEMA} | productos en catálogo={len(products)}")

    if args.apply:
        if not OUTPUT_JSON.exists():
            print(f"[FAIL] Falta {OUTPUT_JSON}", file=sys.stderr)
            return 1
        data = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
        proposed = data.get("products") or []
        print(f"[*] Aplicando propuesta guardada: {len(proposed)} productos")
        apply_tags(proposed)
        try:
            populate_categorias()
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] populate HTTP falló ({exc}); copio tags→categorias en local", flush=True)
        asyncio.run(populate_local())
        if CHECKPOINT_JSON.exists():
            CHECKPOINT_JSON.unlink()
        print(f"OK Fase 1.1 {SCHEMA} aplicada")
        return 0

    print("[*] Generando propuesta IA en lotes (sin escribir en BD)...")
    proposed = asyncio.run(propose_local(products))
    print(f"[+] Propuesta generada: {len(proposed)} / {len(products)}")
    if len(proposed) < len(products):
        print(f"[FAIL] Faltan {len(products) - len(proposed)} productos", file=sys.stderr)
        return 1

    payload = {"schema": SCHEMA, "products": proposed}
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[+] Guardado {OUTPUT_JSON}")
    print_summary(proposed)
    print("[*] No se aplicó a BD. Esperando confirmación del implementador.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
