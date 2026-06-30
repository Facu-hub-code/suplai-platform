#!/usr/bin/env bash
# Reporte de worktrees y ramas locales — Suplai meta-workspace
set -euo pipefail

NO_FETCH=0
SINGLE_REPO=""
PLATFORM_ROOT=""
ALL_BRANCHES=0

usage() {
  cat <<'EOF'
Uso: report-worktrees.sh [--no-fetch] [--repo PATH] [--root PATH]

  --no-fetch   No ejecutar git fetch origin (más rápido; remoto puede estar desactualizado)
  --repo PATH  Analizar un solo repositorio git
  --root PATH  Raíz del meta-workspace (default: detecta suplai-platform desde el script)
  --all-branches  Listar todas las ramas locales extra (default: solo las que no son SEGURO)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-fetch) NO_FETCH=1; shift ;;
    --all-branches) ALL_BRANCHES=1; shift ;;
    --repo) SINGLE_REPO="${2:?}"; shift 2 ;;
    --root) PLATFORM_ROOT="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Opción desconocida: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$PLATFORM_ROOT" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PLATFORM_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
fi

# Mapa repo → path relativo al directorio padre de platform (../)
declare -a REPO_NAMES=()
declare -a REPO_PATHS=()

add_repo() {
  local name="$1"
  local path="$2"
  if [[ -e "$path/.git" ]]; then
    REPO_NAMES+=("$name")
    REPO_PATHS+=("$path")
  fi
}

