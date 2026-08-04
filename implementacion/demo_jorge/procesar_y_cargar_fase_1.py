import os
import sys
import csv
import json
import asyncio
import asyncpg
import requests
import re
import unicodedata
from dotenv import load_dotenv

# Cargar .env de la raíz del workspace
dotenv_path = r"c:\Users\marti\suplai-platform\.env"
load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Normalizar alias para productos_aliases
def normalizar_alias(alias_raw: str) -> str:
    alias_lower = alias_raw.lower().strip()
    alias_flat = unicodedata.normalize('NFKD', alias_lower)
    return "".join([c for c in alias_flat if 'a' <= c <= 'z' or '0' <= c <= '9' or c == ' ']).strip()

# Identificar marcas conocidas para asignar rotacion_index
def determine_brand(nombre: str) -> str:
    n_lower = nombre.lower()
    if "aguila" in n_lower:
        return "Aguila"
    if "arcor" in n_lower:
        return "Arcor"
    if "cofler" in n_lower:
        return "Cofler"
    if "bonobon" in n_lower or "bon o bon" in n_lower:
        return "Bon o Bon"
    if "bc" in n_lower:
        return "BC"
    if "block" in n_lower:
        return "Block"
    if "mogul" in n_lower:
        return "Mogul"
    if "bagley" in n_lower:
        return "Bagley"
    if "butter toffees" in n_lower or "butter toffee" in n_lower:
        return "Butter Toffees"
    if "godet" in n_lower:
        return "Godet"
    if "saladillo" in n_lower:
        return "Saladillo"
    if "ser" in n_lower:
        return "Ser"
    
    # Tomar la primera palabra de más de 2 caracteres que no sea genérica
    words = nombre.split()
    generic_words = {
        "gaseosa", "agua", "soda", "jugo", "chocolatada", "lata", "saborizada", 
        "yerba", "alfajor", "galletitas", "chupetín", "chupetin", "mate", 
        "cerveza", "licor", "chocolate", "caramelo", "caramelos", "chicle", 
        "chicles", "galleta", "oblea", "pan", "budin", "budín", 
        "bolsa", "paquete", "turrón", "turron", "pastilla", "pastillas", 
        "chizitos", "chizito", "papas", "maní", "mani", "semillas", "semilla", 
        "goma", "gomas", "gominola", "gominolas", "dulce", "caja", "pack"
    }
    for word in words:
        w_clean = word.lower().strip(",.-()\"'/+* \t")
        if w_clean not in generic_words and len(w_clean) > 2:
            return word.strip(",.-()\"'/+* \t")
    return "Arcor"

# Detectar si una descripción tiene fluff
def tiene_fluff(desc: str) -> bool:
    if not desc:
        return True
    fluff_words = [
        "descubre", "irresistible", "delicioso", "tentacion", "tentación", "cautivará", "cautivara",
        "exhibir", "kiosco", "almacen", "almacén", "margen", "rentabilidad", "compra por impulso",
        "ventas", "incrementar", "fidelizar", "¡", "no te quedes", "must-have", "dulce momento",
        "perfecto para", "ideal para", "cautivar", "exhibiciones", "mostrador", "potencia tus"
    ]
    desc_lower = desc.lower()
    return any(fw in desc_lower for fw in fluff_words)

