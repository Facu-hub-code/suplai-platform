#!/usr/bin/env python3
"""Genera previews de la campaña de recuperación McCain para Dimer.

Este script no se conecta a la base de datos ni realiza escrituras remotas.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "implementacion" / "dimer" / "outputs"
PROMPT_CONFIG = OUTPUT_DIR / "phase-01-3-prompt-config.json"

CLIENTS = {
    58: "Luisa",
    65: "Juan",
    70: "Luis",
    73: "Gerardo",
    74: "Eduardo",
    85: "Roberto",
    86: "David",
    90: "Agustín",
    91: "Mónica",
    95: "Hernán",
    98: "Christian",
    102: "Juan",
    106: "Daniel",
    110: "Juan",
    113: "Angélica",
    119: "Cristian",
    128: "Luis",
    144: "Gloria",
    146: "Patricio",
    148: "Nicolás",
    151: "Claudia",
    156: "Ricardo",
    160: "Rafael",
    164: "María",
    171: "Víctor",
    173: "David",
    174: "José",
    182: "María",
    185: "Juan",
    186: "Verónica",
}

LEGAL_NAMES = {
    58: "MATEU AYALA LUISA VERONICA",
    65: "CHACON MELLADO JUAN E",
    70: "ELGUETA CAMPOS LUIS ANDRÉS",
    73: "LIZAMA MOL GERARDO ANTONIO",
    74: "GARFE JARUFE EDUARDO ATALA",
    85: "GATICA ESCOBAR ROBERTO EDUARDO",
    86: "VIGUERA QUEUPUL DAVID ALEXIS",
    90: "ABARCA CARVAJAL AGUSTIN REINALDO",
    91: "GORMAZ PALMA MONICA DEL PILAR",
    95: "LUCERO SALINAS HERNAN LEONEL",
    98: "GUTIERREZ ALARCON CHRISTIAN ANDRES",
    102: "AVILA ALVAREZ JUAN ANTONIO",
    106: "ROMERO DANIEL RICARDO",
    110: "CARRERA GUZMAN JUAN ENRIQUE",
    113: "MORI MATTOS ANGELICA RAFAELA",
    119: "CARVAJAL MUNOZ CRISTIAN EDUARDO",
    128: "PALACIOS MORALES LUIS ALBERTO",
    144: "VILLARROEL PEREZ GLORIA ANGELICA",
    146: "SOTO MANCILLA PATRICIO ANTONIO",
    148: "GLUSCEVIC OPAZO NICOLAS MILENKO",
    151: "GONZALEZ PIZARRO CLAUDIA ANDREA",
    156: "FUENTES SALAZAR RICARDO MAURICIO",
    160: "CORTES CAIMALQUEN RAFAEL ALEJANDRO",
    164: "CRUZ MATELUNA MARIA ANGELICA",
    171: "URIBE MATURANA VICTOR ANTONIO",
    173: "SAAVEDRA ESCOBAR DAVID",
    174: "ALVAREZ REYES JOSE LUIS",
    182: "GALAZ GUZMAN MARIA JOSE",
    185: "ALVARADO DIAZ JUAN PABLO",
    186: "SOBARZO HERNANDEZ VERONICA ALICIA",
}

WEIGHTS = {
    "110A74011": (8, 2.25),
    "110A11121": (8, 2.25),
    "110111091": (6, 2.5),
    "1000007407": (6, 2.5),
    "110113101": (6, 2.5),
    "1000006570": (5, 2.5),
    "110A10641": (4, 2.5),
    "110A18951": (6, 1.5),
    "1000010226": (5, 2.5),
    "1000002300": (6, 2.5),
    "11000509": (4, 2.5),
    "236110": (5, 2.5),
    "236211": (5, 2.5),
    "1000002889": (7, 2.5),
}

ALIASES = [
    ("110A74011", "kilo de 7", 1.25),
    ("110A74011", "papa 7", 1.25),
    ("110A74011", "papas 7mm", 1.25),
    ("110A74011", "tipo mcdonalds", 1.25),
    ("110A74011", "corte fast food", 1.10),
    ("110A11121", "corte fino 7", 1.25),
    ("110A11121", "papa fina 7mm", 1.25),
    ("110A11121", "mccain fina", 1.10),
    ("110111091", "kilo de 10", 1.25),
    ("110111091", "papa 10", 1.25),
    ("110111091", "papas 10mm", 1.25),
    ("110111091", "tradicional 10mm", 1.25),
    ("110113101", "kilo de 12", 1.25),
    ("110113101", "papa 12", 1.25),
    ("110113101", "papas 12mm", 1.25),
    ("110113101", "corte casero 12", 1.10),
    ("1000007407", "papa crocante 10", 1.10),
    ("1000007407", "papas que duran crocantes", 1.10),
    ("1000006570", "papas mccain onduladas", 1.25),
    ("1000006570", "corte ondulado", 1.10),
    ("110A10641", "papa decorativa", 1.10),
    ("110A18951", "papas sonrisa", 1.25),
    ("110A18951", "papas carita", 1.25),
    ("110A18951", "croquetas smiles", 1.10),
]

PROMPT_HEADING = "### JERGA DE PAPAS CONGELADAS PARA RESTAURANTES ###"
PROMPT_BLOCK = """### JERGA DE PAPAS CONGELADAS PARA RESTAURANTES ###
- Cuando el cliente diga “7”, “10”, “12”, “7mm”, “el kilo de 7” o expresiones similares, interpretalo como el grosor o diámetro comercial del corte de la papa, no como cantidad.
- Equivalencias comerciales: “7” corresponde a productos rotulados 7 mm; “10” puede corresponder a cajas rotuladas 9 o 10 mm; “12” puede corresponder a cajas rotuladas 11 o 12 mm. La caja puede indicar hasta 1 mm menos que la forma habitual de pedirlo.
- Para “tipo McDonald’s” buscá primero papas McCain Fast Food de 7 mm. Presentalo como referencia de estilo/corte; no afirmes que sea el proveedor exacto ni que el producto sea idéntico.
- Si una medida tiene más de una opción, mostrale primero la alternativa McCain y aclarale el corte real impreso en la caja. Si el motivo de abandono es precio, ofrecé una alternativa del mismo rango de grosor de Caterpak, One Fry o Minuto Verde.
- No asumas que el cliente se fue por precio. Primero preguntá el motivo de manera humana y breve.

