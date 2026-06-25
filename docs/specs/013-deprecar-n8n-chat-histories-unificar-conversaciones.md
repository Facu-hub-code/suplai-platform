# SPEC 013: Deprecar `n8n_chat_histories` — fuente única en `core.conversation_events`

**Estado:** Diseño  
**Fecha:** 2026-06-24  
**Motivación:** Duplicación de historial entre `{schema}.n8n_chat_histories` (legacy n8n / backoffice) y `core.conversation_events` (agente, lab, podcast, tienda). Hoy el backoffice mezcla ambas fuentes de forma ad hoc; el agente escribe en las dos; los reportes leen solo n8n.

---

## 1) Problema

### 1.1 Estado actual (dual-write / dual-read)

| Capa | Escribe en | Lee desde |
|------|------------|-----------|
| Agente (`MemoryStore`, runtime) | `core.conversation_events` + best-effort `n8n_chat_histories` | `core.conversation_events` |
| Backoffice Conversaciones | — | `{schema}.n8n_chat_histories` + merge manual de `core.conversation_events` (solo `podcast_briefing`) |
| Backend agenda / WhatsApp manual | `n8n_chat_histories` + a veces `core.conversation_events` | — |
| Admin Lab | — | `core.conversation_events` |
| Reportes agenda / vendedores | — | `n8n_chat_histories` |
| Followups agente | `n8n_chat_histories` | — |
| Fases implementación 7–8 | inserts mock en `n8n_chat_histories` | — |

### 1.2 Síntomas

- Conversación **vacía en backoffice** aunque existan eventos en `core` (ej. podcast mock, tienda, agenda con evento core).
- **Dos modelos de mensaje** incompatibles: `message jsonb {type, content}` vs `event_type + event_payload`.
- **Dos tablas de conversación**: `{schema}.conversations` (listado backoffice) vs `core.conversations` (memoria agente).
- Trazabilidad del lab y del panel tenant **divergen** (spec 036 vs spec 005 backoffice).

### 1.3 Decisión de producto

**Fuente canónica del hilo:** `core.conversation_events` (timeline ordenado por `created_at`, `id`), agrupado por `core.conversations` (`tenant_id`, `schema_name`, `session_id`).

**Deprecar:** `{schema}.n8n_chat_histories` como store de mensajes (mantener tabla en solo-lectura durante migración; eliminar en fase final).

**Unificar listado backoffice:** `{schema}.conversations` sigue siendo el índice comercial (cliente/vendedor, filtros territorio); el hilo se resuelve vía `core.conversations.session_id = phone_number`.

---

## 2) Objetivo

Un solo pipeline de persistencia y lectura de mensajes para agente, backoffice, reportes y features proactivas (podcast, agenda, tienda).

### Métricas de éxito

- 0 escrituras nuevas en `n8n_chat_histories` post-cutover.
- Backoffice Conversaciones renderiza 100% de mensajes desde `core.conversation_events`.
- Paridad visual: mismos mensajes antes/después en tenant piloto (diff automatizado).
- Latencia p95 `GET /conversaciones/{phone}/mensajes` ≤ baseline + 20%.

---

## 3) Alcance

### En alcance

- Contrato unificado de `event_type` / `event_payload` para UI.
- Migración de datos históricos n8n → core (por tenant, idempotente).
- Cambios en backend, agente, backoffice, scripts de implementación.
- Actualización reportes que hoy leen n8n.
- Feature flag `conversations_use_core_events_only` por tenant.

### Fuera de alcance

- Deprecar n8n como **orquestador** (workflows Railway) — solo la **tabla** espejo.
- Cambiar modelo de `core.agent_turns` / lab (ya usa core).
- Sniffer / Kommo (Postgres aparte).

---

## 4) Modelo objetivo

### 4.1 Identidad de conversación

```
core.conversations (tenant_id, schema_name, session_id)
    └── core.conversation_events[]
            event_type ∈ user_message | assistant_message | outbound_message | system | registration_state | ...
            event_payload jsonb (contrato por kind)
```

