"""
Higiene del tenant demo (SPEC-035, follow-up videollamadas).

Borra productos fuera de catálogo, clientes fuera del pool de 70 con pin,
vendedores inactivos 1/2/3. Backfill de totales, seed de pedidos recientes,
tickets de reclamo, system-prompt v2.

No toca mapa (polígonos / pines / HQ) ni el texto de conversaciones.

    python scripts/demo-videollamadas/higiene_tenant_demo.py --esquema demo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA_ALLOWED = "demo"
TENANT_ID = "8f8fcf47-c191-4cc7-a7d2-5703d474bb8a"
DROP_SELLER_IDS = (1, 2, 3)
ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV = Path("/Users/facundolorenzo/Documents/SuplaiSales/source/backend-supabase/.env")
PROMPT_MD = ROOT / "implementacion" / "demo" / "outputs" / "phase-01-3-system-prompt-v2.md"
SHIFT_SQL = Path(__file__).with_name("shift_fechas.sql")

RECLAMOS = [
    {
        "client_id": "36814",
        "description": (
            "[RECLAMO_CALIDAD] Pedido llegó con olor feo. "
            "El cliente (Almacén La Familia, Palermo) reportó que una caja de golosinas "
            "llegó con olor rancio / a humedad. El agente no puede resolver calidad ni "
            "cambiar mercadería por este chat: ticket abierto para depósito / vendedora Lucía."
        ),
        "hours_ago": 18,
    },
    {
        "client_id": "9",
        "description": (
            "[RECLAMO_ROTURA] Cajas aplastadas en el reparto. "
            "Punto Norte (Belgrano) recibió displays de chocolate con packaging roto. "
            "Fuera de expertise del agente: derivar a logística / Martín Álvarez."
        ),
        "hours_ago": 30,
    },
    {
        "client_id": "36827",
        "description": (
            "[RECLAMO_FACTURA] Falta la factura del último pedido. "
            "El cliente pide el comprobante fiscal por WhatsApp. El agente no emite ni "
            "reenvía facturas: ticket para administración."
        ),
        "hours_ago": 42,
    },
    {
        "client_id": "36803",
        "description": (
            "[RECLAMO_LOGISTICA] Demora de más de 5 días en el reparto. "
            "Almacén El Rincón (Belgrano) pregunta dónde está el camión. El agente no "
            "tiene tracking de flete: ticket para depósito / planificación de ruta."
        ),
        "hours_ago": 8,
    },
]


def _load_env() -> None:
    load_dotenv(ROOT / ".env", override=False)
    if BACKEND_ENV.exists():
        load_dotenv(BACKEND_ENV, override=False)


def _db_url() -> str:
    raw = os.getenv("SUPABASE_DB_URL") or os.getenv("SUPABASE_DB_URL_POOLER") or ""
    if not raw:
        raise SystemExit("[FAIL] SUPABASE_DB_URL no configurada")
    return raw.replace(":5432/", ":6543/")


async def _keep_client_ids(conn: asyncpg.Connection) -> list[int]:
    rows = await conn.fetch("SELECT DISTINCT client_id AS id FROM demo.client_locations ORDER BY 1")
    ids = [int(r["id"]) for r in rows]
    if len(ids) != 70:
        raise SystemExit(f"[FAIL] Se esperaban 70 clientes con pin, hay {len(ids)}")
    return ids


async def delete_extra_clients(conn: asyncpg.Connection, keep_ids: list[int]) -> int:
    drop = await conn.fetch(
        "SELECT id FROM demo.clients WHERE id <> ALL($1::int[])",
        keep_ids,
    )
    drop_ids = [int(r["id"]) for r in drop]
    if not drop_ids:
        print("[OK] Clientes extra: 0")
        return 0

    drop_txt = [str(i) for i in drop_ids]
    task_ids = await conn.fetch(
        """
        SELECT id FROM demo.field_tasks
        WHERE cliente_id = ANY($1::int[])
           OR pdv_id IN (SELECT pdv_id FROM demo.clients WHERE id = ANY($1::int[]) AND pdv_id IS NOT NULL)
        """,
        drop_ids,
    )
    tids = [int(r["id"]) for r in task_ids]
    if tids:
        await conn.execute("DELETE FROM demo.field_task_events WHERE task_id = ANY($1::bigint[])", tids)
        await conn.execute("DELETE FROM demo.field_point_ledger WHERE task_id = ANY($1::bigint[])", tids)
        await conn.execute("DELETE FROM demo.field_tasks WHERE id = ANY($1::bigint[])", tids)

    pedido_ids = await conn.fetch(
        "SELECT id FROM demo.pedidos WHERE cliente_id = ANY($1::int[])",
        drop_ids,
    )
    pids = [int(r["id"]) for r in pedido_ids]
    if pids:
        await conn.execute(
            "UPDATE demo.field_tasks SET pedido_id = NULL WHERE pedido_id = ANY($1::int[])",
            pids,
        )
        await conn.execute("DELETE FROM demo.items_pedido WHERE pedido_id = ANY($1::int[])", pids)
        await conn.execute("DELETE FROM demo.pedidos WHERE id = ANY($1::int[])", pids)

    await conn.execute("DELETE FROM demo.ia_tickets WHERE client_id = ANY($1::text[])", drop_txt)
    await conn.execute("DELETE FROM demo.clientes_etiquetas WHERE client_id = ANY($1::int[])", drop_ids)
    await conn.execute("DELETE FROM demo.client_product_memory WHERE client_id = ANY($1::int[])", drop_ids)
    await conn.execute("DELETE FROM demo.vendedores_clientes WHERE cliente_id = ANY($1::int[])", drop_ids)

    await conn.execute(
        "UPDATE demo.clients SET pdv_id = NULL, updated_at = now() WHERE id = ANY($1::int[])",
        drop_ids,
    )
    del_clients = await conn.execute(
        "DELETE FROM demo.clients WHERE id = ANY($1::int[])", drop_ids
    )
    leftover = await conn.fetchval(
        "SELECT COUNT(*) FROM demo.clients WHERE id = ANY($1::int[])", drop_ids
    )
    if leftover:
        raise SystemExit(f"[FAIL] No se pudieron borrar {leftover} clientes ({del_clients})")

    orphan_pdv = await conn.execute(
        """
        DELETE FROM demo.puntos_venta pv
        WHERE NOT EXISTS (SELECT 1 FROM demo.clients c WHERE c.pdv_id = pv.id)
          AND NOT EXISTS (SELECT 1 FROM demo.field_tasks t WHERE t.pdv_id = pv.id)
        """
    )
    print(f"[OK] Clientes borrados: {len(drop_ids)} ({drop_ids}); PDV huérfanos: {orphan_pdv}")
    return len(drop_ids)


async def delete_offcatalog_products(conn: asyncpg.Connection) -> int:
    n_off = await conn.fetchval(
        "SELECT COUNT(*) FROM demo.productos WHERE COALESCE(en_catalogo, false) = false"
    )
    keep_items_off = await conn.fetchval(
        """
        SELECT COUNT(DISTINCT ip.product_code)
        FROM demo.items_pedido ip
        JOIN demo.pedidos p ON p.id = ip.pedido_id
        JOIN demo.client_locations cl ON cl.client_id = p.cliente_id
        JOIN demo.productos pr ON pr.product_code = ip.product_code
        WHERE COALESCE(pr.en_catalogo, false) = false
          AND p.deleted_at IS NULL
        """
    )
    print(
        f"[*] Productos fuera de catálogo: {n_off}. "
        f"SKUs históricos en pedidos de los 70: {keep_items_off} "
        "(se conservan las líneas; se borra el maestro)."
    )
    if not n_off:
        return 0

    await conn.execute(
        """
        DELETE FROM demo.product_tags
        WHERE product_code IN (SELECT product_code FROM demo.productos WHERE COALESCE(en_catalogo, false) = false)
        """
    )
    await conn.execute(
        """
        DELETE FROM demo.precios_productos
        WHERE product_code IN (SELECT product_code FROM demo.productos WHERE COALESCE(en_catalogo, false) = false)
        """
    )
    await conn.execute(
        """
        DELETE FROM demo.productos_aliases
        WHERE product_code IN (SELECT product_code FROM demo.productos WHERE COALESCE(en_catalogo, false) = false)
        """
    )
    await conn.execute(
        """
        DELETE FROM demo.promocion_grupo_productos
        WHERE product_code IN (SELECT product_code FROM demo.productos WHERE COALESCE(en_catalogo, false) = false)
        """
    )
    await conn.execute(
        """
        DELETE FROM demo.client_product_memory
        WHERE product_code IN (SELECT product_code FROM demo.productos WHERE COALESCE(en_catalogo, false) = false)
        """
    )
    await conn.execute(
        """
        DELETE FROM demo.documents
        WHERE metadata->>'product_code' IN (
          SELECT product_code FROM demo.productos WHERE COALESCE(en_catalogo, false) = false
        )
        """
    )
    # product_categories CASCADE, but be explicit
    await conn.execute(
        """
        DELETE FROM demo.product_categories
        WHERE product_code IN (SELECT product_code FROM demo.productos WHERE COALESCE(en_catalogo, false) = false)
        """
    )
    result = await conn.execute(
        "DELETE FROM demo.productos WHERE COALESCE(en_catalogo, false) = false"
    )
    deleted = int(result.split()[-1])
    print(f"[OK] Productos borrados: {deleted}")
    return deleted


async def delete_inactive_sellers(conn: asyncpg.Connection) -> int:
    existing = await conn.fetch(
        "SELECT id, nombre, activo FROM demo.vendedores WHERE id = ANY($1::int[])",
        list(DROP_SELLER_IDS),
    )
    if not existing:
        print("[OK] Vendedores inactivos: ya no están")
        return 0

    await conn.execute(
        """
        UPDATE demo.conversations
        SET vendedor_id = 10
        WHERE vendedor_id = ANY($1::int[])
        """,
        list(DROP_SELLER_IDS),
    )
    await conn.execute(
        """
        UPDATE demo.grupos
        SET vendedor_id = 11
        WHERE vendedor_id = ANY($1::int[])
        """,
        list(DROP_SELLER_IDS),
    )
    await conn.execute(
        """
        UPDATE demo.field_tournaments
        SET ganador_vendedor_id = NULL
        WHERE ganador_vendedor_id = ANY($1::int[])
        """,
        list(DROP_SELLER_IDS),
    )
    await conn.execute(
        """
        UPDATE demo.geo_zones
        SET vendedor_principal_id = NULL, updated_at = now()
        WHERE vendedor_principal_id = ANY($1::int[])
        """,
        list(DROP_SELLER_IDS),
    )
    await conn.execute(
        """
        UPDATE demo.puntos_venta
        SET vendedor_id = NULL, updated_at = now()
        WHERE vendedor_id = ANY($1::int[])
        """,
        list(DROP_SELLER_IDS),
    )

    task_ids = await conn.fetch(
        "SELECT id FROM demo.field_tasks WHERE vendedor_id = ANY($1::int[])",
        list(DROP_SELLER_IDS),
    )
    tids = [int(r["id"]) for r in task_ids]
    if tids:
        await conn.execute("DELETE FROM demo.field_task_events WHERE task_id = ANY($1::bigint[])", tids)
        await conn.execute("DELETE FROM demo.field_point_ledger WHERE task_id = ANY($1::bigint[])", tids)
        await conn.execute("DELETE FROM demo.field_tasks WHERE id = ANY($1::bigint[])", tids)

    await conn.execute(
        "DELETE FROM demo.field_point_ledger WHERE vendedor_id = ANY($1::int[])",
        list(DROP_SELLER_IDS),
    )
    await conn.execute(
        "DELETE FROM demo.vendedores_clientes WHERE vendedor_id = ANY($1::int[])",
        list(DROP_SELLER_IDS),
    )
    # podcast jobs CASCADE on vendedor delete
    result = await conn.execute(
        "DELETE FROM demo.vendedores WHERE id = ANY($1::int[])",
        list(DROP_SELLER_IDS),
    )
    deleted = int(result.split()[-1])
    left = await conn.fetch("SELECT id, nombre, activo FROM demo.vendedores ORDER BY id")
    print(f"[OK] Vendedores borrados: {deleted}; quedan {[dict(r) for r in left]}")
    return deleted


async def patch_notification_subscribers(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        UPDATE public.distribuidoras
        SET reglas_negocio = jsonb_set(
              jsonb_set(
                COALESCE(reglas_negocio::jsonb, '{}'::jsonb),
                '{system_errors_notification,subscribers}',
                '[{"weight":1,"vendedor_id":10},{"weight":1,"vendedor_id":11}]'::jsonb
              ),
              '{custom_ia_tickets_notification,subscribers}',
              '[{"weight":1,"vendedor_id":10},{"weight":1,"vendedor_id":12}]'::jsonb
            ),
            updated_at = now()
        WHERE schema_name = 'demo'
        """
    )
    print("[OK] Subscribers de notificaciones → vendedores 10/11/12")


