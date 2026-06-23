import os
import sys
import csv
import json
import asyncio
import asyncpg
import requests
import unicodedata
from dotenv import load_dotenv

# Cargar variables de entorno
dotenv_path = r"c:\Users\marti\suplai-platform\.env"
load_dotenv(dotenv_path)

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Normalizar alias
def normalizar_alias(alias_raw: str) -> str:
    alias_lower = alias_raw.lower().strip()
    alias_flat = unicodedata.normalize('NFKD', alias_lower)
    return "".join([c for c in alias_flat if 'a' <= c <= 'z' or '0' <= c <= '9'])

async def cargar():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] La variable de entorno SUPABASE_DB_URL no está configurada en .env.")
        sys.exit(1)
        
    schema = "distribuidora_lyl"
    
    # Path to CSV files
    products_csv = rf"c:\Users\marti\suplai-platform\implementacion\{schema}\outputs\phase-01-productos.csv"
    if not os.path.exists(products_csv):
        print(f"[FAIL] No se encontró {products_csv}")
        sys.exit(1)
        
    # Read products
    products = []
    with open(products_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append(row)
            
    print(f"[*] Leídos {len(products)} productos del CSV.")
    
    conn = await asyncpg.connect(db_url)
    try:
        # Disable timeout for DDL and large inserts
        await conn.execute("SET statement_timeout = 0;")
        
        # 1. Insert Lists of prices
        print("[*] Insertando listas de precios...")
        await conn.execute(f"""
            INSERT INTO {schema}.listas_precios (id, nombre, descripcion, activa, es_publica, is_mock, created_at, updated_at) 
            VALUES 
              (1, 'Lista 1', 'Lista Base (Público)', true, true, true, now(), now()),
              (2, 'Lista 2', 'Lista Minorista Sugerido', true, true, true, now(), now()),
              (3, 'Lista 3', 'Lista Mayorista Especial', true, true, true, now(), now()),
              (4, 'Lista 4', 'Lista Gran Distribuidor', true, true, true, now(), now())
            ON CONFLICT (id) DO UPDATE SET 
              nombre = EXCLUDED.nombre,
              descripcion = EXCLUDED.descripcion,
              activa = EXCLUDED.activa,
              es_publica = EXCLUDED.es_publica,
              updated_at = now();
        """)
        print("✅ Listas de precios insertadas/actualizadas.")
        
        # 2. Insert Products in batches
        print("[*] Limpiando productos, precios y alias anteriores...")
        await conn.execute(f"DELETE FROM {schema}.precios_productos;")
        await conn.execute(f"DELETE FROM {schema}.productos_aliases;")
        await conn.execute(f"DELETE FROM {schema}.productos;")
        print("✅ Tablas limpias.")
        
        print("[*] Insertando productos en la base de datos...")
        products_data = []
        aliases_data = []
        product_codes = []
        
        for p in products:
            code = p["product_code"]
            product_codes.append(code)
            
            # Parse numeric fields
            stock = int(p["stock"]) if p["stock"] else 0
            pack_size = int(p["unidades_por_bulto"]) if p["unidades_por_bulto"] else 1
            rotacion = float(p["rotacion_index"]) if p["rotacion_index"] else 0.1
            priority = float(p["mental_priority"]) if p["mental_priority"] else 0.0
            is_mock = p["is_mock"].lower() == "true"
            
            products_data.append((
                code,
                p["nombre"],
                p["descripcion"],
                p["image_url"],
                stock,
                pack_size,
                "1", # unidad_minima_de_venta
                p["umv_tipo"] or "unidad",
                rotacion,
                priority,
                True, # en_catalogo
                is_mock
            ))
            
            # Prepare aliases
            aliases_str = p["aliases"]
            if aliases_str:
                parts = [a.strip() for a in aliases_str.split("|") if a.strip()]
                for raw_alias in parts:
                    norm = normalizar_alias(raw_alias)
                    if norm:
                        aliases_data.append((
                            code,
                            raw_alias,
                            norm,
                            1.0 # weight
                        ))
                        
        # Batch insert products
        await conn.executemany(f"""
            INSERT INTO {schema}.productos (
                product_code, nombre, descripcion, image_url, stock, unidades_por_bulto,
                unidad_minima_de_venta, umv_tipo, rotacion_index, mental_priority, en_catalogo, is_mock,
                created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, now(), now())
        """, products_data)
        print(f"✅ {len(products_data)} productos insertados.")
        
        # Batch insert aliases
        if aliases_data:
            await conn.executemany(f"""
                INSERT INTO {schema}.productos_aliases (
                    product_code, alias_raw, alias_norm, weight,
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, now(), now())
            """, aliases_data)
            print(f"✅ {len(aliases_data)} alias comerciales insertados.")
            
        # 3. Insert Prices from the 4 lists
        print("[*] Insertando listas de precios de productos...")
        prices_inserted = 0
        for list_id in range(1, 5):
            price_csv = rf"c:\Users\marti\suplai-platform\implementacion\{schema}\outputs\phase-01-lista-precios-{list_id}.csv"
            if not os.path.exists(price_csv):
                print(f"[WARN] No se encontró {price_csv}")
                continue
                
            prices_data = []
            with open(price_csv, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    prices_data.append((
                        row["product_code"],
                        list_id,
                        float(row["precio_unidad"]),
                        row["is_mock"].lower() == "true"
                    ))
                    
            if prices_data:
                await conn.executemany(f"""
                    INSERT INTO {schema}.precios_productos (
                        product_code, lista_precios_id, precio_unidad, is_mock
                    ) VALUES ($1, $2, $3, $4)
                """, prices_data)
                prices_inserted += len(prices_data)
                
        print(f"✅ {prices_inserted} precios registrados en las listas.")
        
        # 4. Re-vectorization (Critical)
        print("[*] Disparando la re-vectorización en el backend...")
        backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
        vec_url = f"{backend_url}/{schema}/productos/vectorize"
        
        try:
            resp = requests.post(vec_url, json=product_codes, timeout=30)
            if resp.status_code == 200:
                print(f"✅ Re-vectorización encolada correctamente en el backend (HTTP 200).")
            else:
                print(f"[WARN] El backend devolvió HTTP {resp.status_code} al vectorizar: {resp.text}")
        except Exception as e:
            print(f"[WARN] Error al conectar con el endpoint de vectorización: {e}")
            
    except Exception as e:
        print(f"[FAIL] Error durante la carga de catálogo: {e}")
        sys.exit(1)
    finally:
        await conn.close()
        
    print("\n==============================================")
    print("PROCESO DE CARGA DE CATÁLOGO COMPLETADO CON ÉXITO")
    print("==============================================")

if __name__ == '__main__':
    asyncio.run(cargar())