### CONSULTAS POR KILO E IVA ###
- Todos los precios informados son finales en CLP y ya incluyen IVA. Nunca sumes IVA nuevamente ni presentes un precio “más IVA”.
- Interpretá “precio por kilo”, “kilo con IVA” o “¿a cuánto está el kilo?” como una consulta por el producto, el corte y su formato comercial; no como un pedido de cotizar exactamente 1 kg.
- Para informar el formato, primero resolvé el SKU con search_products y después usá get_product_by_code con ese product_code. Tomá unidades_por_bulto y peso_referencia_kg de esa segunda herramienta; no los infieras del nombre, del prompt ni de memoria.
- Respondé con el precio vigente de la unidad mínima de venta devuelto por la herramienta y describí la presentación completa: cantidad de bolsas y peso de cada bolsa.
- No dividas el precio de caja para calcular un valor por 1 kg. Si el cliente indica que necesita X kilos, no calcules ni asumas cuántas bolsas o cajas debe comprar: explicá el formato disponible y preguntale cuántas cajas o unidades quiere.
- Formato recomendado: “Tenemos McCain Fast Food 7 mm. La caja trae 8 bolsas de 2,25 kg y sale $Y CLP final, IVA incluido.”
- Si falta el peso estructurado o hay dudas sobre la presentación, no inventes el formato: informá el producto y el precio disponible y pedí confirmar."""

TOOL_DESCRIPTION_OVERRIDES = {
    "search_products": (
        "Busca productos vía RAG en el catálogo del cliente y devuelve candidatos con SKU y precio vigente. "
        "Usala para resolver consultas individuales, incluyendo papas pedidas por corte 7/10/12 mm o "
        "expresiones como “kilo con IVA”. Esta tool no entrega de forma confiable la presentación completa: "
        "después de elegir un único SKU, llamá obligatoriamente a get_product_by_code antes de informar "
        "unidades_por_bulto o peso_referencia_kg. No infieras esos datos del nombre, del prompt ni de memoria. "
        "No la uses si el usuario incluyó cantidades para cargar o una lista de múltiples ítems."
    ),
    "get_product_by_code": (
        "Busca un producto por product_code (SKU) con match exacto y devuelve su precio, UMV, "
        "unidades_por_bulto, es_pesable y peso_referencia_kg. Usala después de search_products cuando debas "
        "informar el formato comercial de un único producto. Para las papas Dimer, tomá de esta respuesta la "
        "cantidad de bolsas y el peso por bolsa; no calcules precio por 1 kg ni conviertas kilos solicitados a "
        "bolsas. No la uses en paralelo para múltiples códigos."
    ),
}


def normalize_alias(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text)


def validate() -> None:
    assert len(CLIENTS) == 30
    assert set(CLIENTS) == set(LEGAL_NAMES)
    assert all(name and name == name.strip() for name in CLIENTS.values())
    assert len(WEIGHTS) == 14
    assert all(units > 0 and kg > 0 for units, kg in WEIGHTS.values())

    pairs = [(normalize_alias(alias), code) for code, alias, _ in ALIASES]
    assert len(pairs) == len(set(pairs))
    primary = {
        normalize_alias(alias): code
        for code, alias, weight in ALIASES
        if weight == 1.25 and alias.startswith(("kilo de", "papa "))
    }
    assert primary["kilode7"] == "110A74011"
    assert primary["kilode10"] == "110111091"
    assert primary["kilode12"] == "110113101"


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def update_prompt_config() -> bool:
    config = json.loads(PROMPT_CONFIG.read_text(encoding="utf-8"))
    context = str(config.get("contexto") or "").rstrip()
    if PROMPT_HEADING in context:
        base_context = context.split(PROMPT_HEADING, 1)[0].rstrip()
    else:
        base_context = context
    updated_context = f"{base_context}\n\n{PROMPT_BLOCK}".strip()
    current_tool_descriptions = config.get("tools_descripciones")
    updated_tool_descriptions = dict(current_tool_descriptions) if isinstance(current_tool_descriptions, dict) else {}
    updated_tool_descriptions.update(TOOL_DESCRIPTION_OVERRIDES)
    changed = (
        updated_context != context
        or current_tool_descriptions != updated_tool_descriptions
    )
    if changed:
        config["contexto"] = updated_context
        config["tools_descripciones"] = updated_tool_descriptions
        PROMPT_CONFIG.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def main() -> None:
    validate()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    client_rows = [
        {
            "client_id": client_id,
            "nombre_legal": LEGAL_NAMES[client_id],
            "nombre_de_pila": first_name,
            "target_group": "Grupo 1",
            "action": "set_first_name_and_replace_membership",
        }
        for client_id, first_name in CLIENTS.items()
    ]
    alias_rows = [
        {
            "product_code": product_code,
            "alias_raw": alias_raw,
            "alias_norm": normalize_alias(alias_raw),
            "weight": f"{weight:.2f}",
            "action": "upsert",
        }
        for product_code, alias_raw, weight in ALIASES
    ]
    weight_rows = [
        {
            "product_code": product_code,
            "unidades_por_bulto": units,
            "peso_referencia_kg": f"{kg:.2f}",
            "peso_total_kg": f"{units * kg:.2f}",
            "action": "set_reference_weight",
        }
        for product_code, (units, kg) in WEIGHTS.items()
    ]

    write_csv(
        OUTPUT_DIR / "recuperacion-mccain-clientes.csv",
        [
            "client_id",
            "nombre_legal",
            "nombre_de_pila",
            "target_group",
            "action",
        ],
        client_rows,
    )
    write_csv(
        OUTPUT_DIR / "recuperacion-mccain-aliases.csv",
        ["product_code", "alias_raw", "alias_norm", "weight", "action"],
        alias_rows,
    )
    write_csv(
        OUTPUT_DIR / "recuperacion-mccain-pesos.csv",
        [
            "product_code",
            "unidades_por_bulto",
            "peso_referencia_kg",
            "peso_total_kg",
            "action",
        ],
        weight_rows,
    )
    prompt_changed = update_prompt_config()

    print(
        f"clients={len(client_rows)} aliases={len(alias_rows)} "
        f"weights={len(weight_rows)} prompt_changed={str(prompt_changed).lower()}"
    )
    print("dry_run=true database_writes=0")


if __name__ == "__main__":
    main()