async def backfill_totals(conn: asyncpg.Connection, keep_ids: list[int]) -> int:
    result = await conn.execute(
        """
        UPDATE demo.pedidos p
        SET total = sub.s, updated_at = now()
        FROM (
          SELECT pedido_id,
                 ROUND(SUM(COALESCE(precio_unitario, 0) * COALESCE(cantidad_solicitada, 0))::numeric, 2) AS s
          FROM demo.items_pedido
          WHERE pedido_id IS NOT NULL
          GROUP BY pedido_id
        ) sub
        WHERE p.id = sub.pedido_id
          AND p.cliente_id = ANY($1::int[])
          AND p.deleted_at IS NULL
          AND (p.total IS NULL OR p.total = 0)
          AND sub.s > 0
        """,
        keep_ids,
    )
    n = int(result.split()[-1])
    print(f"[OK] Totales backfill: {n} pedidos")
    return n


async def seed_recent_orders(conn: asyncpg.Connection, keep_ids: list[int]) -> int:
    today = date.today()
    cursor = date(today.year, today.month, 1)
    created = 0
    for i in range(3):
        start = date(cursor.year, cursor.month, 1)
        if i == 0:
            end = today
            target = 90
        else:
            nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            end = nxt - timedelta(days=1)
            target = 90
        n_exist = await conn.fetchval(
            """
            SELECT COUNT(*) FROM demo.pedidos
            WHERE deleted_at IS NULL
              AND cliente_id = ANY($1::int[])
              AND lower(trim(estado::text)) IN ('confirmado','descargado')
              AND fecha::date >= $2 AND fecha::date <= $3
            """,
            keep_ids, start, end,
        )
        need = max(0, target - int(n_exist))
        print(f"[*] {start:%Y-%m}: hay {n_exist}, falta sembrar {need}", flush=True)
        if need == 0:
            cursor = (start - timedelta(days=1)).replace(day=1)
            continue
        span = max(1, (end - start).days)
        n_ins = await conn.fetchval(
            """
            WITH clients AS (
              SELECT id, COALESCE(lista_precios_id, 1) AS lista_precios_id,
                     row_number() OVER (ORDER BY id) - 1 AS rn
              FROM demo.clients WHERE id = ANY($1::int[])
            ),
            ncli AS (SELECT COUNT(*)::int AS n FROM clients),
            gen AS (
              SELECT gs AS n,
                     ($2::date + ((gs - 1) % $4)::int) AS d
              FROM generate_series(1, $5) gs
            ),
            ins AS (
              INSERT INTO demo.pedidos
                (cliente_id, fecha, items, total, estado, notas, is_mock, origen)
              SELECT c.id,
                     (g.d::timestamp + make_interval(hours => 10 + (g.n % 8))),
                     '[]'::jsonb,
                     0,
                     'confirmado',
                     'seed_demo_videollamadas_metricas',
                     true,
                     'suplai'
              FROM gen g
              CROSS JOIN ncli
              JOIN clients c ON c.rn = (g.n - 1) % ncli.n
              RETURNING id, cliente_id, fecha
            ),
            lines AS (
              INSERT INTO demo.items_pedido
                (client_id, product_code, precio_unitario, fecha_pedido, nombre,
                 cantidad_solicitada, pedido_id, is_mock)
              SELECT i.cliente_id::text, s.product_code, s.precio_unidad, i.fecha::date,
                     s.nombre, 2 + (s.ord % 5), i.id, true
              FROM ins i
              JOIN clients c ON c.id = i.cliente_id
              JOIN LATERAL (
                SELECT pp.product_code, pr.nombre, pp.precio_unidad,
                       row_number() OVER (ORDER BY md5(i.id::text || pp.product_code)) AS ord
                FROM demo.precios_productos pp
                JOIN demo.productos pr ON pr.product_code = pp.product_code
                WHERE pr.en_catalogo = true
                  AND pp.lista_precios_id = c.lista_precios_id
                  AND pp.precio_unidad > 0
                LIMIT 4
              ) s ON true
              RETURNING pedido_id
            )
            SELECT COUNT(DISTINCT pedido_id) FROM lines
            """,
            keep_ids, start, end, span, need,
        )
        await conn.execute(
            """
            UPDATE demo.pedidos p
            SET total = sub.s,
                items = sub.items,
                updated_at = now()
            FROM (
              SELECT ip.pedido_id,
                     ROUND(SUM(ip.precio_unitario * ip.cantidad_solicitada)::numeric, 2) AS s,
                     jsonb_agg(jsonb_build_object(
                       'product_code', ip.product_code,
                       'nombre', ip.nombre,
                       'cantidad_solicitada', ip.cantidad_solicitada,
                       'precio_unitario', ip.precio_unitario
                     )) AS items
              FROM demo.items_pedido ip
              JOIN demo.pedidos p2 ON p2.id = ip.pedido_id
              WHERE p2.notas = 'seed_demo_videollamadas_metricas' AND p2.total = 0
              GROUP BY ip.pedido_id
            ) sub
            WHERE p.id = sub.pedido_id
            """
        )
        created += int(n_ins or 0)
        print(f"[OK] {start:%Y-%m}: semilla {n_ins} pedidos", flush=True)
        cursor = (start - timedelta(days=1)).replace(day=1)
    return created


