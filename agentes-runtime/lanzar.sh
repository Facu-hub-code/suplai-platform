#!/usr/bin/env bash
# Lanza a mano un run de un bot (spec 138, prueba de concepto).
#
# 1. Pide al backend que cree el trabajo y el run y firme el token (POST /admin/agentes/runs/lanzar).
# 2. Ejecuta el Cloud Run job agente-run con ese token como override de la ejecución.
#
# El token nunca se imprime ni se guarda en disco. La contraseña de admin se pide por teclado.
#
# Uso:
#   ADJUNTO=../implementacion/almaro/inputs/productos_display_1_unidad.xlsx \
#     ./lanzar.sh almaro catalogo "Corregí las unidades de venta según el Excel de Vale"
#   TRABAJO_ID=<uuid> ./lanzar.sh almaro catalogo      # otro run del mismo trabajo
#
# ADJUNTO: un .xlsx (se convierte a CSV acá, hoja por hoja) o un archivo de texto. Hasta 1 MB.
# Variables opcionales: BACKEND_URL, ADMIN_EMAIL, MODELO, TIEMPO_MAX_MIN, TOPE_USD, MAX_TURNOS,
# REGION, PROYECTO.
set -euo pipefail

SCHEMA="${1:?Falta el schema (por ejemplo almaro)}"
ROL="${2:-catalogo}"
PEDIDO="${3:-}"
BACKEND_URL="${BACKEND_URL:-https://web-production-f544f.up.railway.app}"
ADMIN_EMAIL="${ADMIN_EMAIL:-facundo@suplaisales.com}"
MODELO="${MODELO:-claude-opus-5-5}"
TIEMPO_MAX_MIN="${TIEMPO_MAX_MIN:-60}"
TOPE_USD="${TOPE_USD:-8}"
MAX_TURNOS="${MAX_TURNOS:-80}"
REGION="${REGION:-us-east4}"
PROYECTO="${PROYECTO:-suplai-agentes}"

read -r -s -p "Contraseña de admin para ${ADMIN_EMAIL}: " ADMIN_PASSWORD
echo

BODY=$(ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_PASSWORD="$ADMIN_PASSWORD" SCHEMA="$SCHEMA" ROL="$ROL" \
  PEDIDO="$PEDIDO" MODELO="$MODELO" TIEMPO_MAX_MIN="$TIEMPO_MAX_MIN" TRABAJO_ID="${TRABAJO_ID:-}" \
  ADJUNTO="${ADJUNTO:-}" python3 -c '
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
    ruta = os.environ["ADJUNTO"]
    if ruta:
        import csv, io, pathlib
        p = pathlib.Path(ruta)
        if p.suffix.lower() in (".xlsx", ".xlsm"):
            import openpyxl
            wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
            b["adjuntos"] = []
            for ws in wb.worksheets:
                out = io.StringIO()
                w = csv.writer(out)
                for fila in ws.iter_rows(values_only=True):
                    w.writerow(["" if v is None else v for v in fila])
                sufijo = "" if len(wb.worksheets) == 1 else "-" + ws.title.replace("/", "-")
                b["adjuntos"].append({"nombre": f"{p.stem}{sufijo}.csv", "tipo": "text/csv", "contenido": out.getvalue()})
        else:
            b["adjuntos"] = [{"nombre": p.name, "tipo": "text/plain", "contenido": p.read_text(encoding="utf-8")}]
print(json.dumps(b))
')
unset ADMIN_PASSWORD

# Sin --fail: si el backend rechaza, se muestra su detalle (nunca trae el token).
RESP=$(curl -sS -w '\n%{http_code}' -X POST "${BACKEND_URL}/admin/agentes/runs/lanzar" \
  -H "Content-Type: application/json" --data-binary @- <<<"$BODY")
unset BODY
CODIGO=${RESP##*$'\n'}
RESP=${RESP%$'\n'*}
if [[ "$CODIGO" != 2* ]]; then
  echo "El backend respondió ${CODIGO}: ${RESP}" >&2
  exit 1
fi

campo() { python3 -c "import json,sys; print(json.load(sys.stdin)['$1'])" <<<"$RESP"; }
RUN_ID=$(campo run_id)
TRABAJO=$(campo trabajo_id)
MCP_URL=$(campo mcp_url)
TOKEN=$(campo token)
unset RESP

echo "Trabajo ${TRABAJO}"
echo "Run     ${RUN_ID} (${ROL}, ${MODELO}, tope US\$ ${TOPE_USD}, ${MAX_TURNOS} turnos)"

gcloud run jobs execute agente-run \
  --project="$PROYECTO" --region="$REGION" --async \
  --update-env-vars="RUN_ID=${RUN_ID},TRABAJO_ID=${TRABAJO},BOT_ROL=${ROL},MODELO=${MODELO},TOPE_USD=${TOPE_USD},MAX_TURNOS=${MAX_TURNOS},MCP_URL=${MCP_URL},MCP_TOKEN=${TOKEN}" \
  --format="value(metadata.name)" | sed 's/^/Ejecución /'
unset TOKEN
