#!/usr/bin/env python3
"""Aplica prompt v2 de Córdoba Frost sin pisar reglas_negocio ni el teléfono."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "implementacion/cordoba_frost/outputs/phase-01-3-prompt-config.json"
SCHEMA = "cordoba_frost"

RECEPCIONISTA_INSTRUCTIONS = """Tono e interacción:
- Sé muy simpático, cálido, cercano y alegre durante todo el proceso de registro (¡evita sonar seco o acartonado!). Saludá de forma muy acogedora.
- Córdoba Frost vende por WhatsApp el catálogo de panadería congelada, helados, congelados, insumos, sin TACC y combos (~285 productos). NUNCA digas que no tenés inventario, catálogo o helados. NUNCA digas que solo vendemos 6 combos.
- Si el usuario pide productos, helados o combos ANTES de terminar el registro: reconocé que sí tenemos esas líneas, pedí el dato de registro que falte (nombre del negocio) y decile que en cuanto termine el alta Martín le muestra el catálogo con precios.
- Al guiar el registro, informale en breve que al finalizar Martín puede mostrar el catálogo (panadería, helados, congelados, etc.), tomar el primer pedido y revisar envío.
- No enumeres ni desgloses el detalle técnico del catálogo durante el cuestionario de registro; mantené las interacciones cortas, fluidas y amables."""


async def main() -> None:
    load_dotenv(ROOT.parent / "backend-supabase/.env")
    load_dotenv(ROOT / ".env", override=False)
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL no configurada.")
        sys.exit(1)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    identidad = cfg["identidad"]
    contexto = cfg["contexto"]
    system_prompt = cfg["system_prompt"]
    base_client = cfg["agent_base_prompt_client"]

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM public.distribuidoras WHERE schema_name = $1)",
            SCHEMA,
        )
        if not exists:
            print(f"[FAIL] No existe schema_name={SCHEMA}")
            sys.exit(1)

        before = await conn.fetchrow(
            """
            SELECT agent_phone_number::text AS phone,
                   reglas_negocio->'order_fulfillment'->>'enabled' AS fulfillment,
                   reglas_negocio->'order_notification'->>'enabled' AS notif
            FROM public.distribuidoras
            WHERE schema_name = $1
            """,
            SCHEMA,
        )
        print(f"[*] Antes: phone={before['phone']} fulfillment={before['fulfillment']} notif={before['notif']}")

        await conn.execute(
            """
            UPDATE public.distribuidoras
            SET identidad = $1,
                contexto = $2,
                system_prompt = $3,
                agent_base_prompt_client = $4,
                receptionist_config = jsonb_set(
                  COALESCE(receptionist_config, '{}'::jsonb),
                  '{custom_instructions}',
                  to_jsonb($5::text),
                  true
                ),
                updated_at = NOW()
            WHERE schema_name = $6
            """,
            identidad,
            contexto,
            system_prompt,
            base_client,
            RECEPCIONISTA_INSTRUCTIONS,
            SCHEMA,
        )

        after = await conn.fetchrow(
            """
            SELECT schema_name,
                   agent_phone_number::text AS phone,
                   length(identidad) AS len_id,
                   length(contexto) AS len_ctx,
                   length(system_prompt) AS len_sp,
                   length(agent_base_prompt_client) AS len_base,
                   (system_prompt ILIKE '%285 SKUs%') AS sp_catalogo,
                   (system_prompt ILIKE '%Vender **6 combos**%' OR system_prompt ILIKE '%solo existen **6 combos**%') AS sp_viejo_6,
                   (agent_base_prompt_client ILIKE '%no un recorte de 6 combos%') AS base_nuevo,
                   (receptionist_config->>'custom_instructions' ILIKE '%~285 productos%') AS rec_nuevo,
                   (receptionist_config->>'custom_instructions' ILIKE '%6 combos cerrados%') AS rec_viejo,
                   reglas_negocio->'order_fulfillment'->>'enabled' AS fulfillment,
                   reglas_negocio->'order_notification'->>'enabled' AS notif,
                   (reglas_negocio ? 'order_fulfillment') AS has_fulfillment,
                   (reglas_negocio->'order_fulfillment'->'delivery'->>'shipping_product_code') AS shipping_sku
            FROM public.distribuidoras
            WHERE schema_name = $1
            """,
            SCHEMA,
        )
        print("✅ Prompt aplicado en public.distribuidoras (schema_name=cordoba_frost)")
        print(f"Teléfono (sin cambio): {after['phone']}")
        print(f"Largos: identidad={after['len_id']} contexto={after['len_ctx']} system_prompt={after['len_sp']} base_client={after['len_base']}")
        print(f"system_prompt catálogo 285: {after['sp_catalogo']} | texto viejo 6 combos: {after['sp_viejo_6']}")
        print(f"base_client nuevo: {after['base_nuevo']} | recepcionista nuevo: {after['rec_nuevo']} viejo: {after['rec_viejo']}")
        print(f"reglas conservadas: fulfillment={after['fulfillment']} notif={after['notif']} ENVIO-DOM={after['shipping_sku']}")
        if after["phone"] != "5493518633611":
            print("[FAIL] El teléfono cambió.")
            sys.exit(1)
        if after["fulfillment"] != "true" or after["shipping_sku"] != "ENVIO-DOM":
            print("[FAIL] Se pisaron reglas de fulfillment.")
            sys.exit(1)
        if not after["sp_catalogo"] or after["sp_viejo_6"] or after["rec_viejo"]:
            print("[FAIL] El texto nuevo no quedó como se esperaba.")
            sys.exit(1)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
