#!/usr/bin/env python3
"""Fase 1.2 benavidez: reescribe descripciones y alias sin OpenAI/Serper.

Usa nombre + taxonomía 1.1 + reglas de rubro. No inventa certificaciones ni orígenes
salvo los que ya están en el nombre (chino, española, nacional, importada).
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

SCHEMA = "benavidez"
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_CSV = ROOT / "outputs" / "phase-01-productos.csv"
TAXONOMY_JSON = ROOT / "outputs" / "phase-01-1-propuesta-categorias.json"
OUT_CSV = ROOT / "outputs" / "vista_previa_enriquecimiento.csv"

FOOD_PREFIXES = {
    "ESP", "ESP2", "ESP4", "ESP5", "ESP10",
    "IN1", "IN5", "IN10", "IN20",
    "ADI", "ANT", "TRI", "HIL", "FCC", "FRA",
    "LEG", "SEM", "FRU", "RIA",
}
TOOL_PREFIXES = {"CUC", "CYG", "REP", "ROP", "BAN", "BAND", "MAQ", "BOL"}

BRANDS = [
    ("ESKILSTUNA", "Eskilstuna"),
    ("INTERPRISE", "Interprise"),
    ("ENTERPRISE", "Enterprise"),
    ("FARMESA", "Farmesa"),
    ("ACROCEL", "Acrocel"),
    ("TRINIDAD", "Trinidad"),
    ("RUEDO", "Ruedo"),
    ("FREIRE", "Freire"),
    ("CISA", "CISA"),
    ("DEVI", "DEVI"),
]

SIZE_RE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(KGS?|KILOS?|GRS?|GMS?|MG|MTS?|METROS?|LTS?|LITROS?|ML|CM|MM)\b",
    re.I,
)
NUMERO_RE = re.compile(r"N[ºO°]?\s*(\d+)", re.I)
PULGADAS_RE = re.compile(r"\b(\d{1,2})\s*(?:\"|''|PULGADAS?)\b|\b(\d{1,2})\"")
PACK_RE = re.compile(r"\bPACK\s*(?:X\s*)?(\d+)\b|\bX\s*(\d+)\s*(?:U(?:NI)?|UNID)?\b", re.I)

USO_L1 = {
    "Especias y condimentos": "Para condimentar carnes, chacinados, adobos y elaborados de carnicería.",
    "Integrales para elaborados": "Preparado para elaborar milanesas, hamburguesas o chacinados en carnicería o fábrica.",
    "Aditivos y antioxidantes": "Insumo técnico para elaborados cárnicos: color, ligue, rendimiento o conservación.",
    "Tripas e hilos": "Insumo para embutir o atar chacinados en carnicería o frigorífico.",
    "Fraccionados y bolsas": "Presentación chica o envase para mostrador y reventa.",
    "Cuchillos y cuchillas": "Herramienta de corte para faena, desposte o picado. No es un alimento.",
    "Máquinas y equipamiento": "Equipo o accesorio de planta para picar, embutir o procesar carne.",
    "Repuestos y accesorios": "Repuesto o accesorio para máquinas de carnicería. No es un alimento.",
    "Indumentaria de frigorífico": "Ropa o calzado de trabajo para faena y cámara.",
    "Legumbres y cereales": "Insumo seco para cocina o elaboración. Pedido con anticipación si el catálogo lo indica.",
    "Frutos secos y semillas": "Fruto seco o semilla para elaboración y reventa.",
    "Repostería": "Insumo de pastelería o repostería. Pedido con anticipación si el catálogo lo indica.",
}

WORD_FIX = {
    "AJI": "ají",
    "AJO": "ajo",
    "PIMIENTA": "pimienta",
    "CHIMICHURRI": "chimichurri",
    "OREGANO": "orégano",
    "PIMENTON": "pimentón",
    "NUEZ": "nuez",
    "MOSCADA": "moscada",
    "CANELA": "canela",
    "COMINO": "comino",
    "CURRY": "curry",
    "INTEGRAL": "integral",
    "MILANESA": "milanesa",
    "MILANESAS": "milanesas",
    "HAMBURGUESA": "hamburguesa",
    "HAMBURGUESAS": "hamburguesas",
    "CHORIZO": "chorizo",
    "MORCILLA": "morcilla",
    "SALAME": "salame",
    "SALCHICHA": "salchicha",
    "TRIPAS": "tripas",
    "TRIPA": "tripa",
    "EMBUTIDORA": "embutidora",
    "MOLEDORA": "moledora",
    "PICADORA": "picadora",
    "CUCHILLO": "cuchillo",
    "CUCHILLA": "cuchilla",
    "GRILLA": "grilla",
    "DISCO": "disco",
    "GUSANO": "gusano",
    "ESPIRAL": "espiral",
    "BANDEJA": "bandeja",
    "DELANTAL": "delantal",
    "CHAQUETILLA": "chaquetilla",
    "PANTALON": "pantalón",
    "PANTALONES": "pantalones",
    "GUANTE": "guante",
    "BOTA": "bota",
    "COFIA": "cofia",
    "HILO": "hilo",
    "BOBINA": "bobina",
    "ACOPLE": "acople",
    "ENGRANAJE": "engranaje",
    "ARANDELA": "arandela",
    "SIERRA": "sierra",
    "REBOZADOR": "rebozador",
    "ANTIOXIDANTE": "antioxidante",
    "ADITIVO": "aditivo",
    "FRACCIONADO": "fraccionado",
    "ALMENDRAS": "almendras",
    "ALMENDRA": "almendra",
    "POROTO": "poroto",
    "LENTEJA": "lenteja",
    "GARBANZO": "garbanzo",
    "ARROZ": "arroz",
    "HARINA": "harina",
    "AZUCAR": "azúcar",
    "SOJA": "soja",
    "HUEVO": "huevo",
    "POLVO": "polvo",
    "MOLIDA": "molida",
    "MOLIDO": "molido",
    "GRANO": "grano",
    "GRANO": "grano",
    "DESHIDRATADO": "deshidratado",
    "DESHIDRATADA": "deshidratada",
    "IMPORTADA": "importada",
    "IMPORTADO": "importado",
    "ESPANOLA": "española",
    "ESPAÑOLA": "española",
    "NACIONAL": "nacional",
    "ECONOMICO": "económico",
    "ECONOMICA": "económica",
    "PREMIUM": "premium",
    "INTERMEDIA": "intermedia",
    "CARNICERO": "carnicero",
    "CARNICERIA": "carnicería",
    "FRIGORIFICO": "frigorífico",
    "INOX": "inox",
    "PLASTICO": "plástico",
    "MADERA": "madera",
    "CERDO": "cerdo",
    "VACA": "vaca",
    "CORDERO": "cordero",
    "KG": "kg",
    "GR": "g",
    "GRS": "g",
    "MTS": "m",
    "PACK": "pack",
    "PARA": "para",
    "CON": "con",
    "SIN": "sin",
    "POR": "por",
    "DE": "de",
    "EN": "en",
    "Y": "y",
    "O": "o",
    "P": "p",
    "X": "x",
}

SYNONYMS = [
    (["AJI", "AJÍ", "CAYENA"], ["ají", "cayena", "pimienta cayena"]),
    (["CHIMICHURRI"], ["chimichurri", "condimento chimichurri"]),
    (["AJO DESHIDRATADO", "AJO"], ["ajo deshidratado", "ajo en polvo"]),
    (["PIMIENTA"], ["pimienta", "pimienta molida"]),
    (["INTEGRAL", "MILANESA"], ["integral milanesa", "preparado milanesa", "condimento milanesa"]),
    (["INTEGRAL", "HAMBURGUESA"], ["integral hamburguesa", "preparado hamburguesa"]),
    (["INTEGRAL", "CHORIZO"], ["integral chorizo", "preparado chorizo"]),
    (["MAD", "CERDO"], ["tripa MAD cerdo", "tripa natural cerdo", "envoltura cerdo"]),
    (["TRIPAS", "TRIPA"], ["tripa", "envoltura", "tripa para embutir"]),
    (["HILO"], ["hilo de atar", "piolín", "hilo chacinados"]),
    (["MOLEDORA", "PICADORA"], ["moledora", "picadora", "máquina de picar"]),
    (["DISCO"], ["disco moledora", "placa picadora", "disco para picar"]),
    (["GUSANO", "ESPIRAL"], ["gusano", "espiral moledora", "sinfin"]),
    (["CUCHILLO"], ["cuchillo carnicero", "cuchillo de faena"]),
    (["CUCHILLA"], ["cuchilla", "cuchilla picadora"]),
    (["CHAQUETILLA", "CHAQUETA"], ["chaquetilla", "chaqueta de frigorífico", "ropa de faena"]),
    (["DELANTAL"], ["delantal", "pechera", "mandil"]),
    (["REBOZADOR"], ["rebozador", "rebozado", "empanado"]),
    (["ANTIOXIDANTE"], ["antioxidante", "conservante cárnico"]),
    (["FRACCIONADO"], ["fraccionado", "sobre", "pack mostrador"]),
]


def fold(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in n if not unicodedata.combining(c)).upper()


def prefix_of(code: str) -> str:
    return (code or "").split("-", 1)[0].upper()


def pretty_phrase(nombre: str) -> str:
    """Title-case seguro: no convierte 'Grano' en 'gano'."""
    tokens = re.split(r"(\s+|-)", nombre.strip())
    out: list[str] = []
    for tok in tokens:
        if not tok or re.fullmatch(r"[\s\-]+", tok):
            out.append(tok)
            continue
        key = fold(tok).replace(".", "")
        if key in WORD_FIX:
            word = WORD_FIX[key]
            if out and out[-1] not in {"", " ", "-"} and not out[-1].endswith((" ", "-")):
                out.append(word)
            elif not out or out[-1] in {" ", "-"} or out[-1].endswith(" "):
                out.append(word[:1].upper() + word[1:] if word else word)
            else:
                out.append(word)
            # Capitalizar si es primer token
            if len("".join(out).strip()) == len(word):
                out[-1] = word[:1].upper() + word[1:]
            continue
        if tok.isupper() or tok.islower():
            low = tok.lower()
            out.append(low[:1].upper() + low[1:] if low else tok)
        else:
            out.append(tok)
    text = "".join(out)
    text = re.sub(r"\s+", " ", text).strip(" -")
    text = text.replace("En Gano", "en grano").replace("en gano", "en grano")
    small = {"de", "en", "y", "o", "para", "con", "por", "sin", "x", "p"}
    bits = text.split(" ")
    fixed = []
    for i, b in enumerate(bits):
        core = re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]", "", b).lower()
        if i > 0 and core in small:
            idx = next((j for j, ch in enumerate(b) if ch.isalpha()), 0)
            fixed.append(b[:idx] + b[idx:].lower())
        else:
            fixed.append(b)
    return " ".join(fixed)


def detect_brand(nombre: str, code: str) -> str | None:
    up = fold(nombre)
    for needle, label in BRANDS:
        if needle in up:
            return label
    pref = prefix_of(code)
    if pref in FOOD_PREFIXES:
        return "Especias Benavidez"
    return None


def extract_size(nombre: str) -> str:
    matches = list(SIZE_RE.finditer(nombre))
    if not matches:
        return ""
    # Prefer the size after the last hyphen (presentación) over "P/ 25 KG" de rendimiento.
    m = None
    if "-" in nombre:
        m = SIZE_RE.search(nombre.rsplit("-", 1)[-1])
    m = m or matches[-1]
    qty = m.group(1).replace(",", ".")
    unit = m.group(2).lower()
    unit_map = {
        "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg",
        "gr": "g", "grs": "g", "gms": "g", "mg": "mg",
        "mt": "m", "mts": "m", "metro": "m", "metros": "m",
        "lt": "L", "lts": "L", "litro": "L", "litros": "L",
        "ml": "ml", "cm": "cm", "mm": "mm",
    }
    return f"{qty} {unit_map.get(unit, unit)}"


def extract_numero(nombre: str) -> str:
    m = NUMERO_RE.search(nombre)
    return f"Nº {m.group(1)}" if m else ""


def extract_pulgadas(nombre: str) -> str:
    m = PULGADAS_RE.search(nombre)
    if not m:
        return ""
    n = m.group(1) or m.group(2)
    return f'{n}"' if n else ""


def pack_units(nombre: str) -> str:
    m = PACK_RE.search(nombre)
    if not m:
        return ""
    n = next((g for g in m.groups() if g), None)
    if not n:
        return ""
    val = int(n)
    if 1 < val <= 200:
        return f"pack x{val}"
    return ""


def uso_for(l1: str, nombre: str, code: str) -> str:
    up = fold(nombre)
    if "MILANESA" in up:
        return "Preparado para milanesas de carnicería."
    if "HAMBURGUESA" in up:
        return "Preparado para hamburguesas."
    if "CHORIZO" in up:
        return "Preparado para chorizo."
    if "MORCILLA" in up:
        return "Preparado para morcilla."
    if "SALAME" in up or "SALAMIN" in up:
        return "Preparado para salame o salamín."
    if "CHIMICHURRI" in up:
        return "Condimento para asado y adobo de carnes."
    if "CONDIMENTO PARA" in up:
        destino = pretty_phrase(re.sub(r"(?i).*condimento\s+para\s+", "", nombre))
        destino = SIZE_RE.sub("", destino).strip(" -")
        if destino:
            return f"Mezcla de especias para {destino[0].lower() + destino[1:]}."
    if "MOLEDORA" in up or "PICADORA" in up:
        return "Para picado de carne en moledora o picadora."
    if "EMBUTIDORA" in up:
        return "Para embutir chacinados."
    if prefix_of(code) in TOOL_PREFIXES:
        return USO_L1.get(l1, "Uso operativo de carnicería o frigorífico. No es un alimento.")
    return USO_L1.get(l1, "Insumo para carnicería, frigorífico o fábrica de chacinados.")


def origen_from_name(nombre: str) -> str:
    up = fold(nombre)
    bits = []
    if "CHINO" in up or "CHINA" in up:
        bits.append("origen chino según el nombre")
    if "ESPANOL" in up or "ESPAÑOL" in up:
        bits.append("origen español según el nombre")
    if "NACIONAL" in up:
        bits.append("origen nacional según el nombre")
    if "IMPORTAD" in up:
        bits.append("importado según el nombre")
    return ", ".join(bits)


def build_description(row: dict, tags: dict) -> str:
    code = row["product_code"]
    nombre = row["nombre"]
    l1 = (tags.get("1") or "").strip()
    l4 = (tags.get("4") or "").strip() or (tags.get("3") or "").strip()
    tipo = l4 or pretty_phrase(nombre)
    pretty = pretty_phrase(nombre)
    brand = detect_brand(nombre, code)
    size = extract_size(nombre)
    numero = extract_numero(nombre)
    pulg = extract_pulgadas(nombre)
    pack = pack_units(nombre)
    uso = uso_for(l1, nombre, code)
    origen = origen_from_name(nombre)

    parts: list[str] = []
    head = tipo[0].upper() + tipo[1:] if tipo else pretty
    if pretty and fold(pretty) != fold(tipo):
        parts.append(f"{head}: {pretty}.")
    else:
        parts.append(f"{head}.")

    extras = []
    if brand:
        if brand == "Especias Benavidez":
            extras.append("Línea Especias Benavidez")
        else:
            extras.append(f"Marca {brand}")
    size_already = bool(size and size.lower() in pretty.lower())
    if size and not size_already:
        extras.append(size)
    if numero:
        extras.append(numero)
    if pulg:
        extras.append(pulg)
    if pack:
        extras.append(pack)
    if "INOX" in fold(nombre):
        extras.append("inox")
    if extras:
        parts.append(", ".join(extras) + ".")
    parts.append(uso)
    if origen:
        parts.append(origen[0].upper() + origen[1:] + ".")
    parts.append(f"Código {code}.")
    text = " ".join(p.strip() for p in parts if p.strip())
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()
    if len(words) > 55:
        text = " ".join(words[:54]).rstrip(",.") + "."
    return text


def build_aliases(row: dict, tags: dict) -> str:
    code = row["product_code"]
    nombre = row["nombre"]
    l4 = (tags.get("4") or "").strip()
    l3 = (tags.get("3") or "").strip()
    brand = detect_brand(nombre, code)
    pretty = pretty_phrase(nombre)
    up = fold(nombre)
    items: list[str] = [code, pretty, l4]
    if l3 and fold(l3) in fold(nombre):
        items.append(l3)
    if brand and brand != "Especias Benavidez":
        items.append(brand)
    compact = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9ÁÉÍÓÚÑáéíóúñ ]+", " ", pretty)).strip()
    items.append(compact)
    no_size = SIZE_RE.sub("", pretty).strip(" -")
    if no_size:
        items.append(no_size)
    for keys, syns in SYNONYMS:
        if all(fold(k) in up for k in keys[:1]) and (len(keys) == 1 or all(fold(k) in up for k in keys)):
            items.extend(syns)
            break
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        val = (raw or "").strip()
        if not val:
            continue
        key = fold(val)
        if key in seen or len(val) < 2:
            continue
        seen.add(key)
        out.append(val)
        if len(out) >= 8:
            break
    return "|".join(out)


def load_taxonomy() -> dict[str, dict]:
    data = json.loads(TAXONOMY_JSON.read_text(encoding="utf-8"))
    return {p["product_code"]: p.get("tags") or {} for p in data.get("products") or []}


def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    tax = load_taxonomy()
    rows = list(csv.DictReader(PRODUCTS_CSV.open(encoding="utf-8")))
    out_rows = []
    missing_tax = 0
    for r in rows:
        code = (r.get("product_code") or "").strip()
        nombre = (r.get("nombre") or "").strip()
        original = (r.get("descripcion") or "").strip()
        tags = tax.get(code) or {}
        if not tags:
            missing_tax += 1
        desc = build_description(r, tags)
        aliases = build_aliases(r, tags)
        out_rows.append(
            {
                "codigo_producto": code,
                "nombre": nombre,
                "descripcion_original": original,
                "descripcion_mejorada": desc,
                "alias_propuestos": aliases,
                "accion": "ACTUALIZAR",
            }
        )
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "codigo_producto",
                "nombre",
                "descripcion_original",
                "descripcion_mejorada",
                "alias_propuestos",
                "accion",
            ],
        )
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"[+] {len(out_rows)} filas -> {OUT_CSV}")
    if missing_tax:
        print(f"[WARN] {missing_tax} SKUs sin taxonomía 1.1")
    print("[*] Muestra:")
    for sample in out_rows[:5]:
        print(f"    {sample['codigo_producto']}: {sample['descripcion_mejorada']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
