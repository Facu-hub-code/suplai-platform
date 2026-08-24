#!/usr/bin/env python3
"""Genera CSVs Fase 1 demo Forsa: 25 SKUs + catalogo-completo.csv."""
from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INP = ROOT / "inputs" / "lista-precios-origen.csv"
OUT = ROOT / "outputs"
FULL = ROOT / "inputs" / "catalogo-completo.csv"

# Mix de líneas para WhatsApp: limpieza, almacén, yerba, snacks, cigarrillos, pan, bebidas.
DEMO_NAMES = [
    "LAVANDINA COMUN X 1 LT X 1 SEDILE",
    "LAVANDINA CONCENTRADA X 1L X 1 ESENCIAL",
    "ALOE VERA LAVAVAJILLAS 1 X 750CC ESENCIAL",
    "LIQ DESINF 1 X900CC ESENCIAL PINO",
    "LIQ P LAVAR ROPA 1 X800 CLOW",
    "PAPEL HIG. X 1 X 50MTS",
    "ROLLO COCINA X3X50P",
    "ARROZ MITAI CALIDAD 0000",
    "FIDEO SPAGHETTI MAROLIO 1U X 500GR",
    "FIDEO TIRABUZON SANTA ISABEL 1U X 500GR",
    "YERBA PLAYADITO 1U X 1KG",
    "YERBA PLAYADITO 1U X 500GR",
    "TAKIS FUEGO 1 P 140 G FLOW BAR EXP",
    "TAKIS ORIGINAL 1P 49 FLOW BAR EXP",
    "BELDENT FRUTILLA X 20UN",
    "ALFAJOR GENIO TRIPLE NEGRO X 24U",
    "MARLBORO BOX 20",
    "MARLBORO PURPLE 12",
    "LUCKY RED 20",
    "RAPIDITAS CLASIC 1U X 240GR",
    "VAINILLAS 1U X 148G VALENTE",
    "PAN BLANCO 1U X 315GR BOH",
    "JUGO DE NARANJA PURA FRUTTA 1U X 1LT",
    "AGUA VIDA BAGGGIO MANZANA 1U X 1.5LT",
    "TRAPO PISO BLANCO X1X60X50CM",
]

SKIP_NAMES = {"ADELANTO CTA CTE", "CANCELACION CTA CTE"}

