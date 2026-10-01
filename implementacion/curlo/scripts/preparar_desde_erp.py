#!/usr/bin/env python3
"""CURLO — genera CSV de implementación desde dumps de la API ERP (httpshare).

Lee implementacion/curlo/inputs/erp/*.json (sin token) y escribe outputs/phase-01/04/06.
No escribe en Supabase.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERP = ROOT / "inputs" / "erp"
OUT = ROOT / "outputs"
IMG_BASE = "https://curlomayorista.com.ar/imagenesproductos"
PREV_PRODUCTOS = OUT / "_backup_mock_2026-08" / "phase-01-productos.csv"
if not PREV_PRODUCTOS.exists():
    PREV_PRODUCTOS = OUT / "phase-01-productos.csv"

ESTADO_MAP = {
    "VENTA": "facturado",
    "RESERVA CONFIRMADA": "confirmado",
    "RESERVA": "pendiente",
    "RESERVA PREPARADA": "confirmado",
    "RESERVA CANCELADA": "cancelado",
    "VENTA CANCELADA": "cancelado",
    "RESERVA CONFIRMADA CANCELADA": "cancelado",
}


def load_rows(name: str) -> list[dict]:
    with (ERP / name).open(encoding="utf-8") as f:
        return json.load(f)["rows"]


def yes(val) -> bool:
    return str(val or "").strip().upper() == "SI"


def fnum(val, default=0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def sku_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def norm_phone(raw: str | None, area_default: str = "299") -> str:
    """Normaliza WhatsApp/teléfono AR a 549 + 10 dígitos. No inventa si no hay dígitos."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits:
        return ""
    if digits.startswith("549") and len(digits) >= 12:
        return digits[:13] if len(digits) >= 13 else digits
    if digits.startswith("54") and not digits.startswith("549") and len(digits) >= 11:
        rest = digits[2:]
        if rest.startswith("9"):
            return ("54" + rest)[:13]
        return ("549" + rest)[:13]
    if digits.startswith("0"):
        digits = digits.lstrip("0")
    # 0AAA 15 XXXXXXX  /  AAA15XXXXXXX
    m = re.match(r"(\d{2,4})15(\d{6,8})$", digits)
    if m:
        body = (m.group(1) + m.group(2))[:10]
        if len(body) == 10:
            return "549" + body
        if len(body) == 9:
            return "549" + body  # 12 dígitos totales; se acepta
    # móvil local 15XXXXXXX
    if digits.startswith("15") and 8 <= len(digits) <= 10:
        local = digits[2:]
        body = (area_default + local)[:10]
        if len(body) >= 9:
            return "549" + body
    if len(digits) == 10:
        return "549" + digits
    if len(digits) == 11:
        return "549" + digits[:10]
    if 8 <= len(digits) <= 9:
        body = (area_default + digits[-7:])[:10]
        return "549" + body
    if len(digits) > 11:
        m = re.match(r"(\d{2,4})15(\d{6,8})", digits)
        if m:
            body = (m.group(1) + m.group(2))[:10]
            if len(body) >= 9:
                return "549" + body
        return "549" + digits[:10]
    return ""


def parse_bulto(nombre: str, qty_min: float) -> int:
    text = nombre or ""
    m = re.search(r"(?:B/|x\s*|X\s*)(\d{1,4})\s*(?:UNIDADES|UNI|U\.?)\b", text, re.I)
    if m:
        n = int(m.group(1))
        return n if n > 1 else 1
    m = re.search(r"\b(\d{1,3})\s*X\s*(\d{1,3})\b", text, re.I)
    if m:
        return max(int(m.group(1)), int(m.group(2)))
    if qty_min and qty_min > 1:
        return int(qty_min)
    return 1


def short_desc(nombre: str, marca: str, categoria: str, prev: str | None) -> str:
    if prev:
        words = prev.split()
        if 8 <= len(words) <= 30:
            return prev
    cat = (categoria or "Insumo").split("/")[0].strip().title()
    marca = (marca or "").strip()
    nombre_l = (nombre or "").strip()
    parts = [cat.rstrip(".")]
    if nombre_l:
        parts.append(nombre_l)
    if marca and marca.upper() not in nombre_l.upper():
        parts.append(f"marca {marca}")
    text = ", ".join(p for p in parts if p) + "."
    words = text.split()
    if len(words) < 10:
        extra = "Presentación de catálogo mayorista para heladería y repostería."
        text = text.rstrip(".") + ". " + extra
    words = text.split()
    if len(words) > 25:
        text = " ".join(words[:25]).rstrip(",.") + "."
    return text


def aliases_for(nombre: str, sku: str, marca: str, prev: str | None) -> str:
    if prev:
        return prev
    bits = [nombre, sku]
    if marca:
        bits.append(marca)
        bits.append(f"{marca} {nombre.split()[0]}" if nombre else marca)
    return "|".join(b.strip() for b in bits if b and str(b).strip())


