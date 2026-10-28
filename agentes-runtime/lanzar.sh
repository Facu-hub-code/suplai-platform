#!/usr/bin/env bash
# Lanza a mano un run de un bot (spec 138, prueba de concepto).
#
# 1. Pide al backend que cree el trabajo y el run y firme el token (POST /admin/agentes/runs/lanzar).
# 2. Ejecuta el Cloud Run job agente-run con ese token como override de la ejecución.
#
# El token nunca se imprime ni se guarda en disco. La contraseña de admin se pide por teclado.
#
# Uso:
#   ./lanzar.sh almaro catalogo "Corregí las unidades de venta según el Excel"
#   TRABAJO_ID=<uuid> ./lanzar.sh almaro catalogo      # otro run del mismo trabajo
#
# Variables opcionales: BACKEND_URL, ADMIN_EMAIL, MODELO, TIEMPO_MAX_MIN, REGION, PROYECTO.
set -euo pipefail

SCHEMA="${1:?Falta el schema (por ejemplo almaro)}"
ROL="${2:-catalogo}"
PEDIDO="${3:-}"
BACKEND_URL="${BACKEND_URL:-https://web-production-f544f.up.railway.app}"
ADMIN_EMAIL="${ADMIN_EMAIL:-facundo@suplaisales.com}"
MODELO="${MODELO:-claude-opus-5-5}"
TIEMPO_MAX_MIN="${TIEMPO_MAX_MIN:-60}"
REGION="${REGION:-us-east4}"
PROYECTO="${PROYECTO:-suplai-agentes}"

read -r -s -p "Contraseña de admin para ${ADMIN_EMAIL}: " ADMIN_PASSWORD
echo

BODY=$(ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_PASSWORD="$ADMIN_PASSWORD" SCHEMA="$SCHEMA" ROL="$ROL" \
  PEDIDO="$PEDIDO" MODELO="$MODELO" TIEMPO_MAX_MIN="$TIEMPO_MAX_MIN" TRABAJO_ID="${TRABAJO_ID:-}" \
  python3 -c '
import json, os
b = {
    "admin_email": os.environ["ADMIN_EMAIL"],
    "admin_password": os.environ["ADMIN_PASSWORD"],
    "schema_name": os.environ["SCHEMA"],
    "rol": os.environ["ROL"],
    "modelo": os.environ["MODELO"],
    "tiempo_max_min": int(os.environ["TIEMPO_MAX_MIN"]),
}
if os.environ["TRABAJO_ID"]:
    b["trabajo_id"] = os.environ["TRABAJO_ID"]
else:
    b["pedido"] = os.environ["PEDIDO"]
print(json.dumps(b))
')
unset ADMIN_PASSWORD

RESP=$(curl -sS --fail-with-body -X POST "${BACKEND_URL}/admin/agentes/runs/lanzar" \
  -H "Content-Type: application/json" --data-binary @- <<<"$BODY")
unset BODY

campo() { python3 -c "import json,sys; print(json.load(sys.stdin)['$1'])" <<<"$RESP"; }
RUN_ID=$(campo run_id)
TRABAJO=$(campo trabajo_id)
MCP_URL=$(campo mcp_url)
TOKEN=$(campo token)
unset RESP

echo "Trabajo ${TRABAJO}"
echo "Run     ${RUN_ID} (${ROL}, ${MODELO})"

gcloud run jobs execute agente-run \
  --project="$PROYECTO" --region="$REGION" --async \
  --update-env-vars="RUN_ID=${RUN_ID},TRABAJO_ID=${TRABAJO},BOT_ROL=${ROL},MODELO=${MODELO},MCP_URL=${MCP_URL},MCP_TOKEN=${TOKEN}" \
  --format="value(metadata.name)" | sed 's/^/Ejecución /'
unset TOKEN
