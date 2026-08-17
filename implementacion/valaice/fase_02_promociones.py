import os
import sys
import csv
import json
import asyncio
import asyncpg
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

OUTPUT_CSV = "implementacion/valaice/outputs/phase-02-promociones.csv"

async def create_promos():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL not found.")
        sys.exit(1)
        
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    
    schema = "valaice"
    now = datetime.now()
    inicio = now - timedelta(days=7)
    fin = now + timedelta(days=30)
    
    promos = [
        {
            "id": 1,
            "product_code": "421",
            "product_name": "MEDIALUNA CON MANTECA",
            "descripcion": "15% OFF en bulto de Medialunas con Manteca",
            "discount_kind": "percent",
            "descuento_percent": 15.0,
            "descuento_nominal": None,
            "precio_promocional": None,
            "lista_precios_id": 1,
            "min_qty_umv": 1,
            "is_mock": True
        },
        {
            "id": 2,
            "product_code": "422-MIX",
            "product_name": "FACTURA MIXTA",
            "descripcion": "$5.000 OFF por bulto de Facturas Mixtas",
            "discount_kind": "nominal",
            "descuento_percent": None,
            "descuento_nominal": 5000.0,
            "precio_promocional": None,
            "lista_precios_id": 1,
            "min_qty_umv": 1,
            "is_mock": True
        },
        {
            "id": 3,
            "product_code": "423",
            "product_name": "CRIOLLO DE HOJALDRE x 11kg*",
            "descripcion": "Precio especial mayorista en Criollo Hojaldre",
            "discount_kind": "fixed_price",
            "descuento_percent": None,
            "descuento_nominal": None,
            "precio_promocional": 48000.00,
            "lista_precios_id": 3,
            "min_qty_umv": 1,
            "is_mock": True
        },
        {
            "id": 4,
            "product_code": "427",
            "product_name": "CHIPÁ x 5kg*",
            "descripcion": "Super Oferta Chipá 5kg",
            "discount_kind": "fixed_price",
            "descuento_percent": None,
            "descuento_nominal": None,
            "precio_promocional": 119000.00,
            "lista_precios_id": 1,
            "min_qty_umv": 1,
            "is_mock": True
        }
    ]
    
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(promos[0].keys()))
        writer.writeheader()
        writer.writerows(promos)
        
    print(f"✅ Generated {OUTPUT_CSV} with {len(promos)} promotions.")
    
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute(f"DELETE FROM {schema}.promociones_semanales;")
        
        for p in promos:
            await conn.execute(f"""
                INSERT INTO {schema}.promociones_semanales (
                    product_code, product_name, descripcion, precio_promocional,
                    fecha_inicio, fecha_fin, lista_precios_id, min_qty_umv, discount_kind,
                    descuento_percent, descuento_nominal, is_mock, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, now(), now()
                );
            """,
            p['product_code'], p['product_name'], p['descripcion'], p['precio_promocional'],
            inicio, fin, p['lista_precios_id'], p['min_qty_umv'], p['discount_kind'],
            p['descuento_percent'], p['descuento_nominal'], p['is_mock']
            )
            
        print(f"✅ Successfully inserted {len(promos)} active promotions into {schema}.promociones_semanales!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(create_promos())
