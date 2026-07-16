import os
import sys
import csv
import asyncio
import asyncpg
import requests
import argparse
import time
import urllib3
import unicodedata
from dotenv import load_dotenv

# Deshabilitar advertencias SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configurar stdout a UTF-8 en Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno
dotenv_path = r"c:\Users\marti\suplai-platform\.env"
load_dotenv(dotenv_path)

def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    flat = unicodedata.normalize('NFKD', str(texto).lower().strip())
    # Mantener alfanuméricos y espacios para la normalización básica
    return "".join([c for c in flat if c.isalnum() or c == ' ']).strip()

def normalizar_para_alias(texto: str) -> str:
    if not texto:
        return ""
    flat = unicodedata.normalize('NFKD', str(texto).lower().strip())
    return "".join([c for c in flat if c.isalnum()])

def parse_stock(stock_str):
    try:
        # Convertir a float y luego a int (ej: "14.05" -> 14)
        return int(float(str(stock_str).replace(',', '.')))
    except Exception:
        return 0

async def main():
    parser = argparse.ArgumentParser(description="Importar y enriquecer los productos faltantes de Al Fuego.")
    parser.add_argument("--esquema", default="al_fuego", help="Nombre del esquema/tenant")
    parser.add_argument("--limit", type=int, help="Límite de productos a procesar (para pruebas)")
    parser.add_argument("--bucket", help="Nombre del bucket de Supabase Storage")
    
    args = parser.parse_args()
    schema = args.esquema
    limit = args.limit
    
    db_url = os.getenv("SUPABASE_DB_URL")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    serper_key = os.getenv("SERPER_API_KEY")
    
    if not db_url or not supabase_url or not supabase_key or not serper_key:
        print("[FAIL] Faltan variables de entorno requeridas (SUPABASE_DB_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SERPER_API_KEY).")
        sys.exit(1)
        
    bucket_name = args.bucket or f"products-{schema}"
    
    # 1. Asegurar la conexión
    print(f"[*] Conectando a Supabase DB para catálogo de '{schema}'...")
    conn = await asyncpg.connect(db_url)
    
    # Obtener productos actuales en base de datos
    db_products = await conn.fetch(f"SELECT product_code FROM {schema}.productos;")
    db_codes = {p["product_code"] for p in db_products}
    print(f"[*] Encontrados {len(db_codes)} productos en la base de datos.")
    
    # 2. Leer archivo LDP-AlFuego.csv
    csv_in_path = rf"c:\Users\marti\suplai-platform\implementacion\{schema}\inputs\LDP-AlFuego.csv"
    if not os.path.exists(csv_in_path):
        csv_in_path = rf"c:\Users\marti\suplai-platform\implementacion\{schema}\inputs\LDP_AlFuego.csv"
        
    if not os.path.exists(csv_in_path):
        print(f"[FAIL] No se encontró el archivo de input en: {csv_in_path}")
        await conn.close()
        sys.exit(1)
        
    missing_products = []
    
    with open(csv_in_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("Producto Codigo") or row.get("product_code")
            name = row.get("Producto Nombre") or row.get("nombre")
            if code:
                code_clean = code.strip()
                if code_clean not in db_codes:
                    missing_products.append({
                        "product_code": code_clean,
                        "nombre": name.strip() if name else "",
                        "categoria": row.get("Categoria", "").strip(),
                        "precio": row.get("Precio", "").strip(),
                        "stock": row.get("Stock", "").strip()
                    })
                    
    print(f"[*] Detectados {len(missing_products)} productos faltantes en la DB.")
    
    if limit:
        missing_products = missing_products[:limit]
        print(f"[*] Limitando ejecución a los primeros {limit} productos por parámetro --limit.")
        
    if not missing_products:
        print("[*] No hay productos faltantes para procesar.")
        await conn.close()
        sys.exit(0)
        
    # 3. Procesar, buscar imagen y cargar cada producto
    serper_url = "https://google.serper.dev/images"
    headers_serper = {
        "X-API-KEY": serper_key,
        "Content-Type": "application/json"
    }
    
    placeholder_default = "https://images.unsplash.com/photo-1544025162-d76694265947?w=400"
    imported_count = 0
    product_codes_to_vectorize = []
    
    # Para almacenar la información y actualizar el CSV de salida local
    new_csv_rows = []
    
    for idx, item in enumerate(missing_products, 1):
        code = item["product_code"]
        name = item["nombre"]
        cat = item["categoria"]
        stock_val = parse_stock(item["stock"])
        
        print(f"\n[{idx}/{len(missing_products)}] Procesando {name} (Código: {code})...")
        
        search_query = name.replace("(C)", "").strip()
        payload = {
            "q": search_query,
            "gl": "ar",
            "hl": "es",
            "num": 5
        }
        
        success = False
        img_url_public = placeholder_default
        
        try:
            r_serper = requests.post(serper_url, headers=headers_serper, json=payload, timeout=10, verify=False)
            if r_serper.status_code == 200:
                res_data = r_serper.json()
                images = res_data.get("images", [])
                
                for img_idx, img_info in enumerate(images):
                    src_url = img_info.get("imageUrl")
                    if not src_url or src_url.startswith("data:"):
                        continue
                        
                    print(f"  -> Descargando imagen opción {img_idx+1}: {src_url[:60]}...")
                    try:
                        r_img = requests.get(src_url, timeout=5, verify=False, headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                        })
                        if r_img.status_code == 200:
                            content_type = r_img.headers.get("Content-Type", "").lower()
                            ext = "jpg"
                            if "png" in content_type:
                                ext = "png"
                            elif "webp" in content_type:
                                ext = "webp"
                                
                            filename = f"{code}.{ext}"
                            image_bytes = r_img.content
                            
                            # Subir a Supabase
                            upload_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket_name}/{filename}"
                            headers_upload = {
                                "Authorization": f"Bearer {supabase_key}",
                                "apikey": supabase_key,
                                "Content-Type": content_type or f"image/{ext}",
                                "x-upsert": "true"
                            }
                            
                            r_upload = requests.post(upload_url, headers=headers_upload, data=image_bytes, verify=False)
                            if r_upload.status_code == 200:
                                img_url_public = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket_name}/{filename}"
                                print(f"  -> ✅ Imagen subida exitosamente: {img_url_public}")
                                success = True
                                break
                            else:
                                print(f"  -> [WARN] Error subiendo a Storage (HTTP {r_upload.status_code}): {r_upload.text}")
                        else:
                            print(f"  -> [WARN] Error de descarga (HTTP {r_img.status_code})")
                    except Exception as e:
                        print(f"  -> [WARN] Excepción al procesar opción {img_idx+1}: {e}")
            else:
                print(f"  -> [FAIL] Error en Serper API (HTTP {r_serper.status_code}): {r_serper.text}")
        except Exception as e:
            print(f"  -> [FAIL] Excepción consultando Serper: {e}")
            
        # Determinar si es pesable
        es_pesable_val = cat.lower() in ("granel-mp", "achuras", "granel")
        
        # Generar descripción
        desc = f"{name}. Producto de {cat} en catálogo Al Fuego."
        
        # 4. Insertar en la Base de Datos
        try:
            # A. Insertar en productos
            await conn.execute(f"""
                INSERT INTO {schema}.productos (
                    product_code, nombre, stock, image_url, en_catalogo, is_mock, 
                    unidades_por_bulto, cantidad_minima_de_venta, umv_tipo, 
                    rotacion_index, mental_priority, es_pesable, descripcion, 
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, now(), now())
                ON CONFLICT (product_code) DO UPDATE 
                SET nombre = EXCLUDED.nombre, stock = EXCLUDED.stock, image_url = EXCLUDED.image_url, updated_at = now();
            """, code, name, stock_val, img_url_public, True, False, 1, 1, 'unidad', 0.1, 0.0, es_pesable_val, desc)
            
            # B. Insertar precios en precios_productos para las 4 listas
            for lista_id in (1, 2, 3, 4):
                await conn.execute(f"""
                    INSERT INTO {schema}.precios_productos (
                        product_code, lista_precios_id, precio_unidad, is_mock
                    ) VALUES ($1, $2, 0.0, false)
                    ON CONFLICT (product_code, lista_precios_id) DO NOTHING;
                """, code, lista_id)
                
            # C. Insertar alias
            alias_norm_val = normalizar_para_alias(name)
            await conn.execute(f"""
                INSERT INTO {schema}.productos_aliases (
                    alias_norm, alias_raw, product_code, weight, created_at, updated_at
                ) VALUES ($1, $2, $3, 1.0, now(), now())
                ON CONFLICT (alias_norm, product_code) DO NOTHING;
            """, alias_norm_val, name, code)
            
            print(f"  -> ✅ Producto {code} insertado exitosamente en DB.")
            imported_count += 1
            product_codes_to_vectorize.append(code)
            
            # Guardar para el CSV
            new_csv_rows.append({
                "product_code": code,
                "nombre": name,
                "precio_lista_1": "0.0",
                "stock": str(stock_val),
                "unidades_por_bulto": "1",
                "unidad_minima_de_venta": "unidad",
                "umv_tipo": "unidad",
                "categoria_1": cat,
                "categoria_2": "",
                "categoria_3": "",
                "categoria_4": "",
                "aliases": f"{name}|{code}",
                "rotacion_index": "0.1",
                "mental_priority": "0.0",
                "descripcion": desc,
                "image_url": img_url_public,
                "en_catalogo": "true",
                "is_mock": "false",
                "fuente_hoja": cat
            })
            
        except Exception as e:
            print(f"  -> ❌ Error al insertar {code} en la DB: {e}")
            
        time.sleep(0.3)
        
    await conn.close()
    
    # 5. Sincronizar archivo CSV local (outputs/phase-01-productos.csv)
    csv_out_path = rf"c:\Users\marti\suplai-platform\implementacion\{schema}\outputs\phase-01-productos.csv"
    if os.path.exists(csv_out_path) and new_csv_rows:
        print(f"\n[*] Sincronizando archivo CSV local en {csv_out_path}...")
        try:
            # Leer filas existentes
            existing_rows = []
            headers_csv = []
            with open(csv_out_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                headers_csv = reader.fieldnames
                existing_rows = list(reader)
                
            # Evitar duplicados por product_code
            existing_codes = {r["product_code"] for r in existing_rows}
            added_count = 0
            for r in new_csv_rows:
                if r["product_code"] not in existing_codes:
                    existing_rows.append(r)
                    added_count += 1
                    
            # Escribir de nuevo
            with open(csv_out_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers_csv)
                writer.writeheader()
                writer.writerows(existing_rows)
            print(f"✅ Sincronizado. Agregados {added_count} nuevos productos al CSV local.")
        except Exception as e:
            print(f"[WARN] Error al sincronizar el CSV local: {e}")
            
    # 6. Disparar re-vectorización en el backend
    if product_codes_to_vectorize:
        print("\n[*] Disparando re-vectorización en el backend...")
        backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
        vec_url = f"{backend_url}/{schema}/productos/vectorize"
        try:
            resp = requests.post(vec_url, json=product_codes_to_vectorize, timeout=30, verify=False)
            if resp.status_code == 200:
                print(f"✅ Re-vectorización encolada en el backend exitosamente.")
            else:
                print(f"[WARN] Backend devolvió HTTP {resp.status_code} al vectorizar: {resp.text}")
        except Exception as e:
            print(f"[WARN] Error disparando vectorización: {e}")
            
    print("\n==============================================")
    print("PROCESO DE IMPORTACIÓN Y ENRIQUECIMIENTO FINALIZADO")
    print(f"Productos importados exitosamente: {imported_count}")
    print("==============================================")

if __name__ == '__main__':
    asyncio.run(main())
