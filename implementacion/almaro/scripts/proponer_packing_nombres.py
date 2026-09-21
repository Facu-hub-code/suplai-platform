#!/usr/bin/env python3
"""Propone packing faltante de Almaro a partir del nombre Arcor/GEV.

No escribe en BD. Solo genera CSV en implementacion/almaro/outputs/.
Uso: python implementacion/almaro/scripts/proponer_packing_nombres.py
"""
from __future__ import annotations

import asyncio
import csv
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "outputs"
SCHEMA = "almaro"

PACK_3 = re.compile(
    r"(?<!\d)(\d{1,4})\s*[xX]\s*(\d{1,4})\s*[xX]\s*(\d{1,4}(?:[.,]\d+)?)\s*"
    r"(G|GR|GRS|KG|ML|L|U|UN|UNID|UNIDADES)?\b",
    re.I,
)
PACK_2 = re.compile(
    r"(?<!\d)(\d{1,4})\s*[xX]\s*(\d{1,4}(?:[.,]\d+)?)\s*"
    r"(G|GR|GRS|KG|ML|CC|L|U|UN|UNID|UNIDADES)?\b",
    re.I,
)

UNIDAD_HINTS = (
    "familiar",
    "taza",
    "pasta",
    "tallarin",
    "spaghetti",
    "mostachol",
    "penne",
    "fideo",
    "ñoqui",
    "ñoquis",
    "pizza",
    "membrillo",
    "tomate",
    "ketchup",
    "aceite",
    "bebida",
    "bolsa",
    "creatina",
    "ramen",
    "salsa",
    "lata",
    "estuche",
    "aireado",
    "block",
    "premezcla",
    "brownie",
    "torta",
)
DISPLAY_HINTS = (
    "mentho",
    "topline",
    "chupetin",
    "chicle",
    "gomita",
    "gomitas",
    "rockleton",
    "barrita",
    "medallon",
    "medallón",
    "mr pops",
    "graffiti",
    "butter toffe",
    "gajitos",
    "criollitas",
    "simple fibra",
    "simple vitalidad",
    "bocadito",
    "rocklets chico",
    "formis",
    "rumba",
    "serranita",
    "traviata",
    "porteñita",
    "cereales bag",
)
GALLETA_POR_HINTS = (
    "formis",
    "rumba",
    "serranita",
    "traviata",
    "criollita",
    "porteñita",
    "cereal",
    "por 3",
    "por 2",
    "por 4",
)


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def _norm(text: str | None) -> str:
    return (text or "").casefold()


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _hint_in(nombre: str, hints: tuple[str, ...]) -> str | None:
    n = _norm(nombre)
    for h in hints:
        if h in n:
            return h
    return None


@dataclass
class ParsedPack:
    patron: str
    a: int
    b: int | None
    contenido: str
    gramos: float | None
    fuente_nombre: str
    match: str


def _gramos(valor: str, unidad: str | None) -> float | None:
    try:
        n = float(valor.replace(",", "."))
    except ValueError:
        return None
    u = (unidad or "G").upper()
    if u == "KG":
        return n * 1000
    if u in {"L"}:
        return n * 1000
    if u in {"ML", "CC"}:
        return n
    if u in {"U", "UN", "UNID", "UNIDADES"}:
        return None
    return n


def parse_pack(nombre: str | None, fuente: str) -> ParsedPack | None:
    text = (nombre or "").strip()
    if not text:
        return None
    matches3 = list(PACK_3.finditer(text))
    if matches3:
        m = matches3[-1]
        a, b, contenido, unidad = m.group(1), m.group(2), m.group(3), m.group(4)
        return ParsedPack(
            patron="3_factores",
            a=int(a),
            b=int(b),
            contenido=f"{contenido}{(unidad or '')}".upper(),
            gramos=_gramos(contenido, unidad),
            fuente_nombre=fuente,
            match=m.group(0).replace(" ", "").upper(),
        )
    matches2 = list(PACK_2.finditer(text))
    if matches2:
        m = matches2[-1]
        a, contenido, unidad = m.group(1), m.group(2), m.group(3)
        return ParsedPack(
            patron="2_factores",
            a=int(a),
            b=None,
            contenido=f"{contenido}{(unidad or '')}".upper(),
            gramos=_gramos(contenido, unidad),
            fuente_nombre=fuente,
            match=m.group(0).replace(" ", "").upper(),
        )
    return None


def best_parse(nombre_almaro: str | None, nombre_gev: str | None) -> ParsedPack | None:
    p_a = parse_pack(nombre_almaro, "almaro")
    p_g = parse_pack(nombre_gev, "gev")
    if p_a and p_g:
        if p_g.patron == "3_factores" and p_a.patron != "3_factores":
            return p_g
        return p_a
    return p_a or p_g


