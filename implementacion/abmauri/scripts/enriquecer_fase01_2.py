#!/usr/bin/env python3
"""Genera la vista previa de descripciones y aliases para los 182 productos.

Serper no tiene créditos en esta sesión. Se usa OpenAI por lotes con el nombre
real, la taxonomía aprobada y guardrails estrictos; si una fila falla, se genera
una descripción determinística sin inventar atributos técnicos.
"""
from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from pathlib import Path

import requests
from dotenv import load_dotenv

SCHEMA = "abmauri"
EXPECTED = 182
BATCH = 15
HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
INPUT = ROOT / "inputs" / "candidatos_a_enriquecer.csv"
PRODUCTS = ROOT / "outputs" / "phase-01-productos.csv"
TAXONOMY = ROOT / "outputs" / "phase-01-1-propuesta-categorias.json"
OUTPUT = ROOT / "outputs" / "vista_previa_enriquecimiento.csv"
REPORT = ROOT / "outputs" / "phase-01-2-enrichment-report.json"

SYSTEM_PROMPT = """
Sos especialista en catálogos B2B de ingredientes para panificación y pastelería.
Recibirás productos reales de AB Mauri con nombre ERP y taxonomía aprobada.

Para cada producto:
- Escribí una sola descripción factual de 30 a 45 palabras.
- Empezá con el tipo concreto indicado por categoria_4.
- Expandí solo abreviaturas evidentes del nombre.
- Conservá marcas/líneas únicamente cuando estén explícitas.
- Conservá presentación, peso y cantidad solo cuando aparezcan en el nombre.
- No inventes ingredientes, certificaciones, rendimientos, aplicaciones,
  sabores, beneficios, compatibilidades ni atributos.
- No uses marketing: prohibido "ideal", "delicioso", "irresistible",
  "perfecto", "excelente", "descubre", "disfruta".
- Generá entre 3 y 6 alias breves en minúsculas, sin SKU.

Respondé JSON estricto:
{"products":[{"product_code":"...","descripcion_mejorada":"...","alias_locales":["..."]}]}
""".strip()


def fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(character for character in normalized if not unicodedata.combining(character))


def clean_spaces(value: str) -> str:
    return " ".join((value or "").split())


def safe_alias(value: str) -> str:
    value = clean_spaces(value).lower().strip(" .,-")
    if not value or len(value) > 100:
        return ""
    forbidden = {"ideal", "delicioso", "irresistible", "perfecto", "excelente"}
    if any(word in value for word in forbidden):
        return ""
    return value


def normalized_name(name: str) -> str:
    replacements = [
        (r"\bLP\b", "línea de plata"),
        (r"\bI360\b", "Innova 360"),
        (r"\bLEV\.?\b", "levadura"),
        (r"\bMARG\.?\b", "margarina"),
        (r"\bPREM\.?\b", "premezcla"),
        (r"\bMEJ\.?\b", "mejorador"),
        (r"\bHOJ\.?\b", "hojaldre"),
        (r"\bCJ\b", "caja"),
        (r"\bBOL\.?\b", "bolsa"),
        (r"\bPAQ\b", "paquete"),
    ]
    result = clean_spaces(name)
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.I)
    result = re.sub(r"\b100A\b", "", result, flags=re.I)
    return clean_spaces(result).strip(" -")


def deterministic_aliases(name: str, tags: dict[str, str], umv: str) -> list[str]:
    normalized = normalized_name(name)
    without_pack = re.sub(
        r"\b(?:caja|bolsa|paquete|bid[oó]n|balde|pote)?\s*"
        r"(?:\d+\s*[xX]\s*)?\d+(?:[.,]\d+)?\s*(?:kg|g|lt|l)\b.*$",
        "",
        normalized,
        flags=re.I,
    )
    candidates = [
        name.lower(),
        normalized.lower(),
        without_pack.lower(),
        tags["4"].lower(),
        tags["3"].lower(),
        f"{tags['4'].lower()} por {umv.lower()}",
    ]
    return list(dict.fromkeys(alias for value in candidates if (alias := safe_alias(value))))


def fallback_description(name: str, tags: dict[str, str], umv: str) -> str:
    return (
        f"{tags['4']} identificado en el catálogo como {normalized_name(name)}, "
        f"dentro de {tags['3']} y {tags['2']}. Presentación comercial por {umv}; "
        "descripción basada únicamente en la denominación ERP y la taxonomía aprobada."
    )


