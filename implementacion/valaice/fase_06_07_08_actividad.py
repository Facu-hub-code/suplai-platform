import os
import sys
import csv
import json
import asyncio
import asyncpg
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

schema = "valaice"

async def main():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL not found.")
        sys.exit(1)
        
    os.makedirs(f"implementacion/{schema}/outputs", exist_ok=True)
    
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        products = await conn.fetch(f"SELECT product_code, nombre FROM {schema}.productos;")
        clients = await conn.fetch(f"SELECT id, phone_number, nombre FROM {schema}.clients;")
        prices_records = await conn.fetch(f"SELECT product_code, precio_unidad FROM {schema}.precios_productos WHERE lista_precios_id = 1;")
        
        prod_map = {p['product_code']: p['nombre'] for p in products}
        price_map = {pr['product_code']: float(pr['precio_unidad']) for pr in prices_records}
        prod_codes = list(prod_map.keys())
        
        print("[*] Generating historical and open orders...")
        pedidos_rows = []
        items_rows = []
        db_pedidos = []
        db_items = []
        
        order_id_counter = 1
        item_id_counter = 1
        now = datetime.now()
        random.seed(42)
        
        # Historical orders
        for c in clients:
            cid = c['id']
            num_hist = random.randint(2, 3)
            for h in range(num_hist):
                days_ago = random.randint(15, 120)
                order_date = now - timedelta(days=days_ago)
                
                chosen_skus = random.sample(prod_codes, random.randint(2, 4))
                total_monto = 0.0
                order_items_json = []
                
                for sku in chosen_skus:
                    qty = random.randint(1, 5)
                    price = price_map.get(sku, 50000.0)
                    item_total = price * qty
                    total_monto += item_total
                    p_name = prod_map[sku]
                    
                    order_items_json.append({
                        "product_code": sku,
                        "nombre": p_name,
                        "cantidad": qty,
                        "precio_unitario": price
                    })
                    
                    items_rows.append({
                        "id": item_id_counter,
                        "pedido_id": order_id_counter,
                        "client_id": str(cid),
                        "product_code": sku,
                        "nombre": p_name,
                        "cantidad_solicitada": qty,
                        "precio_unitario": price,
                        "fecha_pedido": order_date.strftime("%Y-%m-%d"),
                        "is_mock": True
                    })
                    db_items.append((
                        item_id_counter, order_id_counter, str(cid), sku, p_name,
                        qty, price, order_date.date(), True
                    ))
                    item_id_counter += 1
                    
                pedidos_rows.append({
                    "id": order_id_counter,
                    "cliente_id": cid,
                    "fecha": order_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "items": json.dumps(order_items_json, ensure_ascii=False),
                    "total": round(total_monto, 2),
                    "estado": "confirmado",
                    "origen": "whatsapp",
                    "is_mock": True
                })
                db_pedidos.append((
                    order_id_counter, cid, order_date, json.dumps(order_items_json, ensure_ascii=False),
                    round(total_monto, 2), "confirmado", "whatsapp", True
                ))
                order_id_counter += 1
                
        # Open orders
        open_clients = clients[:7]
        for c in open_clients:
            cid = c['id']
            chosen_skus = random.sample(prod_codes, 2)
            total_monto = 0.0
            order_items_json = []
            
            for sku in chosen_skus:
                qty = random.randint(1, 3)
                price = price_map.get(sku, 50000.0)
                item_total = price * qty
                total_monto += item_total
                p_name = prod_map[sku]
                
                order_items_json.append({
                    "product_code": sku,
                    "nombre": p_name,
                    "cantidad": qty,
                    "precio_unitario": price
                })
                
                items_rows.append({
                    "id": item_id_counter,
                    "pedido_id": order_id_counter,
                    "client_id": str(cid),
                    "product_code": sku,
                    "nombre": p_name,
                    "cantidad_solicitada": qty,
                    "precio_unitario": price,
                    "fecha_pedido": now.strftime("%Y-%m-%d"),
                    "is_mock": True
                })
                db_items.append((
                    item_id_counter, order_id_counter, str(cid), sku, p_name,
                    qty, price, now.date(), True
                ))
                item_id_counter += 1
                
            pedidos_rows.append({
                "id": order_id_counter,
                "cliente_id": cid,
                "fecha": now.strftime("%Y-%m-%d %H:%M:%S"),
                "items": json.dumps(order_items_json, ensure_ascii=False),
                "total": round(total_monto, 2),
                "estado": "abierto",
                "origen": "whatsapp",
                "is_mock": True
            })
            db_pedidos.append((
                order_id_counter, cid, now, json.dumps(order_items_json, ensure_ascii=False),
                round(total_monto, 2), "abierto", "whatsapp", True
            ))
            order_id_counter += 1

        with open(f"implementacion/{schema}/outputs/phase-06-pedidos.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(pedidos_rows[0].keys()))
            writer.writeheader()
            writer.writerows(pedidos_rows)
            
        with open(f"implementacion/{schema}/outputs/phase-06-items-pedido.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(items_rows[0].keys()))
            writer.writeheader()
            writer.writerows(items_rows)

        await conn.execute(f"DELETE FROM {schema}.items_pedido;")
        await conn.execute(f"DELETE FROM {schema}.pedidos;")
        
        for p in db_pedidos:
            await conn.execute(f"""
                INSERT INTO {schema}.pedidos (id, cliente_id, fecha, items, total, estado, origen, is_mock, updated_at)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, now());
            """, p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
            
        for it in db_items:
            await conn.execute(f"""
                INSERT INTO {schema}.items_pedido (id, pedido_id, client_id, product_code, nombre, cantidad_solicitada, precio_unitario, fecha_pedido, is_mock, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now(), now());
            """, it[0], it[1], it[2], it[3], it[4], it[5], it[6], it[7], it[8])

        print(f"✅ Inserted {len(pedidos_rows)} orders and {len(items_rows)} order items.")

        # 2. GENERATE CONVERSATIONS (Fase 7)
        print("[*] Generating WhatsApp chat conversations...")
        chats_rows = []
        chat_id_counter = 1
        
        for c in clients[:15]:
            phone = c['phone_number']
            cname = c['nombre']
            
            messages = [
                {"type": "human", "content": f"Hola! Quisiera consultar precios y stock de medialunas con manteca y criollos de hojaldre para {cname}."},
                {"type": "ai", "content": f"¡Hola! Bienvenido a Valaice Ultracongelados. Para {cname} tenemos el bulto de Medialuna con Manteca x168un a $74.650 final IVA incluido y el Criollo de Hojaldre x11kg a $55.100 final. ¿Cuántos bultos te preparo?"},
                {"type": "human", "content": "Excelente, armame un pedido por 2 bultos de medialunas y 1 de criollos."},
                {"type": "ai", "content": "¡Perfecto! Registré tu pedido por 2 bultos de Medialuna con Manteca ($149.300) y 1 bulto de Criollo de Hojaldre ($55.100). Total final con IVA incluido: $204.400. Tu pedido está en estado abierto para entrega programada."}
            ]
            
            for msg in messages:
                chats_rows.append({
                    "id": chat_id_counter,
                    "session_id": phone,
                    "message": json.dumps(msg, ensure_ascii=False),
                    "is_mock": True
                })
                chat_id_counter += 1
                
        with open(f"implementacion/{schema}/outputs/phase-07-conversaciones-resumen.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(chats_rows[0].keys()))
            writer.writeheader()
            writer.writerows(chats_rows)
            
        await conn.execute(f"DELETE FROM {schema}.n8n_chat_histories;")
        for ch in chats_rows:
            await conn.execute(f"""
                INSERT INTO {schema}.n8n_chat_histories (id, session_id, message, is_mock, created_at)
                VALUES ($1, $2, $3::jsonb, $4, now());
            """, ch['id'], ch['session_id'], ch['message'], ch['is_mock'])
            
        print(f"✅ Inserted {len(chats_rows)} chat history messages.")

        # 3. GENERATE INSIGHTS / SMART ALERTS (Fase 8)
        print("[*] Generating smart alert tickets...")
        tickets_rows = []
        
        descriptions = [
            "Cliente solicitó recomendación de horneado para croissants congelados.",
            "Alerta de calidad: Medialunas llegaron con leve pérdida de frío en furgón.",
            "Consulta comercial: Cliente solicitó bonificación por volumen en Pan Mignon.",
            "Alerta de logística: Retraso de 30 min en reparto zona Alta Gracia Norte.",
            "Consulta administrativa: Cliente solicita factura A electrónica con IVA desglosado.",
            "Alerta de rotación: Bar de la Plaza no realiza pedido de criollos hace 25 días.",
            "Oportunidad de prospección: Nuevo comercio gastronómico interesado en catálogo precocido.",
            "Alerta de reposición inteligente: Panadería El Sol agotará stock de baguettes el viernes.",
            "Reclamo menor: Embalaje de chipá roto durante descarga.",
            "Consulta técnica: Tiempo exacto de fermentación previa a horneado de facturas.",
            "Solicitud de visita comercial: Vendedor Carlos Gómez agendó muestra gratis.",
            "Alerta de pago: Transferencia bancaria registrada pendiente de confirmación.",
            "Alerta de reposición: Sugerencia automática de combo Medialuna + Factura Mixta.",
            "Consulta de horario: Confirmación de entrega antes de las 8:00 AM para cafeterías.",
            "Alerta de satisfacción: Cliente felicitó por calidad constante de la masa hojaldrada.",
            "Alerta de stock: Alta demanda de Pan Trebolín crudo en zona Sur."
        ]
        
        for idx, desc in enumerate(descriptions, start=1):
            client = clients[idx - 1]
            cid = str(client['id'])
            status = "ABIERTO" if idx <= 10 else "CERRADO"
            closed_at = None if status == "ABIERTO" else now
            
            tickets_rows.append({
                "id": idx,
                "client_id": cid,
                "description": desc,
                "status": status,
                "closed_at": closed_at.strftime("%Y-%m-%d %H:%M:%S") if closed_at else None,
                "is_mock": True
            })
            
        with open(f"implementacion/{schema}/outputs/phase-08-notificaciones.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(tickets_rows[0].keys()))
            writer.writeheader()
            writer.writerows(tickets_rows)
            
        await conn.execute(f"DELETE FROM {schema}.ia_tickets;")
        for t in tickets_rows:
            c_at = datetime.strptime(t['closed_at'], "%Y-%m-%d %H:%M:%S") if t['closed_at'] else None
            await conn.execute(f"""
                INSERT INTO {schema}.ia_tickets (id, client_id, description, status, closed_at, is_mock, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, now());
            """, t['id'], t['client_id'], t['description'], t['status'], c_at, t['is_mock'])
            
        print(f"✅ Inserted {len(tickets_rows)} smart alert tickets into {schema}.ia_tickets.")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
