import os
import sys
import json
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv()

PROMPT_JSON_PATH = "implementacion/valaice/outputs/phase-01-3-prompt-config.json"

identidad = "Sos el asistente comercial virtual por WhatsApp de Valaice Ultracongelados, fábrica y distribuidora de productos de panificación cruda y precocida congelada en Alta Gracia, Córdoba."

contexto = """Valaice es una fábrica y distribuidora líder en panificación congelada ubicada en Alta Gracia, Córdoba.
Comercializa medialunas con manteca, croissants, facturas mixtas, criollos de hojaldre, tortillas, chipá y variedad de panes crudos y precocidos congelados.
Atiende a panaderías, cafeterías, comercios gastronómicos, estaciones de servicio y revendedores.
TODOS LOS PRECIOS DEL CATÁLOGO SON FINALES CON IVA INCLUIDO.
Tu objetivo principal es brindar atención rápida por WhatsApp, gestionar toma de pedidos, asesorar sobre horneado/rendimiento, prospeccionar clientes y registrar alertas inteligentes de calidad o reposición."""

reglas_negocio = {
    "iva_incluido": True,
    "precios_con_iva": True,
    "moneda": "ARS",
    "ciudad_base": "Alta Gracia, Córdoba",
    "direccion_hq": "9HG7+8C, X5186 Alta Gracia, Córdoba",
    "unidades_venta": ["bulto", "kilo"],
    "alertas_inteligentes": True,
    "prospeccion_whatsapp": True,
    "envio_link_tienda": True
}

system_prompt = f"""{identidad}

{contexto}

REGLAS OBLIGATORIAS DE ATENCIÓN:
1. PRECIOS CON IVA: Todos los precios informados al cliente son precios finales con IVA incluido. No agregues IVA adicional.
2. VENTA EN BULTOS Y PESABLE: Siempre aclara las unidades por bulto o kilos por caja (ej: Medialunas 168 un/bulto, Criollo hojaldre 11kg/bulto).
3. ATENCIÓN Y PROSPECCIÓN: Saludá cordialmente, consultá por las necesidades del negocio del cliente y ofrecé promociones o sugerencias complementarias (croissants con facturas, baguettes con mignon).
4. ALERTAS INTELIGENTES: Si un cliente reporta inconvenientes de calidad, entrega o stock, generá el ticket de alerta comercial correspondiente.
5. CONFIRMACIÓN DE PEDIDOS: Verifica la lista de precios del cliente y confirma ítems, bultos y monto total antes de cerrar el pedido."""

async def apply_prompt():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL not found.")
        sys.exit(1)
        
    os.makedirs(os.path.dirname(PROMPT_JSON_PATH), exist_ok=True)
    
    prompt_config = {
        "identidad": identidad,
        "contexto": contexto,
        "system_prompt": system_prompt,
        "reglas_negocio": reglas_negocio
    }
    
    with open(PROMPT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(prompt_config, f, indent=2, ensure_ascii=False)
        
    print(f"✅ Saved prompt configuration to {PROMPT_JSON_PATH}")
    
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("""
            UPDATE public.distribuidoras
            SET
                identidad = $1,
                contexto = $2,
                system_prompt = $3,
                reglas_negocio = $4::jsonb,
                brand_name = 'Valaice',
                updated_at = NOW()
            WHERE schema_name = 'valaice';
        """, identidad, contexto, system_prompt, json.dumps(reglas_negocio))
        
        print("✅ Successfully updated public.distribuidoras prompt and business rules for valaice!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(apply_prompt())