def load_prev_productos() -> dict[str, dict]:
    if not PREV_PRODUCTOS.exists():
        return {}
    with PREV_PRODUCTOS.open(encoding="utf-8") as f:
        return {r["product_code"]: r for r in csv.DictReader(f)}


def image_url(foto_1, foto_2, foto_3) -> str:
    urls = []
    for foto in (foto_1, foto_2, foto_3):
        name = (foto or "").strip()
        if name:
            urls.append(f"{IMG_BASE}/{name}")
    return " | ".join(urls)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)}")


def skus_en_pedidos_12m() -> set[str]:
    path = ERP / "pedidos_detalle_12m.json"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        rows = json.load(f).get("rows") or []
    return {sku_str(r.get("sku")) for r in rows if sku_str(r.get("sku"))}


def preparar_catalogo() -> tuple[list[dict], set[str]]:
    prev = load_prev_productos()
    productos = load_rows("productos.json")
    precios = load_rows("precios.json")
    listas = load_rows("listasprecios.json")
    vendidos = skus_en_pedidos_12m()

    precio_by = defaultdict(dict)  # sku -> lista_id -> precio
    for p in precios:
        sku = sku_str(p.get("sku"))
        if not sku or sku in {"-1", "0"}:
            continue
        lid = int(p["lista_id"])
        precio = fnum(p.get("precio"))
        if precio > 0:
            precio_by[sku][lid] = round(precio, 2)

    rows = []
    catalog_skus: set[str] = set()
    for p in productos:
        sku = sku_str(p.get("sku"))
        if not sku:
            continue
        activo = yes(p.get("activo"))
        precios_sku = precio_by.get(sku) or {}
        precio1 = precios_sku.get(1) or (min(precios_sku.values()) if precios_sku else 0)
        en_catalogo = activo and precio1 > 0
        if not en_catalogo and sku not in vendidos:
            continue
        catalog_skus.add(sku)
        old = prev.get(sku) or {}
        nombre = (p.get("nombre") or "").strip()
        marca = (p.get("marca") or "").strip()
        cat = (p.get("catalogo") or p.get("categoria") or "").strip()
        sub = (p.get("subcategoria") or "").strip()
        qty_min = fnum(p.get("cantidad_minima_venta"), 1) or 1
        bulto = parse_bulto(nombre, qty_min)
        stock = fnum(p.get("stock_disponible"))
        rows.append(
            {
                "product_code": sku,
                "nombre": nombre,
                "precio_lista_1": f"{precio1:.2f}",
                "stock": int(stock) if stock == int(stock) else stock,
                "unidades_por_bulto": bulto,
                "unidad_minima_de_venta": "unidad",
                "umv_tipo": "unidad",
                "categoria_1": cat or "CATALOGO",
                "categoria_2": (p.get("categoria") or "").strip(),
                "categoria_3": sub,
                "categoria_4": marca,
                "aliases": aliases_for(nombre, sku, marca, old.get("aliases")),
                "rotacion_index": old.get("rotacion_index") or "0.40",
                "mental_priority": old.get("mental_priority") or "0.3",
                "descripcion": short_desc(
                    nombre, marca, p.get("categoria") or cat, old.get("descripcion")
                ),
                "image_url": image_url(p.get("foto_1"), p.get("foto_2"), p.get("foto_3")),
                "en_catalogo": "true" if en_catalogo else "false",
                "is_mock": "false",
                "fuente_hoja": "erp",
                "marca": marca,
                "cantidad_minima_de_venta": int(qty_min) if qty_min >= 1 else 1,
            }
        )

    rows.sort(key=lambda r: (r["categoria_1"], r["nombre"], r["product_code"]))
    fields = [
        "product_code",
        "nombre",
        "precio_lista_1",
        "stock",
        "unidades_por_bulto",
        "unidad_minima_de_venta",
        "umv_tipo",
        "categoria_1",
        "categoria_2",
        "categoria_3",
        "categoria_4",
        "aliases",
        "rotacion_index",
        "mental_priority",
        "descripcion",
        "image_url",
        "en_catalogo",
        "is_mock",
        "fuente_hoja",
        "marca",
        "cantidad_minima_de_venta",
    ]
    write_csv(OUT / "phase-01-productos.csv", rows, fields)

    lista_rows = []
    for lp in sorted(listas, key=lambda x: int(x["lista_id"])):
        lid = int(lp["lista_id"])
        price_rows = []
        for sku, by_lista in precio_by.items():
            if sku not in catalog_skus:
                continue
            precio = by_lista.get(lid)
            if not precio:
                continue
            price_rows.append(
                {"product_code": sku, "precio_unidad": f"{precio:.2f}", "is_mock": "false"}
            )
        price_rows.sort(key=lambda r: r["product_code"])
        write_csv(OUT / f"phase-01-lista-precios-{lid}.csv", price_rows, ["product_code", "precio_unidad", "is_mock"])
        lista_rows.append(
            {
                "lista_precios_id": lid,
                "nombre": lp.get("lista_nombre") or f"Lista {lid}",
                "activa": "true" if yes(lp.get("activa")) else "false",
                "es_publica": "true",
                "is_mock": "false",
                "erp_list_id": lid,
                "filas_precio": len(price_rows),
            }
        )
    write_csv(
        OUT / "phase-01-listas-precios.csv",
        lista_rows,
        ["lista_precios_id", "nombre", "activa", "es_publica", "is_mock", "erp_list_id", "filas_precio"],
    )
    return rows, catalog_skus


