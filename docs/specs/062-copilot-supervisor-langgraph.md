# 062 — Copilot Supervisor (LangGraph) sobre packs existentes

**Estado:** En implementación  
**Fecha:** 2026-09-09  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas:** `feat/copilot-supervisor-langgraph`  
**Extiende:** [038-copilot-agentes-especialistas.md](./038-copilot-agentes-especialistas.md) (el router/supervisor quedó fuera de alcance en v1)  
**Índice:** [001-suplai-copilot.md](./001-suplai-copilot.md)

---

## Objetivo

Agregar un **séptimo agente Supervisor** que orquesta a Carlos, Lucía, Sofía, Martín, Nina y Omar. El usuario pide una tarea multi-oficio; el supervisor decide a quién llamar, encadena especialistas, muestra una **bitácora tipo chat** de cada invocación y transmite su **razonamiento en vivo**. Los chats 1:1 con cada especialista siguen existiendo.

Caso canónico: *armar un grupo de quienes agregaron al carrito y no cerraron pedido, revisar plantillas existentes, crear una solo si hace falta, y agendar el seguimiento*.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Runtime de empleados | Fachadas LangGraph de 1 nodo que llaman `run_chat_turn` | Hoy **no hay** grafos por empleado; son packs OpenAI/httpx. Así no se reescribe el oficio ni se duplica el loop de tools | Migrar cada pack a ReAct LangGraph (doble runtime, drift vs 1:1) |
| Supervisor | `StateGraph` manual (nodo LLM + tools + confirm). **No** `langgraph_supervisor` | El pedido pide patrón Command + transcript + interrupt; la librería oculta el state | Un solo orquestador con todas las tools (rompe el aislamiento 038) |
| Slug | `supervisor` en el mismo `POST /copilot/chat` | Reusa auth, SSE, persistencia y selector de agentes | Endpoint `/copilot/supervisor` aparte |
| Conversación puente | Un hilo fijo `(tenant, user, employee_slug)` con `origin=supervisor_bridge` | El especialista recuerda handoffs previos del supervisor; no contamina la lista 1:1 | Invocar sin persistencia (pierde contexto); mezclar en el chat 1:1 del usuario |
| Transcript | Campo `transcript` en el state + artefacto `handoff_transcript` | La UI solo pinta `user`/`assistant`; no hace falta cambiar el CHECK de `role` | Nuevo `role=handoff` (migración de constraint + UI) |
| Escritura | El especialista corre en dry-run y el interrupt es **después**, sobre `object_choice` (spec 067) | «Delegar permiso» no aportaba: el especialista es el único que escribe. El humano elige crear o reusar | Interrupt antes del empleado (`es_escritura`); ejecutar al confirmar la delegación |
| Detección write | Arg `es_escritura: bool` en cada wrapper | Un tool por empleado (pedido); el LLM marca escritura. Lectura no pausa | 12 tools read/write (más ruido); heurística por keywords |
| LLM | `ChatOpenAI` solo en el supervisor; empleados siguen httpx | Reusa `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | Reescribir empleados a LangChain |
| Tracing | LangSmith **opcional** (`LANGCHAIN_TRACING_V2` + `LANGSMITH_API_KEY`) | Nada de LangSmith/Langfuse estaba en Copilot; LangGraph lo soporta nativo. Sin env, el grafo igual corre | Langfuse (otra SDK); tracing obligatorio |
| Checkpointer | `MemorySaver` hidratado desde `core.copilot_orchestrator_runs` (bytea) | Railway tiene varios workers; interrupt exige checkpoint. JSON puro no serializa mensajes LangChain | Solo MemorySaver (se pierde el resume); pool extra de `langgraph-checkpoint-postgres` |
| Stream | `astream_events(..., version="v2")` | Tokens del supervisor → `reasoning_delta`; cada item de transcript → `transcript_turn` | Seguir el stream post-hoc de 40 chars (no hay razonamiento en vivo) |
| Audiencia ad-hoc (carrito, funnel, IDs) | Etiquetar esos `client_ids` y crear el grupo `mode=etiqueta` | `grupo_create` no acepta un set de IDs; `mode=lista` exige lista de precios + días de visita (ruta comercial), no una audiencia puntual. Copilot no crea etiquetas nuevas: reutiliza una existente (p. ej. Carrito) | `dynamic_condition=open_cart` en Copilot (la API de grupos ya lo tiene; la tool no lo expone); grupo por lista de precios |

---

## Alcance explícito

### Incluido (v1)

- Pack `supervisor` (nombre default **Supervisor**) primero en `GET /agents`.
- Seis wrappers `preguntar_a_{carlos,lucia,sofia,martin,nina,omar}` con Command + InjectedState + transcript.
- Grafo ReAct: supervisor → tools (dry-run) → confirm si hay `object_choice` / preview → supervisor → END.
- `interrupt()` **después** del empleado, sobre propuestas crear/reusar (spec 067). `etiquetas_assign_bulk` sigue en `action_preview`.
- SSE: `reasoning_delta`, `employee_started`, `transcript_turn`, `object_choice` / `confirmation_required` + eventos actuales (`text_delta`, `artifact`, `done`, `error`).
- UI: bitácora Supervisor↔empleado, card crear/reusar/reintentar (spec 067), razonamiento token a token, 1:1 intacto.
- Conversaciones puente ocultas en `GET /conversations`.
- Ejemplo documentado + test del caso carrito abandonado (empleados mockeados).

### Fuera de alcance

- Reescribir el runtime de los seis packs. Sí se ajusta el prompt de Lucía y las descripciones de `grupo_create` / `etiquetas_assign_bulk` para el encadenado etiquetar → grupo por etiqueta.
- Librería `langgraph_supervisor`.
- Thought steps discretos del spec 050 / follow-up chips (el razonamiento del supervisor es texto en vivo, no `thought_step`).
- Disparar sync ERP, campañas/estrategias, upload de catálogo.
- Conversación multivuelta real entre empleados (solo bitácora de invocaciones).
- Langfuse.

---

## Orden de implementación

Cross-repo. Merge **backend (migración + API) → backoffice**. Spec en platform en paralelo.

1. `suplai-platform` — este spec + enlace en 001. Rama `feat/copilot-supervisor-langgraph`.
2. `backend-supabase` — SQL 120, deps LangGraph, grafo, `/chat` ramificado, tests. Misma rama.
3. `product-management-app` — tipos SSE, Supervisor en lista, transcript + reasoning UI. Misma rama.
4. Merge humano en GitHub (no CLI).

---

## Migración de base de datos

Archivo: `backend-supabase/sql/120_copilot_supervisor.sql` (119 ya es product-feedback).

- `core.copilot_conversations.origin text NOT NULL DEFAULT 'user'` — valores `user` \| `supervisor_bridge`.
- Índice único parcial: `(tenant_id, user_id, agent_slug) WHERE origin = 'supervisor_bridge' AND deleted_at IS NULL`.
- `core.copilot_orchestrator_runs`: `thread_id` PK, `conversation_id`, `tenant_id`, `user_id`, `checkpoint bytea`, `status`, `interrupt_payload jsonb`, timestamps.

Sin backfill de producto: filas viejas reciben `origin='user'` por default.

Rollback: dropear tabla de runs, índice y columna `origin` (chats 1:1 siguen). Riesgo bajo.

---

## Plan de prueba en CI/CD

- `tests/test_copilot_catalog.py`: los 6 slugs de especialistas no cambian; `list_packs()` empieza por `supervisor`.
- `tests/test_copilot_supervisor_graph.py`: wrappers append transcript; `es_escritura` dispara interrupt; lectura no; caso carrito mockeado (Lucía listar → etiquetar → grupo por etiqueta → Sofía → Martín).
- Persistencia: `list_conversations` filtra `origin=user`; `ensure_bridge` reusa el mismo id.
- Router: `GET /agents` incluye supervisor primero; chat con `agent_slug=supervisor` no llama `run_chat_turn` del pack genérico.
- Checks existentes de dispatch por pack siguen verdes.
- Gap: sin Playwright e2e obligatorio; prueba humana cubre SSE real.

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenant `demo`.

1. Copilot → **Supervisor** (primero en la lista). Chip o pegar el prompt de carrito abandonado.
2. Ver razonamiento en vivo (no esperar al final).
3. Ver bitácora `Supervisor → Lucía` (listar, después etiquetar, después grupo por etiqueta), luego Sofía, luego Martín.
4. Confirmación del supervisor **antes** de etiquetar, de crear el grupo y de agenda/plantilla; después el `action_preview` o modal existentes. El grupo debe ser `mode=etiqueta`, no lista de precios.
5. Cambiar a Lucía en la sidebar: no aparecen hilos puente; se le puede escribir 1:1.
6. Sin `LANGSMITH_API_KEY`: el flujo igual. Con key: traza con tags `supervisor` / `employee:audiencia`.

---

## Criterios de aceptación

- El usuario puede hablarle al Supervisor **o** a un especialista.
- Cada invocación supervisor→empleado queda en transcript (emisor, receptor, consulta, respuesta, timestamp).
- El razonamiento del supervisor streamea token a token.
- Escrituras no se ejecutan sin elegir crear o reusar (`object_choice`, spec 067). El interrupt ya no es «delegar permiso».
- Packs 038 intactos.

## Prompt configurable (spec 064)

El system prompt del Supervisor tiene **default en código** (`catalog.py`) y **override por tenant** en `core.copilot_agent_prompt_overrides`. Detalle: [064-copilot-orchestrator-system-prompt.md](./064-copilot-orchestrator-system-prompt.md).

## Cancelar / punto muerto (spec 065)

Cancelar una escritura es un **freno**, no un 400. Si el preview tiene 0 destinatarios, el Supervisor advierte y termina. Detalle: [065-copilot-supervisor-cancel-deadlock.md](./065-copilot-supervisor-cancel-deadlock.md).

## Playbooks (spec 066)

El chip de carrito abierto usa un **intérprete + receta**, no el ReAct. Detalle: [066-copilot-supervisor-playbook.md](./066-copilot-supervisor-playbook.md).

## Reuso vs creación (spec 067)

Las tools puntúan objetos existentes y el HITL es una card crear/reusar/reintentar. Detalle: [067-copilot-object-choice.md](./067-copilot-object-choice.md).

## Referencias de código

- Packs: `backend-supabase/services/copilot/catalog.py`
- Turno 1:1: `backend-supabase/services/copilot/orchestrator.py`
- Grafo nuevo: `backend-supabase/services/copilot/supervisor/`
- UI: `product-management-app/components/copilot/CopilotChatView.tsx`
