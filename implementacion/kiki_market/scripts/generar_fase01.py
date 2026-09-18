#!/usr/bin/env python3
"""Fase 1 kiki_market: catálogo completo desde Tienda Nube.

schema_name = kiki_market.
Precio lista única = Precio Tienda Nube × 0.60 (40% menos).
"""
from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INP = ROOT / "inputs" / "tiendanube-catalogo.csv"
OUT = ROOT / "outputs"
FULL = ROOT / "inputs" / "catalogo-completo.csv"
PRECIO_MULT = 0.60
FUENTE = "tiendanube"

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
    "marca",
    "precio_tiendanube",
    "barcode",
]

PRICE_FIELDS = [
    "lista_precios_id",
    "nombre",
    "multiplicador_sobre_lista_1",
    "product_code",
    "precio_unidad",
    "is_mock",
]

DIET_ALIASES = {
    "sin gluten": "sin tacc|sin gluten|sin t.a.c.c.",
    "sin tacc": "sin tacc|sin gluten",
    "vegano": "vegano|vegana|plant based",
    "sin sal": "sin sal|bajo en sodio",
    "organico": "organico|orgánico",
    "keto": "keto|cetogenico",
}

TIPO_NOUN = [
    (r"\bprote[ií]na", "Proteína"),
    (r"\bcol[aá]geno", "Colágeno"),
    (r"\bcreatina", "Creatina"),
    (r"\bomega\s*3", "Suplemento de omega 3"),
    (r"\bprobi[oó]tic", "Probiótico"),
    (r"\bmagnesio", "Suplemento de magnesio"),
    (r"\bcalcio", "Suplemento de calcio"),
    (r"\bmultivitam", "Multivitamínico"),
    (r"\bvitamina", "Vitamina"),
    (r"\bjab[oó]n", "Jabón"),
    (r"\bgalletit", "Galletitas"),
    (r"\bcereal|\bcopos|\baritos|\bbocaditos", "Cereal"),
    (r"\baceite", "Aceite"),
    (r"\bvinagre", "Vinagre"),
    (r"\bendulz|\bestevia|\bhileret", "Endulzante"),
    (r"\bcaf[eé]", "Café"),
    (r"\bt[eé]\b|\binfusi[oó]n", "Infusión"),
    (r"\byerba", "Yerba mate"),
    (r"\bsemilla", "Semillas"),
    (r"\bharina", "Harina"),
    (r"\bsalsa|\baderezo|\btabasco", "Aderezo"),
    (r"\bpasta dental|\bcepillo|\benjuague", "Producto de higiene bucal"),
    (r"\bshampoo|\bachamp[uú]", "Shampoo"),
    (r"\bcrema", "Crema"),
    (r"\bc[aá]psula|\bcomprimido|\bgomita", "Suplemento"),
]


def slug_to_name(slug: str) -> str:
    s = re.sub(r"-[a-z0-9]{5}$", "", slug or "")
    s = s.replace("-", " ").strip()
    return s.title() if s else "Producto Kiki"


def parse_price(s: str | None) -> float | None:
    if not s:
        return None
    t = str(s).strip().replace(" ", "")
    if not t:
        return None
    if t.count(",") == 1 and t.count(".") == 0:
        t = t.replace(",", ".")
    elif t.count(",") >= 1 and t.count(".") == 1:
        t = t.replace(",", "")
    elif t.count(".") >= 1 and t.count(",") == 1:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def parse_stock(s: str | None) -> int:
    if not s:
        return 0
    t = str(s).strip().replace(" ", "").replace(",", ".")
    try:
        n = int(float(t))
        return max(n, 0)
    except ValueError:
        return 0


def norm_code(sku: str, url_id: str) -> str:
    s = (sku or "").strip()
    if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        s = s[:-2]
    s = re.sub(r"\s+", "-", s)
    if not s:
        s = (url_id or "sku").strip()
    return s[:80]