def decide_umv(nombre: str, parsed: ParsedPack | None, umv_actual: str, gonzales_umv: str | None) -> tuple[str, str, str]:
    """Devuelve (umv, regla, confianza)."""
    if gonzales_umv in {"unidad", "display"}:
        return gonzales_umv, "umv_desde_gonzales", "alta"
    actual = (umv_actual or "unidad").strip().lower()
    if actual not in {"unidad", "display"}:
        actual = "unidad"
    if parsed is None:
        return actual, "sin_patron_conserva_umv", "alta" if actual else "baja"

    unidad_h = _hint_in(nombre, UNIDAD_HINTS)
    display_h = _hint_in(nombre, DISPLAY_HINTS)
    g = parsed.gramos

    if parsed.patron == "3_factores":
        por_pack = parsed.b in {2, 3, 4} and (
            (g is not None and g >= 80) or _hint_in(nombre, GALLETA_POR_HINTS)
        )
        if por_pack and not unidad_h:
            return "display", f"3f_pack_interno_{parsed.b}_display", "alta"
        if unidad_h and not display_h:
            return "unidad", f"3f_keyword_unidad:{unidad_h}", "alta"
        if display_h and not unidad_h:
            return "display", f"3f_keyword_display:{display_h}", "alta"
        if unidad_h and display_h:
            if display_h == "barrita":
                return "display", "3f_barrita_gana_taza", "alta"
            return "unidad", f"3f_conflicto_keywords:{unidad_h}|{display_h}", "baja"
        if g is not None and g >= 50:
            return "unidad", "3f_peso_ge_50g_unidad", "alta"
        if g is not None and g < 20:
            return "display", "3f_peso_lt_20g_display", "media"
        return "unidad", "3f_default_unidad_conservador", "media"

    # 2 factores
    if display_h and not unidad_h and (g is None or g >= 250 or (parsed.contenido.endswith(("U", "UN", "UNID", "UNIDADES")))):
        return "display", f"2f_keyword_display:{display_h}", "media"
    return actual if actual == "display" else "unidad", "2f_default_unidad", "alta"


