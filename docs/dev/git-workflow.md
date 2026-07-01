# Git workflow — Suplai (equipo + agentes)

Guía para **dos devs**, **varias features en paralelo** y **agentes de IA** en el meta-workspace `suplai-platform/`.

Regla Cursor (agentes): `.cursor/rules/git-sync-and-feature-branch.mdc`  
Gate worktrees (preguntar antes/después): `.cursor/rules/git-worktree-gate.mdc`  
Protección GitHub: `docs/dev/github-branch-protection.md`

## Modelo mental

```
Checkout principal (hub)     →  no cambiar de rama si hay agentes activos
.worktrees/<rama>/           →  una feature / un chat / un agente
Cloud Agent / clon aparte    →  misma regla: directorio aislado + rama propia
```

**Un chat = un repo path = una rama.**

## Flujo diario (humano o agente)

### 1. Arrancar una feature

**Antes de crear un worktree**, el agente debe preguntar si conviene (hotfix puntual, solo lectura, feature paralela, o reutilizar uno existente). Regla: `.cursor/rules/git-worktree-gate.mdc`.

```bash
cd backend/   # o el repo que corresponda
git fetch origin

# Verificar ignore (una vez por repo)
grep -q '^\.worktrees/' .gitignore || echo '.worktrees/' >> .gitignore

git worktree add .worktrees/feat/mi-feature -b feat/mi-feature origin/main
cd .worktrees/feat/mi-feature
```

**Setup de entorno local** (deps, `.env`, puertos): ver [`worktree-local-dev.md`](./worktree-local-dev.md). Atajo:

```bash
# desde platform/
bash scripts/worktree/add-worktree.sh backend feat/mi-feature
# o, si el worktree ya existe:
bash scripts/worktree/setup-worktree.sh path/al/worktree
```

En `agent/` usar `origin/master` como base.

Abrir Cursor / chat apuntando al path del worktree (o Cloud Agent con rama nueva).

### 2. Trabajar

- Commits cuando tenga sentido (WIP ok; squash al merge si preferís historial limpio).
- **No** `git checkout` en el directorio hub si otro agente usa ese repo.
- Features cross-repo: anotar tabla repo → rama → PR en el spec o descripción del PR.

### 3. Antes del PR

```bash
cd .worktrees/feat/mi-feature
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
- Tras merge:

```bash
git worktree remove .worktrees/feat/mi-feature
git branch -d feat/mi-feature   # si ya está mergeada
git fetch origin && git prune
```

## Convenciones

| Tema | Convención |
|------|------------|
| Nombre de rama | `feat/`, `fix/`, `chore/` + slug; opcional prefijo owner (`fl/`, `toto/`) |
| Troncal | `main` (casi todos); **`master` en `agent/`** |
| PR | Siempre hacia troncal; no push directo a main/master |
| Paralelismo | Worktree o Cloud Agent — nunca mezclar features en un working tree |
| Cross-repo | Merge backend/API antes que front/consumers |

## `.gitignore` por repo

Cada repo del ecosistema **debe** incluir:

```
.worktrees/
```

Así los worktrees locales no se commitean por error. En `suplai-platform` ya está configurado.

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
| Varios agentes en el mismo path sin worktree | Commits en rama equivocada, conflictos, pulls que pisan WIP |
| Worktree nuevo sin preguntar / para la misma feature | Duplicación, diffs divergentes, PRs conflictivos |
| `checkout -b` en hub con agentes corriendo | Cambia la rama bajo otro chat |
| PR largo sin actualizar con main | Conflictos grandes al merge |
| Mergear backend y front en desorden | Front desplegado contra API vieja |
| Push a main “rápido” | Sin review; irreversible en producción |
