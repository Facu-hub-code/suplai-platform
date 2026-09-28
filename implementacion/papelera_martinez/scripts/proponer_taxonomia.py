#!/usr/bin/env python3
"""Propone taxonomía 4 niveles para papelera_martinez.

Intenta POST /categorias/propose-taxonomy (SPEC-060). Si trunca o falla,
completa con la jerarquía del PDF (familia / subgrupo / tipo / variante).
No aplica: solo escribe outputs/phase-01-1-propuesta-categorias.json.
"""
from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

import requests

SCHEMA = "papelera_martinez"
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ROOT / "outputs" / "phase-01-productos.csv"
OUTPUT = ROOT / "outputs" / "phase-01-1-propuesta-categorias.json"
BACKEND = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")


def title_es(value: str) -> str:
    value = " ".join((value or "").split()).strip()
    if not value:
        return ""
    small = {"de", "del", "la", "las", "el", "los", "y", "o", "para", "en", "con", "sin"}
    parts = re.split(r"(\s+|/)", value.lower())
    out = []
    first = True
    for part in parts:
        if part in {" ", "/", ""}:
            out.append(part)
            continue
        if not first and part in small:
            out.append(part)
        else:
            out.append(part[:1].upper() + part[1:])
        first = False
    return "".join(out)


def fold(value: str) -> str:
    n = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower().strip()


FAMILIA_RULES = [
    ("cartel", "Cartelería"),
    ("film", "Embalaje"),
    ("resinite", "Embalaje"),
    ("stretch", "Embalaje"),
    ("polipropileno", "Polipropileno"),
    ("camiseta", "Polietileno"),
    ("arranque", "Polietileno"),
    ("caja pizza", "Cajas de cartón"),
    ("caja torta", "Cajas de cartón"),
    ("maletin", "Cajas de cartón"),
    ("bombonera", "Cajas de cartón"),
    ("clamshell", "Descartable"),
    ("vaso", "Descartable"),
    ("plato", "Descartable"),
    ("bandeja", "Descartable"),
    ("badeja", "Descartable"),
    ("cuchar", "Descartable"),
    ("servilleta", "Descartable"),
    ("sorbete", "Descartable"),
    ("guante", "Higiene institucional"),
    ("pañuelo", "Higiene institucional"),
    ("papel hig", "Higiene institucional"),
    ("dispenser", "Higiene institucional"),
    ("rollo cocina", "Higiene institucional"),
    ("bobina", "Papel"),
    ("resma", "Librería"),
    ("boligrafo", "Librería"),
    ("abrochadora", "Oficina"),
    ("contadora", "Oficina"),
    ("tinta", "Librería"),
    ("cartucho", "Librería"),
    ("cucurucho", "Comestible"),
    ("barquillo", "Comestible"),
    ("cinta decorativa", "Regalería"),
    ("moño", "Regalería"),
    ("fajas de carton", "Descartable"),
    ("escarbadiente", "Descartable"),
    ("expandido", "Descartable"),
    ("espandido", "Descartable"),
    ("oble", "Comestible"),
]

TIPO_RULES = [
    ("papel higienico", "Papel higiénico"),
    ("servilleta", "Servilletas"),
    ("empanada", "Cajas de empanadas"),
    ("pizza", "Cajas de pizza"),
    ("cupcake", "Cajas de cupcakes"),
    ("torta", "Cajas de torta"),
    ("budin", "Cajas de budín"),
    ("hamburguesa", "Cajas de hamburguesa"),
    ("vaso", "Vasos"),
    ("plato", "Platos"),
    ("bandeja", "Bandejas"),
    ("bolsa", "Bolsas"),
    ("resma", "Resmas"),
    ("resaltador", "Resaltadores"),
    ("cartel", "Carteles"),
    ("cono", "Conos"),
    ("salsa", "Salsas"),
    ("film", "Film"),
    ("aluminio", "Aluminio"),
    ("cubierto", "Cubiertos"),
    ("moño", "Moños"),
    ("cinta", "Cintas"),
    ("globo", "Globos"),
    ("vela", "Velas"),
    ("molde", "Moldes"),
    ("pote", "Potes"),
    ("tapa", "Tapas"),
    ("bobina", "Bobinas"),
    ("selladora", "Máquinas"),
    ("guante", "Guantes"),
    ("blonda", "Blondas"),
    ("stretch", "Stretch"),
    ("dispenser", "Dispensers"),
    ("carpeta", "Carpetas"),
    ("boligrafo", "Bolígrafos"),
    ("calculadora", "Calculadoras"),
]


def tipo_from_nombre(nombre: str, fallback: str) -> str:
    n = fold(nombre)
    for needle, label in TIPO_RULES:
        if needle in n:
            return label
    return fallback or "Artículo"