discover_repos() {
  REPO_NAMES=()
  REPO_PATHS=()

  if [[ -n "$SINGLE_REPO" ]]; then
    local abs
    abs="$(cd "$SINGLE_REPO" && pwd)"
    add_repo "$(basename "$abs")" "$abs"
    return
  fi

  local ws="$PLATFORM_ROOT/suplai-platform.code-workspace"
  if [[ -f "$ws" ]] && command -v python3 >/dev/null 2>&1; then
    while IFS=$'\t' read -r name repo_path; do
      [[ -z "$name" || -z "$repo_path" ]] && continue
      add_repo "$name" "$repo_path"
    done < <(python3 - "$ws" "$PLATFORM_ROOT" <<'PY'
import json, sys, os
ws, root = sys.argv[1], sys.argv[2]
with open(ws) as f:
    data = json.load(f)
for folder in data.get("folders", []):
    name = folder.get("name", "")
    rel = folder.get("path", "")
    if rel == ".":
        path = root
    else:
        path = os.path.normpath(os.path.join(root, rel))
    print(f"{name}\t{path}")
PY
)
  fi

  # Fallback: repos conocidos del ecosistema Suplai
  if [[ ${#REPO_NAMES[@]} -eq 0 ]]; then
    local parent
    parent="$(cd "$PLATFORM_ROOT/.." && pwd)"
    add_repo "platform" "$PLATFORM_ROOT"
    add_repo "agent" "$parent/agente-conversacional-multi_tenant"
    add_repo "backend" "$parent/backend-supabase"
    add_repo "backoffice" "$parent/product-management-app"
    add_repo "tienda" "$parent/wholesale-catalog-app"
    add_repo "field-app" "$parent/field-app"
    add_repo "sniffer" "$parent/sniffer-vendedores"
    add_repo "sales-engine" "$parent/sales-engine"
  fi

  # Completar repos del fallback que falten en workspace file
  local parent
  parent="$(cd "$PLATFORM_ROOT/.." && pwd)"
  local -a extras=(
    "field-app:$parent/field-app"
    "sniffer:$parent/sniffer-vendedores"
  )
  for pair in "${extras[@]}"; do
    local en="${pair%%:*}"
    local ep="${pair#*:}"
    local found=0
    for i in "${!REPO_NAMES[@]}"; do
      if [[ "${REPO_NAMES[$i]}" == "$en" ]]; then found=1; break; fi
    done
    [[ $found -eq 0 ]] && add_repo "$en" "$ep"
  done
}

troncal_branch() {
  local repo="$1"
  local ref
  ref="$(git -C "$repo" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null || true)"
  if [[ -n "$ref" ]]; then
    echo "${ref#refs/remotes/origin/}"
    return
  fi
  if git -C "$repo" show-ref --verify --quiet refs/heads/main; then echo main; return; fi
  if git -C "$repo" show-ref --verify --quiet refs/heads/master; then echo master; return; fi
  echo main
}

is_troncal() {
  local branch="$1"
  local troncal="$2"
  branch="${branch#refs/heads/}"
  [[ "$branch" == "$troncal" ]]
}

branch_short() {
  local b="$1"
  b="${b#refs/heads/}"
  echo "$b"
}

branch_on_origin() {
  local repo="$1" branch="$2"
  branch="$(branch_short "$branch")"
  git -C "$repo" show-ref --verify --quiet "refs/remotes/origin/$branch" 2>/dev/null
}

count_dirty() {
  local repo="$1"
  local modified staged untracked
  modified="$(git -C "$repo" status --porcelain | grep -c '^[^? ]' || true)"
  staged="$(git -C "$repo" diff --cached --quiet 2>/dev/null; echo $?)"
  untracked="$(git -C "$repo" status --porcelain | grep -c '^??' || true)"
  echo "${modified}|${untracked}"
}

safe_verdict() {
  local hub="$1" troncal="$2" branch="$3" on_origin="$4" ahead="$5" behind="$6" mod="$7" untracked="$8" merged="$9" is_wt="${10}"

  if is_troncal "$branch" "$troncal"; then
    if [[ "$hub" == "hub" ]]; then
      echo "NO — checkout principal en troncal"
      return
    fi
    echo "NO — worktree en troncal"
    return
  fi

  if [[ "$mod" -gt 0 ]]; then
    echo "NO — cambios sin commitear ($mod archivos)"
    return
  fi

  if [[ "$ahead" -gt 0 ]]; then
    echo "REVISAR — $ahead commit(s) sin push"
    return
  fi

  if [[ "$untracked" -gt 0 ]]; then
    echo "REVISAR — $untracked archivo(s) sin trackear (worktree limpio al borrar si no importan)"
    return
  fi

  if [[ "$on_origin" == "no" ]]; then
    if [[ "$merged" == "yes" ]]; then
      if [[ "$hub" == "hub" ]]; then
        echo "REVISAR — mergeada; hacer checkout a $troncal y luego git branch -d"
        return
      fi
      echo "SEGURO — solo local, ya mergeada en $troncal"
      return
    fi
    echo "REVISAR — rama no existe en origin"
    return
  fi

  if [[ "$behind" -gt 0 ]]; then
    echo "REVISAR — $behind commit(s) detrás de origin/$branch"
    return
  fi

  if [[ "$merged" == "yes" ]]; then
    if [[ "$hub" == "hub" ]]; then
      echo "REVISAR — mergeada; hacer checkout a $troncal y luego git branch -d"
      return
    fi
    if [[ "$is_wt" == "branch" ]]; then
      echo "SEGURO — mergeada; git branch -d OK"
    else
      echo "SEGURO — mergeada; git worktree remove OK"
    fi
    return
  fi

  if [[ "$hub" == "hub" ]]; then
    echo "NO — checkout principal (no borrar; usar otro worktree para features)"
    return
  fi

  echo "REVISAR — rama activa sin merge confirmado en $troncal"
}

report_repo() {
  local name="$1"
  local repo="$2"

  echo "## $name"
  echo ""
  echo "**Path:** \`$repo\`"

  if [[ $NO_FETCH -eq 0 ]]; then
    git -C "$repo" fetch origin --prune --quiet 2>/dev/null || echo "_fetch origin falló (sin red o sin remoto)_"
  fi

  local troncal hub_path
  troncal="$(troncal_branch "$repo")"
  hub_path="$(git -C "$repo" rev-parse --show-toplevel)"

  echo "**Troncal:** \`$troncal\`"
  echo ""

  local wt_file
  wt_file="$(mktemp)"
  git -C "$repo" worktree list --porcelain > "$wt_file"

  echo "| Ubicación | Rama | Tipo | En origin | vs origin | Sin commitear | Sin trackear | ¿Seguro borrar? |"
  echo "|-----------|------|------|-----------|-----------|---------------|--------------|-----------------|"

  local wt_path="" wt_branch="" wt_head=""
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      worktree*)
        wt_path="${line#worktree }"
        ;;
      HEAD)
        wt_head="${line#HEAD }"
        ;;
      branch*)
        wt_branch="${line#branch }"
        ;;
      detached)
        wt_branch="(detached)"
        ;;
      "")
        if [[ -n "$wt_path" ]]; then
          emit_worktree_row "$repo" "$hub_path" "$troncal" "$wt_path" "$wt_branch" "$wt_head"
          wt_path=""; wt_branch=""; wt_head=""
        fi
        ;;
    esac
  done < "$wt_file"
  if [[ -n "$wt_path" ]]; then
    emit_worktree_row "$repo" "$hub_path" "$troncal" "$wt_path" "$wt_branch" "$wt_head"
  fi
  rm -f "$wt_file"

  # Ramas locales sin worktree dedicado (solo ref en hub)
  echo ""
  echo "### Ramas locales adicionales (sin worktree propio)"
  echo ""
  local branches
  branches="$(git -C "$repo" for-each-ref --format='%(refname:short)' refs/heads/ | sort)"
  local any_extra=0
  while IFS= read -r b; do
    [[ -z "$b" ]] && continue
    local in_wt=0
    while IFS= read -r wline; do
      if [[ "$wline" =~ \[$b\] ]] || [[ "$wline" == *"[$b]"* ]]; then in_wt=1; break; fi
    done < <(git -C "$repo" worktree list)
    if [[ $in_wt -eq 1 ]]; then continue; fi
    local row
    row="$(emit_branch_row "$repo" "$troncal" "$b")"
    if [[ $ALL_BRANCHES -eq 1 ]] || [[ "$row" != *"SEGURO"* ]]; then
      any_extra=1
      echo "$row"
    fi
  done <<< "$branches"

  if [[ $any_extra -eq 0 ]]; then
    if [[ $ALL_BRANCHES -eq 0 ]]; then
      echo "_Ninguna pendiente (usar --all-branches para listado completo)_"
    else
      echo "_Ninguna_"
    fi
  fi
  echo ""
}

