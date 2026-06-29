"""
habilitar_field.py
==================
Habilita Suplai Field App para el tenant:
  1. Actualiza public.distribuidoras.metadata → {"field_app_enabled": true}
  2. Verifica que el tenant esté activo y el schema exista.

Uso:
    python scripts/fase-06-1-field/habilitar_field.py --esquema <schema>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common_field import create_conn, sanitize_schema_name

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


async def habilitar(schema: str) -> None:
    conn = await create_conn()
    try:
        # 1. Verificar que el tenant existe
        row = await conn.fetchrow(
            "SELECT id, nombre, activa, metadata FROM public.distribuidoras WHERE schema_name = $1",
            schema,
        )
        if not row:
            raise SystemExit(f"[FAIL] No se encontró distribuidora con schema_name='{schema}'.")
        if not row["activa"]:
            print(f"[WARN] La distribuidora '{row['nombre']}' no está activa (activa=false). Continuando igual.")

        current_meta = row["metadata"] or {}
        if isinstance(current_meta, str):
            current_meta = json.loads(current_meta)

        already_enabled = current_meta.get("field_app_enabled") is True

        if already_enabled:
            print(f"[OK] field_app_enabled ya estaba activo para '{schema}'.")
            return

        # 2. Habilitar
        new_meta = {**current_meta, "field_app_enabled": True}
        await conn.execute(
            "UPDATE public.distribuidoras SET metadata = $1::jsonb WHERE schema_name = $2",
            json.dumps(new_meta),
            schema,
        )

        # 3. Verificar
        updated = await conn.fetchval(
            "SELECT metadata->>'field_app_enabled' FROM public.distribuidoras WHERE schema_name = $1",
            schema,
        )
        if updated != "true":
            raise SystemExit(f"[FAIL] La actualización de metadata falló. Verificar manualmente.")

        print(f"\n{'='*60}")
        print("HABILITACIÓN SUPLAI FIELD")
        print(f"{'='*60}")
        print(f"  Schema:          {schema}")
        print(f"  Distribuidora:   {row['nombre']}")
        print(f"  field_app_enabled: true  ✓")
        print(f"{'='*60}")
        print(f"\nEl job nocturno de tareas procesará este tenant a partir del próximo ciclo.")

    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Habilita Suplai Field App para el tenant.")
    parser.add_argument("--esquema", required=True)
    args = parser.parse_args()
    asyncio.run(habilitar(sanitize_schema_name(args.esquema)))


if __name__ == "__main__":
    main()
