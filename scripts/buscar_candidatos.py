import os
import argparse
import asyncio
import asyncpg
import csv
import re
from dotenv import load_dotenv

load_dotenv()

# Listado de sustantivos comunes de categorías de alimentos/bebidas y golosinas en Argentina.
# Si el nombre del producto no contiene ninguno de estos, se considera altamente ambiguo para un LLM/RAG.
SUSTANTIVOS_CATEGORIA = {
    "chocolate", "choco", "jugo", "galleta", "galletita", "oblea", "caramelo", "chupetin", 
    "chicle", "alfajor", "bebida", "agua", "gaseosa", "salsa", "aderezo", "papas", "snack", 
    "barrita", "aceite", "ketchup", "mostaza", "mayonesa", "arroz", "fideos", "pure", "tomate", 
    "flan", "gelatina", "postre", "bizcochuelo", "polenta", "harina", "yerba", "te", "cafe", 
    "leche", "crema", "queso", "manteca", "yogur", "yogurt", "dulce", "mermelada", "turron", 
    "pastilla", "goma", "mani", "nuez", "almendra", "pistacho", "avellana", "copetin", 
    "chizito", "palito", "cereal", "avena", "vainilla", "bizcocho", "tarta", "budin", "pan", 
    "tostada", "sal", "pimienta", "vinagre", "aceto", "bicarbonato", "polvo", "levadura", 
    "caldo", "sopa", "jardinera", "arveja", "lenteja", "poroto", "garbanzo", "choclo", 
    "maiz", "atun", "sardina", "caballa", "pate", "picadillo", "condimento", "oregano", 
    "provenzal", "pimenton", "aji", "comino", "masala", "curry", "aceituna", "durazno", 
    "pera", "piña", "anana", "coctel", "cacao", "edulcorante", "azucar", "miel", "helado"
}

BOILERPLATE_MARKETING = [
    "descubre", "disfruta", "sabor", "irresistible", "delicioso", "perfecto", "ideal", 
    "margen de ganancia", "rotación", "kiosco", "almacén", "mostrador", "impulso"
]

def calcular_puntuacion_ambiguedad(nombre: str, descripcion: str, tiene_alias: bool) -> float:
    score = 0.0
    nombre_lower = nombre.lower()
    desc_lower = (descripcion or "").lower()

    # 1. Falta de sustantivo de categoría en el nombre (Muy confuso para RAG/LLM)
    tiene_categoria = any(sustantivo in nombre_lower for sustantivo in SUSTANTIVOS_CATEGORIA)
    if not tiene_categoria:
        score += 15.0  # Gran penalización de ambigüedad si no se menciona qué es el producto

    # 2. Ausencia de alias existentes
    if not tiene_alias:
        score += 10.0

    # 3. Descripción nula, vacía o excesivamente corta
    if not descripcion or len(descripcion.strip()) < 10:
        score += 8.0
    else:
        # 4. Presencia de frases publicitarias/marketing (fluff)
        coincidencias_fluff = sum(1 for palabra in BOILERPLATE_MARKETING if palabra in desc_lower)
        score += min(coincidencias_fluff * 1.5, 6.0)

    return score

async def buscar_candidatos(esquema: str, limite: int = 50):
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("Error: SUPABASE_DB_URL no configurada en el archivo .env.")
        return

    # Validamos que el esquema sea alfanumérico para evitar inyecciones SQL
    if not esquema.isalnum() and "_" not in esquema:
        print(f"Error: Nombre de esquema inválido '{esquema}'. Debe ser alfanumérico.")
        return

    conn = await asyncpg.connect(db_url)
    
    # Obtenemos todos los productos activos y marcamos si ya tienen alias
    query = f"""
        SELECT p.product_code, p.nombre, p.descripcion,
               (CASE WHEN a.product_code IS NOT NULL THEN TRUE ELSE FALSE END) as tiene_alias
        FROM {esquema}.productos p
        LEFT JOIN (
            SELECT DISTINCT product_code FROM {esquema}.productos_aliases
        ) a ON p.product_code = a.product_code
        WHERE p.en_catalogo = true;
    """
    
    try:
        rows = await conn.fetch(query)
    except Exception as e:
        print(f"Error al consultar la base de datos: {e}")
        await conn.close()
        return

    await conn.close()
    
    candidatos = []
    for r in rows:
        nombre = r['nombre'] or ""
        descripcion = r['descripcion'] or ""
        tiene_alias = r['tiene_alias']
        
        score = calcular_puntuacion_ambiguedad(nombre, descripcion, tiene_alias)
        candidatos.append({
            "product_code": r['product_code'],
            "nombre": nombre,
            "descripcion": descripcion,
            "score": score
        })
        
    # Ordenar por puntuación de ambigüedad descendente
    candidatos.sort(key=lambda x: x["score"], reverse=True)
    
    # Tomamos los N más ambiguos
    top_candidatos = candidatos[:limite]
    
    print(f"Búsqueda finalizada. Seleccionados {len(top_candidatos)} candidatos más ambiguos para enriquecer.")
    
    directorio_salida = f"implementacion/{esquema}/inputs"
    os.makedirs(directorio_salida, exist_ok=True)
    ruta_salida = os.path.join(directorio_salida, "candidatos_a_enriquecer.csv")
    
    with open(ruta_salida, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["product_code", "nombre", "descripcion"])
        for c in top_candidatos:
            writer.writerow([c['product_code'], c['nombre'], c['descripcion']])
            
    print(f"Archivo de candidatos escrito exitosamente en: {ruta_salida}")

def main():
    parser = argparse.ArgumentParser(description="Busca candidatos a enriquecer según criterios de ambigüedad RAG.")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant en la base de datos (ej: gonzales)")
    parser.add_argument("--limite", type=int, default=50, help="Cantidad de candidatos a buscar (default: 50)")
    args = parser.parse_args()
    
    asyncio.run(buscar_candidatos(args.esquema, args.limite))

if __name__ == "__main__":
    main()
