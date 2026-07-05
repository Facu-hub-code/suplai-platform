---
name: analyze-conversations
description: >-
  Analiza conversaciones reales de un tenant (WhatsApp/agente) para detectar
  desconformidades, errores del agente, productos no encontrados y otras
  oportunidades de mejora del sistema. Filtra por schema, rango de fechas
  (ej. esta semana) o segmentos (vendedores, clientes, zona geo, etiqueta,
  vendedor asignado). Usar cuando el usuario pida auditar conversaciones,
  encontrar puntos de mejora, revisar quejas o calidad operativa del agente.
---

# Análisis de conversaciones — puntos de mejora del sistema

Auditoría **read-only** sobre conversaciones reales. Combina señales SQL (tools, RAG, errores) con lectura semántica de mensajes. No modifica BD ni código salvo que el usuario lo pida después del reporte.

> **Leer antes de ejecutar:** [taxonomy.md](taxonomy.md) (tipos de hallazgo) y [reference.md](reference.md) (SQL de cohorte y señales).

## Cuándo usar

- Revisar calidad del agente en producción o staging post-implementación.
- Responder: "¿qué salió mal esta semana?", "¿dónde se quejan los clientes?", "¿el agente encontró los productos?".
- Segmentar por **vendedores**, **clientes**, **zona geo**, **etiqueta** o **vendedor asignado al PDV**.
- Complementar (no reemplazar) pruebas E2E (`agent-e2e-testing`) con datos reales.

**No confundir con:**

- `tenant-session-loki-debug` → un solo `session_id`, trazas Loki.
- `agent-e2e-testing` → casos sintéticos / casos reales fixture.
- `analyze-system-prompt` → composición del prompt, no conversaciones.

---

## Inputs requeridos

| Dato | Obligatorio | Default |
|------|-------------|---------|
| `schema_name` | Sí | — |
| Rango de fechas | No | últimos 7 días (UTC) |
| Segmento / tag | No | todas las conversaciones con actividad |
| Profundidad | No | `standard` (ver abajo) |
| Guardar reporte | No | sí → `implementacion/{schema}/outputs/` |

### Rangos de fecha (interpretación)

| Usuario dice | SQL |
|--------------|-----|
| hoy | `created_at >= date_trunc('day', now())` |
| ayer | día anterior completo |
| esta semana | `>= date_trunc('week', now())` (lunes ISO) |
| últimos N días | `>= now() - interval 'N days'` |
| entre X e Y | fechas explícitas inclusive |

Aplicar el filtro temporal sobre `core.conversation_events.created_at` (fuente canónica de actividad, spec 013). Fallback legacy: `{schema}.n8n_chat_histories.created_at` si el tenant no migró.

### Segmentos / tags soportados

| Usuario dice | Filtro |
|--------------|--------|
| conversaciones de vendedores | `c.vendedor_id IS NOT NULL` |
| conversaciones de clientes | `c.client_id IS NOT NULL AND c.vendedor_id IS NULL` |
| zona N / zona 5 | `pv.geo_zone_id = N` (confirmar ID con `geo_zones`) |
| clientes de la zona X | mismo filtro por `geo_zone_id` o `geo_zones.name ILIKE` |
| etiqueta X | `cli.etiqueta ILIKE '%X%'` |
| vendedor Juan / vendedor id 3 | join `{schema}.vendedores` por nombre o id en PDV o conversación |
| solo con tickets abiertos | join `{schema}.ia_tickets` status abierto en ventana |

Ante ambigüedad ("zona 5" = id vs nombre), **consultar** `{schema}.geo_zones` vía MCP y confirmar con el usuario si hay más de un match.

---

## Flujo de trabajo

### 0. Preflight

1. MCP Supabase `list_tables` en `public`, `core` y `{schema}` (`verbose: true` si faltan columnas).
2. Resolver `tenant_id`:

```sql
SELECT id::text AS tenant_id, nombre, schema_name
FROM public.distribuidoras
WHERE schema_name = '<schema>'
LIMIT 1;
```

3. Anotar volumen esperado (conversaciones con mensajes en el rango) antes de profundizar.

### 1. Definir cohorte

Usar plantillas de [reference.md](reference.md):

1. `active_sessions` — `session_id` con mensajes humanos o IA en el rango.
2. `cohort` — join `{schema}.conversations` + `clients` + `puntos_venta` + `geo_zones` + `vendedores` + filtros de segmento.
3. Opcional: mapear a `core.conversations` por `session_id` = `phone_number` normalizado.

**Límite de profundidad** (evitar contexto inflado):

| Modo | Conversaciones leídas en detalle | Señales SQL |
|------|----------------------------------|-------------|
| `quick` | top 5 problemáticas | sí, agregadas |
| `standard` | top 15 | sí |
| `deep` | top 30 + muestreo aleatorio 5 | sí + Loki opcional |

Priorizar sesiones con: tool `error`, RAG vacío, tickets abiertos, keywords de frustración (ver taxonomy), latencia > 45s en turno.

### 2. Extraer señales objetivas (SQL)

Ejecutar en paralelo las consultas de [reference.md](reference.md):

