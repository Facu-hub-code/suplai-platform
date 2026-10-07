#!/usr/bin/env python3
"""Propone taxonomía 4 niveles para esekau (SPEC-060).

Intenta categorias/propose-taxonomy, fallback tags. Completa huecos
con LINEA/RUBRO del Excel para cubrir los 1215 SKUs.
"""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

import requests

SCHEMA = "esekau"
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ROOT / "outputs" / "phase-01-productos.csv"
OUTPUT = ROOT / "outputs" / "phase-01-1-propuesta-categorias.json"
BACKEND = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")

LINEA_L1 = {
    "PROCTER": "Cuidado personal",
    "DREAMCO": "Higiene y hogar",
    "CLOROX": "Higiene y hogar",
    "CEPAS": "Bebidas",
    "VARIOS": "Almacén",
}

RUBRO_FIX = {
    "CUIDADO DE CABELLO (HAIR CARE )": "Cuidado del cabello",
    "PAÑALES ( BABY CARE )": "Pañales",
    "CUIDADO BUCAL ( ORAL CARE )": "Cuidado bucal",
    "SISTEMAS (GROOMING)": "Afeitado",
    "DESECHABLES (GROOMING)": "Afeitado",
    "DESODORANTES ( APDOS )": "Desodorantes",
    "CUIDADO FEMENINO ( FEM CARE )": "Cuidado femenino",
    "SUAVIZANTE ( FABRIC ENHANCERS)": "Suavizantes",
    "PILAS ( BATTERIES )": "Pilas",
    "PILAS Y BATERIAS": "Pilas",
    "PREPARADOS DE AFEITAR ( GROOMING )": "Afeitado",
    "PAÑALES  -  TOALLAS FEMENINAS": "Cuidado femenino",
    "CUIDADADO DE LA ROPA": "Cuidado de la ropa",
    "LIMPIADORES LIQUIDOS": "Limpiadores",
    "LIMPIADORES ESPECIFICOS": "Limpiadores",
    "LIMPIADORES ESPECIFICOS DR": "Limpiadores",
    "LIMPIADORES LIQUIDOS": "Limpiadores",
    "JAB LIQUIDO": "Jabón líquido",
    "JAB TOCADOR TRIPACK": "Jabón de tocador",
    "JAB TOCADOR INDIVIDUAL": "Jabón de tocador",
    "JAB COMPACTO": "Jabón en barra",
    "JAB ESPUMA": "Jabón en espuma",
    "SHAMPOO Y ACONDICIONADOR": "Shampoo y acondicionador",
    "TRATAMIENTOS Y CREMAS DE PEINAR": "Tratamiento capilar",
    "LAVAVAJILLAS": "Lavavajillas",
    "POLVOS": "Detergente en polvo",
    "DETERGENTES ( HOME CARE )": "Detergentes",
    "SUAVIZANTES DR": "Suavizantes",
    "ALTO GRADO": "Destilados",
    "LEMON": "Ready to drink",
    "RTD (PRONTO + 1882)": "Ready to drink",
    "AMARGOS VALUE": "Amargos",
    "RESTO APERITIVOS": "Aperitivos",
    "BEBIDAS NO ALCOHOLICAS": "Gaseosas y jugos",
    "CHOCOLATE BONAFIDE": "Chocolate",
    "CHOCOLATE FELFORT": "Chocolate",
    "CHOCOLATE PASCUAS": "Chocolate",
    "CHOCOLATE IMPORTADORA": "Chocolate",
    "CAFE BONAFIDE": "Café",
    "YM": "Yerba mate",
    "YERBAS": "Yerba mate",
    "LATEX": "Preservativos",
    "LATEX M": "Preservativos",
    "CUIDADADO DE LA ROPA": "Cuidado de la ropa",
}

TIPO_RE = [
    (r"\bSH\b|SHAMPOO", "Shampoo"),
    (r"\bAC\b|ACONDICION", "Acondicionador"),
    (r"PAÑAL|PAMPERS|BABYDRY", "Pañal"),
    (r"TOALL", "Toalla femenina"),
    (r"PASTA|DENTAL|ORAL", "Pasta dental"),
    (r"CEPILLO", "Cepillo dental"),
    (r"SUAVIZ|DOWNY", "Suavizante"),
    (r"LAVAVAJ|MAGISTRAL", "Lavavajillas"),
    (r"LAVAND|AYUDIN|AYUDÍN", "Lavandina"),
    (r"DESINF|POETT", "Desinfectante"),
    (r"TERMA|AMARGO", "Amargo"),
    (r"FERNET", "Fernet"),
    (r"VINO", "Vino"),
    (r"RON|BACARDI", "Ron"),
    (r"VODKA", "Vodka"),
    (r"WHISKY|WHISKEY", "Whisky"),
    (r"GIN\b", "Gin"),
    (r"YERBA|TARAGU|MAÑANITA|YM ", "Yerba mate"),
    (r"CHOCOL|FERRERO|BONAFIDE|FELFORT", "Chocolate"),
    (r"PILA|DURACELL", "Pila"),
    (r"PRESERV|PRIME|LATEX", "Preservativo"),
    (r"AFEIT|PRESTO|VENUS|MACH3|FUSION", "Afeitado"),
    (r"PAÑAL", "Pañal"),
]


