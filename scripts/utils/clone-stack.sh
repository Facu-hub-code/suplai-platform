#!/usr/bin/env bash
# Clona suplai-platform y los repos hermanos con los nombres que espera el workspace.
# Uso: ./scripts/clone-stack.sh [directorio-padre]
# Ejemplo: ./scripts/clone-stack.sh ~/SuplaiSales/source

set -euo pipefail

GITHUB_ORG="${GITHUB_ORG:-Facu-hub-code}"
PARENT="${1:-$(cd "$(dirname "$0")/.." && pwd)/..}"

mkdir -p "$PARENT"
cd "$PARENT"

repos=(
  suplai-platform
  agente-conversacional-multi_tenant
  backend-supabase
  product-management-app
  wholesale-catalog-app
  sniffer-vendedores
  sales-engine
)

for repo in "${repos[@]}"; do
  if [[ -d "$repo/.git" ]]; then
    echo "✓ $repo ya existe, omitiendo clone"
  else
    echo "→ Clonando $repo..."
    git clone "git@github.com:${GITHUB_ORG}/${repo}.git"
  fi
done

echo ""
echo "Listo. Abrí en Cursor:"
echo "  $PARENT/suplai-platform/suplai-platform.code-workspace"
