#!/usr/bin/env bash
# Prueba el gateway Almaro. No commitear el token.
# Uso: ALMARO_X_API_KEY=... bash implementacion/almaro/scripts/probe_almaro_api.sh
set -euo pipefail
HOST="${ALMARO_API_HOST:-https://almaro-api.dns-xionico.com}"
KEY="${ALMARO_X_API_KEY:-}"
if [[ -z "$KEY" ]]; then
  echo "Falta ALMARO_X_API_KEY" >&2
  exit 1
fi

probe() {
  local path="$1"
  echo "--- ${path} ---"
  curl -sS -o /tmp/almaro_probe.bin -w "http=%{http_code} time=%{time_total}s size=%{size_download}\n" \
    -L --max-time 60 -H "Accept: application/json" -H "X-API-Key: ${KEY}" "${HOST}${path}"
  python3 - <<'PY'
import json
raw = open("/tmp/almaro_probe.bin", "rb").read()
try:
    data = json.loads(raw)
    if isinstance(data, list):
        first = data[0] if data else None
        if isinstance(first, dict):
            keys = sorted(first.keys())[:8]
            print(f"  list n={len(data)} keys={keys}")
        else:
            print(f"  list n={len(data)} item0={str(first)[:60]}")
    elif isinstance(data, dict):
        print(f"  dict keys={list(data.keys())[:12]}")
    else:
        print("  json", type(data).__name__)
except Exception:
    print("  not-json", raw[:120])
PY
}

probe "/api/articulos/getArticulos/"
probe "/api/vendedores/getVendedores/"
probe "/api/clientes/getClientes/?id_vendedor=1463"
probe "/api/clientes/getClientesDirecciones/?id_vendedor=1463"
probe "/api/listas_precios/getDetallePrecios/?id_vendedor=1463"
