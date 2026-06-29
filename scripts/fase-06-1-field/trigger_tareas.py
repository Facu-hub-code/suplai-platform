"""
trigger_tareas.py
=================
Genera tareas Suplai Field para HOY (y días adicionales) directamente vía
asyncpg + ML API, sin depender de que el backend tenga el endpoint
trigger-daily-tasks desplegado.

Lógica (replica FieldTaskService.ensure_daily_tasks):
  1. Por cada vendedor activo con zonas activas cuyo dia_visita == hoy:
  2. Obtener clientes inactivos (último pedido > INACTIVITY_DAYS) → REACTIVAR_CLIENTE
  3. Llamar ML /predict-combo por cliente activo → CROSS_SELL_COMBO
  4. Llamar ML /predict-replenishment por cliente activo → REPOSICION_HABITO
  5. Insertar field_tasks en batch (ON CONFLICT DO NOTHING)
  6. Insertar ledger initial (puntos pendientes = 0, se actualizan al evaluar pedido)

Uso:
    python scripts/fase-06-1-field/trigger_tareas.py --esquema <schema>
    python scripts/fase-06-1-field/trigger_tareas.py --esquema <schema> --dias 6
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from _common_field import (
    DIAS_ES,
    create_conn,
    get_active_task_templates,
    get_active_tournament,
    get_all_active_vendedores,
    load_all_clients_by_vendedor,
    load_vendedor_dia_visita_zones,
    sanitize_schema_name,
)

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

INACTIVITY_DAYS    = 60    # Días sin pedido → cliente en riesgo
RECENT_WINDOW_DAYS = 90    # Ventana para considerar compras recientes (ML)


def _ml_headers() -> dict[str, str]:
    key = os.getenv("SALES_ENGINE_API_KEY", "")
    return {"X-API-Key": key} if key else {}


def _ml_base() -> str:
    return os.getenv("SALES_ENGINE_URL", "").rstrip("/")


async def get_last_order_dates(conn, schema: str) -> dict[int, date]:
    """Devuelve {cliente_id → fecha_ultimo_pedido}. 1 sola query."""
    rows = await conn.fetch(
        f"""
        SELECT cliente_id, MAX(fecha::date) AS ultima_fecha
        FROM "{schema}".pedidos
        WHERE estado IN ('confirmado', 'entregado', 'facturado', 'descargado')
        GROUP BY cliente_id
        """
    )
    return {int(r["cliente_id"]): r["ultima_fecha"] for r in rows}


async def get_recent_purchase_counts(conn, schema: str) -> dict[int, int]:
    """Cuenta pedidos de los últimos 90 días por cliente. 1 sola query."""
    rows = await conn.fetch(
        f"""
        SELECT cliente_id, COUNT(*) AS cnt
        FROM "{schema}".pedidos
        WHERE estado IN ('confirmado', 'descargado')
          AND fecha >= CURRENT_DATE - INTERVAL '{RECENT_WINDOW_DAYS} days'
        GROUP BY cliente_id
        """
    )
    return {int(r["cliente_id"]): int(r["cnt"]) for r in rows}


def call_ml_combo(schema: str, cliente_id: int, product_codes: list[str], http: httpx.Client) -> list[str]:
    """Llama /predict-combo. Devuelve lista de SKUs sugeridos. [] si error/caído."""
    try:
        resp = http.post(
            f"{_ml_base()}/v1/tenants/{schema}/predict-combo",
            json={"cliente_id": cliente_id, "current_items": product_codes},
            timeout=8.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return [r["product_code"] for r in data.get("recommendations", [])[:3]]
    except Exception:
        pass
    return []


def call_ml_replenishment(schema: str, cliente_id: int, http: httpx.Client) -> list[dict]:
    """Llama /predict-replenishment. Devuelve lista de {product_code, days_until_due}. [] si error."""
    try:
        resp = http.get(
            f"{_ml_base()}/v1/tenants/{schema}/predict-replenishment",
            params={"cliente_id": cliente_id},
            timeout=8.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            due = [
                r for r in data.get("predictions", [])
                if r.get("days_until_due", 999) <= 3
            ]
            return due[:3]
    except Exception:
        pass
    return []


async def generate_tasks_for_date(schema: str, target_date: date) -> dict:
    conn = await create_conn()
    stats = {"date": target_date.isoformat(), "inserted": 0, "skipped": 0, "ml_errors": []}
    try:
        vendedores        = await get_all_active_vendedores(conn, schema)
        templates         = await get_active_task_templates(conn, schema)
        torneo            = await get_active_tournament(conn, schema)
        clients_by_vendor = await load_all_clients_by_vendedor(conn, schema)
        dias_by_vid       = await load_vendedor_dia_visita_zones(conn, schema)
        last_orders       = await get_last_order_dates(conn, schema)
        recent_counts     = await get_recent_purchase_counts(conn, schema)

        torneo_id     = torneo["id"] if torneo else None
        weekday_es    = DIAS_ES[target_date.weekday()]
        tpl_by_tipo   = {str(t["tipo"]): t for t in templates}

        tasks_to_insert: list[tuple] = []

        with httpx.Client() as http:
            for v in vendedores:
                vid         = int(v["id"])
                dias_visita = dias_by_vid.get(vid, [])
                if weekday_es not in dias_visita:
                    continue

                clientes = clients_by_vendor.get(vid, [])
                today    = date.today()

                for client in clientes:
                    cid  = int(client["id"])
                    name = client.get("nombre") or f"Cliente #{cid}"

                    last_order = last_orders.get(cid)
                    days_inactive = (today - last_order).days if last_order else 999
                    recent_cnt    = recent_counts.get(cid, 0)

                    # --- REACTIVAR_CLIENTE ---
                    if days_inactive >= INACTIVITY_DAYS and "REACTIVAR_CLIENTE" in tpl_by_tipo:
                        tpl   = tpl_by_tipo["REACTIVAR_CLIENTE"]
                        tasks_to_insert.append((
                            int(tpl["id"]), vid, cid, "REACTIVAR_CLIENTE",
                            f"Reactivar {name} — {days_inactive} días sin pedir",
                            int(tpl["puntos_default"]),
                            "PENDIENTE",
                            json.dumps({"dias_inactivo": days_inactive, "source": "trigger-local"}),
                            target_date, None,
                        ))

                    # --- CROSS_SELL_COMBO (solo clientes con compras recientes) ---
                    if recent_cnt > 0 and "CROSS_SELL_COMBO" in tpl_by_tipo:
                        combos = call_ml_combo(schema, cid, [], http)
                        if combos:
                            tpl = tpl_by_tipo["CROSS_SELL_COMBO"]
                            tasks_to_insert.append((
                                int(tpl["id"]), vid, cid, "CROSS_SELL_COMBO",
                                f"Combo ML para {name}: {', '.join(combos[:2])}",
                                int(tpl["puntos_default"]),
                                "PENDIENTE",
                                json.dumps({"combo_skus": combos, "source": "trigger-local"}),
                                target_date, None,
                            ))
                        else:
                            stats["ml_errors"].append(f"combo/{cid}")

                    # --- REPOSICION_HABITO (requiere ≥3 pedidos en 90 días) ---
                    if recent_cnt > 3 and "REPOSICION_HABITO" in tpl_by_tipo:
                        due_items = call_ml_replenishment(schema, cid, http)
                        if due_items:
                            tpl = tpl_by_tipo["REPOSICION_HABITO"]
                            skus = [r["product_code"] for r in due_items]
                            tasks_to_insert.append((
                                int(tpl["id"]), vid, cid, "REPOSICION_HABITO",
                                f"Reponer para {name}: {', '.join(skus[:2])}",
                                int(tpl["puntos_default"]),
                                "PENDIENTE",
                                json.dumps({"skus_vencer": skus, "source": "trigger-local"}),
                                target_date, None,
                            ))
                        else:
                            if recent_cnt > 3:
                                stats["ml_errors"].append(f"replenishment/{cid}")

        if tasks_to_insert:
            result = await conn.executemany(
                f"""
                INSERT INTO "{schema}".field_tasks
                  (template_id, vendedor_id, cliente_id, tipo, descripcion, puntos,
                   estado, criterio_json, fecha, completada_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
                ON CONFLICT (vendedor_id, cliente_id, tipo, fecha) DO NOTHING
                """,
                tasks_to_insert,
            )
            stats["inserted"] = len(tasks_to_insert)
        else:
            stats["skipped"] = 1  # Ninguna zona activa hoy

    finally:
        await conn.close()

    return stats


async def run(schema: str, dias: int) -> None:
    today  = date.today()
    dates  = [today + timedelta(days=i) for i in range(dias)]
    ml_warnings: list[str] = []

    print(f"[*] Generando tareas directamente en BD para {dias} día(s)...")

    for target in dates:
        stats = await generate_tasks_for_date(schema, target)
        print(f"  [{stats['date']}] {stats['inserted']} tareas insertadas", end="")
        if stats["skipped"]:
            print(f" (sin zona activa ese día)", end="")
        if stats["ml_errors"]:
            print(f" | ML sin datos: {len(stats['ml_errors'])} clientes", end="")
            ml_warnings.extend(stats["ml_errors"])
        print()

    print(f"\n{'='*60}")
    print("TRIGGER TAREAS FIELD — RESUMEN")
    print(f"{'='*60}")
    print(f"  Días procesados: {len(dates)}")
    if ml_warnings:
        print(f"\n  El modelo ML no devolvió sugerencias para {len(set(ml_warnings))} clientes.")
        print(f"  Esto es normal si el modelo fue entrenado hace poco o hay pocos pedidos.")
        print(f"  Las tareas REACTIVAR_CLIENTE se generaron igual.")
    print(f"{'='*60}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera tareas Suplai Field directamente en BD (sin endpoint HTTP)."
    )
    parser.add_argument("--esquema", required=True)
    parser.add_argument("--dias", type=int, default=1, help="Días a generar desde hoy (default: 1)")
    args = parser.parse_args()
    asyncio.run(run(sanitize_schema_name(args.esquema), args.dias))


if __name__ == "__main__":
    main()
