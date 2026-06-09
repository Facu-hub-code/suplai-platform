import os
import re
import csv
import json
import asyncio
import requests
import argparse
import unicodedata
import asyncpg
from typing import List, Optional
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env local
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

# ==========================================
# LÓGICA DE NORMALIZACIÓN Y LIMPIEZA
# ==========================================
def limpiar_nombre_producto(nombre: str) -> str:
    """
    Elimina ruidos técnicos de empaques masivos como 12X30X15G, 24X48G, 6X60UN, etc.
    """
    patron_pack = r'\b\d+[xX]\d+([xX]\d+)?\s*[gGuUnN]*\b'
    nombre_limpio = re.sub(patron_pack, '', nombre)
    return " ".join(nombre_limpio.split())

def normalizar_alias(alias_raw: str) -> str:
    """
    Normaliza el alias pasando a minúsculas, quitando acentos y dejando caracteres alfanuméricos.
    """
    alias_lower = alias_raw.lower().strip()
    alias_flat = unicodedata.normalize('NFKD', alias_lower)
    return "".join([c for c in alias_flat if 'a' <= c <= 'z' or '0' <= c <= '9'])

def filtrar_alias_peligrosos(nombre_producto: str, alias_locales: List[str]) -> List[str]:
    """
    Remueve alucinaciones críticas basadas en colisiones lingüísticas comunes de Argentina
    (como confundir Chocolate/Choco con Choclo).
    """
    nombre_lower = nombre_producto.lower()
    alias_filtrados = []
    
    # Si el producto NO es de verdad maíz/choclo, eliminamos cualquier alias que contenga "choclo"
    es_choclo_real = "choclo" in nombre_lower or "maiz" in nombre_lower or "polenta" in nombre_lower
    
    for alias in alias_locales:
        alias_clean = alias.strip().lower()
        
        # Guardrail anti-choclo
        if "choclo" in alias_clean and not es_choclo_real:
            continue  # Lo ignoramos silenciosamente
            
        alias_filtrados.append(alias)
        
    return alias_filtrados

# ==========================================
# CONEXIÓN CON BÚSQUEDA WEB (SerpAPI)
# ==========================================
def buscar_contexto_serpapi(nombre_producto: str) -> str:
    """
    Realiza la búsqueda en Google Argentina filtrando por MercadoLibre y Carrefour.
    """
    if not SERPAPI_API_KEY:
        return "Sin contexto web (API Key no configurada)."

    nombre_busqueda = limpiar_nombre_producto(nombre_producto)
    
    # Buscar exclusivamente en e-commerce y retailers argentinos líderes
    query = f"site:mercadolibre.com.ar OR site:carrefour.com.ar {nombre_busqueda}"
    
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "gl": "ar",  # Ubicación: Argentina
        "hl": "es"   # Idioma: Español
    }
    
    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            results = data.get("organic_results", [])
            snippets = [r.get("snippet") for r in results if r.get("snippet")]
            if snippets:
                return "\n".join(f"- {s}" for s in snippets[:3])
    except Exception as e:
        print(f"Error consultando SerpAPI restringido para '{nombre_producto}': {e}")
        
    # Fallback abierto en caso de no obtener resultados
    print(f"Búsqueda restringida sin resultados para '{nombre_producto}'. Usando fallback abierto...")
    params["q"] = f"{nombre_busqueda} golosina alimento argentina"
    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            results = data.get("organic_results", [])
            snippets = [r.get("snippet") for r in results if r.get("snippet")]
            if snippets:
                return "\n".join(f"- {s}" for s in snippets[:3])
    except Exception as e:
        print(f"Error consultando SerpAPI fallback para '{nombre_producto}': {e}")

    return "No se encontraron snippets web relevantes."

