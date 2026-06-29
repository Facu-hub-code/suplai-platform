"""Utilidades compartidas para los scripts de Fase 6.1 — Field App Setup."""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import asyncpg
import yaml
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path("implementacion")
OUTPUT_DIR_NAME = "outputs"
FIELD_SOURCE_TAG = "fase-06-1-field"

# Días de la semana en español (0=lunes, 6=domingo) — alineado con el backend
DIAS_ES = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Vendedores mock creados en Fase 4 (se consultan en tiempo de ejecución)
VENDOR_IDS_MOCK_DEFAULT: list[int] = []


# ---------------------------------------------------------------------------
# Helpers generales
# ---------------------------------------------------------------------------

def sanitize_schema_name(schema: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema):
        raise ValueError(f"Nombre de esquema inválido: {schema!r}")
    return schema


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV no encontrado: {path}")
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def tenant_paths(schema: str) -> dict[str, Path]:
    base = BASE_DIR / schema
    return {
        "base": base,
        "manifest": base / "manifest.yaml",
        "config": base / "config.json",
        "outputs": base / OUTPUT_DIR_NAME,
    }


def load_manifest(schema: str) -> dict[str, Any]:
    paths = tenant_paths(schema)
    return read_yaml(paths["manifest"])


def parse_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "t", "yes", "y"}


def parse_int(v: Any, default: int = 0) -> int:
    if v is None or v == "":
        return default
    try:
        return int(float(str(v)))
    except Exception:
        return default


