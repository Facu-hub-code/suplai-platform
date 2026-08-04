import os
import sys
import json
import csv
import asyncio
import asyncpg
import requests
from dotenv import load_dotenv

# Load workspace env
dotenv_path = r"c:\Users\marti\suplai-platform\.env"
load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Reconfigure stdout to use UTF-8 on Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Fallback helper to assign categories if OpenAI fails or for missing fields
def get_fallback_categories(nombre: str) -> tuple[str, str, str, str]:
    n_lower = nombre.lower()
    cat1 = "Almacén"
    cat2, cat3, cat4 = "", "", ""
    
    if "bon o bon" in n_lower or "bonobon" in n_lower:
        cat2 = "Golosinas"
        cat3 = "Bombones"
        cat4 = "Bon o Bon"
    elif "mogul" in n_lower:
        cat2 = "Golosinas"
        cat3 = "Gomitas"
    elif "rocklets" in n_lower:
        cat2 = "Chocolates"
        cat3 = "Confites"
    elif "pops" in n_lower or "chupetin" in n_lower or "chupetín" in n_lower:
        cat2 = "Golosinas"
        cat3 = "Chupetines"
    elif "topline" in n_lower or "chicle" in n_lower or "belident" in n_lower:
        cat2 = "Golosinas"
        cat3 = "Chicles"
    elif "oblea" in n_lower:
        cat2 = "Galletas"
        cat3 = "Obleas"
    elif "alfajor" in n_lower:
        cat2 = "Golosinas"
        cat3 = "Alfajores"
    elif "tableta" in n_lower or "block" in n_lower or "cofler" in n_lower or "chocolate" in n_lower or "aguila" in n_lower or "águila" in n_lower:
        cat2 = "Chocolates"
        cat3 = "Chocolates en Barra"
    else:
        cat2 = "Golosinas"
        cat3 = "Varios"
        
    if "helado" in n_lower:
        cat2 = "Helados"
        cat3 = "Helados de Crema" if "crema" in n_lower or "cono" in n_lower else "Helados de Palito"
        
    return cat1, cat2, cat3, cat4

