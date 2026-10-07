#!/usr/bin/env python3
"""Enriquece los 1215 SKUs de esekau con checkpoint por fila."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "fase-01-catalogo"))

from enriquecer_catalogo import (  # type: ignore
    buscar_contexto_web,
    filtrar_alias_peligrosos,
    generar_enriquecimiento_ia,
    limpiar_nombre_producto,
)

SCHEMA = "esekau"
IN_CSV = ROOT / "implementacion" / SCHEMA / "inputs" / "candidatos_a_enriquecer.csv"
OUT_CSV = ROOT / "implementacion" / SCHEMA / "outputs" / "vista_previa_enriquecimiento.csv"
FIELDS = [
    "codigo_producto",
    "nombre",
    "descripcion_original",
    "descripcion_mejorada",
    "alias_propuestos",
    "accion",
]


def load_config() -> dict:
    path = ROOT / "implementacion" / SCHEMA / "config.json"
    return json.loads(path.read_text(encoding="utf-8"))


def already_done() -> set[str]:
    if not OUT_CSV.exists():
        return set()
    with OUT_CSV.open(encoding="utf-8") as f:
        return {row["codigo_producto"] for row in csv.DictReader(f) if row.get("codigo_producto")}


def append_row(row: dict) -> None:
    exists = OUT_CSV.exists()
    with OUT_CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)
        f.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Enriquece esekau en lotes, con checkpoint.")
    parser.add_argument("--lote", type=int, default=100, help="SKUs a procesar en esta corrida (default 100)")
    args = parser.parse_args()

    cfg = load_config()
    dominios = [d.strip() for d in (cfg.get("dominios") or "").split(",") if d.strip()]
    sufijo = cfg.get("sufijo_fallback")
    modo = cfg.get("modo_contexto") or "reducido"
    extra = cfg.get("instrucciones_extra")

    productos = list(csv.DictReader(IN_CSV.open(encoding="utf-8")))
    done = already_done()
    print(f"[*] schema={SCHEMA} total={len(productos)} ya={len(done)}")
    pending = [p for p in productos if (p.get("product_code") or p.get("codigo_producto")) not in done]
    pending = pending[: max(0, args.lote)]
    print(f"[*] este lote={len(pending)} (tope {args.lote}) quedan_despues≈{len(productos) - len(done) - len(pending)}")

    for i, prod in enumerate(pending, start=1):
        code = prod.get("product_code") or prod.get("codigo_producto")
        nombre = prod.get("nombre") or ""
        desc = prod.get("descripcion") or ""
        print(f"[{i}/{len(pending)}] {code} | {limpiar_nombre_producto(nombre)}", flush=True)
        try:
            contexto = buscar_contexto_web(nombre, dominios=dominios, sufijo_fallback=sufijo)
            data_ia = generar_enriquecimiento_ia(
                nombre, contexto, modo_contexto=modo, instrucciones_extra=extra
            )
            alias = filtrar_alias_peligrosos(nombre, data_ia.get("alias_locales") or [])
            improved = data_ia.get("descripcion_mejorada") or desc
        except Exception as exc:
            print(f"    WARN {code}: {exc}")
            improved = desc
            alias = []
        append_row(
            {
                "codigo_producto": code,
                "nombre": nombre,
                "descripcion_original": desc,
                "descripcion_mejorada": improved,
                "alias_propuestos": "|".join(alias),
                "accion": "ACTUALIZAR",
            }
        )
    print(f"[OK] lote listo preview={OUT_CSV} acumulado≈{len(done) + len(pending)}/{len(productos)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
