#!/usr/bin/env bash
# Smoke test post-seed para REPOSICION_HABITO en el_gigante.
# Requiere: DATABASE_URL, SALES_ENGINE_URL (default http://127.0.0.1:8001)
set -euo pipefail

SE_URL="${SALES_ENGINE_URL:-http://127.0.0.1:8001}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: export DATABASE_URL (pooler 6543 recomendado)" >&2
  exit 1
fi

CLIENTE_ID=$(psql "$DATABASE_URL" -tA -c \
  "SELECT id FROM el_gigante.clients WHERE phone_number='5493587905250' LIMIT 1")

if [[ -z "$CLIENTE_ID" ]]; then
  echo "ERROR: cliente Dulce Sorpresa no encontrado en el_gigante" >&2
  exit 1
fi

echo "== Retrain el_gigante =="
curl -sf -X POST "$SE_URL/v1/tenants/el_gigante/models/retrain" \
  -H "Content-Type: application/json" \
  -d '{"since_days": 365}'

echo ""
echo "== predict-replenishment cliente_id=$CLIENTE_ID (SKU 295) =="
curl -sf -X POST "$SE_URL/v1/tenants/el_gigante/predict-replenishment" \
  -H "Content-Type: application/json" \
  -d "{\"cliente_id\": \"$CLIENTE_ID\"}" \
  | jq '.predictions[] | select(.product_code=="295")'

echo ""
echo "== pedidos_90d (debe ser > 3) =="
psql "$DATABASE_URL" -c "
SELECT COUNT(*) AS pedidos_90d
FROM el_gigante.pedidos p
JOIN el_gigante.clients c ON c.id = p.cliente_id
WHERE c.phone_number = '5493587905250'
  AND lower(trim(p.estado::text)) IN ('confirmado', 'descargado')
  AND p.fecha >= CURRENT_DATE - INTERVAL '90 days';
"
