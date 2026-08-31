#!/usr/bin/env python3
"""Fase 1 — extrae LISTA-B.pdf → universo + recorte demo 80–100 SKUs (psq).

schema_name = psq. Precio = Lista B (precio final). Sin códigos en el PDF:
se asigna PSQ-NNNN en orden de aparición. Modo demo: no cargar el PDF entero.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "inputs" / "LISTA-B.pdf"
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

# Lista 1 = Lista B recibida. Lista 4 = precio especial por cliente (pedido de Tadeo).
LISTAS = [
    (1, "Lista B Gastronómicos", 1.00),
    (2, "Lista Clean Max (e-commerce)", 1.15),
    (3, "Lista Mayorista", 0.90),
    (4, "Lista Cliente especial", 0.85),
]

SKIP_NAMES = {
    "VARIOS",
    "LOGISTICA SANTI",
    "LOGISTICA PSQUIMICA",
    "CESTO DE RESIDUOPS INDUSTRIAL C/RUEDA 240LTS",
    "SECAMANOS DE AIRE PROFESIONAL ACERO INOX NEGRO",
    "VASO TEQUILA",
}

# Recorte demo (~95). Criterio: marca PSQ, sets fabricación 100 L, línea 1L/5L,
# gastronomía, bolsas, papel, trapos y unas marcas de góndola.
INCLUDE_NORM = {
    # Marca propia PSQ / PSQuimica
    "ANTI-HONGOS GATILLO 500ML PSQ",
    "ANTI-HONGOS X 5LTS PSQUIMICA",
    "DESENGRASANTE 500ML PSQUIMICA",
    "DESTAPA CAÑERIAS X LT PSQUIMICA",
    "ELIMINADOR DE OLORES PSQ X U. (1LT)",
    "ELIMINADOR DE OLORES PSQ X U. (500ML)",
    "LIMPIA TAPIZADOS 500ML PSQ",
    "LIMPIAVIDRIOS GATILLO 475ML PSQ",
    "MULTIUSO AZULEJOS X 500ML PSQUIMICA",
    "QUITAMANCHAS 500ML PSQ",
    "QUITASARRO GATILLO 500ML PSQ",
    "FRIOCLEAN 500ML",
    # Marca blanca / fabricación
    "SET COMBO 4X50 LT (JAB-SUA-DES-PERF)",
    "SET FAB DESENGRASANTE X 100LTS",
    "SET FAB DETERGENTE USO DIRECTO X 100LTS",
    "SET FAB JABON PLUS X 100LTS ARIEL/SKIP",
    "SET FAB SUAVIZANTE X 100LTS CONFORT/ VIVERE",
    "SET LAVANDINA 100LTS",
    "SET PERFUMINA 100 LTS",
    # Línea química 1 L / 5 L (lo que pide el bar por WhatsApp)
    "JABON PLUS X1L (ARIEL/SKIP)",
    "JABON PLUS SKIP/ARIEL X5L",
    "JABON PARA MANOS X1L",
    "JABON PARA MANOS X5L",
    "DETERGENTE USO DIRECTO X1L",
    "DETERGENTE USO DIRECTO X5L",
    "LAVANDINA X1L",
    "LAVANDINA X5L",
    "SUAVIZANTE PARA ROPA X1L",
    "SUAVIZANTE P/ROPA X5L",
    "PERFUMINA X 1L",
    "PERFUMINA X 5L",
    "ALCOHOL EN GEL 1LT",
    "ALCOHOL EN GEL X5L",
    "DESENGRASANTE P-25 X 1L",
    "QUITAMANCHAS X 1LT",
    "QUITA SARRO X1L",
    # Gastronomía
    "CAJA PIZZA GRANDE ECO VERDE X 100U (1)",
    "CAJA PIZZA GRIS CORRUGADA X 50U",
    "CAJA EMPANADA X 100U",
    "CAJA HAMBURGUEZA MICROCORRUGADA X100U",
    "CAJA LOMO GRANDE CARTON X 100 (1)",
    "VASO 110CC PLASTICO TRASLUCIDO X 100 (42)",
    "VASO 220 CC PLASTICO TRASLUCIDO X 50 (62)",
    "VASO 330 CC PLASTICO TRASLUCIDO X 50 (49)",
    "VASO 500ML TRASL X 50UNI",
    "VASO TERMICO 240CC X 25U. - WC - (40)",
    "VASO POLIPAPEL 12 ONZAS X 50U (1000)",
    "PLATO 17CM BLANCO X 50 U (20)",
    "PLATO 22CM BLANCO X 50 U (20)",
    "TENEDOR BLANCO X 100 (1)",
    "CUCHARA SOPERA X 100(1)",
    "CUCHILLO BLANCO X 100 (1)",
    "SERVILLETA SM 33X33 BLANCA",
    "SERVILLETA 18X18 X 1000",
    "SERVILLETAS 30X30 X 1000UNI",
    "BANDEJA DE CARTON N2",
    "BANDEJA DE CARTON N4",
    "BANDEJA 101 PP X 100 (12)",
    "POTE LISO 250CC 088 X 50U (900)",
    "VIANDERA 105 OVAL C/TAPA BISAGRA (200)",
    "SORBETE SUR ENSOBRADO X 1000 EN CAJA",
    "PORTA VASOS CAFE X 50 UNI",
    "AGITADOR DE CAFE MADERA IBERIA 11CM X 1500 U",
    # Bolsas / delivery
    "CAMISETA 40 X 50 ECO MUNDI POLIM. X PAQ (20)",
    "CAMISETA 45 X 60 MUNDI MAX X PAQ (20)",
    "CAMISETA 50 X 70 MUNDI MAX X PAQ (20)",
    "BOLSAS CONSORCIO 60X90 X 50 UNI",
    "BOLSAS CONSORCIO 60X90 X 10 UNI",
    "BOLSA KRAFT DELIVERY N°4 12.5 X 7 X 24 X 50 U (20)",
    "BOLSA KRAFT DELIVERY N°6 20 X 11 X 30 X 50 U (5)",
    "BOLSA PANADERIA KRAFT N 5 - X 100U.(20)",
    "BOLSA PPP 20 X 30 X 100 U(10)",
    "BOLSAS RESIDUOS 45X60 X 50 UNI",
    # Limpieza herramientas
    "TRAPO DE PISO MR TRAPO BLANCO",
    "TRAPO DE PISO BLANCO LA NACIONAL",
    "BALDE 10LTS",
    "BALDE C/ ESCURRIDOR HACENDOZA 9L",
    "ESCOBA DE PAJA",
    "ESCOBILLON ANDEN PLAST 60CM C/CABO",
    "MOPA MR TRAPO",
    "SECADOR HACENDOZA DOBLE GOMA 40CM",
    "CABO 1.20MTS",
    "VALERINA / PAÑO AMARILLO",
    "REJILLA TRICOLOR CHICA N36",
    # Papel / aluminio
    "PAPEL HIG ELEG/FELPITA 4X30 MTS",
    "PAPEL HIG JUMBO C/CH 8X300MTS ECO",
    "ROLLO COCINA ELEG 3X50PAÑOS",
    "ROLLO COCINA FELPITA X 200PAÑOS",
    "TOALLA INTERCALADA EXTRA BLANCO X 2000UNI",
    "ROLLO DE ALUMINIO X 1KG DPM/INCA (12)",
    # Marcas que el PdV nombra
    "ALA EN POLVO 800GRS",
    "AYUDIN CANASTAS P/INOD",
    "RAID CASA Y JARDIN",
    "BLOQUE HARPIC X 1UNI",
    "ZORRO POLVO MATIC 400GRS",
    "VIRULANA",
    "PATO BLOQUE ADH X 3 UNID",
    # Pileta (mix)
    "ALGUICIDA 1:60000 X1L",
    "CLORO P/PILETAS X10L",
    "PASTILLAS DE CLORO MULTIACCION X1KG",
}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def norm(s: str) -> str:
    s = nfc(s).upper()
    s = s.replace("º", "°").replace("Nº", "N°")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_price(raw: str) -> float | None:
    t = raw.strip().replace(" ", "").replace("$", "")
    if not t or t in {"-", "—", "–"}:
        return None
    if not re.fullmatch(r"\d+(?:[.,]\d+)?", t):
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".") if t.count(".") > 1 else t.replace(",", ".")
    else:
        if t.count(".") > 1:
            t = t.replace(".", "")
    try:
        v = float(t)
        return v if v > 0 else None
    except ValueError:
        return None


def parse_pdf() -> list[tuple[str, float]]:
    doc = pymupdf.open(PDF)
    lines: list[str] = []
    for page in doc:
        lines.extend(ln.strip() for ln in page.get_text().splitlines() if ln.strip())
    items: list[tuple[str, float]] = []
    i = 0
    skip_hdr = {"NOMBRE", "PRECIO B", "PRECIO"}
    while i < len(lines):
        name = nfc(lines[i]).strip()
        if name.upper() in skip_hdr:
            i += 1
            continue
        if i + 1 < len(lines):
            price = parse_price(lines[i + 1])
            if price is not None or (parse_price(lines[i + 1]) is None and re.fullmatch(r"0+(?:[.,]0+)?", lines[i + 1].strip())):
                if price is not None:
                    items.append((re.sub(r"\s+", " ", name), price))
                i += 2
                continue
        i += 1
    return items


def skip_row(nombre: str) -> bool:
    n = norm(nombre)
    if n in SKIP_NAMES:
        return True
    if n.startswith("S/N") or n.startswith("SN "):
        return True
    if "LOGISTICA" in n:
        return True
    return False


def unidades_por_bulto(nombre: str) -> int:
    n = nombre
    m = re.search(r"\((\d{1,4})\)\s*$", n)
    if m:
        v = int(m.group(1))
        if 1 < v <= 2000:
            return v
    m = re.search(r"X\s*(\d{2,5})\s*U", n, re.I)
    if m:
        v = int(m.group(1))
        if 2 <= v <= 5000:
            return v
    return 1


def umv_for(nombre: str, bulto: int) -> tuple[str, str]:
    """unidad_minima_de_venta es texto libre; umv_tipo solo admite unidad|display."""
    n = norm(nombre)
    umv_tipo = "unidad"
    if n.startswith("SET "):
        return "set", umv_tipo
    if any(k in n for k in ("VASO", "PLATO", "TENEDOR", "CUCHARA", "CUCHILLO", "SERVILLETA", "BANDEJA", "CAJA PIZZA", "CAJA EMPANADA", "CAJA HAMB", "CAJA LOMO")):
        return "caja", umv_tipo
    if "CAMISETA" in n or n.startswith("BOLSA"):
        return "paquete", umv_tipo
    if bulto > 1:
        return "paquete", umv_tipo
    return "unidad", umv_tipo


def detect_marca(nombre: str) -> str:
    n = norm(nombre)
    brands = [
        ("PSQUIMICA", "PSQ"),
        (" PSQ", "PSQ"),
        ("PSQ ", "PSQ"),
        ("ALA ", "Ala"),
        ("AYUDIN", "Ayudin"),
        ("RAID", "Raid"),
        ("HARPIC", "Harpic"),
        ("PATO ", "Pato"),
        ("ZORRO", "Zorro"),
        ("VIRULANA", "Virulana"),
        ("PLUSBELLE", "Plusbelle"),
        ("SEDAL", "Sedal"),
        ("MR TRAPO", "Mr Trapo"),
        ("HACENDOZA", "Hacendoza"),
        ("FELPITA", "Felpita"),
        ("ELEG", "Elegante"),
        ("IBERIA", "Iberia"),
        ("MUNDI MAX", "Mundi Max"),
        ("FRIOCLEAN", "PSQ"),
        ("SET FAB", "PSQ"),
        ("SET LAVANDINA", "PSQ"),
        ("SET PERFUMINA", "PSQ"),
        ("SET COMBO", "PSQ"),
    ]
    for key, brand in brands:
        if key in n:
            return brand
    if n.endswith(" PSQ") or " PSQ " in n or n.endswith("PSQ"):
        return "PSQ"
    return "PSQ"


def cats(nombre: str) -> tuple[str, str, str, str]:
    n = norm(nombre)
    if n.startswith("SET FAB") or n.startswith("SET LAV") or n.startswith("SET PERF") or n.startswith("SET COMBO"):
        return "Marca blanca", "Set de fabricación", "100 litros", "PSQ"
    if any(k in n for k in ("ANTI-HONGOS", "QUITAMANCHAS", "QUITASARRO", "QUITA SARRO", "LIMPIAVIDR", "LIMPIA TAPIZ", "MULTIUSO", "ELIMINADOR DE OLORES", "DESTAPA", "FRIOCLEAN", "DESENGRASANTE 500ML")):
        return "Limpieza", "Línea PSQ", "Gatillo / listo para usar", "PSQ"
    if any(k in n for k in ("JABON", "DETERGENTE", "LAVANDINA", "SUAVIZANTE", "PERFUMINA", "ALCOHOL EN GEL", "DESENGRASANTE")):
        return "Limpieza", "Líquidos", "Bidón 1 L / 5 L", "PSQ"
    if any(k in n for k in ("VASO", "PLATO", "TENEDOR", "CUCHARA", "CUCHILLO", "SORBETE", "AGITADOR", "PORTA VASOS")):
        return "Descartables", "Gastronomía", "Cubiertos y vasos", "Delivery"
    if any(k in n for k in ("CAJA PIZZA", "CAJA EMPANADA", "CAJA HAMB", "CAJA LOMO")):
        return "Descartables", "Gastronomía", "Cajas delivery", "Delivery"
    if any(k in n for k in ("BANDEJA", "POTE", "VIANDERA")):
        return "Descartables", "Gastronomía", "Envases", "Delivery"
    if "SERVILLETA" in n:
        return "Descartables", "Gastronomía", "Servilletas", "Papel"
    if "CAMISETA" in n:
        return "Bolsas", "Camiseta", "Paquete", "Mundi Max"
    if n.startswith("BOLSA") or n.startswith("BOLSAS"):
        if "KRAFT" in n or "DELIVERY" in n or "PANADER" in n:
            return "Bolsas", "Kraft / delivery", "Paquete", "Delivery"
        if "CONSORCIO" in n or "RESIDUO" in n:
            return "Bolsas", "Residuos", "Consorcio", "Hogar"
        return "Bolsas", "PPP", "Paquete", "Packaging"
    if any(k in n for k in ("TRAPO", "MOPA", "BALDE", "ESCOBA", "ESCOBILL", "SECADOR", "CABO", "VALERINA", "REJILLA")):
        return "Limpieza", "Herramientas", "Piso", "Hogar"
    if any(k in n for k in ("PAPEL HIG", "ROLLO COCINA", "TOALLA INTER", "ALUMINIO")):
        return "Papel", "Higiénico y cocina", "Institucional", "Gastronomía"
    if any(k in n for k in ("ALA ", "AYUDIN", "RAID", "HARPIC", "ZORRO", "VIRULANA", "PATO ")):
        return "Limpieza", "Marcas de góndola", "Terceros", "Supermercado"
    if any(k in n for k in ("ALGUICIDA", "CLORO", "BOYA", "SACAHOJAS", "PILETA")):
        return "Pileta", "Tratamiento de agua", "Cloro", "PSQ"
    return "Limpieza", "General", "Catálogo", "PSQ"


def rotation(nombre: str, marca: str) -> float:
    n = norm(nombre)
    if marca == "PSQ" and any(k in n for k in ("GATILLO", "500ML PSQ", "PSQUIMICA")):
        return 0.90
    if n.startswith("SET "):
        return 0.78
    if any(k in n for k in ("VASO", "CAJA PIZZA", "CAJA EMPANADA", "SERVILLETA", "CAMISETA", "LAVANDINA X", "DETERGENTE USO DIRECTO")):
        return 0.86
    if any(k in n for k in ("TRAPO", "BALDE", "PAPEL HIG", "ROLLO COCINA", "BOLSAS CONSORCIO")):
        return 0.74
    if marca in {"Ala", "Raid", "Ayudin", "Harpic", "Zorro"}:
        return 0.55
    if "PILETA" in n or "CLORO" in n or "ALGUICIDA" in n:
        return 0.48
    return 0.40


def stock_for(rot: float) -> int:
    if rot >= 0.8:
        return 260
    if rot >= 0.6:
        return 140
    return 50


def descripcion(nombre: str, marca: str, cat2: str, bulto: int, umv: str) -> str:
    core = nombre.strip()
    if core.isupper() or core[:3].isupper():
        core = core[0] + core[1:].lower()
        core = re.sub(r"\b(psq|psquimica)\b", lambda m: m.group(1).upper(), core, flags=re.I)
        core = re.sub(r"\b(l|lt|lts|ml)\b", lambda m: m.group(1).upper(), core, flags=re.I)
    extra = [f"marca {marca}"]
    if cat2:
        extra.append(cat2.lower())
    if bulto > 1:
        extra.append(f"{umv} x{bulto}")
    else:
        extra.append("venta por unidad")
    extra.append("lista B")
    text = f"{core}, {', '.join(extra)}."
    words = text.split()
    if len(words) > 25:
        text = " ".join(words[:24]).rstrip(",") + "."
    if len(words) < 10:
        text = text.rstrip(".") + ", catálogo PSQ Córdoba."
    return text


def aliases(code: str, nombre: str, marca: str, umv: str) -> str:
    n = re.sub(r"\s+", " ", nombre).strip()
    bits = [code, n, n.lower()]
    if marca:
        bits.append(marca)
        bits.append(f"{marca} {n.split()[0].lower()}")
    bits.append(umv)
    if umv in {"caja", "paquete"}:
        bits.extend(["caja", "paquete", "bulto"])
    if "GATILLO" in norm(n):
        bits.append("gatillo")
        bits.append("con gatillo")
    if re.search(r"X\s*5\s*L", norm(n)) or "X5L" in norm(n) or "5LTS" in norm(n):
        bits.extend(["bidón 5 litros", "bidon 5 litros", "x5"])
    if re.search(r"X\s*1\s*L", norm(n)) or "X1L" in norm(n) or "1LT" in norm(n) or "1 L" in norm(n):
        bits.extend(["litro", "1 litro", "x1"])
    if "SET FAB" in norm(n) or norm(n).startswith("SET "):
        bits.extend(["marca blanca", "set fabricacion", "kit 100 litros"])
    if "CAMISETA" in norm(n):
        bits.extend(["bolsa camiseta", "bolsas de supermercado"])
    if "CONSORCIO" in norm(n):
        bits.extend(["bolsa consorcio", "bolsas de consorcio"])
    seen: list[str] = []
    for b in bits:
        b = b.strip()
        if b and b not in seen:
            seen.append(b)
    return "|".join(seen[:8])


def make_row(idx: int, nombre: str, precio: float) -> dict:
    code = f"PSQ-{idx:04d}"
    marca = detect_marca(nombre)
    cat1, cat2, cat3, cat4 = cats(nombre)
    bulto = unidades_por_bulto(nombre)
    umv, umv_tipo = umv_for(nombre, bulto)
    rot = rotation(nombre, marca)
    return {
        "product_code": code,
        "nombre": nombre,
        "precio_lista_1": f"{round(precio, 2):.2f}",
        "stock": stock_for(rot),
        "unidades_por_bulto": bulto,
        "unidad_minima_de_venta": umv,
        "umv_tipo": umv_tipo,
        "categoria_1": cat1,
        "categoria_2": cat2,
        "categoria_3": cat3,
        "categoria_4": cat4,
        "aliases": aliases(code, nombre, marca, umv),
        "rotacion_index": f"{rot:.2f}",
        "mental_priority": f"{rot:.2f}",
        "descripcion": descripcion(nombre, marca, cat2, bulto, umv),
        "image_url": "",
        "en_catalogo": "true",
        "is_mock": "true",
        "fuente_hoja": "LISTA B",
    }


def main() -> int:
    parsed = parse_pdf()
    rows: list[dict] = []
    skipped: list[str] = []
    idx = 0
    for nombre, precio in parsed:
        if skip_row(nombre):
            skipped.append(f"omitido {nombre}")
            continue
        idx += 1
        rows.append(make_row(idx, nombre, precio))

    full_path = ROOT / "inputs" / "catalogo-completo.csv"
    with full_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PRODUCT_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"[*] universo con precio: {len(rows)} → {full_path}")

    include = {norm(x) for x in INCLUDE_NORM}
    demo = [p for p in rows if norm(p["nombre"]) in include]
    found = {norm(p["nombre"]) for p in demo}
    missing = sorted(include - found)
    if missing:
        print(f"[WARN] INCLUDE no hallados ({len(missing)}):")
        for m in missing:
            print(f"  - {m}")
    extra = len(demo)
    if not (80 <= extra <= 100):
        print(f"[WARN] recorte demo fuera de 80–100: {extra}")

    out_prod = OUT / "phase-01-productos.csv"
    with out_prod.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PRODUCT_FIELDS)
        w.writeheader()
        w.writerows(demo)

    listas_rows = []
    for lid, lname, mult in LISTAS:
        path = OUT / f"phase-01-lista-precios-{lid}.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["product_code", "precio_unidad", "is_mock"])
            w.writeheader()
            for p in demo:
                precio = round(float(p["precio_lista_1"]) * mult, 2)
                w.writerow({"product_code": p["product_code"], "precio_unidad": f"{precio:.2f}", "is_mock": "true"})
                listas_rows.append((lid, lname, mult, p["product_code"], precio))

    with (OUT / "phase-01-listas-precios.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lista_precios_id", "nombre", "multiplicador_sobre_lista_1", "product_code", "precio_unidad", "is_mock"])
        for lid, lname, mult, code, precio in listas_rows:
            w.writerow([lid, lname, f"{mult:.2f}", code, f"{precio:.2f}", "true"])

    c1 = Counter(p["categoria_1"] for p in demo)
    print(f"[*] productos demo={len(demo)}")
    print(f"[*] por categoria_1: {dict(c1)}")
    print(f"[*] omitidos={len(skipped)}")
    if demo:
        print(f"[*] sample: {demo[0]['product_code']} {demo[0]['nombre']} ${demo[0]['precio_lista_1']}")
    return 0 if 80 <= len(demo) <= 100 and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
