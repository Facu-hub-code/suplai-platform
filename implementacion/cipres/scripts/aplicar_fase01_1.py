#!/usr/bin/env python3
"""Fase 1.1 cipres: propone taxonomía local en lotes, aplica tags y sincroniza categorias."""
from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

SCHEMA = "cipres"
ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT.parent / "backend-supabase"
OUT = Path(__file__).resolve().parents[1] / "outputs"
PRODUCTS_CSV = OUT / "phase-01-productos.csv"
OUTPUT_JSON = OUT / "phase-01-1-propuesta-categorias.json"
CHECKPOINT_JSON = OUT / "phase-01-1-propuesta-categorias.partial.json"
CHUNK = 400
APPLY_CHUNK = 500
MAX_RETRIES = 4

load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(ROOT / ".env")

BACKEND = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")

CIPRES_TAXONOMY_PROMPT = """Rol: Arquitecto de Información experto en retail de limpieza, higiene, bazar y cuidado personal (B2B mayorista).
Clasificá cada producto en 4 niveles:

Nivel 1 (Departamento): gran rubro (ej. Limpieza del Hogar, Cuidado Personal, Aromatización, Piletas, Bazar, Insecticidas, Ferretería).
Nivel 2 (Categoría): familia (ej. Desinfectantes, Shampoo, Sahumerios, Químicos de pileta).
Nivel 3 (Subcategoría): clase específica (ej. Lavandinas, Acondicionador, Difusores).
Nivel 4 (Tipo de Producto): genérico, sin marca ni tamaño (ej. Lavandina líquida, Acondicionador capilar, Sahumerio).

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
            return await propose_taxonomy(chunk, CIPRES_TAXONOMY_PROMPT, batch_size=60)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = attempt * 5
            print(f"[WARN] chunk falló intento {attempt}/{MAX_RETRIES}: {exc}. Reintento en {wait}s")
            await asyncio.sleep(wait)
    raise RuntimeError(f"chunk agotó reintentos: {last_err}") from last_err


async def propose_local(products: list[dict[str, str]]) -> list[dict]:
    by_code = load_checkpoint()
    if by_code:
        print(f"[*] Reanudando checkpoint con {len(by_code)} productos ya propuestos")

    total = len(products)
    for i in range(0, total, CHUNK):
        chunk = products[i : i + CHUNK]
        pending = [p for p in chunk if p["product_code"] not in by_code]
        if not pending:
            print(f"  … propuesta local {min(i + CHUNK, total)}/{total} (skip, ya en checkpoint)")
            continue
        print(f"  … propuesta local {min(i + CHUNK, total)}/{total} (+{len(pending)} nuevos)")
        part = await propose_chunk(pending)
        for item in part:
            by_code[item["product_code"]] = item
        save_checkpoint(by_code)

    return [by_code[p["product_code"]] for p in products if p["product_code"] in by_code]


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
    if resp.status_code != 200:
        raise RuntimeError(f"populate HTTP {resp.status_code}: {resp.text[:400]}")
    print(f"[+] populate-from-tags: {resp.text[:300]}")


def main() -> int:
    if not PRODUCTS_CSV.exists():
        print(f"[FAIL] Falta {PRODUCTS_CSV}", file=sys.stderr)
        return 1

    products = load_products()
    print(f"[*] Fase 1.1 — schema={SCHEMA} | productos={len(products)}")

    print("[*] Generando propuesta IA en lotes locales...")
    proposed = asyncio.run(propose_local(products))
    print(f"[+] Propuesta generada: {len(proposed)} productos")

    if len(proposed) < len(products):
        missing = len(products) - len(proposed)
        print(f"[FAIL] Faltan {missing} productos sin taxonomía", file=sys.stderr)
        return 1

    payload = {"schema": SCHEMA, "products": proposed}
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[+] Guardado {OUTPUT_JSON}")

    print("[*] Aplicando tags en Supabase vía backend...")
    apply_tags(proposed)

    print("[*] Sincronizando categorias externas...")
    populate_categorias()

    if CHECKPOINT_JSON.exists():
        CHECKPOINT_JSON.unlink()

    print("OK Fase 1.1 cipres completada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
