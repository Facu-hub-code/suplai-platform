#!/usr/bin/env bash
# Configura entorno local de un worktree (deps, env, puertos).
# Uso:
#   bash scripts/worktree/setup-worktree.sh [PATH]
#   bash scripts/worktree/setup-worktree.sh --if-needed [PATH]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

IF_NEEDED=0
TARGET="${PWD}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --if-needed) IF_NEEDED=1; shift ;;
    -h|--help)
      cat <<'EOF'
Uso: setup-worktree.sh [--if-needed] [PATH]

  --if-needed   Omite si .worktree-setup-stamp está al día
  PATH          Raíz del worktree (default: cwd)

Escribe .worktree-dev.env con puerto y comando sugerido.
EOF
      exit 0
      ;;
    *)
      TARGET="$(cd "$1" && pwd)"
      shift
      ;;
  esac
done

[[ -d "${TARGET}/.git" || -f "${TARGET}/.git" ]] || die "No es un checkout git: ${TARGET}"

if ! is_linked_worktree "$TARGET"; then
  log "Checkout principal (hub) — setup opcional; continuando."
fi

if [[ "$IF_NEEDED" -eq 1 ]] && ! needs_setup "$TARGET"; then
  log "Setup al día (${TARGET}/${STAMP_NAME})"
  exit 0
fi

REPO_KEY="$(resolve_repo_key "$TARGET" || true)"
[[ -n "$REPO_KEY" ]] || die "Repo no reconocido en manifest.json para ${TARGET}"

STACK="$(manifest_get "$REPO_KEY" stack)"
ENV_FILES_JSON="$(manifest_get "$REPO_KEY" env_files)"
ENV_TEMPLATE="$(manifest_get "$REPO_KEY" env_template)"
HUB="$(hub_worktree_path "$TARGET" || true)"

log "Repo=${REPO_KEY} stack=${STACK} path=${TARGET}"

# Parse env_files JSON array
ENV_FILES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && ENV_FILES+=("$line")
done < <(python3 - <<'PY' "$ENV_FILES_JSON"
import json, sys
for item in json.loads(sys.argv[1] or "[]"):
    print(item)
PY
)

if [[ -n "$HUB" ]]; then
  link_or_copy_env "$TARGET" "$HUB" "${ENV_FILES[@]}"
fi
if [[ -n "$ENV_TEMPLATE" ]]; then
  ensure_env_from_template "$TARGET" "$ENV_TEMPLATE" "${ENV_FILES[@]}"
fi

case "$STACK" in
  python) setup_python_repo "$TARGET" "$REPO_KEY" ;;
  next) setup_next_repo "$TARGET" "$REPO_KEY" ;;
  platform) setup_platform_repo "$TARGET" ;;
  *) warn "Stack desconocido: ${STACK}" ;;
esac

run_repo_hook "$TARGET"
write_dev_env_file "$TARGET" "$REPO_KEY"
touch_stamp "$TARGET"

log "Listo. Comando sugerido:"
dev_cmd="$(manifest_get "$REPO_KEY" dev_command)"
printf '  cd %s\n  %s\n' "$TARGET" "$dev_cmd"
