#!/usr/bin/env python3
"""Genera la propuesta taxonómica de AB Mauri sin escribir en Supabase.

El endpoint generativo produjo una respuesta truncada (22/182). Este script
usa las divisiones/rubros/segmentos reales del Excel y reglas normalizadas
para completar los 182 productos de forma determinística.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

SCHEMA = "abmauri"
EXPECTED = 182
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ROOT / "outputs" / "phase-01-productos.csv"
OUTPUT = ROOT / "outputs" / "phase-01-1-propuesta-categorias.json"


def fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(character for character in normalized if not unicodedata.combining(character)).upper()


def premezcla_type(name: str, segment: str) -> str:
    patterns = [
        (r"PAN DE QUESO", "Pan de Queso"),
        (r"COOKIE", "Cookies"),
        (r"MUFFIN", "Muffins"),
        (r"FACTURA|MEDIALUNA", "Facturas y Medialunas"),
        (r"ROSCA|PAN DULCE", "Rosca y Pan Dulce"),
        (r"BIZCOCHUELO", "Bizcochuelos"),
        (r"BUDIN", "Budines"),
        (r"CHURRO", "Churros"),
        (r"ÑOQUI|NOQUI", "Ñoquis"),
        (r"PIZZA", "Pizza"),
        (r"HOJALDRE", "Hojaldre"),
        (r"\bPAN\b", "Panificados"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, name):
            return label
    return {
        "PASTELERIA": "Preparados de Pastelería",
        "PANADERIA": "Preparados de Panadería",
        "HOJALDRE": "Preparados para Hojaldre",
        "MASAS": "Preparados para Masas",
    }.get(segment, "Premezcla")


def taxonomy(row: dict[str, str]) -> dict[str, str]:
    name = fold(row["nombre"])
    rubro = fold(row["categoria_2"])
    segment = fold(row["categoria_3"]).rstrip(".")
    level_1 = "Panificación y Pastelería"

    if rubro in {"FRESCA", "SECA", "ALIMENTICIA"}:
        level_2 = "Levaduras"
        level_3 = {
            "FRESCA": "Levaduras Frescas",
            "SECA": "Levaduras Secas",
            "ALIMENTICIA": "Levaduras Alimenticias",
        }[rubro]
        if rubro == "FRESCA":
            level_4 = "Levadura Fresca Prensada"
        elif rubro == "SECA":
            level_4 = "Levadura Seca Instantánea"
        else:
            level_4 = "Levadura Alimenticia"
    elif rubro == "MARGARINAS":
        level_2 = "Grasas y Margarinas"
        if "HOJ" in name or segment == "HOJALDRE":
            level_3, level_4 = "Margarinas para Hojaldre", "Margarina para Hojaldre"
        elif "TAPA" in name or segment == "TAPAS":
            level_3, level_4 = "Margarinas para Tapas", "Margarina para Tapas"
        else:
            level_3, level_4 = "Margarinas para Masas", "Margarina para Masas"
    elif rubro in {"GRASAS/SHORTENINGS", "ACEITES"}:
        level_2 = "Grasas y Margarinas"
        if rubro == "ACEITES" or "ACEITE" in name:
            level_3, level_4 = "Aceites para Panificación", "Aceite Vegetal"
        elif "OLEOMARGARINA" in name:
            level_3, level_4 = "Grasas para Panificación", "Oleomargarina"
        else:
            level_3, level_4 = "Grasas para Panificación", "Grasa Refinada"
    elif rubro == "PREMEZCLAS":
        level_2 = "Premezclas"
        level_3 = {
            "PASTELERIA": "Premezclas de Pastelería",
            "PANADERIA": "Premezclas de Panadería",
            "HOJALDRE": "Premezclas para Hojaldre",
            "MASAS": "Premezclas para Masas",
        }.get(segment, "Premezclas Especiales")
        level_4 = premezcla_type(name, segment)
    elif rubro == "MEJORADORES":
        level_2 = "Mejoradores"
        level_3 = {
            "CONCENTRADO": "Mejoradores Concentrados",
            "COMUN": "Mejoradores Comunes",
            "ESPECIFICO": "Mejoradores Específicos",
        }.get(segment, "Mejoradores para Panificación")
        level_4 = "Mejorador para Panificación"
    elif rubro == "ESENCIAS Y COLORANTES":
        level_2 = "Esencias y Colorantes"
        if "KOLAROMA" in name:
            level_3, level_4 = "Saborizantes Concentrados", "Kolaroma"
        elif "COLOR" in name and "ESENCIA" not in name:
            level_3, level_4 = "Colorantes", "Colorante Alimentario"
        else:
            level_3, level_4 = "Esencias", "Esencia Alimentaria"
    elif rubro in {"CREMAS", "CREMA"}:
        level_2 = "Ingredientes de Pastelería"
        if "VEG" in name or "UHT" in name:
            level_3, level_4 = "Cremas Vegetales", "Crema Vegetal"
        else:
            level_3, level_4 = "Cremas Pasteleras", "Crema Pastelera"
    elif rubro == "CHOCOLATES":
        level_2 = "Ingredientes de Pastelería"
        if "BAÑO" in name or "BANO" in name or segment in {"BAÑOS", "COBERTURAS / BAÑOS"}:
            level_3, level_4 = "Baños y Coberturas", "Baño de Repostería"
        else:
            level_3, level_4 = "Chocolates", "Chocolate para Repostería"
    elif rubro == "EXTRACTOS Y HARINAS DE MALTA":
        level_2 = "Aditivos e Ingredientes"
        if "HAR" in name and "MALTA" in name:
            level_3, level_4 = "Maltas", "Harina de Malta"
        else:
            level_3, level_4 = "Maltas", "Extracto de Malta"
    elif rubro == "POLVO DE HORNEAR Y OTROS ADITI":
        level_2 = "Aditivos e Ingredientes"
        if "POLVO" in name:
            level_3, level_4 = "Polvos de Hornear", "Polvo de Hornear"
        elif "EMUL" in name:
            level_3, level_4 = "Emulsionantes", "Emulsionante"
        else:
            level_3, level_4 = "Aditivos para Panificación", "Aditivo para Panificación"
    else:
        raise ValueError(
            f"Rubro sin cobertura para {row['product_code']}: {row['categoria_2']}"
        )

    return {"1": level_1, "2": level_2, "3": level_3, "4": level_4}


def main() -> None:
    with PRODUCTS.open(encoding="utf-8-sig", newline="") as handle:
        source = list(csv.DictReader(handle))
    products = [
        {
            "product_code": row["product_code"],
            "nombre": row["nombre"],
            "tags": taxonomy(row),
        }
        for row in source
    ]
    data = {
        "schema": SCHEMA,
        "generation_method": "reglas_normalizadas_desde_excel",
        "backend_attempt": {"returned": 22, "expected": EXPECTED, "status": "truncated"},
        "products": products,
    }
    if len(products) != EXPECTED:
        raise RuntimeError(f"Se esperaban {EXPECTED} productos y se generaron {len(products)}")
    for item in products:
        tags = item.get("tags") or {}
        if set(tags) != {"1", "2", "3", "4"} or any(not str(value).strip() for value in tags.values()):
            raise RuntimeError(
                f"Taxonomía incompleta para {item.get('product_code')}: {tags}"
            )
    OUTPUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"propuesta={OUTPUT}")
    print(f"productos={len(products)}")


if __name__ == "__main__":
    main()
