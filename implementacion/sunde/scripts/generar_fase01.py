#!/usr/bin/env python3
"""Genera CSVs Fase 1 demo sunde: universo → catalogo-completo.csv, recorte 80–100.

schema_name = sunde. Precio de lista = columna de precio del Excel (precio final).
Modo demo: no cargar el Excel entero.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

import xlrd

ROOT = Path(__file__).resolve().parents[1]
XLS = ROOT / "inputs" / "lista-precios-21-08-26.xls"
OUT = ROOT / "outputs"

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

LISTAS = [
    (1, "Lista Base (Público)", 1.00),
    (2, "Lista Minorista Sugerido", 1.15),
    (3, "Lista Mayorista Especial", 0.90),
    (4, "Lista Gran Distribuidor", 0.85),
]

# Recorte demo (~95). Criterio skill: exclusiva SUNDE/fabricación, líneas de la
# reunión (escoba, escobillón de cerda, olla del 50, baldes, organizadores),
# líquidos de terceros, jardín, sahumerios, bazar. Sin La Gotita.
INCLUDE = {
    # Fabricación / exclusiva SUNDE (~28)
    "1415", "1416", "1414", "1407", "1421",
    "FS-701", "1828", "FS-702", "1830",
    "1600", "1607", "1604", "1608", "1950",
    "1521", "1522", "1523",
    "SND-2521", "SND-2522", "SND-2523", "SND-2524",
    "SND-569", "SND-568",
    "8026", "8030", "7416",
    "2600", "2601", "2572",
    # Pedidos por WhatsApp (olla, balde, organizador, pala)
    "MK-6934", "B2412", "LNN-2460", "LNN-248", "LNN-183",
    "B3140", "B3146", "B3150", "B3248", "B3250",
    "B2533", "B2530", "B2531",
    "1700", "7004", "7000",
    # Líquidos de terceros (no fabrican)
    "3410", "3408", "4204", "4200", "IJL07", "ALB-1001", "MEL-04", "IDI25",
    # Marcas de zona / competencia (Make y FS, máx ~8 Make)
    "FS-2020", "FS-2021", "FS-2035", "FS-2040",
    "MK-6252", "MK-40N", "MK-6127",
    # Jardinería
    "1802", "1810", "B2507", "B2510", "B2515", "FL-900", "FL-904", "B2490", "FL-911",
    # Sahumerios + aromatización
    "160-02", "160-03", "160-12", "160-33", "160-10",
    "150-02", "432B-02", "432D-10", "100P-5",
    "072-10", "072-25", "051-14", "051-39", "AER-559L", "MK-70014",
    # Bazar (Loekemeyer, Make, Tramontina)
    "A2470", "A2472", "MK-6585", "MK-6130",
    "PTB-0327806002", "PTB-20144622", "PTB-20510726", "PTB-0327899038",
    "B5122",
}

MARCAS = [
    ("LOEKEMEYER", "Loekemeyer"),
    ("TRAMONTINA", "Tramontina"),
    ("FORMIA", "Formia"),
    ("VERMONT", "Vermont"),
    ("FRAGANSS", "Fraganss"),
    ("AROMANZA", "Aromanza"),
    ("SUNDE", "SUNDE"),
    ("FRAU", "Frau"),
    ("MAKE", "Make"),
    ("MEKE", "Make"),
]

PREFIX_MARCA = {
    "MK": "Make",
    "LKM": "Loekemeyer",
    "PTB": "Tramontina",
    "SND": "SUNDE",
    "AER": "Fraganss",
    "FL": "Florencia",
    "DSP": "Dispro",
    "NWP": "Newplast",
    "EDN": "Edén",
    "OL": "Oliva",
}

HIGH_ROT = (
    "ESCOBA",
    "ESCOBILLON",
    "ESCOBILLÓN",
    "BALDE",
    "OLLA",
    "CABO",
    "TRAPO",
    "LAMPAZO",
    "SECADOR",
    "PALA",
    "REJILLA",
    "ESPONJA",
    "DETERGENTE",
    "LAVANDINA",
    "JABON",
    "JABÓN",
)

MED_ROT = (
    "MACETA",
    "BARREHOJA",
    "SAHUMERIO",
    "AROMATIZANTE",
    "VELON",
    "VELÓN",
    "ASADERA",
    "SARTEN",
    "SARTÉN",
    "FUENTON",
    "FUENTÓN",
    "ORGANIZADOR",
    "PLATO",
    "VASO",
    "TASA",
    "TAZA",
)

BULT_RE = re.compile(
    r"(?:\(B/(\d+)\)|\bX\s*(\d+)\s*(?:UN|UNID|U)\b|\bJGO\s*X\s*(\d+)\b|\bSET\s*X\s*(\d+)\b|\bX(\d+)\s*UN\b)",
    re.I,
)


def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii").upper()


def is_price(v) -> bool:
    return isinstance(v, (int, float)) and float(v) > 0


def clean_code(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def clean_name(v) -> str:
    return " ".join(str(v or "").split())


def unidades_por_bulto(nombre: str) -> int:
    m = BULT_RE.search(nombre)
    if not m:
        return 1
    for g in m.groups():
        if g:
            n = int(g)
            return n if 1 < n <= 500 else 1
    return 1


def detect_marca(code: str, nombre: str) -> str:
    n = norm(nombre)
    for needle, label in MARCAS:
        if needle in n:
            return label
    pref = code.split("-")[0].upper() if "-" in code else ""
    return PREFIX_MARCA.get(pref, "")


def has_token(n: str, *keys: str) -> bool:
    return any(re.search(rf"(?<![A-Z]){re.escape(k)}", n) for k in keys)


def cats_from_name(cat1: str, nombre: str) -> tuple[str, str, str]:
    n = norm(nombre)
    nro = re.search(r"N[°º]?\s*(\d+)", n)
    nro_s = nro.group(1) if nro else ""
    if has_token(n, "ESCOBITA", "ESCOBA"):
        return "Escobas", "Cerdas" if "HILO" in n else "", ""
    if has_token(n, "ESCOBILL"):
        return "Escobillones", "", ""
    if has_token(n, "BALDE"):
        return "Baldes", "Colores" if "COLOR" in n else "", ""
    if has_token(n, "CABO"):
        return "Cabos", "Madera" if "MADERA" in n else "Accesorios", ""
    if has_token(n, "LAMPAZO", "MOPA"):
        return "Lampazos", "Premium" if "PREMIUM" in n else "Estándar", ""
    if has_token(n, "TRAPO", "REJILLA", "PANO"):
        return "Paños y trapos", "", ""
    if has_token(n, "SECADOR"):
        return "Secadores", "", ""
    if has_token(n, "PALA"):
        return "Palas", "", ""
    if has_token(n, "OLLA"):
        return "Ollas", f"N° {nro_s}" if nro_s else "", ""
    if has_token(n, "SARTEN"):
        return "Sartenes", "", ""
    if has_token(n, "ASADERA"):
        return "Asaderas", "", ""
    if has_token(n, "ABRELATA"):
        return "Abrelatas", "", ""
    if has_token(n, "MACETA", "JARDINERA"):
        return "Macetas", "", ""
    if has_token(n, "BARREHOJA"):
        return "Barrehojas", "", ""
    if has_token(n, "SAHUMER", "INCIENSO"):
        return "Sahumerios", "", ""
    if has_token(n, "AROMATIZ", "AEROSOL"):
        return "Aromatizantes", "Aerosol" if "AEROSOL" in n else "", ""
    if has_token(n, "VELON", "ESENCIA", "HORNILLO"):
        return "Aromatización", "", ""
    if has_token(n, "DETERGENTE", "LAVANDINA", "JABON", "CLORO", "DESENGRAS"):
        return "Líquidos de limpieza", "", ""
    if has_token(n, "ORGANIZADOR"):
        return "Organizadores", "", ""
    if has_token(n, "ADHESIVO", "GOTITA", "SILICONA", "CINTA"):
        return "Adhesivos", "", ""
    if has_token(n, "TORNILLO", "CLAVO", "TUERCA", "ALICATE"):
        return "Ferretería", "", ""
    return cat1.title(), "", ""


def rotation(nombre: str, marca: str) -> float:
    n = norm(nombre)
    if any(k in n for k in HIGH_ROT):
        return 0.86
    if marca == "Make" or any(k in n for k in MED_ROT):
        return 0.62
    if "GOTITA" in n:
        return 0.18
    return 0.32


def stock_for(rot: float) -> int:
    if rot >= 0.8:
        return 280
    if rot >= 0.55:
        return 140
    return 45


def descripcion(nombre: str, marca: str, cat2: str, bulto: int) -> str:
    name = clean_name(nombre)
    core = name[0].upper() + name[1:].lower() if name else nombre
    extra: list[str] = []
    brand = marca or "SUNDE"
    if brand.upper() not in norm(name):
        extra.append(f"marca {brand}")
    if cat2:
        extra.append(f"rubro {cat2.lower()}")
    extra.append(f"presentación x{bulto}" if bulto > 1 else "venta por unidad")
    text = f"{core}, {', '.join(extra)}."
    words = text.split()
    if len(words) > 25:
        text = " ".join(words[:24]).rstrip(",") + "."
    if len(words) < 10:
        text = text.rstrip(".") + ", catálogo SUNDE."
    return text


def aliases(code: str, nombre: str, marca: str) -> str:
    n = clean_name(nombre)
    bits = [code, n]
    short = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9ÁÉÍÓÚÑ°\s\-/]", "", n, flags=re.I)).strip()
    if short and short != n:
        bits.append(short)
    if marca:
        bits.append(marca)
    # jerga: "olla del 50", "balde lila"
    m = re.search(r"OLLA.*?N[°º]?\s*(\d+)", norm(n))
    if m:
        bits.append(f"olla del {m.group(1)}")
        bits.append(f"olla {m.group(1)}")
    m = re.search(r"ESCOBA\s+(.+)", n, re.I)
    if m:
        bits.append(f"escoba {m.group(1).strip().lower()}")
    if "ESCOBILL" in norm(n):
        bits.append("escobillón")
        if "CERDA" in norm(n):
            bits.append("escobillon de cerda")
    if "BALDE" in norm(n):
        bits.append("balde")
        color = re.search(r"\b(LILA|AMARILLO|ROJO|AZUL|VERDE|NEGRO|BLANCO|NARANJA)\b", norm(n))
        if color:
            bits.append(f"balde {color.group(1).lower()}")
        if "COLOR" in norm(n):
            bits.extend(["balde lila", "balde amarillo", "tres baldes lilas"])
    seen: list[str] = []
    for b in bits:
        b = b.strip()
        if b and b not in seen:
            seen.append(b)
    return "|".join(seen[:8])


def add_row(rows: list[dict], seen: dict[str, str], *, code: str, nombre: str, precio: float, cat1: str, fuente: str, skipped: list[str]) -> None:
    code = clean_code(code)
    nombre = clean_name(nombre)
    if not code or not nombre or not is_price(precio):
        return
    if code.upper() in {"CODIGO", "CÓDIGO"}:
        return
    if code in seen:
        skipped.append(f"duplicado {code} ({fuente}, ya en {seen[code]})")
        return
    seen[code] = fuente
    marca = detect_marca(code, nombre)
    cat2, cat3, cat4 = cats_from_name(cat1, nombre)
    rot = rotation(nombre, marca)
    bulto = unidades_por_bulto(nombre)
    rows.append(
        {
            "product_code": code,
            "nombre": nombre,
            "precio_lista_1": f"{round(float(precio), 2):.2f}",
            "stock": stock_for(rot),
            "unidades_por_bulto": bulto,
            "unidad_minima_de_venta": "unidad",
            "umv_tipo": "unidad",
            "categoria_1": cat1,
            "categoria_2": cat2,
            "categoria_3": cat3 or marca,
            "categoria_4": cat4,
            "aliases": aliases(code, nombre, marca),
            "rotacion_index": f"{rot:.2f}",
            "mental_priority": f"{rot:.2f}",
            "descripcion": descripcion(nombre, marca, cat2, bulto),
            "image_url": "",
            "en_catalogo": "true",
            "is_mock": "true",
            "fuente_hoja": fuente,
        }
    )


def parse_simple(sh, sheet_name: str, default_cat: str, rows, seen, skipped) -> None:
    cat = default_cat
    for r in range(sh.nrows):
        c0, c1, c2 = sh.cell_value(r, 0), sh.cell_value(r, 1), sh.cell_value(r, 2)
        code, name = clean_code(c0), clean_name(c1)
        if not code and name and not is_price(c2):
            cat = name.title()
            continue
        add_row(rows, seen, code=code, nombre=name, precio=c2 if is_price(c2) else 0, cat1=cat, fuente=sheet_name, skipped=skipped)


def parse_sahumerios(sh, rows, seen, skipped) -> None:
    packs = [
        (0, 1, "Sahumerio empaste simple x100", 5408.19),
        (2, 3, "Sahumerio empaste simple x15", 1051.49),
        (4, 5, "Sahumerio triple empaste x50", 4124.5),
        (6, 7, "Sahumerio triple empaste x10", 1241.28),
    ]
    for r in range(6, 35):
        for col_code, col_name, pref, price in packs:
            code = clean_code(sh.cell_value(r, col_code))
            name = clean_name(sh.cell_value(r, col_name))
            if not code or code.upper() in {"CODIGO", "SAHUMERIOS"}:
                continue
            if not name or name.upper().startswith("SAHUMERIOS") or name.upper() in {"ZAD BLACK", "AROMANZA"}:
                continue
            full = f"{pref} {name}".strip()
            add_row(rows, seen, code=code, nombre=full, precio=price, cat1="Sahumerios", fuente="S 21-8", skipped=skipped)

    # Tibetano x8
    for r in range(38, 44):
        code = clean_code(sh.cell_value(r, 6))
        name = clean_name(sh.cell_value(r, 7))
        if code and name:
            add_row(
                rows,
                seen,
                code=code,
                nombre=f"Sahumerio tibetano x8 {name}",
                precio=3727.43,
                cat1="Sahumerios",
                fuente="S 21-8",
                skipped=skipped,
            )
    add_row(
        rows,
        seen,
        code="101Q-B",
        nombre="Sahumerio Aromanza magistral x8 Mix Resinas",
        precio=2282.55,
        cat1="Sahumerios",
        fuente="S 21-8",
        skipped=skipped,
    )


def parse_aromas(sh, rows, seen, skipped) -> None:
    # Veloncitos 072-* @ 1743
    for r in range(5, 22):
        code = clean_code(sh.cell_value(r, 2))
        name = clean_name(sh.cell_value(r, 3))
        if code and name and not name.upper().startswith("AROMATIZ"):
            add_row(
                rows,
                seen,
                code=code,
                nombre=f"Veloncito aromático 5x3.5 {name}",
                precio=1743.0,
                cat1="Aromatizantes",
                fuente="A 21-8",
                skipped=skipped,
            )
    # Esencias 051-* @ 1332.19
    for r in range(5, 34):
        code = clean_code(sh.cell_value(r, 4))
        name = clean_name(sh.cell_value(r, 5))
        if code and name:
            add_row(
                rows,
                seen,
                code=code,
                nombre=f"Esencia para hornillo {name}",
                precio=1332.19,
                cat1="Aromatizantes",
                fuente="A 21-8",
                skipped=skipped,
            )
    # Fraganss 360 ml @ 2972.5
    for r in range(30, 35):
        code = clean_code(sh.cell_value(r, 2))
        name = clean_name(sh.cell_value(r, 3))
        if code and name and code.upper() not in {"CODIGO"}:
            add_row(
                rows,
                seen,
                code=code,
                nombre=f"Aromatizante aerosol Fraganss 360ml {name}",
                precio=2972.5,
                cat1="Aromatizantes",
                fuente="A 21-8",
                skipped=skipped,
            )
    # MAKE aerosols: sin precio unitario en la hoja → se omiten
    extras = [
        (36, 2, 3, 36, 5),  # PRACTI DUO
        (37, 2, 3, 37, 5),  # DISPENSER
    ]
    for r_code, c_code, c_name, r_price, c_price in extras:
        code = clean_code(sh.cell_value(r_code, c_code))
        name = clean_name(sh.cell_value(r_code, c_name))
        price = sh.cell_value(r_price, c_price)
        if code and name and is_price(price):
            add_row(rows, seen, code=code, nombre=name, precio=price, cat1="Aromatizantes", fuente="A 21-8", skipped=skipped)


def main() -> int:
    wb = xlrd.open_workbook(XLS)
    rows: list[dict] = []
    seen: dict[str, str] = {}
    skipped: list[str] = []

    parse_simple(wb.sheet_by_name("L 21-08"), "L 21-08", "Fabricación", rows, seen, skipped)
    parse_simple(wb.sheet_by_name("J 21-08"), "J 21-08", "Jardinería", rows, seen, skipped)
    parse_simple(wb.sheet_by_name("B 21-08"), "B 21-08", "Bazar", rows, seen, skipped)
    parse_sahumerios(wb.sheet_by_name("S 21-8"), rows, seen, skipped)
    parse_aromas(wb.sheet_by_name("A 21-8"), rows, seen, skipped)

    full_path = ROOT / "inputs" / "catalogo-completo.csv"
    with full_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PRODUCT_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"[*] universo con precio: {len(rows)} → {full_path}")

    missing = sorted(INCLUDE - {p["product_code"] for p in rows})
    if missing:
        print(f"[WARN] INCLUDE no hallados: {missing}")
    demo = [p for p in rows if p["product_code"] in INCLUDE]
    if not (80 <= len(demo) <= 100):
        print(f"[WARN] recorte demo fuera de 80–100: {len(demo)}")
    rows = demo

    out_prod = OUT / "phase-01-productos.csv"
    with out_prod.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PRODUCT_FIELDS)
        w.writeheader()
        w.writerows(rows)

    listas_rows = []
    for lid, lname, mult in LISTAS:
        path = OUT / f"phase-01-lista-precios-{lid}.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["product_code", "precio_unidad", "is_mock"])
            w.writeheader()
            for p in rows:
                precio = round(float(p["precio_lista_1"]) * mult, 2)
                w.writerow({"product_code": p["product_code"], "precio_unidad": f"{precio:.2f}", "is_mock": "true"})
                listas_rows.append((lid, lname, mult, p["product_code"], precio))

    with (OUT / "phase-01-listas-precios.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lista_precios_id", "nombre", "multiplicador_sobre_lista_1", "product_code", "precio_unidad", "is_mock"])
        for lid, lname, mult, code, precio in listas_rows:
            w.writerow([lid, lname, f"{mult:.2f}", code, f"{precio:.2f}", "true"])

    from collections import Counter

    c1 = Counter(p["categoria_1"] for p in rows)
    print(f"[*] productos={len(rows)}")
    print(f"[*] por categoria_1: {dict(c1)}")
    print(f"[*] omitidos/duplicados={len(skipped)}")
    for s in skipped[:12]:
        print(f"    - {s}")
    print(f"[*] sample: {rows[0]['product_code']} {rows[0]['nombre']} ${rows[0]['precio_lista_1']}")
    print(f"[SUCCESS] {out_prod}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