def title_es(value: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip())
    if not value:
        return "Otros"
    return value[:1].upper() + value[1:]


def clean_rubro(raw: str) -> str:
    raw = re.sub(r"\s+", " ", (raw or "").strip())
    up = raw.upper()
    if up in RUBRO_FIX:
        return RUBRO_FIX[up]
    raw = re.sub(r"\([^)]*\)", "", raw).strip(" -")
    return title_es(raw.lower()) or "Otros"


def tipo_from_name(nombre: str, rubro: str) -> str:
    up = (nombre or "").upper()
    for pat, label in TIPO_RE:
        if re.search(pat, up):
            return label
    return clean_rubro(rubro)


def local_tags(row: dict) -> dict:
    linea = (row.get("categoria_1") or "VARIOS").upper()
    rubro = row.get("categoria_2") or "OTROS"
    marca = row.get("categoria_3") or ""
    l1 = LINEA_L1.get(linea, "Almacén")
    l2 = clean_rubro(rubro)
    l3 = title_es(marca) if marca and marca.lower() not in {"plb"} else (
        "Plusbelle" if (marca or "").lower() == "plb" else l2
    )
    if l3.lower() == "plb":
        l3 = "Plusbelle"
    l4 = tipo_from_name(row.get("nombre") or "", rubro)
    return {"1": l1, "2": l2, "3": l3, "4": l4}


def fetch_backend(limit: int) -> tuple[list[dict], str]:
    payload = {"limit": limit}
    last_err = ""
    for path in (
        f"{BACKEND}/{SCHEMA}/categorias/propose-taxonomy",
        f"{BACKEND}/{SCHEMA}/tags/propose-taxonomy",
    ):
        print(f"[*] POST {path} limit={limit}")
        try:
            resp = requests.post(path, json=payload, timeout=600)
        except Exception as exc:
            last_err = str(exc)
            print(f"[WARN] {path}: {exc}")
            continue
        print(f"    HTTP {resp.status_code} bytes={len(resp.content)}")
        if resp.status_code != 200:
            last_err = resp.text[:300]
            continue
        data = resp.json()
        products = data.get("products") or []
        if products:
            return products, path
    print(f"[WARN] backend no devolvió propuesta: {last_err}")
    return [], ""


def normalize_item(item: dict) -> dict | None:
    code = str(item.get("product_code") or item.get("codigo") or "").strip()
    if not code:
        return None
    tags = item.get("tags") or item.get("categorias") or {}
    if isinstance(tags, dict):
        mapped = {
            "1": tags.get("1") or tags.get(1) or tags.get("nivel_1") or "",
            "2": tags.get("2") or tags.get(2) or tags.get("nivel_2") or "",
            "3": tags.get("3") or tags.get(3) or tags.get("nivel_3") or "",
            "4": tags.get("4") or tags.get(4) or tags.get("nivel_4") or "",
        }
    else:
        return None
    if not mapped["1"]:
        return None
    return {
        "product_code": code,
        "nombre": item.get("nombre") or "",
        "tags": mapped,
    }


def main() -> int:
    rows = list(csv.DictReader(PRODUCTS.open(encoding="utf-8")))
    print(f"[*] schema={SCHEMA} productos_csv={len(rows)}")
    proposed, source = fetch_backend(max(len(rows), 1300))
    by_code = {}
    for item in proposed:
        norm = normalize_item(item)
        if norm:
            by_code[norm["product_code"]] = norm

    filled = 0
    products = []
    for row in rows:
        code = row["product_code"].strip()
        if code in by_code and all(by_code[code]["tags"].values()):
            item = by_code[code]
            item["nombre"] = row["nombre"]
            products.append(item)
            continue
        tags = local_tags(row)
        products.append({"product_code": code, "nombre": row["nombre"], "tags": tags})
        filled += 1

    payload = {
        "schema": SCHEMA,
        "source": source or "local_linea_rubro",
        "products": products,
        "notes": f"backend={len(by_code)} local_fill={filled} total={len(products)}",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] {OUTPUT} total={len(products)} backend={len(by_code)} fill={filled}")
    roots = {}
    for p in products:
        roots[p["tags"]["1"]] = roots.get(p["tags"]["1"], 0) + 1
    print("[*] raíces:", roots)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
