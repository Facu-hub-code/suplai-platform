from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path("implementacion")
OUTPUT_DIR_NAME = "outputs"
DEFAULT_TOTAL_TICKETS = 18
DEFAULT_OPEN_RATIO = 0.6
DEFAULT_OPEN_QUALITY = 3
DEFAULT_OPEN_LOGISTICS = 3
DEFAULT_OPEN_HOURS = (0, 12)
DEFAULT_CLOSED_DAYS = (5, 20)
DEFAULT_OPEN_DAYS = (0, 3)


def sanitize_schema_name(schema: str) -> str:
    if not schema or not all(c.isalnum() or c == "_" for c in schema):
        raise ValueError(f"Nombre de esquema invalido: {schema!r}")
    return schema


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


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


def seed_from_text(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def stable_rng(*parts: Any) -> random.Random:
    return random.Random(seed_from_text("|".join("" if p is None else str(p) for p in parts)))


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped.lower()).strip()


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
    phase_cfg = config.get("fase_08", {}) if isinstance(config, dict) else {}
    return {
        "schema": schema,
        "paths": paths,
        "manifest": manifest,
        "config": config,
        "fase_08": phase_cfg if isinstance(phase_cfg, dict) else {},
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
        raise ValueError("Fecha vacia")
    if "T" in raw:
        return datetime.fromisoformat(raw)
    if len(raw) == 10:
        return datetime.fromisoformat(f"{raw} 00:00:00")
    return datetime.fromisoformat(raw)


def format_dt(dt: datetime) -> str:
    return dt.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def load_clients(schema: str) -> list[dict[str, Any]]:
    paths = tenant_paths(schema)
    phase4 = read_csv_rows(paths["outputs"] / "phase-04-clientes.csv")
    phase5_path = paths["outputs"] / "phase-05-clientes-flags.csv"
    phase5 = read_csv_rows(phase5_path) if phase5_path.exists() else []
    flags_by_phone = {row.get("phone_number", ""): row for row in phase5 if row.get("phone_number")}

    clients: list[dict[str, Any]] = []
    for row in phase4:
        phone = row.get("phone_number", "")
        flags = flags_by_phone.get(phone, {})
        clients.append(
            {
                "cliente_phone": phone,
                "cliente_codigo": parse_int(flags.get("codigo_erp", row.get("codigo", 0)), 0),
                "cliente_razon_social": row.get("razon_social", ""),
                "cliente_nombre": row.get("nombre") or row.get("nombre_contacto") or row.get("razon_social", ""),
                "lista_precios_id": parse_int(row.get("lista_precios_id"), 1),
                "vendedor_nombre": row.get("vendedor_nombre", ""),
                "zona_idx": parse_int(row.get("zona_idx"), 0),
                "vendedor_idx": parse_int(row.get("vendedor_idx"), 0),
                "is_prospect": parse_bool(flags.get("is_prospect", "false")),
            }
        )
    clients.sort(key=lambda c: (c["cliente_codigo"], c["cliente_phone"]))
    return clients


def load_phase07_summary(schema: str) -> list[dict[str, Any]]:
    rows = read_csv_rows(tenant_paths(schema)["outputs"] / "phase-07-conversaciones-resumen.csv")
    return rows


def load_phase07_messages(schema: str) -> list[dict[str, Any]]:
    path = tenant_paths(schema)["outputs"] / "phase-07-mensajes.csv"
    if not path.exists():
        return []
    return read_csv_rows(path)


def load_orders(schema: str) -> list[dict[str, Any]]:
    rows = read_csv_rows(tenant_paths(schema)["outputs"] / "phase-06-pedidos.csv")
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "pedido_ref": row.get("pedido_ref", ""),
                "cliente_phone": row.get("cliente_phone", ""),
                "cliente_codigo": parse_int(row.get("cliente_codigo"), 0),
                "cliente_razon_social": row.get("cliente_razon_social", ""),
                "fecha": parse_dt(row.get("fecha", "2026-01-01 00:00:00")),
                "estado": row.get("estado", ""),
                "total": row.get("total", "0"),
                "notas": row.get("notas", ""),
                "is_mock": parse_bool(row.get("is_mock", "true")),
                "es_pedido_abierto": parse_bool(row.get("es_pedido_abierto", "false")),
                "lista_precios_id": parse_int(row.get("lista_precios_id"), 0),
            }
        )
    return out


def load_items(schema: str) -> list[dict[str, Any]]:
    rows = read_csv_rows(tenant_paths(schema)["outputs"] / "phase-06-items-pedido.csv")
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "pedido_ref": row.get("pedido_ref", ""),
                "cliente_phone": row.get("cliente_phone", ""),
                "cliente_codigo": parse_int(row.get("cliente_codigo"), 0),
                "product_code": row.get("product_code", ""),
                "nombre": row.get("nombre", ""),
                "cantidad_solicitada": parse_int(row.get("cantidad_solicitada"), 1),
                "precio_unitario": row.get("precio_unitario", "0"),
                "lista_precios_id": parse_int(row.get("lista_precios_id"), 0),
                "notas": row.get("notas", ""),
                "is_mock": parse_bool(row.get("is_mock", "true")),
                "es_pedido_abierto": parse_bool(row.get("es_pedido_abierto", "false")),
                "promo_aplicada": parse_bool(row.get("promo_aplicada", "false")),
            }
        )
    return out


