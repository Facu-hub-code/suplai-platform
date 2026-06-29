#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-https://web-production-f544f.up.railway.app}"
SCHEMA="${SCHEMA:-al_fuego}"

echo "== Occasion Planner preview — tenant ${SCHEMA} =="
echo "Backend: ${BACKEND_URL}"

HTTP_CODE=$(curl -s -o /tmp/al_fuego_op_preview.json -w "%{http_code}" \
  "${BACKEND_URL}/${SCHEMA}/distribuidora/config/occasion-planners/preview?scenario_id=asado" \
  -H "x-schema-name: ${SCHEMA}")

echo "HTTP ${HTTP_CODE}"
cat /tmp/al_fuego_op_preview.json | python3 -m json.tool 2>/dev/null || cat /tmp/al_fuego_op_preview.json
echo

if [[ "${HTTP_CODE}" == "404" ]]; then
  echo "WARN: endpoint no encontrado — desplegar backend feat/occasion-planners-config"
  exit 2
fi

if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "FAIL: preview no respondió 200"
  exit 1
fi

READY=$(python3 - <<'PY'
import json
with open("/tmp/al_fuego_op_preview.json") as f:
    data = json.load(f)
print("true" if data.get("ready_for_runtime") else "false")
PY
)

if [[ "${READY}" != "true" ]]; then
  echo "FAIL: ready_for_runtime != true"
  exit 1
fi

echo "OK: ready_for_runtime=true"