async def insert_reclamos(conn: asyncpg.Connection, keep_ids: list[int]) -> list[dict]:
    created = []
    keep_txt = {str(i) for i in keep_ids}
    for rec in RECLAMOS:
        if rec["client_id"] not in keep_txt:
            raise SystemExit(f"[FAIL] reclamo client_id {rec['client_id']} no está en el pool 70")
        exists = await conn.fetchval(
            "SELECT id FROM demo.ia_tickets WHERE description LIKE $1 LIMIT 1",
            rec["description"][:40] + "%",
        )
        if exists:
            created.append({"id": int(exists), "status": "exists", "title": rec["description"][:80]})
            continue
        ts = datetime.now(timezone.utc) - timedelta(hours=rec["hours_ago"])
        tid = await conn.fetchval(
            """
            INSERT INTO demo.ia_tickets (description, client_id, status, created_at, is_mock)
            VALUES ($1, $2, 'open', $3, true)
            RETURNING id
            """,
            rec["description"], rec["client_id"], ts,
        )
        created.append({"id": int(tid), "status": "open", "title": rec["description"].split(".")[0]})
    print(f"[OK] Tickets reclamo: {created}")
    return created


async def apply_prompt_v2(conn: asyncpg.Connection) -> None:
    if not PROMPT_MD.exists():
        raise SystemExit(f"[FAIL] Falta {PROMPT_MD}")
    prompt = PROMPT_MD.read_text(encoding="utf-8").strip()
    if "Arcor" in prompt:
        raise SystemExit("[FAIL] El prompt v2 todavía menciona Arcor")
    await conn.execute(
        """
        UPDATE public.distribuidoras
        SET system_prompt = $1,
            identidad = $2,
            contexto = $3,
            metadata = COALESCE(metadata, '{}'::jsonb) || '{"use_new_system_prompt": true}'::jsonb,
            updated_at = now()
        WHERE schema_name = 'demo' AND id = $4::uuid
        """,
        prompt,
        "Ver system_prompt v2 (Tato, Demo golosinas CABA, marca líder COFLER).",
        "Legacy desactivado. metadata.use_new_system_prompt=true.",
        TENANT_ID,
    )
    print("[OK] system_prompt v2 + flag use_new_system_prompt")


