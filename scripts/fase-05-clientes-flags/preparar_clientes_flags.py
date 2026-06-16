"""
preparar_clientes_flags.py
==========================
Genera el CSV de flags de clientes para Fase 5 del onboarding Suplai Sales.

Lee el CSV de clientes de Fase 4 y genera una distribución de:
  - 40 clientes de cartera (ERP): codigo secuencial desde 25001
      - 30 con whatsapp_estado = 'validado' (+ whatsapp_validado_at)
      - 10 con whatsapp_estado = 'existente'
  - 10 clientes prospectos: codigo = 0, etiqueta = 'PROSPECTO'
      - whatsapp_estado variado

Output: implementacion/{esquema}/outputs/phase-05-clientes-flags.csv

Uso:
    python scripts/fase-05-clientes-flags/preparar_clientes_flags.py --esquema <nombre_esquema>

Columnas del CSV de salida (todas mapean a UPDATE en {schema}.clients):
    phone_number, codigo_erp, whatsapp_estado, whatsapp_validado_at, etiqueta, is_prospect_flag

Enums válidos para whatsapp_estado (de la BD real):
    no_existente | existente | no_validado | validado
"""

import os
import sys
import csv
import argparse
from datetime import datetime, timezone

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

# Distribución según SKILL.md:
# 40 clientes ERP: 30 validado / 10 existente
# 10 prospectos: mezcla
WHATSAPP_ERP_VALIDADO = 30
WHATSAPP_ERP_EXISTENTE = 10
TOTAL_ERP = 40
TOTAL_PROSPECTOS = 10
TOTAL = TOTAL_ERP + TOTAL_PROSPECTOS

WHATSAPP_PROSPECTO_MIX = [
    "no_validado", "existente", "no_validado", "existente",
    "no_validado", "validado", "no_existente", "no_validado",
    "existente", "no_validado",
]

NOW_ISO = datetime.now(timezone.utc).isoformat()
ERP_CODIGO_INICIO = 25001


def main():
    parser = argparse.ArgumentParser(
        description="Genera phase-05-clientes-flags.csv para un tenant Suplai Sales."
    )
    parser.add_argument("--esquema", required=True, help="Esquema del tenant (ej: al_fuego)")
    args = parser.parse_args()
    esquema = args.esquema

    # Leer CSV de clientes de Fase 4
    clientes_csv = f"implementacion/{esquema}/outputs/phase-04-clientes.csv"
    if not os.path.exists(clientes_csv):
        print(f"[FAIL] No se encontró el CSV de Fase 4: {clientes_csv}")
        print("       Ejecutá primero: python scripts/fase-04-red-comercial/preparar_red_comercial.py")
        sys.exit(1)

    clientes = []
    with open(clientes_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clientes.append(row)

    total = len(clientes)
    print(f"[*] Clientes leídos de Fase 4: {total}")

    if total < TOTAL:
        print(f"[WARN] Se esperaban {TOTAL} clientes, hay {total}. Ajustando distribución.")

    n_erp = min(TOTAL_ERP, total)
    n_prospectos = total - n_erp

    output_dir = f"implementacion/{esquema}/outputs"
    os.makedirs(output_dir, exist_ok=True)
    output_path = f"{output_dir}/phase-05-clientes-flags.csv"

    rows = []

    # --- Clientes ERP (primeros 40) ---
    erp_codigo = ERP_CODIGO_INICIO
    for i, cliente in enumerate(clientes[:n_erp]):
        if i < WHATSAPP_ERP_VALIDADO:
            wa_estado = "validado"
            wa_validado_at = NOW_ISO
        else:
            wa_estado = "existente"
            wa_validado_at = ""

        rows.append({
            "phone_number": cliente["phone_number"],
            "razon_social": cliente["razon_social"],
            "codigo_erp": erp_codigo,
            "whatsapp_estado": wa_estado,
            "whatsapp_validado_at": wa_validado_at,
            "etiqueta": "",
            "is_prospect": "false",
        })
        erp_codigo += 1

    # --- Prospectos (últimos 10) ---
    for i, cliente in enumerate(clientes[n_erp:]):
        wa_estado = WHATSAPP_PROSPECTO_MIX[i % len(WHATSAPP_PROSPECTO_MIX)]
        wa_validado_at = NOW_ISO if wa_estado == "validado" else ""
        rows.append({
            "phone_number": cliente["phone_number"],
            "razon_social": cliente["razon_social"],
            "codigo_erp": 0,
            "whatsapp_estado": wa_estado,
            "whatsapp_validado_at": wa_validado_at,
            "etiqueta": "PROSPECTO",
            "is_prospect": "true",
        })

    # Escribir CSV
    fieldnames = [
        "phone_number", "razon_social", "codigo_erp",
        "whatsapp_estado", "whatsapp_validado_at", "etiqueta", "is_prospect",
    ]
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Resumen
    validados = sum(1 for r in rows if r["whatsapp_estado"] == "validado")
    prospectos = sum(1 for r in rows if r["is_prospect"] == "true")
    erp_con_codigo = sum(1 for r in rows if int(r["codigo_erp"]) > 0)

    print(f"\n✅ CSV generado: {output_path}")
    print(f"   Total filas:        {len(rows)}")
    print(f"   Clientes ERP:       {erp_con_codigo}  (código ≥ {ERP_CODIGO_INICIO})")
    print(f"   Prospectos:         {prospectos}  (código = 0, etiqueta = PROSPECTO)")
    print(f"   WA validado:        {validados}")
    print(f"   WA existente:       {sum(1 for r in rows if r['whatsapp_estado'] == 'existente')}")
    print(f"   WA no_validado:     {sum(1 for r in rows if r['whatsapp_estado'] == 'no_validado')}")
    print(f"   WA no_existente:    {sum(1 for r in rows if r['whatsapp_estado'] == 'no_existente')}")

    print(f"\nPróximo paso:")
    print(f"   python scripts/fase-05-clientes-flags/cargar_clientes_flags.py --esquema {esquema}")


if __name__ == "__main__":
    main()
