import os
import sys
import csv
import argparse
import asyncio
import asyncpg
from datetime import datetime
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env local
load_dotenv()

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

async def cargar_promociones(esquema: str):
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] La variable de entorno SUPABASE_DB_URL no está configurada en el archivo .env.")
        sys.exit(1)

    # Validamos que el esquema sea alfanumérico para evitar inyecciones SQL
    if not esquema.isalnum() and "_" not in esquema:
        print(f"[FAIL] Nombre de esquema inválido '{esquema}'. Debe ser alfanumérico.")
        sys.exit(1)

    csv_path = f"implementacion/{esquema}/outputs/phase-02-promociones.csv"
    if not os.path.exists(csv_path):
        print(f"[FAIL] No se encontró el archivo CSV de promociones en: {csv_path}")
        sys.exit(1)

    # Leer promociones del CSV
    promociones = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            promociones.append(row)

    if not promociones:
        print("[FAIL] El archivo CSV de promociones está vacío.")
        sys.exit(1)

    conn = await asyncpg.connect(db_url)
    try:
        print(f"[*] Limpiando promociones anteriores en {esquema}.promociones_semanales...")
        await conn.execute(f"DELETE FROM {esquema}.promociones_semanales")
        print("✅ Promociones anteriores eliminadas.")

        inserted_count = 0
        for p in promociones:
            product_code = p["product_code"]
            
            # Obtener nombre del producto real de la DB
            product_name = await conn.fetchval(
                f"SELECT nombre FROM {esquema}.productos WHERE product_code = $1",
                product_code
            )
            if not product_name:
                print(f"[WARN] El producto {product_code} no existe en la tabla de productos. Saltando.")
                continue

            # Mapear tipos de descuento y valores
            kind = p["discount_kind"]
            val = float(p["discount_value"])
            
            descuento_percent = None
            descuento_nominal = None
            precio_promocional = None
            discount_kind_db = ""

            if kind == "percent_off":
                discount_kind_db = "percent"
                descuento_percent = val
            elif kind == "total_off":
                discount_kind_db = "nominal"
                descuento_nominal = val
            elif kind == "fixed_price":
                discount_kind_db = "fixed_price"
                precio_promocional = val
            else:
                print(f"[WARN] Tipo de descuento '{kind}' desconocido para {product_code}. Saltando.")
                continue

            # Combinar título y descripción para la columna descripcion en BD
            full_desc = f"{p['titulo']}. {p['descripcion']}"

            # Convertir fechas
            fecha_inicio = datetime.strptime(p["fecha_inicio"], "%Y-%m-%d")
            fecha_fin = datetime.strptime(p["fecha_fin"], "%Y-%m-%d")
            
            lista_precios_id = int(p["lista_precios_id"])
            min_qty_umv = float(p["min_qty_umv"])
            is_mock = p["is_mock"].lower() == "true"

            print(f"[*] Insertando promo para {product_code} ({product_name}) - {discount_kind_db}...")
            await conn.execute(
                f"""
                INSERT INTO {esquema}.promociones_semanales (
                    product_code, descripcion, precio_promocional, fecha_inicio, fecha_fin,
                    product_name, lista_precios_id, min_qty_umv, discount_kind,
                    descuento_percent, descuento_nominal, is_mock, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW(), NOW())
                """,
                product_code, full_desc, precio_promocional, fecha_inicio, fecha_fin,
                product_name, lista_precios_id, min_qty_umv, discount_kind_db,
                descuento_percent, descuento_nominal, is_mock
            )
            inserted_count += 1

        print(f"\n✅ Carga finalizada. Se insertaron {inserted_count} promociones en la base de datos.")

        # Verificación post-carga
        rows = await conn.fetch(
            f"""
            SELECT id, product_code, product_name, discount_kind, precio_promocional, descuento_percent, descuento_nominal, lista_precios_id
            FROM {esquema}.promociones_semanales
            ORDER BY id ASC
            """
        )
        print("\n" + "=" * 60)
        print("VERIFICACIÓN DE PROMOCIONES CARGADAS EN DB")
        print("=" * 60)
        for r in rows:
            print(f"ID: {r['id']} | Cód: {r['product_code']} | Nombre: {r['product_name']}")
            print(f"  Tipo: {r['discount_kind']} | Lista Precios: {r['lista_precios_id']}")
            if r['discount_kind'] == 'percent':
                print(f"  Descuento: {r['descuento_percent']}% OFF")
            elif r['discount_kind'] == 'nominal':
                print(f"  Descuento: ${r['descuento_nominal']} OFF")
            elif r['discount_kind'] == 'fixed_price':
                print(f"  Precio Promo: ${r['precio_promocional']}")
        print("=" * 60)

    except Exception as e:
        print(f"[FAIL] Error durante la carga a la base de datos: {e}")
        sys.exit(1)
    finally:
        await conn.close()

def main():
    parser = argparse.ArgumentParser(description="Carga promociones desde el CSV a la tabla promociones_semanales de la base de datos.")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant en Supabase (ej: al_fuego)")
    args = parser.parse_args()
    
    asyncio.run(cargar_promociones(args.esquema))

if __name__ == "__main__":
    main()
