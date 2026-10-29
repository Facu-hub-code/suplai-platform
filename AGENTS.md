# Suplai Platform — Guía para agentes

## Qué es este workspace

Meta-proyecto que agrupa **ocho repos** del ecosistema Suplai Sales. Úsalo cuando la tarea cruce capas: UI → API → BD → agente → tienda → field app → ML → análisis de conversaciones.

## Repos y responsabilidades

| Repo | Carpeta (hermana de `suplai-platform/`) | Acceso a BD |
|------|-------|-------------|
| `agent/` | `agente-conversacional-multi_tenant/` | Directo a Postgres/Supabase |
| `backend/` | `backend-supabase/` | Directo vía asyncpg; fuente de migraciones |
| `backoffice/` | `product-management-app/` | Solo vía backend (proxy en `app/api/*`) |
| `tienda/` | `wholesale-catalog-app/` | Solo vía backend (`lib/tienda-api.ts`) |
| `field-app/` | `field-app/` | Solo vía backend (`lib/field-api.ts`) — app vendedores |
| `sniffer/` | `sniffer-vendedores/` | Postgres propio (espejo Kommo) |
| `sales-engine/` | `sales-engine/` | Lee `{tenant}.pedidos` / `items_pedido` en Supabase |

En el resto de esta guía se usa el nombre corto de la columna "Repo". Cada carpeta (y `suplai-platform/`) es un **repositorio git independiente**; commits y PRs se hacen dentro del repo que toques.

## Git antes de modificar código

**Flujo por defecto:** rama feature en el **hub** del repo (`backend/`, `backoffice/`, `agent/`, etc.). Los **worktrees solo** cuando el usuario pide hotfix aislado o explícitamente "creá worktree".

**Excepción:** carga de datos o avance de un tenant en `implementacion/{schema}/` — sin rama, worktree ni PR (regla `suplai-implementation-no-branch`).

Antes del **primer cambio de código** en un repo:

1. **`git fetch origin`** en el directorio donde vas a editar (hub en rama feature, salvo worktree pedido).
2. **`git pull`** / merge de troncal si la rama feature está atrás.
3. **Rama feature** desde `origin/main` (o `origin/master` en `agent/`): `git checkout -b feat/<slug>` o checkout de rama existente. Anunciar repo, path y rama antes de editar.
4. **Nunca** implementar en troncal (`main` / `master`) salvo pedido explícito.
5. Antes del PR: merge de troncal, push, `gh pr create`; el **humano mergea** en GitHub.

Features cross-repo: documentar tabla repo → rama → PR; mergear backend/API antes que consumers.

Guía humana: `docs/dev/git-workflow.md`  
Regla completa (Cursor): `.cursor/rules/git-sync-and-feature-branch.mdc`  
Gate worktrees (solo hotfix explícito): `.cursor/rules/git-worktree-gate.mdc`  
Skill worktrees: `.agents/skills/using-git-worktrees/SKILL.md`

## Multi-tenant

- Tabla maestra: `public.distribuidoras` (`schema_name`, credenciales, metadata del agente).
- Datos por cliente: schema PostgreSQL dedicado (`gonzales`, `demo`, `del_corro`, etc.).
- Memoria/conversaciones del agente: schema `core`.
- Header HTTP tenant: `x-schema-name`.

## Integraciones entre repos

| Flujo | Origen | Destino |
|-------|--------|---------|
| Link de catálogo | `agent/` tool `get_catalog_link` | `tienda/` (`https://tienda.suplaisales.com/{schema}?wp=...`) |
| App vendedor (Suplai Field) | `agent/` tools `get_field_app_link`, `get_seller_*` | `field-app/` (`https://field.suplaisales.com/{schema}?wp=...`) |
| Pedido en tienda | `tienda/` | `backend/` endpoints `/login-tienda`, `/{schema}/tienda/*` |
| Tareas y torneos vendedor | `field-app/`, `agent/` | `backend/` endpoints `/{schema}/vendedor-app/*`, `/{schema}/field/*` |
| Recomendaciones combo | `sales-engine/` | Entrena desde pedidos del tenant; puede alimentar sugerencias del agente |
| Análisis comercial vendedor | `sniffer/` | Webhooks Kommo → espejo para patrones de éxito (independiente del agente Meta) |
| Automatización / workflows | n8n en Railway (`n8n infra`) | MCP instance-level + REST API; skill `platform/.cursor/skills/n8n-railway-mcp/` |

## Supabase MCP (obligatorio para esquema principal)

Antes de afirmar columnas, FKs o escribir SQL de esquema del stack principal:

