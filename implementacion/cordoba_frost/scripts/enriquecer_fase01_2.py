#!/usr/bin/env python3
"""Fase 1.2 cordoba_frost: dry-run con checkpoint (no escribe BD)."""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT.parent / "backend-supabase"
TENANT = Path(__file__).resolve().parents[1]
IN_CSV = TENANT / "inputs" / "candidatos_a_enriquecer.csv"
OUT_CSV = TENANT / "outputs" / "vista_previa_enriquecimiento.csv"
FIELDS = [
    "codigo_producto",
    "nombre",
    "descripcion_original",
    "descripcion_mejorada",
    "alias_propuestos",
    "accion",
]

load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(ROOT / ".env", override=False)
sys.path.insert(0, str(ROOT / "scripts" / "fase-01-catalogo"))

from enriquecer_catalogo import (  # noqa: E402
    buscar_contexto_web,
    filtrar_alias_peligrosos,
    generar_enriquecimiento_ia,
    limpiar_nombre_producto,
)


def load_config() -> dict:
    path = TENANT / "config.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_done() -> dict[str, dict]:
    if not OUT_CSV.exists():
        return {}
    done = {}
    with OUT_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = (row.get("codigo_producto") or "").strip()
            if code and (row.get("descripcion_mejorada") or "").strip():
                done[code] = row
    return done


def append_row(row: dict) -> None:
    exists = OUT_CSV.exists()
    with OUT_CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})


def main() -> int:
    cfg = load_config()
    dominios = [d.strip() for d in (cfg.get("dominios") or "").split(",") if d.strip()]
    sufijo = cfg.get("sufijo_fallback")
    modo = cfg.get("modo_contexto") or "reducido"
    extra = cfg.get("instrucciones_extra")
    print(f"[*] schema_name confirmado: cordoba_frost")
    print(f"[*] modo={modo} dominios={dominios}")

    productos = []
    with IN_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = (row.get("codigo_producto") or row.get("product_code") or "").strip()
            if code:
                productos.append(row)
    done = load_done()
    print(f"[*] candidatos={len(productos)} ya_enriquecidos={len(done)}")

    for i, prod in enumerate(productos, start=1):
        code = (prod.get("codigo_producto") or prod.get("product_code") or "").strip()
        if code in done:
            print(f"  [{i}/{len(productos)}] skip {code}", flush=True)
            continue
        nombre = prod.get("nombre") or ""
        print(f"  [{i}/{len(productos)}] {code} | {limpiar_nombre_producto(nombre)}", flush=True)
        contexto = buscar_contexto_web(nombre, dominios=dominios or None, sufijo_fallback=sufijo)
        data_ia = generar_enriquecimiento_ia(
            nombre, contexto, modo_contexto=modo, instrucciones_extra=extra
        )
        alias_str = "|".join(
            filtrar_alias_peligrosos(nombre, data_ia.get("alias_locales") or [])
        )
        append_row(
            {
                "codigo_producto": code,
                "nombre": nombre,
                "descripcion_original": prod.get("descripcion") or "",
                "descripcion_mejorada": data_ia.get("descripcion_mejorada") or "",
                "alias_propuestos": alias_str,
                "accion": "ACTUALIZAR",
            }
        )

    print(f"[+] preview {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
