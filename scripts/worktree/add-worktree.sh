#!/usr/bin/env bash
# Crea worktree + setup de entorno local.
# Uso:
#   bash scripts/worktree/add-worktree.sh <repo> <rama> [base-remota]
#
# Ejemplos:
#   bash scripts/worktree/add-worktree.sh backend fix/benfresh-odoo-client-sync
#   bash scripts/worktree/add-worktree.sh backoffice feat/erp-ui origin/main
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

REPO="${1:-}"
BRANCH="${2:-}"
BASE="${3:-}"

usage() {
  cat <<EOF
Uso: $(basename "$0") <repo> <rama> [base-remota]

Repos en manifest: $(python3 - <<'PY' "$MANIFEST"
import json, sys
print(", ".join(json.load(open(sys.argv[1]))["repos"].keys()))
PY
)

Ejemplo:
  $(basename "$0") backend fix/benfresh-odoo-client-sync origin/main
EOF
}

[[ -n "$REPO" && -n "$BRANCH" ]] || { usage; exit 1; }

REPO_DIR_REL="$(manifest_get "$REPO" dir)"
DEFAULT_BRANCH="$(manifest_get "$REPO" default_branch)"
BASE="${BASE:-origin/${DEFAULT_BRANCH}}"

REPO_PATH="$(cd "${PLATFORM_ROOT}/${REPO_DIR_REL}" && pwd)"
WORKTREE_PATH="${REPO_PATH}/.worktrees/${BRANCH}"

if [[ ! -d "$REPO_PATH/.git" && ! -f "$REPO_PATH/.git" ]]; then
  die "Repo no encontrado: ${REPO_PATH}"
fi

git -C "$REPO_PATH" check-ignore -q .worktrees 2>/dev/null || {
  die "Agregá .worktrees/ al .gitignore de ${REPO} antes de crear worktrees"
}

git -C "$REPO_PATH" fetch origin

if [[ -d "$WORKTREE_PATH" ]]; then
  die "Ya existe worktree: ${WORKTREE_PATH}"
fi

mkdir -p "$(dirname "$WORKTREE_PATH")"

if git -C "$REPO_PATH" show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  git -C "$REPO_PATH" worktree add "$WORKTREE_PATH" "$BRANCH"
else
  git -C "$REPO_PATH" worktree add "$WORKTREE_PATH" -b "$BRANCH" "$BASE"
fi

bash "${SCRIPT_DIR}/setup-worktree.sh" "$WORKTREE_PATH"

cat <<EOF

Worktree creado:
  repo:  ${REPO}
  path:  ${WORKTREE_PATH}
  rama:  ${BRANCH}

Dev (ver .worktree-dev.env):
  cd ${WORKTREE_PATH}
  $(manifest_get "$REPO" dev_command)

Cursor: move_agent_to_root → ${WORKTREE_PATH}
EOF
