import os
import sys
import argparse
import asyncio
import asyncpg
import json
import time
import uuid
import requests
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv()

from e2e_journeys import (
    flatten_journey_steps,
    load_journey_manifest,
    load_journeys,
    validate_journey_cases,
)
from e2e_real_cases import (
    expand_real_cases_with_llm,
    load_manifest,
    load_real_cases,
    resolve_sender_phone,
    validate_real_cases,
)

# Reconfigure stdout to use UTF-8 on Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

TEST_CLIENT_PHONE = "5491133333333"
TEST_SELLER_PHONE = os.getenv("E2E_SELLER_PHONE")

# The default set of 29 tools in the system
ALL_TOOLS = [
    "ping", "resolve_client", "search_products", "search_products_by_category",
    "get_product_by_code", "get_catalog_link", "list_promotions", "suggest_order_boost",
    "create_order", "list_recent_orders", "get_order_status", "get_open_order_status",
    "edit_order", "confirm_order", "create_distributor_ticket", "manage_contact_agenda",
    "register_client_location", "load_seller_order_text", "list_seller_clients",
    "get_seller_client_details", "set_seller_selected_client", "get_seller_selected_client",
    "get_open_order_status_for_client", "edit_order_for_client", "confirm_order_for_client",
    "suggest_order_boost_for_client", "clear_seller_context", "seller_help"
]

async def ensure_test_client(conn: asyncpg.Connection, schema: str) -> int:
    """
    Verifica que el cliente de pruebas 'suplai-platform-test' con teléfono '5491133333333'
    exista en el esquema de la distribuidora. Devuelve la lista_precios_id asignada.
    """
    row = await conn.fetchrow(
        f"SELECT lista_precios_id FROM {schema}.clients WHERE phone_number = $1 LIMIT 1",
        TEST_CLIENT_PHONE
    )
    if not row:
        raise ValueError(
            f"El cliente de pruebas 'suplai-platform-test' con número {TEST_CLIENT_PHONE} no existe en el esquema '{schema}'. "
            "Por favor, ejecute el healthcheck con el parámetro --fix-client para crearlo correctamente antes de correr el E2E."
        )
    print(f"[*] Cliente de prueba 'suplai-platform-test' verificado con éxito (Lista Precios ID: {row['lista_precios_id']}).")
    return row["lista_precios_id"]

async def resolve_client_id_by_identifier(
    conn: asyncpg.Connection, schema: str, client_identifier: str
) -> int | None:
    """Busca cliente por nombre o razón social (ILIKE)."""
    if not client_identifier:
        return None
    pattern = f"%{client_identifier.strip()}%"
    return await conn.fetchval(
        f"""
        SELECT id FROM {schema}.clients
        WHERE nombre ILIKE $1 OR razon_social ILIKE $1
        ORDER BY CASE
          WHEN nombre ILIKE $2 OR razon_social ILIKE $2 THEN 0
          ELSE 1
        END
        LIMIT 1
        """,
        pattern,
        client_identifier.strip(),
    )


async def clear_client_orders_by_id(conn: asyncpg.Connection, schema: str, client_id: int) -> None:
    await conn.execute(
        f"""
        DELETE FROM {schema}.items_pedido
        WHERE pedido_id IN (SELECT id FROM {schema}.pedidos WHERE cliente_id = $1)
        """,
        client_id,
    )
    await conn.execute(
        f"DELETE FROM {schema}.pedidos WHERE cliente_id = $1",
        client_id,
    )


async def clear_client_orders_by_identifier(
    conn: asyncpg.Connection, schema: str, client_identifier: str | None
) -> None:
    if not client_identifier:
        return
    client_id = await resolve_client_id_by_identifier(conn, schema, client_identifier)
    if not client_id:
        print(f"[WARN] No se encontró cliente '{client_identifier}' para limpiar pedidos.")
        return
    print(f"[*] Limpiando pedidos del cliente '{client_identifier}' (ID: {client_id})...")
    await clear_client_orders_by_id(conn, schema, client_id)


async def clear_session_context(conn: asyncpg.Connection, schema: str, session_phone: str) -> None:
    tenant_id = await conn.fetchval(
        "SELECT id::text FROM public.distribuidoras WHERE schema_name = $1",
        schema,
    )
    if not tenant_id:
        return
    conv_ids = await conn.fetch(
        "SELECT id FROM core.conversations WHERE tenant_id = $1::uuid AND session_id = $2",
        tenant_id,
        session_phone,
    )
    if not conv_ids:
        return
    ids = [int(r["id"]) for r in conv_ids]
    await conn.execute(
        """
        DELETE FROM core.followup_sequence_executions
        WHERE conversation_id = ANY($1::bigint[])
        """,
        ids,
    )
    await conn.execute(
        "DELETE FROM core.seller_context WHERE conversation_id = ANY($1::bigint[])",
        ids,
    )
    await conn.execute(
        "DELETE FROM core.conversation_events WHERE conversation_id = ANY($1::bigint[])",
        ids,
    )
    await conn.execute(
        "DELETE FROM core.conversations WHERE id = ANY($1::bigint[])",
        ids,
    )
    await conn.execute(
        "DELETE FROM core.message_buffers WHERE tenant_id = $1::uuid AND session_id = $2",
        tenant_id,
        session_phone,
    )
    print(f"[*] Contexto core limpiado para sesión {session_phone}.")


async def clear_journey_state(
    conn: asyncpg.Connection,
    schema: str,
    *,
    session_phone: str,
    client_identifier: str | None,
) -> None:
    await clear_client_orders_by_identifier(conn, schema, client_identifier)
    await clear_session_context(conn, schema, session_phone)
    try:
        backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
        conv_id = await conn.fetchval(
            "SELECT id FROM core.conversations WHERE session_id = $1 AND schema_name = $2 LIMIT 1",
            session_phone,
            schema,
        )
        if conv_id:
            url = f"{backend_url}/{schema}/conversaciones/{conv_id}/context"
            resp = requests.delete(url, timeout=30)
            if resp.status_code == 200:
                print(f"[*] Contexto API eliminado para conversación {conv_id}.")
    except Exception as e:
        print(f"[WARN] Error al limpiar contexto API de journey: {e}")


async def clear_test_client_orders(conn: asyncpg.Connection, schema: str):
    """
    Elimina los pedidos y carritos abiertos/históricos del cliente de prueba 'suplai-platform-test'
    para asegurar que cada ejecución de E2E comience con un estado completamente limpio.
    """
    client_id = await conn.fetchval(
        f"SELECT id FROM {schema}.clients WHERE phone_number = $1 LIMIT 1",
        TEST_CLIENT_PHONE
    )
    if client_id:
        print(f"[*] Limpiando pedidos previos del cliente de prueba '{TEST_CLIENT_PHONE}' (ID: {client_id}) en '{schema}'...")
        # Borrar items del pedido primero por FK
        await conn.execute(
            f"""
            DELETE FROM {schema}.items_pedido 
            WHERE pedido_id IN (SELECT id FROM {schema}.pedidos WHERE cliente_id = $1)
            """,
            client_id
        )
        # Borrar pedidos
        await conn.execute(
            f"DELETE FROM {schema}.pedidos WHERE cliente_id = $1",
            client_id
        )

