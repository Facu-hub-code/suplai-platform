#!/usr/bin/env python3
"""Genera CSVs Fase 1 demo Rawson: 25 SKUs + catalogo-completo.csv (148)."""
from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INP = ROOT / "inputs" / "rawson_productos.csv"
OUT = ROOT / "outputs"
FULL = ROOT / "inputs" / "catalogo-completo.csv"

# 25 SKUs de demo: mix de líneas para WhatsApp (bandejas, vasos, bolsas, aluminio, guantes).
DEMO_CODES = [
    "120",  # Aluminio DPM x10
    "344",  # Rollo aluminio 1kg
    "339",  # Bandeja aluminio F100
    "545",  # Plato aluminio N21
    "457",  # Bandeja INPACK 101PP
    "173",  # Bandeja SUPERBAND PET
    "252",  # Bolsa camiseta
    "178",  # Vaso 180cc
    "150",  # Film PVC DPM
    "558",  # Pote 270cc
    "331",  # Sorbetes
    "123",  # Bolsa fondo cuadrado
    "488",  # Blonda 25cm
    "420",  # Molde airfryer
    "211",  # Papel diario
    "509",  # Caja cartulina visor
    "241",  # Bandeja cartón N4
    "202",  # Caja media pizza
    "353",  # Bandeja exp 180
    "531",  # Oblea telgopor
    "589",  # Vaso ripple 12oz
    "411",  # Hilo algodón
    "257",  # Guantes látex
    "262",  # Guantes nitrilo
    "347",  # Pinchos bambú
]

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

PRICE_FIELDS = ["lista_precios_id", "nombre", "multiplicador_sobre_lista_1", "product_code", "precio_unidad", "is_mock"]

LISTAS = [
    (1, "Lista Base (Público)", 1.00),
    (2, "Lista Minorista Sugerido", 1.15),
    (3, "Lista Mayorista Especial", 0.90),
    (4, "Lista Gran Distribuidor", 0.85),
]

MARCAS = [
    "INPACK",
    "SUPERBAND",
    "EXTRUCSYSTEM",
    "CELPAK",
    "DPM",
    "TELGOPOR",
    "PETIT",
]


def pack_qty(nombre: str) -> int:
    n = nombre.upper()
    patterns = [
        r"X\s*(\d+)\s*U",
        r"POR\s+(\d+)\s*U",
        r"X\s*(\d+)\s*UNI",
        r"X\s*(\d+)\s*UNID",
        r"X\s*(\d+)\s*UN\b",
        r"(\d+)\s*PAQ",
        r"X(\d+)\s*U",
        r"X(\d+)U",
        r"X(\d+)\s*UNID",
        r"POR\s+(\d+)U",
        r"X\s*(\d+)\s*$",
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
            return m
    return ""


def descripcion_corta(nombre: str, categoria: str, etiqueta: str, qty: int) -> str:
    marca = marca_de(nombre)
    linea = categoria.replace("Línea ", "").strip() or etiqueta
    extra = f", marca {marca}" if marca else ""
    pack = f", pack x{qty}" if qty > 1 else ""
    text = f"{etiqueta.capitalize()} de {linea.lower()}{extra}{pack}, {nombre.split(' X ')[0].split(' POR ')[0].strip().lower()}."
    words = text.split()
    if len(words) > 25:
        text = " ".join(words[:24]) + "."
    return text[0].upper() + text[1:]


def aliases(nombre: str, categoria: str, etiqueta: str, code: str) -> str:
    parts = [nombre.lower(), etiqueta, categoria.replace("Línea ", "").lower(), code]
    marca = marca_de(nombre)
    if marca:
        parts.append(marca.lower())
        parts.append(f"{marca.lower()} {etiqueta}")
    # tokens útiles
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


def normalizar_alias(alias_raw: str) -> str:
    alias_lower = alias_raw.lower().strip()
    alias_flat = unicodedata.normalize("NFKD", alias_lower)
    return "".join(c for c in alias_flat if ("a" <= c <= "z") or ("0" <= c <= "9"))


def to_row(r: dict, i: int, n: int) -> dict | None:
    try:
        precio = float(r.get("precio") or 0)
    except ValueError:
        return None
    if precio <= 0:
        return None
    code = str(r["product_id"]).strip()
    nombre = (r.get("nombre") or "").strip()
    if not nombre:
        return None
    qty = pack_qty(nombre)
    cat1 = (r.get("categoria") or "Descartables").strip()
    etq = (r.get("etiqueta") or "").strip()
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
        "categoria_2": etq,
        "categoria_3": marca_de(nombre),
        "categoria_4": "",
        "aliases": aliases(nombre, cat1, etq, code),
        "rotacion_index": str(rot),
        "mental_priority": str(round(rot * 0.8, 2)),
        "descripcion": descripcion_corta(nombre, cat1, etq, qty),
        "image_url": (r.get("imagen_url") or "").strip(),
        "en_catalogo": "true",
        "is_mock": "true",
        "fuente_hoja": "rawson_productos.csv",
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
    by_code: dict[str, dict] = {}
    for i, r in enumerate(raw):
        row = to_row(r, i, len(raw))
        if not row:
            continue
        full_rows.append(row)
        by_code[row["product_code"]] = row

    write_csv(FULL, PRODUCT_FIELDS, full_rows)
    print(f"[*] catalogo-completo.csv: {len(full_rows)} filas (origen {len(raw)})")

    demo: list[dict] = []
    missing = []
    for i, code in enumerate(DEMO_CODES):
        src = by_code.get(code)
        if not src:
            missing.append(code)
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

    for list_id, nombre, mult in LISTAS:
        price_rows = []
        for p in demo:
            base = float(p["precio_lista_1"])
            price_rows.append(
                {
                    "lista_precios_id": list_id,
                    "nombre": nombre,
                    "multiplicador_sobre_lista_1": f"{mult:.2f}",
                    "product_code": p["product_code"],
                    "precio_unidad": f"{round(base * mult, 2):.2f}",
                    "is_mock": "true",
                }
            )
        write_csv(OUT / f"phase-01-lista-precios-{list_id}.csv", PRICE_FIELDS, price_rows)
        print(f"[*] lista {list_id} {nombre}: {len(price_rows)}")

    print("\n--- MUESTRA DEMO ---")
    for p in demo:
        print(f"  {p['product_code']:>5}  ${float(p['precio_lista_1']):>10.2f}  {p['nombre'][:62]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
