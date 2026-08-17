#!/usr/bin/env python3
"""Marca clients Benfresh con phone USA válido como whatsapp_estado=existente.

Uso:
  set -a && source ../backend-supabase/.env && set +a
  python scripts/benfresh/backfill_whatsapp_existente_usa.py
  python scripts/benfresh/backfill_whatsapp_existente_usa.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "implementacion" / "benfresh" / "outputs"
SCHEMA = "benfresh"
USA_RE = re.compile(r"^1[2-9]\d{9}$")
CSV_FIELDS = [
    "id",
    "nombre",
    "phone_number",
    "digits",
    "whatsapp_estado_prev",
    "action",
]

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend-supabase" / ".env")


def _db_url() -> str:
    url = (
        os.getenv("SUPABASE_DB_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL / DATABASE_URL")
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    return url


def classify(digits: str, estado: str | None) -> str:
    if estado in ("validado", "existente", "no_existente"):
        return "skip_already"
    if digits.startswith("99"):
        return "skip_fake99"
    if USA_RE.match(digits):
        return "mark_existente"
    return "skip_invalid"


async def main(apply: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "whatsapp_usa_existente_dryrun.csv"
    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        rows = await conn.fetch(
            f"""
            SELECT id, nombre, phone_number, whatsapp_estado::text AS wa
            FROM {SCHEMA}.clients
            ORDER BY id
            """
        )
        report: list[dict[str, object]] = []
        to_mark: list[int] = []
        for r in rows:
            digits = re.sub(r"\D", "", r["phone_number"] or "")
            action = classify(digits, r["wa"])
            report.append(
                {
                    "id": r["id"],
                    "nombre": r["nombre"],
                    "phone_number": r["phone_number"],
                    "digits": digits,
                    "whatsapp_estado_prev": r["wa"],
                    "action": action,
                }
            )
            if action == "mark_existente":
                to_mark.append(int(r["id"]))

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            w.writerows(report)

        counts: dict[str, int] = {}
        for row in report:
            action = str(row["action"])
            counts[action] = counts.get(action, 0) + 1
        print(f"[*] total={len(report)} counts={counts} csv={csv_path}")
        if not apply:
            print("[*] Dry-run: no writes. Pass --apply to update.")
            return

        if not to_mark:
            print("[*] Nada para marcar.")
            return

        updated = await conn.execute(
            f"""
            UPDATE {SCHEMA}.clients
            SET whatsapp_estado = 'existente'::core.whatsapp_estado_cliente_enum,
                whatsapp_existencia_verificada_at = now(),
                whatsapp_validado_at = NULL,
                whatsapp_validado_por = NULL,
                updated_at = now()
            WHERE id = ANY($1::int[])
              AND whatsapp_estado = 'no_validado'::core.whatsapp_estado_cliente_enum
            """,
            to_mark,
        )
        print(f"[*] apply result: {updated}")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
