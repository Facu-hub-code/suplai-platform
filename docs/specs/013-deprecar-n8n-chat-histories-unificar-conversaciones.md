# SPEC 013: Deprecar `n8n_chat_histories` — fuente única en `core.conversation_events`

**Estado:** Listo para implementación (MVP same-day)  
**Fecha:** 2026-06-24 · **Actualizado:** 2026-07-04 (plan simplificado)  
**Epic cross-repo:** deprecación historial conversacional legacy  
**Motivación:** El agente persiste en `core.conversation_events`, pero el backoffice lee `n8n_chat_histories` y parchea excepciones (podcast) con merge manual. Mantener ambas fuentes genera dual-write, sobre-ingeniería y conversaciones vacías en el panel tenant.

---

## 0) Resumen ejecutivo

| Hoy | MVP (cerrable hoy) | Backlog (PRs posteriores) |
|-----|-------------------|---------------------------|
| Agente escribe core + n8n | Agente escribe **solo core** | — |
| Backoffice lee n8n + merge podcast | Backend lee **core primero**, fallback n8n | Reportes, Grafana, métricas agente |
| Fase 7–8 mock → n8n | Fase 7–8 mock → **core** (skills + scripts) | Backfill histórico n8n→core |
| — | Eliminar merge `_fetch_podcast_briefing_events` | Archivar tabla n8n, triggers |

**Fuente canónica:** `core.conversation_events` agrupado por `core.conversations`.  
**Legacy sin backfill:** si core está vacío para una sesión, el endpoint devuelve n8n tal cual (historial viejo sigue visible).  
**No deprecar:** n8n como orquestador Railway — solo la **tabla espejo**.

---

## 1) Problema (sin cambios)

Ver inventario §8. Anti-patrón principal: `GET /conversaciones/{phone}/mensajes` lee n8n, luego mergea podcast desde core en Python.

---

## 2) Objetivo MVP

En **un mismo día de trabajo** (1–3 PRs cross-repo):

1. Backoffice muestra hilos **core** (mensajes nuevos + podcast/tienda/onboarding).
2. Historial **solo n8n** sigue visible vía fallback automático.
3. Agente deja de escribir en n8n.
4. **Implementación agentica** (fases 7–8–10, analyze-conversations) escribe/lee **core**, no n8n.

### Métricas de cierre del día

- AC-M1..M5 en verde (§6).
- CI backend + backoffice build verdes.
- Skills actualizadas y coherentes con el código desplegado.

---

## 3) Alcance

### MVP — en alcance hoy

| Repo | Entregable |
|------|------------|
| **backend** | `get_mensajes` core-first + normalizador + fallback n8n; quitar merge podcast; `ultimo_mensaje` core-first en listado (opcional mismo PR) |
| **agente** | Quitar dual-write: `runtime.py`, `registration/runtime.py`, `followups.py` |
| **backoffice** | Sin cambios si API devuelve mismo shape `{ id, type, content, created_at, podcast_briefing? }` |
| **platform** | Skills fase 7, 8, 10, analyze-conversations; scripts fase 7–8 cargar en core |

### Backlog — fuera del MVP hoy

- Backfill masivo n8n → core
- Flag por tenant (`conversations_use_core_events_only`)
- Reportes (`agenda_report`, `vendedores_report`), `metricas_service`, Grafana
- `whatsapp_send` / `agenda_sender` escribiendo solo core
- Archivar tabla n8n, quitar trigger migración 20
- Hilos **mixtos** (historial n8n + mensajes nuevos core en un solo timeline ordenado)

---

## 4) Diseño técnico MVP

### 4.1 `GET /{schema}/conversaciones/{phone}/mensajes`

```
1. Resolver core.conversations por (tenant_id, schema_name, session_id=phone)
2. Si existe → SELECT core.conversation_events ORDER BY created_at, id
3. Si hay eventos → normalizar a respuesta legacy (§4.2) y RETURN
4. Si 0 eventos → SELECT n8n_chat_histories (comportamiento actual) y RETURN
5. Eliminar _fetch_podcast_briefing_events y merge Python
```

### 4.2 Normalizador core → JSON backoffice (compatible hoy)

El backoffice **no cambia** en MVP si el backend mapea:

| `event_type` core | `type` respuesta | `content` |
|-------------------|------------------|-----------|
| `user_message` | `human` | `payload.text` |
| `assistant_message` | `ai` | `payload.text` o `payload.transcription` |
| `outbound_message` | `ai` | `payload.text` |
| `assistant_message` + `kind=podcast_briefing` | `ai` | `"Briefing del día"` + campo `podcast_briefing` anidado |

