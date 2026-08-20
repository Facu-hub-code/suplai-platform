#!/usr/bin/env python3
"""Aplica Fase 1.2 benavidez: descripciones + alias en lotes, luego vectorize."""
from __future__ import annotations

import asyncio
import csv
import os
import sys
import unicodedata
from pathlib import Path

import asyncpg
import requests
from dotenv import load_dotenv

SCHEMA = "benavidez"  # confirmado
ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT.parent / "backend-supabase"
CSV_PATH = Path(__file__).resolve().parents[1] / "outputs" / "vista_previa_enriquecimiento.csv"
BATCH = 80
VECTORIZE_CHUNK = 200

load_dotenv(BACKEND_ROOT / ".env")
load_dotenv(ROOT / ".env")


def force_pooler(url: str) -> str:
    return url.replace(":5432/", ":6543/")


def normalizar_alias(alias_raw: str) -> str:
    alias_lower = alias_raw.lower().strip()
    alias_flat = unicodedata.normalize("NFKD", alias_lower)
    return "".join(c for c in alias_flat.encode("ascii", "ignore").decode("ascii") if c.isalnum())


async def main() -> int:
    print(f"[*] schema_name confirmado: {SCHEMA}")
    db_url = os.getenv("SUPABASE_DB_URL_POOLER") or os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] Falta SUPABASE_DB_URL_POOLER", file=sys.stderr)
        return 1
    db_url = force_pooler(db_url)
    backend = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")

    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    to_apply = []
    for r in rows:
        accion = (r.get("accion") or "ACTUALIZAR").strip().upper()
        code = (r.get("codigo_producto") or r.get("product_code") or "").strip()
        desc = (r.get("descripcion_mejorada") or "").strip()
        if accion not in {"ACTUALIZAR", "UPDATE"} or not code or not desc:
            continue
        aliases = [a.strip() for a in (r.get("alias_propuestos") or "").split("|") if a.strip()]
        to_apply.append((code, desc, aliases))
    print(f"[*] Aplicando {len(to_apply)} descripciones en lotes de {BATCH}")

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    updated = 0
    aliases_upserted = 0
    try:
        for i in range(0, len(to_apply), BATCH):
            chunk = to_apply[i : i + BATCH]
            codes = [c[0] for c in chunk]
            descs = [c[1] for c in chunk]
            await conn.execute(
                f"""
                UPDATE {SCHEMA}.productos p
                SET descripcion = v.descripcion, updated_at = now()
                FROM unnest($1::text[], $2::text[]) AS v(product_code, descripcion)
                WHERE p.product_code = v.product_code
                """,
                codes,
                descs,
            )
            updated += len(chunk)

            alias_codes: list[str] = []
            alias_raws: list[str] = []
            alias_norms: list[str] = []
            seen: set[tuple[str, str]] = set()
            for code, _desc, aliases in chunk:
                for raw in aliases:
                    norm = normalizar_alias(raw)
                    if not norm:
                        continue
                    key = (norm, code)
                    if key in seen:
                        continue
                    seen.add(key)
                    alias_codes.append(code)
                    alias_raws.append(raw)
                    alias_norms.append(norm)
            if alias_norms:
                await conn.execute(
                    f"""
                    INSERT INTO {SCHEMA}.productos_aliases
                        (alias_norm, alias_raw, product_code, weight, updated_at)
                    SELECT x.alias_norm, x.alias_raw, x.product_code, 1.0, now()
                    FROM unnest($1::text[], $2::text[], $3::text[])
                        AS x(alias_norm, alias_raw, product_code)
                    ON CONFLICT (alias_norm, product_code) DO UPDATE
                    SET alias_raw = EXCLUDED.alias_raw, updated_at = now()
                    """,
                    alias_norms,
                    alias_raws,
                    alias_codes,
                )
                aliases_upserted += len(alias_norms)
            print(f"  … {min(i + BATCH, len(to_apply))}/{len(to_apply)}", flush=True)
    finally:
        await conn.close()

    print(f"[+] Productos actualizados: {updated}")
    print(f"[+] Aliases upsert: {aliases_upserted}")

    codes_all = [c[0] for c in to_apply]
    print(f"[*] Vectorize {len(codes_all)} códigos en chunks de {VECTORIZE_CHUNK}")
    ok = 0
    for i in range(0, len(codes_all), VECTORIZE_CHUNK):
        part = codes_all[i : i + VECTORIZE_CHUNK]
        url = f"{backend}/{SCHEMA}/productos/vectorize"
        resp = requests.post(url, json=part, timeout=120)
        if resp.status_code != 200:
            print(f"[WARN] vectorize {resp.status_code}: {resp.text[:300]}")
        else:
            ok += len(part)
            print(f"  … vectorize {min(i + VECTORIZE_CHUNK, len(codes_all))}/{len(codes_all)}")
    print(f"[+] Vectorize encolado: {ok}/{len(codes_all)}")
    print(f"OK Fase 1.2 {SCHEMA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
