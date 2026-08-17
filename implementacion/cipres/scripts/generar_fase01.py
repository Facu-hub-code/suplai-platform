#!/usr/bin/env python3
"""Genera CSVs de Fase 1 (catálogo) para cipres desde el .xls de lista de precios."""
from __future__ import annotations

import csv
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XLS = ROOT / "inputs" / "cipres-listadodeprecios.xls"
OUT = ROOT / "outputs"

BRANDS = [
    "SAPHIRUS",
    "URBAN FRESH",
    "MR MUSCULO",
    "MR. MUSCULO",
    "LA ANONIMA",
    "CIPCLOR",
    "GLADE",
    "AROMANZA",
    "PLUSBELLE",
    "ALGABO",
    "VULCANO",
    "COLGATE",
    "LYSOFORM",
    "WOOLITE",
    "PANTENE",
    "REXONA",
    "AYUDIN",
    "HAR PIC",
    "HARPIC",
    "POETT",
    "NIVEA",
    "DOVE",
    "RAID",
    "SKIP",
    "CIF",
    "ECHO",
    "SEDAL",
    "ELVIVE",
    "AGREE",
    "BLEM",
    "ORAL B",
    "ORAL-B",
    "PHILCO",
    "ZUIPY",
    "VIRULANA",
    "JOHNSON",
    "PANTENE",
    "HEAD & SHOULDERS",
    "MAPA",
    "PROCENEX",
    "AYUDIN",
    "POETT",
    "PLAC",
    "FASTIX",
    "FUMIXAN",
]

LEADER_BRANDS = {
    "SAPHIRUS",
    "GLADE",
    "CIF",
    "AROMANZA",
    "URBAN FRESH",
    "ALGABO",
    "PLUSBELLE",
    "COLGATE",
    "CIPCLOR",
    "VULCANO",
    "LYSOFORM",
    "AYUDIN",
    "RAID",
    "SKIP",
    "POETT",
    "WOOLITE",
}

