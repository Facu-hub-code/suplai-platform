# Suplai Platform — Guía para agentes

## Qué es este workspace

Meta-proyecto que agrupa **ocho repos** del ecosistema Suplai Sales. Úsalo cuando la tarea cruce capas: UI → API → BD → agente → tienda → field app → ML → análisis de conversaciones.

## Repos y responsabilidades

| Repo | Stack | Acceso a BD |
|------|-------|-------------|
| `agent/` | Python, FastAPI, LangGraph | Directo a Postgres/Supabase |
| `backend/` | Python, FastAPI | Directo vía asyncpg; fuente de migraciones |
| `backoffice/` | Next.js 16, React 19 | Solo vía backend (proxy en `app/api/*`) |
| `tienda/` | Next.js (v0/Vercel) | Solo vía backend (`lib/tienda-api.ts`) |
| `field-app/` | Next.js (Vercel) | Solo vía backend (`lib/field-api.ts`) — app vendedores |
| `sniffer/` | Python, FastAPI, Alembic | Postgres propio (espejo Kommo) |
| `sales-engine/` | Python, FastAPI, scikit-learn | Lee `{tenant}.pedidos` / `items_pedido` en Supabase |

Cada carpeta anterior (y `platform/`) es un **repositorio git independiente**; commits y PRs se hacen dentro del repo que toques.

## Git antes de modificar código

Antes del **primer cambio de código** en un repo:

1. En la raíz de ese repo: `git fetch` y luego `git pull`.
2. Trabajar siempre en una **rama aparte** de la troncal (`main` / `master`); no editar ni commitear en troncal salvo pedido explícito.
3. Si estás en troncal: `git checkout -b <tipo>/<descripcion>` (ej. `feat/...`, `fix/...`).

Si `git pull` falla, detenerse y resolver con el usuario antes de editar.

Regla completa (Cursor): `.cursor/rules/git-sync-and-feature-branch.mdc`

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

1. Usar MCP `supabase` con `project_ref=cvlbietibaaehgeimxgw`.
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

| Skill | Cuándo |
|-------|--------|
| `cross-repo-investigation` | Bugs o preguntas que cruzan repos |
| `suplai-implementation` | Onboarding tenant (fases 0–10) + `implementacion/README.md` |
| `agent-e2e-testing` | E2E conversacional + healthcheck BD por tenant |
| `analyze-system-prompt` | Auditar prompt ensamblado y tokens |
| `analyze-conversations` | Análisis cualitativo de chats reales |
| `n8n-railway-mcp` | Operación n8n en Railway |
| `enhance-descriptions` | Optimizar descripciones comerciales |
| `feature-test-guide` | Guías de prueba de features |

### Vendor (skills.sh — no en git, lock sí)

Tras clone o actualización del lock:

```bash
bash scripts/install-vendor-skills.sh
```

- **Lock:** `skills-lock.json` — versiones pinneadas.
- **Catálogo y mapeo:** `skills-vendor.manifest.json` (tiers 1–5, Cursor vs Antigravity).
- **Antigravity:** lee `.agents/skills/` directamente.
- **Cursor:** symlinks en `.cursor/skills/_vendor/` (no mezclar con skills Suplai).

| Tier | Skills clave | Agentes |
|------|--------------|---------|
| 1 Arquitectura | `langchain-architecture`, `langgraph`, `mcp-builder` | Cursor + Antigravity |
| 2 Meta | `writing-skills`, `skill-creator`, `find-skills` | Cursor + Antigravity |
| 3 Orquestación dev | `brainstorming`, `writing-plans`, `subagent-driven-development`, … | Solo Cursor |
| 4 Evaluación | `llm-evaluation`, `eval-harness` (+ `agent-e2e-testing` Suplai) | Cursor + Antigravity |
| 5 Testing web | `webapp-testing`, `agent-browser`, `web-design-guidelines` | Cursor + Antigravity |
