#!/usr/bin/env python3
"""Aplica Fase 1.2 en curlo: solo descripcion + aliases. Resume filas pendientes."""
from __future__ import annotations

import csv
import os
import sys
import unicodedata
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "curlo"
CSV_IN = Path(__file__).resolve().parents[1] / "outputs" / "vista_previa_enriquecimiento.csv"
BATCH = 80


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def load_env() -> None:
    for path in (
        Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env"),
        Path(__file__).resolve().parents[3] / ".env",
    ):
        if path.exists():
            load_dotenv(path, override=False)


def normalizar_alias(alias_raw: str) -> str:
    flat = unicodedata.normalize("NFKD", alias_raw.lower().strip())
    return "".join(c for c in flat.encode("ascii", "ignore").decode("ascii") if c.isalnum())


async def main() -> int:
    load_env()
    print(f"[*] schema_name confirmado: {SCHEMA}")
    db_url = force_pooler(os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL") or "")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL", file=sys.stderr)
        return 1

    rows = [r for r in csv.DictReader(CSV_IN.open(encoding="utf-8")) if (r.get("accion") or "").upper() == "ACTUALIZAR"]
    print(f"[*] filas ACTUALIZAR={len(rows)}")

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        actuales = {
            r["product_code"]: (r["descripcion"] or "")
            for r in await conn.fetch(f"SELECT product_code, descripcion FROM {SCHEMA}.productos")
        }
        pending = []
        codes = []
        for row in rows:
            code = (row.get("codigo_producto") or "").strip()
            desc = (row.get("descripcion_mejorada") or "").strip()
            if not code or not desc:
                continue
            if code not in actuales:
                print(f"    skip inexistente {code}")
                continue
            codes.append(code)
            if actuales[code].strip() != desc:
                pending.append((desc, code))
        print(f"[*] pendientes descripcion={len(pending)} aliases_sobre={len(codes)}")

        for i in range(0, len(pending), BATCH):
            chunk = pending[i : i + BATCH]
            await conn.executemany(
                f"UPDATE {SCHEMA}.productos SET descripcion=$1, updated_at=now() WHERE product_code=$2",
                chunk,
            )
            print(f"    desc {i + 1}–{i + len(chunk)}")

        alias_rows = []
        seen = set()
        for row in rows:
            code = (row.get("codigo_producto") or "").strip()
            if code not in actuales:
                continue
            for raw in (row.get("alias_propuestos") or "").split("|"):
                raw = raw.strip()
                if not raw:
                    continue
                norm = normalizar_alias(raw)
                if not norm or "choclo" in norm:
                    continue
                key = (code, norm)
                if key in seen:
                    continue
                seen.add(key)
                alias_rows.append((code, raw, norm))
        print(f"[*] upsert aliases={len(alias_rows)}")
        for i in range(0, len(alias_rows), BATCH):
            await conn.executemany(
                f"""
                INSERT INTO {SCHEMA}.productos_aliases (product_code, alias_raw, alias_norm, weight, updated_at)
                VALUES ($1,$2,$3,1.0,now())
                ON CONFLICT (product_code, alias_norm) DO UPDATE
                SET alias_raw = EXCLUDED.alias_raw, updated_at = now()
                """,
                alias_rows[i : i + BATCH],
            )
            if i % 400 == 0:
                print(f"    aliases {i + 1}–{min(i + BATCH, len(alias_rows))}")

        verify = await conn.fetchrow(
            f"""
            SELECT
              (SELECT COUNT(*) FROM {SCHEMA}.productos WHERE en_catalogo) AS en_catalogo,
              (SELECT COUNT(*) FROM {SCHEMA}.productos_aliases) AS aliases,
              (SELECT COUNT(*) FROM {SCHEMA}.productos WHERE is_mock) AS mock
            """
        )
        print(f"[VERIFY] {dict(verify)}")
    finally:
        await conn.close()

    backend = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
    print(f"[*] vectorize {len(codes)} codes...")
    resp = requests.post(f"{backend}/{SCHEMA}/productos/vectorize", json=codes, timeout=180)
    print(f"[*] vectorize HTTP {resp.status_code}: {resp.text[:250]}")
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
