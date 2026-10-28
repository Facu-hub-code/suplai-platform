#!/usr/bin/env bash
# Aprueba o rechaza una propuesta de un bot (POST /admin/agentes/propuestas/resolver).
# Aprobar aplica los cambios; cada producto se toca solo si sigue como estaba al proponerlo.
#
# Uso:
#   ./aprobar.sh 123                       # aprueba la propuesta 123
#   ./aprobar.sh 123 rechazar "No era eso"  # la rechaza con motivo
set -euo pipefail

PROPUESTA="${1:?Falta el id de la propuesta (lo muestra la traza)}"
DECISION="${2:-aprobar}"
MOTIVO="${3:-}"
BACKEND_URL="${BACKEND_URL:-https://web-production-f544f.up.railway.app}"
ADMIN_EMAIL="${ADMIN_EMAIL:-facundo@suplaisales.com}"

read -r -s -p "Contraseña de admin para ${ADMIN_EMAIL}: " ADMIN_PASSWORD
echo

ADMIN_EMAIL="$ADMIN_EMAIL" ADMIN_PASSWORD="$ADMIN_PASSWORD" PROPUESTA="$PROPUESTA" DECISION="$DECISION" MOTIVO="$MOTIVO" \
  python3 -c '
import json, os
b = {"admin_email": os.environ["ADMIN_EMAIL"], "admin_password": os.environ["ADMIN_PASSWORD"],
     "propuesta_id": int(os.environ["PROPUESTA"]), "decision": os.environ["DECISION"]}
if os.environ["MOTIVO"]:
    b["motivo"] = os.environ["MOTIVO"]
print(json.dumps(b))
' | curl -sS --fail-with-body -X POST "${BACKEND_URL}/admin/agentes/propuestas/resolver" \
  -H "Content-Type: application/json" --data-binary @- \
  | python3 -c '
import json, sys
r = json.load(sys.stdin)
print("Propuesta", r["propuesta_id"], "-", r["decision"])
print("Aplicados:", len(r["aplicados"]))
for s in r["salteados"]:
    print("Sin tocar", s["product_code"], "-", s["motivo"])
'
unset ADMIN_PASSWORD
