import os
import sys
import csv
import asyncio
import asyncpg
import requests
import argparse
import time
import urllib3
from dotenv import load_dotenv

# Deshabilitar advertencias de certificados SSL no verificados
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno
dotenv_path = r"c:\Users\marti\suplai-platform\.env"
load_dotenv(dotenv_path)

async def main():
    parser = argparse.ArgumentParser(description="Enriquecer imágenes de productos usando Serper Google Images.")
    parser.add_argument("--esquema", required=True, help="Nombre del esquema/tenant (ej: al_fuego)")
    parser.add_argument("--limit", type=int, help="Límite de productos a procesar (para pruebas)")
    parser.add_argument("--forzar", action="store_true", help="Forzar actualización incluso si ya tienen imagen no-placeholder")
    parser.add_argument("--bucket", help="Nombre del bucket de Supabase Storage. Por defecto: products-{esquema}")
    
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
    
    # 1. Asegurar bucket en Supabase Storage
    print(f"[*] Verificando/Creando bucket público '{bucket_name}'...")
    storage_bucket_url = f"{supabase_url.rstrip('/')}/storage/v1/bucket"
    headers_storage = {
        "Authorization": f"Bearer {supabase_key}",
        "apikey": supabase_key,
        "Content-Type": "application/json"
    }
    
    try:
        bucket_payload = {"id": bucket_name, "name": bucket_name, "public": True}
        # verify=False para mitigar error de certificados locales
        r_bucket = requests.post(storage_bucket_url, headers=headers_storage, json=bucket_payload, verify=False)
        if r_bucket.status_code == 200:
            print(f"✅ Bucket '{bucket_name}' creado con éxito.")
        elif r_bucket.status_code == 400 or "already exists" in r_bucket.text.lower():
            print(f"[*] El bucket '{bucket_name}' ya está disponible.")
        else:
            print(f"[WARN] Error creando bucket: {r_bucket.status_code} - {r_bucket.text}")
    except Exception as e:
        print(f"[WARN] No se pudo asegurar el bucket: {e}")
        
    # 2. Conectar a Base de Datos y descargar productos
    print(f"[*] Conectando a Supabase DB para descargar catálogo de '{schema}'...")
    conn = await asyncpg.connect(db_url)
    try:
        # Obtener todos los productos
        db_products = await conn.fetch(f"SELECT product_code, nombre, image_url FROM {schema}.productos ORDER BY product_code;")
        print(f"[*] Descargados {len(db_products)} productos desde la base de datos.")
    except Exception as e:
        print(f"[FAIL] Error leyendo la tabla {schema}.productos: {e}")
        await conn.close()
        sys.exit(1)
        
    if not db_products:
        print("[FAIL] No hay productos registrados en la base de datos para este esquema.")
        await conn.close()
        sys.exit(1)
        
    # 3. Filtrar productos a procesar
    placeholder_url = "https://images.unsplash.com/photo-1544025162-d76694265947"
    products_to_process = []
    
    for p in db_products:
        img_url = p["image_url"] or ""
        # Si es placeholder, está vacía, o se forzó, la procesamos
        if args.forzar or not img_url or placeholder_url in img_url or "placeholder" in img_url:
            products_to_process.append(p)
            
    print(f"[*] {len(products_to_process)} productos necesitan actualización de imagen (tienen placeholder o están vacíos).")
    
    if limit:
        products_to_process = products_to_process[:limit]
        print(f"[*] Limitando ejecución a los primeros {limit} productos por parámetro --limit.")
        
    if not products_to_process:
        print("[*] No hay productos por procesar. Todos tienen imágenes válidas. Usa --forzar si quieres volver a buscarlas.")
        await conn.close()
        sys.exit(0)
        
    # 4. Procesar y buscar imágenes en Serper
    product_image_mappings = {}  # product_code -> public_url
    product_codes_to_vectorize = []
    
    serper_url = "https://google.serper.dev/images"
    headers_serper = {
        "X-API-KEY": serper_key,
        "Content-Type": "application/json"
    }
    
    print("\n[*] Iniciando enriquecimiento con Serper y descarga de imágenes...")
    
    for i, p in enumerate(products_to_process, 1):
        code = p["product_code"]
        name = p["nombre"]
        
        print(f"[{i}/{len(products_to_process)}] Buscando imagen para: {name} (Código: {code})...")
        
        # Búsqueda optimizada. Si el nombre tiene aclaraciones como "(C)" las removemos para la búsqueda
        search_query = name.replace("(C)", "").strip()
        
        # Payload para Serper
        payload = {
            "q": search_query,
            "gl": "ar", # Búsqueda en Argentina
            "hl": "es", # Idioma Español
            "num": 5    # Traer 5 resultados
        }
        
        success = False
        img_url_public = None
        
        try:
            # verify=False para mitigar error de certificados locales
            r_serper = requests.post(serper_url, headers=headers_serper, json=payload, timeout=10, verify=False)
            if r_serper.status_code == 200:
                res_data = r_serper.json()
                images = res_data.get("images", [])
                
                if not images:
                    print(f"  -> [WARN] No se encontraron imágenes en Google para: {search_query}")
                
                # Intentar descargar los resultados uno a uno hasta que uno funcione
                for idx, img_info in enumerate(images):
                    src_url = img_info.get("imageUrl")
                    if not src_url or src_url.startswith("data:"):
                        continue
                        
                    print(f"  -> Intentando descargar opción {idx+1}: {src_url[:70]}...")
                    try:
                        # Descargar la imagen sin verificar SSL
                        r_img = requests.get(src_url, timeout=5, verify=False, headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                        })
                        if r_img.status_code == 200:
                            # Detectar extensión
                            content_type = r_img.headers.get("Content-Type", "").lower()
                            ext = "jpg"
                            if "png" in content_type:
                                ext = "png"
                            elif "webp" in content_type:
                                ext = "webp"
                            elif "gif" in content_type:
                                ext = "gif"
                            else:
                                # Fallback a partir de la URL
                                if ".png" in src_url.lower():
                                    ext = "png"
                                elif ".webp" in src_url.lower():
                                    ext = "webp"
                                    
                            filename = f"{code}.{ext}"
                            image_bytes = r_img.content
                            
                            # Subir a Supabase Storage sin verificar SSL
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
                                print(f"  -> [WARN] Error al subir a Supabase Storage (HTTP {r_upload.status_code}): {r_upload.text}")
                        else:
                            print(f"  -> [WARN] Error de descarga de imagen (HTTP {r_img.status_code})")
                    except Exception as e:
                        print(f"  -> [WARN] Excepción al descargar/subir opción {idx+1}: {e}")
            else:
                print(f"  -> [FAIL] Error en Serper API (HTTP {r_serper.status_code}): {r_serper.text}")
                
        except Exception as e:
            print(f"  -> [FAIL] Error al consultar Serper API: {e}")
            
        if success and img_url_public:
            product_image_mappings[code] = img_url_public
            product_codes_to_vectorize.append(code)
        else:
            print(f"  -> ❌ No se pudo asignar imagen para {name}")
            
        # Pequeño delay de cortesía
        time.sleep(0.3)
        
    # 5. Actualizar la base de datos
    if product_image_mappings:
        print(f"\n[*] Actualizando URLs de imagen en la base de datos ({len(product_image_mappings)} productos)...")
        try:
            db_updates = []
            for code, img_url in product_image_mappings.items():
                db_updates.append((img_url, code))
                
            await conn.execute("SET statement_timeout = 0;")
            await conn.executemany(f"""
                UPDATE {schema}.productos 
                SET image_url = $1, updated_at = now() 
                WHERE product_code = $2;
            """, db_updates)
            print(f"✅ Base de datos actualizada con éxito.")
        except Exception as e:
            print(f"[FAIL] Error actualizando Supabase DB: {e}")
            await conn.close()
            sys.exit(1)
    else:
        print("\n[*] No se obtuvieron imágenes válidas para actualizar en la base de datos.")
        
    await conn.close()
    
    # 6. Sincronizar archivo CSV local si existe
    csv_path = rf"c:\Users\marti\suplai-platform\implementacion\{schema}\outputs\phase-01-productos.csv"
    if os.path.exists(csv_path) and product_image_mappings:
        print(f"\n[*] Sincronizando archivo CSV local en {csv_path}...")
        rows_to_write = []
        headers_csv = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                headers_csv = reader.fieldnames
                for row_dict in reader:
                    code = row_dict["product_code"]
                    if code in product_image_mappings:
                        row_dict["image_url"] = product_image_mappings[code]
                    rows_to_write.append(row_dict)
                    
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers_csv)
                writer.writeheader()
                writer.writerows(rows_to_write)
            print("✅ Archivo CSV local sincronizado.")
        except Exception as e:
            print(f"[WARN] No se pudo sincronizar el CSV local: {e}")
            
    # 7. Disparar re-vectorización en el backend
    if product_codes_to_vectorize:
        print("\n[*] Disparando re-vectorización en el backend...")
        backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
        vec_url = f"{backend_url}/{schema}/productos/vectorize"
        try:
            # verify=False para el backend también
            resp = requests.post(vec_url, json=product_codes_to_vectorize, timeout=30, verify=False)
            if resp.status_code == 200:
                print(f"✅ Re-vectorización encolada en el backend exitosamente.")
            else:
                print(f"[WARN] Backend devolvió HTTP {resp.status_code} al vectorizar: {resp.text}")
        except Exception as e:
            print(f"[WARN] Error disparando vectorización: {e}")
            
    print("\n==============================================")
    print("PROCESO DE ASOCIACIÓN CON SERPER FINALIZADO")
    print("==============================================")

if __name__ == '__main__':
    asyncio.run(main())
