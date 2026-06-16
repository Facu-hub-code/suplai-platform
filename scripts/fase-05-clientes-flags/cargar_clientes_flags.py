"""
cargar_clientes_flags.py
========================
Carga los flags de clientes (Fase 5) al tenant Suplai Sales.

Lee el CSV generado por preparar_clientes_flags.py y realiza UPDATEs
en {schema}.clients (NO inserta nuevas filas):

  - codigo        ← codigo_erp del CSV (int; 0 para prospectos)
  - whatsapp_estado ← enum: no_existente | existente | no_validado | validado
  - whatsapp_validado_at ← timestamp si está validado; NULL si no
  - etiqueta      ← 'PROSPECTO' para prospectos; NULL o vacío para el resto

El match se hace por phone_number (UNIQUE en la tabla).

Uso:
    python scripts/fase-05-clientes-flags/cargar_clientes_flags.py --esquema <nombre_esquema>

Variables de entorno requeridas (en .env):
    SUPABASE_DB_URL
"""

import os
import sys
import csv
import argparse
import asyncio
import asyncpg
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


async def cargar_flags(esquema: str):
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL no está configurada en .env")
        sys.exit(1)

    if not all(c.isalnum() or c == "_" for c in esquema):
        print(f"[FAIL] Nombre de esquema inválido: '{esquema}'")
        sys.exit(1)

    csv_path = f"implementacion/{esquema}/outputs/phase-05-clientes-flags.csv"
    if not os.path.exists(csv_path):
        print(f"[FAIL] CSV no encontrado: {csv_path}")
        print("       Ejecutá primero: python scripts/fase-05-clientes-flags/preparar_clientes_flags.py")
        sys.exit(1)

    filas = []
    with open(csv_path, "r", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))

    print(f"[*] Procesando {len(filas)} clientes del CSV...")

    conn = await asyncpg.connect(db_url)
    try:
        # search_path para resolver los enums del tenant
        await conn.execute(f"SET search_path TO {esquema}, core, public, extensions")

        updated = 0
        not_found = []

        for row in filas:
            phone = row["phone_number"]
            codigo_erp = int(row["codigo_erp"])
            wa_estado = row["whatsapp_estado"]
            wa_validado_at_str = row.get("whatsapp_validado_at", "").strip()
            etiqueta = row.get("etiqueta", "").strip() or None

            # Parsear timestamp si existe
            wa_validado_at = None
            if wa_validado_at_str:
                try:
                    wa_validado_at = datetime.fromisoformat(wa_validado_at_str)
                except ValueError:
                    print(f"  [WARN] Timestamp inválido para {phone}: '{wa_validado_at_str}'")

            result = await conn.execute(f"""
                UPDATE {esquema}.clients
                SET
                    codigo             = $1,
                    whatsapp_estado    = $2::whatsapp_estado_cliente_enum,
                    whatsapp_validado_at = $3,
                    etiqueta           = $4,
                    updated_at         = now()
                WHERE phone_number = $5
            """, codigo_erp, wa_estado, wa_validado_at, etiqueta, phone)

            rows_affected = int(result.split(" ")[-1])
            if rows_affected == 0:
                not_found.append(phone)
            else:
                updated += 1

        # Verificación
        count_erp = await conn.fetchval(
            f"SELECT COUNT(*) FROM {esquema}.clients WHERE codigo > 0 AND is_mock = true"
        )
        count_prospectos = await conn.fetchval(
            f"SELECT COUNT(*) FROM {esquema}.clients WHERE codigo = 0 AND is_mock = true"
        )
        count_validados = await conn.fetchval(
            f"SELECT COUNT(*) FROM {esquema}.clients WHERE whatsapp_estado = 'validado' AND is_mock = true"
        )
        count_etiqueta = await conn.fetchval(
            f"SELECT COUNT(*) FROM {esquema}.clients WHERE etiqueta = 'PROSPECTO' AND is_mock = true"
        )

        print("\n" + "=" * 60)
        print("VERIFICACIÓN FASE 5 — FLAGS DE CLIENTES")
        print("=" * 60)
        print(f"  Clientes actualizados:   {updated}")
        print(f"  No encontrados (warn):   {len(not_found)}")
        print(f"  Clientes ERP (cod>0):    {count_erp}")
        print(f"  Prospectos (cod=0):      {count_prospectos}")
        print(f"  WA validado:             {count_validados}")
        print(f"  Etiqueta PROSPECTO:      {count_etiqueta}")
        print("=" * 60)

        if not_found:
            print(f"\n[WARN] {len(not_found)} teléfonos no encontrados en BD:")
            for p in not_found[:5]:
                print(f"  {p}")
            if len(not_found) > 5:
                print(f"  ... y {len(not_found) - 5} más.")

        if count_erp >= 38 and count_prospectos >= 8:
            print("✅ Verificación exitosa: distribución ERP/prospectos correcta.")
        else:
            print("[WARN] Los conteos no coinciden con los esperados (40/10). Revisar logs.")

    except Exception as e:
        print(f"\n[FAIL] Error durante la carga: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Carga flags de clientes (Fase 5) al schema del tenant."
    )
    parser.add_argument("--esquema", required=True, help="Esquema del tenant (ej: al_fuego)")
    args = parser.parse_args()
    asyncio.run(cargar_flags(args.esquema))


if __name__ == "__main__":
    main()
