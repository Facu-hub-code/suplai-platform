"""Utilidades compartidas para carga de ventas x artículo x cliente — el_gigante."""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import unicodedata
import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

import openpyxl
import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
for _extra_env in (
    ROOT.parent / "backend-supabase" / ".env",
    ROOT.parent / "agente-conversacional-multi_tenant" / ".env",
):
    if _extra_env.exists():
        load_dotenv(_extra_env)
load_dotenv()

DEFAULT_SCHEMA = "el_gigante"
DEFAULT_INPUT_DIR = Path.home() / "Desktop" / "el_gigante" / "ventas x articulo x cliente"

DEFAULT_MESES = ("marzo", "abril", "mayo", "junio")

MES_CONFIG: dict[str, dict[str, str | date]] = {
    "marzo": {
        "archivo": "marzo 26 vta x art cliente - vendedor - ruta.xlsx",
        "fecha_pedido": date(2026, 3, 15),
    },
    "abril": {
        "archivo": "abril 26 vta x art cliente - vendedor - ruta.xlsx",
        "fecha_pedido": date(2026, 4, 15),
    },
    "mayo": {
        "archivo": "mayo 26 vta x art cliente - vendedor- ruta.xlsx",
        "fecha_pedido": date(2026, 5, 15),
    },
    "junio": {
        "archivo": "junio 26 vta x art cliente - vendedor - ruta.xlsx",
        "fecha_pedido": date(2026, 6, 15),
    },
}

TAG_PREFIX = {
    "grupo": "Línea",
    "marca": "Marca",
    "proveedor": "Proveedor",
}

# Códigos contables / no producto en ventas ERP (rotación y pedidos)
SKIP_PRODUCT_CODES = {"10002", "10063", "10159", "10162"}

# EGRESO contable — no cargar como producto nuevo
SKIP_PRODUCT_LOAD_CODES = {"10002"}

PLACEHOLDER_IMAGE = "https://images.unsplash.com/photo-1542838132-92c53300491e?w=500&q=80"

# ERP ventas → vendedor Suplai (5 activos en red comercial)
VENDEDOR_ERP_ALIASES: dict[str, str] = {
    "fernando q": "Fernando",
    "fernando": "Fernando",
    "ivan gon": "Ivan",
    "ivan gonzalez": "Ivan",
    "ivan": "Ivan",
    "enrique gon": "Enrique",
    "enrique": "Enrique",
    "javier cabrera": "Javier",
    "javier": "Javier",
    "diego": "Diego",
    "cristian": "Diego",
    "rodrigo salas": "Fernando",
    "martin pereyra": "Diego",
    "luis": "Diego",
    "mica": "Ivan",
    "administrador": "Javier",
    "colman": "Diego",
    "marcos": "Diego",
}

# Ruta ERP → geo_zone.name (fuzzy manual)
RUTA_ZONE_ALIASES: dict[str, str] = {
    "venezuela": "Venezuela",
    "lote 110": "Lote 4",
    "lote 4": "Lote 4",
    "centro 2": "Centro 2",
    "centro 1": "Centro 1",
    "guadalupe": "Guadalupe",
    "don bosco": "Don Bosco",
    "don bosco´ii": "Don Bosco",
    "san miguel": "San Miguel",
    "san agustin": "San Agustin",
    "la paz": "La Paz",
    "liborsi": "Virgen del Rosario",
    "virgen del rosario": "Virgen del Rosario",
    "venta oficina": "Centro 1",
    "venta directa": "Centro 1",
    "la nueva formosa": "Malvinas",
    "independencia": "Juan Manuel de Rosas",
    "la colonia": "La Paz",
    "12 de octubre": "Evita",
    "fontana": "Fontana",
    "terminal": "Terminal",
    "parque urbano": "Parque Urbano",
    "mariano moreno": "Mariano Moreno",
    "juan manuel de rosas": "Juan Manuel de Rosas",
    "2 de abril": "2 de Abril",
    "7 de noviembre": "7 de Noviembre",
    "laguna siam": "Laguna Siam",
    "la pilar": "La pilar",
    "obrero": "Obrero",
    "san jose obrero": "San jose obrero",
    "san juan bautista": "San Juan Bautista",
    "villa hermosa": "Villa hermosa",
    "villa lourdes": "Villa Lourdes",
    "b vial": "B° vial",
}