async def fetch_catalog_sample(conn: asyncpg.Connection, schema: str, lista_precios_id: int) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Recupera una muestra de productos activos con stock y categorías del catálogo para alimentar el LLM.
    """
    # 1. Productos con stock que tienen precio en la lista de precios del cliente de prueba
    prod_rows = await conn.fetch(
        f"""
        SELECT p.product_code, p.nombre, p.stock, p.unidades_por_bulto, p.descripcion, p.unidad_minima_de_venta
        FROM {schema}.productos p
        JOIN {schema}.precios_productos pp ON p.product_code = pp.product_code
        WHERE p.en_catalogo = true AND p.stock > 0 AND pp.lista_precios_id = $1
        ORDER BY p.rotacion_index DESC NULLS LAST
        LIMIT 15
        """,
        lista_precios_id
    )
    products = [dict(r) for r in prod_rows]
    
    # 2. Categorías (tags)
    tag_rows = await conn.fetch(
        f"SELECT id, name, description FROM {schema}.tags ORDER BY name LIMIT 15"
    )
    tags = [dict(r) for r in tag_rows]
    
    return products, tags


async def fetch_valid_catalog_skus(
    conn: asyncpg.Connection, schema: str, lista_precios_id: int | None = None
) -> set[str]:
    """SKUs activos con stock. Si hay lista_precios_id, filtra por precio en esa lista."""
    if lista_precios_id is not None:
        rows = await conn.fetch(
            f"""
            SELECT p.product_code
            FROM {schema}.productos p
            JOIN {schema}.precios_productos pp ON p.product_code = pp.product_code
            WHERE p.en_catalogo = true AND p.stock > 0 AND pp.lista_precios_id = $1
            """,
            lista_precios_id,
        )
    else:
        rows = await conn.fetch(
            f"""
            SELECT product_code FROM {schema}.productos
            WHERE en_catalogo = true AND stock > 0
            """
        )
    return {r["product_code"] for r in rows}

def call_openai_chat(system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
    if not OPENAI_API_KEY:
        print("[FAIL] Falta OPENAI_API_KEY en el archivo .env.")
        sys.exit(1)
        
    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2
    }
    
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
        
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[FAIL] Error llamando a OpenAI: {e}")
        raise e

def repair_test_suite(test_cases: list, products: list) -> list:
    """
    Completa expected_skus cuando el LLM genera menos de los requeridos (tipologías 2 y 4).
    Evita reintentos fallidos en modo secuencial sin relajar la validación posterior.
    """
    import re

    by_code = {p["product_code"]: p for p in products}

    def _words(name: str) -> set[str]:
        clean = re.sub(r"[^\w\s]", " ", (name or "").lower())
        return {w for w in clean.split() if len(w) > 2}

    def _pick_related(extra_pool: list, anchor_codes: list[str]) -> str | None:
        anchor_words: set[str] = set()
        for code in anchor_codes:
            prod = by_code.get(code)
            if prod:
                anchor_words |= _words(prod.get("nombre", ""))
        if anchor_words:
            for p in extra_pool:
                code = p["product_code"]
                if code in anchor_codes:
                    continue
                if anchor_words & _words(p.get("nombre", "")):
                    return code
        for p in extra_pool:
            if p["product_code"] not in anchor_codes:
                return p["product_code"]
        return None

    for idx, case in enumerate(test_cases):
        if not isinstance(case, dict):
            continue
        case_id = idx + 1
        if case_id not in (2, 4):
            continue
        skus = list(case.get("expected_skus") or [])
        while len(skus) < 2:
            extra = _pick_related(products, skus)
            if not extra or extra in skus:
                break
            skus.append(extra)
        case["expected_skus"] = skus
    return test_cases


def validate_test_suite(test_cases: list, valid_skus: set, valid_tools: set, products: list, seller: bool) -> list[str]:
    """
    Valida de forma determinista que los casos de prueba generados por el LLM
    tengan la estructura correcta y utilicen únicamente SKUs y tools existentes.
    También valida que el mensaje del test case mencione los productos reales
    correspondientes a los SKUs esperados y que se esperen las herramientas
    adecuadas según la tipología de prueba y el perfil (vendedor vs cliente).
    """
    import re
    errors = []
    if not isinstance(test_cases, list):
        errors.append("La propiedad 'test_cases' debe ser una lista.")
        return errors
        
    if len(test_cases) != 10:
        errors.append(f"Se esperaban exactamente 10 casos de prueba, se generaron {len(test_cases)}.")

    stop_words = {"de", "del", "la", "las", "el", "los", "un", "una", "unos", "unas", "con", "sin", "y", "en", "para", "por", "a", "al", "o", "x"}

    for idx, case in enumerate(test_cases):
        prefix = f"Caso [{idx+1}]:"
        if not isinstance(case, dict):
            errors.append(f"{prefix} No es un objeto JSON válido.")
            continue
            
        for field in ["id", "name", "message", "expected_skus", "expected_behavior", "expected_tools"]:
            if field not in case:
                errors.append(f"{prefix} Falta el campo requerido '{field}'.")
        
        # Validar ID secuencial
        cid = case.get("id")
        if not isinstance(cid, int) or cid != idx + 1:
            errors.append(f"{prefix} El 'id' debe ser el entero {idx + 1}, obtenido: {cid}.")

        # Validar campos string no vacíos
        for str_field in ["name", "message", "expected_behavior"]:
            val = case.get(str_field)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"{prefix} El campo '{str_field}' debe ser un string no vacío.")

        # Validar SKUs (si hay alguno provisto)
        expected_skus = case.get("expected_skus", [])
        if isinstance(expected_skus, list):
            case_id = idx + 1
            # Ciertas tipologías requieren SKUs reales
            if case_id in [1, 3, 5, 6, 7, 8] and len(expected_skus) < 1:
                errors.append(f"{prefix} Tipología {case_id} requiere al menos 1 SKU esperado en 'expected_skus'.")
            elif case_id in [2, 4] and len(expected_skus) < 2:
                errors.append(f"{prefix} Tipología {case_id} requiere al menos 2 SKUs esperados en 'expected_skus'.")
            elif case_id in [10] and len(expected_skus) != 0:
                errors.append(f"{prefix} Tipología 10 (Onboarding) no debe contener SKUs esperados.")

            for sku in expected_skus:
                if not isinstance(sku, str):
                    errors.append(f"{prefix} El SKU '{sku}' en 'expected_skus' debe ser un string.")
                    continue
                if sku not in valid_skus:
                    errors.append(f"{prefix} SKU alucinado '{sku}' no existe en el catálogo activo.")
                else:
                    # Validar que el mensaje mencione al producto real correspondiente
                    # Solo aplicamos esta validación estricta para tipologías específicas donde el producto se pide por nombre o código.
                    if case_id in [1, 2, 3, 6, 7]:
                        prod = next((p for p in products if p["product_code"] == sku), None)
                        if prod:
                            msg_lower = case.get("message", "").lower()
                            sku_lower = sku.lower()
                            prod_name_lower = prod.get("nombre", "").lower()
                            
                            # Quitar puntuación y caracteres especiales del nombre del producto
                            clean_name = re.sub(r'[^\w\s]', ' ', prod_name_lower)
                            words = [w.strip() for w in clean_name.split() if len(w.strip()) > 2 and w.strip() not in stop_words]
                            
                            # Match por código o por alguna palabra significativa del nombre
                            has_code = sku_lower in msg_lower
                            has_name_word = any(w in msg_lower for w in words) if words else False
                            
                            if not (has_code or has_name_word):
                                errors.append(
                                    f"{prefix} El mensaje simulado no parece referenciar al producto "
                                    f"esperado '{prod.get('nombre')}' (SKU: {sku})."
                                )
        else:
            errors.append(f"{prefix} 'expected_skus' debe ser una lista.")
            
        # Validar tools
        expected_tools = case.get("expected_tools", [])
        if isinstance(expected_tools, list):
            case_id = idx + 1
            if case_id != 10 and len(expected_tools) < 1:
                errors.append(f"{prefix} Requiere al menos 1 herramienta esperada en 'expected_tools'.")
                
            for tool in expected_tools:
                if tool not in valid_tools:
                    errors.append(f"{prefix} Tool inválida '{tool}' no existe en el sistema.")

            # Validar herramientas específicas esperadas por tipología y rol
            if case_id == 1:
                # Búsqueda directa
                if "search_products" not in expected_tools:
                    errors.append(f"{prefix} Debe esperar la herramienta 'search_products' para búsqueda directa.")
            elif case_id == 2:
                # Pedido texto libre (multi-ítem)
                order_tools = ["load_seller_order_text", "edit_order_for_client"] if seller else ["create_order", "edit_order"]
                if not any(t in expected_tools for t in order_tools):
                    errors.append(f"{prefix} Debe esperar alguna tool de pedido ({', '.join(order_tools)}) para pedido multi-ítem.")
            elif case_id == 3:
                # Consulta de precio
                price_tools = ["search_products", "get_product_by_code"]
                if not any(t in expected_tools for t in price_tools):
                    errors.append(f"{prefix} Debe esperar 'search_products' o 'get_product_by_code' para consulta de precio.")
            elif case_id == 4:
                # Ambigüedad de catálogo
                if "search_products" not in expected_tools:
                    errors.append(f"{prefix} Debe esperar la herramienta 'search_products' para desambiguar productos por nombre.")
            elif case_id == 5:
                # Atributo semántico
                semantic_tools = ["search_products", "search_products_by_category"]
                if not any(t in expected_tools for t in semantic_tools):
                    errors.append(f"{prefix} Debe esperar 'search_products' o 'search_products_by_category' para búsqueda semántica/atributo.")
            elif case_id == 6:
                # Producto por código
                code_tools = ["get_product_by_code", "create_order", "load_seller_order_text"]
                if not any(t in expected_tools for t in code_tools):
                    errors.append(f"{prefix} Debe esperar una tool de código o pedido ({', '.join(code_tools)}) para producto por código.")
            elif case_id == 8:
                # Sugerencia / boost (cross-sell)
                boost_tool = "suggest_order_boost_for_client" if seller else "suggest_order_boost"
                if boost_tool not in expected_tools:
                    errors.append(f"{prefix} Debe esperar la herramienta '{boost_tool}' para sugerencias de cross-sell.")
            elif case_id == 9:
                # Confirmación de pedido (Checkout)
                confirm_tools = ["confirm_order_for_client"] if seller else ["confirm_order"]
                if not any(t in expected_tools for t in confirm_tools):
                    errors.append(f"{prefix} Debe esperar la herramienta '{confirm_tools[0]}' para confirmación de pedido.")
        else:
            errors.append(f"{prefix} 'expected_tools' debe ser una lista.")
            
    return errors

def generate_test_suite(schema: str, products: List[Dict[str, Any]], tags: List[Dict[str, Any]], seller: bool, sequential: bool) -> List[Dict[str, Any]]:
    """
    Llama a OpenAI para generar 10 casos de prueba conversacionales basados en los productos y categorías reales.
    Utiliza validación determinista y reintento en caso de fallas.
    """
    print("[*] Generando suite de pruebas personalizado usando OpenAI...")
    
    products_txt = json.dumps(products, indent=2, ensure_ascii=False)
    tags_txt = json.dumps(tags, indent=2, ensure_ascii=False)
    
    actor_str = "Vendedor / Asistente de Ventas" if seller else "Cliente Final (comprador de negocio)"
    
    if sequential:
        flow_desc = """IMPORTANTE: Generarás un flujo secuencial coordinado para las pruebas. Los casos del 1 al 9 ocurren dentro del mismo chat/pedido de forma consecutiva, por lo que cada mensaje es una continuación lógica del turno anterior. 
