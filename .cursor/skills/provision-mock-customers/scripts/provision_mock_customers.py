import os
import sys
import yaml
import random
import math
import argparse
import asyncio
import asyncpg
from dotenv import load_dotenv

# Define Argentine names and business suffixes for high-quality mock data
BUSINESS_TYPES = ["Almacén", "Kiosco", "Minimercado", "Supermercado", "Fiambrería", "Verdulería", "Carnicería", "Parrilla", "Rotisería", "Ferretería", "Pinturería", "Farmacia"]
BUSINESS_NAMES = [
    "El Sol", "Don Bosco", "San Martín", "La Amistad", "La Estación", "El Gaucho", "La Esquina", "Nuestra Señora", 
    "Los Pinos", "El Recreo", "Don Pedro", "Don Juan", "La Unión", "El Nene", "La Cumbre", "El Cruce", 
    "El Trébol", "La Palmera", "El Solcito", "La Esperanza", "San Cayetano", "Don Carlos", "El Buen Gusto", 
    "La Favorita", "El Progreso", "Los Amigos", "El Edén", "San José", "La Tradición", "El Porvenir", 
    "La Estrella", "Don Luis", "Doña María", "El Triunfo", "Las Flores", "El Sauce", "La Nueva Era", 
    "Los Olivos", "El Ombú", "La Querencia"
]

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado"]

def generar_telefono(seed: int) -> str:
    random.seed(seed + 9999)
    codigo_area = random.choice(["11", "351", "341", "261", "381", "358", "299"])
    sufijo = random.randint(1000000, 9999999)
    return f"549{codigo_area}{sufijo}"