# (keywords in name, cat1, cat2, cat3, cat4, noun for description)
# Más específico primero: insecticidas/piletas antes que "AEROSOL".
TAXONOMY = [
    (["INSECTICIDA", "RAID", "BAYGON", "FUMIXAN", "MATA MOSCA", "CUCARACHA", "MOSQUIT"], "Insecticidas", "Insecticidas", "Aerosoles insecticidas", "Insecticidas", "Insecticida"),
    (["CLORO", "PILETA", "PISCINA", "BARREFONDO", "ROBOT LIMPIADOR", "BOMBA PISCINA", "ZUIPY", "VULCANO"], "Piletas y mantenimiento", "Piletas", "Químicos y equipos de pileta", "Piletas", "Producto para pileta"),
    (["SAHUMERIO", "INCIENSO", "PALO SANTO", "CONITOS"], "Aromatización", "Sahumerios", "Sahumerios", "Sahumerios", "Sahumerio"),
    (["DIFUSOR", "DIFFUSER", "REED"], "Aromatización", "Difusores", "Difusores de ambiente", "Difusores", "Difusor de ambiente"),
    (["ESENCIA PARA HORNITO", "ESENCIA ", "ACEITE ESENCIAL"], "Aromatización", "Esencias", "Esencias para hornito", "Esencias", "Esencia aromática"),
    (["ANTIHUMEDAD", "AROMATIZADOR", "CANASTA LIQUIDA", "CANASTA SOLIDA", "DISCO GEL", "BLOQUE PARA MOCHILA"], "Aromatización", "Aromatizantes", "Inodoro y humedad", "Aromatizantes", "Aromatizante"),
    (["AEROSOL", "AROMATIZANTE", "AMBIENTADOR", "GLADE", "POETT", "SAPHIRUS"], "Aromatización", "Aromatizantes", "Aerosoles de ambiente", "Aromatizantes", "Aromatizante de ambientes"),
    (["PERFUME"], "Aromatización", "Perfumes de ambiente", "Perfumes de ambiente", "Perfumes", "Perfume de ambiente"),
    (["ENJUAGUE BUCAL", "ENJUAGUE"], "Cuidado personal", "Higiene bucal", "Enjuague bucal", "Higiene bucal", "Enjuague bucal"),
    (["DISCO DE ALGODON", "ALGODON", "HISOPO"], "Cuidado personal", "Higiene", "Algodón e hisopos", "Higiene", "Algodón"),
    (["SHAMPOO", "SHAMPO"], "Cuidado personal", "Cabello", "Shampoo", "Shampoo", "Shampoo"),
    (["ACONDICIONADOR", "ACOND."], "Cuidado personal", "Cabello", "Acondicionador", "Acondicionador", "Acondicionador"),
    (["DESODORANTE", "DESOD.", "ROLLON", "ROLL-ON", "ANTITRANSPIRANTE"], "Cuidado personal", "Desodorantes", "Desodorantes", "Desodorantes", "Desodorante"),
    (["JABON LIQUIDO", "JABÓN LÍQUIDO", "JABON"], "Cuidado personal", "Jabones", "Jabones", "Jabones", "Jabón"),
    (["CREMA", "NIVEA", "LOCION", "LOCION"], "Cuidado personal", "Cremas y lociones", "Cremas", "Cremas", "Crema"),
    (["PASTA DENTAL", "DENTIFRICO", "COLGATE", "ORAL B", "CEPILLO DE DIENTES"], "Cuidado personal", "Higiene bucal", "Higiene bucal", "Higiene bucal", "Producto de higiene bucal"),
    (["TOALLA FEMENINA", "PROTECTOR DIARIO", "TAMPON"], "Cuidado personal", "Higiene femenina", "Higiene femenina", "Higiene femenina", "Producto de higiene femenina"),
    (["PAÑAL", "TOALLITA HUMEDA", "TOALLITAS"], "Cuidado personal", "Bebés", "Higiene bebé", "Bebés", "Producto de higiene para bebé"),
    (["DETERG", "LAVARROPAS", "SKIP", "WOOLITE", "SUAVIZANTE", "JABON EN POLVO"], "Lavandería", "Detergentes", "Detergentes y suavizantes", "Lavandería", "Detergente para ropa"),
    (["LAVAVAJILLA", "DETER. LAVAVAJILLAS", "CIF CREMA", "CIF LIQUIDO"], "Limpieza del hogar", "Cocina", "Lavavajillas", "Cocina", "Lavavajillas"),
    (["LAVANDINA", "CIPCLOR", "AYUDIN", "LYSOFORM", "DESINFECTANTE"], "Limpieza del hogar", "Desinfectantes", "Lavandinas y desinfectantes", "Desinfectantes", "Desinfectante"),
    (["LIMPIADOR", "MR MUSCULO", "PROCENEX", "CIF ", "HARPIC", "INODORO", "SANITARIO"], "Limpieza del hogar", "Limpiadores", "Limpiadores de superficies", "Limpiadores", "Limpiador"),
    (["LUSTRAMUEBLE", "BLEM", "CERA ", "PISO"], "Limpieza del hogar", "Pisos y muebles", "Lustramuebles y pisos", "Pisos", "Producto para pisos o muebles"),
    (["CESTO", "CANASTO", "ORGANIZADOR", "DISPENSER", "DISPENS"], "Bazar y organización", "Organizadores", "Cestos y organizadores", "Bazar", "Organizador"),
    (["GUANTE", "VIRULANA", "ESCOBA", "SECADOR", "REJILLA", "ESPONJA", "ESPONJJA", "TRAPO", "BALDE", "PALO DE"], "Limpieza del hogar", "Accesorios de limpieza", "Utensilios", "Utensilios", "Utensilio de limpieza"),
    (["BOLSA", "DESCARTABLE", "FILM", "ROLLO DE COCINA", "SERVILLETA"], "Descartables", "Descartables", "Bolsas y films", "Descartables", "Descartable"),
    (["ENCENDEDOR", "VELA", "FASTIX", "ADHESIVO", "SILICONA"], "Ferretería y mantenimiento", "Mantenimiento", "Adhesivos y ferretería", "Ferretería", "Artículo de mantenimiento"),
]

