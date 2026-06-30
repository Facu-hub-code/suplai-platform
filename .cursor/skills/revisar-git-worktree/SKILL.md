---
name: revisar-git-worktree
description: >-
  Audita worktrees y ramas locales del meta-workspace Suplai: estado vs origin,
  cambios sin commitear/trackear y si es seguro borrarlas. Usar cuando el
  usuario pida revisar worktrees, limpiar ramas locales, auditar git en
  paralelo o saber qué checkout/worktree puede eliminarse.
---

# Revisar Git Worktree

## Cuándo usar

- Antes de limpiar worktrees o ramas locales.
- Para saber qué features siguen activas en disco.
- Tras merge de PRs, para validar qué directorios `.worktrees/` borrar.
- Auditoría periódica del meta-workspace (8 repos).

Anunciar al inicio: _"Uso la skill revisar-git-worktree para auditar ramas y worktrees."_

## Flujo

### 1. Ejecutar el script de reporte

Desde la raíz de `platform/` (suplai-platform):

```bash
bash .cursor/skills/revisar-git-worktree/scripts/report-worktrees.sh
```

Opciones:

| Flag | Uso |
|------|-----|
| _(ninguna)_ | `git fetch origin --prune` en cada repo y reporte completo |
| `--no-fetch` | Solo estado local (rápido, remoto puede estar desactualizado) |
| `--all-branches` | Incluir ramas locales mergeadas/borrables en el listado extra |
| `--repo PATH` | Un solo repositorio |
| `--root PATH` | Raíz del meta-workspace si no se detecta sola |

El script descubre repos desde `suplai-platform.code-workspace` y completa `field-app` y `sniffer` si faltan.

### 2. Presentar el reporte al usuario

Entregar la salida del script (markdown) con un **resumen ejecutivo** arriba:

```markdown
## Resumen

- **Repos auditados:** N
- **Seguro borrar:** … (listar path/rama)
- **Revisar antes:** … (commits sin push, untracked, no mergeadas)
- **No borrar:** … (hub, troncal, dirty)

[pegar tablas del script]
```

No omitir filas con veredicto `NO` o `REVISAR`.

### 3. Interpretación de columnas

| Columna | Significado |
|---------|-------------|
| **Tipo** | `hub` = checkout principal del repo · `worktree` = linked worktree (p. ej. `.worktrees/feat/x`) |
| **En origin** | Existe `origin/<rama>` |
| **vs origin** | `↑N` commits locales sin push · `↓N` detrás de remoto |
| **Sin commitear** | Archivos modificados o staged |
| **Sin trackear** | Archivos `??` en `git status` |
| **¿Seguro borrar?** | Veredicto heurístico (ver abajo) |

### 4. Veredictos de borrado

| Veredicto | Significado | Acción |
|-----------|-------------|--------|
| **SEGURO** | Limpio y mergeado en troncal, o solo untracked prescindibles | `git worktree remove` o `git branch -d` |
| **REVISAR** | Commits sin push, rama no en origin, untracked, o sin merge confirmado | Preguntar al usuario antes de borrar |
| **NO** | Hub principal, troncal (`main`/`master`), o cambios sin commitear | No borrar |

**Reglas del ecosistema Suplai** (`.cursor/rules/git-sync-and-feature-branch.mdc`):

- **Nunca** recomendar borrar el **hub** si otro agente/chat puede usarlo — avisar explícitamente.
- Troncal en `agent/` es `master`; en el resto, `main`.
- Borrar worktree **no** borra la rama; sugerir `git branch -d` solo si el veredicto lo permite.

### 5. Comandos de limpieza (solo si el usuario lo pide)

```bash
# Worktree mergeado y limpio
git worktree remove .worktrees/feat/mi-feature

# Rama ya mergeada
git branch -d feat/mi-feature

# Referencias remotas obsoletas
git fetch origin --prune
```

**Prohibido** ejecutar borrados masivos sin confirmación explícita del usuario.

## Ejemplo de invocación

Usuario: _"Revisá mis worktrees y decime cuáles puedo borrar"_

1. Ejecutar script (con fetch).
2. Resumen + tablas.
3. Listar comandos concretos solo para filas `SEGURO`.

## Referencias

- Skill creación de worktrees: `.agents/skills/using-git-worktrees/SKILL.md`
- Guía humana: `docs/dev/git-workflow.md`
- Regla agentes: `.cursor/rules/git-sync-and-feature-branch.mdc`
