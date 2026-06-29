"""
setup_torneo.py
===============
Crea 1 torneo activo para el mes corriente en field_tournaments,
incluyendo a todos los vendedores mock activos del schema.

Si ya existe un torneo ACTIVO, no crea uno nuevo (avisa al implementador).

Uso:
    python scripts/fase-06-1-field/setup_torneo.py --esquema <schema>
    python scripts/fase-06-1-field/setup_torneo.py --esquema <schema> --forzar
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common_field import (
    create_conn,
    get_active_mock_vendedores,
    sanitize_schema_name,
    tenant_paths,
    write_csv_rows,
)

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


async def setup(schema: str, forzar: bool) -> None:
    today = date.today()
    conn  = await create_conn()
    try:
        # Verificar tabla
        table_ok = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=$1 AND table_name='field_tournaments' LIMIT 1",
            schema,
        )
        if not table_ok:
            raise SystemExit(f"[FAIL] Tabla field_tournaments no encontrada en schema '{schema}'.")

        # Verificar torneo activo existente
        existing = await conn.fetchrow(
            f"SELECT id, nombre FROM \"{schema}\".field_tournaments WHERE estado='ACTIVO' LIMIT 1"
        )
        if existing and not forzar:
            print(
                f"[INFO] Ya existe un torneo activo: '{existing['nombre']}' (id={existing['id']}).\n"
                f"       Usá --forzar para crear uno nuevo de todas formas.\n"
                f"       Si querés continuar con el existente, el CSV se exportará igual."
            )
            torneo_id = int(existing["id"])
        else:
            # Obtener vendedores mock
            vendedores = await get_active_mock_vendedores(conn, schema)
            if not vendedores:
                # Fallback: todos los activos
                from _common_field import get_all_active_vendedores
                vendedores = await get_all_active_vendedores(conn, schema)

            vendedor_ids = [v["id"] for v in vendedores]

            # Fechas: inicio y fin del mes actual
            mes_inicio = today.replace(day=1)
            ultimo_dia = calendar.monthrange(today.year, today.month)[1]
            mes_fin    = today.replace(day=ultimo_dia)

            nombre_torneo = f"Torneo {MESES_ES[today.month - 1]} {today.year}"
            premio_nota   = "Bonus de $5.000 + reconocimiento del equipo"

            row = await conn.fetchrow(
                f"""
                INSERT INTO "{schema}".field_tournaments
                  (nombre, fecha_inicio, fecha_fin, estado, premio_nota, vendedor_ids)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, nombre, fecha_inicio, fecha_fin;
                """,
                nombre_torneo,
                mes_inicio,
                mes_fin,
                "ACTIVO",
                premio_nota,
                vendedor_ids,
            )
            torneo_id = int(row["id"])

            print(f"\n{'='*60}")
            print("SETUP FIELD TOURNAMENT")
            print(f"{'='*60}")
            print(f"  Torneo:      {row['nombre']}")
            print(f"  Período:     {row['fecha_inicio']} → {row['fecha_fin']}")
            print(f"  Vendedores:  {[v['nombre'] for v in vendedores]}")
            print(f"  ID en BD:    {torneo_id}")
            print(f"{'='*60}")

        # CSV output
        paths   = tenant_paths(schema)
        csv_path = paths["outputs"] / "phase-06-1-torneo.csv"
        write_csv_rows(
            csv_path,
            [{"torneo_id": torneo_id, "schema": schema, "estado": "ACTIVO"}],
            ["torneo_id", "schema", "estado"],
        )
        print(f"  CSV: {csv_path}")

    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea el torneo mensual de Suplai Field.")
    parser.add_argument("--esquema", required=True)
    parser.add_argument("--forzar", action="store_true", help="Crea torneo aunque ya exista uno activo.")
    args = parser.parse_args()
    asyncio.run(setup(sanitize_schema_name(args.esquema), args.forzar))


if __name__ == "__main__":
    main()
