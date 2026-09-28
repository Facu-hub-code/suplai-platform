#!/usr/bin/env python3
"""Parsea inputs/lista-precios.pdf → CSVs de Fase 1 (Papelera Martínez)."""
from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

import fitz

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
PDF = ROOT / "inputs" / "lista-precios.pdf"
OUT = ROOT / "outputs"
RAW = OUT / "pdf-extract-raw.txt"
COMPLETO = ROOT / "inputs" / "catalogo-completo.csv"
PRODUCTOS = OUT / "phase-01-productos.csv"
LISTA = OUT / "phase-01-lista-precios-1.csv"

GENERIC = {"sin subgrupo", "sin familia", "sin grupo", "prueba", "productos"}
FOOTER = {"cañuelas", "canuelas", "sucursal:", "sucursal", "lista de precios:", "lista de precios"}
COL_HEADERS = {"codigo", "articulo", "unidad", "precio"}
CODE_RE = re.compile(r"^\d{3,8}$")
PRICE_RE = re.compile(r"^\$\s*[\d.,]+$")
UNIT_RE = re.compile(
    r"^(unidades|unidad|caja|cajas|kg|kilos?|rollo|rollos|bulto|bultos|"
    r"pack|packs|docena|docenas|metros?|mts?)$",
    re.I,
)
PACK_RE = re.compile(
    r"(?:^|[\s\(])x\s*(\d{1,4})\s*(?:u(?:n(?:i(?:dades?)?)?)?\.?)?\b",
    re.I,
)
PACK_ALT_RE = re.compile(r"\b(\d{2,4})\s*u(?:nidades?)?\b", re.I)
KNOWN_FAMILIAS = {
    "cajas de carton",
    "carteleria",
    "comestible",
    "cotillon",
    "descartable",
    "embalaje",
    "higiene institucional",
    "libreria",
    "oficina",
    "papel",
    "polietileno",
    "polipropileno",
    "regaleria",
}


def fold(s: str) -> str:
    n = unicodedata.normalize("NFKD", s)
    return "".join(c for c in n if not unicodedata.combining(c)).lower().strip()


def parse_price(raw: str) -> float:
    s = raw.strip().replace("$", "").strip()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        left, _, right = s.partition(",")
        if len(right) == 2 and left.replace(".", "").isdigit():
            s = left.replace(".", "") + "." + right
        else:
            s = s.replace(",", "")
    return float(s)


def unidades_por_bulto(nombre: str) -> int:
    m = PACK_RE.search(nombre)
    if m:
        n = int(m.group(1))
        return n if 1 < n <= 2000 else 1
    m = PACK_ALT_RE.search(nombre)
    if m:
        n = int(m.group(1))
        if 10 <= n <= 2000 and any(tok in fold(nombre) for tok in (" x ", "x ", "caja", "pack")):
            return n
    return 1


def iter_spans(doc: fitz.Document):
    for page_i, page in enumerate(doc, start=1):
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = " ".join("".join(s["text"] for s in spans).split()).strip()
                if not text:
                    continue
                yield {
                    "page": page_i,
                    "text": text,
                    "font": spans[0].get("font", ""),
                    "size": round(spans[0].get("size", 0), 1),
                }


def is_category(span: dict) -> bool:
    return "BoldItalic" in span["font"] and span["size"] >= 12


def is_footer(span: dict) -> bool:
    key = fold(span["text"])
    if key in FOOTER or key.startswith("lista 2"):
        return True
    if span["size"] >= 14:
        return True
    if span["font"] == "Calibri" and span["size"] >= 12 and "BoldItalic" not in span["font"]:
        return True
    return False