Para evitar falsos fallos por ambigüedad de nombre, asegúrate de que cuando el usuario se refiera a un producto específico para agregarlo o consultar su precio (Casos 1, 2, 3, 6, 7, 8), mencione un nombre comercial lo suficientemente específico y completo (o el código SKU directo) de modo que el agente pueda mapearlo de forma unívoca a un único producto del catálogo provisto. Evita usar términos demasiado cortos o genéricos compartidos por múltiples productos.

Línea temporal secuencial que DEBES seguir estrictamente:
1. Búsqueda directa por nombre comercial: El usuario saluda y busca el producto A. Usar un nombre de producto específico y único en el catálogo.
   - expected_tools: ["search_products"]
   - expected_skus: [SKU de A]
2. Pedido en texto libre (multi-ítem): El usuario pide agregar 2 unidades de A y 3 unidades de un producto B de tu catálogo a su pedido, mencionando los nombres específicos completos para evitar ambigüedades.
   - expected_tools: ["create_order"], ["edit_order"], ["load_seller_order_text"], ["edit_order_for_client"] o ["load_seller_order_text"]
   - expected_skus: [SKU de A, SKU de B]
3. Consulta de precio: El usuario pregunta el precio de un tercer producto C de tu catálogo sin intención de comprarlo por ahora.
   - expected_tools: ["search_products"] o ["get_product_by_code"]
   - expected_skus: [SKU de C]
4. Ambigüedad de catálogo: El usuario pide agregar un producto de forma vaga (ej. usando un término general como la marca o tipo sin especificar la variedad exacta) de modo que coincida con al menos 2 SKUs en el catálogo. El bot debe desambiguar.
   - expected_tools: ["search_products"]
   - expected_skus: [Al menos 2 SKUs del catálogo que compartan el término vago]
5. Atributo semántico / Categoría: El usuario busca productos de una categoría del catálogo. DEBES elegir y usar uno de los nombres de categorías/tags reales que se te proveen en la lista de tags. No uses términos ausentes de la lista de tags para evitar ambigüedades.
   - expected_tools: ["search_products"] o ["search_products_by_category"]
   - expected_skus: [Al menos 1 SKU de producto que cumpla con el tag seleccionado]
6. Producto por código: El usuario pide agregar un producto D usando su product_code SKU directo de forma explícita (ej. "cargame 12 unidades del código [SKU de D]").
   - expected_tools: ["get_product_by_code"], ["create_order"], ["load_seller_order_text"] o ["load_seller_order_text"]
   - expected_skus: [SKU de D]
7. Formato o empaque distinto: El usuario pide un producto E en una presentación de empaque específica (ej. "caja cerrada de [Nombre de E]" o "bulto de [Nombre de E]"), indicando el nombre comercial muy detallado de E para que no haya confusión.
   - expected_tools: ["search_products"], ["get_product_by_code"], ["create_order"] o ["load_seller_order_text"]
   - expected_skus: [SKU de E]
