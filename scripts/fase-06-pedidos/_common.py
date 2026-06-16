from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

import yaml


BASE_DIR = Path("implementacion")
OUTPUT_DIR_NAME = "outputs"
DEFAULT_HISTORIC_START = date(2026, 3, 1)
DEFAULT_HISTORIC_END = date(2026, 5, 31)
DEFAULT_HISTORIC_PER_CLIENT = 3
DEFAULT_OPEN_ORDERS = 7
DEFAULT_OPEN_HOUR = 11
DEFAULT_OPEN_MINUTE = 15
DEFAULT_OPEN_STATUS_PRIORITY = ("abierto", "pendiente")
DEFAULT_HISTORIC_STATUSES = ("confirmado", "entregado", "facturado")
DEFAULT_MONEY_QUANT = Decimal("0.01")


def sanitize_schema_name(schema: str) -> str:
    if not schema or not all(c.isalnum() or c == "_" for c in schema):
        raise ValueError(f"Nombre de esquema invalido: {schema!r}")
    return schema


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"No se encontro el archivo CSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def money(value: Any) -> Decimal:
    return to_decimal(value).quantize(DEFAULT_MONEY_QUANT, rounding=ROUND_HALF_UP)


def as_money_str(value: Any) -> str:
    quantized = money(value)
    return format(quantized, "f")


def seed_from_text(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def stable_rng(*parts: Any) -> random.Random:
    joined = "|".join("" if p is None else str(p) for p in parts)
    return random.Random(seed_from_text(joined))


def strip_accents(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_text(text: str) -> str:
    return strip_accents((text or "").lower()).strip()


def tenant_paths(schema: str) -> dict[str, Path]:
    base = BASE_DIR / schema
    return {
        "base": base,
        "manifest": base / "manifest.yaml",
        "config": base / "config.json",
        "outputs": base / OUTPUT_DIR_NAME,
    }


def load_tenant_context(schema: str) -> dict[str, Any]:
    schema = sanitize_schema_name(schema)
    paths = tenant_paths(schema)
    manifest = read_yaml(paths["manifest"])
    config = read_json(paths["config"])
    fase_06_cfg = config.get("fase_06", {}) if isinstance(config, dict) else {}
    return {
        "schema": schema,
        "paths": paths,
        "manifest": manifest,
        "config": config,
        "fase_06": fase_06_cfg if isinstance(fase_06_cfg, dict) else {},
    }


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def parse_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value)))
    except Exception:
        return default


def parse_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(str(value))
    except Exception:
        return default