- Errores de tools (`core.agent_tool_runs.status = 'error'`).
- `search_products` sin candidatos incluidos en resultado.
- Tools con latencia p95 alta por tool_name.
- Eventos `tool_invocation` / `rag_search` en `core.conversation_events` si hay traza.
- Tickets `{schema}.ia_tickets` en la ventana.
- Ratio mensajes humanos vs respuestas IA sin tool cuando el usuario pidió acción (heurística: revisar en lectura).

### 3. Leer conversaciones (semántica)

Por cada sesión priorizada:

1. Cargar hilo desde `core.conversation_events` (`user_message`/`assistant_message`, orden `created_at ASC`). Fallback legacy: `{schema}.n8n_chat_histories` (orden `id ASC`) si el tenant no migró.
2. Cruzar con `core.agent_tool_runs` del mismo `request_id` / ventana temporal.
3. Clasificar hallazgos según [taxonomy.md](taxonomy.md).
4. Citar evidencia: cita literal del usuario, respuesta del agente, tool/error asociado, `session_id`, timestamp.

**Reglas de interpretación:**

- Separar **hechos** (tool falló, no hubo match RAG) de **hipótesis** (prompt confuso).
- No penalizar desambiguación correcta ni confirmaciones comerciales válidas.
- Marcar si el problema es **datos** (catálogo, precio, cliente), **prompt/reglas**, **tool/RAG** o **UX/latencia**.

### 4. Loki (opcional)

Si el usuario pide causa raíz de un turno concreto o hay errores 500/opacos, delegar a skill `tenant-session-loki-debug` para ese `session_id` + `request_id`. No es obligatorio para el reporte agregado.

### 5. Sintetizar y recomendar

Agrupar hallazgos por categoría y **acción sugerida**:

| Capa | Ejemplos de acción |
|------|-------------------|
| Catálogo / datos | enriquecer descripciones, alias, lista de precios |
| Prompt / reglas | ajustar `system_prompt`, desactivar regla contradictoria |
| Tools | fix bug, deshabilitar tool ruidosa, mejorar descripción |
| RAG | re-vectorizar, revisar filtros de búsqueda |
| Operación | capacitar vendedores, revisar zona/geo asignación |

Indicar **prioridad**: 🔴 alta (bloquea venta / genera queja), 🟡 media, 🟢 baja (mejora incremental).

### 6. Entregar reporte

Guardar en:

`implementacion/{schema}/outputs/auditoria_conversaciones_{YYYYMMDD}.md`

Usar la plantilla abajo. Presentar resumen ejecutivo al usuario en el chat con link al archivo.

---

## Plantilla de reporte

```markdown
# Auditoría de conversaciones — {nombre_distribuidora} ({schema})

**Ventana:** {fecha_desde} → {fecha_hasta} (UTC)
**Segmento:** {filtros o "todas"}
**Conversaciones con actividad:** {N}
**Analizadas en detalle:** {M}

## Resumen ejecutivo

{2–4 oraciones: principales problemas, impacto estimado, 1–3 acciones top}

## Métricas de señal

| Señal | Cantidad |
|-------|----------|
| Errores de tool | |
| Búsquedas sin producto | |
| Tickets IA abiertos | |
| Sesiones con frustración detectada | |
| Latencia turno > 45s | |

## Hallazgos por categoría

### 🔴 {categoría}
- **Sesión:** `{session_id}` — {cliente/vendedor}
- **Evidencia usuario:** "..."
- **Respuesta agente:** "..."
- **Señal técnica:** {tool/error/RAG}
- **Acción sugerida:** ...

### 🟡 ...

## Patrones recurrentes

1. ...
2. ...

## Recomendaciones priorizadas

| # | Prioridad | Acción | Capa | Esfuerzo |
|---|-----------|--------|------|----------|
| 1 | 🔴 | ... | prompt | bajo |

## Sesiones revisadas

| session_id | perfil | motivo selección |
|------------|--------|------------------|
| ... | client/seller | tool error |

## Limitaciones

- {muestra parcial, sin Loki, schema sin agent_turns, etc.}
```

---

## Checklist

- [ ] `schema_name` y `tenant_id` resueltos vía MCP.
- [ ] Rango de fechas y segmento confirmados (o defaults declarados).
- [ ] Cohorte construida; volumen informado al usuario.
- [ ] Señales SQL ejecutadas y contadas.
- [ ] ≥5 sesiones leídas en detalle (modo standard).
- [ ] Hallazgos clasificados con taxonomy + evidencia citada.
- [ ] Recomendaciones separadas por capa (datos / prompt / tool / ops).
- [ ] Reporte guardado en `implementacion/{schema}/outputs/`.

---

## Ejemplos de invocación

**Esta semana, tenant Benfresh, solo vendedores:**

> Analizá las conversaciones de vendedores de benfresh de esta semana y encontrá puntos de mejora.

**Zona geo + profundidad:**

> Revisá conversaciones de clientes de la zona 5 en gonzales, últimos 14 días, modo deep.

**Post-deploy:**

> Después del deploy del martes, auditá benfresh (últimos 3 días) buscando productos no encontrados y quejas.
