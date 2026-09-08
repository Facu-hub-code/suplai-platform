# 038 — Copilot: agentes especialistas

**Estado:** Implementado en ramas feat/copilot-agentes-especialistas (pendiente migración SQL 118 + merge)  
**Fecha:** 2026-09-08  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas sugeridas:** `feat/copilot-agentes-especialistas`  
**Supersede parcial:** un solo Copilot generalista de [027-copilot-hablar-con-datos.md](./027-copilot-hablar-con-datos.md). No invalida el contrato de ventas [042](../../backend-supabase/docs/specs/042-suplai-copilot-contrato-ventas.md).  
**Índice:** [001-suplai-copilot.md](./001-suplai-copilot.md)

---

## Objetivo

Reemplazar el Copilot generalista por **varios agentes especialistas** en la misma pantalla de chats (estilo Grok Bot). Cada agente tiene un pack cerrado de tools, un nombre editable y una descripción de producto. Agregar una necesidad nueva (ej. campañas de marketing) es **sumar un agente**, no engordar a Carlos.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Modelo | Catálogo de producto (`slug` fijo + pack de tools) | Crece por agentes; el LLM no ve tools que no le tocan | Un solo orquestador con todas las tools; tenant que crea agentes a medida |
| Nombre | Editable por operador (`display_name`) | Cada uno lo llama como quiere | Nombre solo de producto, o un nombre compartido por todo el tenant |
| Descripción / prompt / tools | Las define Suplai | El especialista es producto, no un custom GPT | Descripción editable por el tenant (se desvía del pack) |
| Runtime | Mismo backend Copilot (SSE, persistencia, confirm) parametrizado por `agent_slug` | Reusa auth, historial y writes | Servicio LLM aparte por agente |
| UI | Misma vista full-page: lista de agentes → chats de ese agente → thread | Discovery claro; no hay router generalista | Drawer, tab extra, o un “Copilot” que rutea solo |
| Un chat = un agente | `core.copilot_conversations.agent_slug` | La memoria no se mezcla entre especialistas | Historial global compartido |
| Memoria | Últimos **12** mensajes al modelo (límite actual del orquestador); scroll atrás carga más en UI | Barato y predecible | Mandar todo el hilo siempre; embeddings/RAG en v1 |
| NL→SQL | Solo Carlos (`reportes`) | Evita que Lucía/Martín se vuelvan generalistas | `nl_sql_query` en todos |
| Writes | Dry-run + `confirm_token` + audit (patrón actual). Sofía abre el **modal de plantillas** | Acciones peligrosas no se ejecutan en silencio; plantillas Meta ya tienen UI | Ejecutar writes directo desde el LLM |
| Timezone agendas | TZ del tenant (`metadata.timezone`, default `America/Argentina/Buenos_Aires`) | Córdoba Frost y el sender ya viven en hora local; no bloquear v1 en columna por fila | `AGENDA_TZ` global de env como única fuente |
| Archivos | Fuera de v1 | El usuario lo pospuso | Upload de imágenes de catálogo desde el chat |
| Funnel | Vive con Lucía (`audiencia`), no con Carlos | “No responden / no compran” es insumo para etiquetar y agrupar | Funnel en reportes o agente 7 |

---

## Alcance explícito

### Incluido (v1)

- Registry en backend: slug, default_name, description, system_prompt, tools[], chips, capabilities.
- `GET /{schema}/copilot/agents` — la UI no hardcodea la lista.
- Prefs de nombre por operador.
- Conversaciones scoped por `agent_slug`. Chats actuales de Copilot → `reportes` (Carlos).
- Seis agentes de producto (detalle de tools se pule en implementación):

| Slug | Nombre default | Oficio (v1) | Tools (envolver lo que ya existe) |
|------|----------------|-------------|-----------------------------------|
| `reportes` | Carlos | Ventas y ad hoc | Pack actual de Copilot + `nl_sql_query` |
| `audiencia` | Lucía | Funnel temporal, etiquetar, armar grupos | `metricas` / funnel estrategia / etiquetas bulk / `grupo_create` |
| `plantillas` | Sofía | Listar y crear plantillas | `plantillas-meta` + artefacto que abre `CreateMetaTemplateModal` |
| `agendas` | Martín | Crear/listar agendas con TZ del tenant | `agenda` + preview/confirm |
| `catalogo` | Nina | Cobertura de imágenes (lectura) | `GET /productos` y `/productos/diagnostico` |
| `operaciones` | Omar | Estado de sync ERP (lectura) | `GET /erp/dependency-health` |

- Chat: composer + tablas + `action_preview`. Sin archivos.
- Si un agente no puede: decir qué colega sí (chip opcional “abrir chat con X”). Sin handoff automático.

### Fuera de alcance (v1)

