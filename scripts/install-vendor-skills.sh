#!/usr/bin/env bash
# Restaura skills vendor desde skills-lock.json y expone symlinks en Cursor.
# Uso: bash scripts/install-vendor-skills.sh
# Requisitos: Node.js, acceso a GitHub (repos públicos en skills-lock.json).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOCK_FILE="$ROOT/skills-lock.json"
VENDOR_DIR="$ROOT/.cursor/skills/_vendor"
AGENTS_DIR="$ROOT/.agents/skills"

if [[ ! -f "$LOCK_FILE" ]]; then
  echo "ERROR: no existe $LOCK_FILE" >&2
  exit 1
fi

echo "==> Restaurando skills desde skills-lock.json → .agents/skills/"
npx skills experimental_install -y

# Tier 3: reinstalar solo en Cursor (experimental_install puede propagar a todos los agentes)
TIER3_SKILLS=(
  brainstorming
  dispatching-parallel-agents
  executing-plans
  subagent-driven-development
  systematic-debugging
  using-git-worktrees
  verification-before-completion
  writing-plans
)
echo "==> Reinstalando Tier 3 (solo Cursor): ${TIER3_SKILLS[*]}"
npx skills add https://github.com/obra/superpowers \
  --skill "${TIER3_SKILLS[@]}" \
  --agent cursor \
  -y --copy

echo "==> Sincronizando symlinks Cursor: .cursor/skills/_vendor/ → .agents/skills/"
mkdir -p "$VENDOR_DIR"
find "$VENDOR_DIR" -mindepth 1 -maxdepth 1 ! -name 'README.md' -exec rm -rf {} +

if [[ ! -d "$AGENTS_DIR" ]]; then
  echo "ERROR: $AGENTS_DIR no existe tras la instalación" >&2
  exit 1
fi

for skill_dir in "$AGENTS_DIR"/*/; do
  [[ -d "$skill_dir" ]] || continue
  name="$(basename "$skill_dir")"
  ln -sfn "../../../.agents/skills/$name" "$VENDOR_DIR/$name"
  echo "  ✓ $name"
done

echo ""
echo "Listo. Skills Suplai custom siguen en .cursor/skills/ (sin _vendor/)."
echo "Antigravity lee .agents/skills/ directamente."
echo "Opcional (Tier 4): agent-evaluation — ver skills-vendor.manifest.json"
npx skills list 2>/dev/null | head -30 || true