emit_worktree_row() {
  local repo="$1" hub_path="$2" troncal="$3" wt_path="$4" branch="$5" head="$6"
  local branch_name
  branch_name="$(branch_short "$branch")"

  local tipo="worktree"
  local hub="worktree"
  if [[ "$wt_path" == "$hub_path" ]]; then
    tipo="hub"
    hub="hub"
  fi

  local on_origin="no" ahead=0 behind=0 upstream=""
  local mod=0 untracked=0
  local merged="no"
  local vs_origin="—"

  if [[ "$branch" != "(detached)" && -n "$branch" ]]; then
    if branch_on_origin "$repo" "$branch_name"; then
      on_origin="sí"
    fi
    upstream="$(git -C "$wt_path" rev-parse --abbrev-ref '@{u}' 2>/dev/null || true)"
    if [[ -n "$upstream" ]]; then
      read -r behind ahead _ <<< "$(git -C "$wt_path" rev-list --left-right --count '@{u}...HEAD' 2>/dev/null || echo '0 0')"
      behind="${behind:-0}"
      ahead="${ahead:-0}"
      vs_origin="↑$ahead ↓$behind"
    elif [[ "$on_origin" == "sí" ]]; then
      vs_origin="sin upstream local"
    else
      vs_origin="solo local"
    fi
    if git -C "$repo" merge-base --is-ancestor "$branch_name" "origin/$troncal" 2>/dev/null; then
      merged="yes"
    fi
  else
    branch_name="(detached @ ${head:0:7})"
    vs_origin="—"
  fi

  IFS='|' read -r mod untracked <<< "$(count_dirty "$wt_path")"
  mod="${mod:-0}"
  untracked="${untracked:-0}"
  local safe
  safe="$(safe_verdict "$hub" "$troncal" "$branch_name" "$on_origin" "$ahead" "$behind" "$mod" "$untracked" "$merged" "$tipo")"

  local short_path="$wt_path"
  if [[ ${#short_path} -gt 48 ]]; then
    short_path="…${short_path: -45}"
  fi

  echo "| \`$short_path\` | \`$branch_name\` | $tipo | $on_origin | $vs_origin | $mod | $untracked | $safe |"
}

emit_branch_row() {
  local repo="$1" troncal="$2" branch="$3"

  local on_origin="no" ahead=0 behind=0 vs_origin="—"
  local merged="no"

  if branch_on_origin "$repo" "$branch"; then
    on_origin="sí"
  fi
  local upstream
  upstream="$(git -C "$repo" rev-parse --abbrev-ref "$branch@{u}" 2>/dev/null || true)"
  if [[ -n "$upstream" ]]; then
    read -r behind ahead _ <<< "$(git -C "$repo" rev-list --left-right --count "$branch@{u}...$branch" 2>/dev/null || echo '0 0')"
    behind="${behind:-0}"
    ahead="${ahead:-0}"
    vs_origin="↑$ahead ↓$behind"
  elif [[ "$on_origin" == "sí" ]]; then
    vs_origin="sin upstream local"
  else
    vs_origin="solo local"
  fi
  if git -C "$repo" merge-base --is-ancestor "$branch" "origin/$troncal" 2>/dev/null; then
    merged="yes"
  fi

  local safe
  safe="$(safe_verdict "branch-only" "$troncal" "$branch" "$on_origin" "$ahead" "$behind" "0" "0" "$merged" "branch")"

  echo "| \`$branch\` | ref local | $on_origin | $vs_origin | — | — | $safe |"
}

# --- main ---
discover_repos

if [[ ${#REPO_NAMES[@]} -eq 0 ]]; then
  echo "No se encontraron repositorios git." >&2
  exit 1
fi

echo "# Reporte Git Worktrees — Suplai"
echo ""
echo "_Generado: $(date '+%Y-%m-%d %H:%M %Z')_"
if [[ $NO_FETCH -eq 1 ]]; then
  echo "_Modo: --no-fetch (estado remoto puede estar desactualizado)_"
else
  echo "_Modo: git fetch origin --prune en cada repo_"
fi
echo ""

for i in "${!REPO_NAMES[@]}"; do
  report_repo "${REPO_NAMES[$i]}" "${REPO_PATHS[$i]}"
done

echo "---"
echo ""
echo "**Leyenda vs origin:** ↑N = commits locales sin push · ↓N = commits en origin que faltan local"
echo ""
echo "**Borrado sugerido (worktree):** \`git worktree remove <path>\` · **rama:** \`git branch -d <rama>\`"
echo ""
echo "**Nunca borrar sin confirmar:** checkout principal (hub), troncal, cambios sin commitear, commits sin push."