def group_items_by_order(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[item["pedido_ref"]].append(item)
    return grouped


def load_catalog_products(schema: str) -> list[dict[str, Any]]:
    rows = read_csv_rows(tenant_paths(schema)["outputs"] / "phase-01-productos.csv")
    products: list[dict[str, Any]] = []
    for row in rows:
        products.append(
            {
                "product_code": row.get("product_code", ""),
                "nombre": row.get("nombre", ""),
                "descripcion": row.get("descripcion", ""),
                "aliases": row.get("aliases", ""),
                "precio_lista_1": parse_float(row.get("precio_lista_1"), 0.0),
                "rotacion_index": parse_float(row.get("rotacion_index"), 0.0),
                "is_mock": parse_bool(row.get("is_mock", "true")),
            }
        )
    products.sort(key=lambda p: (-p["rotacion_index"], p["product_code"]))
    return products


def load_promotions(schema: str) -> list[dict[str, Any]]:
    path = tenant_paths(schema)["outputs"] / "phase-02-promociones.csv"
    if not path.exists():
        return []
    rows = read_csv_rows(path)
    promos: list[dict[str, Any]] = []
    for row in rows:
        promos.append(
            {
                "promo_id": parse_int(row.get("promo_id"), 0),
                "product_code": row.get("product_code", ""),
                "titulo": row.get("titulo", ""),
                "descripcion": row.get("descripcion", ""),
                "discount_kind": row.get("discount_kind", ""),
                "discount_value": parse_float(row.get("discount_value"), 0.0),
                "lista_precios_id": parse_int(row.get("lista_precios_id"), 0),
                "min_qty_umv": parse_int(row.get("min_qty_umv"), 1),
                "fecha_inicio": row.get("fecha_inicio", ""),
                "fecha_fin": row.get("fecha_fin", ""),
                "activa": parse_bool(row.get("activa", "true")),
                "is_mock": parse_bool(row.get("is_mock", "true")),
            }
        )
    return promos


def latest_order_for_client(orders: list[dict[str, Any]], client_phone: str, open_only: bool = False) -> dict[str, Any] | None:
    matches = [o for o in orders if o["cliente_phone"] == client_phone and (o["es_pedido_abierto"] or not open_only)]
    if not matches:
        return None
    matches.sort(key=lambda o: (o["fecha"], o["pedido_ref"]))
    return matches[-1]


def client_display_name(client: dict[str, Any]) -> str:
    return client.get("cliente_razon_social") or client.get("cliente_nombre") or client.get("cliente_phone") or "cliente"


def order_items_lines(order_ref: str, items_by_order: dict[str, list[dict[str, Any]]], limit: int = 2) -> list[str]:
    items = items_by_order.get(order_ref, [])
    out: list[str] = []
    for item in items:
        name = item.get("nombre") or item.get("product_code") or ""
        if name and name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def deterministic_ticket_prefix(schema: str) -> int:
    return 2000 + (seed_from_text(schema) % 700)


def ticket_ref(prefix: int, index: int) -> str:
    return f"TKT-{prefix + index:04d}"


def ticket_category_pool() -> list[str]:
    return ["Calidad", "Logistica", "Comercial", "Administracion"]


def category_description(categoria: str, brand: str, product: str | None = None) -> tuple[str, str]:
    brand_product = product or "producto"
    if categoria == "Calidad":
        return (
            f"Reclamo de caja incompleta o producto dañado de {brand_product}",
            f"Hola, me llego {brand_product} en mal estado y quiero reclamar.",
        )
    if categoria == "Logistica":
        return (
            f"No recibio mercaderia del ultimo pedido de {brand_product}",
            f"Buen dia, sigo esperando el pedido y no llego el camion.",
        )
    if categoria == "Comercial":
        return (
            "Pide hablar con su vendedor o encargado comercial",
            "Necesito hablar con el encargado para revisar la cuenta.",
        )
    return (
        "Solicita correccion de datos administrativos en sistema",
        "Por favor, corrijan mis datos administrativos en el sistema.",
    )


def status_for_index(index: int, open_count: int) -> str:
    return "Abierto" if index < open_count else "Cerrado"


def ticket_created_at(base_dt: datetime, open_ticket: bool, index: int) -> datetime:
    if open_ticket:
        return base_dt - timedelta(days=index % 3, hours=(index * 3) % 12)
    return base_dt - timedelta(days=5 + (index % 16), hours=(index * 2) % 8)

