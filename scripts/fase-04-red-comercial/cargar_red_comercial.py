"""
cargar_red_comercial.py
=======================
Carga la red comercial mock de un tenant Suplai Sales a la base de datos.

Lee los CSVs generados por preparar_red_comercial.py y realiza la inserción
secuencial respetando las claves foráneas (según SKILL.md phase-04):

  1. vendedores             → {schema}.vendedores
  2. geo_zones              → {schema}.geo_zones  (PostGIS MultiPolygon SRID=4326)
  3. vendedor_geo_zones     → {schema}.vendedor_geo_zones
  4. puntos_venta           → {schema}.puntos_venta  (un PdV por cliente, CRÍTICO para visibilidad en backoffice)
  5. clients                → {schema}.clients  (con pdv_id del paso anterior)
  6. vendedores_clientes    → {schema}.vendedores_clientes  (vínculo vendedor ↔ cliente)
  7. client_locations       → {schema}.client_locations  (lat/lng)

Uso:
    python scripts/cargar_red_comercial.py --esquema <nombre_esquema>

Variables de entorno requeridas (en .env):
    SUPABASE_DB_URL

Campos requeridos en manifest.yaml del tenant:
    tenant_id, ciudad_base, rubro, coordenadas_centro
"""

import os
import sys
import csv
import yaml
import argparse
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