def apply_header_burst(pending: list[str], familia: str, subgrupo: str) -> tuple[str, str]:
    keys = [fold(h) for h in pending]
    if "sin grupo" in keys:
        familia = "General"
        subgrupo = ""
    if "sin familia" in keys:
        familia = familia or "General"
        subgrupo = ""
    if "sin subgrupo" in keys:
        subgrupo = ""
    meaningful = [h for h in pending if fold(h) not in GENERIC]
    if len(meaningful) >= 2:
        first, last = meaningful[-2], meaningful[-1]
        if fold(first) in KNOWN_FAMILIAS:
            familia, subgrupo = first, last
        elif fold(last) in KNOWN_FAMILIAS:
            familia, subgrupo = last, ""
        else:
            subgrupo = last
    elif len(meaningful) == 1:
        header = meaningful[0]
        if fold(header) in KNOWN_FAMILIAS or "sin familia" in keys or "sin grupo" in keys or "sin subgrupo" in keys:
            familia = header
            subgrupo = ""
        else:
            subgrupo = header
    return familia, subgrupo


def parse_products(doc: fitz.Document) -> list[dict]:
    spans = [s for s in iter_spans(doc) if not is_footer(s) and fold(s["text"]) not in COL_HEADERS]
    products: list[dict] = []
    pending: list[str] = []
    familia = ""
    subgrupo = ""
    i = 0
    n = len(spans)
    while i < n:
        span = spans[i]
        text = span["text"]
        if is_category(span):
            pending.append(text)
            i += 1
            continue
        if (
            CODE_RE.match(text)
            and i + 3 < n
            and UNIT_RE.match(spans[i + 2]["text"])
            and PRICE_RE.match(spans[i + 3]["text"])
        ):
            if pending:
                familia, subgrupo = apply_header_burst(pending, familia, subgrupo)
                pending = []
            try:
                precio = parse_price(spans[i + 3]["text"])
            except ValueError:
                i += 1
                continue
            if precio > 0:
                products.append(
                    {
                        "product_code": text,
                        "nombre": spans[i + 1]["text"],
                        "precio": round(precio, 2),
                        "unidad": spans[i + 2]["text"].lower(),
                        "categoria_1": familia or "General",
                        "categoria_2": subgrupo,
                        "fuente_hoja": f"lista-precios.pdf#p{span['page']}",
                    }
                )
            i += 4
            continue
        i += 1
    return products


def categoria_3(nombre: str) -> str:
    n = fold(nombre)
    rules = [
        ("pizza", "Pizza"),
        ("empanada", "Empanadas"),
        ("torta", "Tortas"),
        ("cupcake", "Cupcakes"),
        ("budin", "Budines"),
        ("vaso", "Vasos"),
        ("plato", "Platos"),
        ("servilleta", "Servilletas"),
        ("bandeja", "Bandejas"),
        ("bolsa", "Bolsas"),
        ("papel higienico", "Papel higiénico"),
        ("resma", "Resmas"),
        ("resaltador", "Resaltadores"),
        ("cartel", "Carteles"),
        ("cono", "Conos"),
        ("salsa", "Salsas"),
        ("aluminio", "Aluminio"),
        ("film", "Film"),
        ("copa", "Copas"),
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
    ]
    for needle, label in rules:
        if needle in n:
            return label
    return ""


def aliases(code: str, nombre: str) -> str:
    parts = [nombre, code.lstrip("0") or code, code]
    compact = re.sub(r"\s+", " ", nombre)
    if compact != nombre:
        parts.append(compact)
    short = re.sub(r"\b(de|para|con|sin|tipo)\b", " ", fold(nombre), flags=re.I)
    short = re.sub(r"\s+", " ", short).strip()
    if short:
        parts.append(short)
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        key = fold(part)
        if key and key not in seen:
            seen.add(key)
            out.append(part)
    return "|".join(out[:6])


def descripcion(nombre: str, cat1: str, cat2: str, pack: int) -> str:
    bits = [nombre.strip().rstrip(".")]
    if cat2:
        bits.append(f"línea {cat2.lower()}")
    elif cat1:
        bits.append(cat1.lower())
    if pack > 1:
        bits.append(f"presentación x{pack}")
    text = ", ".join(bits) + "."
    words = text.split()
    if len(words) < 10:
        text = f"Artículo de {cat1.lower() or 'papelera'}, {nombre.strip()}, venta por unidad."
        words = text.split()
    if len(words) > 25:
        text = " ".join(words[:25]).rstrip(",.") + "."
    return text


def stock_for(rotacion: float) -> int:
    return max(10, min(500, int(40 + rotacion * 460)))