async def apply_shift_fn(conn: asyncpg.Connection) -> None:
    await conn.execute(SHIFT_SQL.read_text(encoding="utf-8"))
    print("[OK] Recreada demo.shift_sales_demo_dates() (tickets estáticos)")


async def verify(conn: asyncpg.Connection) -> dict:
    row = await conn.fetchrow(
        """
        SELECT
          (SELECT COUNT(*) FROM demo.productos) AS productos_total,
          (SELECT COUNT(*) FROM demo.productos WHERE en_catalogo) AS productos_en_catalogo,
          (SELECT COUNT(*) FROM demo.clients) AS clients_total,
          (SELECT COUNT(DISTINCT client_id) FROM demo.client_locations) AS clients_con_pin,
          (SELECT jsonb_agg(jsonb_build_object('id',id,'nombre',nombre,'activo',activo) ORDER BY id)
             FROM demo.vendedores) AS vendedores,
          (SELECT COUNT(*) FROM demo.ia_tickets WHERE description LIKE '[RECLAMO_%') AS tickets_reclamo,
          (SELECT system_prompt) AS system_prompt,
          (SELECT metadata->>'use_new_system_prompt' FROM public.distribuidoras WHERE schema_name='demo') AS prompt_v2
        FROM public.distribuidoras WHERE schema_name='demo'
        """
    )
    months = await conn.fetch(
        """
        SELECT to_char(date_trunc('month', fecha), 'YYYY-MM') AS mes,
               COUNT(*) AS n,
               ROUND(COALESCE(SUM(total),0)::numeric, 0) AS monto
        FROM demo.pedidos p
        JOIN demo.client_locations cl ON cl.client_id = p.cliente_id
        WHERE p.deleted_at IS NULL
          AND lower(trim(p.estado::text)) IN ('confirmado','descargado')
          AND fecha >= date_trunc('month', CURRENT_DATE) - interval '2 months'
        GROUP BY 1
        ORDER BY 1
        """
    )
    reclamos = await conn.fetch(
        """
        SELECT id, left(description, 80) AS titulo, client_id, status
        FROM demo.ia_tickets
        WHERE description LIKE '[RECLAMO_%'
        ORDER BY id
        """
    )
    prompt = row["system_prompt"] or ""
    report = {
        "productos_total": int(row["productos_total"]),
        "productos_en_catalogo": int(row["productos_en_catalogo"]),
        "clients_total": int(row["clients_total"]),
        "clients_con_pin": int(row["clients_con_pin"]),
        "vendedores": row["vendedores"],
        "tickets_reclamo": int(row["tickets_reclamo"]),
        "prompt_v2": row["prompt_v2"],
        "prompt_tiene_arcor": "Arcor" in prompt or "arcor" in prompt.lower(),
        "pedidos_mes": [dict(m) for m in months],
        "reclamos": [dict(r) for r in reclamos],
    }
    print("[VERIFY]", json.dumps(report, default=str, ensure_ascii=False, indent=2))
    return report


