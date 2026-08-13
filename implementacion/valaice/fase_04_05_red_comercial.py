import os
import sys
import csv
import json
import asyncio
import asyncpg
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

schema = "valaice"

vendedores_list = [
    {"id": 1, "nombre": "Carlos Gómez", "telefono": "5493547111001", "email": "cgomez@valaice.com.ar", "zona": "Alta Gracia Centro & Norte", "is_mock": True},
    {"id": 2, "nombre": "Martin Peralta", "telefono": "5493547111002", "email": "mperalta@valaice.com.ar", "zona": "Alta Gracia Sur & Paravachasca", "is_mock": True},
    {"id": 3, "nombre": "Sofía Rossi", "telefono": "5493547111003", "email": "srossi@valaice.com.ar", "zona": "Córdoba Capital Sur", "is_mock": True}
]

zonas_list = [
    {"id": 101, "name": "Alta Gracia Centro", "zone_type": "sales", "vendedor_principal_id": 1, "is_mock": True},
    {"id": 102, "name": "Alta Gracia Norte / Pellegrini", "zone_type": "sales", "vendedor_principal_id": 1, "is_mock": True},
    {"id": 103, "name": "Alta Gracia Sur / Liniers", "zone_type": "sales", "vendedor_principal_id": 2, "is_mock": True},
    {"id": 104, "name": "Anisacate / La Bolsa", "zone_type": "sales", "vendedor_principal_id": 2, "is_mock": True},
    {"id": 105, "name": "Villa General Belgrano", "zone_type": "sales", "vendedor_principal_id": 2, "is_mock": True},
    {"id": 106, "name": "Córdoba Capital Sur", "zone_type": "sales", "vendedor_principal_id": 3, "is_mock": True}
]

sample_geojson = json.dumps({
    "type": "Polygon",
    "coordinates": [[
        [-64.44, -31.64],
        [-64.41, -31.64],
        [-64.41, -31.67],
        [-64.44, -31.67],
        [-64.44, -31.64]
    ]]
})

nombres_negocios = [
    "Panadería El Sol", "Café Central Alta Gracia", "Confitería La Estación", "Minimarket El Buen Gusto",
    "Servicentro YPF La Gruta", "Panadería Dulce Hogar", "Buffet Club Deportivo", "Parador Los Aromos",
    "Bakery & Coffee Sierras", "Panadería La Espiga", "Cafetería Italia", "Bar & Resto Plaza",
    "Estación Shell Paravachasca", "Supermercado Becerra", "Despensa Don José", "Panadería Santa María",
    "Delicias de la Villa", "Café de la Plaza", "Panadería El Rosario", "Punto Dulce Alta Gracia",
    "Estación Axion Ruta 5", "Panadería San Cayetano", "Cafetería El Molino", "Despensa La Esquina",
    "Panadería Hojaldres & Co", "Café Bar El Tajamar", "Panificados La Serranita", "Minimarket Los Olivos",
    "Buffet Estación Shell", "Panadería La Nueva Espiga", "Croissant & Co", "Café Gourmet Sierras",
    "Panadería Tradición Serrana", "Supermercado San Martín", "Bar de la Estación", "Parador VGB",
    "Panadería El Artesano", "Despensa El Cruce", "Café Avenida", "Panadería Los Criollos",
    "Panadería San Antonio", "Café Los Álamos", "Minimarket Belgrano", "Parador El Candil",
    "Panadería La Cabaña", "Cafetería La Catedral", "Despensa El Carmen", "Buffet YPF Sierras",
    "Panadería El Trigo de Oro", "Café Colonial"
]

dias = ["lunes", "martes", "miercoles", "jueves", "viernes"]