def parse_float(v: Any, default: float = 0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(str(v))
    except Exception:
        return default


def money(v: Any) -> Decimal:
    try:
        return Decimal(str(v or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


# ---------------------------------------------------------------------------
# Conexión a la BD (Transaction Mode pooler, port 6543)
# ---------------------------------------------------------------------------

def _get_db_url() -> str:
    raw = os.getenv("SUPABASE_DB_URL", "")
    if not raw:
        raise SystemExit("[FAIL] SUPABASE_DB_URL no está configurada en .env")
    # Forzar Transaction Mode pooler (port 6543) según reglas del workspace.
    return raw.replace(":5432/", ":6543/")


async def create_conn() -> asyncpg.Connection:
    url = _get_db_url()
    return await asyncpg.connect(url, statement_cache_size=0)


async def create_pool(min_size: int = 1, max_size: int = 2) -> asyncpg.Pool:
    url = _get_db_url()
    return await asyncpg.create_pool(
        url,
        min_size=min_size,
        max_size=max_size,
        statement_cache_size=0,
    )


# ---------------------------------------------------------------------------
# Helpers de BD de campo
# ---------------------------------------------------------------------------

async def get_active_mock_vendedores(conn: asyncpg.Connection, schema: str) -> list[dict]:
    """Devuelve los vendedores is_mock=true y activos del schema."""
    rows = await conn.fetch(
        f'SELECT id, nombre, telefono FROM "{schema}".vendedores '
        f'WHERE activo = true AND is_mock = true ORDER BY id;'
    )
    return [dict(r) for r in rows]


async def get_all_active_vendedores(conn: asyncpg.Connection, schema: str) -> list[dict]:
    rows = await conn.fetch(
        f'SELECT id, nombre, telefono FROM "{schema}".vendedores WHERE activo = true ORDER BY id;'
    )
    return [dict(r) for r in rows]


async def get_clients_for_vendedor(conn: asyncpg.Connection, schema: str, vendedor_id: int) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT c.id, c.nombre, c.phone_number, c.lista_precios_id
        FROM "{schema}".clients c
        JOIN "{schema}".vendedores_clientes vc ON vc.cliente_id = c.id
        WHERE vc.vendedor_id = $1 AND vc.activo = true
        ORDER BY c.id;
        """,
        vendedor_id,
    )
    return [dict(r) for r in rows]


async def load_all_clients_by_vendedor(
    conn: asyncpg.Connection, schema: str
) -> dict[int, list[dict]]:
    """Carga todos los clientes agrupados por vendedor_id en 1 sola query.
    Usar en lugar de llamar get_clients_for_vendedor en un loop.
    Retorna: {vendedor_id → [client_dict, ...]}.
    """
    rows = await conn.fetch(
        f"""
        SELECT vc.vendedor_id, c.id, c.nombre, c.phone_number, c.lista_precios_id
        FROM "{schema}".clients c
        JOIN "{schema}".vendedores_clientes vc ON vc.cliente_id = c.id
        WHERE vc.activo = true
        ORDER BY vc.vendedor_id, c.id;
        """
    )
    result: dict[int, list[dict]] = {}
    for r in rows:
        vid = int(r["vendedor_id"])
        result.setdefault(vid, []).append({
            "id":              r["id"],
            "nombre":          r["nombre"],
            "phone_number":    r["phone_number"],
            "lista_precios_id": r["lista_precios_id"],
        })
    return result


async def load_vendedor_dia_visita_zones(
    conn: asyncpg.Connection, schema: str
) -> dict[int, list[str]]:
    """Carga los dias_visita de las zonas de todos los vendedores en 1 query.
    Retorna: {vendedor_id → [dia_visita, ...]}.
    """
    rows = await conn.fetch(
        f"""
        SELECT vgz.vendedor_id, gz.dia_visita
        FROM "{schema}".vendedor_geo_zones vgz
        JOIN "{schema}".geo_zones gz ON gz.id = vgz.geo_zone_id
        WHERE vgz.activo = true AND gz.dia_visita IS NOT NULL
        """
    )
    result: dict[int, list[str]] = {}
    for r in rows:
        vid = int(r["vendedor_id"])
        result.setdefault(vid, []).append(str(r["dia_visita"]).lower())
    return result


async def get_top_products(conn: asyncpg.Connection, schema: str, limit: int = 20) -> list[dict]:
    rows = await conn.fetch(
        f"""
        SELECT product_code, nombre, rotacion_index
        FROM "{schema}".productos
        WHERE en_catalogo = true
        ORDER BY rotacion_index DESC NULLS LAST, product_code ASC
        LIMIT $1;
        """,
        limit,
    )
    return [dict(r) for r in rows]


async def get_price_for_product(
    conn: asyncpg.Connection, schema: str, product_code: str, lista_id: int
) -> Decimal:
    # Intentar con la lista del cliente primero, fallback a lista 1 (base).
    row = await conn.fetchrow(
        f"""
        SELECT precio_unidad FROM "{schema}".precios_productos
        WHERE product_code = $1 AND lista_precios_id = $2
        LIMIT 1;
        """,
        product_code,
        lista_id,
    )
    if row:
        return money(row["precio_unidad"])
    # Fallback: primer precio disponible para el producto en cualquier lista.
    row = await conn.fetchrow(
        f"""
        SELECT precio_unidad FROM "{schema}".precios_productos
        WHERE product_code = $1
        ORDER BY lista_precios_id ASC
        LIMIT 1;
        """,
        product_code,
    )
    return money(row["precio_unidad"]) if row else Decimal("1.00")


async def load_all_prices(conn: asyncpg.Connection, schema: str) -> dict[tuple[str, int], Decimal]:
    """Pre-carga todos los precios en memoria: {(product_code, lista_id) → precio_unidad}.
    Usar en scripts de generación masiva para evitar N+1 queries.
    """
    rows = await conn.fetch(
        f'SELECT product_code, lista_precios_id, precio_unidad FROM "{schema}".precios_productos'
    )
    prices: dict[tuple[str, int], Decimal] = {}
    # Primer precio de cada (product_code, lista) — en caso de duplicados toma el primero.
    for r in rows:
        key = (str(r["product_code"]), int(r["lista_precios_id"]))
        if key not in prices:
            prices[key] = money(r["precio_unidad"])
    return prices


def lookup_price(
    prices: dict[tuple[str, int], Decimal], product_code: str, lista_id: int
) -> Decimal:
    """Resuelve precio desde la caché pre-cargada. Fallback: lista 1, luego fallback fijo."""
    val = prices.get((product_code, lista_id))
    if val is not None:
        return val
    # Fallback: buscar la lista base (1)
    val = prices.get((product_code, 1))
    if val is not None:
        return val
    # Fallback: cualquier lista disponible para el producto
    for (code, _), price in prices.items():
        if code == product_code:
            return price
    return Decimal("1.00")


async def get_active_task_templates(conn: asyncpg.Connection, schema: str) -> list[dict]:
    rows = await conn.fetch(
        f'SELECT * FROM "{schema}".field_task_templates WHERE activo = true ORDER BY id;'
    )
    return [dict(r) for r in rows]


async def get_active_tournament(conn: asyncpg.Connection, schema: str) -> dict | None:
    row = await conn.fetchrow(
        f'SELECT id FROM "{schema}".field_tournaments WHERE estado = \'ACTIVO\' LIMIT 1;'
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Cálculo de días laborables anteriores (para seed histórico)
# ---------------------------------------------------------------------------

def workdays_back(from_date: date, n: int) -> list[date]:
    """Devuelve las últimas `n` fechas (sin domingos) anteriores a `from_date`."""
    days: list[date] = []
    cursor = from_date - timedelta(days=1)
    while len(days) < n:
        if cursor.weekday() != 6:  # 6 = domingo
            days.append(cursor)
        cursor -= timedelta(days=1)
    return days


def today() -> date:
    return date.today()
