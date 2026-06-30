#!/usr/bin/env bash
# Borra ramas locales cuyo headRefName tiene PR MERGED en GitHub (sin PR OPEN).
set -euo pipefail

GIT="${GIT:-/usr/bin/git}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "Uso: $0 [--dry-run]" >&2; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

declare -a SPECS=(
  "agente-conversacional-multi_tenant:master"
  "backend-supabase:main"
  "product-management-app:main"
  "field-app:main"
)

delete_branch() {
  local repo="$1" trunk="$2" branch="$3"
  if [[ "$branch" == "$trunk" ]]; then return; fi
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  DRY delete: $branch"
  else
    "$GIT" -C "$repo" branch -D "$branch" 2>/dev/null || "$GIT" -C "$repo" branch -d "$branch"
    echo "  Deleted: $branch"
  fi
}

for spec in "${SPECS[@]}"; do
  name="${spec%%:*}"
  trunk="${spec#*:}"
  repo="$SOURCE_ROOT/$name"
  echo "=== $name ==="
  "$GIT" -C "$repo" fetch origin -q || { echo "  SKIP fetch"; continue; }

  current="$("$GIT" -C "$repo" branch --show-current)"
  if [[ "$current" != "$trunk" ]]; then
    echo "  checkout $trunk (desde $current)"
    if [[ $DRY_RUN -eq 0 ]]; then
      "$GIT" -C "$repo" checkout "$trunk" -q
      "$GIT" -C "$repo" pull --ff-only origin "$trunk" -q 2>/dev/null || true
    fi
  else
    if [[ $DRY_RUN -eq 0 ]]; then
      "$GIT" -C "$repo" pull --ff-only origin "$trunk" -q 2>/dev/null || true
    fi
  fi

  deleted=0
  kept=0

  while IFS= read -r b; do
    [[ -z "$b" || "$b" == "$trunk" ]] && continue
    merged=$(gh pr list --repo "Facu-hub-code/$name" --head "$b" --state merged --json number --jq 'length' 2>/dev/null || echo 0)
    open=$(gh pr list --repo "Facu-hub-code/$name" --head "$b" --state open --json number --jq 'length' 2>/dev/null || echo 0)
    if [[ "${merged:-0}" -gt 0 && "${open:-0}" -eq 0 ]]; then
      delete_branch "$repo" "$trunk" "$b"
      deleted=$((deleted + 1))
    else
      echo "  Keep: $b (merged=$merged open=$open)"
      kept=$((kept + 1))
    fi
  done < <("$GIT" -C "$repo" for-each-ref refs/heads/ --format='%(refname:short)')
  echo "  → $deleted borrada(s), $kept conservada(s)"
  echo
done
