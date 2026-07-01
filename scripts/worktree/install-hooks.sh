#!/usr/bin/env bash
# Instala post-checkout hook en cada repo del manifest para auto-setup de worktrees.
# Uso: bash scripts/worktree/install-hooks.sh [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

HOOK_TEMPLATE="${SCRIPT_DIR}/hooks/post-checkout"
MANIFEST="${SCRIPT_DIR}/manifest.json"
DRY_RUN=0

[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

[[ -f "$HOOK_TEMPLATE" ]] || die "Falta plantilla: ${HOOK_TEMPLATE}"

install_hook_for_repo() {
  local repo_key="$1"
  local repo_dir="$2"
  local repo_path git_dir hooks_dir hook_path

  repo_path="$(cd "${PLATFORM_ROOT}/${repo_dir}" 2>/dev/null && pwd)" || {
    warn "Repo omitido (no existe): ${repo_dir}"
    return 0
  }

  git_dir="$(git -C "$repo_path" rev-parse --git-dir)"
  hooks_dir="$(cd "$repo_path/$git_dir/hooks" 2>/dev/null && pwd)" || {
    warn "Sin hooks dir: ${repo_path}"
    return 0
  }

  hook_path="${hooks_dir}/post-checkout"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "[dry-run] instalaría hook en ${repo_path}"
    return 0
  fi

  if [[ -f "$hook_path" ]] && ! grep -q "suplai-worktree-setup" "$hook_path" 2>/dev/null; then
    warn "post-checkout existente y no es Suplai — no sobrescribo: ${hook_path}"
    return 0
  fi

  sed "s|@SUPLAI_PLATFORM_ROOT@|${PLATFORM_ROOT}|g" "$HOOK_TEMPLATE" > "$hook_path"
  chmod +x "$hook_path"
  log "Hook instalado: ${repo_key} → ${hook_path}"
}

python3 - <<'PY' "$MANIFEST" | while IFS=$'\t' read -r key dir; do
import json, sys
data = json.load(open(sys.argv[1]))
for key, repo in data["repos"].items():
    print(f"{key}\t{repo['dir']}")
PY
  install_hook_for_repo "$key" "$dir"
done

log "Hooks listos. Al crear o hacer checkout en un worktree linked se ejecuta setup (--if-needed)."