DEFAULT_CAT = ("Limpieza e insumos", "General", "General", "General", "Producto de limpieza")

IMAGES = {
    "Aromatización": "https://images.unsplash.com/photo-1608571423902-eed4a5ad8108?w=400",
    "Cuidado personal": "https://images.unsplash.com/photo-1556228720-195a609e8dba?w=400",
    "Lavandería": "https://images.unsplash.com/photo-1582735689369-4fe89db7114c?w=400",
    "Limpieza del hogar": "https://images.unsplash.com/photo-1563453392212-326f5e854473?w=400",
    "Insecticidas": "https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=400",
    "Piletas y mantenimiento": "https://images.unsplash.com/photo-1576013551627-0cc20b96c2a7?w=400",
    "Bazar y organización": "https://images.unsplash.com/photo-1556912173-46c336c7fd55?w=400",
    "Descartables": "https://images.unsplash.com/photo-1610484826967-09c5720778c7?w=400",
    "Ferretería y mantenimiento": "https://images.unsplash.com/photo-1581244277943-fe4a9c777189?w=400",
    "Limpieza e insumos": "https://images.unsplash.com/photo-1563453392212-326f5e854473?w=400",
}

REJECT_NAMES = re.compile(
    r"^(ENVIO|ENVÍO|FLETE|AJUSTE|PRODUCTOS VARIOS|PRODUCTOS VARIOS - AJUSTE)$",
    re.I,
)

PACK_RE = re.compile(
    r"""(?:
        \(\s*B\s*/\s*(\d{1,3})\s*\) |
        \bPACK\s*(?:DE\s*)?(\d{1,3})\b |
        \bX\s*(\d{1,3})\s*(?:U(?:NI(?:DADES?|D)?)?|UNID)\b |
        \b(\d{1,3})\s*U(?:NI(?:DADES?)?)?\s*$
    )""",
    re.I | re.VERBOSE,
)

SIZE_RE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(LTS?|LITROS?|ML|CC|GRS?|KG|CM|MM)\b",
    re.I,
)


def fold(s: str) -> str:
    n = unicodedata.normalize("NFKD", s)
    return "".join(c for c in n if not unicodedata.combining(c)).upper()


def clean_name(raw: str) -> str:
    n = re.sub(r"\s+", " ", str(raw or "").strip())
    n = re.sub(r"\s*[-–.]+$", "", n).strip()
    return n


def detect_brand(name_up: str) -> str:
    for b in BRANDS:
        if b in name_up:
            return b.title() if b not in {"CIF", "3M"} else b
    return ""


def categorize(name_up: str) -> tuple[str, str, str, str, str]:
    for keys, c1, c2, c3, c4, noun in TAXONOMY:
        if any(k in name_up for k in keys):
            return c1, c2, c3, c4, noun
    return DEFAULT_CAT


def unidades_por_bulto(name: str) -> int:
    m = PACK_RE.search(name)
    if not m:
        return 1
    for g in m.groups():
        if g:
            n = int(g)
            return n if 1 < n <= 48 else 1
    return 1


def extract_size(name: str) -> str:
    m = SIZE_RE.search(name)
    if not m:
        return ""
    qty, unit = m.group(1).replace(",", "."), m.group(2).lower()
    unit_map = {
        "lt": "L",
        "lts": "L",
        "litro": "L",
        "litros": "L",
        "ml": "ml",
        "cc": "cc",
        "gr": "g",
        "grs": "g",
        "g": "g",
        "kg": "kg",
        "cm": "cm",
        "mm": "mm",
    }
    u = unit_map.get(unit, unit)
    return f"{qty} {u}"


