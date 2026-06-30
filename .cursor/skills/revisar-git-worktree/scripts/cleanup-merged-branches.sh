#!/usr/bin/env bash
# Borra ramas locales mergeadas en origin/<troncal>. Excluye main/master.
# Uso: cleanup-merged-branches.sh [--dry-run] [--repo PATH] [--trunk main|master]
set -euo pipefail

DRY_RUN=0
SINGLE_REPO=""
FORCED_TRUNK=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --repo) SINGLE_REPO="${2:?}"; shift 2 ;;
    --trunk) FORCED_TRUNK="${2:?}"; shift 2 ;;
    *) echo "Opción desconocida: $1" >&2; exit 1 ;;
  esac
done

GIT="${GIT:-/usr/bin/git}"

troncal_for() {
  local repo="$1"
  if [[ -n "$FORCED_TRUNK" ]]; then echo "$FORCED_TRUNK"; return; fi
  local ref
  ref="$("$GIT" -C "$repo" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null || true)"
  if [[ -n "$ref" ]]; then echo "${ref#refs/remotes/origin/}"; return; fi
  if "$GIT" -C "$repo" show-ref --verify --quiet refs/heads/master; then echo master; return; fi
  echo main
}

cleanup_repo() {
  local name="$1" repo="$2"
  echo ""
  echo "=== $name ==="
  echo "Path: $repo"

  if ! "$GIT" -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
    echo "SKIP: no es repo git"
    return
  fi

  "$GIT" -C "$repo" fetch origin --prune -q || { echo "SKIP: fetch falló"; return; }

  local dirty trunk current
  dirty="$("$GIT" -C "$repo" status --porcelain | /usr/bin/grep -c '^[^? ]' || true)"
  dirty="${dirty:-0}"
  if [[ "$dirty" -gt 0 ]]; then
    echo "SKIP: $dirty archivo(s) con cambios sin commitear"
    return
  fi

  trunk="$(troncal_for "$repo")"
  current="$("$GIT" -C "$repo" branch --show-current)"

  if ! "$GIT" -C "$repo" show-ref --verify --quiet "refs/remotes/origin/$trunk"; then
    echo "SKIP: no existe origin/$trunk"
    return
  fi

  # Actualizar ref local de troncal sin checkout destructivo
  if "$GIT" -C "$repo" show-ref --verify --quiet "refs/heads/$trunk"; then
    if [[ $DRY_RUN -eq 0 ]]; then
      "$GIT" -C "$repo" fetch origin "$trunk:$trunk" -q 2>/dev/null || true
    fi
  fi

  # Si estamos en rama mergeada, mover a troncal para poder borrarla
  if [[ -n "$current" && "$current" != "$trunk" ]]; then
    if "$GIT" -C "$repo" merge-base --is-ancestor "$current" "origin/$trunk" 2>/dev/null; then
      echo "Checkout: $current → $trunk (rama actual ya mergeada)"
      if [[ $DRY_RUN -eq 0 ]]; then
        "$GIT" -C "$repo" checkout "$trunk" -q
        "$GIT" -C "$repo" pull --ff-only origin "$trunk" -q 2>/dev/null || true
      fi
      current="$trunk"
    else
      echo "Mantener rama actual (no mergeada): $current"
    fi
  fi

  local branches deleted=0 skipped=0
  branches="$("$GIT" -C "$repo" branch --merged "origin/$trunk" | /usr/bin/sed 's/^[*+ ] //' | /usr/bin/grep -vE "^(main|master)$" || true)"

  if [[ -z "$branches" ]]; then
    echo "Nada que borrar."
    return
  fi

  while IFS= read -r b; do
    [[ -z "$b" ]] && continue
    if [[ "$b" == "$current" ]]; then
      echo "SKIP (checkout actual, no mergeada en troncal): $b"
      skipped=$((skipped + 1))
      continue
    fi
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "DRY-RUN delete: $b"
    else
      if "$GIT" -C "$repo" branch -d "$b"; then
        echo "Deleted: $b"
      else
        echo "FAIL delete: $b"
        skipped=$((skipped + 1))
        continue
      fi
    fi
    deleted=$((deleted + 1))
  done <<< "$branches"

  echo "Resumen: ${deleted} borrada(s), ${skipped} omitida(s)"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

declare -a SPECS=(
  "agent:$SOURCE_ROOT/agente-conversacional-multi_tenant"
  "backend:$SOURCE_ROOT/backend-supabase"
  "backoffice:$SOURCE_ROOT/product-management-app"
  "tienda:$SOURCE_ROOT/wholesale-catalog-app"
  "field-app:$SOURCE_ROOT/field-app"
  "sniffer:$SOURCE_ROOT/sniffer-vendedores"
  "sales-engine:$SOURCE_ROOT/sales-engine"
)

echo "# Limpieza ramas mergeadas (excluye suplai-platform)"
[[ $DRY_RUN -eq 1 ]] && echo "MODO DRY-RUN"

if [[ -n "$SINGLE_REPO" ]]; then
  cleanup_repo "$(basename "$SINGLE_REPO")" "$(cd "$SINGLE_REPO" && pwd)"
else
  for spec in "${SPECS[@]}"; do
    name="${spec%%:*}"
    repo="${spec#*:}"
    cleanup_repo "$name" "$repo"
  done
fi