def variante(nombre: str, tipo: str) -> str:
    n = fold(nombre)
    extras = []
    if "kraft" in n:
        extras.append("kraft")
    if "blanco" in n or "blanca" in n:
        extras.append("blanco")
    if "negro" in n or "negra" in n:
        extras.append("negro")
    if "visor" in n:
        extras.append("con visor")
    if "termic" in n:
        extras.append("térmico")
    if "microonda" in n or "micro " in n:
        extras.append("microondas")
    if re.search(r"x\s*\d+", n):
        m = re.search(r"x\s*(\d+)", n)
        if m and int(m.group(1)) > 1:
            extras.append(f"x{m.group(1)}")
    if extras:
        return title_es(f"{tipo} {' '.join(extras)}")
    return tipo


def familia_from_nombre(nombre: str, fallback: str) -> str:
    n = fold(nombre)
    for needle, label in FAMILIA_RULES:
        if needle in n:
            return label
    return fallback


CANON_L1 = {
    "cajas de carton": "Cajas de cartón",
    "carteleria": "Cartelería",
    "comestible": "Comestible",
    "cotillon": "Cotillón",
    "descartable": "Descartable",
    "embalaje": "Embalaje",
    "higiene institucional": "Higiene institucional",
    "libreria": "Librería",
    "oficina": "Oficina",
    "papel": "Papel",
    "polietileno": "Polietileno",
    "polipropileno": "Polipropileno",
    "regaleria": "Regalería",
}


def canon_l1(value: str) -> str:
    return CANON_L1.get(fold(value), title_es(value))


def from_csv() -> list[dict]:
    rows = list(csv.DictReader(PRODUCTS.open(encoding="utf-8")))
    products = []
    for row in rows:
        raw_fam = (row.get("categoria_1") or "").strip()
        if raw_fam and fold(raw_fam) != "general":
            familia = canon_l1(raw_fam)
        else:
            familia = canon_l1(familia_from_nombre(row["nombre"], "Descartable"))
        sub = title_es(row.get("categoria_2") or "")
        tipo = title_es(row.get("categoria_3") or "") or tipo_from_nombre(row["nombre"], sub or familia)
        if not sub:
            sub = tipo
        products.append(
            {
                "product_code": row["product_code"].strip(),
                "nombre": row["nombre"],
                "tags": {
                    "1": familia,
                    "2": sub,
                    "3": tipo,
                    "4": variante(row["nombre"], tipo),
                },
            }
        )
    return products


def try_backend(limit: int) -> dict | None:
    for path in (
        f"{BACKEND}/{SCHEMA}/categorias/propose-taxonomy",
        f"{BACKEND}/{SCHEMA}/tags/propose-taxonomy",
    ):
        print(f"[*] POST {path} limit={limit}")
        try:
            resp = requests.post(path, json={"limit": limit}, timeout=300)
        except Exception as exc:
            print(f"[WARN] {path}: {exc}")
            continue
        print(f"    HTTP {resp.status_code} bytes={len(resp.content)}")
        if resp.status_code != 200:
            print(f"    body={resp.text[:300]}")
            continue
        try:
            return {"url": path, "data": resp.json()}
        except Exception as exc:
            print(f"[WARN] JSON inválido: {exc}")
    return None


def tree_summary(products: list[dict]) -> list[str]:
    counts: Counter[tuple[str, str]] = Counter()
    for item in products:
        tags = item["tags"]
        counts[(tags["1"], tags["2"])] += 1
    lines = []
    current = None
    for (l1, l2), n in sorted(counts.items(), key=lambda kv: (kv[0][0], -kv[1])):
        if l1 != current:
            total = sum(v for (a, _), v in counts.items() if a == l1)
            lines.append(f"{l1} ({total})")
            current = l1
        lines.append(f"  · {l2}: {n}")
    return lines


def main() -> int:
    csv_products = from_csv()
    print(f"[*] CSV productos={len(csv_products)}")
    backend = None
    if os.getenv("PROPONER_TAXONOMIA_BACKEND", "0") == "1":
        backend = try_backend(len(csv_products))
    method = "jerarquia_pdf_lista_2"
    products = csv_products
    backend_meta = None
    if backend:
        proposed = backend["data"].get("products") or []
        backend_meta = {
            "url": backend["url"],
            "returned": len(proposed),
            "expected": len(csv_products),
            "status": "ok" if len(proposed) >= len(csv_products) else "truncated",
        }
        print(f"[*] backend returned={len(proposed)} expected={len(csv_products)}")
        if len(proposed) >= len(csv_products):
            products = proposed
            method = "backend_propose_taxonomy"
        else:
            print("[*] Backend incompleto: se usa la jerarquía del PDF para los 1325 SKUs.")
    payload = {
        "schema": SCHEMA,
        "generation_method": method,
        "backend_attempt": backend_meta,
        "products": products,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] {OUTPUT}")
    print("[*] Árbol propuesto:")
    for line in tree_summary(products):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