# ==========================================
# LLAMADA AL LLM (OPENAI LLM ENDPOINT)
# ==========================================
def generar_enriquecimiento_ia(nombre: str, contexto_web: str) -> dict:
    """
    Llama de manera directa al endpoint de OpenAI utilizando JSON Mode para formatear la descripción.
    No pasamos la descripción anterior para evitar sesgos de marketing.
    """
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY no configurada.")
        return {"descripcion_mejorada": "", "alias_locales": []}

    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt_sistema = (
        "Sos un sistema experto en auditoría de catálogos e indexación RAG para e-commerce en Argentina.\n"
        "El catálogo pertenece a una distribuidora mayorista de consumo masivo (golosinas, alimentos, bebidas, artículos de limpieza y perfumería). Ten en cuenta este contexto al interpretar la verdadera naturaleza del producto (por ejemplo, evita confundir marcas de golosinas o alimentos con herramientas industriales, pinturas artísticas u otros rubros ajenos).\n"
        "Tu objetivo es generar una descripción técnica y ultra-concisa del producto y una lista de alias de alta calidad.\n\n"
        
        "REGLAS ESTRICTAS PARA LA DESCRIPCIÓN (CRUCIAL):\n"
        "1. LONGITUD MÁXIMA: La descripción mejorada debe tener un máximo de 10 a 15 palabras (una sola oración breve).\n"
        "2. CERO FLUFF/MARKETING: Queda terminantemente prohibido usar palabras como 'delicioso', 'irresistible', 'suave', "
        "'refrescante', 'ideal', 'perfecto', 'único', 'descubre', 'disfruta', o cualquier mención a kioscos, almacenes, "
        "ganancia, rotación o ventas.\n"
        "3. FORMATO DIRECTO: Empezá directamente con el sustantivo de la categoría del producto (ej: 'Chocolate con leche...', "
        "'Jugo en polvo...', 'Galletitas dulces...', 'Aceite de girasol...').\n"
        "4. DETALLE TÉCNICO: Nombrá la marca principal, el sabor y formato físico sin adornar.\n"
        "Ejemplo correcto: 'Chocolate con leche relleno con crema de yogurt sabor frutilla, marca Cofler.'\n"
        "Ejemplo incorrecto: 'Delicioso chocolate Cofler relleno de yogurt sabor frutilla, presentado en cajas ideal para kiosco.'\n\n"
        
        "REGLAS PARA LOS ALIAS:\n"
        "- Extraé sinónimos coloquiales válidos en Argentina en minúsculas (ej: 'galletitas', 'chicle', 'chupetin', 'pastillas').\n"
        "- No inventes abreviaturas peligrosas (nunca uses 'choclo' para chocolate).\n\n"
        
        "Deberás responder estrictamente con un objeto JSON que contenga las llaves:\n"
        "- 'descripcion_mejorada': (string) La descripción técnica ultra-concisa.\n"
        "- 'alias_locales': (array de strings) Los alias válidos en minúsculas."
    )
    
    prompt_usuario = (
        f"=== CONTEXTO DE BÚSQUEDA WEB (Google Argentina) ===\n"
        f"{contexto_web}\n\n"
        f"PRODUCTO TARGET: {nombre}\n\n"
        f"INSTRUCCIÓN: Basándote únicamente en el contexto web, identifica la verdadera naturaleza de {nombre}. "
        f"Escribí una descripción técnica ultra-concisa de una sola oración (máximo 15 palabras) que empiece con la categoría del producto. "
        f"Extraé sus alias locales."
    )
    
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": prompt_usuario}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0  # Temperatura 0.0 para ser determinista
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=40)
        if res.status_code == 200:
            return json.loads(res.json()["choices"][0]["message"]["content"])
        else:
            print(f"Error en OpenAI (HTTP {res.status_code}): {res.text}")
    except Exception as e:
        print(f"Error procesando IA para {nombre}: {e}")
        
    return {"descripcion_mejorada": "", "alias_locales": []}

