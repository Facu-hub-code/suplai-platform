#!/usr/bin/env python3
"""Clasifica productos Benfresh en taxonomía tienda navegable."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

CATEGORIES = [
    ("Frozen Fruits", "Frutas congeladas IQF y tropicais", 10),
    ("Frozen Vegetables", "Verduras y hortalizas congeladas", 20),
    ("Blends & Mixes", "Mezclas y blends (California, Fajita, Soup Mix, etc.)", 30),
    ("Sorbets & Desserts", "Sorbets, postres y snacks dulces", 40),
    ("Acai & Smoothie Bases", "Acai, bases para smoothie y bowls", 50),
    ("Dry Goods", "Arroz, legumbres y secos", 60),
    ("Beverages", "Bebidas y aguas", 70),
    ("Specialty", "Otros productos de catálogo", 80),
]

PACKAGING_RE = re.compile(
    r"(^bag\b|^bags\b|^box\b|^boxes\b|packing goods|repacking|packaging)",
    re.I,
)


def norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def classify(nombre: str, product_code: str) -> str | None:
    """Devuelve nombre de categoría o None = packaging (fuera de tienda)."""
    n = norm(nombre)
    code = (product_code or "").strip()

    if PACKAGING_RE.search(n) or n.startswith("bag ") or n.startswith("bags "):
        return None
    if code.startswith("100") and ("bag" in n or "box" in n):
        return None
    if code.startswith("200") and "box" in n:
        return None

    # Orden importa
    if "sorbet" in n or "franui" in n or "rice cake" in n or "dessert" in n:
        return "Sorbets & Desserts"
    if "acai" in n or "smoothie blend" in n:
        return "Acai & Smoothie Bases"
    if any(
        k in n
        for k in (
            "blend",
            "mix ",
            " mix",
            "fajita",
            "sofrito",
            "soup mix",
            "california",
            "key west",
            "3 vegetables",
            "4 vegetables",
            "peas & carrot",
            "peas and carrot",
        )
    ):
        return "Blends & Mixes"
    if any(k in n for k in ("rice ", " rice", "bean black dry", "dry bean", "parboiled")):
        return "Dry Goods"
    if any(k in n for k in ("water", "juice", "beverage", "coconut water")):
        return "Beverages"

    fruit_kw = (
        "strawberry",
        "blueberr",
        "raspberr",
        "blackberr",
        "mango",
        "pineapple",
        "banana",
        "cherry",
        "cherries",
        "papaya",
        "mamey",
        "passion",
        "maracuya",
        "pitaya",
        "dragon fruit",
        "cranberr",
        "apple",
        "guayaba",
        "plantain",
        "platano",
        "berry",
        "berries",
        "tropical",
        "pulp",
    )
    veg_kw = (
        "broccoli",
        "spinach",
        "carrot",
        "onion",
        "pepper",
        "sweetcorn",
        "corn ",
        "pea",
        "green bean",
        "edamame",
        "potato",
        "zucchini",
        "courgette",
        "cauliflower",
        "celery",
        "asparagus",
        "eggplant",
        "aubergine",
        "berenjena",
        "okra",
        "squash",
        "butternut",
        "yuca",
        "cassava",
        "tomato",
        "tomate",
        "french fries",
        "fries",
    )

    if any(k in n for k in fruit_kw):
        return "Frozen Fruits"
    if any(k in n for k in veg_kw):
        return "Frozen Vegetables"

    return "Specialty"


def main() -> None:
    import sys

    products = json.load(sys.stdin)
    assignments = []
    unpublish = []
    counts: Counter[str] = Counter()

    for p in products:
        cat = classify(p["nombre"], p["product_code"])
        if cat is None:
            unpublish.append(p)
            counts["__packaging__"] += 1
            continue
        assignments.append(
            {
                "product_code": p["product_code"],
                "nombre": p["nombre"],
                "en_catalogo": p.get("en_catalogo"),
                "category": cat,
            }
        )
        counts[cat] += 1

    out = {
        "schema": "benfresh",
        "categories": [
            {"name": n, "description": d, "sort_order": s} for n, d, s in CATEGORIES
        ],
        "assignments": assignments,
        "unpublish_packaging": [
            {"product_code": p["product_code"], "nombre": p["nombre"]} for p in unpublish
        ],
        "counts": dict(counts),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