async def run(schema: str) -> dict:
    if schema != SCHEMA_ALLOWED:
        raise SystemExit(f"[FAIL] Solo schema '{SCHEMA_ALLOWED}', recibido '{schema}'")
    print(f"[*] schema_name confirmado: {schema} (tenant_id={TENANT_ID})", flush=True)
    conn = await asyncpg.connect(_db_url(), statement_cache_size=0, timeout=30)
    try:
        await conn.execute("SET search_path TO demo, core, public, extensions")
        tid = await conn.fetchval(
            "SELECT id::text FROM public.distribuidoras WHERE schema_name='demo'"
        )
        if tid != TENANT_ID:
            raise SystemExit(f"[FAIL] tenant id inesperado: {tid}")

        keep_ids = await _keep_client_ids(conn)
        print("[*] Borrando clientes fuera del pool 70...", flush=True)
        n_cli = await delete_extra_clients(conn, keep_ids)
        print("[*] Borrando productos fuera de catálogo...", flush=True)
        n_prod = await delete_offcatalog_products(conn)
        print("[*] Borrando vendedores inactivos 1/2/3...", flush=True)
        n_vend = await delete_inactive_sellers(conn)
        await patch_notification_subscribers(conn)
        print("[*] Backfill totales...", flush=True)
        n_bf = await backfill_totals(conn, keep_ids)
        print("[*] Sembrando pedidos recientes...", flush=True)
        n_seed = await seed_recent_orders(conn, keep_ids)
        reclamos = await insert_reclamos(conn, keep_ids)
        await apply_prompt_v2(conn)
        await apply_shift_fn(conn)

        report = await verify(conn)
        report["deleted"] = {"clientes": n_cli, "productos": n_prod, "vendedores": n_vend}
        report["backfill_totales"] = n_bf
        report["seed_pedidos"] = n_seed
        report["reclamos_insert"] = reclamos
        return report
    finally:
        await conn.close()


def main() -> None:
    _load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--esquema", default="demo")
    args = parser.parse_args()
    asyncio.run(run(args.esquema))


if __name__ == "__main__":
    main()