# Process batch with OpenAI
async def enrich_batch_openai(batch):
    if not OPENAI_API_KEY:
        print("[WARN] OPENAI_API_KEY no encontrada. Usando fallbacks.")
        return []

    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    batch_data = [{"product_code": p["product_code"], "nombre": p["nombre"]} for p in batch]
    
    prompt_sistema = (
        "Sos un sistema experto en categorización e indexación de catálogos RAG para e-commerce de golosinas y alimentos en Argentina.\n"
        "Se te proporcionará una lista de productos en formato JSON con su código y nombre.\n"
        "Para cada producto, debes proponer una taxonomía de categorías jerárquicas de 4 niveles en un objeto JSON que contenga:\n"
        "- 'product_code': El código de producto exacto provisto en la entrada. Debe coincidir exactamente.\n"
        "- 'categoria_1': Siempre usar 'Almacén'.\n"
        "- 'categoria_2': Categoría de nivel 2 (ej: Golosinas, Chocolates, Galletas, Bebidas, Helados, Almacén, etc.)\n"
        "- 'categoria_3': Categoría de nivel 3 (ej: Caramelos, Gaseosas, Chicles, Bombones, Alfajores, Gomitas, Chupetines, Obleas, Chocolates en Barra, Helados de Crema, Helados de Palito, etc.)\n"
        "- 'categoria_4': Categoría de nivel 4 (ej: Cola, Naranja, Frutilla, con Maní, Blanco, Relleno, o vacío/omitido si no aplica)\n"
        "Responde estrictamente con un objeto JSON que contenga la llave 'productos' con la lista de respuestas correspondientes a cada 'product_code'."
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
    
    print(f"[*] Iniciando re-clasificación y carga de categorías en el esquema: {schema}")
    
    conn = await asyncpg.connect(db_url)
    try:
        # 1. Obtener todos los productos de demo_jorge
        print("[*] Leyendo productos del esquema...")
        products = await conn.fetch(f"SELECT product_code, nombre FROM {schema}.productos")
        print(f"    Leídos {len(products)} productos.")
        
        if not products:
            print("[FAIL] No hay productos en la base de datos.")
            return
            
        # 2. Llamar a OpenAI en paralelo para clasificar
        print("[*] Clasificando productos con OpenAI...")
        batch_size = 45
        batches = [products[i:i + batch_size] for i in range(0, len(products), batch_size)]
        
        tasks = [enrich_batch_openai(b) for b in batches]
        results = await asyncio.gather(*tasks)
        
        # Aplanar resultados de OpenAI
        enrich_lookup = {}
        for r_list in results:
            for item in r_list:
                if "product_code" in item:
                    enrich_lookup[item["product_code"]] = item
                    
        print(f"    Recibidas clasificaciones de OpenAI para {len(enrich_lookup)} productos.")
        
        # 3. Preparar lista completa de clasificaciones
        final_products = []
        for p in products:
            code = p["product_code"]
            nombre = p["nombre"]
            
            enrich = enrich_lookup.get(code, {})
            cat1 = enrich.get("categoria_1") or "Almacén"
            cat2 = enrich.get("categoria_2") or ""
            cat3 = enrich.get("categoria_3") or ""
            cat4 = enrich.get("categoria_4") or ""
            
            # Si faltan categorías intermedias, usar fallback inteligente
            if not cat2 or not cat3:
                f_cat1, f_cat2, f_cat3, f_cat4 = get_fallback_categories(nombre)
                cat1 = cat1 or f_cat1
                cat2 = cat2 or f_cat2
                cat3 = cat3 or f_cat3
                cat4 = cat4 or f_cat4
                
            # Limpiar acentos o espacios extras
            cat1 = cat1.strip()
            cat2 = cat2.strip()
            cat3 = cat3.strip()
            cat4 = cat4.strip() if cat4 else ""
            
            final_products.append({
                "product_code": code,
                "nombre": nombre,
                "categoria_1": cat1,
                "categoria_2": cat2,
                "categoria_3": cat3,
                "categoria_4": cat4
            })
            
        print("[*] Limpiando tablas de taxonomía previas...")
        await conn.execute(f"DELETE FROM {schema}.product_categories;")
        await conn.execute(f"DELETE FROM {schema}.product_tags;")
        await conn.execute(f"DELETE FROM {schema}.categorias;")
        await conn.execute(f"DELETE FROM {schema}.tags;")
        print("    Tablas vaciadas.")
        
        # 4. Crear jerarquías de categorías/tags
        print("[*] Insertando jerarquías y asociaciones...")
        
        # Cache en memoria: name_lower -> id
        tag_cache = {}
        
        async def get_or_create_tag_and_category(name, parent_id):
            name_clean = name.strip()
            name_lower = name_clean.lower()
            
            # Ignorar placeholders o valores vacíos/sin categoría
            if not name_clean or name_lower in ('omitido', 'omitida', 'vacio', 'vacío', 'no aplica', 'ninguno', 'ninguna', 'sin categoría', 'sin categoria', 'omitir'):
                return None
                
            if name_lower in tag_cache:
                return tag_cache[name_lower]
                
            # Insertar en tags
            tag_row = await conn.fetchrow(
                f"INSERT INTO {schema}.tags (name, parent_id, created_at, updated_at) VALUES ($1, $2, now(), now()) RETURNING id",
                name_clean, parent_id
            )
            tag_id = tag_row["id"]
            
            # Insertar en categorias con el MISMO ID
            await conn.execute(
                f"INSERT INTO {schema}.categorias (id, name, parent_id, sort_order, created_at, updated_at) VALUES ($1, $2, $3, 0, now(), now())",
                tag_id, name_clean, parent_id
            )
            
            tag_cache[name_lower] = tag_id
            return tag_id
            
        product_tag_mappings = []
        product_cat_mappings = []
        
        for p in final_products:
            code = p["product_code"]
            
            # Niveles definidos
            levels = [p["categoria_1"], p["categoria_2"], p["categoria_3"], p["categoria_4"]]
            
            parent_id = None
            for lvl_name in levels:
                if not lvl_name:
                    continue
                tag_id = await get_or_create_tag_and_category(lvl_name, parent_id)
                if tag_id is not None:
                    product_tag_mappings.append((code, tag_id))
                    product_cat_mappings.append((code, tag_id))
                    parent_id = tag_id
                
        # 5. Inserciones masivas (executemany) de mappings
        # Deduplicar mappings
        unique_tag_mappings = list(set(product_tag_mappings))
        unique_cat_mappings = list(set(product_cat_mappings))
        
        print(f"    Insertando {len(unique_tag_mappings)} mapeos de product_tags...")
        await conn.executemany(
            f"INSERT INTO {schema}.product_tags (product_code, tag_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            unique_tag_mappings
        )
        
        print(f"    Insertando {len(unique_cat_mappings)} mapeos de product_categories...")
        await conn.executemany(
            f"INSERT INTO {schema}.product_categories (product_code, categoria_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            unique_cat_mappings
        )
        
        print(f"✅ Proceso de base de datos finalizado. Creados {len(tag_cache)} categorías/tags.")
        
        # 6. Re-vectorizar catálogo y categorías/tags (CRÍTICO)
        print("[*] Iniciando re-vectorización en el backend...")
        backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
        
        # Vectorizar productos
        vec_prod_url = f"{backend_url}/{schema}/productos/vectorize"
        product_codes = [p["product_code"] for p in final_products]
        try:
            resp = requests.post(vec_prod_url, json=product_codes, timeout=60)
            if resp.status_code == 200:
                print("  ✅ Re-vectorización de catálogo encolada (HTTP 200).")
            else:
                print(f"  [WARN] Falló vectorización de catálogo: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"  [WARN] Error de red al vectorizar catálogo: {e}")
            
        # Vectorizar categorías/tags
        vec_tag_url = f"{backend_url}/{schema}/tags/vectorize"
        try:
            resp = requests.post(vec_tag_url, json={"tag_ids": []}, timeout=60)
            if resp.status_code == 200:
                print("  ✅ Re-vectorización de categorías encolada (HTTP 200).")
            else:
                print(f"  [WARN] Falló vectorización de categorías: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"  [WARN] Error de red al vectorizar categorías: {e}")
            
    except Exception as e:
        print(f"[FAIL] Error durante la ejecución del script: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