def aliases(nombre: str, brand: str, code: str) -> str:
    parts = [nombre]
    if brand:
        parts.append(brand)
        parts.append(f"{brand} {nombre.split()[0]}")
    compact = re.sub(r"[^A-Za-z0-9ÁÉÍÓÚÑáéíóúñ ]+", " ", nombre)
    compact = re.sub(r"\s+", " ", compact).strip()
    if compact and compact != nombre:
        parts.append(compact)
    words = nombre.split()
    if len(words) >= 2:
        parts.append(" ".join(words[:2]))
    parts.append(code)
    seen = set()
    out = []
    for p in parts:
        k = fold(p)
        if k and k not in seen:
            seen.add(k)
            out.append(p)
    return "|".join(out[:6])


def word_count(s: str) -> int:
    return len(s.split())


def descripcion(noun: str, nombre: str, brand: str, size: str, bulto: int) -> str:
    bits = [f"{noun} {nombre}"]
    if brand and fold(brand) not in fold(nombre):
        bits.append(f"marca {brand}")
    elif brand:
        bits.append(f"marca {brand}")
    if size:
        bits.append(size)
    if bulto > 1:
        bits.append(f"x{bulto} unidades por bulto")
    text = ", ".join(bits) + "."
    # recortar a 25 palabras
    words = text.split()
    if len(words) > 25:
        text = " ".join(words[:24]).rstrip(",.") + "."
    # rellenar si quedó corto
    if word_count(text) < 10:
        extra = "línea Ciprés Limpieza, Villa Constitución"
        text = text.rstrip(".") + ", " + extra + "."
    if word_count(text) < 10:
        text = text.rstrip(".") + ", venta por unidad."
    return text


def load_xls(path: Path) -> list[tuple]:
    sys.path.insert(0, "/tmp/cipres-xlrd")
    import xlrd  # type: ignore

    sh = xlrd.open_workbook(str(path)).sheet_by_index(0)
    rows = []
    for r in range(1, sh.nrows):
        rows.append(
            (
                str(sh.cell_value(r, 0) or ""),
                sh.cell_value(r, 1) or 0,
                sh.cell_value(r, 2) or 0,
                sh.cell_value(r, 3) or 0,
            )
        )
    return rows


