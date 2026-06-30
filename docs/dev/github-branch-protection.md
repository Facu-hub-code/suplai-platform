# GitHub — rama feature al día con main/master

## Estado actual (Jun 2026)

| Repo | Visibilidad | Branch protection | Rama troncal |
|------|-------------|-------------------|--------------|
| `suplai-platform` | **Public** | **Activa** en `main` (`strict: true`) | `main` |
| `backend-suplai` | Private | No disponible en plan Free | `main` |
| `product-management-app` | Private | No disponible en plan Free | `main` |
| `agente-conversacional-multi_tenant` | Private | No disponible en plan Free | `master` |
| `field-app`, `tienda`, `sniffer`, `sales-engine` | Private | No disponible en plan Free | `main` |

En repos **privados** del plan Free, GitHub responde `403 Upgrade to GitHub Pro` al intentar branch protection o rulesets. No se puede bloquear el merge desde la UI sin **GitHub Pro** (o hacer el repo público).

### Qué sí configuramos en todos los repos

- **`allow_update_branch: true`** — botón *Update branch* en PRs para traer `main`/`master` sin CLI.

### `suplai-platform` (público)

Branch protection en `main`:

- **Require branches to be up to date before merging** (`strict: true`)
- Workflow CI: `.github/workflows/branch-up-to-date.yml` (check *Branch up to date with base*)

### Repos privados — alternativa hasta tener Pro

1. Copiar `.github/workflows/branch-up-to-date.yml` (template en este repo) al repo destino.
2. El check falla en rojo si el PR está *behind*, pero **no bloquea merge** hasta activar branch protection.
3. Con **GitHub Pro**: Settings → Branches → Add rule en `main`/`master`:
   - ☑ Require a pull request before merging (opcional)
   - ☑ **Require status checks to pass before merging**
   - ☑ **Require branches to be up to date before merging**
   - Status check requerido: `Branch up to date with base`

## Comandos locales (agentes y devs)

Antes de abrir o actualizar un PR:

```bash
git fetch origin
git merge origin/main    # o origin/master en agent/
# alternativa: git rebase origin/main
git push
```

Verificar si estás atrás:

```bash
git fetch origin
git rev-list --left-right --count origin/main...HEAD
# formato: <atrás> <adelante>
```

En GitHub CLI:

```bash
gh pr view --json mergeable,mergeStateStatus,statusCheckRollup
```

- `mergeStateStatus: BEHIND` → hay commits en base que faltan en tu rama
- `mergeable: CONFLICTING` → conflictos al mergear

## Template workflow

Ver `.github/workflows/branch-up-to-date.yml` en este repo. Funciona con cualquier rama base (`main`, `master`, `staging`) porque usa `github.base_ref`.

## Trabajo paralelo (equipo + agentes)

Varias features abiertas a la vez implica **una rama por directorio**, no un `checkout` compartido:

- Crear worktrees en `.worktrees/<rama>/` (cada repo debe tener `.worktrees/` en `.gitignore`).
- Operaciones de PR (`merge origin/main`, `push`, `gh pr create`) en el **worktree de esa rama**, no en el hub.
- No usar `git checkout` en el checkout principal mientras haya agentes u otra feature en curso.

Flujo completo: `docs/dev/git-workflow.md`.