8. Sugerencia / Acompañamiento: El usuario pregunta qué recomendás para acompañar, maridar o complementar el producto A que cargó al inicio de la conversación.
   - expected_tools: ["suggest_order_boost"] o ["suggest_order_boost_for_client"]
   - expected_skus: [SKU de A]
9. Confirmación de pedido (Checkout): El usuario decide que el carrito está listo y pide explícitamente finalizar la compra y confirmar el pedido.
   - expected_tools: ["confirm_order"] o ["confirm_order_for_client"]
   - expected_skus: [] (lista vacía)
10. Teléfono no registrado (Onboarding): Un cliente distinto saluda desde un número de teléfono no registrado. (Este caso es independiente del flujo anterior).
    - expected_tools: [] (lista vacía, ya que resolve_client puede estar desactivado en el esquema)
    - expected_skus: [] (lista vacía)
"""
    else:
        flow_desc = """IMPORTANTE: Generarás 10 casos de prueba completamente independientes y autónomos. Cada uno asume que es el primer mensaje en una sesión nueva y limpia.
Para evitar falsos fallos por ambigüedad de nombre, asegúrate de que cuando el usuario se refiera a un producto específico para agregarlo o consultar su precio (Casos 1, 2, 3, 6, 7, 8), mencione un nombre comercial lo suficientemente específico y completo (o el código SKU directo) de modo que el agente pueda mapearlo de forma unívoca a un único producto del catálogo provisto. Evita usar términos demasiado cortos o genéricos compartidos por múltiples productos.

Tipologías de los 10 casos:
1. Búsqueda directa por nombre comercial: Intención clara de buscar un producto por su nombre comercial real específico.
   - expected_tools: Debe contener exactamente ["search_products"].
   - expected_skus: Al menos 1 SKU real. El mensaje de texto DEBE mencionar claramente el nombre o parte del nombre de ese producto.
2. Pedido en texto libre (multi-ítem): Mensaje informal pidiendo comprar/cargar al menos 2 productos con cantidades (ej: bultos, botellas, unidades), indicando nombres comerciales muy específicos para evitar ambigüedades.
   - expected_tools: ["create_order"], ["edit_order"], ["load_seller_order_text"], ["edit_order_for_client"] o ["load_seller_order_text"].
   - expected_skus: Al menos 2 SKUs reales. El mensaje de texto DEBE mencionar los nombres de ambos productos.
3. Consulta de precio: Pregunta sobre el precio o valor de un producto (ej. "¿Cuánto cuesta...?"), usando el nombre comercial específico.
   - expected_tools: ["search_products"] o ["get_product_by_code"].
   - expected_skus: Al menos 1 SKU real. El mensaje de texto DEBE mencionar el nombre de ese producto.
4. Ambigüedad de catálogo: Pedir un producto de forma muy vaga (ej. usando la marca o el tipo genérico sin especificar variedad) de modo que coincida con al menos 2 SKUs reales en el catálogo provisto (que compartan un término similar en sus nombres).
   - expected_tools: Debe contener exactamente ["search_products"].
   - expected_skus: Al menos 2 SKUs reales que compartan ese término vago.
5. Atributo semántico / Categoría: Búsqueda por un tag o categoría real provisto en la lista de tags. No uses términos ausentes de la lista de tags para evitar ambigüedades.
   - expected_tools: ["search_products"] o ["search_products_by_category"].
   - expected_skus: Al menos 1 SKU real de un producto que comparta el tag seleccionado.
6. Producto por código: Pedir o consultar usando el product_code / SKU directo (ej. "Cargá el código [SKU] x 12 unidades").
   - expected_tools: ["get_product_by_code"], ["create_order"], ["load_seller_order_text"] o ["load_seller_order_text"].
   - expected_skus: Al menos 1 SKU real. El mensaje de texto DEBE contener exactamente el código SKU en mayúsculas.
7. Formato o empaque distinto: Pedir el producto en un formato específico (ej. "caja", "botella", "pack"), especificando el nombre completo del producto de forma precisa.
   - expected_tools: ["search_products"], ["get_product_by_code"], ["create_order"] o ["load_seller_order_text"].
   - expected_skus: Al menos 1 SKU real. El mensaje de texto DEBE mencionar el nombre del producto y el empaque.
8. Sugerencia / Acompañamiento: Preguntar qué recomendación da para un producto base (cross-sell), mencionando el nombre comercial de dicho producto de manera específica.
   - expected_tools: ["suggest_order_boost"] o ["suggest_order_boost_for_client"].
   - expected_skus: Al menos 1 SKU real del producto base.
9. Confirmación de pedido (Checkout): El usuario decide cerrar el pedido actual y finalizar la compra.
   - expected_tools: ["confirm_order"] o ["confirm_order_for_client"].
   - expected_skus: [] (lista vacía).
10. Teléfono no registrado (Onboarding): Mensaje simple de saludo o inicio desde un teléfono no registrado.
    - expected_tools: [] (lista vacía, ya que resolve_client puede estar desactivado en el esquema).
    - expected_skus: [] (lista vacía).
"""

    system_prompt = f"""Sos un analista de testing de software experto en el ecosistema Suplai Sales en Argentina.
Tu objetivo es generar exactamente 10 casos de prueba conversacionales para validar que el agente del distribuidor interprete correctamente las intenciones del usuario final.

El perfil del remitente de los mensajes es: {actor_str}.

{flow_desc}

Responde ÚNICAMENTE con un JSON que contenga la propiedad "test_cases" que es un array de 10 objetos con la siguiente estructura:
{{
  "id": (int, 1 a 10),
  "name": (string, nombre corto del caso),
  "message": (string, el mensaje de texto en español simulado que enviará el usuario al bot),
  "expected_skus": (array de strings, los códigos SKU (product_code) que se esperan identificar, si aplica),
  "expected_behavior": (string, descripción de la respuesta y comportamiento esperados),
  "expected_tools": (array de strings, nombres de las tools que se espera que el agente llame, ej: ["search_products", "create_order"])
}}
"""

    user_prompt = f"""Aquí tienes los productos activos con stock del catálogo:
{products_txt}

Aquí tienes las categorías tags del catálogo:
{tags_txt}

