#!/usr/bin/env python3
"""Fase 1 — extrae LISTA DE PRECIOS BLANCA AGOSTO 2026.pdf → CSVs dinamic.

schema_name = dinamic. Un SKU por código de presentación. Precio = lista blanca
(fraccionado: $/litro o $/kg según columna; pileta/envases: precio del envase).
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pymupdf

SCHEMA = "dinamic"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PDF = ROOT / "inputs" / "LISTA DE PRECIOS BLANCA AGOSTO 2026.pdf"
OUT = ROOT / "outputs"
RAW = ROOT / "inputs" / "catalogo-raw.json"

PRICE_TOKEN = re.compile(r"^\$?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)$")
DASH = {"-", "—", "–"}
HEADER_HINT = re.compile(
    r"^(C |COD |MES |DIVISI[OÓ]N|DIVISION|LINEA |LIMPIADORES |NOVEDADES|LISTO$)",
    re.I,
)


def parse_price(tok: str) -> float | None:
    t = tok.replace("$", "").strip()
    if t in DASH or t == "":
        return None
    t = t.replace(".", "").replace(",", ".")
    try:
        v = float(t)
        return v if v > 0 else None
    except ValueError:
        return None


def is_price_token(tok: str) -> bool:
    t = tok.replace("$", "").strip()
    if t in DASH:
        return True
    return bool(PRICE_TOKEN.match(t))


def pdf_lines(page) -> list[str]:
    words = sorted(page.get_text("words"), key=lambda w: (round(w[1], 0), w[0]))
    lines: list[tuple[float, list]] = []
    cur_y = None
    cur: list = []
    for w in words:
        y = round(w[1] / 2.5) * 2.5
        if cur_y is None or abs(y - cur_y) > 3.5:
            if cur:
                lines.append((cur_y, sorted(cur, key=lambda x: x[0])))
            cur_y = y
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append((cur_y, sorted(cur, key=lambda x: x[0])))
    return [" ".join(w[4] for w in ws) for _, ws in lines]


def split_row(text: str) -> tuple[list[str], str, list[float], str]:
    """codes, dilucion, prices, name."""
    toks = text.replace("$", " $ ").split()
    toks = [t for t in toks if t != "$"]
    codes: list[str] = []
    i = 0
    while i < len(toks) and re.fullmatch(r"\d{1,4}", toks[i]) and len(codes) < 3:
        codes.append(toks[i])
        i += 1
    dil = "LISTO"
    rest = toks[i:]
    joined_head = " ".join(rest[:6])
    if rest:
        if rest[0].lower() == "listo":
            dil = "LISTO"
            rest = rest[1:]
        elif re.fullmatch(r"1\+\d", rest[0]):
            dil = rest[0]
            rest = rest[1:]
        elif rest[0] == "1" and len(rest) >= 2 and rest[1].startswith("+"):
            dil = "1" + rest[1]
            rest = rest[2:]
        elif re.match(r"^1$", rest[0]) is None and "LT +" in joined_head.upper() or "LT +" in " ".join(rest[:5]).upper():
            # 1 LT + 50 / 1 LT + 60 / 1 LT + 20
            m = re.match(r"^(1\s*LT\s*\+\s*\d+)\s+(.*)$", " ".join(rest), re.I)
            if m:
                dil = re.sub(r"\s+", " ", m.group(1).upper())
                rest = m.group(2).split()
        elif re.fullmatch(r"1\+\d", "".join(rest[:2]).replace(" ", "")):
            dil = "".join(rest[:2]).replace(" ", "")
            rest = rest[2:]

    prices_rev: list[float | None] = []
    name_toks = list(rest)
    while name_toks and (is_price_token(name_toks[-1]) or name_toks[-1] in DASH):
        prices_rev.append(parse_price(name_toks[-1]))
        name_toks.pop()
    prices = list(reversed(prices_rev))
    name = " ".join(name_toks)
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = name.replace("!!SUPER EFECTIVO!!", "").replace("NUEVO OFERTA", "")
    name = name.replace("(VER VIDEO DEMOSTRACION)", "")
    name = name.replace("NUEVA FORMULA X3 CONCENTRADO", "X3 CONCENTRADO")
    name = name.replace("NUEVA FORMULA", "").replace("NUEVO AROMA", "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return codes, dil, [p for p in prices if p is not None], name


SECTION_CAT = [
    ("COSMETICA AUTOMOTORES", ("Automotriz", "Limpieza", "Dinamic")),
    ("TEXTILES JABONES PREMIUM", ("Ropa", "Jabón líquido premium", "Dinamic")),
    ("TEXTILES JABONES", ("Ropa", "Jabón líquido", "Dinamic")),
    ("TEXTILES SUAVIZANTES", ("Ropa", "Suavizante", "Dinamic")),
    ("TEXTILES VARIOS", ("Ropa", "Lavandina y pretreat", "Dinamic")),
    ("DESENGRASANTES", ("Desengrasantes", "Industrial", "Dinamic")),
    ("DETERGENTES", ("Detergentes", "Lavavajillas", "Dinamic")),
    ("CERAS", ("Pisos", "Ceras", "Dinamic")),
    ("BACTERICIDAS", ("Desinfectantes", "Bactericidas", "Dinamic")),
    ("LINEA INNOVADORA", ("Pisos", "Limpiador concentrado", "Línea innovadora")),
    ("LINEA TRADICIONAL", ("Pisos", "Limpiador concentrado", "Línea tradicional")),
    ("LINEA CLASICA", ("Pisos", "Limpiador concentrado", "Línea clásica")),
    ("LIMPIADORES PARA PISOS", ("Pisos", "Limpiador concentrado", "Dinamic")),
    ("DIVISION VARIOS", ("Varios", "Hogar", "Dinamic")),
    ("NOVEDADES", ("Químicos", "Insumos", "Dinamic")),
    ("PERFUMES ROPA", ("Ropa", "Perfume textil", "Dinamic")),
    ("JABONES LIQUIDOS MANOS", ("Higiene", "Jabón de manos", "Dinamic")),
    ("JABONES EN POLVO", ("Ropa", "Jabón en polvo", "Dinamic")),
    ("COSMETICA CAPILAR", ("Higiene", "Capilar", "Dinamic")),
    ("DIFUSORES", ("Aromas", "Difusores", "Dinamic")),
    ("ESENCIAS PARA HORNILLOS", ("Aromas", "Hornillos", "Dinamic")),
    ("PERFUMANTES P/VEHICULOS", ("Automotriz", "Aromatizante", "Dinamic")),
    ("ENVASES PLASTICOS", ("Envases", "Plástico", "Dinamic")),
    ("CLORO", ("Pileta", "Cloro", "Dinamiclor")),
]


def cats_for(section: str) -> tuple[str, str, str]:
    u = section.upper()
    for key, val in SECTION_CAT:
        if key in u:
            return val
    return ("Limpieza", "General", "Dinamic")


def presentations_for(section: str, n_codes: int, n_prices: int) -> list[str]:
    u = section.upper()
    if "JABONES" in u and "MANOS" not in u and "POLVO" not in u:
        opts = ["5 L", "20 L", "200 L"]
    elif "SUAVIZANTES" in u or "DETERGENTES" in u:
        opts = ["5 L", "20 L", "200 L"]
    elif "BACTERICIDAS" in u or "1/4" in u or "INNOVADORA" in u or "TRADICIONAL" in u or "CLASICA" in u:
        opts = ["1 L", "5 L", "1/4"]
    elif "POLVO" in u:
        opts = ["10 kg"]
    else:
        opts = ["1 L", "5 L", "20 L"]
    n = min(n_codes, n_prices, len(opts))
    return opts[:n]


NOUN = {
    "Ropa": "Producto para ropa",
    "Automotriz": "Producto automotor",
    "Desengrasantes": "Desengrasante",
    "Detergentes": "Detergente lavavajillas",
    "Pisos": "Producto para pisos",
    "Desinfectantes": "Desinfectante",
    "Higiene": "Producto de higiene",
    "Químicos": "Insumo químico",
    "Varios": "Producto de limpieza",
    "Aromas": "Aromatizante",
    "Envases": "Envase plástico",
    "Pileta": "Producto para pileta",
    "Limpieza": "Producto de limpieza",
}


def describe(nombre: str, cat1: str, presentacion: str, dil: str) -> str:
    noun = NOUN.get(cat1, "Producto de limpieza")
    dil_txt = "listo para usar" if dil.upper() == "LISTO" else f"dilución {dil}"
    pretty = nombre.title() if nombre == nombre.upper() else nombre
    words_name = pretty.split()
    if len(words_name) > 8:
        pretty = " ".join(words_name[:8])
    raw = f"{noun} {pretty}, marca Dinamic, {presentacion}, {dil_txt}."
    words = raw.split()
    if len(words) > 25:
        raw = f"{noun} {pretty}, marca Dinamic, {presentacion}, {dil_txt}."
    if len(raw.split()) < 10:
        raw = f"{noun}, marca Dinamic, presentación {presentacion}, {dil_txt}."
    # strip fluff leftovers
    for bad in ("super", "efectivo", "ideal", "perfecto"):
        raw = re.sub(bad, "", raw, flags=re.I)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:1].upper() + raw[1:]


def aliases(code: str, nombre: str, presentacion: str, cat2: str) -> str:
    bits = [
        code,
        nombre.lower(),
        cat2.lower(),
        presentacion.lower(),
        "dinamic",
        "dinamicquim",
    ]
    # first 4 significant words
    words = [w for w in re.split(r"[^a-zA-Záéíóúñ0-9+]+", nombre.lower()) if len(w) > 2][:5]
    bits.extend(words)
    seen = set()
    out = []
    for b in bits:
        b = b.strip()
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return "|".join(out[:10])


def parse_pages_1_3(doc) -> list[dict]:
    rows = []
    section = "GENERAL"
    for pi in range(3):
        for line in pdf_lines(doc[pi]):
            up = line.upper()
            if "DIVISI" in up or up.startswith("LINEA ") or "LIMPIADORES PARA PISOS" in up or "NOVEDADES" in up:
                section = line
            if HEADER_HINT.match(line) or line.upper().startswith("C X"):
                continue
            skip_sec = section.upper()
            if any(
                k in skip_sec
                for k in ("DIFUSORES", "ESENCIAS PARA HORNILLOS", "PERFUMANTES P/VEHICULOS", "ENVASES PLASTICOS")
            ):
                continue
            if not re.match(r"^\d{1,4}\b", line):
                continue
            codes, dil, prices, name = split_row(line)
            if codes and codes[0] in {"150", "152", "153"} or (codes and 450 <= int(codes[0]) <= 457):
                continue
            if not codes or not name or not prices:
                continue
            if "PREGUNTAR POR PRECIO" in name.upper():
                name = re.sub(r"\(PREGUNTAR POR PRECIO A GRANEL 1\.000 LT\.\)", "", name, flags=re.I).strip()
            presents = presentations_for(section, len(codes), len(prices))
            cat1, cat2, cat3 = cats_for(section)
            nu = name.upper()
            if "CLORO" in nu or "LAVANDINA" in nu:
                cat1, cat2 = "Limpieza", "Cloro y lavandina"
            if len(codes) == 1 and re.search(r"5\s*LTS", nu):
                presents = ["5 L"]
            n = min(len(codes), len(prices), len(presents))
            for i in range(n):
                rows.append(
                    {
                        "product_code": codes[i],
                        "nombre_base": name,
                        "presentacion": presents[i],
                        "precio": prices[i],
                        "dilucion": dil,
                        "categoria_1": cat1,
                        "categoria_2": cat2,
                        "categoria_3": cat3,
                        "fuente_hoja": f"pagina-{pi + 1}",
                        "seccion": section,
                    }
                )
    return rows


def parse_page_4(doc) -> list[dict]:
    lines = pdf_lines(doc[3])
    rows = []
    pending_price = None
    pending_pres = None
    for line in lines:
        if line.upper().startswith("COD ") or line.upper() == "COD PRODUCTO PRESENTACION PRECIO":
            continue
        # combined: CODE NAME PRES $ PRICE
        m = re.match(
            r"^(\d{3,4})\s+(.+?)\s+(UNIDAD|1 KG|5 KG|50 KG|45 KG|1 LT|5 LT)\s+\$?\s*([\d\.,]+)$",
            line,
            re.I,
        )
        if m:
            rows.append(_pileta(m.group(1), m.group(2), m.group(3), parse_price(m.group(4))))
            pending_price = None
            continue
        m = re.match(r"^(UNIDAD|1 KG|5 KG|50 KG|45 KG|1 LT|5 LT)\s+\$?\s*([\d\.,]+)$", line, re.I)
        if m:
            pending_pres, pending_price = m.group(1), parse_price(m.group(2))
            continue
        m = re.match(r"^(\d{3,4})\s+(.+)$", line)
        if m and pending_price:
            rows.append(_pileta(m.group(1), m.group(2), pending_pres or "UNIDAD", pending_price))
            pending_price = None
            pending_pres = None
            continue
        m = re.match(r"^(\d{3,4})\s+(.+?)\s+(UNIDAD)\s*$", line, re.I)
        if m:
            # name without price yet — wait next price? page 4 accessories sometimes reverse
            pending_name = (m.group(1), m.group(2), m.group(3))
            # store as pending product
            pending_price = ("prod", pending_name)
            continue
    return [r for r in rows if r and r["precio"]]


def _pileta(code, name, pres, price):
    if not price:
        return None
    name = re.sub(r"\s+", " ", name).strip()
    cat2 = "Accesorios"
    up = name.upper()
    if any(k in up for k in ("BOYA", "SACAHOJAS", "CABO", "KIT MEDIDOR")):
        cat2 = "Accesorios"
    elif "CLORO" in up or "MICRO" in up or "PASTILLA" in up:
        cat2 = "Cloro"
    elif "ALGUICIDA" in up:
        cat2 = "Alguicida"
    elif "CLARIFICANTE" in up:
        cat2 = "Clarificante"
    elif "PH" in up or "KIT MEDIDOR" in up:
        cat2 = "Accesorios"
    return {
        "product_code": code,
        "nombre_base": name,
        "presentacion": pres.upper(),
        "precio": price,
        "dilucion": "LISTO",
        "categoria_1": "Pileta",
        "categoria_2": cat2,
        "categoria_3": "Dinamiclor",
        "fuente_hoja": "pagina-4",
        "seccion": "DINAMICLOR",
    }


def parse_specials(doc) -> list[dict]:
    """Difusores / esencias / envases with atypical columns."""
    rows = []
    raw_lines = pdf_lines(doc[2])
    lines: list[str] = []
    for line in raw_lines:
        if lines and re.match(r"^\d{2,4}\b", lines[-1]) and not re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}", lines[-1]):
            if not re.match(r"^\d{2,4}\b", line):
                lines[-1] = lines[-1] + " " + line
                continue
        lines.append(line)
    section = ""
    for line in lines:
        up = line.upper()
        if "DIFUSORES" in up:
            section = "DIFUSORES"
            continue
        if "ESENCIAS PARA HORNILLOS" in up:
            section = "ESENCIAS PARA HORNILLOS"
            continue
        if "PERFUMANTES P/VEHICULOS" in up:
            section = "PERFUMANTES P/VEHICULOS"
            continue
        if "ENVASES PLASTICOS" in up:
            section = "ENVASES PLASTICOS"
            continue
        if not re.match(r"^\d{2,4}\b", line):
            continue
        if section not in {
            "DIFUSORES",
            "ESENCIAS PARA HORNILLOS",
            "PERFUMANTES P/VEHICULOS",
            "ENVASES PLASTICOS",
        }:
            continue
        codes, dil, prices, name = split_row(line)
        if not codes or not prices:
            continue
        cat1, cat2, cat3 = cats_for(section)
        pres = "unidad"
        if "DIFUSOR" in section:
            name = "DIFUSOR CON VARILLAS " + name
        elif "ESENCIAS" in section:
            name = "ESENCIA HORNILLO " + name
        elif "PERFUMANTES" in section:
            name = "PERFUMANTE VEHICULO " + name
        rows.append(
            {
                "product_code": codes[0],
                "nombre_base": name or section.title(),
                "presentacion": pres,
                "precio": prices[0],
                "dilucion": "LISTO",
                "categoria_1": cat1,
                "categoria_2": cat2,
                "categoria_3": cat3,
                "fuente_hoja": "pagina-3",
                "seccion": section,
            }
        )
    return rows


def rotation_for(cat1: str, cat2: str) -> float:
    core = {
        "Jabón líquido",
        "Suavizante",
        "Lavavajillas",
        "Limpiador concentrado",
        "Jabón de manos",
    }
    if cat2 in core:
        return 0.88
    if cat1 in {"Ropa", "Detergentes", "Pisos"}:
        return 0.75
    if cat1 in {"Pileta", "Automotriz", "Desengrasantes"}:
        return 0.62
    if cat1 in {"Envases", "Aromas"}:
        return 0.28
    return 0.45


def build_products(raw: list[dict]) -> list[dict]:
    seen = set()
    products = []
    for r in raw:
        code = str(r["product_code"]).strip()
        if not code or code in seen:
            continue
        if not r.get("precio"):
            continue
        seen.add(code)
        pres = r["presentacion"]
        nombre = f"{r['nombre_base']} — {pres}".upper()
        rot = rotation_for(r["categoria_1"], r["categoria_2"])
        stock = int(40 + rot * 420)
        cat1, cat2, cat3 = r["categoria_1"], r["categoria_2"], r["categoria_3"]
        products.append(
            {
                "product_code": code,
                "nombre": nombre,
                "precio_lista_1": round(float(r["precio"]), 2),
                "stock": stock,
                "unidades_por_bulto": 1,
                "unidad_minima_de_venta": "unidad",
                "umv_tipo": "unidad",
                "categoria_1": cat1,
                "categoria_2": cat2,
                "categoria_3": cat3,
                "categoria_4": pres,
                "aliases": aliases(code, r["nombre_base"], pres, cat2),
                "rotacion_index": rot,
                "mental_priority": round(rot - 0.05, 2),
                "descripcion": describe(r["nombre_base"], cat1, pres, r["dilucion"]),
                "image_url": "",
                "en_catalogo": True,
                "is_mock": True,
                "fuente_hoja": r["fuente_hoja"],
            }
        )
    return products


def _take(pool: list[dict], n: int, used: set[str]) -> list[dict]:
    out = []
    for p in sorted(pool, key=lambda x: (-float(x["rotacion_index"]), x["nombre"], x["product_code"])):
        if p["product_code"] in used:
            continue
        out.append(p)
        used.add(p["product_code"])
        if len(out) >= n:
            break
    return out


def select_demo(products: list[dict], target: int = 95) -> list[dict]:
    """80–100 SKUs descriptivos. Bidón 5 L primero (pedido WhatsApp); mix de líneas."""
    used: set[str] = set()
    chosen: list[dict] = []
    by_code = {p["product_code"]: p for p in products}
    for code in (
        "1008",  # jabón verde 5 L — héroe WhatsApp
        "1018",  # suavizante celeste 5 L
        "1002",  # shampoo automotor 5 L
        "1016",  # lavandina ropa blanca 5 L
        "1235",  # lavavajillas limón 5 L
        "150",  # difusor
        "153",  # esencia hornillo
        "450",
        "451",
        "1077",
    ):
        p = by_code.get(code)
        if p and p["product_code"] not in used:
            chosen.append(p)
            used.add(p["product_code"])

    def add(filt, n: int) -> None:
        chosen.extend(_take([p for p in products if filt(p)], n, used))

    # Marca líder / fábrica (jabón, suavizante, detergente, piso) ~30%
    add(lambda p: p["categoria_2"] == "Jabón líquido" and p["categoria_4"] == "5 L", 6)
    add(lambda p: p["categoria_2"] == "Jabón líquido premium" and p["categoria_4"] == "5 L", 2)
    add(lambda p: p["categoria_2"] == "Suavizante" and p["categoria_4"] == "5 L", 5)
    add(lambda p: p["categoria_2"] == "Lavandina y pretreat" and p["categoria_4"] == "5 L", 4)
    add(lambda p: p["categoria_2"] == "Lavavajillas" and p["categoria_4"] == "5 L", 5)
    add(lambda p: p["categoria_2"] == "Limpiador concentrado" and p["categoria_4"] == "5 L", 7)
    add(lambda p: p["categoria_2"] == "Jabón en polvo", 1)

    # Formatos que se piden por chat: litro vs bidón vs 20 L
    add(lambda p: p["categoria_2"] == "Jabón líquido" and p["categoria_4"] == "20 L", 1)
    add(lambda p: p["categoria_2"] == "Suavizante" and p["categoria_4"] == "20 L", 1)
    add(lambda p: p["categoria_2"] == "Lavavajillas" and p["categoria_4"] == "20 L", 1)
    add(lambda p: p["categoria_2"] == "Lavandina y pretreat" and p["categoria_4"] == "1 L", 2)
    add(lambda p: p["categoria_2"] == "Limpiador concentrado" and p["categoria_4"] == "1 L", 3)

    # Otras líneas (≥3 si existen)
    add(lambda p: p["categoria_1"] == "Automotriz" and p["categoria_2"] == "Limpieza" and p["categoria_4"] == "5 L", 6)
    add(lambda p: p["categoria_1"] == "Automotriz" and p["categoria_2"] == "Limpieza" and p["categoria_4"] == "1 L", 2)
    add(lambda p: p["categoria_2"] == "Aromatizante", 1)
    add(lambda p: p["categoria_1"] == "Desengrasantes" and p["categoria_4"] == "5 L", 5)
    add(lambda p: p["categoria_2"] == "Cloro y lavandina" and p["categoria_4"] == "5 L", 4)
    add(lambda p: p["categoria_2"] == "Jabón de manos" and p["categoria_4"] == "5 L", 4)
    add(lambda p: p["categoria_2"] == "Capilar" and p["categoria_4"] == "5 L", 3)
    add(lambda p: p["categoria_2"] == "Ceras" and p["categoria_4"] in {"5 L", "1 L"}, 5)
    add(lambda p: p["categoria_2"] == "Hogar" and p["categoria_4"] == "5 L", 5)
    add(lambda p: p["categoria_2"] == "Perfume textil" and p["categoria_4"] == "5 L", 4)
    add(lambda p: p["categoria_1"] == "Químicos" and p["categoria_4"] == "5 L", 3)
    add(lambda p: p["categoria_1"] == "Pileta" and p["categoria_2"] == "Cloro" and p["categoria_4"] in {"1 KG", "5 KG"}, 4)
    add(lambda p: p["categoria_1"] == "Pileta" and p["categoria_2"] == "Alguicida" and p["categoria_4"] == "5 LT", 2)
    add(lambda p: p["categoria_1"] == "Pileta" and p["categoria_2"] == "Clarificante" and p["categoria_4"] == "5 LT", 2)
    add(lambda p: p["categoria_1"] == "Pileta" and p["categoria_2"] == "Accesorios", 3)
    add(lambda p: p["categoria_1"] == "Envases", 3)
    add(lambda p: p["categoria_1"] == "Aromas", 2)

    if len(chosen) < 80:
        add(lambda p: p["categoria_4"] == "5 L", 80 - len(chosen))
    if len(chosen) > target:
        chosen = chosen[:target]
    chosen.sort(key=lambda p: (p["categoria_1"], p["categoria_2"], p["product_code"]))
    return chosen


def enrich_demo_aliases(products: list[dict]) -> None:
    for p in products:
        extra = []
        pres = (p.get("categoria_4") or "").upper()
        if pres in {"5 L", "5 LT"}:
            extra = ["bidon", "bidón", "5 litros", "cinco litros"]
        elif pres in {"20 L"}:
            extra = ["bidon 20", "20 litros", "granel"]
        elif pres in {"1 L", "1 LT"}:
            extra = ["litro", "botella"]
        elif pres == "UNIDAD" or pres == "unidad":
            extra = ["unidad", "pieza"]
        if extra:
            bits = p["aliases"].split("|")
            for e in extra:
                if e not in bits:
                    bits.append(e)
            p["aliases"] = "|".join(bits[:12])


FIELDS = [
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
    doc = pymupdf.open(PDF)
    raw = parse_pages_1_3(doc) + parse_specials(doc) + parse_page_4(doc)
    RAW.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    all_products = build_products(raw)
    all_products.sort(key=lambda p: (p["categoria_1"], p["categoria_2"], p["product_code"]))

    OUT.mkdir(exist_ok=True)
    completo = ROOT / "inputs" / "catalogo-completo.csv"
    with completo.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(all_products)

    products = select_demo(all_products, target=95)
    enrich_demo_aliases(products)

    prod_path = OUT / "phase-01-productos.csv"
    with prod_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(products)

    lists = [
        (1, "Lista Base (Público)", 1.00),
        (2, "Lista Minorista Sugerido", 1.15),
        (3, "Lista Mayorista Especial", 0.90),
        (4, "Lista Gran Distribuidor", 0.85),
    ]
    overview_rows = []
    for lid, lname, mult in lists:
        path = OUT / f"phase-01-lista-precios-{lid}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["product_code", "precio_unidad", "is_mock"])
            w.writeheader()
            for p in products:
                precio = round(p["precio_lista_1"] * mult, 2)
                w.writerow(
                    {
                        "product_code": p["product_code"],
                        "precio_unidad": f"{precio:.2f}",
                        "is_mock": True,
                    }
                )
                overview_rows.append(
                    {
                        "lista_precios_id": lid,
                        "nombre": lname,
                        "multiplicador_sobre_lista_1": f"{mult:.2f}",
                        "product_code": p["product_code"],
                        "precio_unidad": f"{precio:.2f}",
                        "is_mock": True,
                    }
                )
    with (OUT / "phase-01-listas-precios.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "lista_precios_id",
                "nombre",
                "multiplicador_sobre_lista_1",
                "product_code",
                "precio_unidad",
                "is_mock",
            ],
        )
        w.writeheader()
        w.writerows(overview_rows)

    from collections import Counter

    cats = Counter(p["categoria_1"] for p in products)
    print(f"[*] catalogo completo: {len(all_products)} -> {completo}")
    print(f"[*] demo recorte: {len(products)} SKUs")
    print(f"[*] categorias demo: {dict(cats)}")
    print(f"[*] sample: {products[0]['product_code']} {products[0]['nombre']} ${products[0]['precio_lista_1']}")
    print(f"[*] wrote {prod_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
