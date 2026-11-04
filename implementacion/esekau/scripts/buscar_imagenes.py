#!/usr/bin/env python3
"""DEV-125 — busca imágenes para productos de esekau, por EAN, sin escribir en la BD.

Prioridad de productos:
  1) Los SKUs de los combos vigentes de DFSoft (`--combos`, JSON de /Vendedor/Combos).
  2) Pantene y las marcas más grandes de P&G, Clorox y Dreamco, hasta `--extra` productos.

Fuente: el EAN de cada producto (viene en los aliases de phase-01-productos.csv) se busca
en las tiendas VTEX de supermercados argentinos (Carrefour, Jumbo, Más Online). Un EAN
exacto identifica el producto; además se comparan el tamaño y la variante del nombre
de esekau con el de la tienda para decidir la confianza:
  alta   EAN exacto, tamaño igual y variante igual en al menos una tienda.
  media  EAN exacto y tamaño igual, variante con diferencias menores.
  dudosa EAN exacto con tamaño o variante distintos, o sin EAN exacto. No se asigna.

Después de la búsqueda se revisaron todas las imágenes a ojo (planchas de miniaturas).
Los veredictos están en outputs/phase-01-imagenes-revision.csv y se aplican al final:
`ok` pasa una dudosa a la propuesta; `dudosa` saca una de la propuesta.

Uso:
  python implementacion/esekau/scripts/buscar_imagenes.py --combos /ruta/combos.json
Salida: outputs/phase-01-imagenes-propuesta.csv y outputs/phase-01-imagenes-dudosas.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
PRODUCTOS = ROOT / "outputs" / "phase-01-productos.csv"
OUT_OK = ROOT / "outputs" / "phase-01-imagenes-propuesta.csv"
OUT_DUDOSAS = ROOT / "outputs" / "phase-01-imagenes-dudosas.csv"
REVISION = ROOT / "outputs" / "phase-01-imagenes-revision.csv"

TIENDAS = (
    ("carrefour.com.ar", "https://www.carrefour.com.ar"),
    ("jumbo.com.ar", "https://www.jumbo.com.ar"),
    ("masonline.com.ar", "https://www.masonline.com.ar"),
    ("cordiez.com.ar", "https://www.cordiez.com.ar"),
)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

# Marcas de la segunda tanda, en orden: la líder primero, después las de más SKUs por proveedor.
PROVEEDORES_GRANDES = ("PROCTER", "CLOROX", "DREAMCO")

# Abreviaturas del Excel de esekau → palabra que usan las tiendas.
SINONIMOS = {
    "sh": "shampoo", "ac": "acondicionador", "acond": "acondicionador", "plb": "plusbelle",
    "hs": "head shoulders", "presto": "prestobarba", "desod": "desodorante", "ap": "antitranspirante",
    "suav": "suavizante", "lav": "lavandina", "detg": "detergente", "det": "detergente",
    "jab": "jabon", "liq": "liquido", "repuesto": "repuesto", "rep": "repuesto", "dp": "doypack",
    "ym": "yerba", "cc": "", "pt": "", "pet": "", "st": "", "x": "",
}
# Palabras que no definen variante (formato, marca genérica, ruido del Excel).
RUIDO = {
    "sin", "tacc", "con", "de", "la", "el", "y", "en", "para", "por", "x12", "x6", "x24", "u", "un",
    "unidad", "unid", "caja", "bulto", "pack", "nuevo", "new", "oferta", "promo",
}
# Palabras que distinguen variantes que se confunden fácil: si una aparece de un lado y no del otro, es otra variante.
CRITICAS = {
    "shampoo", "acondicionador", "anticaida", "antiquiebre", "liso", "rizos", "control", "caspa",
    "mentol", "manzana", "limon", "pomelo", "naranja", "lavanda", "repuesto", "doypack", "aerosol",
    "gel", "barra", "crema", "hombre", "mujer", "men", "women", "bebe", "baby", "noche", "dia",
    "rosa", "blanco", "tinto", "dulce", "seco", "light", "zero", "original", "clasico", "clasica",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " ").replace("-", " ").replace("/", " ")
    return re.sub(r"[^a-z0-9.,% ]+", " ", s)


def tamanos(s: str) -> set[tuple[str, float]]:
    """Tamaños del nombre normalizados a (unidad base, cantidad): 1.5 L → ('ml', 1500)."""
    out = set()
    for num, unit in re.findall(r"(\d+(?:[.,]\d+)?)\s*(ml|cc|cm3|l|lt|lts|litros?|g|gr|grs|kg|kgs)\b", norm(s)):
        n = float(num.replace(",", "."))
        unit = unit.rstrip("s")
        if unit in ("l", "lt", "litro"):
            out.add(("ml", round(n * 1000)))
        elif unit in ("ml", "cc", "cm3"):
            out.add(("ml", round(n)))
        elif unit == "kg":
            out.add(("g", round(n * 1000)))
        else:
            out.add(("g", round(n)))
    return out


def palabras(s: str) -> set[str]:
    out = set()
    for w in norm(s).split():
        w = w.strip(".,%")
        if not w or w.isdigit() or re.fullmatch(r"\d+([.,]\d+)?(ml|cc|l|g|gr|kg|lt)?", w):
            continue
        w = SINONIMOS.get(w, w)
        for part in w.split():
            if len(part) > 1 and part not in RUIDO:
                out.add(part)
    return out


def ean_de(row: dict) -> str:
    for a in (row.get("aliases") or "").split("|"):
        a = a.strip()
        if re.fullmatch(r"\d{8,14}", a):
            return a
    return ""


def buscar_ean(ean: str) -> list[dict]:
    """Un resultado por tienda que tenga el EAN exacto."""
    hits = []
    for dominio, base in TIENDAS:
        try:
            r = requests.get(
                f"{base}/api/catalog_system/pub/products/search",
                params={"fq": f"alternateIds_Ean:{ean}"},
                headers={"User-Agent": UA},
                timeout=20,
            )
            data = r.json() if r.status_code in (200, 206) else []
        except Exception:
            data = []
        for p in data[:1]:
            for it in p.get("items") or []:
                if it.get("ean") != ean or not it.get("images"):
                    continue
                img = it["images"][0]["imageUrl"].split("?")[0]
                hits.append({
                    "tienda": dominio,
                    "nombre_tienda": p.get("productName") or it.get("name") or "",
                    "image_url": img,
                    "pagina": p.get("link") or "",
                })
                break
        time.sleep(0.15)
    return hits


def evaluar(nombre: str, marca: str, hit: dict) -> tuple[str, str]:
    """(confianza, motivo) para un resultado con EAN exacto."""
    t_ours, t_theirs = tamanos(nombre), tamanos(hit["nombre_tienda"])
    if t_ours and t_theirs and not (t_ours & t_theirs):
        return "dudosa", f"tamaño distinto ({sorted(t_ours)} vs {sorted(t_theirs)})"
    ours = palabras(nombre) - palabras(marca)
    theirs = palabras(hit["nombre_tienda"])
    falta_crit = (ours & CRITICAS) - theirs
    sobra_crit = (theirs & CRITICAS) - ours
    if falta_crit:
        return "dudosa", f"variante: la tienda no dice {sorted(falta_crit)}"
    comunes = ours & theirs
    cobertura = len(comunes) / len(ours) if ours else 1.0
    if t_ours and not t_theirs:
        return "media", "la tienda no indica tamaño"
    if sobra_crit:
        return "media", f"la tienda agrega {sorted(sobra_crit)}"
    if cobertura >= 0.5:
        return "alta", ""
    return "media", f"pocas palabras en común ({sorted(comunes)})"


def objetivos(productos: dict[str, dict], combo_skus: list[str], extra: int) -> list[tuple[str, str]]:
    """[(product_code, prioridad)] — combos primero, después marcas grandes."""
    out = [(c, "combo") for c in combo_skus if c in productos]
    ya = {c for c, _ in out}

    def rank(p: dict) -> float:
        return -float(p.get("rotacion_index") or 0)

    resto = [p for c, p in productos.items() if c not in ya and p["categoria_1"] in PROVEEDORES_GRANDES]
    pantene = sorted((p for p in resto if p["categoria_3"].lower() == "pantene"), key=rank)
    por_marca: dict[str, list[dict]] = {}
    for p in resto:
        if p["categoria_3"].lower() != "pantene":
            por_marca.setdefault(p["categoria_3"], []).append(p)
    # Las marcas con más SKUs primero; dentro de cada una, por rotación.
    marcas = sorted(por_marca, key=lambda m: -len(por_marca[m]))
    cola = list(pantene)
    for m in marcas:
        cola += sorted(por_marca[m], key=rank)
    for p in cola[:extra]:
        out.append((p["product_code"], f"marca:{p['categoria_3']}"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--combos", required=True, help="JSON con la respuesta de /Vendedor/Combos (clave 'norm')")
    ap.add_argument("--extra", type=int, default=110, help="productos de marca además de los combos")
    args = ap.parse_args()

    productos = {r["product_code"]: r for r in csv.DictReader(PRODUCTOS.open(encoding="utf-8"))}
    data = json.loads(Path(args.combos).read_text(encoding="utf-8"))
    combo_skus: list[str] = []
    for combo in data["norm"]:
        for item in combo["items"]:
            if item["sku"] not in combo_skus:
                combo_skus.append(item["sku"])

    lista = objetivos(productos, combo_skus, args.extra)
    revision = {}
    if REVISION.exists():
        revision = {r["product_code"]: r for r in csv.DictReader(REVISION.open(encoding="utf-8"))}
    ok_rows, dud_rows = [], []
    for i, (code, prioridad) in enumerate(lista, 1):
        p = productos[code]
        nombre, marca, ean = p["nombre"], p["categoria_3"], ean_de(p)
        base = {"product_code": code, "nombre": nombre, "marca": marca, "ean": ean, "prioridad": prioridad}
        if not ean:
            dud_rows.append({**base, "estado": "no_encontrada", "motivo": "sin EAN en el catálogo",
                             "candidata_url": "", "fuente": "", "nombre_fuente": ""})
            continue
        hits = buscar_ean(ean)
        if not hits:
            dud_rows.append({**base, "estado": "no_encontrada", "motivo": "EAN sin resultados en Carrefour/Jumbo/Más Online/Cordiez",
                             "candidata_url": "", "fuente": "", "nombre_fuente": ""})
            print(f"[{i}/{len(lista)}] {code} {nombre} — sin resultados")
            continue
        evaluados = [(h, *evaluar(nombre, marca, h)) for h in hits]
        orden = {"alta": 0, "media": 1, "dudosa": 2}
        evaluados.sort(key=lambda e: orden[e[1]])
        best, conf, motivo = evaluados[0]
        confirmaciones = sum(1 for _, c, _ in evaluados if c != "dudosa")
        difieren = [f"{h['tienda']}: {m}" for h, c, m in evaluados if c == "dudosa"]
        if conf != "dudosa" and difieren:
            motivo = "; ".join(filter(None, [motivo, "otra tienda difiere — " + " | ".join(difieren)]))
        fila = {**base, "image_url": best["image_url"], "fuente": best["tienda"], "nombre_fuente": best["nombre_tienda"],
                "pagina_fuente": best["pagina"], "confianza": conf, "tiendas_con_ean": len(hits),
                "tiendas_coinciden": confirmaciones, "motivo": motivo}
        veredicto = revision.get(code)
        if veredicto and veredicto["veredicto"] == "ok" and conf == "dudosa":
            conf, motivo = "media", f"revisión visual: {veredicto['nota']} (auto: {motivo})"
        elif veredicto and veredicto["veredicto"] == "dudosa":
            conf, motivo = "dudosa", f"revisión visual: {veredicto['nota']}"
        fila.update(confianza=conf, motivo=motivo)
        if conf == "dudosa":
            dud_rows.append({**base, "estado": "dudosa", "motivo": motivo, "candidata_url": best["image_url"],
                             "fuente": best["tienda"], "nombre_fuente": best["nombre_tienda"]})
        else:
            ok_rows.append(fila)
        print(f"[{i}/{len(lista)}] {code} {nombre} — {conf} ({best['tienda']}: {best['nombre_tienda']}) {motivo}")

    ok_cols = ["product_code", "nombre", "marca", "ean", "prioridad", "image_url", "fuente", "nombre_fuente",
               "pagina_fuente", "confianza", "tiendas_con_ean", "tiendas_coinciden", "motivo"]
    dud_cols = ["product_code", "nombre", "marca", "ean", "prioridad", "estado", "motivo", "candidata_url",
                "fuente", "nombre_fuente"]
    with OUT_OK.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ok_cols)
        w.writeheader()
        w.writerows(ok_rows)
    with OUT_DUDOSAS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=dud_cols)
        w.writeheader()
        w.writerows(dud_rows)
    print(f"\nObjetivo {len(lista)} | con imagen {len(ok_rows)} | dudosas/no encontradas {len(dud_rows)}")


if __name__ == "__main__":
    main()
