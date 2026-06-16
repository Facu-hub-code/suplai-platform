import os
import sys
import csv
import yaml
import json
import argparse
import requests
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env local
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def generar_mapeos_con_ia(productos) -> dict:
    """
    Llama a OpenAI para realizar un emparejamiento semántico inteligente y realista de cross-sell y up-sell.
    """
    if not OPENAI_API_KEY:
        print("[WARN] OpenAI API Key no configurada. Se usará el emparejamiento heurístico por defecto.")
        return {}

    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    # Simplificar el catálogo para enviar al modelo y no exceder límites
    catalogo_simplificado = []
    for p in productos:
        catalogo_simplificado.append({
            "product_code": p["product_code"],
            "nombre": p["nombre"],
            "descripcion": p.get("descripcion", "")[:100],
            "categoria": p.get("categoria_1", "")
        })

    prompt_sistema = (
        "Sos un consultor de marketing digital y RAG e-commerce para distribuidoras en Argentina.\n"
        "Tu objetivo es proponer asociaciones lógicas de venta cruzada (cross-sell) y venta incremental (up-sell) para el catálogo de productos brindado.\n\n"
        "REGLA DE CÓDIGOS DE PRODUCTO ABSOLUTA (MANDATORIA):\n"
        "- Está TERMINANTEMENTE PROHIBIDO inventar, alucinar, truncar, modificar o alterar cualquier código de producto (`product_code`).\n"
        "- Debes usar ÚNICAMENTE y de forma exacta los códigos presentes en la lista de entrada.\n"
        "- Cada par base_product_code y related_product_code debe corresponder a un producto real de la lista.\n"
        "- Si el producto B no está en la lista de entrada con su código exacto, no lo asocies.\n\n"
        "Definiciones:\n"
        "- Cross-sell (Venta Cruzada): Productos de categorías complementarias que suelen consumirse juntos (ej: carne con carbón/leña, pizza con cerveza, carnes con vino tinto, mariscos con vino blanco, provoleta con chimichurri, etc.). Generar exactamente entre 10 y 14 pares únicos.\n"
        "- Up-sell (Venta Incremental): Reemplazo de un producto por una alternativa superior, de mayor volumen/tamaño o línea premium del mismo tipo (ej: aceite de oliva 250ml a 500ml, vino de mesa a reserva/blend premium, corte de carne común a corte Angus premium, gaseosa chica a gaseosa de 1.5L). Generar exactamente entre 6 y 10 pares únicos.\n\n"
        "Requisitos:\n"
        "1. Asegúrate de incluir al menos una relación de cross-sell que involucre un queso de la marca líder 'Formagge'.\n"
        "2. Evita emparejar productos idénticos entre sí.\n"
        "3. La justificación (reason) debe ser corta, persuasiva y en español.\n\n"
        "Deberás responder con un objeto JSON que contenga las llaves:\n"
        "- 'cross_sell': Lista de objetos con 'base_product_code', 'related_product_code', 'reason'.\n"
        "- 'up_sell': Lista de objetos con 'base_product_code', 'related_product_code', 'reason'."
    )

    prompt_usuario = (
        f"Catálogo de productos:\n{json.dumps(catalogo_simplificado, indent=2)}\n\n"
        "Generá los mapeos de venta cruzada (cross_sell) e incremental (up_sell) basándote en este catálogo."
    )

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=40)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        else:
            print(f"[WARN] Error en OpenAI (HTTP {resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"[WARN] Error llamando a OpenAI: {e}")

    return {}

def generar_mapeos_heuristicos(productos, marca_lider: str) -> dict:
    """
    Emparejamiento heurístico fallback si OpenAI no está configurado.
    """
    print("[*] Ejecutando emparejamiento heurístico...")
    cross_sell = []
    up_sell = []

    # Buscar códigos clave si existen
    carbon_code = next((p["product_code"] for p in productos if "carbon" in p["nombre"].lower()), None)
    chimichurri_code = next((p["product_code"] for p in productos if "chimichurri" in p["nombre"].lower()), None)
    
    # 1. Cross-sell heurístico
    for p in productos:
        nombre = p["nombre"].lower()
        code = p["product_code"]
        
        # Cortes de carne -> Carbón / Chimichurri
        if ("vacuno" in p.get("categoria_1", "").lower() or "cerdo" in p.get("categoria_1", "").lower()) and code not in [carbon_code, chimichurri_code]:
            if carbon_code:
                cross_sell.append({
                    "base_product_code": code,
                    "related_product_code": carbon_code,
                    "reason": "Carbón vegetal de alta calidad ideal para encender la parrilla y asar este corte."
                })
            if chimichurri_code:
                cross_sell.append({
                    "base_product_code": code,
                    "related_product_code": chimichurri_code,
                    "reason": "El chimichurri artesanal es el aderezo tradicional perfecto para este corte."
                })

    # 2. Up-sell heurístico (Buscar aceites de oliva de distinto tamaño)
    aceite_250 = next((p["product_code"] for p in productos if "aceite" in p["nombre"].lower() and "250" in p["nombre"]), None)
    aceite_500 = next((p["product_code"] for p in productos if "aceite" in p["nombre"].lower() and "500" in p["nombre"]), None)
    if aceite_250 and aceite_500:
        up_sell.append({
            "base_product_code": aceite_250,
            "related_product_code": aceite_500,
            "reason": "Llevá el formato de 500ml con mejor precio por litro para mayor rendimiento."
        })

    # Coca Cola vidrio a 1.5L
    coca_chica = next((p["product_code"] for p in productos if "coca" in p["nombre"].lower() and "237" in p["nombre"]), None)
    coca_grande = next((p["product_code"] for p in productos if "coca" in p["nombre"].lower() and "1.5" in p["nombre"]), None)
    if coca_chica and coca_grande:
        up_sell.append({
            "base_product_code": coca_chica,
            "related_product_code": coca_grande,
            "reason": "Elegí el formato familiar de 1.5 litros ideal para compartir."
        })

    return {
        "cross_sell": cross_sell[:12],
        "up_sell": up_sell[:8]
    }

def main():
    parser = argparse.ArgumentParser(description="Genera propuestas inteligentes de Cross-sell y Up-sell para el catálogo.")
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
    tenant_id = manifest.get("tenant_id", "")
    if not tenant_id:
        print("[FAIL] tenant_id no configurado en manifest.yaml.")
        sys.exit(1)

    # 2. Leer catálogo
    productos_csv = f"implementacion/{esquema}/outputs/phase-01-productos.csv"
    if not os.path.exists(productos_csv):
        print(f"[FAIL] No se encontró el catálogo en: {productos_csv}")
        sys.exit(1)

    productos = []
    with open(productos_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            productos.append(row)

    if not productos:
        print("[FAIL] Catálogo vacío.")
        sys.exit(1)

    # 3. Generar mapeos
    mapeos = generar_mapeos_con_ia(productos)
    if not mapeos or "cross_sell" not in mapeos or "up_sell" not in mapeos:
        mapeos = generar_mapeos_heuristicos(productos, marca_lider)
            
    # Validar y filtrar que los códigos existan en el catálogo cargado para evitar alucinaciones
    codigos_validos = {p["product_code"] for p in productos}
    mapeos["cross_sell"] = [item for item in mapeos.get("cross_sell", []) if item["base_product_code"] in codigos_validos and item["related_product_code"] in codigos_validos]
    mapeos["up_sell"] = [item for item in mapeos.get("up_sell", []) if item["base_product_code"] in codigos_validos and item["related_product_code"] in codigos_validos]

    # 4. Escribir CSVs
    output_dir = f"implementacion/{esquema}/outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    # Escribir Cross-sell
    cross_csv = os.path.join(output_dir, "phase-03-cross-sell.csv")
    with open(cross_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["base_product_code", "related_product_code", "reason", "is_mock"])
        for item in mapeos.get("cross_sell", []):
            writer.writerow([item["base_product_code"], item["related_product_code"], item["reason"], "true"])

    # Escribir Up-sell
    up_csv = os.path.join(output_dir, "phase-03-up-sell.csv")
    with open(up_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["base_product_code", "related_product_code", "reason", "is_mock"])
        for item in mapeos.get("up_sell", []):
            writer.writerow([item["base_product_code"], item["related_product_code"], item["reason"], "true"])

    print(f"\n✅ Propuesta de Cross-sell guardada en: {cross_csv}")
    print(f"✅ Propuesta de Up-sell guardada en: {up_csv}")
    print(f"Total Cross-sell sugeridos: {len(mapeos.get('cross_sell', []))}")
    print(f"Total Up-sell sugeridos: {len(mapeos.get('up_sell', []))}")

    # Mostrar preview
    print("\n--- PREVIEW CROSS-SELL ---")
    for item in mapeos.get("cross_sell", [])[:5]:
        print(f"  {item['base_product_code']} -> {item['related_product_code']} | Razón: {item['reason']}")
    print("\n--- PREVIEW UP-SELL ---")
    for item in mapeos.get("up_sell", [])[:5]:
        print(f"  {item['base_product_code']} -> {item['related_product_code']} | Razón: {item['reason']}")

if __name__ == "__main__":
    main()
