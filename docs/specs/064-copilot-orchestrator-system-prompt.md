# 064 — System prompt configurable del orquestador Copilot

**Estado:** En implementación  
**Fecha:** 2026-09-10  
**Repos:** `backend-supabase`, `product-management-app`, `suplai-platform`  
**Ramas:** `feat/copilot-supervisor-langgraph`  
**Extiende:** [062-copilot-supervisor-langgraph.md](./062-copilot-supervisor-langgraph.md)  
**Índice:** [001-suplai-copilot.md](./001-suplai-copilot.md)

---

## Objetivo

El system prompt del Supervisor (orquestador LangGraph) deja de estar solo hardcodeado. Hay un **default de plataforma en código** y un **override por tenant** persistido, editable desde el back office.

El agente WhatsApp **no** entra: su prompt ya vive en `public.distribuidoras.system_prompt`. El orquestador Copilot corre en el backend (`services/copilot/supervisor/`).

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Alcance | Default global en código + override **por tenant** | Copilot siempre es tenant-scoped (`x-schema-name`). El default en `catalog.py` es el “global”; cada distribuidora puede tunear el orquestador sin redeploy | Tabla global + override (no hay settings de plataforma para prompts; el WhatsApp ya es por tenant) |
| Storage | `core.copilot_agent_prompt_overrides (tenant_id, agent_slug)` | Copilot ya vive en `core` (`copilot_agent_prefs`, conversaciones). La PK por slug deja listo el mismo mecanismo para especialistas | Columna en `distribuidoras` (mezcla el prompt de WhatsApp con Copilot; la tabla ya está saturada). `metadata` JSONB (malo para textos largos; el WhatsApp ya salió de JSON a columnas) |
| Fallback | Fila ausente / texto vacío → `_SUPERVISOR_PROMPT` | NULL = “usar el de plataforma”; no hay que seedear tenants | Copiar el default a todos los tenants (drift cuando cambia el código) |
| Env flag | Ninguno | El override se edita en UI/API; un env exigiría redeploy y no es por tenant | `COPILOT_SUPERVISOR_SYSTEM_PROMPT` (capa extra innecesaria en v1) |
| API | `GET/PUT/DELETE /{schema}/copilot/agents/{slug}/system-prompt` | Reusa auth Copilot y el slug del pack. DELETE restaura el default | Meter el texto en `PATCH /agents/{slug}` (ese endpoint es el rename visible) |
| v1 slug | Solo `supervisor` | El pedido es el orquestador. Especialistas siguen en código | Hacer editables los 6 packs (más UI y riesgo de romper oficios) |
| Auth | Mismo Bearer Copilot que el resto del chat | Spec 001: todos los roles del back office pueden operar Copilot; auditoría con `updated_by` | Matriz admin-only (no existe en Copilot v1) |
| Runtime | El grafo lee `state.system_prompt`; `stream.py` lo hidrata al inicio del turno | El checkpointer no debe congelar un prompt viejo en chats nuevos; el resume de interrupt sí conserva el del turno en curso | Recompilar el grafo con el prompt (el grafo es por request; el state ya viaja) |

---

## Alcance explícito

### Incluido (v1)

- Default `_SUPERVISOR_PROMPT` en `services/copilot/catalog.py`.
- Tabla `core.copilot_agent_prompt_overrides`.
- API admin (operador logueado): leer, guardar, restaurar default.
- El stream del supervisor usa override si existe.
- UI: engranaje en la tarjeta del Supervisor → diálogo con textarea, Guardar y Restaurar default.
- Tests: fallback vs override (catalog, grafo, persistencia, router).

### Fuera de alcance

- Prompts de Carlos, Lucía, Sofía, Martín, Nina, Omar (siguen en código).
- Preview tokenizado tipo system-prompt de WhatsApp.
- Historial / versiones del prompt.
- Feature flag nuevo (Copilot ya está on).
- Agente WhatsApp / repo `agente-conversacional-multi_tenant`.
- Empty-state / skeleton de la lista de conversaciones (otro cambio en paralelo).

---

## Orden de implementación

Cross-repo. Merge **migración + API → backoffice**. Spec en platform en paralelo.

| # | Repo | Qué |
|---|------|-----|
| 1 | `backend-supabase` | SQL 121, persistencia, API, grafo/stream, tests |
| 2 | `product-management-app` | Proxy BFF, diálogo, i18n |
| 3 | `suplai-platform` | Este spec + enlace en 001 y 062 |

Rama en los tres: `feat/copilot-supervisor-langgraph`. Merge humano en GitHub.

---

## Migración de base de datos

Archivo: `backend-supabase/sql/121_copilot_agent_prompt_overrides.sql` (aplicar con `python scripts/migrations/apply_migration_121.py`).

```sql
CREATE TABLE IF NOT EXISTS core.copilot_agent_prompt_overrides (
    tenant_id uuid NOT NULL REFERENCES public.distribuidoras(id) ON DELETE CASCADE,
    agent_slug text NOT NULL,
    system_prompt text NOT NULL,
    updated_by uuid,
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, agent_slug)
);
```

Sin backfill: sin fila = default de código.

**Rollback:** `DROP TABLE IF EXISTS core.copilot_agent_prompt_overrides;` — el orquestador vuelve al prompt de `catalog.py`. Riesgo bajo.

No aplicar a producción vía MCP `apply_migration`; el archivo vive en el repo.

---

## Plan de prueba en CI/CD

- `tests/test_copilot_catalog.py`: `resolve_supervisor_system_prompt` (None/blank → default; texto → override); `is_prompt_configurable` solo supervisor.
- `tests/test_copilot_supervisor_graph.py`: `_history_messages` usa override vs default.
- `tests/test_copilot_persistence_agents.py`: upsert trim; especialistas `PROMPT_NOT_CONFIGURABLE`.
- `tests/test_copilot_agents_router.py`: GET default, PUT override, DELETE reset, GET reportes → 400.
- Checks existentes de packs 038 / grafo 062 siguen verdes.

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenant `demo`. Aplicar migración 121 en el entorno local.

1. Copilot → hover en **Supervisor** → engranaje → se abre el diálogo con el default de plataforma.
2. Editar una frase distintiva (ej. “Siempre firmá como Orquestador Demo”) → Guardar → badge “Personalizado”.
3. Chat nuevo al Supervisor: el razonamiento / estilo refleja el override.
4. Restaurar default → badge “Default de plataforma” → un chat nuevo ya no usa la frase custom.
5. `GET /demo/copilot/agents/reportes/system-prompt` → 400 `PROMPT_NOT_CONFIGURABLE`.
6. No se rompe el 1:1 con especialistas ni la lista de chats (empty-state/skeleton ajenos).

---

## Criterios de aceptación

- Sin fila en BD, el orquestador usa el prompt de código.
- Con override, el stream del supervisor usa ese texto (más `Tenant schema` / `Locale`).
- Un operador del back office puede leer, guardar y restaurar el default desde la UI del Supervisor.
- Especialistas no son editables en v1.

## Referencias de código

- Default: `backend-supabase/services/copilot/catalog.py`
- Grafo: `backend-supabase/services/copilot/supervisor/graph.py`
- Stream: `backend-supabase/services/copilot/supervisor/stream.py`
- API: `backend-supabase/routers/copilot.py`
- UI: `product-management-app/components/copilot/CopilotSupervisorPromptDialog.tsx`
