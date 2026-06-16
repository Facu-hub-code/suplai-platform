import os
import sys
import csv
import yaml
import json
import argparse
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env local
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def generar_textos_comerciales_ia(productos_promo) -> list:
    """
    Llama a OpenAI para redactar títulos y descripciones promocionales atractivos y realistas en español neutro/argentino.
    """
    if not OPENAI_API_KEY:
        print("[WARN] OpenAI API Key no configurada. Usando descripciones por defecto.")
        return []

    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    # Estructura de entrada para el prompt
    input_data = []
    for p in productos_promo:
        input_data.append({
            "promo_id": p["promo_id"],
            "nombre": p["nombre"],
            "precio": p["precio"],
            "tipo_descuento": p["discount_kind"],
            "valor_descuento": p["discount_value"],
            "min_qty": p["min_qty_umv"]
        })

    prompt_sistema = (
        "Sos un redactor publicitario B2B experto en consumo masivo y retail en Argentina.\n"
        "Tu objetivo es escribir títulos y descripciones promocionales atractivos para WhatsApp y e-commerce.\n"
        "Evitá palabras exageradas como 'el mejor del mundo', pero usá ganchos comerciales válidos (ej. '¡Oferta Semanal!', 'Imperdible', 'Stock Limitado').\n"
        "Usa español rioplatense natural. Mantén los textos breves y al grano.\n\n"
        "Deberás devolver estrictamente una lista JSON que contenga objetos con las llaves:\n"
        "- 'promo_id': (entero) que corresponda a la promo dada.\n"
        "- 'titulo': (string) Título corto con gancho comercial y nombre del producto.\n"
        "- 'descripcion': (string) Breve descripción comercial detallando el beneficio (máximo 15-20 palabras)."
    )

    prompt_usuario = (
        f"Generá los textos comerciales para las siguientes 4 promociones de productos:\n"
        f"{json.dumps(input_data, indent=2)}\n\n"
        "Devolvé la lista JSON estructurada."
    )

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            # Puede venir envuelto en una llave "promociones" o ser la lista directa
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list) and len(v) == 4:
                        return v
            if isinstance(data, list) and len(data) == 4:
                return data
        else:
            print(f"[WARN] Error en OpenAI (HTTP {resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"[WARN] Error llamando a OpenAI: {e}")

    return []

def main():
    parser = argparse.ArgumentParser(description="Genera la matriz de 4 promociones mock basadas en el top de rotación y marca líder.")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant (ej: al_fuego)")
    args = parser.parse_args()

    esquema = args.esquema

    # 1. Leer manifest
    manifest_path = f"implementacion/{esquema}/manifest.yaml"
    if not os.path.exists(manifest_path):
        print(f"[FAIL] No se encontró el manifest en: {manifest_path}")
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as mf:
        manifest = yaml.safe_load(mf)

    marca_lider = manifest.get("marca_lider", "")
    if not marca_lider:
        print("[WARN] No se especificó 'marca_lider' en el manifest. Se usará el top puro de rotación.")

    # 2. Leer productos del catálogo
    productos_csv = f"implementacion/{esquema}/outputs/phase-01-productos.csv"
    if not os.path.exists(productos_csv):
        print(f"[FAIL] No se encontró el archivo de productos en: {productos_csv}")
        sys.exit(1)

    productos = []
    with open(productos_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row['rotacion_index'] = float(row['rotacion_index']) if row.get('rotacion_index') else 0.0
            row['precio_lista_1'] = float(row['precio_lista_1']) if row.get('precio_lista_1') else 0.0
            productos.append(row)

    if not productos:
        print("[FAIL] El archivo de productos está vacío.")
        sys.exit(1)

    # Ordenar por rotacion_index DESC
    productos.sort(key=lambda x: x['rotacion_index'], reverse=True)

    # 3. Selección de productos según el diseño (Efecto Cruzado con Marca Líder)
    top_1 = None
    if marca_lider:
        # Buscar el producto de mayor rotación de la marca líder
        for p in productos:
            if marca_lider.lower() in p['nombre'].lower():
                top_1 = p
                break

    if not top_1:
        print(f"[WARN] No se encontró ningún producto de la marca líder '{marca_lider}'. Usando el primero de rotación.")
        top_1 = productos[0]

    # Seleccionar top 2, 3, 4 asegurando no repetir el top 1
    otros_productos = [p for p in productos if p['product_code'] != top_1['product_code']]
    top_2 = otros_productos[0]
    top_3 = otros_productos[1]
    top_4 = otros_productos[2]

    print("\n--- PRODUCTOS SELECCIONADOS ---")
    print(f"Top 1 (Marca Líder: {marca_lider}): {top_1['product_code']} - {top_1['nombre']} (Rotación: {top_1['rotacion_index']})")
    print(f"Top 2: {top_2['product_code']} - {top_2['nombre']} (Rotación: {top_2['rotacion_index']})")
    print(f"Top 3: {top_3['product_code']} - {top_3['nombre']} (Rotación: {top_3['rotacion_index']})")
    print(f"Top 4: {top_4['product_code']} - {top_4['nombre']} (Rotación: {top_4['rotacion_index']})")

    # 4. Construir la estructura de promociones
    hoy = datetime.now()
    fecha_inicio = (hoy - timedelta(days=7)).strftime("%Y-%m-%d")
    fecha_fin = (hoy + timedelta(days=30)).strftime("%Y-%m-%d")

    promo_templates = [
        {
            "promo_id": 1,
            "product_code": top_1['product_code'],
            "nombre": top_1['nombre'],
            "precio": top_1['precio_lista_1'],
            "discount_kind": "percent_off",
            "discount_value": 15,
            "lista_precios_id": 1,
            "min_qty_umv": 1
        },
        {
            "promo_id": 2,
            "product_code": top_2['product_code'],
            "nombre": top_2['nombre'],
            "precio": top_2['precio_lista_1'],
            "discount_kind": "total_off",
            "discount_value": 1000,
            "lista_precios_id": 2,
            "min_qty_umv": 1
        },
        {
            "promo_id": 3,
            "product_code": top_3['product_code'],
            "nombre": top_3['nombre'],
            "precio": top_3['precio_lista_1'],
            "discount_kind": "fixed_price",
            "discount_value": round(top_3['precio_lista_1'] * 0.88, 2),
            "lista_precios_id": 1,
            "min_qty_umv": 3
        },
        {
            "promo_id": 4,
            "product_code": top_4['product_code'],
            "nombre": top_4['nombre'],
            "precio": top_4['precio_lista_1'],
            "discount_kind": "percent_off",
            "discount_value": 20,
            "lista_precios_id": 3,
            "min_qty_umv": 1
        }
    ]

    # Redactar textos de marketing
    print("\n[*] Generando textos publicitarios vía OpenAI...")
    textos_ia = generar_textos_comerciales_ia(promo_templates)
    
    textos_dict = {t["promo_id"]: t for t in textos_ia if "promo_id" in t}

    # Completar títulos y descripciones
    filas_csv = []
    for pt in promo_templates:
        pid = pt["promo_id"]
        
        # Valores por defecto por si falla OpenAI
        titulo_def = f"Super Promo {pt['nombre']}"
        if pt["discount_kind"] == "percent_off":
            desc_def = f"{pt['discount_value']}% de descuento en tu compra."
        elif pt["discount_kind"] == "total_off":
            desc_def = f"${pt['discount_value']} de descuento directo en este producto."
        else:
            desc_def = f"Llevando {pt['min_qty_umv']} o más, pagás un precio promocional de ${pt['discount_value']} c/u."

        titulo = textos_dict.get(pid, {}).get("titulo", titulo_def)
        descripcion = textos_dict.get(pid, {}).get("descripcion", desc_def)

        filas_csv.append({
            "promo_id": pid,
            "product_code": pt["product_code"],
            "titulo": titulo,
            "descripcion": descripcion,
            "discount_kind": pt["discount_kind"],
            "discount_value": pt["discount_value"],
            "lista_precios_id": pt["lista_precios_id"],
            "min_qty_umv": pt["min_qty_umv"],
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "activa": "true",
            "is_mock": "true"
        })

    # 5. Escribir archivo CSV
    output_dir = f"implementacion/{esquema}/outputs"
    os.makedirs(output_dir, exist_ok=True)
    output_csv = os.path.join(output_dir, "phase-02-promociones.csv")

    headers = [
        "promo_id", "product_code", "titulo", "descripcion", 
        "discount_kind", "discount_value", "lista_precios_id", 
        "min_qty_umv", "fecha_inicio", "fecha_fin", "activa", "is_mock"
    ]

    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(filas_csv)

    print(f"\n✅ Archivo de promociones escrito exitosamente en: {output_csv}")
    print("\n--- PROPUESTA DE PROMOCIONES ---")
    for r in filas_csv:
        print(f"Promo {r['promo_id']} | Código: {r['product_code']} | Tipo: {r['discount_kind']} ({r['discount_value']})")
        print(f"  Título: {r['titulo']}")
        print(f"  Descripción: {r['descripcion']}")
    print("--------------------------------")

if __name__ == "__main__":
    main()