def call_openai(batch: list[dict[str, str]], api_key: str, model: str) -> dict[str, dict]:
    response = requests.post(
        os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        + "/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps({"products": batch}, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = json.loads(response.json()["choices"][0]["message"]["content"])
    return {
        str(item.get("product_code")): item
        for item in payload.get("products", [])
        if item.get("product_code")
    }


def main() -> None:
    load_dotenv("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env")
    load_dotenv(HERE.parents[3] / ".env", override=False)
    api_key = os.getenv("OPENAI_API_KEY") or ""
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY")

    with INPUT.open(encoding="utf-8", newline="") as handle:
        candidates = list(csv.DictReader(handle))
    with PRODUCTS.open(encoding="utf-8-sig", newline="") as handle:
        product_rows = {
            row["product_code"]: row for row in csv.DictReader(handle)
        }
    taxonomy_data = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    taxonomy = {
        item["product_code"]: item["tags"] for item in taxonomy_data["products"]
    }
    if len(candidates) != EXPECTED or len(taxonomy) != EXPECTED:
        raise RuntimeError(
            f"Cobertura inválida: candidatos={len(candidates)} taxonomía={len(taxonomy)}"
        )

    generated: dict[str, dict] = {}
    api_failures = 0
    for start in range(0, len(candidates), BATCH):
        source_batch = candidates[start : start + BATCH]
        prompt_batch = [
            {
                "product_code": row["product_code"],
                "nombre": row["nombre"],
                "categoria_1": taxonomy[row["product_code"]]["1"],
                "categoria_2": taxonomy[row["product_code"]]["2"],
                "categoria_3": taxonomy[row["product_code"]]["3"],
                "categoria_4": taxonomy[row["product_code"]]["4"],
                "unidad_minima_venta": product_rows[row["product_code"]][
                    "unidad_minima_de_venta"
                ],
            }
            for row in source_batch
        ]
        try:
            generated.update(call_openai(prompt_batch, api_key, model))
        except (requests.RequestException, ValueError, KeyError, json.JSONDecodeError) as error:
            api_failures += len(source_batch)
            print(f"[WARN] Lote {start + 1}-{start + len(source_batch)}: {error}")
        print(
            f"procesados={min(start + BATCH, len(candidates))}/{len(candidates)} "
            f"respuestas={len(generated)}"
        )

    preview: list[dict[str, str]] = []
    fallback_count = 0
    for row in candidates:
        code = row["product_code"]
        tags = taxonomy[code]
        umv = product_rows[code]["unidad_minima_de_venta"]
        item = generated.get(code) or {}
        description = clean_spaces(str(item.get("descripcion_mejorada") or ""))
        words = description.rstrip(".").split()
        forbidden = (
            "ideal",
            "delicioso",
            "irresistible",
            "perfecto",
            "excelente",
            "descubre",
            "disfruta",
        )
        if not 20 <= len(words) <= 50 or any(word in description.lower() for word in forbidden):
            description = fallback_description(row["nombre"], tags, umv)
            fallback_count += 1

        aliases = deterministic_aliases(row["nombre"], tags, umv)
        for value in item.get("alias_locales") or []:
            alias = safe_alias(str(value))
            if alias and alias not in aliases:
                aliases.append(alias)
        preview.append(
            {
                "codigo_producto": code,
                "nombre": row["nombre"],
                "descripcion_original": row["descripcion"],
                "descripcion_mejorada": description,
                "alias_propuestos": "|".join(aliases[:8]),
                "accion": "ACTUALIZAR",
            }
        )

    if len(preview) != EXPECTED:
        raise RuntimeError(f"Vista previa incompleta: {len(preview)}/{EXPECTED}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(preview[0]))
        writer.writeheader()
        writer.writerows(preview)
    REPORT.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "productos": len(preview),
                "modelo": model,
                "perfil": "tecnico_ampliado",
                "web_search": "unavailable_serper_no_credits",
                "openai_responses": len(generated),
                "fallback_descriptions": fallback_count,
                "api_batch_failures": api_failures,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"preview={OUTPUT}")
    print(f"productos={len(preview)} openai={len(generated)} fallback={fallback_count}")


if __name__ == "__main__":
    main()