1. Usar MCP `supabase` con `project_ref=cvlbietibaaehgeimxgw` (Suplai-east).
2. `list_tables` con `verbose: true` en `public`, `core` y el tenant relevante.
3. `execute_sql` solo lectura salvo cambios explícitos pedidos por el usuario.

Migraciones oficiales viven en `backend/`.

## Dónde buscar según la pregunta

| Pregunta | Empezar en |
|----------|------------|
| Tools, prompts, webhook, link tienda | `agent/app/` |
| Endpoint REST, migraciones | `backend/routers/`, `backend/services/` |
| Back office UI / proxy | `backoffice/app/`, `backoffice/components/` |
| Catálogo web, carrito, login tienda | `tienda/components/`, `tienda/lib/tienda-api.ts` |
| App vendedor Suplai Field | `field-app/`, spec índice `platform/docs/specs/003-suplai-field-app.md` |
| Conversaciones Kommo, patrones vendedor | `sniffer/app/`, `sniffer/docs/` |
| Modelo ML, retrain, predict-combo | `sales-engine/main.py`, `sales-engine/docs/` |
| n8n, workflows, MCP n8n, integraciones GEV | `platform/.cursor/skills/n8n-railway-mcp/`, repo `test-api-gev/` |
| Spec funcional | `*/docs/specs/` de cada repo |
| OpenAPI backend | `backoffice/doc/openapi.json` o `/openapi.json` en Railway |
| Estructura BD principal | MCP Supabase |

## URLs de producción (referencia)

- Backend: `https://web-production-f544f.up.railway.app`
- Agente: `https://agente-conversacional-multitenant-production.up.railway.app`
- Tienda: `https://tienda.suplaisales.com`
- Suplai Field (vendedores): `https://field.suplaisales.com`
- Swagger backend: `https://web-production-f544f.up.railway.app/docs`

## Skills

### Custom Suplai (en git, `.cursor/skills/`)

Cada carpeta de `.cursor/skills/` tiene un `SKILL.md` con su descripción; leelo cuando la tarea coincida (onboarding de tenant → `suplai-implementation`, bugs cross-repo → `cross-repo-investigation`, E2E → `agent-e2e-testing`).

### Vendor (skills.sh — no en git, lock sí)

Tras clone o actualización del lock:

```bash
bash scripts/install-vendor-skills.sh
```

- **Lock:** `skills-lock.json` — versiones pinneadas.
- **Catálogo y mapeo:** `skills-vendor.manifest.json` (tiers 1–5, Cursor vs Antigravity).
- **Antigravity:** lee `.agents/skills/` directamente.
- **Cursor:** symlinks en `.cursor/skills/_vendor/` (no mezclar con skills Suplai).

# Analytics Tracking — Mixpanel

This workspace uses **Mixpanel** as the single source of truth for product events across backoffice, tienda, field and backend. Spec: `docs/specs/073-mixpanel-analytics.md`. **Microsoft Clarity** (`@microsoft/clarity`) covers session replay and heatmaps in the web frontends. Do not introduce other analytics tools without explicit instruction.

## Before You Add or Modify Any Tracking

⛔ **Do not write Mixpanel tracking code without reading spec 073 and the AGENTS.md Mixpanel section of the target repo.**

### Mandatory checklist

- [ ] Correct SDK: `mixpanel-browser` in Next apps (`lib/analytics.ts`); `mixpanel` Python in `backend-supabase/services/mixpanel_client.py`
- [ ] No CDP — send events with the Mixpanel SDK, not Segment/RudderStack
- [ ] Consent: v1 does not gate on EU/CA; do not add PII
- [ ] Reuse the tracking plan in spec 073 — do not duplicate `pedido_confirmado` on the client

Token: gitignored `.env.local` → `NEXT_PUBLIC_MIXPANEL_TOKEN`; backend `.env` → `MIXPANEL_TOKEN`. Never commit the token. `distinct_id` is `{app}:{schema}:{id}` — never phone or email. Business events (`pedido_confirmado`, `pedido_confirmado_field`, `tarea_completada`, `erp_pedido_enviado`) fire only from the backend. Identity, tracking plan and SDK versions live in spec 073.

## How to Add a New Mixpanel Event

1. Check spec 073 — reuse existing events.
2. `snake_case`, past tense; track after success; no PII.
3. Client: `track()` from `lib/analytics.ts`. Server: `services/mixpanel_client.py`.
4. Update spec 073 and the repo `AGENTS.md`.
5. Verify in Mixpanel Live View.

## What Not to Do

- Do not hardcode the project token or the Clarity project ID.
- Do not track PII.
- Do not fire canonical order events from the browser.
- Do not skip `reset` on logout.
- Do not duplicate Mixpanel business events with `Clarity.event`.