Generá el suite de 10 pruebas en formato JSON. Sé extremadamente específico con los nombres y SKUs del catálogo real provisto. Evita alucinar códigos que no existan."""

    valid_skus = {p["product_code"] for p in products}
    valid_tools = set(ALL_TOOLS)
    
    for attempt in range(1, 4):
        try:
            content = call_openai_chat(system_prompt, user_prompt, json_mode=True)
            suite = json.loads(content)
            test_cases = repair_test_suite(suite.get("test_cases", []), products)
            errors = validate_test_suite(test_cases, valid_skus, valid_tools, products, seller)
            if not errors:
                print(f"[*] Suite de pruebas generado y validado con éxito (intento {attempt}).")
                return test_cases
            else:
                print(f"[WARN] El suite generado en el intento {attempt} falló la validación:")
                for err in errors:
                    print(f"  - {err}")
        except Exception as e:
            print(f"[WARN] Error en intento {attempt} al generar suite: {e}")
            
    raise ValueError("No se pudo generar un suite de pruebas validado de forma determinista después de 3 intentos.")


def build_test_suite(
    schema: str,
    products: List[Dict[str, Any]],
    tags: List[Dict[str, Any]],
    seller: bool,
    sequential: bool,
    *,
    suite_mode: str = "generic",
    expand: int = 0,
    valid_skus: set[str] | None = None,
    journey_mode: str = "chained",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    suite_mode: generic | real | hybrid
    """
    meta: dict[str, Any] = {"suite_mode": suite_mode, "expand": expand, "source": "generic"}

    if suite_mode == "generic":
        return generate_test_suite(schema, products, tags, seller, sequential), meta

    if suite_mode == "journey":
        journey_manifest = load_journey_manifest(schema)
        isolated = journey_mode == "isolated"
        journeys = load_journeys(schema, isolated=isolated)
        sku_set = valid_skus if valid_skus is not None else {p["product_code"] for p in products}
        cases = flatten_journey_steps(journeys, journey_mode=journey_mode)
        errors = validate_journey_cases(cases, sku_set, set(ALL_TOOLS))
        if errors:
            raise ValueError("Journeys inválidos:\n" + "\n".join(f"  - {e}" for e in errors))
        if journey_manifest.get("profile") == "seller":
            seller = True
        return cases, {
            "suite_mode": "journey",
            "journey_mode": journey_mode,
            "journey_count": len(journeys),
            "step_count": len(cases),
            "manifest_profile": journey_manifest.get("profile"),
        }

    manifest = load_manifest(schema)
    if manifest.get("profile") == "seller":
        seller = True
    if manifest.get("sequential_default") and suite_mode in {"real", "hybrid"}:
        sequential = True

    real_cases = load_real_cases(schema)
    sku_set = valid_skus if valid_skus is not None else {p["product_code"] for p in products}
    errors = validate_real_cases(real_cases, sku_set, set(ALL_TOOLS))
    if errors:
        raise ValueError("Casos reales inválidos:\n" + "\n".join(f"  - {e}" for e in errors))

    expanded: list[dict[str, Any]] = []
    if expand > 0:
        print(f"[*] Generando {expand} variantes similares desde casos reales...")
        expanded = expand_real_cases_with_llm(
            schema=schema,
            real_cases=real_cases,
            products=products,
            tags=tags,
            seller=seller,
            extra_count=expand,
            call_openai_chat=call_openai_chat,
        )
        err2 = validate_real_cases(expanded, sku_set, set(ALL_TOOLS))
        if err2:
            print("[WARN] Variantes generadas con errores (se omiten las inválidas):")
            for e in err2:
                print(f"  - {e}")
            expanded = [c for c in expanded if not any(c.get("slug") in e for e in err2)]

    cases = real_cases + expanded
    if suite_mode == "hybrid":
        print("[*] Modo hybrid: agregando suite genérica de catálogo después de casos reales...")
        generic = generate_test_suite(schema, products, tags, seller, sequential)
        offset = len(cases)
        for g in generic:
            g = dict(g)
            g["id"] = offset + int(g["id"])
            g["source"] = "generic"
            cases.append(g)

    meta = {
        "suite_mode": suite_mode,
        "expand": expand,
        "source": "real",
        "real_count": len(real_cases),
        "generated_count": len(expanded),
        "manifest_profile": manifest.get("profile"),
    }
    return cases, meta

async def toggle_implementation_debug(conn: asyncpg.Connection, schema: str, enable: bool) -> dict | None:
    """
    Habilita o deshabilita la traza del laboratorio en el metadata del distribuidor.
    Retorna el metadata original para su restauración posterior.
    """
    row = await conn.fetchrow(
        "SELECT id, metadata FROM public.distribuidoras WHERE schema_name = $1",
        schema
    )
    if not row:
        return None
    
    dist_id = row["id"]
    meta_raw = row["metadata"]
    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else dict(meta_raw) if meta_raw else {}
    
    original_meta = json.loads(json.dumps(meta)) # deepcopy
    
    if enable:
        if "implementation_debug" not in meta:
            meta["implementation_debug"] = {}
        meta["implementation_debug"]["trace_enabled"] = True
    else:
        if "implementation_debug" in meta:
            meta["implementation_debug"]["trace_enabled"] = False
            
    await conn.execute(
        "UPDATE public.distribuidoras SET metadata = CAST($1 AS jsonb), updated_at = now() WHERE id = $2",
        json.dumps(meta), dist_id
    )
    return original_meta

async def restore_metadata(conn: asyncpg.Connection, schema: str, original_meta: dict):
    """
    Restaura el metadata original de la distribuidora.
    """
    await conn.execute(
        "UPDATE public.distribuidoras SET metadata = CAST($1 AS jsonb), updated_at = now() WHERE schema_name = $2",
        json.dumps(original_meta), schema
    )

async def get_agent_phone_number(conn: asyncpg.Connection, schema: str) -> str:
    phone = await conn.fetchval(
        "SELECT agent_phone_number FROM public.distribuidoras WHERE schema_name = $1",
        schema
    )
    if not phone:
        raise ValueError(f"No hay un número de teléfono asignado al agente en '{schema}'")
    return str(phone)

async def fetch_tool_trace(conn: asyncpg.Connection, schema: str, session_id: str, test_start_time: datetime) -> List[Dict[str, Any]]:
    """
    Busca en core.agent_turns y core.agent_tool_runs la ejecución de herramientas del último turno de esta sesión.
    """
    # Buscamos el último turno de la conversación del test
    turn = await conn.fetchrow(
        """
        SELECT id FROM core.agent_turns
        WHERE schema_name = $1 AND session_id = $2 AND created_at >= $3
        ORDER BY created_at DESC LIMIT 1
        """,
        schema, session_id, test_start_time
    )
    if not turn:
        return []
    
    turn_id = turn["id"]
    
    # Buscamos las ejecuciones de herramientas para este turno
    tool_rows = await conn.fetch(
        """
        SELECT tool_name, status, latency_ms, args_json, error_summary
        FROM core.agent_tool_runs
        WHERE turn_id = $1
        ORDER BY created_at ASC
        """,
        turn_id
    )
    return [dict(r) for r in tool_rows]

def send_message_to_agent(agent_phone: str, sender_phone: str, text: str) -> tuple[Dict[str, Any], float]:
    url = "https://agente-conversacional-multitenant-production.up.railway.app/webhook"
    
    payload = {
        "provider": "custom",
        "to_agent_phone": agent_phone,
        "from_user_id": sender_phone,
        "text": text,
        "timestamp": int(time.time()),
        "provider_message_id": str(uuid.uuid4())
    }
    
    start_time = time.perf_counter()
    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        response_data = resp.json()
    except Exception as e:
        response_data = {"error": str(e)}
        
    end_time = time.perf_counter()
    return response_data, (end_time - start_time)

