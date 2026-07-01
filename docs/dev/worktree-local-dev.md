# Worktree — entorno local (deps, env, puertos)

Scripts en `platform/scripts/worktree/` para que cada **linked worktree** quede listo para probar en localhost sin copiar manualmente `.env`, venv y `node_modules`.

## Respuesta rápida

| Pregunta | Respuesta |
|----------|-----------|
| ¿Existían hooks antes? | **No** — solo una nota en `worktree_hooks.md`. |
| ¿Qué hay ahora? | Manifest de repos, setup automático, hook `post-checkout`, wrapper `add-worktree.sh`. |
| ¿Qué instala? | Symlinks de `.env` / `.env.local` desde el hub, venv o `node_modules` compartidos, `.worktree-dev.env` con puerto y comando. |

## Instalación (una vez por máquina)

Desde la raíz de `suplai-platform/`:

```bash
bash scripts/worktree/install-hooks.sh
```

Esto instala `post-checkout` en cada repo del [manifest.json](../scripts/worktree/manifest.json). Al crear o cambiar de rama **dentro de un worktree**, corre setup con `--if-needed`.

## Crear worktree + setup

Preferido (reemplaza `git worktree add` manual):

```bash
cd suplai-platform
bash scripts/worktree/add-worktree.sh backend fix/benfresh-odoo-client-sync
```

Equivalente manual:

```bash
cd backend-supabase
git worktree add .worktrees/fix/benfresh-odoo-client-sync -b fix/... origin/main
bash ../suplai-platform/scripts/worktree/setup-worktree.sh .worktrees/fix/benfresh-odoo-client-sync
```

## Setup solo (worktree ya existente)

```bash
bash scripts/worktree/setup-worktree.sh /path/al/worktree
# o desde el worktree:
bash ../suplai-platform/scripts/worktree/setup-worktree.sh .
```

## Puertos locales (multi-app)

| Servicio | Puerto | Comando típico |
|----------|--------|----------------|
| Backend | **8000** | `uvicorn main:app --reload --port 8000` |
| Agente | 8002 | `uvicorn app.main:app --reload --port 8002` |
| **Backoffice** | **3000** | `npm run dev` (Maps SDK) |
| Field app | 3001 | `npm run dev -- -p 3001` |
| Tienda | 3002 | `npm run dev -- -p 3002` |
| Sales engine | 8001 | `uvicorn main:app --reload --port 8001` |

Tras el setup, cada worktree tiene `.worktree-dev.env` con `SUPLAI_DEV_PORT` y `SUPLAI_DEV_COMMAND`.

## Hooks por repo (opcional)

Si un repo necesita pasos extra, agregar **`scripts/worktree/setup.sh`** ejecutable en ese repo. Ejemplo: `backend-supabase/scripts/worktree/setup.sh`.

## Probar hotfix BenFresh (backend + backoffice)

```bash
# 1) Backend (worktree con el fix)
cd backend-supabase/.worktrees/fix/benfresh-odoo-client-sync
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 2) Backoffice (hub o worktree; puerto 3000 fijo)
cd product-management-app
npm run dev
# .env.local debe tener NEXT_PUBLIC_BACKEND_URL_DEV=http://127.0.0.1:8000

# 3) Cola Odoo
# Backoffice → Configuración → Integraciones ERP → Clientes pendientes → Sync + detectar → Aprobar ANGELES
```

## Archivos que no se commitean

- `.worktree-setup-stamp` — marca de setup OK
- `.worktree-dev.env` — puerto/comando generados
- Symlinks a `.env`, `venv`, `node_modules` del hub

## Referencias

- [git-workflow.md](./git-workflow.md)
- Regla agentes: `.cursor/rules/git-worktree-gate.mdc`
- Skill: `.agents/skills/using-git-worktrees/SKILL.md`