async def cargar_red_comercial(esquema: str):
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] La variable SUPABASE_DB_URL no está configurada en .env")
        sys.exit(1)

    # Validar esquema
    if not all(c.isalnum() or c == "_" for c in esquema):
        print(f"[FAIL] Nombre de esquema inválido: '{esquema}'")
        sys.exit(1)

    # Rutas CSV
    base = f"implementacion/{esquema}/outputs"
    vendedores_csv = f"{base}/phase-04-vendedores.csv"
    zonas_csv = f"{base}/phase-04-zonas.csv"
    clientes_csv = f"{base}/phase-04-clientes.csv"

    for path in [vendedores_csv, zonas_csv, clientes_csv]:
        if not os.path.exists(path):
            print(f"[FAIL] CSV no encontrado: {path}")
            print("Asegúrate de haber ejecutado preparar_red_comercial.py primero.")
            sys.exit(1)

    conn = await asyncpg.connect(db_url)
    try:
        # Configurar search_path para que los tipos enum del schema del tenant
        # sean visibles sin calificar (ej: dia_de_visita_enum)
        await conn.execute(f"SET search_path TO {esquema}, core, public, extensions")

        # ----------------------------------------------------------------
        # 0. Limpiar datos mock previos (orden inverso a FKs)
        # ----------------------------------------------------------------
        print(f"[*] Limpiando datos mock previos en esquema '{esquema}'...")

        await conn.execute(f"""
            DELETE FROM {esquema}.client_locations
            WHERE client_id IN (
                SELECT id FROM {esquema}.clients WHERE is_mock = true
            )
        """)
        await conn.execute(f"""
            DELETE FROM {esquema}.vendedores_clientes
            WHERE cliente_id IN (
                SELECT id FROM {esquema}.clients WHERE is_mock = true
            )
        """)
        await conn.execute(f"DELETE FROM {esquema}.clients WHERE is_mock = true")
        await conn.execute(f"DELETE FROM {esquema}.puntos_venta WHERE is_mock = true")
        await conn.execute(f"DELETE FROM {esquema}.vendedor_geo_zones WHERE is_mock = true")
        await conn.execute(f"DELETE FROM {esquema}.geo_zones WHERE is_mock = true")
        await conn.execute(f"DELETE FROM {esquema}.vendedores WHERE is_mock = true")
        print("✅ Limpieza completada.")

        # ----------------------------------------------------------------
        # 1. Insertar vendedores
        # ----------------------------------------------------------------
        print("\n[*] Insertando vendedores...")
        vendedores_ids = []  # lista indexada (índice = vendedor_idx en CSV)
        with open(vendedores_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                vid = await conn.fetchval(f"""
                    INSERT INTO {esquema}.vendedores
                        (nombre, telefono, email, zona, codigo_ruta, activo, is_mock)
                    VALUES ($1, $2, $3, $4, $5, true, true)
                    RETURNING id
                """,
                    row["nombre"],
                    row["telefono"],
                    row["email"],
                    row["zona"],
                    row["codigo_ruta"],
                )
                vendedores_ids.append(vid)
                print(f"  ✅ Vendedor: {row['nombre']} → id={vid}")

        # ----------------------------------------------------------------
        # 2. Insertar geo_zones y vendedor_geo_zones
        # ----------------------------------------------------------------
        print(f"\n[*] Insertando {len(vendedores_ids) * 2} geo_zones...")
        geo_zone_ids = []
        with open(zonas_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                vendedor_idx = int(row["vendedor_idx"])
                vendedor_id = vendedores_ids[vendedor_idx]

                # Insertar geo_zone usando ST_GeomFromEWKT para el MultiPolygon
                # El cast ::dia_de_visita_enum funciona porque search_path ya incluye el schema
                gzid = await conn.fetchval(f"""
                    INSERT INTO {esquema}.geo_zones
                        (name, zone_type, description, color, dia_visita, codigo_ruta,
                         vendedor_principal_id, geometry, active, is_mock)
                    VALUES ($1, $2, $3, $4, $5::dia_de_visita_enum, $6, $7,
                            extensions.ST_GeomFromEWKT($8), true, true)
                    RETURNING id
                """,
                    row["nombre"],
                    row["zone_type"],
                    row["description"],
                    row["color"],
                    row["dia_visita"],
                    row["codigo_ruta"],
                    vendedor_id,
                    row["geometry_wkt"],
                )
                geo_zone_ids.append(gzid)
                print(f"  ✅ Zona: {row['nombre']} → id={gzid}")

                # Asociar vendedor ↔ zona
                await conn.execute(f"""
                    INSERT INTO {esquema}.vendedor_geo_zones
                        (vendedor_id, geo_zone_id, activo, is_mock)
                    VALUES ($1, $2, true, true)
                """, vendedor_id, gzid)

        # ----------------------------------------------------------------
        # 3-6. Insertar puntos_venta, clients, vendedores_clientes, client_locations
        # ----------------------------------------------------------------
        print(f"\n[*] Insertando clientes (puntos_venta + clients + vínculos + ubicaciones)...")

        inserted_clients = 0
        with open(clientes_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                vendedor_idx = int(row["vendedor_idx"])
                zona_idx = int(row["zona_idx"])
                vendedor_id = vendedores_ids[vendedor_idx]
                geo_zone_id = geo_zone_ids[zona_idx]

                lista_precios_id = int(row["lista_precios_id"])
                dia_visita = row["dia_de_visita"]
                dia_entrega = row["dia_de_entrega"]
                codigo = int(row["codigo"])

                # 3. Crear punto de venta
                pdv_id = await conn.fetchval(f"""
                    INSERT INTO {esquema}.puntos_venta
                        (razon_social, codigo, lista_precios_id, dia_de_visita,
                         dia_de_entrega, direccion, vendedor, vendedor_id,
                         geo_zone_id, activo_ai, is_mock)
                    VALUES ($1, $2, $3, $4::dia_de_visita_enum, $5::dia_de_entrega_enum,
                            $6, $7, $8, $9, true, true)
                    RETURNING id
                """,
                    row["razon_social"],
                    codigo,
                    lista_precios_id,
                    dia_visita,
                    dia_entrega,
                    row["direccion"],
                    row["vendedor_nombre"],
                    vendedor_id,
                    geo_zone_id,
                )

                # 4. Crear cliente vinculado al PDV
                cliente_id = await conn.fetchval(f"""
                    INSERT INTO {esquema}.clients
                        (phone_number, nombre, razon_social, lista_precios_id,
                         codigo, dia_de_visita, dia_de_entrega, direccion,
                         vendedor, pdv_id, activo_ai, is_mock)
                    VALUES ($1, $2, $3, $4, $5, $6::dia_de_visita_enum,
                            $7::dia_de_entrega_enum, $8, $9, $10, true, true)
                    RETURNING id
                """,
                    row["phone_number"],
                    row["razon_social"],
                    row["razon_social"],
                    lista_precios_id,
                    codigo,
                    dia_visita,
                    dia_entrega,
                    row["direccion"],
                    row["vendedor_nombre"],
                    pdv_id,
                )

                # 5. Vincular vendedor ↔ cliente
                await conn.execute(f"""
                    INSERT INTO {esquema}.vendedores_clientes
                        (vendedor_id, cliente_id, activo)
                    VALUES ($1, $2, true)
                """, vendedor_id, cliente_id)

                # 6. Insertar ubicación con campo geometry para satisfacer client_locations_check
                lat = float(row["lat"])
                lng = float(row["lng"])
                await conn.execute(f"""
                    INSERT INTO {esquema}.client_locations
                        (client_id, source, latitude, longitude, location,
                         geocode_status, is_primary)
                    VALUES ($1, 'backoffice', $2, $3,
                            extensions.ST_SetSRID(extensions.ST_MakePoint($3, $2), 4326),
                            'not_required', true)
                """, cliente_id, lat, lng)

                inserted_clients += 1

        # ----------------------------------------------------------------
        # Verificación post-carga
        # ----------------------------------------------------------------
        count_v = await conn.fetchval(f"SELECT COUNT(*) FROM {esquema}.vendedores WHERE is_mock = true")
        count_z = await conn.fetchval(f"SELECT COUNT(*) FROM {esquema}.geo_zones WHERE is_mock = true")
        count_c = await conn.fetchval(f"SELECT COUNT(*) FROM {esquema}.clients WHERE is_mock = true")
        count_pdv = await conn.fetchval(f"SELECT COUNT(*) FROM {esquema}.puntos_venta WHERE is_mock = true")
        count_vc = await conn.fetchval(f"""
            SELECT COUNT(*) FROM {esquema}.vendedores_clientes vc
            JOIN {esquema}.clients c ON c.id = vc.cliente_id
            WHERE c.is_mock = true
        """)
        count_loc = await conn.fetchval(f"""
            SELECT COUNT(*) FROM {esquema}.client_locations cl
            JOIN {esquema}.clients c ON c.id = cl.client_id
            WHERE c.is_mock = true
        """)

        print("\n" + "=" * 60)
        print("VERIFICACIÓN RED COMERCIAL EN BASE DE DATOS")
        print("=" * 60)
        print(f"  Vendedores (mock):         {count_v}")
        print(f"  Geo Zones (mock):          {count_z}")
        print(f"  Puntos de Venta (mock):    {count_pdv}")
        print(f"  Clientes (mock):           {count_c}")
        print(f"  Vínculos vendedor-cliente: {count_vc}")
        print(f"  Ubicaciones (client_loc):  {count_loc}")
        print("=" * 60)

        if count_c == 50 and count_v == 3 and count_z == 6:
            print("✅ Verificación exitosa: 3 vendedores, 6 zonas, 50 clientes.")
        else:
            print("[WARN] Los conteos no coinciden con los esperados (3/6/50). Revisar logs.")

    except Exception as e:
        print(f"\n[FAIL] Error durante la carga: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Carga la red comercial mock (vendedores, zonas, clientes) en la BD."
    )
    parser.add_argument(
        "--esquema", required=True, help="Esquema del tenant en Supabase (ej: al_fuego)"
    )
    args = parser.parse_args()

    asyncio.run(cargar_red_comercial(args.esquema))


if __name__ == "__main__":
    main()