### 4.3 Listado `GET /conversaciones` (opcional MVP)

Subquery `ultimo_mensaje`:

```
COALESCE(
  (SELECT payload->>'text' FROM core.conversation_events ... ORDER BY id DESC LIMIT 1),
  (SELECT message->>'content' FROM n8n_chat_histories ... ORDER BY id DESC LIMIT 1)
)
```

Filtros `respondieron_hoy` / rango fechas: **siguen en n8n** en MVP (aceptable; follow-up backlog).

### 4.4 Agente — stop-write

Eliminar `append_n8n_history_message` y writes equivalentes en registration/followups. Lectura de memoria ya es core (`MemoryStore.load_recent_events`).

### 4.5 Mock implementación → core

Scripts y skills fase 7–8 insertan en:

```
core.conversations (get_or_create por session_id = client_phone)
core.conversation_events (event_type + event_payload, payload.is_mock = true)
```

Fase 10 purga: `DELETE FROM core.conversation_events WHERE event_payload->>'is_mock' = 'true'` (y limpieza n8n mock legacy si quedó).

---

## 5) Plan de implementación — same day

Orden de merge:

```
1. platform  — skills + spec (este doc) + scripts fase 7–8 (puede ir en paralelo)
2. backend   — normalizador + core-first + fallback
3. agente    — stop-write
4. Verificación manual demo (AC-M1..M5)
```

**Sin** flag por tenant: el fallback n8n es el rollback implícito.

Estimación: 4–6 h dev + 30–45 min QA manual.

---

## 6) Criterios de aceptación MVP

| ID | Escenario | Resultado |
|----|-----------|-----------|
| **AC-M1** | Conversación vieja (solo n8n, 0 eventos core) | Hilo idéntico al actual |
| **AC-M2** | Mensaje agente post-deploy | Visible en backoffice; 0 inserts n8n |
| **AC-M3** | Sesión con podcast (solo core) | Bubble podcast sin merge ad hoc |
| **AC-M4** | Correr fase 7 en tenant demo | Mensajes mock visibles en backoffice vía core |
| **AC-M5** | CI | `pytest` conversaciones + `npm run build` verdes |

---

## 7) Skills y scripts — obligatorio en MVP

Para que la **implementación agentica** no vuelva a escribir en n8n, actualizar en el **mismo entregable** (platform):

### 7.1 Fase 7 — conversaciones

| Archivo | Cambio |
|---------|--------|
| `.cursor/skills/suplai-implementation/phase-07-conversaciones/SKILL.md` | Fuente mock: `core.conversation_events`; n8n solo legacy/read |
| `.cursor/skills/suplai-implementation/phase-07-conversaciones/skill-guide.md` | Preflight: verificar `core.conversations` + eventos; quitar preflight n8n como destino |
| `scripts/fase-07-conversaciones/cargar_conversaciones.py` | Insertar eventos core (`user_message`/`assistant_message`, `is_mock` en payload) en lugar de `n8n_chat_histories` |
| `scripts/fase-07-conversaciones/preparar_conversaciones.py` | Sin cambio CSV; documentar que carga va a core |

Validación skill: `SELECT COUNT(*) FROM core.conversation_events e JOIN core.conversations c ON ... WHERE c.schema_name = '{schema}' AND e.event_payload->>'is_mock' = 'true'`.

### 7.2 Fase 8 — insights / tickets cruzados

| Archivo | Cambio |
|---------|--------|
| `.cursor/skills/suplai-implementation/phase-08-insights/SKILL.md` | Inyección cruzada → `user_message` en core, no n8n |
| `.cursor/skills/suplai-implementation/phase-08-insights/skill-guide.md` | Idem |
| `scripts/fase-08-insights/cargar_insights.py` | Si inserta mensaje de queja en chat, usar core |

### 7.3 Fase 10 — purga mock

| Archivo | Cambio |
|---------|--------|
| `.cursor/skills/suplai-implementation/phase-10-purga-mock/SKILL.md` | Purga core mock events + n8n mock legacy |
| `.cursor/skills/suplai-implementation/phase-10-purga-mock/skill-guide.md` | SQL delete core por `is_mock` |
| Orden purga | `core.conversation_events` (mock) → `n8n_chat_histories` (mock legacy) → resto igual |

### 7.4 analyze-conversations