def configure_stdout() -> None:
    if sys.platform.startswith("win"):
        sys.stdout.reconfigure(encoding="utf-8")


def pooler_url(url: str) -> str:
    if ":5432/" in url:
        return url.replace(":5432/", ":6543/")
    return url


def db_url() -> str:
    url = (
        os.getenv("SUPABASE_DB_URL_POOLER")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or ""
    )
    return pooler_url(url)


def tenant_outputs(schema: str) -> Path:
    return ROOT / "implementacion" / schema / "outputs"


def normalize_mes(mes: str) -> str:
    key = (mes or "").strip().lower()
    aliases = {
        "mar-jun": DEFAULT_MESES,
        "marzo-junio": DEFAULT_MESES,
        "marzo-jun": DEFAULT_MESES,
        "todos": DEFAULT_MESES,
        "all": DEFAULT_MESES,
    }
    if key in aliases:
        raise SystemExit(
            f"Usá parse_meses() para multi-mes ({mes!r}). "
            f"Meses individuales: {', '.join(MES_CONFIG)}"
        )
    if key not in MES_CONFIG:
        raise SystemExit(f"Mes inválido {mes!r}. Opciones: {', '.join(MES_CONFIG)}")
    return key


def parse_meses(mes: str | None = None, *, todos: bool = False) -> list[str]:
    """Resuelve --mes mar-jun | marzo | marzo,abril | --todos."""
    if todos:
        return list(DEFAULT_MESES)
    raw = (mes or "mar-jun").strip().lower()
    multi = {
        "mar-jun": list(DEFAULT_MESES),
        "marzo-junio": list(DEFAULT_MESES),
        "marzo-jun": list(DEFAULT_MESES),
        "todos": list(DEFAULT_MESES),
        "all": list(DEFAULT_MESES),
    }
    if raw in multi:
        return multi[raw]
    if "," in raw:
        return [normalize_mes(part) for part in raw.split(",") if part.strip()]
    return [normalize_mes(raw)]


def period_slug(meses: list[str]) -> str:
    if meses == list(DEFAULT_MESES):
        return "mar-jun"
    if len(meses) == 1:
        return meses[0]
    return "-".join(m[:3] for m in meses)


def excel_path_for_mes(mes: str, input_dir: Path | None = None) -> Path:
    cfg = MES_CONFIG[normalize_mes(mes)]
    base = input_dir or DEFAULT_INPUT_DIR
    path = base / str(cfg["archivo"])
    if not path.exists():
        raise SystemExit(f"No se encontró el Excel: {path}")
    return path


def fecha_pedido_for_mes(mes: str) -> date:
    return MES_CONFIG[normalize_mes(mes)]["fecha_pedido"]  # type: ignore[return-value]


def read_ventas_meses(meses: list[str], input_dir: Path | None = None) -> list[VentaRow]:
    rows: list[VentaRow] = []
    for mes in meses:
        rows.extend(read_ventas_excel(excel_path_for_mes(mes, input_dir)))
    return rows


def add_mes_arg(parser: argparse.ArgumentParser, default: str = "mar-jun") -> None:
    parser.add_argument(
        "--mes",
        default=default,
        help="mar-jun (default) | marzo | abril | mayo | junio | marzo,abril",
    )
    parser.add_argument(
        "--todos",
        action="store_true",
        help="Equivalente a --mes mar-jun (marzo–junio)",
    )


def tag_name(tipo: str, valor: str) -> str:
    prefix = TAG_PREFIX[tipo]
    valor = (valor or "").strip()
    return f"{prefix}: {valor}" if valor else ""