# Enriquecer un lote de productos usando OpenAI
async def enrich_batch_openai(batch):
    if not OPENAI_API_KEY:
        print("[WARN] OPENAI_API_KEY no encontrada. Usando fallback básico.")
        return []

    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    batch_data = [{"product_code": p["product_code"], "nombre": p["nombre"], "descripcion_sucia": p.get("descripcion_sucia", "")} for p in batch]
    
    prompt_sistema = (
        "Sos un sistema experto en auditoría de catálogos e indexación RAG para e-commerce en Argentina.\n"
        "Se te proporcionará una lista de productos en formato JSON con su código, nombre y descripción previa (que contiene fluff/marketing).\n"
        "Para cada producto, debes generar un objeto JSON que contenga:\n"
        "- 'product_code': El código de producto exacto provisto en la entrada (ej. '11601' o '13332'). Es obligatorio e indispensable que coincida exactamente con el de la entrada.\n"
        "- 'categoria_2': Categoría de nivel 2 (ej: Bebidas con Gas, Chocolates, Golosinas, Jugos, Aguas, Galletas, Almacén, etc.)\n"
        "- 'categoria_3': Categoría de nivel 3 (ej: Gaseosas, Alfajores, Caramelos, Aguas Minerales, Chocolates en Barra, etc.)\n"
        "- 'categoria_4': Categoría de nivel 4 (ej: Cola, Naranja, Frutilla, con Maní, Relleno, o vacío si no aplica)\n"
        "- 'aliases': Sinónimos comerciales coloquiales de Argentina separados por '|' en minúsculas (ej: 'gaseosa de pomelo | secco pomelo | secco de pomelo')\n"
        "- 'descripcion': Descripción comercial RAG de entre 10 y 25 palabras, estrictamente LIBRE DE FLUFF/MARKETING. "
        "Debe ser directa y empezar con el sustantivo de la categoría. Prohibido usar palabras como 'delicioso', 'irresistible', 'suave', 'ideal', 'perfecto', 'descubre', 'disfruta', 'cautivará', 'atractivo', ni mencionar ventas, kioscos, márgenes, rentabilidad o compras por impulso.\n"
        "  * Ejemplo correcto: 'Tableta de chocolate blanco con trozos de maní tostado, marca Arcor, presentación de 80 g.'\n"
        "  * Ejemplo incorrecto: 'Descubre el irresistible Chocolate Blanco con Maní, ideal para tu kiosco...'\n\n"
        "Responde estrictamente con un objeto JSON que contenga la llave 'productos' con la lista de respuestas correspondientes a cada 'product_code', asegurando que cada objeto tenga la clave 'product_code' con su valor."
    )
    
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": json.dumps(batch_data, ensure_ascii=False)}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0
    }
    
    for attempt in range(3):
        try:
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=payload, timeout=50)
            )
            if res.status_code == 200:
                res_data = json.loads(res.json()["choices"][0]["message"]["content"])
                return res_data.get("productos", [])
            else:
                print(f"[WARN] OpenAI error (HTTP {res.status_code}): {res.text}")
        except Exception as e:
            print(f"[WARN] Intento {attempt+1} falló para lote OpenAI: {e}")
            await asyncio.sleep(1)
            
    return []

