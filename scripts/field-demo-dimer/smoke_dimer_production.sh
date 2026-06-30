#!/usr/bin/env bash
# Post-seed producción — retrain + generar tareas reposición Juan Pérez (dimer)
set -euo pipefail

SCHEMA="${SCHEMA:-dimer}"
SE_URL="${SALES_ENGINE_URL:-https://sales-engine-production-f6bd.up.railway.app}"
BE_URL="${BACKEND_URL:-https://web-production-f544f.up.railway.app}"
VENDEDOR_WP="${VENDEDOR_WP:-5493516123456}"

if [ -f "${SALES_ENGINE_ENV:-../sales-engine/.env}" ]; then
  set -a && . "${SALES_ENGINE_ENV:-../sales-engine/.env}" && set +a
fi

echo "== 1. Retrain sales-engine (${SE_URL}) =="
curl -sf -X POST "${SE_URL}/v1/tenants/${SCHEMA}/models/retrain" \
  -H "Content-Type: application/json" \
  ${SALES_ENGINE_API_KEY:+-H "X-API-Key: ${SALES_ENGINE_API_KEY}"} \
  -d '{"since_days": 365}'
echo ""

echo "== 2. Predicción Comidas Congeladas (cliente 28) =="
curl -sf -X POST "${SE_URL}/v1/tenants/${SCHEMA}/predict-replenishment" \
  -H "Content-Type: application/json" \
  ${SALES_ENGINE_API_KEY:+-H "X-API-Key: ${SALES_ENGINE_API_KEY}"} \
  -d '{"cliente_id": "28"}'
echo ""

echo "== 3. Home vendedor (dispara ensure_daily_tasks) =="
curl -sf "${BE_URL}/${SCHEMA}/vendedor-app/home" \
  -H "x-schema-name: ${SCHEMA}" \
  -H "x-vendedor-telefono: ${VENDEDOR_WP}" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
for i in d.get('ruta', {}).get('items', []):
    for t in i.get('tareas') or []:
        if t.get('tipo') == 'REPOSICION_HABITO':
            print(f\"✓ {i.get('nombre')}: {t.get('descripcion', '')[:100]}\")
"

echo ""
echo "Field App: https://field.suplaisales.com/${SCHEMA}?wp=${VENDEDOR_WP}"
