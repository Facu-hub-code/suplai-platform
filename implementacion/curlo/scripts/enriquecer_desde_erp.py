#!/usr/bin/env python3
"""CURLO Fase 1.2 — descripciones/aliases anclados al ERP (sin tocar precio/stock/nombre).

Serper no se usa: el contexto es via_productos. OpenAI solo reescribe texto comercial.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
TENANT = Path(__file__).resolve().parents[1]
ERP = TENANT / "inputs" / "erp" / "productos.json"
CANDIDATOS = TENANT / "inputs" / "candidatos_a_enriquecer.csv"
OUT = TENANT / "outputs" / "vista_previa_enriquecimiento.csv"
SCHEMA = "curlo"
WORKERS = 6


def load_env() -> None:
    for path in (
        Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
        ROOT.parent / "backend-supabase" / ".env",
        ROOT / ".env",
    ):
        if path.exists():
            load_dotenv(path, override=False)


load_env()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def sku_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    s = str(val).strip()
    return s[:-2] if s.endswith(".0") else s


def yes(val) -> bool:
    return str(val or "").strip().upper() == "SI"


def normalizar_alias(alias_raw: str) -> str:
    flat = unicodedata.normalize("NFKD", alias_raw.lower().strip())
    return "".join(c for c in flat.encode("ascii", "ignore").decode("ascii") if c.isalnum())


def alias_base(p: dict) -> list[str]:
    sku = sku_str(p.get("sku"))
    nombre = (p.get("nombre") or "").strip()
    marca = (p.get("marca") or "").strip()
    bits = [nombre, sku]
    if marca:
        bits.append(marca)
        first = nombre.split()[0] if nombre else ""
        if first:
            bits.append(f"{marca} {first}")
    short = re.sub(r"\s+", " ", nombre)
    short = re.sub(r"\bX\s+\d+.*$", "", short, flags=re.I).strip()
    if short and short != nombre:
        bits.append(short)
    out = []
    seen = set()
    for b in bits:
        n = normalizar_alias(b)
        if not n or n in seen:
            continue
        if "choclo" in n and "choclo" not in nombre.lower():
            continue
        seen.add(n)
        out.append(b.lower() if b != sku else sku)
    return out


def contexto_erp(p: dict) -> str:
    return (
        f"sku={sku_str(p.get('sku'))}\n"
        f"nombre_erp={p.get('nombre') or ''}\n"
        f"marca_erp={p.get('marca') or ''}\n"
        f"catalogo_erp={p.get('catalogo') or ''}\n"
        f"categoria_erp={p.get('categoria') or ''}\n"
        f"subcategoria_erp={p.get('subcategoria') or ''}\n"
        f"descripcion_erp={p.get('descripcion') or ''}\n"
        f"unidad_venta_erp={p.get('unidad_venta') or ''}\n"
        f"cantidad_minima_venta_erp={p.get('cantidad_minima_venta') or ''}\n"
        "REGLA: estos campos son la fuente de verdad. No inventes marca, peso, origen ni ingredientes."
    )


def llamar_openai(nombre: str, contexto: str) -> dict:
    if not OPENAI_API_KEY:
        return {"descripcion_mejorada": "", "alias_locales": []}
    system = (
        "Sos un auditor de catálogo B2B para una mayorista de heladería y repostería (CURLO, Cipolletti).\n"
        "La fuente de verdad es el ERP. No uses datos de internet ni inventes atributos.\n"
        "REGLAS DESCRIPCIÓN (10 a 18 palabras, una oración):\n"
        "1. Empezá con el sustantivo de categoría (cucurucho, vaso, envase, cobertura, grana, pulpa, pasta, chocolate, bandeja, accesorio).\n"
        "2. Incluí marca ERP si viene. No reemplaces ALTA ROTACION u otras líneas por marcas famosas.\n"
        "3. Formato solo si está en el nombre ERP. Cero fluff (ideal, delicioso, descubre).\n"
        "4. Prohibido precio, stock, margen, kiosco.\n"
        "ALIAS: minúsculas, SKU, marca, nombre corto, cono/cucurucho/vaso/bulto/caja si aplica. Nunca 'choclo' por chocolate.\n"
        "Respondé JSON con descripcion_mejorada (string) y alias_locales (array de strings)."
    )
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"=== DATOS ERP (única fuente) ===\n{contexto}\n\nPRODUCTO TARGET: {nombre}\n",
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }
    try:
        res = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        if res.status_code == 200:
            return json.loads(res.json()["choices"][0]["message"]["content"])
        print(f"  OpenAI HTTP {res.status_code} para {nombre[:40]}: {res.text[:160]}")
    except Exception as exc:
        print(f"  OpenAI error {nombre[:40]}: {exc}")
    return {"descripcion_mejorada": "", "alias_locales": []}


def fallback_desc(p: dict) -> str:
    cat = (p.get("categoria") or p.get("catalogo") or "Insumo").split("/")[0].strip()
    cat = re.sub(r"^[A-Z]\)\s*", "", cat)
    nombre = (p.get("nombre") or "").strip()
    marca = (p.get("marca") or "").strip()
    extra = (p.get("descripcion") or "").strip()
    parts = [cat.title() if cat else "Insumo", nombre]
    if marca and marca.upper() not in nombre.upper():
        parts.append(f"marca {marca}")
    if extra and extra.upper() not in nombre.upper():
        parts.append(extra)
    text = ", ".join(p for p in parts if p).rstrip(".") + "."
    words = text.split()
    if len(words) > 22:
        text = " ".join(words[:22]).rstrip(",.") + "."
    return text


def enriquecer_uno(p: dict) -> dict:
    nombre = (p.get("nombre") or "").strip()
    data = llamar_openai(nombre, contexto_erp(p))
    desc = (data.get("descripcion_mejorada") or "").strip()
    if not desc or len(desc.split()) < 6:
        desc = fallback_desc(p)
    aliases = alias_base(p)
    for a in data.get("alias_locales") or []:
        if not a or "choclo" in a.lower():
            continue
        n = normalizar_alias(str(a))
        if n and n not in {normalizar_alias(x) for x in aliases}:
            aliases.append(str(a).strip().lower())
    return {
        "codigo_producto": sku_str(p.get("sku")),
        "nombre": nombre,
        "descripcion_original": (p.get("descripcion") or "").strip(),
        "descripcion_mejorada": desc,
        "alias_propuestos": "|".join(aliases),
        "accion": "ACTUALIZAR",
        "marca_erp": (p.get("marca") or "").strip(),
        "categoria_erp": (p.get("categoria") or "").strip(),
    }


def main() -> int:
    if not OPENAI_API_KEY:
        print("[FAIL] Falta OPENAI_API_KEY", file=sys.stderr)
        return 1
    with ERP.open(encoding="utf-8") as f:
        productos = json.load(f)["rows"]
    catalog_csv = TENANT / "outputs" / "phase-01-productos.csv"
    en_catalogo: set[str] = set()
    if catalog_csv.exists():
        with catalog_csv.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if str(row.get("en_catalogo", "")).lower() == "true":
                    en_catalogo.add(str(row["product_code"]).strip())
    activos = [
        p
        for p in productos
        if yes(p.get("activo")) and (not en_catalogo or sku_str(p.get("sku")) in en_catalogo)
    ]
    print(f"[*] schema={SCHEMA} a enriquecer={len(activos)} (solo en_catalogo; no se tocan precio/stock/nombre)")

    CANDIDATOS.parent.mkdir(parents=True, exist_ok=True)
    with CANDIDATOS.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["product_code", "nombre", "descripcion"])
        for p in activos:
            w.writerow([sku_str(p.get("sku")), p.get("nombre") or "", p.get("descripcion") or ""])
    print(f"[*] candidatos: {CANDIDATOS} ({len(activos)})")

    filas = []
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(enriquecer_uno, p): p for p in activos}
        for fut in as_completed(futs):
            filas.append(fut.result())
            done += 1
            if done % 50 == 0 or done == len(activos):
                print(f"    {done}/{len(activos)}")

    filas.sort(key=lambda r: (r["categoria_erp"], r["nombre"], r["codigo_producto"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "codigo_producto",
                "nombre",
                "descripcion_original",
                "descripcion_mejorada",
                "alias_propuestos",
                "accion",
                "marca_erp",
                "categoria_erp",
            ],
        )
        w.writeheader()
        w.writerows(filas)
    print(f"[OK] preview {OUT} filas={len(filas)}")
    print("Revisá el CSV. Decime aplicar cambios para persistir solo descripcion + aliases en curlo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