def preparar_red(catalog_skus: set[str]) -> list[dict]:
    clientes = load_rows("clientes.json")
    domicilios = load_rows("clientes_domicilios.json")
    pedidos_path = ERP / "pedidos_12m.json"
    pedidos = load_rows("pedidos_12m.json") if pedidos_path.exists() else []

    dom_by_cli: dict[int, list[dict]] = defaultdict(list)
    for d in domicilios:
        dom_by_cli[int(d["cliente_id"])].append(d)

    seller_counter: dict[int, Counter] = defaultdict(Counter)
    seller_names: dict[int, str] = {}
    for p in pedidos:
        cid = int(p.get("cliente_id") or 0)
        vid = p.get("vendedor_id")
        nombre = (p.get("vendedor") or "").strip()
        if not cid or vid in (None, "", -10, "-10") or not nombre:
            continue
        vid = int(vid)
        seller_counter[cid][vid] += 1
        seller_names[vid] = nombre

    used_sellers = Counter()
    for cid, cnt in seller_counter.items():
        used_sellers[cnt.most_common(1)[0][0]] += 1

    vendedores = []
    for vid, nombre in sorted(seller_names.items(), key=lambda x: (-used_sellers[x[0]], x[1])):
        if used_sellers[vid] <= 0:
            continue
        slug = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
        slug = re.sub(r"[^a-z0-9]+", ".", slug).strip(".")
        vendedores.append(
            {
                "vendedor_codigo": vid,
                "nombre": nombre,
                "telefono": "",
                "email": "",
                "activo": "true",
                "is_mock": "false",
                "clientes_12m": used_sellers[vid],
            }
        )
    write_csv(
        OUT / "phase-04-vendedores.csv",
        vendedores,
        ["vendedor_codigo", "nombre", "telefono", "email", "activo", "is_mock", "clientes_12m"],
    )

    rows = []
    seen_phones: set[str] = set()
    for c in clientes:
        if not yes(c.get("activo")):
            continue
        cid = int(c["cliente_id"])
        razon = (c.get("razon_social") or "").strip()
        fantasia = (c.get("nombre_fantasia") or "").strip() or razon
        phone = norm_phone(c.get("whatsapp"))
        if not phone:
            for d in dom_by_cli.get(cid, []):
                phone = norm_phone(d.get("whatsapp")) or norm_phone(d.get("telefono_fijo"))
                if phone:
                    break
        if phone in seen_phones:
            phone = ""  # no duplicar WhatsApp; el segundo queda sin número
        if phone:
            seen_phones.add(phone)

        vid = seller_counter[cid].most_common(1)[0][0] if seller_counter[cid] else ""
        vendedor_nombre = seller_names.get(vid, "") if vid != "" else ""
        lista_id = int(c.get("lista_precio_id") or 1)
        if lista_id not in (1, 2, 3):
            lista_id = 1

        dir_parts = [
            (c.get("direccion") or "").strip(),
            (c.get("localidad") or "").strip(),
            (c.get("provincia") or "").strip(),
        ]
        direccion = ", ".join(p for p in dir_parts if p and p not in {"-", "- -"})

        rows.append(
            {
                "cliente_codigo": cid,
                "razon_social": razon,
                "nombre": fantasia,
                "phone_number": phone,
                "zona_codigo": "",
                "vendedor_codigo": vid,
                "vendedor_nombre": vendedor_nombre,
                "lat": "",
                "lng": "",
                "lista_precios_id": lista_id,
                "is_mock": "false",
                "cuit": (c.get("cuit") or "").strip(),
                "email": (c.get("email") or "").strip(),
                "direccion": direccion,
                "localidad": (c.get("localidad") or "").strip(),
                "provincia": (c.get("provincia") or "").strip(),
                "partner_erp_id": cid,
                "lifecycle": "client",
                "whatsapp_raw": (c.get("whatsapp") or "").strip(),
            }
        )

    rows.sort(key=lambda r: int(r["cliente_codigo"]))
    write_csv(
        OUT / "phase-04-clientes.csv",
        rows,
        [
            "cliente_codigo",
            "razon_social",
            "nombre",
            "phone_number",
            "zona_codigo",
            "vendedor_codigo",
            "vendedor_nombre",
            "lat",
            "lng",
            "lista_precios_id",
            "is_mock",
            "cuit",
            "email",
            "direccion",
            "localidad",
            "provincia",
            "partner_erp_id",
            "lifecycle",
            "whatsapp_raw",
        ],
    )
    return rows