async def main():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL no configurada en .env.")
        sys.exit(1)
        
    schema = "demo_jorge"
    
    print("[*] Iniciando Fase 1 para el esquema:", schema)
    
    # 1. Conectarse a Supabase y leer taxonomías/aliases del esquema 'demo'
    print("[*] Leyendo datos históricos del esquema 'demo' en Supabase...")
    conn = await asyncpg.connect(db_url)
    
    try:
        # Obtener todas las categorías del esquema demo
        cat_rows = await conn.fetch("SELECT id, name, parent_id FROM demo.categorias")
        cat_map = {r["id"]: {"name": r["name"], "parent_id": r["parent_id"]} for r in cat_rows}
        
        # Función para construir la jerarquía de categorías
        def get_category_hierarchy(cat_id):
            hierarchy = []
            curr = cat_id
            visited = set()
            while curr is not None and curr not in visited:
                visited.add(curr)
                cat_info = cat_map.get(curr)
                if not cat_info:
                    break
                hierarchy.append(cat_info["name"])
                curr = cat_info["parent_id"]
            hierarchy.reverse()
            return hierarchy
            
        # Obtener mapeo de producto a categorías en demo
        prod_cat_rows = await conn.fetch("SELECT product_code, categoria_id FROM demo.product_categories")
        prod_cat_map = {}
        for r in prod_cat_rows:
            p_code = r["product_code"]
            cat_id = r["categoria_id"]
            hierarchy = get_category_hierarchy(cat_id)
            # Rellenar hasta 4 niveles
            while len(hierarchy) < 4:
                hierarchy.append("")
            prod_cat_map[p_code] = hierarchy[:4]
            
        # Obtener aliases de demo
        alias_rows = await conn.fetch("SELECT product_code, alias_raw FROM demo.productos_aliases")
        prod_alias_map = {}
        for r in alias_rows:
            p_code = r["product_code"]
            alias = r["alias_raw"]
            if p_code not in prod_alias_map:
                prod_alias_map[p_code] = []
            prod_alias_map[p_code].append(alias)
            
        print(f"  ✅ Mapeos de categorías indexados: {len(prod_cat_map)} productos.")
        print(f"  ✅ Mapeos de aliases indexados: {len(prod_alias_map)} productos.")
        
    except Exception as e:
        print(f"[WARN] Error al consultar datos del esquema demo: {e}. Se usarán inferencias completas.")
        prod_cat_map = {}
        prod_alias_map = {}
        
    # 2. Leer los inputs provistos
    input_dir = rf"c:\Users\marti\suplai-platform\implementacion\{schema}\inputs"
    output_dir = rf"c:\Users\marti\suplai-platform\implementacion\{schema}\outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    prod_csv_path = os.path.join(input_dir, "productos_rows (1).csv")
    price_csv_path = os.path.join(input_dir, "Supabase Snippet Filter Products by Price List.csv")
    
    if not os.path.exists(prod_csv_path) or not os.path.exists(price_csv_path):
        print(f"[FAIL] Faltan archivos de entrada en {input_dir}")
        sys.exit(1)
        
    # Cargar precios
    precios = {}
    with open(price_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            precios[row["product_code"]] = float(row["precio_unidad"])
            
    # Cargar productos
    raw_products = []
    with open(prod_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_products.append(row)
            
    print(f"[*] Total productos leídos: {len(raw_products)}. Total precios leídos: {len(precios)}.")
    
    # Cruzar datos: filtrar únicamente los que tienen precio en el CSV de precios
    products_to_process = []
    for p in raw_products:
        code = p["product_code"]
        if code in precios:
            p["precio_lista_1"] = precios[code]
            products_to_process.append(p)
            
    print(f"[*] Productos a procesar (con precio coincidente): {len(products_to_process)}.")
    
    # 3. Clasificar productos: los que requieren llamadas a la IA y los que no
    ia_batch = []
    enriched_products = []
    
    # Marcas líderes de Arcor para indexación de rotación
    leading_brands = {"aguila", "arcor", "cofler", "bonobon", "bon o bon", "bc", "block", "mogul", "bagley", "butter toffees"}
    
    for p in products_to_process:
        code = p["product_code"]
        nombre = p["nombre"]
        desc_original = p["descripcion"]
        
        # Mapear de 'demo' si existe
        cat_hierarchy = prod_cat_map.get(code, ["", "", "", ""])
        aliases_list = prod_alias_map.get(code, [])
        aliases_str = "|".join(aliases_list)
        
        brand = determine_brand(nombre)
        rotacion = 0.85 if brand.lower() in leading_brands else 0.15
        
        # Si no existe en demo, o su descripción tiene fluff, o faltan categorías, lo mandamos a IA
        necesita_ia = (code not in prod_cat_map) or tiene_fluff(desc_original) or (not cat_hierarchy[1]) or (not aliases_str)
        
        item = {
            "product_code": code,
            "nombre": nombre,
            "precio_lista_1": p["precio_lista_1"],
            "stock": int(p["stock"]) if p["stock"] and int(p["stock"]) > 0 else int(100 + (rotacion * 350)),
            "unidades_por_bulto": int(p["unidades_por_bulto"]) if p["unidades_por_bulto"] else 1,
            "unidad_minima_de_venta": p["unidad_minima_de_venta"] or "1",
            "umv_tipo": p["umv_tipo"] or "unidad",
            "categoria_1": cat_hierarchy[0] or "Almacén",
            "categoria_2": cat_hierarchy[1],
            "categoria_3": cat_hierarchy[2],
            "categoria_4": cat_hierarchy[3],
            "aliases": aliases_str,
            "rotacion_index": rotacion,
            "mental_priority": float(p["mental_priority"]) if p["mental_priority"] else 0.0,
            "descripcion": desc_original,
            "image_url": p["image_url"] or "https://via.placeholder.com/300",
            "en_catalogo": p["en_catalogo"] or "true",
            "is_mock": "true",
            "fuente_hoja": "Importación CSV"
        }
        
        if necesita_ia:
            item["descripcion_sucia"] = desc_original
            ia_batch.append(item)
        else:
            enriched_products.append(item)
            
    print(f"[*] Productos que se usarán directamente de cache/demo: {len(enriched_products)}.")
    print(f"[*] Productos que requieren limpieza de descripción o taxonomía con OpenAI: {len(ia_batch)}.")
    
    # 4. Procesar lotes OpenAI si hay productos que lo requieren
    if ia_batch:
        print("[*] Llamando a OpenAI en lotes concurrentes...")
        batch_size = 40
        batches = [ia_batch[i:i + batch_size] for i in range(0, len(ia_batch), batch_size)]
        
        tasks = [enrich_batch_openai(b) for b in batches]
        results = await asyncio.gather(*tasks)
        
        # Aplanar resultados de OpenAI
        enrich_lookup = {}
        for r_list in results:
            for item in r_list:
                if "product_code" in item:
                    enrich_lookup[item["product_code"]] = item
                    
        # Mezclar con los datos originales
        merged_count = 0
        for item in ia_batch:
            code = item["product_code"]
            enrich = enrich_lookup.get(code, {})
            
            # Rellenar campos enriquecidos por IA
            if enrich:
                merged_count += 1
                item["categoria_2"] = enrich.get("categoria_2", item["categoria_2"] or "Golosinas")
                item["categoria_3"] = enrich.get("categoria_3", item["categoria_3"] or "Varios")
                item["categoria_4"] = enrich.get("categoria_4", item["categoria_4"])
                item["aliases"] = enrich.get("aliases", item["aliases"] or item["nombre"].lower())
                item["descripcion"] = enrich.get("descripcion", item["descripcion"])
            
            # Limpiar campos auxiliares antes de guardar
            if "descripcion_sucia" in item:
                del item["descripcion_sucia"]
                
            enriched_products.append(item)
            
        print(f"  ✅ Mezclados {merged_count} de {len(ia_batch)} productos desde OpenAI.")
            
    print(f"[*] Procesamiento de IA completado. Catálogo consolidado: {len(enriched_products)} productos.")
    
    # 5. Escribir entregables CSV
    products_csv_path = os.path.join(output_dir, "phase-01-productos.csv")
    headers = [
        "product_code", "nombre", "precio_lista_1", "stock", "unidades_por_bulto",
        "unidad_minima_de_venta", "umv_tipo", "categoria_1", "categoria_2",
        "categoria_3", "categoria_4", "aliases", "rotacion_index", "mental_priority",
        "descripcion", "image_url", "en_catalogo", "is_mock", "fuente_hoja"
    ]
    
    with open(products_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for p in enriched_products:
            writer.writerow([
                p["product_code"],
                p["nombre"],
                p["precio_lista_1"],
                p["stock"],
                p["unidades_por_bulto"],
                p["unidad_minima_de_venta"],
                p["umv_tipo"],
                p["categoria_1"],
                p["categoria_2"],
                p["categoria_3"],
                p["categoria_4"],
                p["aliases"],
                p["rotacion_index"],
                p["mental_priority"],
                p["descripcion"],
                p["image_url"],
                p["en_catalogo"],
                p["is_mock"],
                p["fuente_hoja"]
            ])
            
    print(f"✅ Catálogo guardado en: {products_csv_path}")
    
    # Generar 4 listas de precios
    multipliers = {
        1: 1.00,
        2: 1.15,
        3: 0.90,
        4: 0.85
    }
    
    for list_id, multiplier in multipliers.items():
        price_csv_path = os.path.join(output_dir, f"phase-01-lista-precios-{list_id}.csv")
        with open(price_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["product_code", "precio_unidad", "is_mock"])
            for p in enriched_products:
                price = round(p["precio_lista_1"] * multiplier, 2)
                writer.writerow([p["product_code"], price, "true"])
        print(f"✅ Lista de precios {list_id} guardada en: {price_csv_path}")
        
    # 6. Carga a Supabase (esquema 'demo_jorge')
    print(f"[*] Conectando a Supabase para cargar datos en el esquema '{schema}'...")
    
    try:
        # Inhabilitar statement_timeout para cargas masivas
        await conn.execute("SET statement_timeout = 0;")
        
        # A. Crear las listas de precios
        print("  - Insertando listas de precios (1-4)...")
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
        
        # B. Limpiar tablas
        print("  - Limpiando tablas de catálogo previas en demo_jorge...")
        await conn.execute(f"DELETE FROM {schema}.precios_productos;")
        await conn.execute(f"DELETE FROM {schema}.productos_aliases;")
        await conn.execute(f"DELETE FROM {schema}.productos;")
        
        # C. Preparar datos de productos y aliases
        products_data = []
        aliases_data = []
        product_codes = []
        
        for p in enriched_products:
            code = p["product_code"]
            product_codes.append(code)
            
            # Mapeo a tupla
            products_data.append((
                code,
                p["nombre"],
                p["descripcion"],
                p["image_url"],
                p["stock"],
                p["unidades_por_bulto"],
                p["unidad_minima_de_venta"],
                p["umv_tipo"],
                p["rotacion_index"],
                p["mental_priority"],
                True, # en_catalogo
                True  # is_mock
            ))
            
            # Procesar aliases
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
                        
        # D. Insertar productos (executemany)
        print(f"  - Cargando {len(products_data)} productos a {schema}.productos...")
        await conn.executemany(f"""
            INSERT INTO {schema}.productos (
                product_code, nombre, descripcion, image_url, stock, unidades_por_bulto,
                unidad_minima_de_venta, umv_tipo, rotacion_index, mental_priority, en_catalogo, is_mock,
                created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, now(), now())
        """, products_data)
        
        # E. Insertar aliases (executemany)
        if aliases_data:
            print(f"  - Cargando {len(aliases_data)} aliases comerciales a {schema}.productos_aliases...")
            await conn.executemany(f"""
                INSERT INTO {schema}.productos_aliases (
                    product_code, alias_raw, alias_norm, weight,
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, now(), now())
            """, aliases_data)
            
        # F. Insertar precios para las 4 listas
        print("  - Cargando precios para las 4 listas a precios_productos...")
        prices_inserted = 0
        for list_id in range(1, 5):
            prices_data = []
            for p in enriched_products:
                price = round(p["precio_lista_1"] * multipliers[list_id], 2)
                prices_data.append((
                    p["product_code"],
                    list_id,
                    price,
                    True # is_mock
                ))
            if prices_data:
                await conn.executemany(f"""
                    INSERT INTO {schema}.precios_productos (
                        product_code, lista_precios_id, precio_unidad, is_mock
                    ) VALUES ($1, $2, $3, $4)
                """, prices_data)
                prices_inserted += len(prices_data)
                
        print(f"  ✅ Carga en Supabase finalizada. {len(products_data)} productos, {len(aliases_data)} alias y {prices_inserted} precios registrados.")
        
        # G. Re-vectorización del catálogo (CRÍTICO)
        print("[*] Iniciando llamada de re-vectorización al backend...")
        backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
        vec_url = f"{backend_url}/{schema}/productos/vectorize"
        
        try:
            resp = requests.post(vec_url, json=product_codes, timeout=40)
            if resp.status_code == 200:
                print("  ✅ Re-vectorización encolada exitosamente en el backend (HTTP 200).")
            else:
                print(f"  [WARN] El backend devolvió HTTP {resp.status_code} al vectorizar: {resp.text}")
        except Exception as e:
            print(f"  [WARN] Error de red al solicitar vectorización al backend: {e}")
            
        # H. Determinar marca líder
        brand_counts = {}
        for p in enriched_products:
            b = determine_brand(p["nombre"])
            brand_counts[b] = brand_counts.get(b, 0) + 1
        sorted_brands = sorted(brand_counts.items(), key=lambda x: x[1], reverse=True)
        marca_lider = sorted_brands[0][0] if sorted_brands else "Arcor"
        print(f"  ✅ Marca líder identificada: {marca_lider} (con {brand_counts.get(marca_lider, 0)} productos).")
        
        # Retornar datos para que el script actualice el manifest o los guarde
        return len(enriched_products), marca_lider
        
    except Exception as e:
        print(f"[FAIL] Error durante la carga a base de datos: {e}")
        sys.exit(1)
    finally:
        await conn.close()

if __name__ == "__main__":
    count, brand = asyncio.run(main())
    
    # Escribir resumen en un archivo temporal para consumirlo en el manifest
    resumen_path = r"c:\Users\marti\suplai-platform\implementacion\demo_jorge\outputs\resumen_fase_1.json"
    with open(resumen_path, 'w', encoding='utf-8') as f:
        json.dump({"cantidad_productos": count, "marca_lider": brand}, f, indent=2)
    print(f"Resumen guardado en {resumen_path}")
