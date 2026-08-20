#!/usr/bin/env python3
"""Fase 1.1 benavidez: propone taxonomía 4 niveles. Aplicar solo con --apply (tras OK del implementador)."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "benavidez"  # confirmado
ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT.parent / "backend-supabase"
OUT = Path(__file__).resolve().parents[1] / "outputs"
PRODUCTS_CSV = OUT / "phase-01-productos.csv"
OUTPUT_JSON = OUT / "phase-01-1-propuesta-categorias.json"
CHECKPOINT_JSON = OUT / "phase-01-1-propuesta-categorias.partial.json"
CHUNK = 400
APPLY_CHUNK = 400
MAX_RETRIES = 4

load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(ROOT / ".env")

BACKEND = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")

BENAVIDEZ_TAXONOMY_PROMPT = """Rol: Arquitecto de Información experto en insumos para carnicerías, frigoríficos y fábricas de chacinados (B2B).
Clasificá cada producto de Especias Benavidez en 4 niveles:

Nivel 1 (Departamento): gran rubro. Usá preferentemente:
  Especias y condimentos, Integrales para elaborados, Aditivos y antioxidantes,
  Tripas e hilos, Indumentaria de frigorífico, Cuchillos y cuchillas,
  Máquinas y equipamiento, Repuestos y accesorios, Fraccionados y bolsas,
  Legumbres y cereales, Frutos secos y semillas, Repostería.

Nivel 2 (Categoría): familia (ej. Especias molidas, Integrales de milanesa, Tripas naturales, Cuchillos profesionales, Espirales para moledora).

Nivel 3 (Subcategoría): clase más específica (ej. Ají molido, Integral hamburguesa 1 kg, Tripa MAD cerdo, Bandejas inox).

Nivel 4 (Tipo de Producto): genérico, SIN marca, SIN peso y SIN tamaño (ej. Ají molido, Integral de milanesas, Chimichurri, Cuchillo carnicero, Embutidora vertical).

Reglas: evitá "Varios/General" si hay clasificación clara. Nivel 4 sin marcas ni presentaciones.
Respondé SOLO un JSON array con objetos {"product_code","tags":{"1","2","3","4"}}.
"""


def load_products() -> list[dict[str, str]]:
    rows = list(csv.DictReader(PRODUCTS_CSV.open(encoding="utf-8")))
    out = []
    for r in rows:
        code = (r.get("product_code") or "").strip()
        name = (r.get("nombre") or "").strip()
        if code and name:
            out.append({"product_code": code, "nombre": name})
    return out


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
            return await propose_taxonomy(chunk, BENAVIDEZ_TAXONOMY_PROMPT, batch_size=40)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = attempt * 5
            print(f"[WARN] chunk falló intento {attempt}/{MAX_RETRIES}: {exc}. Reintento en {wait}s", flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError(f"chunk agotó reintentos: {last_err}") from last_err


async def propose_local(products: list[dict[str, str]]) -> list[dict]:
    by_code = load_checkpoint()
    if by_code:
        print(f"[*] Reanudando checkpoint con {len(by_code)} productos ya propuestos", flush=True)

    total = len(products)
    for i in range(0, total, CHUNK):
        chunk = products[i : i + CHUNK]
        pending = [p for p in chunk if p["product_code"] not in by_code]
        if not pending:
            print(f"  … propuesta local {min(i + CHUNK, total)}/{total} (skip, ya en checkpoint)", flush=True)
            continue
        print(f"  … propuesta local {min(i + CHUNK, total)}/{total} (+{len(pending)} nuevos)", flush=True)
        part = await propose_chunk(pending)
        _merge_proposed(by_code, part, pending)
        missing_in_chunk = [p for p in pending if p["product_code"] not in by_code]
        if missing_in_chunk:
            print(f"  … reintento {len(missing_in_chunk)} SKUs sin parsear en este lote", flush=True)
            part2 = await propose_chunk(missing_in_chunk)
            _merge_proposed(by_code, part2, missing_in_chunk)
        save_checkpoint(by_code)

    return [by_code[p["product_code"]] for p in products if p["product_code"] in by_code]


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


def print_summary(proposed: list[dict]) -> None:
    l1 = Counter((p.get("tags") or {}).get("1") or "(vacío)" for p in proposed)
    print("[*] Nivel 1:")
    for name, n in l1.most_common(15):
        print(f"    {n:4d}  {name}")
    print("[*] Muestra:")
    for p in proposed[:6]:
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
    # El endpoint escribe antes de armar el JSON; un 500 por `categoria_ids`
    # (bug conocido) no implica rollback. Verificamos conteos después.
    if resp.status_code == 200:
        print(f"[+] populate-from-tags: {resp.text[:400]}", flush=True)
        return
    print(
        f"[WARN] populate-from-tags HTTP {resp.status_code}: {resp.text[:500]}",
        flush=True,
    )
    if resp.status_code != 500:
        raise RuntimeError(f"populate HTTP {resp.status_code}: {resp.text[:500]}")


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


async def rebuild_rag() -> None:
    sys.path.insert(0, str(BACKEND_ROOT))
    from utils.vectorizacion_categorias import rebuild_categoria_documents  # type: ignore

    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("Falta SUPABASE_DB_URL_POOLER / SUPABASE_DB_URL")
    db_url = force_pooler(db_url)
    print("[*] Reconstruyendo RAG de categorías (category_documents)...", flush=True)
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        result = await rebuild_categoria_documents(SCHEMA, conn, batch_size=20)
    finally:
        await conn.close()
    print(f"[+] RAG: {result}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplica tags + categorias (solo tras confirmar)")
    parser.add_argument("--rebuild-rag", action="store_true", help="Reconstruye category_documents")
    args = parser.parse_args()

    print(f"[*] schema_name confirmado: {SCHEMA}")
    products = load_products()
    print(f"[*] Fase 1.1 — schema={SCHEMA} | productos CSV={len(products)}")

    if args.rebuild_rag:
        asyncio.run(rebuild_rag())
        return 0

    if args.apply:
        if not OUTPUT_JSON.exists():
            print(f"[FAIL] Falta {OUTPUT_JSON}", file=sys.stderr)
            return 1
        data = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
        proposed = data.get("products") or []
        print(f"[*] Aplicando propuesta guardada: {len(proposed)} productos")
        apply_tags(proposed)
        populate_categorias()
        asyncio.run(rebuild_rag())
        if CHECKPOINT_JSON.exists():
            CHECKPOINT_JSON.unlink()
        print(f"OK Fase 1.1 {SCHEMA} aplicada")
        return 0

    print("[*] Generando propuesta IA en lotes locales (sin escribir en BD)...")
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