def to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def product_code_raw(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return str(int(value))
    return str(value).strip()


def client_code_raw(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return str(int(value))
    return str(value).strip().split(".")[0]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class VentaRow:
    grupo: str
    vendedor: str
    marca: str
    cod_art: str
    articulo: str
    ccliente: str
    cliente: str
    ruta: str
    cant_vendida: float
    cant_piezas: float
    total_costo: Decimal
    total_ventas_neto: Decimal
    total_ventas_final: Decimal
    proveedor: str

    @property
    def es_venta_positiva(self) -> bool:
        return self.cant_vendida > 0 and self.cod_art not in SKIP_PRODUCT_CODES


def read_ventas_excel(path: Path) -> list[VentaRow]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter)
    idx = {h: i for i, h in enumerate(header) if h is not None}

    def cell(row: tuple[Any, ...], name: str, default: Any = "") -> Any:
        i = idx.get(name)
        if i is None or i >= len(row):
            return default
        return row[i]

    out: list[VentaRow] = []
    for row in rows_iter:
        out.append(
            VentaRow(
                grupo=str(cell(row, "Grupo") or "").strip(),
                vendedor=str(cell(row, "Vendedor") or "").strip(),
                marca=str(cell(row, "MARCA") or "").strip(),
                cod_art=product_code_raw(cell(row, "CodArt")),
                articulo=str(cell(row, "Artículo") or "").strip(),
                ccliente=client_code_raw(cell(row, "CCLIENTE")),
                cliente=str(cell(row, "CLIENTE") or "").strip(),
                ruta=str(cell(row, "RUTA") or "").strip(),
                cant_vendida=to_float(cell(row, "Cant. Vendida")),
                cant_piezas=to_float(cell(row, "Cant. Piezas")),
                total_costo=to_decimal(cell(row, "Total Costo")),
                total_ventas_neto=to_decimal(cell(row, "Total Ventas Neto")),
                total_ventas_final=to_decimal(cell(row, "Total Ventas Final")),
                proveedor=str(cell(row, "PROVEEDOR") or "").strip(),
            )
        )
    wb.close()
    return out


def load_client_codes_from_outputs(schema: str) -> set[str]:
    codes: set[str] = set()
    outputs = tenant_outputs(schema)
    for path in sorted(outputs.glob("phase-04-clientes-*-all.csv")):
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                code = client_code_raw(row.get("codigo") or row.get("cliente_codigo"))
                if code:
                    codes.add(code)
    return codes


def load_catalog_product_codes(schema: str) -> set[str]:
    path = tenant_outputs(schema) / "phase-01-productos.csv"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as handle:
        return {row["product_code"].strip() for row in csv.DictReader(handle) if row.get("product_code")}


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


async def fetch_db_codes(schema: str) -> tuple[set[str], set[str]]:
    url = db_url()
    if not url:
        return set(), set()
    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        await conn.execute(f"SET search_path TO {schema}, core, public, extensions")
        products = {
            r["product_code"]
            for r in await conn.fetch(
                "SELECT product_code FROM productos WHERE COALESCE(is_mock,false)=false"
            )
        }
        clients = {
            client_code_raw(r["codigo"])
            for r in await conn.fetch(
                "SELECT codigo FROM clients WHERE codigo IS NOT NULL AND COALESCE(is_mock,false)=false"
            )
        }
        return products, clients
    finally:
        await conn.close()


def norm_match_key(text: str) -> str:
    s = unicodedata.normalize("NFKD", (text or "").strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def resolve_vendedor_canonico(erp_name: str) -> str:
    key = norm_match_key(erp_name)
    if key in VENDEDOR_ERP_ALIASES:
        return VENDEDOR_ERP_ALIASES[key]
    for token in key.split():
        for alias, canon in VENDEDOR_ERP_ALIASES.items():
            if alias.split()[0] == token or token in alias.split():
                return canon
    return ""


def resolve_zone_name_from_ruta(ruta: str) -> str:
    key = norm_match_key(ruta)
    if not key:
        return ""
    if key in RUTA_ZONE_ALIASES:
        return RUTA_ZONE_ALIASES[key]
    for alias, zone in RUTA_ZONE_ALIASES.items():
        if alias in key or key in alias:
            return zone
    return ruta.strip()


def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower()).strip("-")
    return s or "x"
