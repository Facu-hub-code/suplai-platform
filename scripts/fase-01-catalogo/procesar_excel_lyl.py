import os
import re
import csv
import json
import asyncio
import requests
import pandas as pd
from dotenv import load_dotenv

# Load env
dotenv_path = r"c:\Users\marti\suplai-platform\.env"
load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

excel_path = r"c:\Users\marti\suplai-platform\implementacion\distribuidora_lyl\inputs\lista-productos.xlsx"
output_dir = r"c:\Users\marti\suplai-platform\implementacion\distribuidora_lyl\outputs"

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)

def parse_excel():
    xl = pd.ExcelFile(excel_path)
    df = xl.parse(xl.sheet_names[0])
    
    products = []
    current_category = "General"
    
    sku_counter = 1
    
    for idx, row in df.iterrows():
        # Clean col 2 string
        val_col2 = str(row.iloc[2]).strip()
        
        # Check if it is a category header
        if ">>>" in val_col2:
            current_category = val_col2.replace(">>>", "").replace("<<<", "").strip()
            continue
            
        # Skip header rows
        if val_col2 == "nan" or val_col2 == "" or val_col2 == "Producto" or "BEBIDAS" in val_col2 and "ALCOHOL" in val_col2:
            continue
            
        # Parse price
        try:
            price_unit = float(row.iloc[4])
        except (ValueError, TypeError):
            continue
            
        if price_unit <= 0 or pd.isna(row.iloc[4]):
            continue
            
        # Parse pack size (units per bulto)
        try:
            pack_size = int(float(row.iloc[0]))
            if pack_size <= 0:
                pack_size = 1
        except (ValueError, TypeError):
            pack_size = 1
            
        product_code = f"LYL-{sku_counter:04d}"
        sku_counter += 1
        
        products.append({
            "product_code": product_code,
            "nombre": val_col2,
            "precio_lista_1": price_unit,
            "unidades_por_bulto": pack_size,
            "categoria_1": current_category,
        })
        
    print(f"Extracted {len(products)} products from Excel.")
    return products

async def enrich_batch(batch):
    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    batch_data = [{"id": p["product_code"], "nombre": p["nombre"], "categoria_1": p["categoria_1"]} for p in batch]
    
    prompt_sistema = (
        "Sos un sistema experto en auditoría de catálogos e indexación RAG para e-commerce en Argentina.\n"
        "Se te proporcionará una lista de productos en formato JSON.\n"
        "Para cada producto, debes inferir y generar un objeto con:\n"
        "- 'categoria_2': Categoría de nivel 2 (ej: Bebidas con Gas, Chocolates, Golosinas, Jugos, Aguas, Jabón, etc.)\n"
        "- 'categoria_3': Categoría de nivel 3 (ej: Gaseosas, Alfajores, Caramelos, Aguas Minerales, etc.)\n"
        "- 'categoria_4': Categoría de nivel 4 (ej: Cola, Naranja, Frutilla, o vacío si no aplica)\n"
        "- 'aliases': Sinónimos comerciales coloquiales de Argentina separados por '|' en minúsculas (ej: 'gaseosa de pomelo | secco pomelo | secco de pomelo')\n"
        "- 'descripcion': Descripción comercial de máximo 15 palabras, limpia de fluff/marketing, directa, que empiece con el sustantivo de la categoría (ej: 'Gaseosa sabor pomelo de la marca Secco, formato familiar.')\n"
        "- 'rotacion_index': Un float entre 0.05 y 0.95. Si la marca es conocida/líder (ej. Secco, Winner's, Mr. Choco, Sporting, Sporting Isotónica, Speed, Tutti, Bio Balance, Bio Sports), asignar entre 0.75 y 0.95. Si es genérica o poco conocida, menor a 0.2.\n\n"
        "Responde estrictamente con un objeto JSON que contenga la llave 'productos' con la lista de respuestas correspondientes a cada 'id'."
    )
    
    prompt_usuario = json.dumps(batch_data, ensure_ascii=False)
    
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0
    }
    
    for attempt in range(3):
        try:
            # We run this in an executor thread since requests is synchronous
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, json=payload, timeout=40)
            )
            if res.status_code == 200:
                res_data = json.loads(res.json()["choices"][0]["message"]["content"])
                return res_data.get("productos", [])
            else:
                print(f"OpenAI error (HTTP {res.status_code}): {res.text}")
        except Exception as e:
            print(f"Attempt {attempt+1} failed for batch: {e}")
            await asyncio.sleep(1)
            
    # Fallback if OpenAI fails completely
    print("OpenAI failed. Returning fallbacks.")
    return []

