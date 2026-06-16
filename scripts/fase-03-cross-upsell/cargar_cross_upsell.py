import os
import sys
import csv
import yaml
import argparse
import asyncio
import asyncpg
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env local
load_dotenv()

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

async def cargar_cross_upsell(esquema: str):
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] La variable de entorno SUPABASE_DB_URL no está configurada en el archivo .env.")
        sys.exit(1)

    # Validar esquema
    if not esquema.isalnum() and "_" not in esquema:
        print(f"[FAIL] Nombre de esquema inválido '{esquema}'. Debe ser alfanumérico.")
        sys.exit(1)

    # 1. Leer manifest para obtener tenant_id
    manifest_path = f"implementacion/{esquema}/manifest.yaml"
    if not os.path.exists(manifest_path):
        print(f"[FAIL] No se encontró el manifest en: {manifest_path}")
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as mf:
        manifest = yaml.safe_load(mf)

    tenant_id = manifest.get("tenant_id", "")
    if not tenant_id:
        print("[FAIL] tenant_id no configurado en manifest.yaml.")
        sys.exit(1)

    # Rutas de archivos CSV
    cross_csv = f"implementacion/{esquema}/outputs/phase-03-cross-sell.csv"
    up_csv = f"implementacion/{esquema}/outputs/phase-03-up-sell.csv"

    if not os.path.exists(cross_csv) or not os.path.exists(up_csv):
        print(f"[FAIL] Faltan los archivos CSV de mapeo en outputs.")
        print(f"Asegúrate de haber ejecutado preparar_cross_upsell.py primero.")
        sys.exit(1)

    # Leer archivos CSV
    cross_rows = []
    with open(cross_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cross_rows.append(row)

    up_rows = []
    with open(up_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            up_rows.append(row)

    conn = await asyncpg.connect(db_url)
    try:
        # 2. Limpiar mapeos anteriores para este tenant_id
        print(f"[*] Limpiando mapeos anteriores para tenant_id: {tenant_id}...")
        await conn.execute(
            "DELETE FROM public.tenant_cross_sell_mappings WHERE tenant_id = $1",
            tenant_id
        )
        await conn.execute(
            "DELETE FROM public.tenant_up_sell_mappings WHERE tenant_id = $1",
            tenant_id
        )
        print("✅ Mapeos anteriores eliminados.")

        # 3. Cargar Cross-sell
        print(f"[*] Insertando {len(cross_rows)} relaciones de Cross-sell...")
        inserted_cross = 0
        for i, row in enumerate(cross_rows, start=1):
            base_code = row["base_product_code"]
            related_code = row["related_product_code"]
            is_mock = row["is_mock"].lower() == "true"
            
            # Verificar que los códigos existan en productos de este esquema
            exists_base = await conn.fetchval(
                f"SELECT EXISTS(SELECT 1 FROM {esquema}.productos WHERE product_code = $1)",
                base_code
            )
            exists_related = await conn.fetchval(
                f"SELECT EXISTS(SELECT 1 FROM {esquema}.productos WHERE product_code = $1)",
                related_code
            )
            if not exists_base or not exists_related:
                print(f"  [WARN] Salteando par {base_code} -> {related_code} porque alguno de los códigos no existe en {esquema}.productos.")
                continue

            await conn.execute(
                """
                INSERT INTO public.tenant_cross_sell_mappings (
                    tenant_id, base_product_code, related_product_code, priority, active, is_mock, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, true, $5, NOW(), NOW())
                """,
                tenant_id, base_code, related_code, i, is_mock
            )
            inserted_cross += 1

        # 4. Cargar Up-sell
        print(f"[*] Insertando {len(up_rows)} relaciones de Up-sell...")
        inserted_up = 0
        for i, row in enumerate(up_rows, start=1):
            base_code = row["base_product_code"]
            related_code = row["related_product_code"]
            is_mock = row["is_mock"].lower() == "true"
            
            exists_base = await conn.fetchval(
                f"SELECT EXISTS(SELECT 1 FROM {esquema}.productos WHERE product_code = $1)",
                base_code
            )
            exists_related = await conn.fetchval(
                f"SELECT EXISTS(SELECT 1 FROM {esquema}.productos WHERE product_code = $1)",
                related_code
            )
            if not exists_base or not exists_related:
                print(f"  [WARN] Salteando par {base_code} -> {related_code} porque alguno de los códigos no existe en {esquema}.productos.")
                continue

            await conn.execute(
                """
                INSERT INTO public.tenant_up_sell_mappings (
                    tenant_id, base_product_code, related_product_code, priority, active, is_mock, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, true, $5, NOW(), NOW())
                """,
                tenant_id, base_code, related_code, i, is_mock
            )
            inserted_up += 1

        print(f"\n✅ Carga completada. Se insertaron {inserted_cross} cross-sell y {inserted_up} up-sell mappings en public.")

        # 5. Verificación post-carga
        count_cross = await conn.fetchval(
            "SELECT COUNT(*) FROM public.tenant_cross_sell_mappings WHERE tenant_id = $1",
            tenant_id
        )
        count_up = await conn.fetchval(
            "SELECT COUNT(*) FROM public.tenant_up_sell_mappings WHERE tenant_id = $1",
            tenant_id
        )
        
        print("\n" + "=" * 60)
        print("VERIFICACIÓN DE MAPEOS EN LA BASE DE DATOS")
        print("=" * 60)
        print(f"Total Cross-sell en DB: {count_cross}")
        print(f"Total Up-sell en DB: {count_up}")
        print("=" * 60)

    except Exception as e:
        print(f"[FAIL] Error al cargar los mapeos en la base de datos: {e}")
        sys.exit(1)
    finally:
        await conn.close()

def main():
    parser = argparse.ArgumentParser(description="Carga los mapeos de cross-sell y up-sell del CSV a las tablas públicas de la DB.")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant en Supabase (ej: al_fuego)")
    args = parser.parse_args()
    
    asyncio.run(cargar_cross_upsell(args.esquema))

if __name__ == "__main__":
    main()