def preparar_pedidos(catalog_skus: set[str]) -> None:
    pedidos_path = ERP / "pedidos_12m.json"
    det_path = ERP / "pedidos_detalle_12m.json"
    if not pedidos_path.exists():
        print("  skip pedidos: falta pedidos_12m.json")
        return
    pedidos = load_rows("pedidos_12m.json")
    detalles = []
    if det_path.exists():
        with det_path.open(encoding="utf-8") as f:
            payload = json.load(f)
        detalles = payload.get("rows") or []

    cli_ids = {int(c["cliente_id"]) for c in load_rows("clientes.json") if yes(c.get("activo"))}
    lines_by = defaultdict(list)
    extra_skus: set[str] = set()
    for ln in detalles:
        pid = int(ln["pedido_id"])
        sku = sku_str(ln.get("sku"))
        if sku and sku not in catalog_skus:
            extra_skus.add(sku)
        lines_by[pid].append(ln)

    ped_rows = []
    item_rows = []
    skipped = Counter()
    for p in pedidos:
        pid = int(p["pedido_id"])
        cid = int(p.get("cliente_id") or 0)
        estado_erp = (p.get("estado") or "").strip().upper()
        if estado_erp in {"RESERVA CANCELADA", "VENTA CANCELADA", "RESERVA CONFIRMADA CANCELADA"}:
            skipped["cancelado"] += 1
            continue
        if cid not in cli_ids:
            skipped["cliente_inactivo"] += 1
            continue
        lines = lines_by.get(pid) or []
        if not lines:
            skipped["sin_lineas"] += 1
            continue
        estado = ESTADO_MAP.get(estado_erp, "confirmado")
        abierto = estado_erp in {"RESERVA", "RESERVA PREPARADA"}
        ped_rows.append(
            {
                "pedido_ref": pid,
                "cliente_codigo": cid,
                "fecha": p.get("fecha"),
                "estado": estado,
                "total": f"{fnum(p.get('total')):.2f}",
                "notas": f"ERP {estado_erp} vendedor={p.get('vendedor') or ''}".strip(),
                "is_mock": "false",
                "es_pedido_abierto": "true" if abierto else "false",
                "origen": "erp",
                "erp_reference_id": pid,
                "vendedor_nombre": (p.get("vendedor") or "").strip(),
            }
        )
        for ln in lines:
            sku = sku_str(ln.get("sku"))
            item_rows.append(
                {
                    "pedido_ref": pid,
                    "product_code": sku,
                    "cantidad_solicitada": fnum(ln.get("cantidad")),
                    "precio_unitario": f"{fnum(ln.get('precio_unitario')):.2f}",
                    "lista_precios_id": "",
                    "notas": (ln.get("observacion") or "").strip(),
                    "is_mock": "false",
                    "nombre": (ln.get("producto") or "").strip(),
                }
            )

    write_csv(
        OUT / "phase-06-pedidos.csv",
        ped_rows,
        [
            "pedido_ref",
            "cliente_codigo",
            "fecha",
            "estado",
            "total",
            "notas",
            "is_mock",
            "es_pedido_abierto",
            "origen",
            "erp_reference_id",
            "vendedor_nombre",
        ],
    )
    write_csv(
        OUT / "phase-06-items-pedido.csv",
        item_rows,
        [
            "pedido_ref",
            "product_code",
            "cantidad_solicitada",
            "precio_unitario",
            "lista_precios_id",
            "notas",
            "is_mock",
            "nombre",
        ],
    )
    print(f"  pedidos skip={dict(skipped)} extra_skus_fuera_catalogo={len(extra_skus)}")


def main() -> None:
    print("== CURLO ERP → CSV ==")
    prod_rows, catalog_skus = preparar_catalogo()
    cli_rows = preparar_red(catalog_skus)
    preparar_pedidos(catalog_skus)

    con_wa = sum(1 for r in cli_rows if r["phone_number"])
    con_vend = sum(1 for r in cli_rows if r["vendedor_codigo"] != "")
    marcas = Counter(r.get("marca") or r["categoria_4"] for r in prod_rows)
    print(
        f"resumen: productos={len(prod_rows)} clientes={len(cli_rows)} "
        f"con_whatsapp={con_wa} con_vendedor={con_vend} marca_lider={marcas.most_common(1)}"
    )


if __name__ == "__main__":
    main()
