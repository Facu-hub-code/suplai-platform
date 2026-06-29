"""
seed_tareas_historicas.py
=========================
Siembra field_tasks COMPLETADAS y PARCIALES de los últimos 30 días laborables.

Optimizado para alta latencia (us-east desde Argentina):
  - 4 queries de lectura al inicio (bulk load)
  - 1 executemany para field_tasks (~540 rows)
  - 1 query bulk para recuperar IDs insertados
  - 1 executemany para field_point_ledger
  - 1 executemany para field_task_events

Uso:
    python scripts/fase-06-1-field/seed_tareas_historicas.py --esquema <schema> [--dias 30]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).parent))
from _common_field import (
    create_conn,
    get_active_mock_vendedores,
    get_active_task_templates,
    get_active_tournament,
    get_all_active_vendedores,
    load_all_clients_by_vendedor,
    load_vendedor_dia_visita_zones,
    sanitize_schema_name,
    workdays_back,
)

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

DIAS_ES = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def _seeded(schema: str, *parts) -> random.Random:
    import hashlib
    seed = hashlib.sha256("|".join(str(p) for p in [schema, *parts]).encode()).hexdigest()
    return random.Random(int(seed[:16], 16))


async def seed(schema: str, dias: int) -> None:
    conn = await create_conn()
    try:
        # -----------------------------------------------------------------------
        # 1. Carga bulk de todos los datos necesarios (4 queries en total)
        # -----------------------------------------------------------------------
        print(f"[*] Cargando datos del schema '{schema}'...")
        vendedores = await get_active_mock_vendedores(conn, schema)
        if not vendedores:
            vendedores = await get_all_active_vendedores(conn, schema)
        if not vendedores:
            raise SystemExit(f"[FAIL] No hay vendedores activos en {schema}.")

        templates          = await get_active_task_templates(conn, schema)
        torneo             = await get_active_tournament(conn, schema)
        clients_by_vendor  = await load_all_clients_by_vendedor(conn, schema)
        dias_visita_by_vid = await load_vendedor_dia_visita_zones(conn, schema)

        if not templates:
            raise SystemExit("[FAIL] No hay templates activos. Ejecutá setup_templates.py primero.")

        torneo_id = torneo["id"] if torneo else None
        target_dates = workdays_back(date.today(), dias)

        # -----------------------------------------------------------------------
        # 2. Generar todas las filas en Python (sin queries por tarea)
        # -----------------------------------------------------------------------
        tasks_to_insert:  list[tuple] = []
        task_meta:        list[dict]  = []   # para ledger y events (necesitamos el task_id después)

        for v in vendedores:
            vid         = int(v["id"])
            dias_visita = dias_visita_by_vid.get(vid, [])
            clientes    = clients_by_vendor.get(vid, [])
            if not clientes:
                continue

            for target_date in target_dates:
                weekday_es = DIAS_ES[target_date.weekday()]
                if weekday_es not in dias_visita:
                    continue

                rng = _seeded(schema, vid, target_date.isoformat())
                n_clientes = rng.randint(2, min(4, len(clientes)))
                chosen_clients = rng.sample(clientes, n_clientes)

                for client in chosen_clients:
                    cid = client["id"]

                    for tpl in templates:
                        tpl_id   = int(tpl["id"])
                        tipo     = str(tpl["tipo"])
                        puntos   = int(tpl["puntos_default"])
                        criterio = tpl.get("criterio_json") or {}
                        if isinstance(criterio, str):
                            criterio = json.loads(criterio)

                        roll = rng.random()
                        if roll < 0.60:
                            estado, earned_pts = "COMPLETADA", puntos
                        elif roll < 0.85:
                            estado, earned_pts = "PARCIAL", puntos // 2
                        else:
                            estado, earned_pts = "PENDIENTE", 0

                        desc = f"{tipo.replace('_', ' ').title()} — {client.get('nombre') or f'Cliente #{cid}'}"

                        inst_criterio = {
                            **criterio,
                            "evaluacion_cerrada": estado in ("COMPLETADA", "PARCIAL"),
                            "skus_cumplidos": [],
                            # puntos_obtenidos en criterio_json es lo que lee el BFF
                            # (no lo lee del field_point_ledger)
                            "puntos_obtenidos": earned_pts if earned_pts > 0 else None,
                        }

                        completada_at = None
                        if estado in ("COMPLETADA", "PARCIAL"):
                            completada_at = datetime(
                                target_date.year, target_date.month, target_date.day,
                                rng.randint(9, 17), rng.randint(0, 59), 0,
                            )

                        # Tupla para executemany — columnas en orden fijo
                        tasks_to_insert.append((
                            tpl_id,          # template_id
                            vid,             # vendedor_id
                            cid,             # cliente_id
                            tipo,            # tipo
                            desc,            # descripcion
                            puntos,          # puntos
                            estado,          # estado
                            json.dumps(inst_criterio),  # criterio_json
                            target_date,     # fecha
                            completada_at,   # completada_at
                        ))
                        task_meta.append({
                            "vendedor_id": vid,
                            "earned_pts":  earned_pts,
                            "torneo_id":   torneo_id,
                            "fecha":       target_date,
                            "estado":      estado,
                            "vnom":        v["nombre"],
                        })

        print(f"[*] {len(tasks_to_insert)} tareas a insertar. Ejecutando batch...")

        # -----------------------------------------------------------------------
        # 3. Batch INSERT field_tasks (1 executemany call)
        # -----------------------------------------------------------------------
        insert_sql = f"""
            INSERT INTO "{schema}".field_tasks
              (template_id, vendedor_id, cliente_id, tipo, descripcion, puntos,
               estado, criterio_json, fecha, completada_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
            ON CONFLICT (vendedor_id, cliente_id, tipo, fecha) DO NOTHING
        """
        await conn.executemany(insert_sql, tasks_to_insert)

        # -----------------------------------------------------------------------
        # 4. Recuperar IDs de las tareas recién insertadas (1 query bulk)
        # -----------------------------------------------------------------------
        # Usamos (vendedor_id, cliente_id, tipo, fecha) como clave natural
        inserted_task_rows = await conn.fetch(
            f"""
            SELECT id, vendedor_id, cliente_id, tipo, fecha
            FROM "{schema}".field_tasks
            WHERE (vendedor_id, cliente_id, tipo, fecha) = ANY(
                SELECT t.v, t.c, t.tp, t.f
                FROM UNNEST($1::int[], $2::int[], $3::text[], $4::date[]) AS t(v, c, tp, f)
            )
            """,
            [t[1] for t in tasks_to_insert],   # vendedor_id
            [t[2] for t in tasks_to_insert],   # cliente_id
            [t[3] for t in tasks_to_insert],   # tipo
            [t[8] for t in tasks_to_insert],   # fecha
        )
        # Construir mapa (vendedor_id, cliente_id, tipo, fecha) → task_id
        task_id_map: dict[tuple, int] = {
            (int(r["vendedor_id"]), int(r["cliente_id"]), str(r["tipo"]), r["fecha"]): int(r["id"])
            for r in inserted_task_rows
        }

        # -----------------------------------------------------------------------
        # 5. Batch INSERT field_point_ledger y field_task_events
        # -----------------------------------------------------------------------
        ledger_rows: list[tuple] = []
        event_rows:  list[tuple] = []

        for i, task_tuple in enumerate(tasks_to_insert):
            _, vid, cid, tipo, _, _, _, _, fecha, _ = task_tuple
            meta = task_meta[i]
            task_id = task_id_map.get((vid, cid, tipo, fecha))
            if task_id is None:
                continue  # Tarea ya existía (ON CONFLICT DO NOTHING)

            if meta["earned_pts"] > 0:
                ledger_rows.append((
                    vid,
                    task_id,
                    meta["earned_pts"],
                    meta["fecha"],
                    meta["torneo_id"],
                ))

            event_rows.append((
                task_id,
                meta["estado"],
                json.dumps({"source": "fase-06-1-field-seed", "vendedor": meta["vnom"]}),
            ))

        if ledger_rows:
            await conn.executemany(
                f"""
                INSERT INTO "{schema}".field_point_ledger
                  (vendedor_id, task_id, puntos, fecha, torneo_id)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (task_id) DO NOTHING
                """,
                ledger_rows,
            )

        if event_rows:
            await conn.executemany(
                f"""
                INSERT INTO "{schema}".field_task_events
                  (task_id, evento, metadata)
                VALUES ($1, $2, $3::jsonb)
                """,
                event_rows,
            )

        # -----------------------------------------------------------------------
        # 6. Verificación (2 queries)
        # -----------------------------------------------------------------------
        tasks_total  = await conn.fetchval(f'SELECT COUNT(*) FROM "{schema}".field_tasks')
        ledger_total = await conn.fetchval(f'SELECT COUNT(*) FROM "{schema}".field_point_ledger')

        print(f"\n{'='*60}")
        print("SEED TAREAS HISTÓRICAS FIELD")
        print(f"{'='*60}")
        print(f"  Días sembrados:     {dias} laborables hacia atrás")
        print(f"  Tareas generadas:   {len(tasks_to_insert)}")
        print(f"  IDs recuperados:    {len(task_id_map)}")
        print(f"  Puntos (ledger):    {len(ledger_rows)} entradas")
        print(f"  Eventos:            {len(event_rows)}")
        print(f"  Total tareas BD:    {tasks_total}")
        print(f"  Total ledger BD:    {ledger_total}")
        print(f"  Torneo vinculado:   {torneo_id or '(ninguno activo)'}")
        print(f"{'='*60}")

    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Siembra tareas históricas de Suplai Field.")
    parser.add_argument("--esquema", required=True)
    parser.add_argument("--dias", type=int, default=30, help="Días laborables hacia atrás (default: 30)")
    args = parser.parse_args()
    asyncio.run(seed(sanitize_schema_name(args.esquema), args.dias))


if __name__ == "__main__":
    main()