def propose_row(row: dict[str, Any]) -> dict[str, Any] | None:
    nombre = row["nombre"] or ""
    nombre_gev = row["nombre_gev"] or ""
    parsed = best_parse(nombre, nombre_gev)
    umv_actual = (row["umv_tipo"] or "unidad").strip().lower()
    if umv_actual not in {"unidad", "display"}:
        umv_actual = "unidad"
    upd_a = _to_int(row["unidades_por_display"])
    dpb_a = _to_int(row["displays_por_bulto"])
    upb_a = _to_int(row["unidades_por_bulto"]) or 1
    g_umv = (row["g_umv_tipo"] or "").strip().lower() or None
    g_upd = _to_int(row["g_unidades_por_display"])
    g_dpb = _to_int(row["g_displays_por_bulto"])
    g_upb = _to_int(row["g_unidades_por_bulto"])

    default_pack = upb_a == 1 and upd_a is None and dpb_a is None
    gonzales_mejor = bool(
        g_umv
        and (
            (g_upb or 1) > 1
            or g_upd is not None
            or g_dpb is not None
        )
        and (
            default_pack
            or umv_actual != g_umv
            or upb_a != (g_upb or upb_a)
            or upd_a != g_upd
            or dpb_a != g_dpb
        )
    )

    umv_p, regla_umv, conf = decide_umv(
        f"{nombre} {nombre_gev}",
        parsed,
        umv_actual,
        g_umv if gonzales_mejor or (g_umv and not default_pack) else None,
    )
    if gonzales_mejor and g_umv in {"unidad", "display"}:
        umv_p = g_umv
        regla_umv = "copiar_gonzales"
        conf = "alta"

    upd_p, dpb_p, upb_p = upd_a, dpb_a, upb_a
    fuentes: list[str] = []
    notas: list[str] = []

    if gonzales_mejor:
        umv_p = g_umv or umv_p
        upd_p = g_upd if g_upd is not None else upd_p
        dpb_p = g_dpb if g_dpb is not None else dpb_p
        upb_p = g_upb if g_upb is not None else upb_p
        fuentes.append("gonzales")

    if parsed and parsed.patron == "3_factores":
        a, b = parsed.a, parsed.b or 0
        expected_unidad = a * b if b else a
        shape_display = (upb_p == a) or (g_upb == a) or umv_p == "display"
        shape_unidad = (upb_p == expected_unidad) or (g_upb == expected_unidad)
        if shape_display and not shape_unidad:
            umv_p = "display"
            if dpb_p is None or default_pack:
                dpb_p = a
            if default_pack or upb_p == 1:
                upb_p = a
            if upd_p is None and b:
                upd_p = b
            fuentes.append(f"nombre_{parsed.fuente_nombre}_3f_display")
        else:
            if umv_p == "display" and not shape_unidad:
                if dpb_p is None or default_pack:
                    dpb_p = a
                if default_pack or upb_p == 1:
                    upb_p = a
                if upd_p is None and b:
                    upd_p = b
                fuentes.append(f"nombre_{parsed.fuente_nombre}_3f_display")
            else:
                if upd_p is None and b:
                    upd_p = b
                if default_pack or upb_p == 1:
                    upb_p = expected_unidad
                    dpb_p = a if dpb_p is None else dpb_p
                elif expected_unidad and upb_p == expected_unidad and dpb_p is None:
                    dpb_p = a
                fuentes.append(f"nombre_{parsed.fuente_nombre}_3f_unidad")
                if not default_pack and expected_unidad and upb_p != expected_unidad and upb_p != a:
                    notas.append(f"nombre_implica_upb={expected_unidad}_actual={upb_p}")
                    conf = "baja"
                    dpb_p = dpb_a
    elif parsed and parsed.patron == "2_factores":
        a = parsed.a
        if umv_p == "display":
            if dpb_p is None or default_pack:
                dpb_p = a
            if default_pack or upb_p == 1:
                upb_p = a
            fuentes.append(f"nombre_{parsed.fuente_nombre}_2f_display")
        else:
            if default_pack or upb_p == 1:
                upb_p = a
            fuentes.append(f"nombre_{parsed.fuente_nombre}_2f_unidad")
            if not default_pack and upb_p != a:
                notas.append(f"nombre_implica_upb={a}_actual={upb_p}")

    # Completar dpb si hay cuenta exacta unidad × display.
    if umv_p == "unidad" and upd_p and upb_p and upb_p % upd_p == 0 and dpb_p is None:
        dpb_p = upb_p // upd_p
        fuentes.append("completar_dpb_upb_div_upd")
        if conf == "media":
            conf = "alta"

    umv_label_a = (row["unidad_minima_de_venta"] or "").strip()
    umv_label_p = "DISPLAY" if umv_p == "display" else "UNIDAD"
    if umv_label_a.upper() in {"DISPLAY", "UNIDAD"} and umv_p == umv_actual:
        umv_label_p = umv_label_a.upper()

    cambia = any(
        [
            umv_p != umv_actual,
            upd_p != upd_a,
            dpb_p != dpb_a,
            upb_p != upb_a,
        ]
    )
    if not cambia:
        return None

    if default_pack:
        accion = "cargar_packing_desde_nombre"
    elif gonzales_mejor:
        accion = "copiar_gonzales_y_completar"
    elif dpb_a is None and dpb_p is not None and upd_a == upd_p and upb_a == upb_p:
        accion = "completar_displays_por_bulto"
    elif upd_a is None and upd_p is not None:
        accion = "completar_unidades_por_display"
    else:
        accion = "revisar_ajuste"

    if notas:
        conf = "baja" if "implica_upb" in " ".join(notas) else conf

    return {
        "product_code": row["product_code"],
        "nombre_almaro": nombre,
        "nombre_gev": nombre_gev,
        "en_gonzales": "true" if row["g_product_code"] else "false",
        "umv_tipo_actual": umv_actual,
        "umv_tipo_propuesto": umv_p,
        "unidad_minima_de_venta_actual": umv_label_a,
        "unidad_minima_de_venta_propuesta": umv_label_p,
        "unidades_por_display_actual": upd_a or "",
        "unidades_por_display_propuesto": upd_p or "",
        "displays_por_bulto_actual": dpb_a or "",
        "displays_por_bulto_propuesto": dpb_p or "",
        "unidades_por_bulto_actual": upb_a,
        "unidades_por_bulto_propuesto": upb_p,
        "patron": parsed.patron if parsed else "",
        "factor_a": parsed.a if parsed else "",
        "factor_b": parsed.b if parsed and parsed.b else "",
        "contenido": parsed.contenido if parsed else "",
        "match_nombre": parsed.match if parsed else "",
        "regla": regla_umv,
        "fuente": "+".join(fuentes) if fuentes else "sin_cambio_util",
        "confianza": conf,
        "accion": accion,
        "notas": "; ".join(notas),
    }