def fold(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


INFER_CAT = [
    (r"\b(te negro|te manzanilla|te verde|saquitos|infusi)", ["Alimentos y Bebidas", "Infusiones", "", ""]),
    (r"\b(cafe|juan valdez)", ["Alimentos y Bebidas", "Café", "", ""]),
    (r"\b(aceite|oliva|aceto|vinagre)", ["Alimentos y Bebidas", "Aceites y Vinagres", "", ""]),
    (r"\b(salsa|tabasco|aderezo|pimenton|azafran)", ["Alimentos y Bebidas", "Salsas y Condimentos", "", ""]),
    (r"\b(fideo|harina|gallet|cereal|copos)", ["Alimentos y Bebidas", "Almacén", "", ""]),
    (r"\b(edulcor|hileret|endulz)", ["Alimentos y Bebidas", "Endulzantes", "", ""]),
    (r"\b(omega|magnesio|calcio|vitamina|ashwagandha|probiot|creatina|colostro|resveratrol|calostro)", ["Suplementos", "Nutricionales", "", ""]),
    (r"\b(proteina|amino|bcaa)", ["Suplementos", "Deportivos", "Proteina", ""]),
    (r"\b(jabon|pasta dental|shampoo|bucal)", ["Belleza y Cuidado Personal", "Higiene Personal", "", ""]),
]


def infer_cats_from_name(nombre: str) -> list[str]:
    u = fold(nombre)
    for pat, cats in INFER_CAT:
        if re.search(pat, u):
            return list(cats)
    return ["Alimentos y Bebidas", "", "", ""]


def infer_marca(nombre: str, marca: str) -> str:
    if marca:
        return marca
    u = fold(nombre)
    hints = [
        ("vitamin way", "Vitamin Way"),
        ("natufarma", "Natufarma"),
        ("geonat", "Geonat"),
        ("saint gottard", "Saint Gottard"),
        ("sri sri", "Sri Sri Tattva"),
        ("colabella", "Colabella"),
    ]
    for needle, label in hints:
        if needle in u:
            return label
    return ""


def parse_cats(raw: str) -> tuple[list[str], list[str]]:
    trees = [t.strip() for t in (raw or "").split(",") if t.strip()]
    scored: list[tuple[int, list[str]]] = []
    diet: list[str] = []
    for t in trees:
        segs = [s.strip() for s in t.split(">") if s.strip()]
        if not segs:
            continue
        root = segs[0]
        score = len(segs)
        if root in ("Alimentos y Bebidas", "Suplementos", "Belleza y Cuidado Personal"):
            score += 10
        elif root == "Tu dieta":
            score += 1
            diet.extend(segs[1:] or segs)
        elif root == "Marcas":
            score -= 4
        scored.append((score, segs))
    scored.sort(key=lambda x: (-x[0], -len(x[1])))
    best = scored[0][1] if scored else ["General"]
    while len(best) < 4:
        best.append("")
    return best[:4], diet


def unidades_por_bulto(nombre: str) -> int:
    u = fold(nombre)
    if "tripack" in u:
        return 3
    m = re.search(r"(?:pack\s*x\s*|b/\s*)(\d+)\b", u)
    if m:
        n = int(m.group(1))
        if 2 <= n <= 48:
            return n
    return 1


def extraer_formato(nombre: str) -> str:
    m = re.search(
        r"(\d+(?:[.,]\d+)?\s*(?:kg|grs?|g|ml|cc|l|lts?|c[aá]psulas?|comprimidos?|gomitas?|unidades?))",
        nombre,
        re.I,
    )
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def tipo_de(nombre: str, cat2: str, cat3: str) -> str:
    u = fold(nombre)
    for pat, noun in TIPO_NOUN:
        if re.search(pat, u):
            return noun
    for cand in (cat3, cat2):
        if cand:
            return cand
    return "Producto"


def limpiar_nombre_sin_marca(nombre: str, marca: str) -> str:
    n = nombre.strip()
    if marca:
        n = re.sub(re.escape(marca), "", n, flags=re.I).strip(" -–,")
    n = re.sub(r"\s+", " ", n)
    return n


def word_count(s: str) -> int:
    return len([w for w in re.split(r"\s+", s.strip()) if w])


def descripcion_de(nombre: str, marca: str, cat1: str, cat2: str, formato: str, bulto: int) -> str:
    tipo = tipo_de(nombre, cat2, "")
    core = re.sub(r"\s+", " ", nombre).strip(" .")
    parts = [core]
    if marca and fold(marca) not in fold(core):
        parts.append(f"marca {marca}")
    if formato and fold(formato) not in fold(core):
        parts.append(formato)
    if bulto > 1 and f"x{bulto}" not in fold(core) and "tripack" not in fold(core):
        parts.append(f"x{bulto} unidades")
    extra = cat2 or cat1
    blob = fold(" ".join(parts))
    if extra and extra not in ("General",) and fold(extra) not in blob:
        parts.append(extra.lower())
    text = ", ".join(p for p in parts if p).strip()
    if not text.endswith("."):
        text += "."
    text = text[0].upper() + text[1:]
    if word_count(text) < 10:
        filler = tipo if tipo and fold(tipo) not in fold(text) else extra or "suplemento alimenticio"
        text = text[:-1] + f", {str(filler).lower()}."
    if word_count(text) < 10:
        text = text[:-1] + ", presentación individual."
    if word_count(text) < 10:
        text = text[:-1] + ", marca Kiki."
    if word_count(text) > 25:
        short = [tipo or core.split()[0]]
        if marca:
            short.append(f"marca {marca}")
        if formato:
            short.append(formato)
        if extra:
            short.append(extra.lower())
        text = ", ".join(short) + "."
        text = text[0].upper() + text[1:]
    return text


def aliases_de(nombre: str, marca: str, code: str, diet: list[str], formato: str) -> str:
    bits = [nombre]
    if marca:
        bits.append(marca)
        bits.append(f"{marca} {limpiar_nombre_sin_marca(nombre, marca)}")
    bits.append(code)
    if formato:
        bits.append(formato)
    for d in diet:
        fd = fold(d)
        for key, extra in DIET_ALIASES.items():
            if key in fd:
                bits.extend(extra.split("|"))
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for b in bits:
        t = re.sub(r"\s+", " ", (b or "").strip())
        if not t:
            continue
        k = fold(t)
        if k in seen or len(t) < 2:
            continue
        seen.add(k)
        out.append(t)
    return "|".join(out[:12])


def rotacion_de(marca: str, brand_counts: Counter[str], max_count: int) -> float:
    m = (marca or "").strip() or "(sin marca)"
    n = brand_counts[m]
    leaders = {"Vitamin Way": 0.90, "Geonat": 0.84, "Sri Sri Tattva": 0.80, "Saint Gottard": 0.76}
    if m in leaders:
        return leaders[m]
    if max_count <= 1:
        return 0.45
    ratio = n / max_count
    return round(0.18 + 0.55 * ratio, 3)


def load_rows() -> list[dict[str, str]]:
    with INP.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def main() -> int:
    rows = load_rows()
    brand_counts: Counter[str] = Counter()
    prepared: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    skipped_price = 0
    skipped_dup = 0

    for r in rows:
        precio_tn = parse_price(r.get("Precio"))
        if precio_tn is None or precio_tn <= 0:
            skipped_price += 1
            continue
        url_id = (r.get("Identificador de URL") or "").strip()
        sku = (r.get("SKU") or "").strip()
        code = norm_code(sku, url_id)
        if code in seen_codes:
            skipped_dup += 1
            continue
        seen_codes.add(code)
        nombre = (r.get("Nombre") or "").strip() or slug_to_name(url_id)
        marca = infer_marca(nombre, (r.get("Marca") or "").strip())
        brand_counts[marca or "(sin marca)"] += 1
        cats, diet = parse_cats(r.get("Categorías") or "")
        if cats[0] in ("General", "Marcas", "Tu dieta", ""):
            cats = infer_cats_from_name(nombre)
        bulto = unidades_por_bulto(nombre)
        formato = extraer_formato(nombre)
        precio = round(precio_tn * PRECIO_MULT, 2)
        prepared.append(
            {
                "product_code": code,
                "nombre": nombre,
                "precio_tiendanube": f"{precio_tn:.2f}",
                "precio_lista_1": f"{precio:.2f}",
                "stock": str(parse_stock(r.get("Stock (Ventas en Villa Carlos Paz)"))),
                "unidades_por_bulto": str(bulto),
                "unidad_minima_de_venta": "unidad",
                "umv_tipo": "unidad",
                "categoria_1": cats[0],
                "categoria_2": cats[1],
                "categoria_3": cats[2],
                "categoria_4": cats[3],
                "marca": marca,
                "barcode": (r.get("Código de barras") or "").strip(),
                "fuente_hoja": FUENTE,
                "en_catalogo": "true",
                "is_mock": "false",
                "image_url": "",
                "_diet": "|".join(diet),
                "_formato": formato,
            }
        )

    max_count = max(brand_counts.values()) if brand_counts else 1
    marca_lider, n_lider = brand_counts.most_common(1)[0]
    products: list[dict[str, str]] = []
    for p in prepared:
        marca = p["marca"]
        rot = rotacion_de(marca, brand_counts, max_count)
        diet = [d for d in (p.pop("_diet") or "").split("|") if d]
        formato = p.pop("_formato")
        p["rotacion_index"] = f"{rot:.3f}"
        p["mental_priority"] = f"{rot:.3f}"
        p["descripcion"] = descripcion_de(
            p["nombre"], marca, p["categoria_1"], p["categoria_2"], formato, int(p["unidades_por_bulto"])
        )
        p["aliases"] = aliases_de(p["nombre"], marca, p["product_code"], diet, formato)
        products.append(p)

    OUT.mkdir(exist_ok=True)
    FULL.parent.mkdir(exist_ok=True)

    with FULL.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PRODUCT_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(products)

    with (OUT / "phase-01-productos.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PRODUCT_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(products)

    with (OUT / "phase-01-lista-precios-1.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PRICE_FIELDS)
        w.writeheader()
        for p in products:
            w.writerow(
                {
                    "lista_precios_id": 1,
                    "nombre": "Lista única",
                    "multiplicador_sobre_lista_1": 1.00,
                    "product_code": p["product_code"],
                    "precio_unidad": p["precio_lista_1"],
                    "is_mock": "false",
                }
            )

    precios = [float(p["precio_lista_1"]) for p in products]
    print(f"[*] schema_name=kiki_market filas={len(products)}")
    print(f"[*] omitidos precio<=0={skipped_price} duplicados_sku={skipped_dup}")
    print(f"[*] marca_lider={marca_lider} skus={n_lider}")
    print(f"[*] precio lista única min={min(precios):.2f} p50={sorted(precios)[len(precios)//2]:.2f} max={max(precios):.2f}")
    print(f"[*] cat1={Counter(p['categoria_1'] for p in products).most_common(6)}")
    print("[SUCCESS] outputs/phase-01-productos.csv + phase-01-lista-precios-1.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
