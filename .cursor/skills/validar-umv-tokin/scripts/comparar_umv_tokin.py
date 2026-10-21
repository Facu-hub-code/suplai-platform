#!/usr/bin/env python3
"""Compara la UMV que armaría el alta automática contra la conversión de Tokin.

No escribe la base. Tokin es el oráculo del pack (display y bulto). GEV aporta
la unidad del precio. El nombre aporta el número que GEV no manda.

Uso:
  python .cursor/skills/validar-umv-tokin/scripts/comparar_umv_tokin.py --codes 4013,14336,10204
  python .cursor/skills/validar-umv-tokin/scripts/comparar_umv_tokin.py --gev implementacion/almaro/inputs/gev-articulos-20261001.json --limite 40
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SEARCH = "https://tokin.vtexcommercestable.com.br/api/io/_v/api/intelligent-search/product_search"
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_SSL = ssl._create_unverified_context()

COUNT = r"(\d+)"
SEP = r"\s*[xX×]\s*"
MARK = r"(?:u|un|uni|uds|d)?"
WEIGHT = r"(\d+(?:[.,]\d+)?)\s*(?:g|gr|grs|gs|kg|kgs|k|ml|cc|l|lt|lts)?\.?"
PAT3 = re.compile(COUNT + MARK + SEP + COUNT + MARK + SEP + COUNT + MARK + r"(?:" + SEP + WEIGHT + r")?", re.I)
PAT2 = re.compile(COUNT + MARK + SEP + WEIGHT, re.I)
DISPLAY_RE = re.compile(r"display\s*\(\s*(\d+)\s*unidad", re.I)
BULTO_RE = re.compile(r"bulto\s*\(\s*(\d+)\s*(display|unidad)", re.I)


def _int(value) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = int(round(float(str(value).replace(",", "."))))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def parse_pack(nombre: str) -> dict | None:
    """Último pack del nombre. 3 números: A x B x peso. 2 números: N x peso."""
    text = nombre or ""
    found3 = list(PAT3.finditer(text))
    if found3:
        match = found3[-1]
        return {"kind": "3", "a": int(match.group(1)), "b": int(match.group(2)), "span": match.group(0)}
    found2 = list(PAT2.finditer(text))
    if found2:
        match = found2[-1]
        return {"kind": "2", "a": int(match.group(1)), "b": None, "span": match.group(0)}
    return None


def mapear_umv(unidad_venta: str, cantidad, minima, nombre: str) -> dict | None:
    """UMV del alta. None si no hay unidad de venta: ese SKU no se promueve.

    No escribe 1 en un factor que el nombre no trae. En BU, upb=1 es el factor
    real: el precio ya es el bulto y la cantidad de adentro no se copia.
    """
    uv = (unidad_venta or "").strip().upper()
    if uv not in {"UN", "DI", "BU"}:
        return None
    cant = _int(cantidad)
    minima_n = _int(minima) or 1
    pack = parse_pack(nombre)
    if uv == "BU":
        return _fila("unidad", None, None, 1, "bulto", minima_n, "BU", pack)
    if uv == "DI":
        upd = cant if cant and cant > 1 else None
        dpb = upb = None
        regla = "DI"
        if pack and pack["kind"] == "2":
            dpb = upb = pack["a"]
            regla = "DI+NxPeso"
        elif pack and pack["kind"] == "3":
            if upd is None and pack["b"] > 1:
                upd = pack["b"]
            dpb = upb = pack["a"]
            regla = "DI+AxBxPeso"
        return _fila("display", upd, dpb, upb, "display", minima_n, regla, pack)
    upd = dpb = upb = None
    regla = "UN"
    if pack and pack["kind"] == "2":
        upb = pack["a"]
        regla = "UN+NxPeso"
    elif pack and pack["kind"] == "3":
        upd = pack["b"] if pack["b"] > 1 else None
        dpb = pack["a"]
        upb = pack["a"] * pack["b"] if pack["b"] > 1 else pack["a"]
        regla = "UN+AxBxPeso"
    return _fila("unidad", upd, dpb, upb, "unidad", minima_n, regla, pack)


def _fila(umv, upd, dpb, upb, texto, minima, regla, pack) -> dict:
    return {
        "umv_tipo": umv,
        "upd": upd,
        "dpb": dpb,
        "upb": upb,
        "texto": texto,
        "min": minima,
        "regla": regla,
        "span": None if not pack else pack["span"],
    }


def refs_arc(code: str) -> list[str]:
    raw = (code or "").strip()
    digits = raw.lstrip("0") or "0"
    out: list[str] = []
    for body in (f"10{raw}", f"10{digits}", f"10{digits.zfill(5)}"):
        ref = f"ARC-{body}"
        if ref not in out:
            out.append(ref)
    return out


def _get(url: str) -> dict:
    last = None
    for attempt in range(4):
        req = urllib.request.Request(url, headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=40, context=_SSL) as resp:
                return json.load(resp)
        except Exception as exc:  # noqa: BLE001 — reintento de red
            last = exc
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(last)


def fetch_tokin(code: str) -> dict | None:
    for ref in refs_arc(code):
        url = f"{SEARCH}?query={urllib.parse.quote(ref)}&count=3&hideUnavailableItems=false"
        data = _get(url)
        for product in data.get("products") or []:
            if str(product.get("productReference") or "") == ref:
                conv = _conversiones(product)
                conv["ref"] = ref
                conv["nombre"] = product.get("productName") or ""
                return conv
    return None


def _conversiones(product: dict) -> dict:
    display_n = bulto_n = None
    bulto_de = None
    for group in product.get("specificationGroups") or []:
        if group.get("name") != "Conversiones de Unidades":
            continue
        for spec in group.get("specifications") or []:
            values = " ".join(spec.get("values") or [])
            name = spec.get("name") or ""
            if "1" in name:
                found = DISPLAY_RE.search(values)
                if found:
                    display_n = int(found.group(1))
            elif "2" in name:
                found = BULTO_RE.search(values)
                if found:
                    bulto_n = int(found.group(1))
                    bulto_de = "displays" if found.group(2).lower().startswith("display") else "unidades"
    return {"display_n": display_n, "bulto_n": bulto_n, "bulto_de": bulto_de}


def comparar(nuestro: dict, tokin: dict, gev_cant: int | None = None) -> tuple[str, str]:
    """Equivalencia comercial, no igualdad de columnas.

    Display 1 en Tokin es la unidad de venta. Si GEV además dice que ese
    display trae K piezas, K no contradice el 1 de Tokin.
    """
    if tokin.get("display_n") is None and tokin.get("bulto_n") is None:
        return "sin_conversion", "Tokin no publicó la conversión"
    t_upd = tokin["display_n"] if (tokin.get("display_n") or 0) > 1 else None
    if t_upd is None and gev_cant and gev_cant > 1 and nuestro.get("upd") == gev_cant:
        t_upd = gev_cant
    if tokin.get("bulto_de") == "displays":
        t_dpb = tokin["bulto_n"]
        t_piezas = None if t_dpb is None else t_dpb * (t_upd or 1)
    else:
        t_piezas = tokin.get("bulto_n")
        if t_upd and t_piezas and t_piezas % t_upd == 0:
            t_dpb = t_piezas // t_upd
        elif t_upd is None:
            t_dpb = None
        else:
            t_dpb = None
    fallos = []
    if (nuestro["upd"] or None) != t_upd:
        fallos.append(f"upd nuestro={nuestro['upd']} tokin={t_upd}")
    if nuestro["umv_tipo"] == "unidad":
        if t_piezas is not None and nuestro["upb"] != t_piezas:
            fallos.append(f"piezas/bulto nuestro={nuestro['upb']} tokin={t_piezas}")
        if t_dpb is not None and nuestro["dpb"] not in (None, t_dpb) and nuestro["dpb"] != t_dpb:
            fallos.append(f"dpb nuestro={nuestro['dpb']} tokin={t_dpb}")
    else:
        # La mínima es el display. El bulto de Tokin en unidades, con display 1,
        # es la misma cantidad de displays.
        esperado_dpb = t_dpb if t_dpb is not None else (t_piezas if t_upd is None else None)
        if esperado_dpb is not None and nuestro["dpb"] != esperado_dpb:
            fallos.append(f"dpb nuestro={nuestro['dpb']} tokin={esperado_dpb}")
    if fallos:
        return "diff", "; ".join(fallos)
    return "ok", ""


def evaluar(code: str, nombre: str, unidad: str, cantidad, minima) -> dict:
    nuestro = mapear_umv(unidad, cantidad, minima, nombre)
    if nuestro is None:
        return {"code": code, "estado": "sin_unidad", "detalle": "sin UNIDAD_VENTA", "nombre": nombre}
    try:
        tokin = fetch_tokin(code)
    except Exception as exc:  # noqa: BLE001
        return {"code": code, "estado": "error_tokin", "detalle": str(exc), "nuestro": nuestro, "nombre": nombre}
    if not tokin:
        return {"code": code, "estado": "sin_tokin", "detalle": "sin ARC", "nuestro": nuestro, "nombre": nombre}
    estado, detalle = comparar(nuestro, tokin, _int(cantidad))
    return {
        "code": code,
        "estado": estado,
        "detalle": detalle,
        "nombre": nombre,
        "nuestro": nuestro,
        "tokin": tokin,
    }


def _print(row: dict) -> None:
    nuestro = row.get("nuestro") or {}
    tokin = row.get("tokin") or {}
    print(
        f"{row['estado']:14} {row['code']:>8} {nuestro.get('regla',''):14} "
        f"umv={nuestro.get('umv_tipo','-'):8} upd={nuestro.get('upd')} dpb={nuestro.get('dpb')} upb={nuestro.get('upb')} "
        f"| tokin D={tokin.get('display_n')} B={tokin.get('bulto_n')} {tokin.get('bulto_de') or ''} "
        f"| {row.get('detalle','')}"
    )
    print(f"               {row.get('nombre','')[:90]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compara UMV del alta contra Tokin")
    parser.add_argument("--codes", help="Códigos separados por coma")
    parser.add_argument("--gev", type=Path, help="Snapshot getArticulos JSON")
    parser.add_argument("--limite", type=int, default=20)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    items: list[dict] = []
    if args.codes:
        wanted = [c.strip() for c in args.codes.split(",") if c.strip()]
        by = {}
        if args.gev:
            for row in json.loads(args.gev.read_text()):
                by[str(row.get("CODIGO_ARTICULO") or "").strip()] = row
        for code in wanted:
            row = by.get(code) or by.get(code.zfill(4)) or {}
            items.append(row or {"CODIGO_ARTICULO": code, "DESCRIPCION_ARTICULO": "", "UNIDAD_VENTA": "UN", "CANTIDAD_UNIDADES_UNIDAD_VENTA": "1", "UNIDAD_MINIMA_VENTA": "1"})
    elif args.gev:
        items = json.loads(args.gev.read_text())[: args.limite]
    else:
        parser.error("pasá --codes o --gev")
    results = []
    for row in items:
        code = str(row.get("CODIGO_ARTICULO") or "").strip()
        results.append(
            evaluar(
                code,
                str(row.get("DESCRIPCION_ARTICULO") or ""),
                str(row.get("UNIDAD_VENTA") or ""),
                row.get("CANTIDAD_UNIDADES_UNIDAD_VENTA"),
                row.get("UNIDAD_MINIMA_VENTA"),
            )
        )
        _print(results[-1])
        time.sleep(0.15)
    counts: dict[str, int] = {}
    for row in results:
        counts[row["estado"]] = counts.get(row["estado"], 0) + 1
    print("RESUMEN", counts)
    if args.json_out:
        args.json_out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if not any(r["estado"] == "error_tokin" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
