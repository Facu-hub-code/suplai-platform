"""
setup_templates.py
==================
Verifica y/o crea los field_task_templates necesarios para Suplai Field.

Templates requeridos (con MEJORAR_MIX_RENTABLE excluido — no usamos tipo_venta):
  - REACTIVAR_CLIENTE   (puntos: 100)
  - CROSS_SELL_COMBO    (puntos:  75)
  - REPOSICION_HABITO   (puntos:  50)

Si un template ya existe para el tipo, no se toca. Si falta, se crea.
Los templates existentes de tipo CROSS_SELL_RENTABLE y MEJORAR_MIX_RENTABLE
son desactivados (no aplican al onboarding estándar sin tipo_venta).

Uso:
    python scripts/fase-06-1-field/setup_templates.py --esquema <schema>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent))
from _common_field import create_conn, sanitize_schema_name

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

# Templates que activamos
REQUIRED_TEMPLATES = [
    {
        "tipo": "REACTIVAR_CLIENTE",
        "nombre": "Reactivar cliente en riesgo",
        "descripcion_template": "Visitá a {cliente} — lleva {dias} días sin pedir. Ofrecé: {combo}.",
        "puntos_default": 100,
        "criterio_json": {
            "ventana_dias": 120,
            "top_n": 3,
            "delta_unidades": 1,
            "max_items": 5,
            "min_qty_per_sku": 1,
            "puntos_por_sku": 20,
            "bonus_completitud": 20,
        },
        "activo": True,
    },
    {
        "tipo": "CROSS_SELL_COMBO",
        "nombre": "Vender combo ML sugerido",
        "descripcion_template": "Para {cliente} el modelo sugiere: {combo}. ¡Cerrá el combo!",
        "puntos_default": 75,
        "criterio_json": {
            "min_qty_per_sku": 1,
            "puntos_por_sku": 30,
            "bonus_completitud": 15,
        },
        "activo": True,
    },
    {
        "tipo": "REPOSICION_HABITO",
        "nombre": "Reposición por hábito de compra",
        "descripcion_template": "Es momento de reponer para {cliente}: {detalle_skus}.",
        "puntos_default": 50,
        "criterio_json": {
            "days_ahead_max": 3,
            "max_items": 5,
            "min_qty_per_sku": 1,
            "puntos_por_sku": 15,
            "bonus_completitud": 20,
        },
        "activo": True,
    },
]

# Templates que desactivamos (no compatibles sin tipo_venta en productos)
DISABLE_TIPOS = {"MEJORAR_MIX_RENTABLE", "CROSS_SELL_RENTABLE"}


async def setup(schema: str) -> None:
    conn = await create_conn()
    try:
        # Verificar que la tabla existe
        table_exists = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=$1 AND table_name='field_task_templates' LIMIT 1",
            schema,
        )
        if not table_exists:
            raise SystemExit(
                f"[FAIL] Tabla field_task_templates no encontrada en schema '{schema}'.\n"
                "Verificar que Suplai Field esté migrado (SQL 55+)."
            )

        # Cargar templates existentes
        existing = await conn.fetch(
            f'SELECT id, tipo, activo FROM "{schema}".field_task_templates ORDER BY id'
        )
        existing_by_tipo: dict[str, dict] = {str(r["tipo"]): dict(r) for r in existing}

        created  = []
        already  = []
        disabled = []

        # Desactivar los que no usamos
        for tipo in DISABLE_TIPOS:
            if tipo in existing_by_tipo and existing_by_tipo[tipo]["activo"]:
                await conn.execute(
                    f'UPDATE "{schema}".field_task_templates SET activo=false, updated_at=now() '
                    f'WHERE tipo=$1',
                    tipo,
                )
                disabled.append(tipo)

        # Crear o confirmar los requeridos
        for tpl in REQUIRED_TEMPLATES:
            tipo = tpl["tipo"]
            if tipo in existing_by_tipo:
                # Activar si estaba inactivo
                if not existing_by_tipo[tipo]["activo"]:
                    await conn.execute(
                        f'UPDATE "{schema}".field_task_templates SET activo=true, updated_at=now() '
                        f'WHERE tipo=$1',
                        tipo,
                    )
                    already.append(f"{tipo} (reactivado)")
                else:
                    already.append(tipo)
            else:
                await conn.execute(
                    f"""
                    INSERT INTO "{schema}".field_task_templates
                      (tipo, nombre, descripcion_template, puntos_default, criterio_json, activo)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                    """,
                    tpl["tipo"],
                    tpl["nombre"],
                    tpl["descripcion_template"],
                    tpl["puntos_default"],
                    json.dumps(tpl["criterio_json"]),
                    tpl["activo"],
                )
                created.append(tipo)

        # Verificación final
        final = await conn.fetch(
            f'SELECT tipo, nombre, activo, puntos_default FROM "{schema}".field_task_templates ORDER BY id'
        )

        print(f"\n{'='*60}")
        print("SETUP FIELD TASK TEMPLATES")
        print(f"{'='*60}")
        print(f"  Creados:      {created or '(ninguno)'}")
        print(f"  Ya existían:  {already or '(ninguno)'}")
        print(f"  Desactivados: {disabled or '(ninguno)'}")
        print(f"\n  Estado final:")
        for r in final:
            estado = "✓ activo" if r["activo"] else "✗ inactivo"
            print(f"    [{estado:12s}] {r['tipo']:30s} ({r['puntos_default']} pts)")
        print(f"{'='*60}")

    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Configura field_task_templates para el tenant.")
    parser.add_argument("--esquema", required=True)
    args = parser.parse_args()
    asyncio.run(setup(sanitize_schema_name(args.esquema)))


if __name__ == "__main__":
    main()
