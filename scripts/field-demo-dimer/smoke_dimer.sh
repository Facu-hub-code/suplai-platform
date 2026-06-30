#!/usr/bin/env bash
# Smoke test post-seed demo field — tenant dimer
set -euo pipefail

SCHEMA="${SCHEMA:-dimer}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
SALES_ENGINE_URL="${SALES_ENGINE_URL:-http://127.0.0.1:8001}"
VENDEDOR_WP="${VENDEDOR_WP:-5493516123456}"

echo "== Retrain sales-engine =="
curl -sf -X POST "${SALES_ENGINE_URL}/v1/tenants/${SCHEMA}/models/retrain" \
  -H "Content-Type: application/json" || echo "(sales-engine no disponible — continuar)"

echo ""
echo "== Home vendedor =="
curl -sf "${BACKEND_URL}/${SCHEMA}/vendedor-app/home" \
  -H "x-schema-name: ${SCHEMA}" \
  -H "x-vendedor-telefono: ${VENDEDOR_WP}" | head -c 2000

echo ""
echo ""
echo "== Conteos BD (ejecutar en Supabase) =="
cat <<SQL
SELECT 'templates' AS t, count(*) FROM ${SCHEMA}.field_task_templates
UNION ALL SELECT 'tasks', count(*) FROM ${SCHEMA}.field_tasks
UNION ALL SELECT 'torneos', count(*) FROM ${SCHEMA}.field_tournaments
UNION ALL SELECT 'objetivos', count(*) FROM ${SCHEMA}.field_objetivos
UNION ALL SELECT 'ledger', count(*) FROM ${SCHEMA}.field_point_ledger
UNION ALL SELECT 'seed_pedidos', count(*) FROM ${SCHEMA}.pedidos WHERE notas LIKE 'SEED DEMO FIELD DIMER%';
SQL
