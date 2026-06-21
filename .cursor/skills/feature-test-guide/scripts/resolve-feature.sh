#!/usr/bin/env bash
# resolve-feature.sh — resuelve bundle de specs o slug de feature para guía de pruebas.
set -eo pipefail

QUERY="${1:-}"
if [[ -z "$QUERY" ]]; then
  echo "Uso: resolve-feature.sh <slug|004+005|spec-path>" >&2
  echo "Ej:  resolve-feature.sh field-v2" >&2
  echo "     resolve-feature.sh 004,005,006,007" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
RESOLVE_SPEC="$PLATFORM_ROOT/.cursor/skills/spec-podcast/scripts/resolve-spec.sh"

# Bundles conocidos (slug → specs)
case "$QUERY" in
  field-v2|field-v2-productos-vendedores|vendedores-v2)
    echo "field-v2-productos-vendedores"
    echo "004-clasificacion-productos-comerciales"
    echo "005-field-tareas-v2-diseno"
    echo "006-vendedores-unificados-backoffice"
    echo "007-field-app-v2-mejoras"
    exit 0
    ;;
esac

# Lista de números de spec: 004,005,007
if [[ "$QUERY" == *,* ]]; then
  IFS=',' read -ra PARTS <<< "$QUERY"
  SLUG="feature-$(echo "$QUERY" | tr ',' '-')"
  echo "$SLUG"
  for num in "${PARTS[@]}"; do
    num="$(echo "$num" | tr -d ' ')"
    "$RESOLVE_SPEC" "$num" 2>/dev/null | xargs -I{} basename {} .md || true
  done
  exit 0
fi

# Un solo spec o slug parcial
if [[ -f "$QUERY" ]]; then
  basename "$QUERY" .md
  exit 0
fi

if [[ -x "$RESOLVE_SPEC" ]]; then
  SPEC_PATH="$("$RESOLVE_SPEC" "$QUERY" 2>/dev/null || true)"
  if [[ -n "$SPEC_PATH" && -f "$SPEC_PATH" ]]; then
    basename "$SPEC_PATH" .md
    exit 0
  fi
fi

# Buscar en output previo
OUT="$PLATFORM_ROOT/.cursor/skills/feature-test-guide/output"
if [[ -d "$OUT/$QUERY" ]]; then
  echo "$QUERY"
  exit 0
fi

echo "No se encontró feature bundle para: $QUERY" >&2
echo "Bundles conocidos: field-v2, field-v2-productos-vendedores" >&2
exit 1