def evaluate_test_case_result(case: Dict[str, Any], reply: str, tools_called: List[Dict[str, Any]], sequential: bool = False) -> tuple[bool, str]:
    """
    Llama a OpenAI para evaluar el resultado del caso de prueba a partir del mensaje del bot y las herramientas llamadas.
    """
    case_txt = json.dumps(case, indent=2, ensure_ascii=False)
    tools_txt = json.dumps(tools_called, indent=2, ensure_ascii=False)
    tools_names = [t.get("tool_name") for t in tools_called if t.get("tool_name")]

    journey_hint = ""
    if case.get("source") == "journey":
        journey_hint = f"""
JOURNEY E2E: Escenario '{case.get("journey_name")}' paso {case.get("journey_step")}/{case.get("journey_total_steps")} (modo {case.get("journey_mode")}).
"""
        if case.get("journey_mode") == "chained" and int(case.get("journey_step") or 1) > 1:
            journey_hint += """
Este paso corre ENCADENADO: el pedido y la conversación del journey ya existen desde pasos anteriores.
Es correcto usar edit_order_for_client / load_seller_order_text para ajustar cantidades sin recrear el pedido desde cero.
"""
        elif case.get("journey_mode") == "isolated":
            journey_hint += """
Este paso corre AISLADO: el mensaje es autocontenido (incluye contexto del pedido en el mismo turno si hace falta).
"""

    real_case_hint = ""
    if case.get("source") in {"real", "generated", "journey"}:
        any_tools = case.get("expected_tools_any") or []
        if any_tools:
            real_case_hint = f"""
CASO REAL / VARIANTE: Si se ejecutó al menos una de {any_tools}, no penalices por no haber usado otras tools equivalentes.
Tools ejecutadas: {tools_names}
"""
        if case.get("client_identifier"):
            real_case_hint += f"\nEl operador trabaja para el cliente: {case['client_identifier']}.\n"
        if case.get("client_id"):
            real_case_hint += f"Cliente esperado en BD: id={case['client_id']}.\n"
        if case.get("client_alias_recommended"):
            real_case_hint += f"Alias comercial recomendado (pendiente de implementación): '{case['client_alias_recommended']}' → {case.get('client_identifier', 'cliente esperado')}.\n"
        out_of_stock = case.get("expected_skus_out_of_stock") or []
        if out_of_stock:
            real_case_hint += f"""
STOCK ERP: Los SKUs {out_of_stock} tienen stock=0 en ERP. NO penalices si no se cargaron al pedido.
El agente DEBE avisar explícitamente que esos ítems quedaron fuera por falta de stock. Carga parcial con aviso = passed: true.
"""
    
    seq_context = ""
    if sequential:
        seq_context = """
IMPORTANTE - MODO SECUENCIAL:
Este test corre en modo SECUENCIAL. Esto significa que:
1. Las respuestas del bot pueden y deben acumular el historial de la conversación y productos agregados en turnos anteriores. Ver productos previos en la respuesta o resumen del pedido es correcto y ESPERADO. No penalices por esto.
2. Es correcto y esperado que para agregar productos a un pedido existente se llame a la herramienta 'edit_order' o 'edit_order_for_client' en lugar de 'create_order'. Ambas son correctas en este contexto.
"""
    else:
        seq_context = """
IMPORTANTE - MODO AISLADO:
Este test corre en modo AISLADO. Cada caso asume que es el primer mensaje de una sesión limpia. No debe haber productos previos en el pedido ni historial de conversación acumulado.
"""

    system_prompt = f"""Sos un auditor experto de agentes conversacionales inteligentes de ventas.
Tu trabajo es evaluar si el bot respondió satisfactoriamente el mensaje de prueba y si llamó a las herramientas adecuadas.

Vas a recibir:
1. El detalle del caso de prueba (mensaje enviado, SKUs esperados, comportamiento esperado, herramientas esperadas).
2. La respuesta textual del bot ('reply').
3. El trace real de herramientas llamadas en la base de datos ('tools_called').

{seq_context}
{journey_hint}
{real_case_hint}

Reglas de Evaluación:
- Si el caso esperaba cargar ítems al pedido (ej. create_order, edit_order, load_seller_order_text, edit_order_for_client o load_seller_order_text) y no se llamó a ninguna tool de carga, o fallaron, califica como passed: false.
- En el caso de desambiguación (Caso 4), si el bot lista las opciones de productos disponibles y le pide de alguna forma al usuario indicar cuál de ellos desea agregar o confirmar (ej: "Avisame si te interesa alguno y lo agregamos"), esto se considera una desambiguación conversacional correcta y debe ser aprobado (passed: true).
- Si el caso requería desambiguación (Caso 4) y el bot cargó un SKU directamente en el carrito sin preguntar ni listar opciones, califica como passed: false.
- Si la respuesta del bot es errónea, no responde a la intención o alucina SKUs que no estaban en catálogo, califica como passed: false.
- En caso de éxito o comportamiento conversacional coherente con las expectativas, califica como passed: true.

Responde ÚNICAMENTE con un JSON que contenga las llaves:
{{
  "passed": (boolean, true o false),
  "analysis": (string, justificación técnica detallada en español sobre por qué pasa o falla, analizando la respuesta y las herramientas ejecutadas)
}}
"""

    user_prompt = f"""CASO DE PRUEBA:
{case_txt}

RESPUESTA DEL AGENTE:
{reply}

HERRAMIENTAS REALMENTE EJECUTADAS:
{tools_txt}
"""

    content = call_openai_chat(system_prompt, user_prompt, json_mode=True)
    res = json.loads(content)
    return bool(res["passed"]), str(res["analysis"])

async def clear_conversation_context_db_and_api(conn: asyncpg.Connection, schema: str):
    """
    Limpia el contexto de la conversación del cliente de prueba tanto en la base de datos como en el backend.
    """
    try:
        conv_id = await conn.fetchval(
            "SELECT id FROM core.conversations WHERE session_id = $1 AND schema_name = $2 LIMIT 1",
            TEST_CLIENT_PHONE, schema
        )
        if conv_id:
            backend_url = os.getenv("BACKEND_URL", "https://web-production-f544f.up.railway.app").rstrip("/")
            url = f"{backend_url}/{schema}/conversaciones/{conv_id}/context"
            resp = requests.delete(url, timeout=30)
            if resp.status_code == 200:
                print(f"[*] Contexto de conversación {conv_id} eliminado exitosamente en el backend.")
            else:
                print(f"[WARN] No se pudo eliminar el contexto de conversación: HTTP {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[WARN] Error al limpiar contexto de conversación: {e}")

def _should_cleanup_journey_step(
    case: dict[str, Any],
    prev_case: dict[str, Any] | None,
    journey_mode: str,
) -> bool:
    if journey_mode == "isolated":
        return True
    if not prev_case or prev_case.get("journey_slug") != case.get("journey_slug"):
        return True
    return False


