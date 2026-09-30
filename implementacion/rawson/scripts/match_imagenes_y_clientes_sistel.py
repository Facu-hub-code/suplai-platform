#!/usr/bin/env python3
"""Cruza el catálogo local (con fotos) contra Sistel y copia image_url a SKUs ERP.

También sondea clientes en la API. No purga mock.

    cd backend-supabase
    source venv/bin/activate
    PYTHONPATH=. python ../suplai-platform/implementacion/rawson/scripts/match_imagenes_y_clientes_sistel.py
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

PLATFORM_ROOT = Path(__file__).resolve().parents[3]
TENANT_DIR = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PLATFORM_ROOT.parent / "backend-supabase"
SCHEMA = "rawson"
OUT_DIR = TENANT_DIR / "outputs"
STOP = {
    "X",
    "U",
    "UN",
    "UNID",
    "UNIDAD",
    "UNIDADES",
    "POR",
    "P",
    "C",
    "DE",
    "CON",
    "PARA",
    "EL",
    "LA",
    "LOS",
    "LAS",
}


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip().strip("'\""))


_load_dotenv(TENANT_DIR / ".env")
_load_dotenv(BACKEND_ROOT / ".env")
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def norm_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    text = text.upper()
    text = re.sub(r"N[º°ª]", "N", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    tokens = [t for t in text.split() if t and t not in STOP]
    return " ".join(tokens)


def tokens(value: str) -> set[str]:
    return set(norm_name(value).split())


def score_names(left: str, right: str) -> float:
    a, b = norm_name(left), norm_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    jacc = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    return (ratio * 0.55) + (jacc * 0.45)


def _is_img(url: str) -> bool:
    return bool(url and url.strip().startswith("http"))


def load_local_with_images() -> list[dict]:
    by_code: dict[str, dict] = {}

    def add(code: str, nombre: str, image: str, source: str) -> None:
        code = str(code or "").strip()
        image = (image or "").strip()
        if not code or not _is_img(image):
            return
        prev = by_code.get(code)
        if prev and prev.get("image_url"):
            return
        by_code[code] = {"local_code": code, "nombre": (nombre or "").strip(), "image_url": image, "source": source}

    for path, code_key, name_key, img_key, source in (
        (TENANT_DIR / "inputs" / "rawson_productos.csv", "product_id", "nombre", "imagen_url", "web"),
        (TENANT_DIR / "inputs" / "catalogo-completo.csv", "product_code", "nombre", "image_url", "catalogo"),
        (TENANT_DIR / "outputs" / "phase-01-productos.csv", "product_code", "nombre", "image_url", "fase01"),
    ):
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                add(row.get(code_key, ""), row.get(name_key, ""), row.get(img_key, ""), source)
    return list(by_code.values())


def pick_match(local: dict, erp_rows: list[dict]) -> dict | None:
    local_name = local["nombre"]
    local_norm = norm_name(local_name)
    if not local_norm:
        return None

    exact = [row for row in erp_rows if norm_name(row.get("nombre") or "") == local_norm]
    if exact:
        if len(exact) == 1:
            return {**exact[0], "match": "nombre_exacto", "score": 1.0}
        exact.sort(
            key=lambda row: SequenceMatcher(
                None, (local_name or "").upper(), (row.get("nombre") or "").upper()
            ).ratio(),
            reverse=True,
        )
        best, runner = exact[0], exact[1]
        best_raw = SequenceMatcher(
            None, (local_name or "").upper(), (best.get("nombre") or "").upper()
        ).ratio()
        runner_raw = SequenceMatcher(
            None, (local_name or "").upper(), (runner.get("nombre") or "").upper()
        ).ratio()
        if best_raw >= 0.88 and (best_raw - runner_raw) >= 0.04:
            return {**best, "match": "nombre_exacto_desempate", "score": round(best_raw, 3)}
        return None

    ranked = []
    for row in erp_rows:
        sc = score_names(local_name, row.get("nombre") or "")
        raw = SequenceMatcher(
            None, (local_name or "").upper(), (row.get("nombre") or "").upper()
        ).ratio()
        if sc >= 0.90 or raw >= 0.90:
            ranked.append((max(sc, raw), row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return None
    best_score, best = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_score >= 0.92 and (best_score - second) >= 0.03:
        return {**best, "match": "nombre_fuzzy", "score": round(best_score, 3)}
    return None


async def main() -> None:
    from core.db import get_connection, validate_schema
    from erp.connectors.sistel import SistelConnector
    from erp.services.erp_customer_onboarding_service import sync_customers_to_raw
    from erp.services.erp_sync_service import save_erp_config

    base_url = os.environ.get("SISTEL_BASE_URL", "http://asp12.selfip.net:3448").rstrip("/")
    credentials = {
        "username": os.environ.get("SISTEL_USER", "SuplaiSales"),
        "password": os.environ.get("SISTEL_PASS", ""),
    }
    if not credentials["password"]:
        raise SystemExit("Falta SISTEL_PASS")

    local = load_local_with_images()
    print(f"[local] productos con imagen={len(local)}")

    connector = SistelConnector(base_url=base_url, credentials=credentials)
    erp_products = await connector.fetch_products()
    print(f"[sistel] productos={len(erp_products)}")

    customers = await connector.fetch_customers()
    extra_client_aliases = (
        "raw_clientes",
        "aw_clientes",
        "raw_cliente",
        "raw_cuentas",
        "clientes",
        "cuentas",
    )
    alias_counts: dict[str, int] = {"fetch_customers": len(customers)}
    for alias in extra_client_aliases:
        rows = await connector.fetch_vista(alias)
        alias_counts[alias] = len(rows)

    print(f"[sistel] clientes fetch_customers={len(customers)} aliases={alias_counts}")

    matches: list[dict] = []
    used_skus: set[str] = set()
    unmatched: list[dict] = []
    for item in local:
        hit = pick_match(item, erp_products)
        if not hit or hit["sku"] in used_skus:
            unmatched.append(item)
            continue
        used_skus.add(hit["sku"])
        matches.append(
            {
                "local_code": item["local_code"],
                "local_nombre": item["nombre"],
                "erp_sku": hit["sku"],
                "erp_nombre": hit["nombre"],
                "match": hit["match"],
                "score": hit["score"],
                "image_url": item["image_url"],
                "source": item["source"],
            }
        )

    print(f"[match] ok={len(matches)} sin_match={len(unmatched)}")

    conn = await get_connection()
    applied = 0
    already = 0
    missing_sku = 0
    try:
        schema = await validate_schema(SCHEMA, conn=conn)
        await conn.execute(
            f"""
            UPDATE "{schema}".productos
            SET image_url = NULL
            WHERE product_code = '40249'
              AND image_url ILIKE '%CEM12X50%'
            """
        )
        for row in matches:
            existing = await conn.fetchrow(
                f'SELECT product_code, image_url FROM "{schema}".productos WHERE product_code = $1 AND is_mock = false',
                row["erp_sku"],
            )
            if not existing:
                missing_sku += 1
                row["applied"] = "sku_ausente"
                continue
            if (existing["image_url"] or "").strip():
                already += 1
                row["applied"] = "ya_tenia"
                continue
            await conn.execute(
                f'UPDATE "{schema}".productos SET image_url = $1 WHERE product_code = $2 AND is_mock = false',
                row["image_url"],
                row["erp_sku"],
            )
            applied += 1
            row["applied"] = "copiada"
        with_img = await conn.fetchval(
            f"""
            SELECT count(*) FROM "{schema}".productos
            WHERE is_mock = false AND image_url IS NOT NULL AND length(trim(image_url)) > 0
            """
        )
        mock_clients = await conn.fetchval(
            f'SELECT count(*) FROM "{schema}".clients WHERE is_mock = true'
        )
        real_clients = await conn.fetchval(
            f'SELECT count(*) FROM "{schema}".clients WHERE COALESCE(is_mock, false) = false'
        )
    finally:
        await conn.close()

    customers_raw = None
    if customers:
        await save_erp_config(
            SCHEMA,
            connector="sistel",
            base_url=base_url,
            credentials=credentials,
            sync_frequency="6h",
            push_orders_enabled=False,
        )
        customers_raw = await sync_customers_to_raw(SCHEMA)
        print(f"[clientes] sync_raw={customers_raw}")

    OUT_DIR.mkdir(exist_ok=True)
    match_csv = OUT_DIR / "phase-10-match-imagenes-sistel.csv"
    with match_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "local_code",
                "local_nombre",
                "erp_sku",
                "erp_nombre",
                "match",
                "score",
                "applied",
                "image_url",
                "source",
            ],
        )
        writer.writeheader()
        writer.writerows(matches)
        for item in unmatched:
            writer.writerow(
                {
                    "local_code": item["local_code"],
                    "local_nombre": item["nombre"],
                    "erp_sku": "",
                    "erp_nombre": "",
                    "match": "sin_match",
                    "score": "",
                    "applied": "",
                    "image_url": item["image_url"],
                    "source": item["source"],
                }
            )

    summary = {
        "local_con_imagen": len(local),
        "sistel_productos": len(erp_products),
        "matches": len(matches),
        "unmatched": len(unmatched),
        "images_applied": applied,
        "already_had_image": already,
        "missing_sku": missing_sku,
        "erp_with_image": int(with_img or 0),
        "sistel_customers": len(customers),
        "alias_counts": alias_counts,
        "customers_raw": customers_raw,
        "db_mock_clients": int(mock_clients or 0),
        "db_real_clients": int(real_clients or 0),
        "match_csv": str(match_csv),
    }
    summary_path = OUT_DIR / "phase-10-match-imagenes-sistel.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[summary] {json.dumps(summary, ensure_ascii=False)}")


if __name__ == "__main__":
    asyncio.run(main())
