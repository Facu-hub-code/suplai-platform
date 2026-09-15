#!/usr/bin/env bash
# Prueba el gateway nuevo de GG. No commitear el token.
# Uso: GG_X_API_KEY=... bash implementacion/gonzales/scripts/probe_gg_api.sh
set -euo pipefail
HOST="${GG_API_HOST:-https://gg-api.dns-xionico.com}"
KEY="${GG_X_API_KEY:-}"
if [[ -z "$KEY" ]]; then
  echo "Falta GG_X_API_KEY" >&2
  exit 1
fi

probe() {
  local path="$1"
  echo "--- ${path} ---"
  curl -sS -o /tmp/gg_probe.bin -w "http=%{http_code} time=%{time_total}s size=%{size_download}\n" \
    -L --max-time 60 -H "Accept: application/json" -H "X-API-Key: ${KEY}" "${HOST}${path}"
  python3 - <<'PY'
import json
raw = open("/tmp/gg_probe.bin", "rb").read()
try:
    data = json.loads(raw)
    if isinstance(data, list):
        keys = sorted((data[0] or {}).keys())[:8] if data and isinstance(data[0], dict) else []
        print(f"  list n={len(data)} keys={keys}")
    elif isinstance(data, dict):
        print(f"  dict keys={list(data.keys())[:12]}")
    else:
        print("  json", type(data).__name__)
except Exception:
    print("  not-json", raw[:120])
PY
}

probe "/api/articulos/getArticulos/"
probe "/api/clientes/getClientes/?id_vendedor=07"
probe "/api/listas_precios/getListaPrecios/"
probe "/api/listas_precios/getDetallePrecios/?id_vendedor=07"
