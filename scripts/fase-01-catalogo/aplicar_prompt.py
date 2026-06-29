import os
import sys
import json
import argparse
import asyncio
import asyncpg
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env local
load_dotenv()

# Reconfigurar stdout a UTF-8 en Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

async def aplicar_prompt(esquema: str):
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] La variable de entorno SUPABASE_DB_URL no está configurada en el archivo .env.")
        sys.exit(1)

    # Validamos que el esquema sea alfanumérico para evitar inyecciones SQL
    if not esquema.isalnum() and "_" not in esquema:
        print(f"[FAIL] Nombre de esquema inválido '{esquema}'. Debe ser alfanumérico.")
        sys.exit(1)

    config_path = f"implementacion/{esquema}/outputs/phase-01-3-prompt-config.json"
    if not os.path.exists(config_path):
        print(f"[FAIL] No se encontró el archivo de configuración en: {config_path}")
        print("Asegúrate de haber generado el prompt en los pasos previos.")
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"[FAIL] Error al leer el archivo JSON {config_path}: {e}")
        sys.exit(1)

    # Validar campos obligatorios en el JSON
    required_keys = ["identidad", "contexto", "reglas_negocio", "agent_phone_number"]
    missing_keys = [k for k in required_keys if k not in config]
    if missing_keys:
        print(f"[FAIL] Faltan claves requeridas en el archivo JSON: {', '.join(missing_keys)}")
        sys.exit(1)

    identidad = config["identidad"]
    contexto = config["contexto"]
    reglas_negocio = json.dumps(config["reglas_negocio"])
    agent_phone_number = str(config["agent_phone_number"])

    conn = await asyncpg.connect(db_url)
    try:
        print(f"[*] Actualizando public.distribuidoras para el esquema: {esquema}...")
        
        # Primero verificamos si el registro existe en public.distribuidoras
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM public.distribuidoras WHERE schema_name = $1)",
            esquema
        )
        if not exists:
            print(f"[FAIL] No existe ningún registro con schema_name = '{esquema}' en public.distribuidoras.")
            sys.exit(1)

        # Actualizar los datos del prompt
        await conn.execute(
            """
            UPDATE public.distribuidoras 
            SET 
              identidad = $1,
              contexto = $2,
              reglas_negocio = CAST($3 AS jsonb),
              agent_phone_number = $4,
              updated_at = NOW()
            WHERE schema_name = $5
            """,
            identidad, contexto, reglas_negocio, agent_phone_number, esquema
        )
        print("✅ Base de datos actualizada con éxito.")

        # Secuencias de seguimiento por defecto (desactivadas — el cliente las activa cuando quiera)
        tenant_id = await conn.fetchval(
            "SELECT id FROM public.distribuidoras WHERE schema_name = $1", esquema
        )
        if tenant_id:
            await conn.executemany(
                """
                INSERT INTO public.followup_sequences
                  (name, description, enabled, trigger_after_seconds, conditions, actions,
                   max_executions_per_conversation, tenant_id)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8)
                ON CONFLICT DO NOTHING
                """,
                [
                    (
                        "followup_sin_respuesta_10min",
                        "El cliente no respondio al mensaje del agente en 10 minutos. Se envia un mensaje cordial para retomar el contacto.",
                        False,
                        600,
                        '{"all":[{"type":"minutes_idle_gte","value":10}]}',
                        '[{"type":"send_followup_message","message":"Hola! Solo queria asegurarme de que todo este bien. Podemos ayudarte con algo?"}]',
                        1,
                        tenant_id,
                    ),
                    (
                        "followup_carrito_abandonado_30min",
                        "El cliente tiene un carrito abierto por mas de 30 minutos sin confirmar. El agente lo contacta para ayudarlo a cerrar el pedido.",
                        False,
                        1800,
                        '{"all":[{"type":"has_open_order"},{"type":"minutes_idle_gte","value":30}]}',
                        '[{"type":"send_followup_message","message":"Hola de nuevo! Veo que tenes un pedido en proceso. Te gustaria que lo revisemos juntos? Puedo modificar, agregar o ajustar lo que necesites para confirmarlo."}]',
                        1,
                        tenant_id,
                    ),
                ],
            )
            print("✅ Secuencias de seguimiento creadas (desactivadas por defecto).")

        # Verificación post-carga
        row = await conn.fetchrow(
            """
            SELECT schema_name, identidad, contexto, reglas_negocio, agent_phone_number 
            FROM public.distribuidoras 
            WHERE schema_name = $1
            """,
            esquema
        )
        if row:
            print("\n" + "=" * 60)
            print("VERIFICACIÓN DE CARGA POST-PROMPT")
            print("=" * 60)
            print(f"Esquema: {row['schema_name']}")
            print(f"Teléfono del Agente: {row['agent_phone_number']}")
            print(f"Largo de Identidad: {len(row['identidad'])} caracteres")
            print(f"Largo de Contexto: {len(row['contexto'])} caracteres")
            print(f"Reglas de Negocio en DB: {row['reglas_negocio']}")
            print("=" * 60)
        else:
            print("[FAIL] Error al intentar verificar el registro después de la actualización.")
            
    except Exception as e:
        print(f"[FAIL] Ocurrió un error inesperado al actualizar la base de datos: {e}")
        sys.exit(1)
    finally:
        await conn.close()

def main():
    parser = argparse.ArgumentParser(description="Actualiza la tabla public.distribuidoras con la identidad y contexto del prompt del agente.")
    parser.add_argument("--esquema", required=True, help="Esquema del tenant en Supabase (ej: colormix)")
    args = parser.parse_args()
    
    asyncio.run(aplicar_prompt(args.esquema))

if __name__ == "__main__":
    main()