PROD_FIELDS = [
    "product_code",
    "nombre",
    "precio_lista_1",
    "stock",
    "unidades_por_bulto",
    "unidad_minima_de_venta",
    "umv_tipo",
    "categoria_1",
    "categoria_2",
    "categoria_3",
    "categoria_4",
    "aliases",
    "rotacion_index",
    "mental_priority",
    "descripcion",
    "image_url",
    "en_catalogo",
    "is_mock",
    "fuente_hoja",
]


def main() -> int:
    doc = fitz.open(PDF)
    RAW.write_text(
        "".join(f"\n\n===== PAGE {i+1} =====\n{page.get_text('text')}" for i, page in enumerate(doc)),
        encoding="utf-8",
    )
    products = parse_products(doc)

    seen: dict[str, dict] = {}
    dups = 0
    for product in products:
        if product["product_code"] in seen:
            dups += 1
            continue
        seen[product["product_code"]] = product
    unique = list(seen.values())

    n = len(unique)
    for i, product in enumerate(unique):
        rank = 1 - (i / max(n - 1, 1))
        rot = round(0.10 + 0.85 * (rank**1.4), 3)
        if fold(product["categoria_1"]) in {"cajas de carton", "descartable", "embalaje", "polietileno"}:
            rot = min(0.95, round(rot + 0.08, 3))
        product["unidades_por_bulto"] = unidades_por_bulto(product["nombre"])
        product["rotacion_index"] = rot
        product["mental_priority"] = rot
        product["stock"] = stock_for(rot)
        product["categoria_3"] = categoria_3(product["nombre"])
        product["aliases"] = aliases(product["product_code"], product["nombre"])
        product["descripcion"] = descripcion(
            product["nombre"],
            product["categoria_1"],
            product["categoria_2"],
            product["unidades_por_bulto"],
        )

    def row(product: dict) -> dict:
        return {
            "product_code": product["product_code"],
            "nombre": product["nombre"],
            "precio_lista_1": f"{product['precio']:.2f}",
            "stock": product["stock"],
            "unidades_por_bulto": product["unidades_por_bulto"],
            "unidad_minima_de_venta": "unidad",
            "umv_tipo": "unidad",
            "categoria_1": product["categoria_1"],
            "categoria_2": product["categoria_2"],
            "categoria_3": product["categoria_3"],
            "categoria_4": "",
            "aliases": product["aliases"],
            "rotacion_index": f"{product['rotacion_index']:.3f}",
            "mental_priority": f"{product['mental_priority']:.3f}",
            "descripcion": product["descripcion"],
            "image_url": "",
            "en_catalogo": "true",
            "is_mock": "false",
            "fuente_hoja": product["fuente_hoja"],
        }

    COMPLETO.parent.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (COMPLETO, PRODUCTOS):
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=PROD_FIELDS)
            writer.writeheader()
            for product in unique:
                writer.writerow(row(product))

    lista_fields = [
        "lista_precios_id",
        "nombre",
        "multiplicador_sobre_lista_1",
        "product_code",
        "precio_unidad",
        "is_mock",
    ]
    with LISTA.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=lista_fields)
        writer.writeheader()
        for product in unique:
            writer.writerow(
                {
                    "lista_precios_id": 1,
                    "nombre": "Lista 2",
                    "multiplicador_sobre_lista_1": 1.0,
                    "product_code": product["product_code"],
                    "precio_unidad": f"{product['precio']:.2f}",
                    "is_mock": "false",
                }
            )

    cats: dict[str, set[str]] = {}
    for product in unique:
        cats.setdefault(product["categoria_1"], set()).add(product["categoria_2"] or "(sin subgrupo)")
    print(f"[*] productos={n} duplicados_omitidos={dups} paginas={doc.page_count}")
    print(f"[*] categorias_1={len(cats)}")
    for fam, subs in sorted(cats.items(), key=lambda kv: (-sum(1 for p in unique if p['categoria_1']==kv[0]), kv[0])):
        count = sum(1 for p in unique if p["categoria_1"] == fam)
        print(f"    - {fam} ({count}): {', '.join(sorted(subs))}")
    print(f"[*] {PRODUCTOS}")
    print(f"[*] {LISTA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