async def provision_mock_customers(esquema: str, cantidad: int, db_url: str = None):
    # Load env vars
    if not db_url:
        load_dotenv(".env")
        db_url = os.getenv("SUPABASE_DB_URL")
        
    if not db_url:
        print("[FAIL] La variable SUPABASE_DB_URL no está configurada.")
        sys.exit(1)

    print(f"[*] Iniciando aprovisionamiento de clientes mock para el esquema '{esquema}'...")
    
    # Try to read coordinates and rubro from manifest
    lat_centro = -31.4135
    lon_centro = -64.1810
    rubro = "distribuidora general"
    
    manifest_path = f"implementacion/{esquema}/manifest.yaml"
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)
                coords = manifest.get("coordenadas_centro")
                if coords:
                    lat_centro = float(coords[0])
                    lon_centro = float(coords[1])
                rubro = manifest.get("rubro", rubro)
                print(f"  [+] Info del manifest: Coordenadas [{lat_centro}, {lon_centro}], Rubro: '{rubro}'")
        except Exception as e:
            print(f"  [WARN] No se pudo leer manifest.yaml: {e}. Usando coordenadas de fallback.")
    else:
        print(f"  [NOTE] Manifest local no encontrado en '{manifest_path}'. Usando coordenadas de fallback.")

    conn = await asyncpg.connect(db_url)
    try:
        # Set search_path
        await conn.execute(f"SET search_path TO {esquema}, core, public, extensions")
        
        # 1. Fetch or create Vendedores
        vendedores = await conn.fetch(f"SELECT id, nombre, zona FROM {esquema}.vendedores")
        if not vendedores:
            print("  [*] No se encontraron vendedores en la BD. Creando 3 vendedores por defecto...")
            vendedor_names = ["Carlos Gomez", "Ana Martinez", "Diego Rodriguez"]
            for i, name in enumerate(vendedor_names):
                tel = generar_telefono(i + 100)
                email = f"{name.lower().replace(' ', '.')}@suplaisales.mock"
                vid = await conn.fetchval(f"""
                    INSERT INTO {esquema}.vendedores (nombre, telefono, email, zona, codigo_ruta, activo, is_mock)
                    VALUES ($1, $2, $3, $4, $5, true, true)
                    RETURNING id
                """, name, tel, email, f"ZONA_{i+1}", f"R0{i+1}")
                print(f"    ✅ Vendedor creado: {name} (ID: {vid})")
            vendedores = await conn.fetch(f"SELECT id, nombre, zona FROM {esquema}.vendedores")
        else:
            print(f"  [+] Encontrados {len(vendedores)} vendedores existentes.")

        # 2. Fetch or create Geo Zones
        zones = await conn.fetch(f"SELECT id, name, ST_X(extensions.ST_Centroid(geometry)) as lon, ST_Y(extensions.ST_Centroid(geometry)) as lat FROM {esquema}.geo_zones")
        if not zones:
            print("  [*] No se encontraron geo_zones en la BD. Creando 6 zonas por defecto...")
            colores = ["#E74C3C", "#E67E22", "#27AE60", "#2980B9", "#8E44AD", "#F39C12"]
            for i in range(6):
                angulo = math.radians(i * 60)
                dist = 0.015
                lon_c = round(lon_centro + dist * math.cos(angulo), 4)
                lat_c = round(lat_centro + dist * math.sin(angulo), 4)
                
                # Make a simple square polygon
                delta = 0.004
                coords_poly = [
                    (lon_c - delta, lat_c - delta),
                    (lon_c + delta, lat_c - delta),
                    (lon_c + delta, lat_c + delta),
                    (lon_c - delta, lat_c + delta),
                    (lon_c - delta, lat_c - delta)
                ]
                coords_str = ", ".join(f"{lon} {lat}" for lon, lat in coords_poly)
                wkt = f"SRID=4326;MULTIPOLYGON((({coords_str})))"
                
                vendedor = vendedores[i % len(vendedores)]
                vendedor_id = vendedor["id"]
                
                gzid = await conn.fetchval(f"""
                    INSERT INTO {esquema}.geo_zones 
                    (name, zone_type, description, color, dia_visita, codigo_ruta, vendedor_principal_id, geometry, active, is_mock)
                    VALUES ($1, 'sales', $2, $3, $4::dia_de_visita_enum, $5, $6, extensions.ST_GeomFromEWKT($7), true, true)
                    RETURNING id
                """, f"Sector {i+1}", f"Zona de prueba {i+1}", colores[i], DIAS[i], f"R0{(i//2)+1}-A", vendedor_id, wkt)
                
                # Link vendedor to zone
                await conn.execute(f"""
                    INSERT INTO {esquema}.vendedor_geo_zones (vendedor_id, geo_zone_id, activo, is_mock)
                    VALUES ($1, $2, true, true)
                """, vendedor_id, gzid)
                
                print(f"    ✅ Geo Zone creada: Sector {i+1} (ID: {gzid})")
                
            zones = await conn.fetch(f"SELECT id, name, ST_X(extensions.ST_Centroid(geometry)) as lon, ST_Y(extensions.ST_Centroid(geometry)) as lat FROM {esquema}.geo_zones")
        else:
            print(f"  [+] Encontradas {len(zones)} geo_zones existentes.")

        # 3. Fetch price lists
        price_lists = await conn.fetch(f"SELECT id FROM {esquema}.listas_precios")
        price_list_ids = [r["id"] for r in price_lists] if price_lists else [1]
        print(f"  [+] Usando IDs de listas de precios: {price_list_ids}")

        # 4. Generate mock customers
        print(f"  [*] Generando {cantidad} clientes mock...")
        created_count = 0
        
        # Prepare business types suitable for the tenant's rubro
        rubro_l = rubro.lower()
        suitable_types = BUSINESS_TYPES
        if "pintur" in rubro_l:
            suitable_types = ["Pinturería", "Ferretería", "Corralón"]
        elif "carne" in rubro_l or "parrill" in rubro_l:
            suitable_types = ["Carnicería", "Parrilla", "Rotisería", "Asadería"]
        elif "ferret" in rubro_l:
            suitable_types = ["Ferretería", "Herramientas", "Corralón"]

        used_phones = set()
        
        # Query existing phones to avoid conflicts
        existing_phones = await conn.fetch(f"SELECT phone_number FROM {esquema}.clients")
        for p in existing_phones:
            used_phones.add(p["phone_number"])

        for i in range(cantidad):
            # Select a random zone and its associated seller
            zone = random.choice(zones)
            zone_id = zone["id"]
            
            # Find seller linked to this zone, or pick a random one
            vendedor_id = None
            vendedor_name = "Sin Vendedor"
            vendedor_row = await conn.fetchrow(f"""
                SELECT v.id, v.nombre FROM {esquema}.vendedores v
                JOIN {esquema}.vendedor_geo_zones vgz ON v.id = vgz.vendedor_id
                WHERE vgz.geo_zone_id = $1 LIMIT 1
            """, zone_id)
            if vendedor_row:
                vendedor_id = vendedor_row["id"]
                vendedor_name = vendedor_row["nombre"]
            else:
                vendedor = random.choice(vendedores)
                vendedor_id = vendedor["id"]
                vendedor_name = vendedor["nombre"]

            # Generate names
            b_type = random.choice(suitable_types)
            b_name = random.choice(BUSINESS_NAMES)
            razon_social = f"{b_type} {b_name} SRL"
            nombre_comercial = f"{b_type} {b_name}"
            
            # Generate unique phone
            phone = None
            for attempt in range(100):
                candidate = generar_telefono(i + attempt * 1000)
                if candidate not in used_phones:
                    phone = candidate
                    used_phones.add(phone)
                    break
            if not phone:
                phone = f"54911{random.randint(10000000, 99999999)}"

            # Disperse coordinate around zone centroid
            zone_lon = float(zone["lon"]) if zone["lon"] else lon_centro
            zone_lat = float(zone["lat"]) if zone["lat"] else lat_centro
            lat_disp = round(zone_lat + random.uniform(-0.005, 0.005), 6)
            lon_disp = round(zone_lon + random.uniform(-0.005, 0.005), 6)

            # Randomize attributes
            lista_precios_id = random.choice(price_list_ids)
            dia_visita = random.choice(DIAS)
            dia_entrega = random.choice(DIAS)
            codigo = 1000 + i
            direccion = f"Calle Ficticia {random.randint(100, 2999)}, {esquema.replace('_', ' ').title()}"

            # Create Punto Venta
            pdv_id = await conn.fetchval(f"""
                INSERT INTO {esquema}.puntos_venta
                (razon_social, codigo, lista_precios_id, dia_de_visita, dia_de_entrega, direccion, vendedor, vendedor_id, geo_zone_id, activo_ai, is_mock)
                VALUES ($1, $2, $3, $4::dia_de_visita_enum, $5::dia_de_entrega_enum, $6, $7, $8, $9, true, true)
                RETURNING id
            """, razon_social, codigo, lista_precios_id, dia_visita, dia_entrega, direccion, vendedor_name, vendedor_id, zone_id)

            # Create Client
            cliente_id = await conn.fetchval(f"""
                INSERT INTO {esquema}.clients
                (phone_number, nombre, razon_social, lista_precios_id, codigo, dia_de_visita, dia_de_entrega, direccion, vendedor, pdv_id, activo_ai, is_mock)
                VALUES ($1, $2, $3, $4, $5, $6::dia_de_visita_enum, $7::dia_de_entrega_enum, $8, $9, $10, true, true)
                RETURNING id
            """, phone, nombre_comercial, razon_social, lista_precios_id, codigo, dia_visita, dia_entrega, direccion, vendedor_name, pdv_id)

            # Link Vendedor ↔ Client
            await conn.execute(f"""
                INSERT INTO {esquema}.vendedores_clientes (vendedor_id, cliente_id, activo)
                VALUES ($1, $2, true)
            """, vendedor_id, cliente_id)

            # Create Location
            await conn.execute(f"""
                INSERT INTO {esquema}.client_locations (client_id, source, latitude, longitude, location, geocode_status, is_primary)
                VALUES ($1, 'backoffice', $2, $3, extensions.ST_SetSRID(extensions.ST_MakePoint($4, $2), 4326), 'not_required', true)
            """, cliente_id, lat_disp, lon_disp, lon_disp)

            created_count += 1

        print(f"  [+] Aprovisionamiento exitoso. Se insertaron {created_count} clientes en '{esquema}'.")

    except Exception as e:
        print(f"[FAIL] Error durante el aprovisionamiento: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aprovisiona clientes mock genéricos para pruebas de implementación.")
    parser.add_argument("--esquema", required=True, help="El esquema del tenant (ej: distribuidora_lyl)")
    parser.add_argument("--cantidad", type=int, default=50, help="Cantidad de clientes mock a generar (default: 50)")
    args = parser.parse_args()
    
    asyncio.run(provision_mock_customers(args.esquema, args.cantidad))
