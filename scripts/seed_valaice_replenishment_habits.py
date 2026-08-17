"""
Seed habit orders for valaice and trigger sales-engine retrain so replenishment alarms are active.
"""

import asyncio
import json
import os
import sys
import asyncpg
import urllib.request
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

schema = "valaice"

# Top SKUs en valaice: 421 (Medialuna), 422 (Factura Mixta), 425 (Croissant), 440 (Pan Baguette)
core_skus = ["421", "422", "425", "440"]

async def main():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL not found.")
        sys.exit(1)

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        print(f"[*] Obteniendo clientes y productos en '{schema}'...")
        clients = await conn.fetch(f"SELECT id, phone_number, nombre FROM {schema}.clients ORDER BY id;")
        products = await conn.fetch(f"SELECT product_code, nombre FROM {schema}.productos;")
        prices_records = await conn.fetch(f"SELECT product_code, precio_unidad FROM {schema}.precios_productos WHERE lista_precios_id = 1;")
        
        prod_map = {p['product_code']: p['nombre'] for p in products}
        price_map = {pr['product_code']: float(pr['precio_unidad']) for pr in prices_records}

        max_order_id = await conn.fetchval(f"SELECT COALESCE(MAX(id), 0) FROM {schema}.pedidos;")
        max_item_id = await conn.fetchval(f"SELECT COALESCE(MAX(id), 0) FROM {schema}.items_pedido;")

        order_counter = max_order_id + 1
        item_counter = max_item_id + 1
        now = datetime.now()

        # Sembrar 3-4 compras periódicas para 25 clientes clave en los últimos 30 días
        print(f"[*] Generando hábitos de recompras en 25 clientes para generar alarmas de reposición...")
        target_clients = clients[:25]

        for c in target_clients:
            cid = c['id']
            # Seleccionar 1 o 2 SKUs del core para este cliente
            sku1 = core_skus[cid % len(core_skus)]
            sku2 = core_skus[(cid + 1) % len(core_skus)]
            skus = [sku1, sku2]

            # 4 compras espaciadas cada 7 días (hace 24d, 17d, 10d, y 3d)
            intervals = [24, 17, 10, 3]

            for days_ago in intervals:
                order_date = now - timedelta(days=days_ago)
                total_monto = 0.0
                order_items_json = []

                db_items_to_insert = []
                for sku in skus:
                    qty = 2 + (cid % 3)
                    price = price_map.get(sku, 50000.0)
                    item_total = price * qty
                    total_monto += item_total
                    p_name = prod_map.get(sku, "Producto Valaice")

                    order_items_json.append({
                        "product_code": sku,
                        "nombre": p_name,
                        "cantidad": qty,
                        "precio_unitario": price
                    })

                    db_items_to_insert.append((
                        item_counter, order_counter, str(cid), sku, p_name,
                        qty, price, order_date.date(), True
                    ))
                    item_counter += 1

                await conn.execute(f"""
                    INSERT INTO {schema}.pedidos (id, cliente_id, fecha, items, total, estado, origen, is_mock, updated_at)
                    VALUES ($1, $2, $3, $4::jsonb, $5, 'confirmado', 'whatsapp', true, now());
                """, order_counter, cid, order_date, json.dumps(order_items_json, ensure_ascii=False), round(total_monto, 2))

                for db_it in db_items_to_insert:
                    await conn.execute(f"""
                        INSERT INTO {schema}.items_pedido (id, pedido_id, client_id, product_code, nombre, cantidad_solicitada, precio_unitario, fecha_pedido, is_mock, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now(), now());
                    """, db_it[0], db_it[1], db_it[2], db_it[3], db_it[4], db_it[5], db_it[6], db_it[7], db_it[8])

                order_counter += 1

        print(f"  [+] Hábitos sembrados exitosamente.")

        # Trigger sales-engine retrain
        print(f"[*] Solicitando reentrenamiento de sales-engine en producción para '{schema}'...")
        api_key = os.getenv("SALES_ENGINE_API_KEY", "a20f45cf132fb6f3f39519a43c3597bab44eb1212233b4bf")
        req = urllib.request.Request(
            "https://sales-engine-production-f6bd.up.railway.app/v1/tenants/valaice/models/retrain",
            method="POST",
            headers={"X-API-Key": api_key}
        )
        res_data = urllib.request.urlopen(req).read().decode('utf-8')
        print(f"  [+] Respuesta sales-engine: {res_data}")

        # Repopular client_product_memory
        await conn.execute(
            f"""
            INSERT INTO {schema}.client_product_memory (
                client_id,
                product_code,
                order_count,
                total_qty_umv,
                last_qty_umv,
                typical_qty_umv,
                last_order_at,
                updated_at
            )
            SELECT
                p.cliente_id AS client_id,
                ip.product_code,
                COUNT(DISTINCT p.id) AS order_count,
                SUM(COALESCE(ip.cantidad_solicitada, 0)) AS total_qty_umv,
                (ARRAY_AGG(COALESCE(ip.cantidad_solicitada, 0) ORDER BY p.fecha DESC))[1] AS last_qty_umv,
                ROUND(SUM(COALESCE(ip.cantidad_solicitada, 0)) / COUNT(DISTINCT p.id), 2) AS typical_qty_umv,
                MAX(COALESCE(p.fecha::timestamptz, now())) AS last_order_at,
                now() AS updated_at
            FROM {schema}.pedidos p
            JOIN {schema}.items_pedido ip ON ip.pedido_id = p.id
            WHERE p.estado IN ('confirmado', 'descargado')
              AND p.cliente_id IS NOT NULL
              AND ip.product_code IS NOT NULL
            GROUP BY p.cliente_id, ip.product_code
            ON CONFLICT (client_id, product_code)
            DO UPDATE SET
                order_count = EXCLUDED.order_count,
                total_qty_umv = EXCLUDED.total_qty_umv,
                last_qty_umv = EXCLUDED.last_qty_umv,
                typical_qty_umv = EXCLUDED.typical_qty_umv,
                last_order_at = EXCLUDED.last_order_at,
                updated_at = now();
            """
        )
        print(f"  [+] client_product_memory actualizado.")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
