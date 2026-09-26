#!/usr/bin/env python3
"""Revisión conservadora del preview: elimina claims no verificados."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

EXPECTED = 182
HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
PREVIEW = ROOT / "outputs" / "vista_previa_enriquecimiento.csv"
PRODUCTS = ROOT / "outputs" / "phase-01-productos.csv"
TAXONOMY = ROOT / "outputs" / "phase-01-1-propuesta-categorias.json"
REPORT = ROOT / "outputs" / "phase-01-2-enrichment-report.json"

UMV_LABEL = {
    "caja": "caja",
    "bolsa": "bolsa",
    "balde": "balde",
    "pilon": "pilón",
    "paquete": "paquete",
    "bidon": "bidón",
    "pote": "pote",
    "unidad": "unidad",
    "display": "display",
    "tambor": "tambor",
    "sobre": "sobre",
    "botella": "botella",
}


def main() -> None:
    with PREVIEW.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with PRODUCTS.open(encoding="utf-8-sig", newline="") as handle:
        products = {row["product_code"]: row for row in csv.DictReader(handle)}
    taxonomy_data = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    taxonomy = {
        item["product_code"]: item["tags"] for item in taxonomy_data["products"]
    }
    if len(rows) != EXPECTED:
        raise RuntimeError(f"Preview incompleto: {len(rows)}/{EXPECTED}")

    for row in rows:
        code = row["codigo_producto"]
        product = products[code]
        tags = taxonomy[code]
        original = product["descripcion"]
        presentation_match = re.search(
            r"presentación comercial de (.+?)\.?$", original, flags=re.I
        )
        presentation = presentation_match.group(1) if presentation_match else "catálogo"
        umv = UMV_LABEL.get(
            product["unidad_minima_de_venta"].lower(),
            product["unidad_minima_de_venta"].lower(),
        )
        row["descripcion_mejorada"] = (
            f"{tags['4']}, presentación comercial de {presentation} por {umv}, "
            f"con denominación ERP «{row['nombre']}». Pertenece a {tags['3']}, "
            f"dentro de {tags['2']} del catálogo AB Mauri."
        )

    forbidden_patterns = (
        r"\bideal\b",
        r"\bdelicioso\b",
        r"\birresistible\b",
        r"\bperfecto\b",
        r"\bexcelente\b",
        r"\bdescubre\b",
        r"\bdisfruta\b",
        r"\boptimiza\w*",
        r"\bformulad\w*",
        r"\bdiseñad\w*",
        r"\bgarantiza\w*",
    )
    for row in rows:
        description = row["descripcion_mejorada"]
        words = description.rstrip(".").split()
        if not 20 <= len(words) <= 50:
            raise RuntimeError(
                f"Longitud inválida {row['codigo_producto']}: {len(words)} palabras"
            )
        if any(re.search(pattern, description, flags=re.I) for pattern in forbidden_patterns):
            raise RuntimeError(f"Claim no permitido {row['codigo_producto']}: {description}")
        if not row["alias_propuestos"].strip():
            raise RuntimeError(f"Sin aliases: {row['codigo_producto']}")

    with PREVIEW.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    report["description_strategy"] = "conservadora_taxonomia_erp"
    report["proactive_description_corrections"] = EXPECTED
    report["verified_web_claims_used"] = 0
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"revisados={len(rows)} claims_no_verificados=0")


if __name__ == "__main__":
    main()