async def run_e2e_suite(
    schema: str,
    seller: bool,
    limit: Optional[int],
    sequential: bool = False,
    *,
    suite_mode: str = "generic",
    expand: int = 0,
    journey_mode: str = "chained",
):
    db_url = os.getenv("SUPABASE_DB_URL")
    conn = await asyncpg.connect(db_url)
    
    try:
        # 1. Asegurar cliente de prueba, configuraciones y limpiar estado inicial
        print("[*] Asegurando cliente de pruebas 'suplai-platform-test'...")
        lista_precios_id = await ensure_test_client(conn, schema)
        await clear_test_client_orders(conn, schema)
        await clear_conversation_context_db_and_api(conn, schema)
        
        # 2. Obtener productos y tags del catálogo
        products, tags = await fetch_catalog_sample(conn, schema, lista_precios_id)
        if not products:
            print("[FAIL] El catálogo del esquema no tiene productos activos con stock. Healthcheck fallido.")
            sys.exit(1)

        catalog_skus = await fetch_valid_catalog_skus(
            conn,
            schema,
            lista_precios_id=None if suite_mode in {"real", "hybrid", "journey"} else lista_precios_id,
        )
            
        # 3. Generar casos de prueba
        test_cases, suite_meta = build_test_suite(
            schema, products, tags, seller, sequential,
            suite_mode=suite_mode, expand=expand,
            valid_skus=catalog_skus if suite_mode in {"real", "hybrid", "journey"} else None,
            journey_mode=journey_mode,
        )
        if suite_mode == "journey":
            journey_manifest = load_journey_manifest(schema)
            if journey_manifest.get("profile") == "seller":
                seller = True
            if seller and not TEST_SELLER_PHONE and not journey_manifest.get("sender_phone"):
                print(
                    "[FAIL] Modo seller con journeys requiere E2E_SELLER_PHONE en .env "
                    "o sender_phone en manifest.json."
                )
                sys.exit(1)
        elif suite_mode in {"real", "hybrid"}:
            manifest = load_manifest(schema)
            if manifest.get("profile") == "seller":
                seller = True
            if manifest.get("sequential_default"):
                sequential = True
            if seller and not TEST_SELLER_PHONE and not manifest.get("sender_phone"):
                print(
                    "[FAIL] Modo seller con casos reales requiere E2E_SELLER_PHONE en .env "
                    "o sender_phone en manifest.json (vendedor registrado en el tenant)."
                )
                sys.exit(1)
        if limit:
            test_cases = test_cases[:limit]
            print(f"[*] Modo limit activo: reduciendo suite de pruebas a {limit} casos.")
            
        # 4. Obtener teléfono del agente
        agent_phone = await get_agent_phone_number(conn, schema)
        
        # 5. Habilitar la traza de laboratorio
        print("[*] Habilitando temporalmente 'implementation_debug.trace_enabled'...")
        original_meta = await toggle_implementation_debug(conn, schema, enable=True)
        
        print("\n" + "=" * 60)
        print("INICIANDO EJECUCIÓN DE PRUEBAS")
        print("=" * 60)
        
        results_report = []
        prev_case: dict[str, Any] | None = None
        journey_mode_effective = suite_meta.get("journey_mode", "chained")
        manifest = (
            load_journey_manifest(schema) if suite_mode == "journey"
            else load_manifest(schema) if suite_mode in {"real", "hybrid"} else {}
        )
        
        for idx, case in enumerate(test_cases, start=1):
            if suite_mode == "journey":
                if _should_cleanup_journey_step(case, prev_case, journey_mode_effective):
                    sender_for_cleanup = resolve_sender_phone(
                        case,
                        manifest,
                        default_client_phone=TEST_CLIENT_PHONE,
                        default_seller_phone=TEST_SELLER_PHONE,
                        seller_mode=seller,
                    )
                    print(
                        f"[*] Journey ({journey_mode_effective}): limpiando estado antes de "
                        f"'{case.get('journey_name')}' paso {case.get('journey_step')}..."
                    )
                    await clear_journey_state(
                        conn,
                        schema,
                        session_phone=sender_for_cleanup,
                        client_identifier=case.get("client_identifier"),
                    )
                    await asyncio.sleep(0.5)
            elif not sequential:
                # Si no es secuencial, limpiamos el estado antes de cada caso para asegurar aislamiento total
                print(f"[*] Aislamiento activo: Limpiando carrito y contexto antes de '{case['name']}'...")
                if suite_mode in {"real", "hybrid"} and case.get("client_identifier"):
                    sender_for_cleanup = resolve_sender_phone(
                        case,
                        manifest,
                        default_client_phone=TEST_CLIENT_PHONE,
                        default_seller_phone=TEST_SELLER_PHONE,
                        seller_mode=seller,
                    )
                    await clear_journey_state(
                        conn,
                        schema,
                        session_phone=sender_for_cleanup,
                        client_identifier=case.get("client_identifier"),
                    )
                else:
                    await clear_test_client_orders(conn, schema)
                    await clear_conversation_context_db_and_api(conn, schema)
                await asyncio.sleep(0.5)

            print(f"\n[{idx}/{len(test_cases)}] Ejecutando caso: {case['name']}")
            print(f"    Mensaje: '{case['message']}'")
            
            # El caso 10 genérico simula un teléfono no registrado
            is_unregistered = (
                suite_mode == "generic"
                and case.get("id") == 10
                and case.get("source") != "real"
            )
            sender_phone = resolve_sender_phone(
                case,
                manifest,
                default_client_phone=TEST_CLIENT_PHONE,
                default_seller_phone=TEST_SELLER_PHONE,
                seller_mode=seller,
            ) if suite_mode in {"real", "hybrid", "journey"} else (
                f"54999{int(time.time()) % 100000000:08d}" if is_unregistered else TEST_CLIENT_PHONE
            )
            
            # Marcamos tiempo de inicio para buscar los logs después en PostgreSQL
            test_start_time = datetime.now(timezone.utc)
            
            # Envío de webhook y medición de latencia
            response_data, exec_time = send_message_to_agent(agent_phone, sender_phone, case['message'])
            reply = response_data.get("echo", "")
            
            print(f"    Respuesta: {reply[:100]}..." if len(reply) > 100 else f"    Respuesta: {reply}")
            print(f"    Latencia Webhook: {exec_time:.2f} segundos")
            
            # Pequeño delay y consulta de traza de tools en Supabase
            await asyncio.sleep(1)
            tools_called = await fetch_tool_trace(conn, schema, sender_phone, test_start_time)
            
            print(f"    Tools llamadas: {len(tools_called)}")
            for t in tools_called:
                print(f"      - {t['tool_name']} (Status: {t['status']}, Latency: {t['latency_ms']:.1f}ms)")
                
            # Evaluación con LLM
            eval_sequential = sequential or (
                suite_mode == "journey"
                and journey_mode_effective == "chained"
                and int(case.get("journey_step") or 1) > 1
            )
            passed, analysis = evaluate_test_case_result(case, reply, tools_called, eval_sequential)
            status_str = "PASS" if passed else "FAIL"
            print(f"    Resultado: {status_str}")
            print(f"    Análisis: {analysis}")
            
            results_report.append({
                "case": case,
                "reply": reply,
                "latency": exec_time,
                "tools": tools_called,
                "passed": passed,
                "analysis": analysis
            })
            prev_case = case
            
        # 6. Restaurar metadata del distribuidor
        print("\n[*] Restaurando 'implementation_debug.trace_enabled' original...")
        if original_meta is not None:
            await restore_metadata(conn, schema, original_meta)
            
        # 7. Escribir reporte markdown
        write_markdown_report(schema, seller, results_report, suite_meta)
        
    finally:
        await conn.close()