`{schema}.conversations` **permanece** como vista comercial enriquecida (client_id, vendedor_id, phone_number, filtros geo). Debe mantener FK lógica o trigger hacia `core.conversations.id` (nuevo campo opcional `core_conversation_id bigint`).

### 4.2 Mapeo legacy n8n → core

| n8n `message->>'type'` | `event_type` core | `event_payload` |
|------------------------|-------------------|-----------------|
| `human`, `user` | `user_message` | `{ "text": "<content>", "source": "whatsapp" }` |
| `ia`, `ai` | `assistant_message` | `{ "text": "<content>" }` |
| (plantilla agenda) | `assistant_message` | `{ "text": "...", "kind": "template", "template_name": "..." }` |
| podcast (nuevo) | `assistant_message` | `{ "kind": "podcast_briefing", "audio": {...}, "transcription": "..." }` |

Regla: **`kind` opcional** en payload para renderizado especializado en backoffice (podcast, pedido confirmado tienda, etc.).

### 4.3 API backoffice (target)

`GET /{schema}/conversaciones/{phone}/mensajes`:

1. Resolver `core.conversations.id` por `(tenant_id, schema_name, session_id=phone)`.
2. `SELECT ... FROM core.conversation_events WHERE conversation_id = $1 ORDER BY created_at, id`.
3. **Eliminar** query a `n8n_chat_histories`.
4. Normalizar respuesta JSON estable para UI (ver §4.4).

### 4.4 Contrato respuesta UI (propuesto)

```json
{
  "id": 45117,
  "event_type": "assistant_message",
  "created_at": "2026-06-24T23:55:20Z",
  "payload": {
    "kind": "podcast_briefing",
    "text": "Briefing diario (audio)",
    "audio": { "supabase_path": "..." },
    "transcription": "..."
  },
  "legacy_n8n": false
}
```

El backoffice deja de parsear `message.type` / `message.content` y usa `event_type` + `payload`.

---

## 5) Plan de migración (fases)

### Fase 0 — Inventario (1 sprint)

- Script `backend/scripts/audit_n8n_vs_core.py`: por tenant, conteos, session_ids solo-en-n8n, solo-en-core, divergencia último mensaje.
- Documentar consumidores (grep cross-repo) — baseline en este spec §8.

### Fase 1 — Dual-read, single-write (agente + nuevos features)

- Agente: **dejar de escribir** en `n8n_chat_histories` tras flag ON (mantener lectura fallback 30 días).
- Podcast, tienda, agenda: **solo** `core.conversation_events`.
- Backoffice: leer core primero; si flag OFF, merge n8n (comportamiento actual).

### Fase 2 — Backfill histórico

- Migración SQL/Python idempotente por tenant:
  - Para cada fila `n8n_chat_histories` sin evento equivalente en core (hash `session_id + created_at + text`), insertar `conversation_events`.
  - `request_id = 'backfill-n8n-{n8n_id}'` para idempotencia.
- Validación: conteos ±0, muestreo 50 hilos manual.

### Fase 3 — Single-read cutover

- Backend `get_mensajes` solo core.
- Reportes (`agenda_report`, `vendedores_report`) migrados a core.
- Skills implementación fases 7–8 escriben en core (o adapter compartido).

### Fase 4 — Deprecación tabla

- Renombrar `{schema}.n8n_chat_histories` → `n8n_chat_histories_archived_{YYYYMMDD}` o RLS deny insert.
- Eliminar código muerto agente/backend.
- Actualizar `core/tenancy.py` provisioning (no crear n8n table en tenants nuevos).

---

## 6) Requisitos funcionales

