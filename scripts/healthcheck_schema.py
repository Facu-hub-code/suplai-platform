import os
import sys
import argparse
import asyncio
import asyncpg
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# Reconfigure stdout to use UTF-8 on Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# The default set of 29 tools in the system
ALL_TOOLS = [
    "ping", "resolve_client", "search_products", "search_products_by_category",
    "get_product_by_code", "get_catalog_link", "list_promotions", "suggest_order_boost",
    "create_order", "list_recent_orders", "get_order_status", "get_open_order_status",
    "edit_order", "confirm_order", "create_distributor_ticket", "manage_contact_agenda",
    "register_client_location", "create_order_for_client", "list_seller_clients",
    "get_seller_client_details", "set_seller_selected_client", "get_seller_selected_client",
    "get_open_order_status_for_client", "edit_order_for_client", "confirm_order_for_client",
    "suggest_order_boost_for_client", "clear_seller_context", "seller_help", "resolve_free_text_order"
]

# Client-facing only tools
CLIENT_ONLY_TOOLS = [
    "create_order", "edit_order", "confirm_order", 
    "get_open_order_status", "get_order_status", "list_recent_orders", 
    "resolve_client"
]

# Seller assistant only tools
SELLER_ONLY_TOOLS = [
    "create_order_for_client", "list_seller_clients", "get_seller_client_details",
    "set_seller_selected_client", "get_seller_selected_client", "get_open_order_status_for_client",
    "edit_order_for_client", "confirm_order_for_client", "suggest_order_boost_for_client",
    "clear_seller_context", "seller_help", "resolve_free_text_order"
]