- Agente de campañas/estrategias (`campanas`) — se suma después como pack nuevo.
- Subir archivos / imágenes al catálogo desde el chat.
- Definición fina de “consultaron línea X” (se pule cuando toque Lucía).
- Tenant que crea agentes custom.
- Router/supervisor que elige el agente.
- `nl_sql_query` fuera de Carlos.
- Disparar sync ERP, PDF/mapa/charts deprecados, Sniffer/Kommo, Sales Engine.
- Columna `timezone` por fila de agenda (solo si al implementar Martín no alcanza el TZ de tenant).

---

## UX (misma pantalla)

1. Sidebar: agentes (avatar, nombre editable inline, descripción corta de producto).
2. Al elegir un agente: sus chats + “Nueva conversación”.
3. Centro: thread actual. Chips = los del pack. Scroll arriba pide página anterior de mensajes (UI); el modelo sigue viendo solo los últimos N.

---

## Cómo se agrega un agente mañana

1. Registrar pack en el catalogo (código).
2. Encapsular APIs existentes en tools con buena descripción.
3. La lista de la UI se actualiza sola vía `GET .../agents`.

Sin página nueva de chat.

---

## Orden de implementación

Cross-repo. Merge **backend (migración + API) → backoffice**.

| Orden | Repo | Entrega | Rama |
|------:|------|---------|------|
| 1 | `backend-supabase` | Migración `agent_slug` + prefs; registry; `GET /agents`; chat exige slug; Carlos = pack actual | `feat/copilot-agentes-especialistas` |
| 2 | `product-management-app` | Lista de agentes + chats filtrados + rename; misma `CopilotChatView` | misma slug |
| 3 | `backend-supabase` + UI | Packs restantes uno por uno: Lucía → Sofía (modal) → Martín → Nina → Omar | PRs chicos sobre la misma rama o follow-ups |
| 4 | `suplai-platform` | Este spec + enlace en 001 | este repo |

Pulido de tools caso a caso en el paso 3, no en el bootstrap.

---

## Migración de base de datos

Schema `core` (Supabase `cvlbietibaaehgeimxgw`):

1. `core.copilot_conversations.agent_slug text NOT NULL DEFAULT 'reportes'` + índice `(tenant_id, user_id, agent_slug, updated_at DESC)`.
2. Backfill: filas existentes → `reportes`.
3. `core.copilot_agent_prefs (tenant_id, user_id, agent_slug, display_name, updated_at)` PK `(tenant_id, user_id, agent_slug)`.

Rollback: dropear prefs y columna (chats siguen siendo Copilot único). Riesgo bajo: default cubre código viejo hasta el deploy de UI.

---

## Plan de prueba en CI/CD

- Backend: registry expone los 6 slugs; chat con slug desconocido → 400; tools de `audiencia` no se despachan en `reportes`; conversación persistida con slug.
- Migración: test de backfill a `reportes` si hay fixture de conversaciones.
- Front: typecheck/lint; la lista se arma desde `GET /agents` (no array hardcodeado de 6).
- Evals Copilot actuales: correr contra `reportes` / Carlos.
- Gap: sin e2e Playwright obligatorio en v1; packs 3–6 se cubren al pulir cada agente.

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenant `demo` o `cordoba_frost`.

1. Abrir Copilot: se ven 6 agentes con nombre default y descripción.
2. Renombrar Carlos → recargar → el nombre persiste para ese usuario.
3. Chat viejo aparece bajo Carlos (`reportes`), no bajo Lucía.
4. Preguntar a Carlos un top de productos → tabla (comportamiento actual).
5. Preguntarle a Carlos “creá una agenda” → no la crea; apunta a Martín.
6. Nueva conversación en Lucía no aparece en la lista de Carlos.
7. Scroll atrás en un hilo largo carga mensajes viejos; el turno nuevo no manda el hilo entero al modelo (verificar por logs/tool_calls o tamaño de request).

OK mínimo del bootstrap (pasos 1–2): 1–4 y 6. Sofía/Martín/Nina/Omar se prueban cuando se implemente cada pack.

---

## Criterios de aceptación (bootstrap)

- No hay un agente que tenga todas las tools.
- La UI lista agentes desde API.
- Nombre editable por operador; descripción no.
- Chat scoped por `agent_slug`.
- Carlos sigue respondiendo el catálogo actual de ventas.

---

## Referencias

- UI actual: `product-management-app/components/copilot/CopilotChatView.tsx`
- Orquestador: `backend-supabase/services/copilot/orchestrator.py`
- Tools actuales: `backend-supabase/services/copilot/tools.py`
- Migración de `agent_slug`: `backend-supabase/sql/118_copilot_agent_slug.sql`
- Persistencia: `backend-supabase/sql/33_copilot_tables.sql`
- Funnel: `services/metricas_service.py`, `get_estrategia_funnel`
- ERP health: `GET /{schema}/erp/dependency-health`
- TZ tenant: `distribuidoras.metadata->>'timezone'` (Field podcast)