def main() -> int:
    if not XLS.exists():
        print(f"[FAIL] no está {XLS}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    raw = load_xls(XLS)

    seen_names: Counter[str] = Counter()
    accepted = []
    rejected = []

    for nombre_raw, p2, p3, p5 in raw:
        nombre = clean_name(nombre_raw)
        p2f, p3f, p5f = float(p2 or 0), float(p3 or 0), float(p5 or 0)
        reason = ""
        if not nombre:
            reason = "nombre vacío"
        elif REJECT_NAMES.match(nombre) or "AJUSTE" in fold(nombre):
            reason = "no es producto vendible (envío/ajuste)"
        elif p2f <= 0:
            reason = "precio lista 1 (precioventa2) <= 0"
        if reason:
            rejected.append({"nombre": nombre or nombre_raw, "motivo": reason, "precioventa2": p2f})
            continue
        seen_names[nombre] += 1
        display = nombre if seen_names[nombre] == 1 else f"{nombre} ({seen_names[nombre]})"
        accepted.append((display, p2f, p3f if p3f > 0 else p2f, p5f if p5f > 0 else p2f))

    # rotación: líderes primero
    scored = []
    for i, (nombre, p2, p3, p5) in enumerate(accepted):
        up = fold(nombre)
        brand = detect_brand(up)
        leader = fold(brand) in {fold(b) for b in LEADER_BRANDS} or any(
            fold(b) in up for b in LEADER_BRANDS
        )
        scored.append((0 if leader else 1, i, nombre, p2, p3, p5, brand))
    scored.sort()

    n = len(scored)
    cut = max(1, int(n * 0.20))
    products = []
    for rank, (_g, _i, nombre, p2, p3, p5, brand) in enumerate(scored):
        code = f"CIP-{rank + 1:04d}"
        up = fold(nombre)
        c1, c2, c3, c4, noun = categorize(up)
        bulto = unidades_por_bulto(nombre)
        size = extract_size(nombre)
        if rank < cut:
            rot = round(0.95 - (rank / cut) * 0.20, 4)
            prio = round(1.0 - (rank / cut) * 0.50, 4)
        else:
            span = max(1, n - cut)
            rot = round(0.70 - ((rank - cut) / span) * 0.60, 4)
            prio = round(0.30 - ((rank - cut) / span) * 0.30, 4)
        rot = max(0.10, min(0.95, rot))
        prio = max(0.0, min(1.0, prio))
        stock = int(10 + rot * 490)
        products.append(
            {
                "product_code": code,
                "nombre": nombre,
                "precio_lista_1": f"{p2:.2f}",
                "stock": stock,
                "unidades_por_bulto": bulto,
                "unidad_minima_de_venta": "unidad",
                "umv_tipo": "unidad",
                "categoria_1": c1,
                "categoria_2": c2,
                "categoria_3": c3,
                "categoria_4": brand or c4,
                "aliases": aliases(nombre, brand, code),
                "rotacion_index": f"{rot:.4f}",
                "mental_priority": f"{prio:.4f}",
                "descripcion": descripcion(noun, nombre, brand, size, bulto),
                "image_url": IMAGES.get(c1, IMAGES["Limpieza e insumos"]),
                "en_catalogo": "true",
                "is_mock": "true",
                "fuente_hoja": "cipres",
                "_p2": p2,
                "_p3": p3,
                "_p5": p5,
                "_brand": brand,
            }
        )

    prod_fields = [
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
    with (OUT / "phase-01-productos.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=prod_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(products)

    for lid, key, fname in (
        (1, "_p2", "phase-01-lista-precios-1.csv"),
        (2, "_p3", "phase-01-lista-precios-2.csv"),
        (3, "_p5", "phase-01-lista-precios-3.csv"),
    ):
        with (OUT / fname).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["product_code", "precio_unidad", "is_mock"])
            w.writeheader()
            for p in products:
                w.writerow(
                    {
                        "product_code": p["product_code"],
                        "precio_unidad": f"{p[key]:.2f}",
                        "is_mock": "true",
                    }
                )

    with (OUT / "phase-01-listas-precios.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["lista_precios_id", "nombre", "descripcion", "origen_excel", "is_mock"],
        )
        w.writeheader()
        w.writerows(
            [
                {
                    "lista_precios_id": 1,
                    "nombre": "Mayorista",
                    "descripcion": "Lista mayorista / revendedores (precioventa2)",
                    "origen_excel": "precioventa2",
                    "is_mock": "true",
                },
                {
                    "lista_precios_id": 2,
                    "nombre": "Intermedia",
                    "descripcion": "Lista intermedia (precioventa3)",
                    "origen_excel": "precioventa3",
                    "is_mock": "true",
                },
                {
                    "lista_precios_id": 3,
                    "nombre": "Público",
                    "descripcion": "Lista público / mostrador (precioventa5)",
                    "origen_excel": "precioventa5",
                    "is_mock": "true",
                },
            ]
        )

    with (OUT / "phase-01-rechazados.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["nombre", "motivo", "precioventa2"])
        w.writeheader()
        w.writerows(rejected)

    cats = Counter(p["categoria_1"] for p in products)
    brands = Counter(p["_brand"] or "(sin marca)" for p in products)
    print(f"aceptados={len(products)} rechazados={len(rejected)}")
    print("categorias:", dict(cats))
    print("top marcas:", brands.most_common(8))
    print("sku unico", len({p['product_code'] for p in products}) == len(products))
    print("precio>0", all(p["_p2"] > 0 for p in products))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
