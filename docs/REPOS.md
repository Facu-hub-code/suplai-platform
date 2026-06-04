# Mapa de repositorios

Rutas relativas desde `source/` (hermanas de `suplai-platform/`).

## agente-conversacional-multi_tenant → `agent/`

| Área | Ruta clave |
|------|------------|
| Entrypoint API | `app/main.py` |
| Runtime LangGraph | `app/agent/runtime.py` |
| Tools | `app/agent/tools/` |
| Link tienda | `app/agent/tools/catalog.py` |
| Webhook WhatsApp | `app/webhooks/` |
| SQL baseline | `sql/` |
| Specs | `docs/specs/` |

## backend-supabase → `backend/`

| Área | Ruta clave |
|------|------------|
| Routers | `routers/` |
| Servicios | `services/` |
| Endpoints tienda | buscar `tienda` en routers |
| Specs | `docs/specs/` |
| Snapshots BD | `docs/db-structure/snapshots/` |
| OpenAPI | `/docs` y `/openapi.json` en runtime |

## product-management-app → `backoffice/`

| Área | Ruta clave |
|------|------------|
| Panel usuario | rutas raíz, `/login` |
| Panel admin | `app/admin/` |
| Proxy API | `app/api/` |
| OpenAPI ref | `doc/openapi.json` |
| Specs UI | `doc/specs/` |

## wholesale-catalog-app → `tienda/`

| Área | Ruta clave |
|------|------------|
| Cliente catálogo | `components/catalog-client.tsx` |
| Carrito / pedido | `components/cart.tsx` |
| API tienda | `lib/tienda-api.ts` |
| Config backend | `lib/api-config.ts` |
| Specs | `docs/specs/` |
| Skill API | `.cursor/skills/suplai-tienda-api/SKILL.md` |

## sniffer-vendedores → `sniffer/`

| Área | Ruta clave |
|------|------------|
| Entrypoint | `app/main.py` |
| Webhook Kommo | `POST /webhook/kommo` |
| UI conversaciones | `/admin/kommo/conversations` |
| Migraciones | `alembic/` |
| Arquitectura | `docs/arqui-kommo.md` |
| Skill Railway | `.cursor/skills/railway-sniffer-vendedores/` |

## Specs Suplai Copilot (cross-repo)

| Documento | Repo |
|-----------|------|
| Índice y decisiones | `platform/docs/specs/001-suplai-copilot.md` |
| Backend / tools / PDF | `backend-supabase/docs/specs/041-*.md`, `042-*.md` |
| UI artefactos | `backoffice/doc/specs/039-suplai-copilot-ui-artefactos.md` |

## sales-engine → `sales-engine/`

| Área | Ruta clave |
|------|------------|
| Entrypoint | `main.py` |
| Config | `config.py` |
| Entrenamiento offline | `train.py` |
| Docs pedagógicas | `docs/README.md` |
| Modelos | `{MODEL_DIR}/{schema}.pkl` |
| Retrain API | `POST /v1/tenants/{schema}/models/retrain` |
| Predicción | `POST /v1/tenants/{schema}/predict-combo` |

## suplai-platform → `platform/`

| Área | Ruta clave |
|------|------------|
| Workspace | `suplai-platform.code-workspace` |
| MCP Supabase | `.cursor/mcp.json` |
| Reglas | `.cursor/rules/` |
| Skill investigación | `.cursor/skills/cross-repo-investigation/` |

## Git

Cada repo mantiene su propio `.git`. Commits y PRs se hacen **dentro del repo correspondiente**.