def parse_dt(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("No se puede parsear una fecha vacia")
    if "T" in raw:
        return datetime.fromisoformat(raw)
    if len(raw) == 10:
        return datetime.fromisoformat(f"{raw} 00:00:00")
    return datetime.fromisoformat(raw)


def format_dt(dt: datetime) -> str:
    return dt.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def get_client_sort_key(client: dict[str, Any]) -> tuple[int, int, str]:
    is_prospect = 1 if client.get("is_prospect") else 0
    codigo = parse_int(client.get("cliente_codigo"), 0)
    phone = client.get("cliente_phone") or client.get("phone_number") or ""
    return (is_prospect, codigo, phone)


def load_merged_clients(schema: str) -> list[dict[str, Any]]:
    paths = tenant_paths(schema)
    phase_04_path = paths["outputs"] / "phase-04-clientes.csv"
    phase_05_path = paths["outputs"] / "phase-05-clientes-flags.csv"

    clients_04 = read_csv_rows(phase_04_path)
    flags_05 = read_csv_rows(phase_05_path) if phase_05_path.exists() else []

    flags_by_phone = {row.get("phone_number", ""): row for row in flags_05 if row.get("phone_number")}
    merged: list[dict[str, Any]] = []

    for row in clients_04:
        phone = row.get("phone_number", "")
        flags = flags_by_phone.get(phone, {})
        cliente_codigo = parse_int(flags.get("codigo_erp", row.get("codigo", 0)), 0)
        is_prospect = parse_bool(flags.get("is_prospect", cliente_codigo == 0))
        merged.append(
            {
                "cliente_codigo": cliente_codigo,
                "cliente_phone": phone,
                "cliente_razon_social": row.get("razon_social", ""),
                "cliente_nombre": row.get("nombre_contacto") or row.get("nombre") or row.get("razon_social", ""),
                "lista_precios_id": parse_int(row.get("lista_precios_id"), 1),
                "vendedor_nombre": row.get("vendedor_nombre", ""),
                "vendedor_idx": parse_int(row.get("vendedor_idx"), 0),
                "zona_idx": parse_int(row.get("zona_idx"), 0),
                "lat": parse_float(row.get("lat")),
                "lng": parse_float(row.get("lng")),
                "is_prospect": is_prospect,
                "whatsapp_estado": flags.get("whatsapp_estado", ""),
                "whatsapp_validado_at": flags.get("whatsapp_validado_at", ""),
                "codigo_erp": cliente_codigo,
            }
        )

    merged.sort(key=get_client_sort_key)
    return merged


def load_catalog_products(schema: str) -> list[dict[str, Any]]:
    rows = read_csv_rows(tenant_paths(schema)["outputs"] / "phase-01-productos.csv")
    products: list[dict[str, Any]] = []
    for row in rows:
        products.append(
            {
                "product_code": row.get("product_code", ""),
                "nombre": row.get("nombre", ""),
                "precio_lista_1": money(row.get("precio_lista_1", 0)),
                "stock": parse_int(row.get("stock"), 0),
                "unidades_por_bulto": parse_int(row.get("unidades_por_bulto"), 1),
                "unidad_minima_de_venta": row.get("unidad_minima_de_venta", "unidad"),
                "umv_tipo": row.get("umv_tipo", "unidad"),
                "rotacion_index": parse_float(row.get("rotacion_index"), 0.0),
                "mental_priority": parse_float(row.get("mental_priority"), 0.0),
                "descripcion": row.get("descripcion", ""),
                "aliases": row.get("aliases", ""),
                "categoria_1": row.get("categoria_1", ""),
                "is_mock": parse_bool(row.get("is_mock", True)),
            }
        )
    products.sort(key=lambda p: (-p["rotacion_index"], p["product_code"]))
    return products


def load_prices(schema: str) -> dict[str, dict[int, Decimal]]:
    rows = read_csv_rows(tenant_paths(schema)["outputs"] / "phase-01-listas-precios.csv")
    prices: dict[str, dict[Any, Decimal]] = {}
    for row in rows:
        code = row.get("product_code", "")
        raw_lista_id = row.get("lista_precios_id") or row.get("lista_id") or row.get("lista") or ""
        if not code or not raw_lista_id:
            continue
        price = money(row.get("precio_unidad", row.get("precio", 0)))
        bucket = prices.setdefault(code, {})
        bucket[raw_lista_id] = price

        numeric_key = parse_int(raw_lista_id, 0)
        if numeric_key:
            bucket[numeric_key] = price
    return prices


def load_promotions(schema: str) -> dict[tuple[str, int], dict[str, Any]]:
    path = tenant_paths(schema)["outputs"] / "phase-02-promociones.csv"
    if not path.exists():
        return {}
    rows = read_csv_rows(path)
    promos: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        code = row.get("product_code", "")
        lista_id = parse_int(row.get("lista_precios_id"), 0)
        if not code or not lista_id:
            continue
        promos[(code, lista_id)] = {
            "promo_id": parse_int(row.get("promo_id"), 0),
            "product_code": code,
            "titulo": row.get("titulo", ""),
            "descripcion": row.get("descripcion", ""),
            "discount_kind": row.get("discount_kind", ""),
            "discount_value": money(row.get("discount_value", 0)),
            "lista_precios_id": lista_id,
            "min_qty_umv": parse_int(row.get("min_qty_umv"), 1),
            "fecha_inicio": row.get("fecha_inicio", ""),
            "fecha_fin": row.get("fecha_fin", ""),
            "activa": parse_bool(row.get("activa", True)),
            "is_mock": parse_bool(row.get("is_mock", True)),
        }
    return promos


def resolve_brand_leader_product(products: Iterable[dict[str, Any]], brand: str) -> dict[str, Any] | None:
    brand_norm = normalize_text(brand)
    if not brand_norm:
        return None

    matches = []
    for product in products:
        haystack = " ".join(
            [
                normalize_text(product.get("nombre", "")),
                normalize_text(product.get("aliases", "")),
                normalize_text(product.get("descripcion", "")),
            ]
        )
        if brand_norm in haystack:
            matches.append(product)

    if not matches:
        return None

    matches.sort(key=lambda p: (-p["rotacion_index"], p["product_code"]))
    return matches[0]


def pick_products_for_order(
    products: list[dict[str, Any]],
    rng: random.Random,
    quantity: int,
    exclude: set[str] | None = None,
) -> list[dict[str, Any]]:
    exclude = exclude or set()
    pool = [p for p in products if p["product_code"] not in exclude]
    if not pool:
        pool = list(products)
    sample_size = min(quantity, len(pool))
    if sample_size == len(pool):
        chosen = list(pool)
        rng.shuffle(chosen)
        return chosen[:quantity]
    return rng.sample(pool, sample_size)


def build_item_note(product: dict[str, Any], qty: int) -> str:
    sale_unit = (product.get("unidad_minima_de_venta") or "unidad").strip() or "unidad"
    canonical_unit = sale_unit if sale_unit else "unidad"
    bundle_size = max(parse_int(product.get("unidades_por_bulto"), 1), 1)
    normalized_qty = qty * bundle_size
    if bundle_size > 1:
        return f"Pedido: {qty} {sale_unit} (normalizado: {normalized_qty} {canonical_unit}; equiv: {qty} {sale_unit})"
    return f"Pedido: {qty} {sale_unit} (normalizado: {normalized_qty} {canonical_unit}; equiv: {qty} {sale_unit})"


def build_order_note(is_open: bool, promo_label: str = "", client_label: str = "") -> str:
    parts = ["Pedido abierto mock" if is_open else "Pedido historico mock"]
    if promo_label:
        parts.append(promo_label)
    if client_label:
        parts.append(client_label)
    return " - ".join(parts)


def apply_promo_price(base_price: Decimal, promo: dict[str, Any], qty: int) -> Decimal:
    discount_kind = promo.get("discount_kind", "")
    discount_value = money(promo.get("discount_value", 0))
    if discount_kind == "percent_off":
        factor = Decimal("1") - (discount_value / Decimal("100"))
        return money(base_price * factor)
    if discount_kind == "total_off":
        return money(max(base_price - discount_value, Decimal("0")))
    if discount_kind == "fixed_price":
        return money(discount_value)
    return money(base_price)


def historic_timestamp(index: int, repetition: int, cfg: dict[str, Any]) -> datetime:
    start_raw = cfg.get("historicos_inicio")
    end_raw = cfg.get("historicos_fin")
    start = date.fromisoformat(start_raw) if start_raw else DEFAULT_HISTORIC_START
    end = date.fromisoformat(end_raw) if end_raw else DEFAULT_HISTORIC_END
    span_days = max((end - start).days, 1)
    day_offset = (index * 7 + repetition * 17) % (span_days + 1)
    base_day = start + timedelta(days=day_offset)
    hour = 8 + ((index * 3 + repetition) % 10)
    minute = (index * 11 + repetition * 19) % 60
    second = (index * 23 + repetition * 7) % 60
    return datetime(base_day.year, base_day.month, base_day.day, hour, minute, second)


def open_timestamp(cfg: dict[str, Any], index: int) -> datetime:
    fecha_raw = cfg.get("fecha_abiertos")
    if fecha_raw:
        base_day = date.fromisoformat(fecha_raw)
    else:
        base_day = date.today()
    hour = parse_int(cfg.get("hora_abiertos"), DEFAULT_OPEN_HOUR)
    minute = parse_int(cfg.get("minuto_abiertos"), DEFAULT_OPEN_MINUTE)
    second = (index * 13) % 60
    return datetime(base_day.year, base_day.month, base_day.day, hour, minute, second)


def order_reference(index: int) -> str:
    return f"P-{index:05d}"