async def main():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL not found.")
        sys.exit(1)
        
    os.makedirs(f"implementacion/{schema}/outputs", exist_ok=True)
    
    with open(f"implementacion/{schema}/outputs/phase-04-vendedores.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(vendedores_list[0].keys()))
        writer.writeheader()
        writer.writerows(vendedores_list)
        
    with open(f"implementacion/{schema}/outputs/phase-04-zonas.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(zonas_list[0].keys()))
        writer.writeheader()
        writer.writerows(zonas_list)
        
    clients_rows = []
    flags_rows = []
    
    random.seed(42)
    now = datetime.now()
    
    for i in range(1, 51):
        is_erp = (i <= 40)
        code = 1000 + i if is_erp else 0
        name = nombres_negocios[i - 1]
        phone = f"549354749{i:04d}"
        
        v_idx = (i % 3)
        vendedor = vendedores_list[v_idx]["nombre"]
        lista_id = 1 if i % 2 == 1 else (3 if i % 3 == 0 else 2)
        
        is_wa_valid = (i <= 30)
        wa_status = "CONFIRMED" if is_wa_valid else "UNCHECKED"
        
        client_entry = {
            "id": i,
            "codigo": code,
            "nombre": name,
            "razon_social": f"{name} S.R.L.",
            "phone_number": phone,
            "direccion": f"Av. Belgrano {100 + i * 15}, Alta Gracia, Córdoba",
            "vendedor": vendedor,
            "lista_precios_id": lista_id,
            "cuit": f"30-71{i:06d}-9",
            "activo_ai": True,
            "is_mock": True
        }
        clients_rows.append(client_entry)
        
        flag_entry = {
            "cliente_id": i,
            "codigo_erp": code,
            "nombre": name,
            "phone_number": phone,
            "es_cliente_erp": is_erp,
            "whatsapp_validado": is_wa_valid,
            "whatsapp_estado": wa_status
        }
        flags_rows.append(flag_entry)
        
    with open(f"implementacion/{schema}/outputs/phase-04-clientes.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(clients_rows[0].keys()))
        writer.writeheader()
        writer.writerows(clients_rows)
        
    with open(f"implementacion/{schema}/outputs/phase-05-clientes-flags.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(flags_rows[0].keys()))
        writer.writeheader()
        writer.writerows(flags_rows)
        
    print(f"✅ Generated Phase 4 and 5 CSVs for {schema}.")
    
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute(f"DELETE FROM {schema}.vendedores_clientes;")
        await conn.execute(f"DELETE FROM {schema}.vendedor_geo_zones;")
        await conn.execute(f"DELETE FROM {schema}.clients;")
        await conn.execute(f"DELETE FROM {schema}.geo_zones;")
        await conn.execute(f"DELETE FROM {schema}.vendedores;")
        
        for v in vendedores_list:
            await conn.execute(f"""
                INSERT INTO {schema}.vendedores (id, nombre, telefono, email, activo, zona, is_mock, created_at, updated_at)
                VALUES ($1, $2, $3, $4, true, $5, $6, now(), now())
            """, v['id'], v['nombre'], v['telefono'], v['email'], v['zona'], v['is_mock'])
            
        for z in zonas_list:
            zid = z['id']
            # Asignar geometrías delimitadas por zona
            geom_wkt = 'POLYGON((-64.44 -31.64, -64.41 -31.64, -64.41 -31.66, -64.44 -31.66, -64.44 -31.64))'
            if zid == 102:
                geom_wkt = 'POLYGON((-64.44 -31.61, -64.41 -31.61, -64.41 -31.64, -64.44 -31.64, -64.44 -31.61))'
            elif zid == 103:
                geom_wkt = 'POLYGON((-64.45 -31.66, -64.41 -31.66, -64.41 -31.69, -64.45 -31.69, -64.45 -31.66))'
            elif zid == 104:
                geom_wkt = 'POLYGON((-64.44 -31.69, -64.38 -31.69, -64.38 -31.74, -64.44 -31.74, -64.44 -31.69))'
            elif zid == 105:
                geom_wkt = 'POLYGON((-64.58 -31.95, -64.52 -31.95, -64.52 -32.00, -64.58 -32.00, -64.58 -31.95))'
            elif zid == 106:
                geom_wkt = 'POLYGON((-64.22 -31.43, -64.16 -31.43, -64.16 -31.48, -64.22 -31.48, -64.22 -31.43))'

            await conn.execute(f"""
                INSERT INTO {schema}.geo_zones (id, name, zone_type, vendedor_principal_id, geometry, active, is_mock, created_at, updated_at)
                VALUES ($1, $2, $3, $4, ST_Multi(ST_SetSRID(ST_GeomFromText($5), 4326)), true, $6, now(), now())
            """, z['id'], z['name'], z['zone_type'], z['vendedor_principal_id'], geom_wkt, z['is_mock'])
            
            await conn.execute(f"""
                INSERT INTO {schema}.vendedor_geo_zones (vendedor_id, geo_zone_id, activo, is_mock, created_at, updated_at)
                VALUES ($1, $2, true, true, now(), now())
            """, z['vendedor_principal_id'], z['id'])
            
        for c in clients_rows:
            cid = c['id']
            code = c['codigo']
            is_wa_valid = (cid <= 30)
            wa_valid_at = now if is_wa_valid else None
            v_id = vendedores_list[(cid % 3)]['id']
            z_id = 101 + (cid % 6)
            
            await conn.execute(f"""
                INSERT INTO {schema}.clients (
                    id, codigo, nombre, razon_social, phone_number, direccion, vendedor,
                    lista_precios_id, cuit, activo_ai, pdv_id, is_mock,
                    whatsapp_existencia_verificada_at, whatsapp_validado_at, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $1, $11, $12, $13, now(), now()
                )
            """, cid, code, c['nombre'], c['razon_social'], c['phone_number'], c['direccion'],
            c['vendedor'], c['lista_precios_id'], c['cuit'], c['activo_ai'], c['is_mock'],
            now, wa_valid_at
            )
            
            await conn.execute(f"""
                INSERT INTO {schema}.vendedores_clientes (vendedor_id, cliente_id, activo, created_at, updated_at)
                VALUES ($1, $2, true, now(), now())
            """, v_id, cid)

            await conn.execute(f"""
                INSERT INTO {schema}.puntos_venta (
                    id, razon_social, codigo, direccion, cuit, vendedor,
                    lista_precios_id, geo_zone_id, vendedor_id, activo_ai, is_mock, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, true, true, now(), now()
                )
            """, cid, c['razon_social'], code, c['direccion'], c['cuit'], c['vendedor'], c['lista_precios_id'], z_id, v_id)

            lat = -31.655 + (((cid * 17) % 50) - 25) * 0.001
            lon = -64.425 + (((cid * 23) % 50) - 25) * 0.001
            await conn.execute(f"""
                INSERT INTO {schema}.client_locations (
                    client_id, source, latitude, longitude, location, address_text, name,
                    is_primary, geocode_status, created_by, created_at, updated_at
                ) VALUES (
                    $1, 'manual_text', $2, $3, ST_SetSRID(ST_MakePoint($3, $2), 4326), $4, $5,
                    true, 'resolved', 'agent', now(), now()
                )
            """, cid, lat, lon, c['direccion'], c['nombre'])
            
        print(f"✅ Successfully inserted 3 sellers, 6 zones, and 50 clients into {schema} schema!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