async def enrich_all(products):
    batch_size = 20
    batches = [products[i:i + batch_size] for i in range(0, len(products), batch_size)]
    
    tasks = [enrich_batch(b) for b in batches]
    results = await asyncio.gather(*tasks)
    
    # Flatten and build a lookup dict
    enrich_lookup = {}
    for r_list in results:
        for item in r_list:
            if "id" in item:
                enrich_lookup[item["id"]] = item
                
    # Merge back to products
    for p in products:
        code = p["product_code"]
        enrich = enrich_lookup.get(code, {})
        p["categoria_2"] = enrich.get("categoria_2", "")
        p["categoria_3"] = enrich.get("categoria_3", "")
        p["categoria_4"] = enrich.get("categoria_4", "")
        p["aliases"] = enrich.get("aliases", "")
        p["descripcion"] = enrich.get("descripcion", f"Producto {p['nombre']} de la categoría {p['categoria_1']}.")
        p["rotacion_index"] = enrich.get("rotacion_index", 0.1)
        p["stock"] = int(100 + (p["rotacion_index"] * 400)) # Scale stock based on rotation index
        p["mental_priority"] = 0
        p["image_url"] = "https://via.placeholder.com/150"
        p["en_catalogo"] = "true"
        p["is_mock"] = "true"
        p["fuente_hoja"] = "Hoja1"
        
    return products

def determine_brand(nombre):
    # Detect common brands in the dataset
    n_lower = nombre.lower()
    if "secco" in n_lower:
        return "Secco"
    if "winner" in n_lower:
        return "Winner's"
    if "tutti" in n_lower:
        return "Tutti"
    if "choco" in n_lower:
        return "Mr. Choco"
    if "sporting" in n_lower:
        return "Sporting"
    if "bio balance" in n_lower:
        return "Bio Balance"
    if "bio sports" in n_lower or "bio sport" in n_lower:
        return "Bio Sports"
    if "speed" in n_lower:
        return "Speed"
    if "yap" in n_lower:
        return "Yap"
    
    # Try to grab the first word
    words = nombre.split()
    generic_words = {
        "gaseosa", "agua", "soda", "jugo", "chocolatada", "bidón", "bidon", "lata", "saborizada", 
        "vino", "yerba", "alfajor", "galletitas", "chupetín", "chupetin", "mate", "fernet", 
        "cerveza", "licor", "aperitivo", "chocolate", "caramelo", "caramelos", "chicle", 
        "chicles", "galleta", "oblea", "pan", "budin", "budín", "pan dulce", "panettone", 
        "sifón", "sifon", "bolsa", "paquete", "turrón", "turron", "pastilla", "pastillas", 
        "chizitos", "chizito", "papas", "maní", "mani", "semillas", "semilla", "palitos", 
        "palito", "goma", "gomas", "gominola", "gominolas", "dulce", "caja", "pack", "termo"
    }
    
    for word in words:
        w_clean = word.lower().strip(",.-()\"'/+* \t")
        if w_clean not in generic_words and len(w_clean) > 2:
            return word.strip(",.-()\"'/+* \t")
            
    return "L&L"

def main():
    products = parse_excel()
    if not products:
        print("No products found to process.")
        return
        
    print("Running AI enrichment via OpenAI...")
    asyncio.run(enrich_all(products))
    
    # Write phase-01-productos.csv
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
        for p in products:
            writer.writerow([
                p["product_code"],
                p["nombre"],
                p["precio_lista_1"],
                p["stock"],
                p["unidades_por_bulto"],
                "1", # unidad_minima_de_venta
                "unidad", # umv_tipo
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
            
    print(f"Saved {len(products)} products to {products_csv_path}")
    
    # Write 4 price lists:
    # 1: Base (1.00)
    # 2: Minorista Sugerido (1.15)
    # 3: Mayorista Especial (0.90)
    # 4: Gran Distribuidor (0.85)
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
            for p in products:
                price = round(p["precio_lista_1"] * multiplier, 2)
                writer.writerow([p["product_code"], price, "true"])
        print(f"Saved price list {list_id} to {price_csv_path}")
        
    # Analyze leading brand
    brand_counts = {}
    for p in products:
        brand = determine_brand(p["nombre"])
        brand_counts[brand] = brand_counts.get(brand, 0) + 1
        
    sorted_brands = sorted(brand_counts.items(), key=lambda x: x[1], reverse=True)
    print("\nBrand Distribution:")
    for b, c in sorted_brands[:10]:
        print(f"  {b}: {c}")
        
    leading_brand = sorted_brands[0][0] if sorted_brands else "Secco"
    print(f"\nLeading Brand (marca_lider): {leading_brand}")
    
    # Save leading brand to manifest.yaml later
    
if __name__ == '__main__':
    main()
