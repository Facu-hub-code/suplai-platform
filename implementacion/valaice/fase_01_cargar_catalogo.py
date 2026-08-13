import os
import sys
import csv
import json
import asyncio
import asyncpg
import unicodedata
from dotenv import load_dotenv

load_dotenv()

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def normalizar_alias(alias_raw: str) -> str:
    alias_lower = alias_raw.lower().strip()
    alias_flat = unicodedata.normalize('NFKD', alias_lower)
    return "".join([c for c in alias_flat if 'a' <= c <= 'z' or '0' <= c <= '9'])

RAW_CSV = r"implementacion/valaice/inputs/productos_raw.csv"
OUTPUT_CSV = r"implementacion/valaice/outputs/phase-01-productos.csv"

async def main():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL not found.")
        sys.exit(1)
        
    schema = "valaice"
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    
    products = []
    with open(RAW_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            products.append(r)
            
    print(f"[*] Processing {len(products)} products...")
    
    output_rows = []
    for idx, p in enumerate(products):
        sku = p['sku']
        name = p['nombre']
        bulto_units = int(p['unidades_por_bulto']) if p['unidades_por_bulto'] else 1
        peso_g = float(p['peso_por_unidad_g']) if p['peso_por_unidad_g'] else 0
        peso_kg = round(peso_g / 1000.0, 3) if peso_g > 0 else 0
        precio_bulto = float(p['precio_bulto']) if p['precio_bulto'] else 0
        precio_un_kg = float(p['precio_unidad_kg']) if p['precio_unidad_kg'] else 0
        comercializa_por = p['comercializa_por'].strip().lower()
        es_pesable = (comercializa_por == 'peso')
        
        if 'MEDIALUNA' in name.upper():
            cat = "Panadería Congelada > Medialunas"
            rot = round(0.95 - (idx * 0.02), 2)
            prio = round(0.95 - (idx * 0.02), 2)
        elif 'FACTURA' in name.upper() or 'CROISSANT' in name.upper():
            cat = "Panadería Congelada > Facturas y Bollería"
            rot = round(0.90 - (idx * 0.02), 2)
            prio = round(0.90 - (idx * 0.02), 2)
        elif 'CRIOLLO' in name.upper() or 'HOJALDRE' in name.upper() or 'TORTILLA' in name.upper() or 'CHIPACA' in name.upper() or 'CHIPÁ' in name.upper():
            cat = "Panadería Congelada > Especialidades y Criollos"
            rot = round(0.85 - (idx * 0.02), 2)
            prio = round(0.85 - (idx * 0.02), 2)
        else:
            cat = "Panadería Congelada > Panes Crudos y Precocidos"
            rot = round(0.75 - (idx * 0.02), 2)
            prio = round(0.75 - (idx * 0.02), 2)
            
        rot = max(0.10, rot)
        prio = max(0.10, prio)
        
        desc = f"Producto congelado Valaice: {name}. Formato comercial: {bulto_units} un/bulto. Precios finales con IVA incluido."
        placeholder_img = "https://images.unsplash.com/photo-1555507036-ab1f4038808a?w=500"
        
        row = {
            "product_code": sku,
            "nombre": name,
            "categoria": cat,
            "descripcion": desc,
            "precio_base": precio_bulto,
            "precio_unidad_kg": precio_un_kg,
            "unidades_por_bulto": bulto_units,
            "es_pesable": str(es_pesable).lower(),
            "peso_referencia_kg": peso_kg if peso_kg > 0 else "",
            "stock": 100,
            "rotacion_index": rot,
            "mental_priority": prio,
            "unidad_minima_de_venta": "unidad",
            "umv_tipo": "unidad",
            "cantidad_minima_de_venta": 1,
            "en_catalogo": "true",
            "is_mock": "true",
            "image_url": placeholder_img
        }
        output_rows.append(row)
        
    fieldnames = list(output_rows[0].keys())
    with open(OUTPUT_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
        
    print(f"✅ Generated {OUTPUT_CSV} with {len(output_rows)} items.")
    
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute(f"""
            INSERT INTO {schema}.listas_precios (id, nombre, descripcion, activa, es_publica, is_mock, created_at, updated_at)
            VALUES
              (1, 'Lista 1', 'Lista Base (Público - IVA Inc.)', true, true, false, now(), now()),
              (2, 'Lista 2', 'Lista Minorista Sugerido', true, true, false, now(), now()),
              (3, 'Lista 3', 'Lista Mayorista Especial', true, true, false, now(), now()),
              (4, 'Lista 4', 'Lista Gran Distribuidor', true, true, false, now(), now())
            ON CONFLICT (id) DO UPDATE SET
              nombre = EXCLUDED.nombre,
              descripcion = EXCLUDED.descripcion,
              activa = EXCLUDED.activa,
              updated_at = now();
        """)
        
        await conn.execute(f"DELETE FROM {schema}.precios_productos;")
        await conn.execute(f"DELETE FROM {schema}.productos_aliases;")
        await conn.execute(f"DELETE FROM {schema}.productos;")
        
        for r in output_rows:
            sku = r['product_code']
            peso_val = float(r['peso_referencia_kg']) if r['peso_referencia_kg'] != "" else None
            
            await conn.execute(f"""
                INSERT INTO {schema}.productos (
                    product_code, nombre, descripcion, image_url, stock, unidades_por_bulto,
                    rotacion_index, mental_priority, unidad_minima_de_venta, cantidad_minima_de_venta,
                    umv_tipo, en_catalogo, is_mock, es_pesable, peso_referencia_kg, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, now(), now()
                )
            """,
            sku, r['nombre'], r['descripcion'], r['image_url'],
            int(r['stock']), int(r['unidades_por_bulto']), float(r['rotacion_index']),
            float(r['mental_priority']), r['unidad_minima_de_venta'], int(r['cantidad_minima_de_venta']),
            r['umv_tipo'], True, True, (r['es_pesable'] == 'true'), peso_val
            )
            
            base_p = float(r['precio_base'])
            prices = [
                (1, base_p),
                (2, round(base_p * 1.15, 2)),
                (3, round(base_p * 0.90, 2)),
                (4, round(base_p * 0.85, 2))
            ]
            for lid, p_val in prices:
                await conn.execute(f"""
                    INSERT INTO {schema}.precios_productos (
                        product_code, lista_precios_id, precio_unidad, is_mock, created_at, updated_at
                    ) VALUES ($1, $2, $3, true, now(), now())
                """, sku, lid, p_val)
                
            alias_clean = normalizar_alias(r['nombre'])
            if alias_clean:
                await conn.execute(f"""
                    INSERT INTO {schema}.productos_aliases (
                        product_code, alias_raw, alias_norm, created_at, updated_at
                    ) VALUES ($1, $2, $3, now(), now())
                    ON CONFLICT DO NOTHING
                """, sku, r['nombre'].lower(), alias_clean)
                
        print(f"✅ Successfully inserted {len(output_rows)} products and prices into {schema}.productos!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
