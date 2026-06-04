# Suplai Platform — Guía para agentes

## Qué es este workspace

Meta-proyecto que agrupa **siete repos** del ecosistema Suplai Sales. Úsalo cuando la tarea cruce capas: UI → API → BD → agente → tienda → ML → análisis de conversaciones.

## Repos y responsabilidades

| Repo | Stack | Acceso a BD |
|------|-------|-------------|
| `agent/` | Python, FastAPI, LangGraph | Directo a Postgres/Supabase |
| `backend/` | Python, FastAPI | Directo vía asyncpg; fuente de migraciones |
| `backoffice/` | Next.js 16, React 19 | Solo vía backend (proxy en `app/api/*`) |
| `tienda/` | Next.js (v0/Vercel) | Solo vía backend (`lib/tienda-api.ts`) |
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
| Pedido en tienda | `tienda/` | `backend/` endpoints `/login-tienda`, `/{schema}/tienda/*` |
| Recomendaciones combo | `sales-engine/` | Entrena desde pedidos del tenant; puede alimentar sugerencias del agente |
| Análisis comercial vendedor | `sniffer/` | Webhooks Kommo → espejo para patrones de éxito (independiente del agente Meta) |
| Automatización / workflows | n8n en Railway (`n8n infra`) | MCP instance-level + REST API; skill `platform/.cursor/skills/n8n-railway-mcp/` |

## Supabase MCP (obligatorio para esquema principal)

Antes de afirmar columnas, FKs o escribir SQL de esquema del stack principal:

1. Usar MCP `supabase` con `project_ref=nxmeezcvjltlqfybbczt`.
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
- Swagger backend: `https://web-production-f544f.up.railway.app/docs`

## Skill recomendada

Investigaciones cross-repo: `.cursor/skills/cross-repo-investigation/SKILL.md`  
Onboarding / implementación tenant: `.cursor/skills/suplai-implementation/SKILL.md` + `implementacion/README.md`