FIELDS = [
    "product_code",
    "nombre_almaro",
    "nombre_gev",
    "en_gonzales",
    "umv_tipo_actual",
    "umv_tipo_propuesto",
    "unidad_minima_de_venta_actual",
    "unidad_minima_de_venta_propuesta",
    "unidades_por_display_actual",
    "unidades_por_display_propuesto",
    "displays_por_bulto_actual",
    "displays_por_bulto_propuesto",
    "unidades_por_bulto_actual",
    "unidades_por_bulto_propuesto",
    "patron",
    "factor_a",
    "factor_b",
    "contenido",
    "match_nombre",
    "regla",
    "fuente",
    "confianza",
    "accion",
    "notas",
]


def _self_check() -> None:
    cases = [
        ("AGUILA TAZA FAMILIAR 4X15X150G", "3_factores", 4, 15),
        ("CHOCO FLIAR AGUILA 4X15X150G", "3_factores", 4, 15),
        ("TAZA AGUILA 3 X 12 X 225G", "3_factores", 3, 12),
        ("ROCKLETS MINI BOLSA 32X150G", "2_factores", 32, None),
        ("ROCKLETS CHICO 12X24X20G", "3_factores", 12, 24),
        ("MENTHO PLUS MENTHOL 12X12X29.4G", "3_factores", 12, 12),
    ]
    for nombre, patron, a, b in cases:
        p = parse_pack(nombre, "test")
        assert p is not None, nombre
        assert p.patron == patron and p.a == a and p.b == b, (nombre, p)


async def main() -> int:
    _self_check()
    load_dotenv(ROOT.parent / "backend-supabase" / ".env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)
    OUT.mkdir(parents=True, exist_ok=True)

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        rows = await conn.fetch(
            """
            SELECT
              a.product_code,
              a.nombre,
              r.nombre AS nombre_gev,
              a.umv_tipo,
              a.unidad_minima_de_venta,
              a.unidades_por_display,
              a.displays_por_bulto,
              a.unidades_por_bulto,
              a.caja_semantica,
              g.product_code AS g_product_code,
              g.umv_tipo AS g_umv_tipo,
              g.unidades_por_display AS g_unidades_por_display,
              g.displays_por_bulto AS g_displays_por_bulto,
              g.unidades_por_bulto AS g_unidades_por_bulto
            FROM almaro.productos a
            LEFT JOIN almaro.erp_products_raw r ON r.sku = a.product_code
            LEFT JOIN gonzales.productos g ON g.product_code = a.product_code
            ORDER BY a.product_code
            """
        )
    finally:
        await conn.close()

    proposed: list[dict[str, Any]] = []
    for r in rows:
        item = propose_row(dict(r))
        if item:
            proposed.append(item)

    proposed.sort(key=lambda x: (x["confianza"], x["accion"], x["product_code"]))
    csv_path = OUT / "propuesta-packing-unidades-20260921.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(proposed)

    def count(pred) -> int:
        return sum(1 for p in proposed if pred(p))

    summary = {
        "catalogo": len(rows),
        "propuestas": len(proposed),
        "alta": count(lambda p: p["confianza"] == "alta"),
        "media": count(lambda p: p["confianza"] == "media"),
        "baja": count(lambda p: p["confianza"] == "baja"),
        "completar_dpb": count(lambda p: p["accion"] == "completar_displays_por_bulto"),
        "completar_upd": count(lambda p: p["accion"] == "completar_unidades_por_display"),
        "cargar_nombre": count(lambda p: p["accion"] == "cargar_packing_desde_nombre"),
        "copiar_gonzales": count(lambda p: p["accion"] == "copiar_gonzales_y_completar"),
        "revisar": count(lambda p: p["accion"] == "revisar_ajuste"),
        "sku_12901": next((p for p in proposed if p["product_code"] == "12901"), None),
    }
    print(f"OK {csv_path.name} catalogo={summary['catalogo']} propuestas={summary['propuestas']}")
    print(
        "confianza alta={alta} media={media} baja={baja} | "
        "dpb={completar_dpb} upd={completar_upd} nombre={cargar_nombre} "
        "gonzales={copiar_gonzales} revisar={revisar}".format(**summary)
    )
    if summary["sku_12901"]:
        s = summary["sku_12901"]
        print(
            f"12901 → upd {s['unidades_por_display_actual']}→{s['unidades_por_display_propuesto']} "
            f"dpb {s['displays_por_bulto_actual']}→{s['displays_por_bulto_propuesto']} "
            f"upb {s['unidades_por_bulto_actual']}→{s['unidades_por_bulto_propuesto']} "
            f"umv {s['umv_tipo_actual']}→{s['umv_tipo_propuesto']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