# ==========================================
# PROCESAMIENTO MODO ENRIQUECIMIENTO (CSV)
# ==========================================
def ejecutar_enriquecimiento_csv(csv_entrada: str, csv_salida: str):
    print(f"\nIniciando enriquecimiento de catálogo desde: {csv_entrada}")
    if not os.path.exists(csv_entrada):
        print(f"Error: El archivo de entrada '{csv_entrada}' no existe.")
        return
 
    productos = []
    with open(csv_entrada, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Soportar nombres de columnas en inglés y español para mayor compatibilidad
            code = row.get("codigo_producto") or row.get("product_code")
            nombre = row.get("nombre") or row.get("name") or ""
            desc = row.get("descripcion") or row.get("description") or ""
            
            if not code:
                continue
            productos.append({
                "codigo_producto": code,
                "nombre": nombre,
                "descripcion": desc
            })

    if not productos:
        print("No se encontraron productos válidos para procesar en el CSV.")
        return

    print(f"Procesando {len(productos)} productos...")
    preview_filas = []

    for i, prod in enumerate(productos, start=1):
        code = prod["codigo_producto"]
        nombre = prod["nombre"]
        desc_actual = prod["descripcion"]
        
        nombre_clean = limpiar_nombre_producto(nombre)
        print(f"[{i}/{len(productos)}] Procesando: {code} | {nombre_clean}")
        
        # 1. SerpAPI
        contexto = buscar_contexto_serpapi(nombre)
        
        # 2. OpenAI
        data_ia = generar_enriquecimiento_ia(nombre, contexto)
        
        # 3. Guardrails
        alias_crudos = data_ia.get("alias_locales", [])
        alias_seguros = filtrar_alias_peligrosos(nombre, alias_crudos)
        alias_str = "|".join(alias_seguros)
        
        preview_filas.append({
            "codigo_producto": code,
            "nombre": nombre,
            "descripcion_original": desc_actual,
            "descripcion_mejorada": data_ia.get("descripcion_mejorada"),
            "alias_propuestos": alias_str,
            "accion": "ACTUALIZAR"
        })

    # Asegurar directorio de salida
    os.makedirs(os.path.dirname(os.path.abspath(csv_salida)), exist_ok=True)

    with open(csv_salida, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["codigo_producto", "nombre", "descripcion_original", "descripcion_mejorada", "alias_propuestos", "accion"])
        writer.writeheader()
        writer.writerows(preview_filas)

    print(f"\n¡Enriquecimiento completado exitosamente!")
    print(f"Verificá y editá el archivo de preview en: {csv_salida}")
    print("Para aplicar los cambios a la base de datos, ejecuta el comando con el flag --aplicar.")

# ==========================================
# PROCESAMIENTO MODO APLICACIÓN (DB)
# ==========================================
async def aplicar_actualizaciones_db(esquema: str, csv_entrada: str):
    print(f"\nAplicando actualizaciones en base de datos. Esquema: {esquema} | Entrada: {csv_entrada}")
    if not os.path.exists(csv_entrada):
        print(f"Error: El archivo de preview '{csv_entrada}' no existe.")
        return

    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("Error: SUPABASE_DB_URL no está configurada en el archivo .env.")
        return

    try:
        conn = await asyncpg.connect(db_url)
    except Exception as e:
        print(f"Error al conectar a Supabase: {e}")
        return

    actualizados = 0
    aliases_insertados = 0
    product_codes_modificados = []

    try:
        with open(csv_entrada, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                product_code = row.get("codigo_producto") or row.get("product_code")
                accion = row.get("accion") or row.get("action") or "ACTUALIZAR"
                accion = accion.upper()
                desc_mejorada = row.get("descripcion_mejorada")
                alias_propuestos_raw = row.get("alias_propuestos", "")

                if accion not in ["ACTUALIZAR", "UPDATE"]:
                    print(f"Saltando codigo_producto: {product_code} (accion={accion})")
                    continue

                if not product_code or not desc_mejorada:
                    print(f"Fila incompleta para codigo_producto: {product_code}. Ignorando.")
                    continue

                # 1. Verificar existencia del producto
                exists = await conn.fetchval(
                    f"SELECT EXISTS(SELECT 1 FROM {esquema}.productos WHERE product_code = $1)",
                    product_code
                )
                if not exists:
                    print(f"Advertencia: El producto {product_code} no existe en {esquema}.productos.")
                    continue

                # 2. Actualizar descripción en DB
                try:
                    await conn.execute(
                        f"UPDATE {esquema}.productos SET descripcion = $1, updated_at = NOW() WHERE product_code = $2",
                        desc_mejorada, product_code
                    )
                    actualizados += 1
                    product_codes_modificados.append(product_code)
                except Exception as e:
                    print(f"Error actualizando descripción para {product_code}: {e}")
                    continue

                # 3. Insertar/Actualizar aliases
                if alias_propuestos_raw:
                    aliases = [a.strip() for a in alias_propuestos_raw.split("|") if a.strip()]
                    nombre_prod = row.get("nombre", "")
                    aliases_seguros = filtrar_alias_peligrosos(nombre_prod, aliases)

                    for alias_raw in aliases_seguros:
                        alias_norm = normalizar_alias(alias_raw)
                        if not alias_norm:
                            continue
                        try:
                            await conn.execute(
                                f"""
                                INSERT INTO {esquema}.productos_aliases (product_code, alias_raw, alias_norm, weight, updated_at)
                                VALUES ($1, $2, $3, 1.0, NOW())
                                ON CONFLICT (product_code, alias_norm) DO UPDATE
                                SET alias_raw = EXCLUDED.alias_raw, updated_at = NOW()
                                """,
                                product_code, alias_raw, alias_norm
                            )
                            aliases_insertados += 1
                        except Exception as e:
                            print(f"Error actualizando alias '{alias_raw}' para {product_code}: {e}")

        print(f"\n¡Base de datos actualizada con éxito!")
        print(f"- Productos modificados: {actualizados}")
        print(f"- Aliases agregados/modificados: {aliases_insertados}")

        # 4. Encolar la vectorización en el backend si hay productos modificados
        if product_codes_modificados:
            backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app")
            print(f"\nDisparando re-vectorización en el backend para {len(product_codes_modificados)} productos...")
            try:
                base_url = backend_url.rstrip("/")
                endpoint = f"{base_url}/{esquema}/productos/vectorize"
                resp = requests.post(endpoint, json=product_codes_modificados, timeout=30)
                if resp.status_code == 200:
                    print(f"¡Re-vectorización encolada exitosamente en el backend!")
                else:
                    print(f"Error al encolar re-vectorización en el backend (Código {resp.status_code}): {resp.text}")
            except Exception as e:
                print(f"Error de conexión al encolar re-vectorización: {e}")

    finally:
        await conn.close()

# ==========================================
# ORQUESTADOR PRINCIPAL
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Enriquecimiento de descripciones y alias de catálogos.")
    parser.add_argument("--esquema", required=True, help="Esquema de Supabase del tenant (ej: gonzales)")
    parser.add_argument("--csv-entrada", required=True, help="Ruta del CSV de entrada con los productos")
    parser.add_argument("--csv-salida", help="Ruta del CSV de salida para preview (no requerido si se usa --aplicar)")
    parser.add_argument("--aplicar", action="store_true", help="Aplica las descripciones y alias del CSV de entrada a la DB")
    
    args = parser.parse_args()

    if args.aplicar:
        asyncio.run(aplicar_actualizaciones_db(args.esquema, args.csv_entrada))
    else:
        # Modo Enriquecimiento (Dry-run / Preview)
        csv_out_path = args.csv_salida or f"implementacion/{args.esquema}/outputs/descripciones_mejoradas.csv"
        ejecutar_enriquecimiento_csv(args.csv_entrada, csv_out_path)

if __name__ == "__main__":
    main()
