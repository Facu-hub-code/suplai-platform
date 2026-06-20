#!/usr/bin/env bash
# resolve-spec.sh — encuentra un spec markdown por número, slug o path parcial.
# Compatible con bash 3.x (macOS).
set -eo pipefail

QUERY="${1:-}"
if [[ -z "$QUERY" ]]; then
  echo "Uso: resolve-spec.sh <numero|slug|path-parcial>" >&2
  echo "Ej:  resolve-spec.sh 004" >&2
  echo "     resolve-spec.sh clasificacion-productos" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
WORKSPACE_ROOT="$(cd "$PLATFORM_ROOT/.." && pwd)"

SEARCH_ROOTS=(
  "$PLATFORM_ROOT/docs/specs"
  "$WORKSPACE_ROOT/backend-supabase/docs/specs"
  "$WORKSPACE_ROOT/agente-conversacional-multi_tenant/docs/specs"
  "$WORKSPACE_ROOT/product-management-app/docs/specs"
  "$WORKSPACE_ROOT/wholesale-catalog-app/docs/specs"
  "$WORKSPACE_ROOT/sales-engine/docs/specs"
)

# Path absoluto o relativo existente
if [[ -f "$QUERY" ]]; then
  realpath "$QUERY"
  exit 0
fi

CANDIDATE="$PLATFORM_ROOT/$QUERY"
if [[ -f "$CANDIDATE" ]]; then
  realpath "$CANDIDATE"
  exit 0
fi

MATCHES=""
for root in "${SEARCH_ROOTS[@]}"; do
  [[ -d "$root" ]] || continue
  while IFS= read -r f; do
    base="$(basename "$f")"
    if [[ "$base" == *"$QUERY"* ]] || [[ "$base" =~ ^${QUERY}[-_] ]] || [[ "$base" =~ ^0*${QUERY}[-_] ]]; then
      MATCHES="${MATCHES}${f}"$'\n'
    fi
  done < <(
    find "$root" -maxdepth 1 -name '*.md' -type f 2>/dev/null | sort -u
  )
done

MATCHES="$(printf '%s' "$MATCHES" | sed '/^$/d' | sort -u)"

# Priorizar platform/docs/specs cuando hay colisión de número entre repos
PLATFORM_SPECS="$PLATFORM_ROOT/docs/specs"
if [[ "$QUERY" =~ ^[0-9]+$ ]] || [[ "$QUERY" =~ ^0*[0-9]+$ ]]; then
  PREFERRED="$(printf '%s\n' "$MATCHES" | grep "^${PLATFORM_SPECS}/" | head -1 || true)"
  if [[ -n "$PREFERRED" ]]; then
    printf '%s\n' "$PREFERRED"
    exit 0
  fi
fi

COUNT="$(printf '%s\n' "$MATCHES" | sed '/^$/d' | wc -l | tr -d ' ')"

if [[ "$COUNT" -eq 0 ]]; then
  echo "No se encontró spec para: $QUERY" >&2
  echo "Buscado en:" >&2
  for root in "${SEARCH_ROOTS[@]}"; do
    [[ -d "$root" ]] && echo "  - $root" >&2
  done
  exit 1
fi

if [[ "$COUNT" -eq 1 ]]; then
  printf '%s\n' "$MATCHES"
  exit 0
fi

echo "Varios specs coinciden con '$QUERY':" >&2
printf '%s\n' "$MATCHES" | while IFS= read -r m; do
  [[ -n "$m" ]] && echo "  - $m" >&2
done
printf '%s\n' "$MATCHES" | head -1
exit 2