async def check_schema(schema: str, fix_tools: bool = False, fix_rag: bool = False, fix_client: bool = False):
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] La variable de entorno SUPABASE_DB_URL no está configurada en el archivo .env.")
        sys.exit(1)

    print("=" * 60)
    print(f"EJECUTANDO HEALTHCHECK PARA EL ESQUEMA: {schema}")
    print("=" * 60)

    conn = await asyncpg.connect(db_url)
    try:
        # 1. Verificar public.distribuidoras
        print("[*] Verificando tabla public.distribuidoras...")
        dist = await conn.fetchrow(
            "SELECT id, nombre, agent_phone_number, activa, tools_habilitadas, sales_assistant_enabled, metadata FROM public.distribuidoras WHERE schema_name = $1",
            schema
        )
        if not dist:
            print(f"[FAIL] No se encontró ninguna distribuidora con schema_name = '{schema}' en public.distribuidoras.")
            sys.exit(1)

        print(f"    Nombre: {dist['nombre']}")
        print(f"    Activa: {dist['activa']}")
        print(f"    Asistente de Vendedor (sales_assistant_enabled): {dist['sales_assistant_enabled']}")

        agent_phone = dist['agent_phone_number']
        if not agent_phone or not str(agent_phone).strip():
            print("    [FAIL] No hay un número de teléfono asignado al agente (agent_phone_number).")
        else:
            print(f"    Teléfono del Agente: {agent_phone}")

        # 2. Verificar productos activos
        print(f"[*] Verificando productos en el esquema '{schema}'...")
        active_prod_count = await conn.fetchval(
            f"SELECT count(*) FROM {schema}.productos WHERE en_catalogo = true"
        )
        print(f"    Productos en catálogo (en_catalogo=true): {active_prod_count}")
        if active_prod_count == 0:
            print("    [FAIL] El catálogo no contiene productos activos (en_catalogo = true).")
        
        active_stock_count = await conn.fetchval(
            f"SELECT count(*) FROM {schema}.productos WHERE en_catalogo = true AND stock > 0"
        )
        print(f"    Productos en catálogo con stock > 0: {active_stock_count}")
        if active_stock_count == 0:
            print("    [FAIL] Ningún producto activo tiene stock > 0.")

        # 3. Verificar descripciones de productos
        missing_desc_rows = await conn.fetch(
            f"SELECT product_code, nombre FROM {schema}.productos WHERE en_catalogo = true AND stock > 0 AND (descripcion IS NULL OR TRIM(descripcion) = '')"
        )
        print(f"    Productos activos con stock sin descripción: {len(missing_desc_rows)}")
        if missing_desc_rows:
            print(f"    [WARN] Hay {len(missing_desc_rows)} productos activos con stock que carecen de descripción comercial.")
            print("           Se sugiere correr la skill 'enhance-descriptions' para enriquecerlos.")

        # 4. Verificar etiquetas de productos (tags)
        missing_tags_rows = await conn.fetch(
            f"""
            SELECT p.product_code, p.nombre 
            FROM {schema}.productos p
            LEFT JOIN {schema}.product_tags pt ON p.product_code = pt.product_code
            WHERE p.en_catalogo = true AND p.stock > 0 AND pt.product_code IS NULL
            """
        )
        missing_tags_count = len(missing_tags_rows)
        total_active_with_stock = active_stock_count or 1
        pct_missing = (missing_tags_count / total_active_with_stock) * 100.0
        print(f"    Productos activos con stock sin tags: {missing_tags_count} ({pct_missing:.1f}%)")
        if pct_missing > 30.0:
            print(f"    [FAIL] Más del 30% de los productos activos con stock ({pct_missing:.1f}%) carecen de tags asociados.")
            print("           Se sugiere proponer y aplicar una taxonomía usando los endpoints del backend.")
        elif missing_tags_count > 0:
            print(f"    [WARN] Hay {missing_tags_count} productos ({pct_missing:.1f}%) sin tags. Se encuentra dentro del límite aceptable (<=30%).")

        # 5. Verificar RAG de Productos (documents)
        print(f"[*] Verificando RAG de Productos (documents) en '{schema}'...")
        missing_doc_rows = await conn.fetch(
            f"""
            SELECT p.product_code, p.nombre 
            FROM {schema}.productos p
            WHERE p.en_catalogo = true AND p.stock > 0
              AND p.product_code NOT IN (
                  SELECT (metadata->>'product_code')::text 
                  FROM {schema}.documents 
                  WHERE metadata->>'product_code' IS NOT NULL
              )
            """
        )
        print(f"    Productos activos con stock no vectorizados en RAG: {len(missing_doc_rows)}")
        if missing_doc_rows:
            print(f"    [FAIL] Hay {len(missing_doc_rows)} productos activos con stock que NO están en documents (RAG).")
            if fix_rag:
                print(f"           [FIX] Encolando re-vectorización para {len(missing_doc_rows)} productos...")
                missing_codes = [r["product_code"] for r in missing_doc_rows]
                backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
                try:
                    resp = requests.post(f"{backend_url}/{schema}/productos/vectorize", json=missing_codes, timeout=30)
                    if resp.status_code == 200:
                        print("           [FIX] Re-vectorización encolada exitosamente.")
                    else:
                        print(f"           [FIX] Error al llamar al backend (Código {resp.status_code}): {resp.text}")
                except Exception as e:
                    print(f"           [FIX] Error de conexión: {e}")
            else:
                print("           Se requiere re-vectorizar. Ejecute con --fix-rag para encolarla automáticamente.")

        # 6. Verificar RAG de Categorías (category_documents)
        print(f"[*] Verificando RAG de Categorías (category_documents) en '{schema}'...")
        missing_cat_docs = await conn.fetch(
            f"""
            SELECT t.id, t.name 
            FROM {schema}.tags t
            WHERE t.id NOT IN (
                SELECT (metadata->>'tag_id')::integer 
                FROM {schema}.category_documents 
                WHERE metadata->>'tag_id' IS NOT NULL
            )
            """
        )
        print(f"    Categorías (tags) no vectorizadas en RAG: {len(missing_cat_docs)}")
        if missing_cat_docs:
            print(f"    [FAIL] Hay {len(missing_cat_docs)} categorías en tags que NO están en category_documents.")
            if fix_rag:
                print(f"           [FIX] Encolando re-vectorización de categorías...")
                missing_ids = [int(r["id"]) for r in missing_cat_docs]
                backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
                try:
                    resp = requests.post(f"{backend_url}/{schema}/tags/vectorize", json={"tag_ids": missing_ids}, timeout=30)
                    if resp.status_code == 200:
                        print("           [FIX] Re-vectorización de categorías encolada exitosamente.")
                    else:
                        print(f"           [FIX] Error al llamar al backend (Código {resp.status_code}): {resp.text}")
                except Exception as e:
                    print(f"           [FIX] Error de conexión: {e}")
            else:
                print("           Se requiere re-vectorizar las categorías. Ejecute con --fix-rag para encolarla automáticamente.")

        # 7. Verificar Clientes
        print(f"[*] Verificando clientes registrados en '{schema}'...")
        client_count = await conn.fetchval(f"SELECT count(*) FROM {schema}.clients")
        print(f"    Clientes registrados en total: {client_count}")
        
        test_client_exists = await conn.fetchval(
            f"SELECT EXISTS(SELECT 1 FROM {schema}.clients WHERE phone_number = '5491133333333')"
        )
        if test_client_exists:
            print("    Cliente de pruebas 'suplai-platform-test' (5491133333333): PRESENTE")
        else:
            print("    Cliente de pruebas 'suplai-platform-test' (5491133333333): AUSENTE")
            if fix_client:
                print("    [FIX] Creando cliente de prueba 'suplai-platform-test'...")
                # Buscar preferentemente una lista de precios que contenga precios en precios_productos
                first_price_list = await conn.fetchval(
                    f"SELECT DISTINCT lista_precios_id FROM {schema}.precios_productos LIMIT 1"
                )
                if not first_price_list:
                    first_price_list = await conn.fetchval(f"SELECT id FROM {schema}.listas_precios LIMIT 1")
                if not first_price_list:
                    # Crear lista de precios dummy si no hay ninguna
                    print("          [FIX] Creando lista de precios por defecto...")
                    first_price_list = await conn.fetchval(
                        f"INSERT INTO {schema}.listas_precios (nombre, created_at, updated_at) VALUES ('Lista General', now(), now()) RETURNING id"
                    )
                
                # Obtener pdv_id
                pdv_id = await conn.fetchval(f"SELECT id FROM {schema}.puntos_venta LIMIT 1")
                if not pdv_id:
                    print("          [FIX] Creando punto de venta por defecto...")
                    pdv_id = await conn.fetchval(
                        f"INSERT INTO {schema}.puntos_venta (razon_social, codigo, lista_precios_id, created_at, updated_at) VALUES ($1, $2, $3, now(), now()) RETURNING id",
                        "Suplai E2E Test PDV", 999999, first_price_list
                    )

                await conn.execute(
                    f"""
                    INSERT INTO {schema}.clients (nombre, phone_number, razon_social, codigo, activo_ai, lista_precios_id, pdv_id, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, now(), now())
                    """,
                    "suplai-platform-test", "5491133333333", "Suplai E2E Test PDV", 999999, True, first_price_list, pdv_id
                )
                print("          [FIX] Cliente de pruebas insertado con éxito.")
            else:
                print("    [FAIL] No existe un cliente de pruebas activo. Ejecute con --fix-client para insertarlo.")

        # 8. Verificar tools_habilitadas (Latencia)
        print(f"[*] Verificando configuración de herramientas (tools_habilitadas)...")
        tools_flags = dist['tools_habilitadas']
        
        if not tools_flags:
            tools_flags = {}
        else:
            tools_flags = json.loads(tools_flags) if isinstance(tools_flags, str) else dict(tools_flags)

        disabled_tools = [k for k, v in tools_flags.items() if v is False]
        print(f"    Herramientas desactivadas: {len(disabled_tools)} de {len(ALL_TOOLS)}")
        for t in disabled_tools:
            print(f"      - {t}")

        # Si no hay ninguna tool desactivada, alertamos
        if len(disabled_tools) == 0:
            print("    [FAIL] Todas las herramientas están activadas (0 herramientas marcadas como False en la DB).")
            print("           Esto aumenta sustancialmente la latencia de respuesta del agente.")
            
            # Proponemos las que se deberían desactivar
            perfil = "seller" if dist['sales_assistant_enabled'] else "client"
            to_disable = CLIENT_ONLY_TOOLS if perfil == "seller" else SELLER_ONLY_TOOLS
            to_disable = to_disable + ["ping"] # Siempre deshabilitar ping en prod
            
            print(f"    [SUGERENCIA] Para el perfil '{perfil}', se recomienda desactivar las siguientes {len(to_disable)} tools:")
            print(f"                 {', '.join(to_disable)}")
            
            if fix_tools:
                print("    [FIX] Actualizando public.distribuidoras.tools_habilitadas...")
                updated_flags = {**tools_flags}
                for t in to_disable:
                    updated_flags[t] = False
                
                await conn.execute(
                    "UPDATE public.distribuidoras SET tools_habilitadas = CAST($1 AS jsonb), updated_at = now() WHERE id = $2",
                    json.dumps(updated_flags), dist['id']
                )
                print("    [FIX] Herramientas desactivadas en la base de datos con éxito.")
            else:
                print("           Para desactivar automáticamente estas herramientas, por favor, apruebe la sugerencia y corra con --fix-tools.")

    except Exception as e:
        print(f"\n[FAIL] Ocurrió un error inesperado al realizar el healthcheck: {e}")
        sys.exit(1)
    finally:
        await conn.close()
        print("\n" + "=" * 60)
        print("PROCESO TERMINADO")
        print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="Healthcheck del esquema de base de datos de distribuidoras.")
    parser.add_argument("--schema", required=True, help="Esquema del tenant en Supabase (ej: vadra)")
    parser.add_argument("--fix-tools", action="store_true", help="Desactiva herramientas redundantes automáticamente")
    parser.add_argument("--fix-rag", action="store_true", help="Encola la re-vectorización de productos/categorías faltantes")
    parser.add_argument("--fix-client", action="store_true", help="Crea el cliente de pruebas suplai-platform-test si no existe")
    
    args = parser.parse_args()
    asyncio.run(check_schema(args.schema, fix_tools=args.fix_tools, fix_rag=args.fix_rag, fix_client=args.fix_client))

if __name__ == "__main__":
    main()
