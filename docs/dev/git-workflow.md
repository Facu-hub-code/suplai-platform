# Git workflow — Suplai (equipo + agentes)

Guía para **dos devs**, **varias features en paralelo** y **agentes de IA** en el meta-workspace `suplai-platform/`.

Regla Cursor (agentes): `.cursor/rules/git-sync-and-feature-branch.mdc`  
Worktrees (solo hotfix explícito): `.cursor/rules/git-worktree-gate.mdc`  
Protección GitHub: `docs/dev/github-branch-protection.md`

## Modelo mental

```
Checkout principal (hub)     →  rama feature por defecto (feat/…, fix/…)
.worktrees/<rama>/           →  solo si pedís hotfix aislado o "creá worktree"
Cloud Agent / clon aparte    →  misma regla: rama propia; worktree no automático
```

**Un chat = un repo path = una rama.**

## Flujo diario (humano o agente)

### 1. Arrancar una feature

```bash
cd backend/   # o el repo que corresponda
git fetch origin
git checkout -b feat/mi-feature origin/main   # o checkout rama existente
git merge origin/main   # si la rama ya existía
```

En `agent/` usar `origin/master` como base.

**Worktree** — solo si lo pedís explícitamente (hotfix urgente con hub ocupado). Regla: `.cursor/rules/git-worktree-gate.mdc`.

```bash
git worktree add .worktrees/fix/mi-hotfix -b fix/mi-hotfix origin/main
cd .worktrees/fix/mi-hotfix
bash scripts/worktree/setup-worktree.sh   # desde platform/, si aplica
```

Abrir Cursor apuntando al path donde trabajás (hub o worktree).

### 2. Trabajar

- Commits cuando tenga sentido (WIP ok; squash al merge si preferís historial limpio).
- **No** implementar en `main` / `master`.
- Features cross-repo: anotar tabla repo → rama → PR en el spec o descripción del PR.

### 3. Antes del PR

```bash
cd backend/   # hub en la rama feature, o path del worktree si usaste uno
git fetch origin
git merge origin/main    # o origin/master en agent/
git push -u origin HEAD
gh pr create --base main --title "..." --body "..."
```

Verificar:

```bash
git rev-list --left-right --count origin/main...HEAD   # primer número = 0
gh pr view --json mergeable,mergeStateStatus
```

### 4. Merge y limpieza

- Merge **solo desde GitHub** (el otro dev revisa o aprueba).
- Tras merge en hub:

```bash
git checkout main && git pull origin main
git branch -d feat/mi-feature   # si ya está mergeada
```

Si usaste worktree:

```bash
git worktree remove .worktrees/fix/mi-hotfix   # solo con OK explícito
git fetch origin && git prune
```

## Convenciones

| Tema | Convención |
|------|------------|
| Nombre de rama | `feat/`, `fix/`, `chore/` + slug; opcional prefijo owner (`fl/`, `toto/`) |
| Troncal | `main` (casi todos); **`master` en `agent/`** |
| PR | Siempre hacia troncal; no push directo a main/master |
| Paralelismo | Rama feature en hub; worktree solo bajo pedido |
| Cross-repo | Merge backend/API antes que front/consumers |

## `.gitignore` por repo

Cada repo del ecosistema **debe** incluir:

```
.worktrees/
```

Así los worktrees locales no se commitean por error.

## Checklist pre-merge (repos privados sin branch protection)

Hasta tener GitHub Pro en repos privados:

- [ ] PR no está *behind* (`mergeStateStatus` ≠ `BEHIND`)
- [ ] Sin conflictos (`mergeable` ≠ `CONFLICTING`)
- [ ] CI / workflow *Branch up to date* en verde (si está copiado)
- [ ] El otro dev miró el diff (equipo de 2)
- [ ] Si es cross-repo: dependencias mergeadas en orden

## Comandos útiles

```bash
# Listar worktrees
git worktree list

# Ver ramas locales y remotas
git branch -vv

# ¿Cuántos commits atrás de main?
git fetch origin && git rev-list --count HEAD..origin/main
```

## Anti-patrones

| Evitar | Por qué |
|--------|---------|
| Worktree automático en cada feature | Stack en path equivocado; fricción innecesaria |
| Varios agentes editando la misma rama sin coordinar | Commits mezclados, conflictos |
| PR largo sin actualizar con main | Conflictos grandes al merge |
| Mergear backend y front en desorden | Front desplegado contra API vieja |
| Push a main “rápido” | Sin review; irreversible en producción |