- `RF-1` Toda entrada/salida WhatsApp del agente persiste un evento core antes de responder OK al webhook.
- `RF-2` Backoffice Conversaciones muestra user + assistant + outbound (podcast, plantillas) desde un solo endpoint.
- `RF-3` Búsqueda en hilo (spec 005 backoffice) filtra sobre payload.text / transcription unificados.
- `RF-4` `clear_seller_context` / delete contexto borra solo `core.conversation_events` (n8n archivado ignorado).
- `RF-5` Followups evalúan condiciones (`last_assistant_message`, idle) leyendo core, no n8n.

---

## 7) Requisitos no funcionales

- `RNF-1` Backfill batch: ≤ 5k filas/min por tenant, sin agotar pool (reglas MCP 6543, pools mínimos).
- `RNF-2` Índice existente en `core.conversation_events (conversation_id, created_at)` — verificar/crear si falta.
- `RNF-3` Rollback: flag tenant revierte a dual-read sin perder datos core.

---

## 8) Impacto por repo

| Repo | Cambios principales |
|------|---------------------|
| **backend-supabase** | `routers/conversaciones.py`, `whatsapp_send.py`, `agenda_sender.py`, reportes, migración backfill, flag en `distribuidoras.metadata` |
| **agente-conversacional-multi_tenant** | `memory/store.py`, `runtime.py`, `followups.py`, `registration/runtime.py`, `seller.py` clear context |
| **product-management-app** | `conversations-view.tsx` — parser unificado; tipos en `lib/conversations.ts` |
| **platform** | skills fase 7–8, `analyze-conversations`, guías QA |
| **tienda** | ya escribe core en confirmación (spec 028) — verificar paridad |

### Specs hijas (a crear al implementar)

| Repo | Archivo propuesto |
|------|-------------------|
| backend | `059-unify-conversation-events-api.md` |
| agente | `034-stop-dual-write-n8n-histories.md` |
| backoffice | `049-conversations-core-events-ui.md` |

---

## 9) Criterios de aceptación

### `AC-1` Paridad tenant piloto

- **Given** tenant `demo` con flag ON y backfill completo.
- **When** se abre Conversaciones para un cliente con historial pre-migración.
- **Then** el hilo coincide en cantidad y orden con export pre-cutover (tolerancia timestamps ±1s).

### `AC-2` Podcast sin n8n

- **Given** job podcast `SENT` con evento core.
- **When** se abre conversación seller.
- **Then** bubble podcast visible **sin** filas en n8n para esa sesión.

### `AC-3` Agente sin dual-write

- **Given** flag ON en tenant.
- **When** el vendedor envía un mensaje y recibe respuesta.
- **Then** hay eventos `user_message` + `assistant_message` en core y **0 inserts** en n8n post-request.

---

## 10) Riesgos

| Riesgo | Mitigación |
|--------|------------|
| Reportes rotos | Migrar queries en mismo PR que cutover; dashboard Grafana si aplica |
| Payloads sin `text` | Normalizador en API: derivar display de `kind`-specific fields |
| Tenants sin `core.conversations` | Backfill crea conversación core por cada `session_id` distinto en n8n |
| Performance listado | Paginación cursor en `GET mensajes` (V2 si hilo > 500 eventos) |

---

## 11) Relación con otras specs

| Spec | Relación |
|------|----------|
| [012 seguimiento proactivo](./012-seguimiento-proactivo-vendedor.md) | Podcast expuso el problema del merge ad hoc |
| [036 lab backend](../../../backend-supabase/docs/specs/036-laboratorio-implementaciones-admin-endpoints.md) | Lab ya es core-first |
| [005 busqueda conversaciones backoffice](../../../product-management-app/doc/specs/005-busqueda-clientes-vendedor-y-mensajes-conversaciones.md) | Búsqueda debe migrar a payload unificado |
| [028 tienda pedido patch](../../../backend-supabase/docs/specs/028-tienda-pedido-patch-confirmar-politica-minimo.md) | Patrón `assistant_message` en core |

---

## Changelog

- 2026-06-24: Spec inicial — deprecación `n8n_chat_histories`, unificación en `core.conversation_events`.
