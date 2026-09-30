#!/usr/bin/env python3
"""Carga carousel_config en las agendas que usan `opciones_carrusel`.

La plantilla aprobada en Meta tiene 2 tarjetas con header IMAGE; sin
carousel_config el send sale sin componente carrusel y Meta responde #132012.
Las imágenes son las mismas que se subieron al crear la plantilla (verificado
byte a byte contra el example.header_handle de Meta).

  python implementacion/del_corro/scripts/parche_carrusel_opciones.py
  python implementacion/del_corro/scripts/parche_carrusel_opciones.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA = "del_corro"
TEMPLATE = "opciones_carrusel"
ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "implementacion" / "del_corro" / "outputs" / "carrusel-2026-09-30"
MEDIA_BASE = "https://cvlbietibaaehgeimxgw.supabase.co/storage/v1/object/public/meta_templates_media/"
CAROUSEL_CONFIG = [
    {"header_image_url": MEDIA_BASE + "del_corro/1790279003_del_corro_1790279002974_8f939445__NUEVOS_INGRESOS___-_Septiembre__2_.jpg"},
    {"header_image_url": MEDIA_BASE + "del_corro/1790279155_del_corro_1790279155611_ffad43df__NUEVOS_INGRESOS___-_Septiembre__5_.jpg"},
]

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend-supabase" / ".env")


def _db_url() -> str:
    url = (os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
    if not url:
        raise SystemExit("Falta DATABASE_URL")
    return url.replace(":5432/", ":6543/")


SELECT_SQL = f"""
    SELECT a.id, a.carousel_config::text AS carousel_config, a.dynamic_params::text AS dynamic_params,
           a.supabase_media_url, a.enviado_at, a.proxima_fecha_envio
    FROM {SCHEMA}.agenda a
    JOIN public.meta_plantillas mp ON mp.id = a.meta_plantilla_id
    WHERE mp.template_name = $1
    ORDER BY a.id;
"""


async def main(apply: bool) -> None:
    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        before = [dict(r) for r in await conn.fetch(SELECT_SQL, TEMPLATE)]
        print(f"Agendas con {TEMPLATE}: {[r['id'] for r in before]}")
        if not apply:
            print("Dry run. Usar --apply para escribir.")
            return

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = OUT_DIR / f"backup-agenda-{stamp}.json"
        backup.write_text(json.dumps(before, default=str, ensure_ascii=False, indent=1))
        print(f"Backup: {backup}")

        ids = [r["id"] for r in before]
        async with conn.transaction():
            n = await conn.execute(
                f"""
                UPDATE {SCHEMA}.agenda
                SET carousel_config = $1::jsonb,
                    dynamic_params = '[]'::jsonb
                WHERE id = ANY($2::int[]);
                """,
                json.dumps(CAROUSEL_CONFIG),
                ids,
            )
        print(n)

        after = await conn.fetch(
            f"""
            SELECT id, jsonb_array_length(carousel_config) AS n_cards, dynamic_params::text AS dynamic_params
            FROM {SCHEMA}.agenda WHERE id = ANY($1::int[]) ORDER BY id;
            """,
            ids,
        )
        for r in after:
            print(dict(r))
    finally:
        await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    asyncio.run(main(p.parse_args().apply))