def write_markdown_report(schema: str, seller: bool, results: List[Dict[str, Any]], suite_meta: Optional[dict[str, Any]] = None):
    report_dir = f"implementacion/{schema}/outputs"
    os.makedirs(report_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = ""
    if suite_meta.get("suite_mode") == "journey":
        suffix = f"_{suite_meta.get('journey_mode', 'chained')}"
    filename = os.path.join(report_dir, f"reporte_e2e_{timestamp}{suffix}.md")
    
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    avg_latency = sum(r["latency"] for r in results) / total_count if total_count > 0 else 0
    
    # 8. Analizar posibles optimizaciones proactivas
    latency_warnings = []
    tool_failures = []
    
    for r in results:
        # Latencia webhook > 8s
        if r["latency"] > 8.0:
            latency_warnings.append(f"Caso '{r['case']['name']}' superó 8s de latencia (Medido: {r['latency']:.2f}s).")
        # Latencias de herramientas individuales > 3s
        for t in r["tools"]:
            if t["latency_ms"] > 3000:
                latency_warnings.append(f"La herramienta '{t['tool_name']}' demoró {t['latency_ms']/1000:.2f}s en '{r['case']['name']}'.")
            if t["status"] == "error":
                tool_failures.append(f"La herramienta '{t['tool_name']}' falló en '{r['case']['name']}': {t['error_summary']}")
                
    # Proponer optimización de tools
    optimization_suggestions = []
    if latency_warnings or tool_failures:
        optimization_suggestions.append("### ⚡ Recomendaciones de Optimización Proactivas:")
        if tool_failures:
            optimization_suggestions.append("#### 🛠️ Errores detectados:")
            for f in tool_failures:
                optimization_suggestions.append(f"- {f}")
        if latency_warnings:
            optimization_suggestions.append("#### 🐢 Cuellos de botella de latencia:")
            for w in latency_warnings:
                optimization_suggestions.append(f"- {w}")
            optimization_suggestions.append("\n*Recomendación:* Evalúe si hay herramientas activadas innecesarias y desactívelas mediante `healthcheck_schema.py` con `--fix-tools`.")
            
    if not results:
        optimization_suggestions.append("No se ejecutaron pruebas.")
        
    suite_meta = suite_meta or {}
    suite_line = ""
    if suite_meta.get("suite_mode") == "journey":
        suite_line = (
            f"- **Suite:** journey — modo **{suite_meta.get('journey_mode', 'chained')}** "
            f"({suite_meta.get('journey_count', 0)} journeys, "
            f"{suite_meta.get('step_count', 0)} pasos)\n"
        )
    elif suite_meta.get("suite_mode") and suite_meta["suite_mode"] != "generic":
        suite_line = (
            f"- **Suite:** {suite_meta['suite_mode']} "
            f"(reales: {suite_meta.get('real_count', 0)}, "
            f"generados: {suite_meta.get('generated_count', 0)})\n"
        )

    md_content = f"""# Reporte de Testing E2E — Agente Suplai

Distribuidora: **{schema}**
Perfil de prueba: **{"Asistente de Vendedor" if seller else "Cliente Final"}**
Fecha de ejecución: **{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**
{suite_line}
## 📊 Resumen Ejecutivo
- **Resultado Global:** {passed_count}/{total_count} Aprobados ({(passed_count/total_count)*100:.1f}%)
- **Latencia Promedio:** {avg_latency:.2f} segundos

| Caso # | Nombre del Caso | Aprobado | Latencia (s) | Tools llamadas |
| :--- | :--- | :---: | :---: | :--- |
"""

    for r in results:
        status_icon = "🟢 PASS" if r["passed"] else "🔴 FAIL"
        tools_str = ", ".join(f"`{t['tool_name']}`" for t in r["tools"]) if r["tools"] else "*Ninguna*"
        source_tag = ""
        if r["case"].get("source") == "real":
            source_tag = " `[real]`"
        elif r["case"].get("source") == "generated":
            source_tag = " `[generado]`"
        elif r["case"].get("source") == "journey":
            source_tag = f" `[journey p{r['case'].get('journey_step')}]`"
        md_content += f"| {r['case']['id']} | {r['case']['name']}{source_tag} | {status_icon} | {r['latency']:.2f} | {tools_str} |\n"

    md_content += "\n## 📝 Detalle de Casos de Prueba\n"
    
    for r in results:
        status_icon = "🟢 PASS" if r["passed"] else "🔴 FAIL"
        tools_txt = ""
        if r["tools"]:
            tools_txt = "\n**Tools ejecutadas:**\n"
            for t in r["tools"]:
                tools_txt += f"- `{t['tool_name']}` ({t['latency_ms']:.0f}ms) - Status: `{t['status']}`\n"
                if t["error_summary"]:
                    tools_txt += f"  - Error: *{t['error_summary']}*\n"
                    
        md_content += f"""
---

### Caso {r['case']['id']}: {r['case']['name']} ({status_icon})
- **Origen:** {r['case'].get('source', 'generic')}{f" — fixture `{r['case'].get('fixture_dir')}`" if r['case'].get('fixture_dir') else ""}{f" — journey `{r['case'].get('journey_slug')}` paso {r['case'].get('journey_step')}/{r['case'].get('journey_total_steps')}" if r['case'].get('source') == 'journey' else ""}
- **Mensaje enviado:** *"{r['case']['message']}"*
- **Comportamiento esperado:** {r['case']['expected_behavior']}
- **Respuesta del bot:**
  > "{r['reply']}"
- **Latencia:** {r['latency']:.2f}s
{tools_txt}
- **Análisis de Auditoría:**
  {r['analysis']}
"""

    if optimization_suggestions:
        md_content += "\n\n" + "\n".join(optimization_suggestions)
        
    with open(filename, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    print("\n" + "=" * 60)
    print("EJECUCIÓN DE PRUEBAS COMPLETADA CON ÉXITO")
    print(f"Reporte generado en: {filename}")
    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="Script para ejecutar suite de pruebas conversacionales E2E en Suplai.")
    parser.add_argument("--schema", required=True, help="Esquema de la distribuidora (ej: vadra)")
    parser.add_argument("--seller", action="store_true", help="Ejecutar pruebas del perfil asistente de vendedor")
    parser.add_argument("--limit", type=int, help="Límite de casos de prueba a ejecutar (para smoke test rápido)")
    parser.add_argument("--sequential", action="store_true", help="Ejecutar pruebas de forma secuencial (manteniendo el estado del carrito y conversación)")
    parser.add_argument(
        "--suite",
        choices=["generic", "real", "hybrid", "journey"],
        default="generic",
        help="generic: 10 casos de catálogo (default). real: casos-reales. hybrid: reales + genéricos. journey: multi-paso.",
    )
    parser.add_argument(
        "--journey-mode",
        choices=["chained", "isolated"],
        default="chained",
        help="Con --suite journey: chained encadena pasos por escenario; isolated usa mensajes autocontenidos por paso.",
    )
    parser.add_argument(
        "--expand",
        type=int,
        default=0,
        help="Con --suite real|hybrid: cantidad de variantes similares generadas por LLM desde casos reales.",
    )
    
    args = parser.parse_args()
    
    asyncio.run(
        run_e2e_suite(
            args.schema,
            args.seller,
            args.limit,
            args.sequential,
            suite_mode=args.suite,
            expand=args.expand,
            journey_mode=args.journey_mode,
        )
    )

if __name__ == "__main__":
    main()
