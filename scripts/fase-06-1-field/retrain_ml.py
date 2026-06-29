"""
retrain_ml.py
=============
Dispara el re-entrenamiento del modelo ML (co-ocurrencia + frecuencia) del
sales-engine para el schema indicado, usando los pedidos históricos recién cargados.

Lee SALES_ENGINE_URL y SALES_ENGINE_API_KEY del .env del proyecto.

Uso:
    python scripts/fase-06-1-field/retrain_ml.py --esquema <schema>

El comando verifica:
  - Health del servicio antes de entrenar.
  - Que rows_used > 0 tras el re-entrenamiento.
  - Notifica si el servicio está caído (no falla el flujo, solo avisa).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from _common_field import sanitize_schema_name

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()


def _get_sales_engine_config() -> tuple[str, str]:
    url = os.getenv("SALES_ENGINE_URL", "").rstrip("/")
    key = os.getenv("SALES_ENGINE_API_KEY", "")
    if not url:
        raise SystemExit("[FAIL] SALES_ENGINE_URL no configurada en .env")
    return url, key


def _headers(key: str) -> dict[str, str]:
    if key:
        return {"X-API-Key": key}
    return {}


def retrain(schema: str) -> None:
    base_url, api_key = _get_sales_engine_config()
    headers = _headers(api_key)
    ml_warnings: list[str] = []

    # 1. Health check
    try:
        resp = httpx.get(f"{base_url}/health", timeout=8.0)
        health = resp.json()
        db_ok = health.get("database") == "connected"
        if not db_ok:
            ml_warnings.append(
                f"[ADVERTENCIA] Sales-engine responde pero la BD no está conectada: {health}"
            )
            print("\n".join(ml_warnings))
            print("[SKIP] Re-entrenamiento saltado. Podés re-intentarlo manualmente:")
            print(f"  curl -X POST {base_url}/v1/tenants/{schema}/models/retrain -H 'X-API-Key: {api_key}'")
            return
        print(f"[OK] Sales-engine health: {health.get('status')}")
    except Exception as exc:
        ml_warnings.append(
            f"[ADVERTENCIA] Sales-engine no disponible ({exc}). "
            "El re-entrenamiento será saltado. Las tareas de tipo CROSS_SELL_COMBO y "
            "REPOSICION_HABITO no se generarán hasta que el modelo esté entrenado."
        )
        print("\n".join(ml_warnings))
        return

    # 2. Retrain (sin filtro de fechas → usa ventana por defecto del servicio = DEFAULT_TRAIN_SINCE_DAYS)
    print(f"[*] Iniciando re-entrenamiento para schema '{schema}'...")
    try:
        resp = httpx.post(
            f"{base_url}/v1/tenants/{schema}/models/retrain",
            json={},
            headers=headers,
            timeout=120.0,  # El entrenamiento puede tomar tiempo con datos ricos
        )
        if resp.status_code == 404:
            raise SystemExit(
                f"[FAIL] El tenant '{schema}' no está activo en el sales-engine. "
                "Verificar que public.distribuidoras tenga schema_name correcto y activa=true."
            )
        if resp.status_code != 200:
            ml_warnings.append(
                f"[ADVERTENCIA] Re-entrenamiento retornó status {resp.status_code}: {resp.text[:300]}"
            )
            print("\n".join(ml_warnings))
            return

        result = resp.json()
        rows_used  = result.get("rows_used", 0)
        model_path = result.get("model_path", "?")

        if rows_used == 0:
            ml_warnings.append(
                "[ADVERTENCIA] rows_used=0. El modelo no fue actualizado. "
                "Verificar que existan pedidos en el rango de entrenamiento."
            )
            print("\n".join(ml_warnings))
            return

        print(f"\n{'='*60}")
        print("RE-ENTRENAMIENTO ML — SALES ENGINE")
        print(f"{'='*60}")
        print(f"  Schema:      {schema}")
        print(f"  Filas usadas: {rows_used}")
        print(f"  Modelo:      {model_path}")
        print(f"{'='*60}")
        print("[OK] Modelo entrenado. CROSS_SELL_COMBO y REPOSICION_HABITO están disponibles.")

    except httpx.TimeoutException:
        ml_warnings.append(
            "[ADVERTENCIA] Re-entrenamiento tardó más de 120 s. Puede haber terminado igualmente."
            " Verificar con: GET /v1/tenants/{schema}/models/debug"
        )
        print("\n".join(ml_warnings))


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-entrena el modelo ML del sales-engine para el tenant.")
    parser.add_argument("--esquema", required=True)
    args = parser.parse_args()
    retrain(sanitize_schema_name(args.esquema))


if __name__ == "__main__":
    main()
