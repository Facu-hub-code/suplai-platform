#!/usr/bin/env python3
"""Fase 1.1 cipres: taxonomía 2 niveles desde CSV (sin IA)."""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

SCHEMA = "cipres"
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
PRODUCTS_CSV = OUT / "phase-01-productos.csv"
OUTPUT_JSON = OUT / "phase-01-1-propuesta-categorias.json"
APPLY_CHUNK = 500

load_dotenv(ROOT.parent / "backend-supabase" / ".env")
load_dotenv(ROOT / ".env")
BACKEND = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")


def build_proposal() -> list[dict]:
    rows = list(csv.DictReader(PRODUCTS_CSV.open(encoding="utf-8")))
    products: list[dict] = []
    skipped = 0
    for row in rows:
        code = (row.get("product_code") or "").strip()
        nombre = (row.get("nombre") or "").strip()
        c1 = (row.get("categoria_1") or "").strip()
        c2 = (row.get("categoria_2") or "").strip()
        if not code or not c1:
            skipped += 1
            continue
        products.append(
            {
                "product_code": code,
                "nombre": nombre,
                "tags": {"1": c1, "2": c2 or c1, "3": "", "4": ""},
            }
        )
    if skipped:
        print(f"[WARN] Omitidos {skipped} productos sin categoria_1")
    pairs = Counter((p["tags"]["1"], p["tags"]["2"]) for p in products)
    print(f"[+] Propuesta CSV: {len(products)} productos | {len(pairs)} pares nivel1+nivel2")
    print(f"    Nivel 1 únicos: {len({p['tags']['1'] for p in products})}")
    return products


def apply_tags(products: list[dict]) -> None:
    url = f"{BACKEND}/{SCHEMA}/tags/apply-proposed-taxonomy"
    for i in range(0, len(products), APPLY_CHUNK):
        chunk = products[i : i + APPLY_CHUNK]
        print(f"  … apply tags {min(i + APPLY_CHUNK, len(products))}/{len(products)}")
        resp = requests.post(url, json={"products": chunk}, timeout=600)
        if resp.status_code != 200:
            raise RuntimeError(f"apply HTTP {resp.status_code}: {resp.text[:400]}")


def populate_categorias() -> dict | None:
    url = f"{BACKEND}/{SCHEMA}/categorias/populate-from-tags"
    resp = requests.post(url, timeout=600)
    if resp.status_code == 200:
        return resp.json()
    # En prod, apply-proposed-taxonomy ya sincroniza categorias; populate puede devolver 500 si ya está hecho.
    print(f"[WARN] populate-from-tags HTTP {resp.status_code}: {resp.text[:200]}")
    return None


def main() -> int:
    if not PRODUCTS_CSV.exists():
        print(f"[FAIL] Falta {PRODUCTS_CSV}", file=sys.stderr)
        return 1

    print(f"[*] Fase 1.1 CSV 2 niveles — schema={SCHEMA}")
    products = build_proposal()
    if not products:
        print("[FAIL] Propuesta vacía", file=sys.stderr)
        return 1

    payload = {"schema": SCHEMA, "products": products, "source": "csv_2_levels"}
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[+] Guardado {OUTPUT_JSON}")

    print("[*] Aplicando tags...")
    t0 = time.time()
    apply_tags(products)
    print(f"[+] Tags aplicados en {time.time()-t0:.1f}s")

    print("[*] Sincronizando categorias...")
    result = populate_categorias()
    print(f"[+] populate-from-tags: {result}")

    print("OK Fase 1.1 cipres (CSV 2 niveles) completada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