| Archivo | Cambio |
|---------|--------|
| `.cursor/skills/analyze-conversations/SKILL.md` | Fuente canónica: `core.conversation_events`; fallback n8n solo si core vacío |
| `.cursor/skills/analyze-conversations/reference.md` | Reescribir queries ejemplo contra core |
| `.cursor/skills/analyze-conversations/taxonomy.md` | Señales sobre `event_type` / `payload.text` |

### 7.5 Referencias cruzadas

| Archivo | Cambio |
|---------|--------|
| `.cursor/rules/suplai-implementation-mcp-writes.mdc` | Writes mock conversación → core, no n8n |
| `.cursor/skills/n8n-railway-mcp/reference.md` | Aclarar: tabla n8n deprecada para chat; n8n workflows campaña excepción |

### 7.6 Agente (skills cleanup — repo agent)

| Archivo | Cambio |
|---------|--------|
| `agent/.cursor/skills/cleanup-test-user-data/SKILL.md` | Borrar eventos core de sesión; n8n opcional legacy |
| `agent/docs/specs/019-persistencia-chat-recepcionista-tenant.md` | Marcar **deprecated** — superseded by spec 013 |

---

## 8) Prueba manual (checklist 30 min)

En `demo` o tenant piloto, con backend + backoffice local (puerto 3000):

1. [ ] Abrir conversación con historial antiguo → hilo completo (AC-M1)
2. [ ] Enviar WhatsApp al agente → burbuja en backoffice en <30s (AC-M2)
3. [ ] Abrir sesión vendedor con podcast → audio/transcripción (AC-M3)
4. [ ] `preparar_conversaciones` + `cargar_conversaciones` → mocks visibles (AC-M4)
5. [ ] `phase-10` purga mock → hilos mock desaparecen de backoffice

---

## 9) Inventario consumidores

### MVP toca

- `backend/routers/conversaciones.py`
- `agent/app/agent/runtime.py`, `registration/runtime.py`, `followups.py`
- `platform/scripts/fase-07-*`, `fase-08-*`
- Skills §7

### Backlog (no bloquean MVP)

- `backend/services/whatsapp_send.py`, `agenda_sender.py`, reportes, `metricas_service`, `whatsapp_cliente_estado_service`
- `agent/memory/store.py` (`get_last_customer_interaction_at` → migrar a core)
- Grafana, workflows n8n Del Corro

---

## 10) Specs hijas

| Repo | Archivo | Alcance |
|------|---------|---------|
| backend | `063-conversaciones-core-first-fallback.md` | Normalizador + endpoint + tests |
| agente | `035-stop-dual-write-n8n.md` | Runtime + registration + followups |
| platform | *(este spec 013)* | Skills + scripts fase 7–8–10 |
| backoffice | — | **Sin spec** en MVP (contrato API estable) |

Specs hijas son opcionales si 013 basta para el agente implementador; crear solo si el PR crece mucho.

---

## 11) Riesgos MVP

| Riesgo | Mitigación |
|--------|------------|
| Hilo mixto n8n+core invisible parcial | Aceptado hoy; backlog merge ordenado |
| Fase 7 corrida con skill vieja | Skills en mismo PR que scripts |
| `ultimo_mensaje` vacío en conv. solo-core | Subquery core-first §4.3 |
| Payload sin `text` | Normalizador usa `transcription` o label por `kind` |

---

## 12) Backlog post-MVP (spec futuro o § append)

1. Backfill n8n → core (tenant a tenant)
2. Reportes + Grafana + métricas agente
3. Escrituras backend (whatsapp manual, agenda) → core
4. Hilos mixtos: UNION ordenado n8n + core
5. Archivar `n8n_chat_histories`; tenancy sin provisionar tabla
6. Trigger migración 20 → sync desde core

---

## 13) Relación con otras specs

| Spec | Relación |
|------|----------|
| [036 lab backend](../../backend/docs/specs/036-laboratorio-implementaciones-admin-endpoints.md) | Modelo core de referencia |
| [019 recepcionista agente](../../agent/docs/specs/019-persistencia-chat-recepcionista-tenant.md) | **Deprecated** |
| [012 seguimiento proactivo](./012-seguimiento-proactivo-vendedor.md) | Podcast motivó el fix |
| Auditoría BenFresh 2026-07-02 | Evidencia desvío |

---

## Changelog

- 2026-06-24: Spec inicial (plan multi-fase).
- 2026-07-04: Inventario y sobre-ingeniería documentados.
- 2026-07-04b: **Plan simplificado same-day** — core-first + fallback n8n, stop-write agente, skills fase 7–8–10 + analyze-conversations en MVP; backlog explícito.