PRODUCT_FIELDS = [
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

PRICE_FIELDS = [
    "lista_precios_id",
    "nombre",
    "multiplicador_sobre_lista_1",
    "product_code",
    "precio_unidad",
    "is_mock",
]

LISTAS = [
    (1, "Lista Base (Público)", 1.00),
    (2, "Lista Minorista Sugerido", 1.15),
    (3, "Lista Mayorista Especial", 0.90),
    (4, "Lista Gran Distribuidor", 0.85),
]

MARCAS = [
    "SEDILE",
    "ESENCIAL",
    "CLOW",
    "DOMITEC",
    "PLAYADITO",
    "MAROLIO",
    "SANTA ISABEL",
    "TAKIS",
    "BELDENT",
    "MARLBORO",
    "LUCKY",
    "BIMBO",
    "VALENTE",
    "PURA FRUTTA",
    "BAGGIO",
    "BAGGGIO",
    "GENIO",
    "RASTA",
    "BOH",
    "MITAI",
    "CASCABEL",
    "NEVARES",
]


def pack_qty(nombre: str) -> int:
    n = nombre.upper()
    patterns = [
        r"X\s*(\d+)\s*U\b",
        r"X\s*(\d+)\s*UN\b",
        r"POR\s+(\d+)\s*U",
        r"X(\d+)\s*U",
        r"X(\d+)U",
        r"(\d+)\s*PAQ",
    ]
    for pat in patterns:
        m = re.search(pat, n)
        if m:
            q = int(m.group(1))
            if 1 < q <= 5000:
                return q
    return 1


def marca_de(nombre: str) -> str:
    up = nombre.upper()
    for m in MARCAS:
        if m in up:
            return "BAGGIO" if m == "BAGGGIO" else m
    return ""


def categorias(nombre: str) -> tuple[str, str, str, str]:
    u = nombre.upper()
    marca = marca_de(nombre)
    if any(x in u for x in ["MARLBORO", "LUCKY"]):
        return ("Cigarrillos", "Box", marca, "")
    if any(x in u for x in ["LAVANDINA", "LAVAVAJ", "DETER", "DESINF", "CLOW", "SEDILE", "ESENCIAL"]):
        linea = "Lavandina" if "LAVANDINA" in u else "Limpieza"
        if "LAVAVAJ" in u or "VAVAJ" in u:
            linea = "Lavavajillas"
        if "DESINF" in u:
            linea = "Desinfectante"
        if "LAVAR ROPA" in u:
            linea = "Ropa"
        return ("Limpieza", linea, marca, "")
    if "PAPEL HIG" in u or "ROLLO COCINA" in u:
        return ("Papel", "Higiene" if "HIG" in u else "Cocina", marca, "")
    if "TRAPO" in u:
        return ("Limpieza", "Paños", marca, "")
    if any(x in u for x in ["FIDEO", "ARROZ", "ATUN", "POLENTA", "LENTEJA"]):
        return ("Almacén", "Secos", marca, "")
    if "YERBA" in u or "MATE COCIDO" in u:
        return ("Infusiones", "Yerba", marca, "")
    if "TAKIS" in u or "PAPAS FRITAS" in u:
        return ("Snacks", "Picadas", marca, "")
    if any(x in u for x in ["BELDENT", "ALFAJOR", "CHUPETIN", "GALL ", "BUDIN"]):
        return ("Golosinas", "Kiosco", marca, "")
    if any(x in u for x in ["BIMBO", "VAINILLA", "PAN ", "RAPIDITA"]):
        return ("Panificados", "Panadería", marca, "")
    if any(x in u for x in ["AGUA", "JUGO", "VINO", "BAGGGIO", "BAGGIO"]):
        return ("Bebidas", "Jugos" if "JUGO" in u or "AGUA VIDA" in u else "Otras", marca, "")
    return ("Almacén", "General", marca, "")


def descripcion_corta(nombre: str, cat1: str, cat2: str, qty: int) -> str:
    marca = marca_de(nombre)
    extra = f", marca {marca.title() if marca != 'SEDILE' else 'Sedile'}" if marca else ""
    if marca == "SEDILE":
        extra = ", marca Sedile"
    pack = f", pack x{qty}" if qty > 1 else ""
    base = nombre.split(" X ")[0].split(" 1U")[0].strip().lower()
    text = f"{cat2 or cat1} de {cat1.lower()}{extra}{pack}, {base}."
    words = text.split()
    if len(words) > 25:
        text = " ".join(words[:24]) + "."
    return text[0].upper() + text[1:]


def aliases(nombre: str, cat1: str, cat2: str, code: str) -> str:
    parts = [nombre.lower(), cat2.lower(), cat1.lower(), code]
    marca = marca_de(nombre)
    if marca:
        parts.append(marca.lower())
        parts.append(f"{marca.lower()} {cat2.lower()}")
    for tok in re.findall(r"[A-ZÁÉÍÓÚÑ]{3,}", nombre):
        if tok.lower() not in {p.lower() for p in parts}:
            parts.append(tok.lower())
    seen: set[str] = set()
    out = []
    for p in parts:
        p = p.strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return "|".join(out[:8])


def to_row(r: dict, i: int, n: int) -> dict | None:
    nombre = (r.get("nombre") or "").strip()
    if not nombre or nombre.upper() in SKIP_NAMES:
        return None
    try:
        precio = float(r.get("precio") or 0)
    except ValueError:
        return None
    if precio <= 1:
        return None
    row_num = int(float(r["row_num"]))
    code = f"F{row_num:03d}"
    qty = pack_qty(nombre)
    cat1, cat2, cat3, cat4 = categorias(nombre)
    rot = round(0.92 - (i / max(n - 1, 1)) * 0.55, 2)
    stock = int(80 + rot * 350)
    return {
        "product_code": code,
        "nombre": nombre,
        "precio_lista_1": f"{precio:.2f}",
        "stock": str(stock),
        "unidades_por_bulto": str(qty),
        "unidad_minima_de_venta": "unidad",
        "umv_tipo": "unidad",
        "categoria_1": cat1,
        "categoria_2": cat2,
        "categoria_3": cat3,
        "categoria_4": cat4,
        "aliases": aliases(nombre, cat1, cat2, code),
        "rotacion_index": str(rot),
        "mental_priority": str(round(rot * 0.8, 2)),
        "descripcion": descripcion_corta(nombre, cat1, cat2, qty),
        "image_url": "",
        "en_catalogo": "true",
        "is_mock": "true",
        "fuente_hoja": "Hoja1",
    }


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def main() -> int:
    with INP.open(encoding="utf-8", newline="") as f:
        raw = list(csv.DictReader(f))

    full_rows: list[dict] = []
    by_name: dict[str, dict] = {}
    for i, r in enumerate(raw):
        row = to_row(r, i, len(raw))
        if not row:
            continue
        full_rows.append(row)
        by_name[row["nombre"].strip().upper()] = row

    write_csv(FULL, PRODUCT_FIELDS, full_rows)
    print(f"[*] catalogo-completo.csv: {len(full_rows)} filas (origen {len(raw)})")

    demo: list[dict] = []
    missing = []
    for i, name in enumerate(DEMO_NAMES):
        src = by_name.get(name.strip().upper())
        if not src:
            missing.append(name)
            continue
        row = dict(src)
        row["rotacion_index"] = str(round(0.95 - i * 0.02, 2))
        row["mental_priority"] = str(round(float(row["rotacion_index"]) * 0.85, 2))
        row["stock"] = str(int(120 + float(row["rotacion_index"]) * 280))
        demo.append(row)
    if missing:
        print(f"[FAIL] SKUs demo no encontrados: {missing}")
        return 1

    write_csv(OUT / "phase-01-productos.csv", PRODUCT_FIELDS, demo)
    print(f"[*] phase-01-productos.csv: {len(demo)} SKUs demo")

    combined_prices: list[dict] = []
    for list_id, nombre, mult in LISTAS:
        price_rows = []
        for p in demo:
            base = float(p["precio_lista_1"])
            rec = {
                "lista_precios_id": list_id,
                "nombre": nombre,
                "multiplicador_sobre_lista_1": f"{mult:.2f}",
                "product_code": p["product_code"],
                "precio_unidad": f"{round(base * mult, 2):.2f}",
                "is_mock": "true",
            }
            price_rows.append(rec)
            combined_prices.append(rec)
        write_csv(OUT / f"phase-01-lista-precios-{list_id}.csv", PRICE_FIELDS, price_rows)
        print(f"[*] lista {list_id} {nombre}: {len(price_rows)}")

    write_csv(OUT / "phase-01-listas-precios.csv", PRICE_FIELDS, combined_prices)

    print("\n--- MUESTRA DEMO ---")
    for p in demo:
        print(f"  {p['product_code']:>5}  ${float(p['precio_lista_1']):>10.2f}  {p['nombre'][:62]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
