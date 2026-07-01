#!/usr/bin/env bash
# Funciones compartidas para setup de worktrees Suplai.
set -euo pipefail

WORKTREE_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_SCRIPTS_DIR="$(cd "${WORKTREE_LIB_DIR}/.." && pwd)"
PLATFORM_ROOT="$(cd "${WORKTREE_SCRIPTS_DIR}/../.." && pwd)"
MANIFEST="${WORKTREE_SCRIPTS_DIR}/manifest.json"
STAMP_NAME=".worktree-setup-stamp"

log() { printf '[worktree-setup] %s\n' "$*"; }
warn() { printf '[worktree-setup] WARN: %s\n' "$*" >&2; }
die() { printf '[worktree-setup] ERROR: %s\n' "$*" >&2; exit 1; }

is_linked_worktree() {
  local git_dir git_common
  git_dir="$(git -C "$1" rev-parse --git-dir 2>/dev/null | xargs -I{} sh -c 'cd "{}" 2>/dev/null && pwd -P' || true)"
  git_common="$(git -C "$1" rev-parse --git-common-dir 2>/dev/null | xargs -I{} sh -c 'cd "{}" 2>/dev/null && pwd -P' || true)"
  [[ -n "$git_dir" && -n "$git_common" && "$git_dir" != "$git_common" ]]
}

hub_worktree_path() {
  local target="$1"
  git -C "$target" worktree list --porcelain | awk '
    $1 == "worktree" { path = $2 }
    $1 == "branch" && $2 == "refs/heads/main" { print path; exit }
    $1 == "branch" && $2 == "refs/heads/master" { print path; exit }
  '
}

resolve_repo_key() {
  local target abs_target repo_dir abs_repo
  target="$(cd "$1" && pwd)"
  python3 - <<'PY' "$MANIFEST" "$target"
import json, os, sys
manifest_path, target = sys.argv[1], os.path.realpath(sys.argv[2])
with open(manifest_path, encoding="utf-8") as f:
    data = json.load(f)
platform_root = os.path.dirname(os.path.dirname(os.path.dirname(manifest_path)))
best = None
for key, repo in data["repos"].items():
    repo_dir = os.path.realpath(os.path.join(platform_root, repo["dir"]))
    if target == repo_dir or target.startswith(repo_dir + os.sep):
        if best is None or len(repo_dir) > len(best[1]):
            best = (key, repo_dir)
if best:
    print(best[0])
PY
}

manifest_get() {
  local key field
  key="$1"
  field="$2"
  python3 - <<'PY' "$MANIFEST" "$key" "$field"
import json, sys
manifest_path, key, field = sys.argv[1], sys.argv[2], sys.argv[3]
with open(manifest_path, encoding="utf-8") as f:
    data = json.load(f)
repo = data["repos"][key]
if field == "dev_port":
    print(repo.get("dev_port", data["ports"].get(key, "")))
elif field == "dir":
    print(repo["dir"])
else:
    val = repo.get(field, "")
    if isinstance(val, (dict, list)):
        import json as j
        print(j.dumps(val))
    else:
        print(val or "")
PY
}

link_or_copy_env() {
  local target="$1"
  local hub="$2"
  shift 2
  local files=("$@")
  local f hub_file target_file
  for f in "${files[@]}"; do
    [[ -n "$f" ]] || continue
    hub_file="${hub}/${f}"
    target_file="${target}/${f}"
    if [[ -e "$target_file" ]]; then
      log "Env ya presente: ${target_file}"
      continue
    fi
    if [[ -f "$hub_file" ]]; then
      ln -s "$hub_file" "$target_file"
      log "Symlink env: ${f} ← hub"
    fi
  done
}

ensure_env_from_template() {
  local target="$1"
  local template="$2"
  shift 2
  local files=("$@")
  local f target_file template_file
  template_file="${target}/${template}"
  for f in "${files[@]}"; do
    target_file="${target}/${f}"
    [[ -e "$target_file" ]] && continue
    if [[ -f "$template_file" ]]; then
      cp "$template_file" "$target_file"
      warn "Creé ${f} desde ${template}. Completá secretos antes de probar."
    fi
  done
}

write_dev_env_file() {
  local target="$1"
  local repo_key="$2"
  local port dev_cmd
  port="$(manifest_get "$repo_key" dev_port)"
  dev_cmd="$(manifest_get "$repo_key" dev_command)"
  cat > "${target}/.worktree-dev.env" <<EOF
# Generado por platform/scripts/worktree/setup-worktree.sh — no commitear
SUPLAI_REPO=${repo_key}
SUPLAI_DEV_PORT=${port}
# shellcheck disable=SC2148
SUPLAI_DEV_COMMAND=${dev_cmd}
EOF
  log "Escrito ${target}/.worktree-dev.env (puerto ${port})"
}

needs_setup() {
  local target="$1"
  local stamp="${target}/${STAMP_NAME}"
  [[ ! -f "$stamp" ]] && return 0
  local dep
  for dep in requirements.txt package.json pyproject.toml; do
    [[ -f "${target}/${dep}" && "${target}/${dep}" -nt "$stamp" ]] && return 0
  done
  return 1
}

touch_stamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "$1/${STAMP_NAME}"
}

setup_python_repo() {
  local target="$1"
  local repo_key="$2"
  local hub venv_dir req
  hub="$(hub_worktree_path "$target")"
  venv_dir="$(manifest_get "$repo_key" venv_dir)"
  req="$(manifest_get "$repo_key" requirements)"
  venv_dir="${venv_dir:-venv}"

  if [[ -d "${target}/${venv_dir}" ]]; then
    log "venv presente en worktree"
  elif [[ -n "$hub" && -d "${hub}/${venv_dir}" ]]; then
    ln -s "${hub}/${venv_dir}" "${target}/${venv_dir}"
    log "Symlink ${venv_dir} ← hub"
  else
    log "Creando venv en worktree..."
    python3 -m venv "${target}/${venv_dir}"
    # shellcheck disable=SC1091
    source "${target}/${venv_dir}/bin/activate"
    if [[ -n "$req" && -f "${target}/${req}" ]]; then
      pip install -q -r "${target}/${req}"
    fi
  fi
}

setup_next_repo() {
  local target="$1"
  local repo_key="$2"
  local hub
  hub="$(hub_worktree_path "$target")"

  if [[ -d "${target}/node_modules" ]]; then
    log "node_modules presente en worktree"
    return 0
  fi
  if [[ -n "$hub" && -d "${hub}/node_modules" ]]; then
    ln -s "${hub}/node_modules" "${target}/node_modules"
    log "Symlink node_modules ← hub"
    return 0
  fi
  if [[ -f "${target}/package-lock.json" ]]; then
    log "npm ci..."
    (cd "$target" && npm ci)
  elif [[ -f "${target}/package.json" ]]; then
    log "npm install..."
    (cd "$target" && npm install)
  fi
}

setup_platform_repo() {
  local target="$1"
  if [[ -f "${target}/requirements.txt" ]] && [[ ! -d "${target}/.venv" ]]; then
    python3 -m venv "${target}/.venv"
    # shellcheck disable=SC1091
    source "${target}/.venv/bin/activate"
    pip install -q -r "${target}/requirements.txt"
  fi
}

run_repo_hook() {
  local target="$1"
  local hook="${target}/scripts/worktree/setup.sh"
  if [[ -x "$hook" ]]; then
    log "Ejecutando hook local: ${hook}"
    SUPLAI_PLATFORM_ROOT="$PLATFORM_ROOT" SUPLAI_WORKTREE_PATH="$target" "$hook"
  fi
}
