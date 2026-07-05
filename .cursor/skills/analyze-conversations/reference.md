# Referencia SQL — cohorte y señales

Proyecto Supabase: **`cvlbietibaaehgeimxgw`** (Suplai-east). Ejecutar vía MCP `execute_sql`. Reemplazar placeholders:

- `<schema>` — schema del tenant
- `<tenant_id>` — UUID de `public.distribuidoras`
- `<from>`, `<to>` — timestamptz UTC

## Normalización de teléfono

Patrón usado en backend (`core/tenancy.py`, `conversaciones.py`):

```sql
regexp_replace(COALESCE(phone, ''), '[\+\-\s\(\)]', '', 'g')
```

`session_id` en `core.conversations` coincide con `{schema}.conversations.phone_number`.

> [!IMPORTANT]
> **Fuente canónica (spec 013): `core.conversation_events`** enlazada a `core.conversations`
> (`schema_name = '<schema>'`, `tenant_id = '<tenant_id>'`). Mapeo:
> - Texto del mensaje → `event_payload->>'text'` (fallback `->>'transcription'`).
> - Humano → `event_type = 'user_message'`; agente → `event_type IN ('assistant_message','outbound_message')`.
> - Timestamp → `ce.created_at`.
>
> Las queries que leen `{schema}.n8n_chat_histories` quedan como **fallback legacy**
> (solo tenants que aún no migraron su historial). Preferir siempre las versiones core.

---

## 1. Volumen de actividad (core)

```sql
SELECT
  COUNT(DISTINCT ce.conversation_id) AS sesiones_activas,
  COUNT(*) FILTER (WHERE ce.event_type = 'user_message') AS mensajes_humanos,
  COUNT(*) FILTER (WHERE ce.event_type IN ('assistant_message', 'outbound_message')) AS respuestas_ia
FROM core.conversation_events ce
JOIN core.conversations c ON c.id = ce.conversation_id
WHERE c.schema_name = '<schema>'
  AND ce.tenant_id = '<tenant_id>'
  AND ce.created_at >= '<from>'::timestamptz
  AND ce.created_at < '<to>'::timestamptz;
```

> Fallback legacy (n8n): `COUNT(DISTINCT h.session_id)` con `h.message->>'type'` sobre `"<schema>".n8n_chat_histories`.

---

## 2. Cohorte base (con segmentos)

```sql
WITH active_sessions AS (
  SELECT DISTINCT c.session_id
  FROM core.conversation_events ce
  JOIN core.conversations c ON c.id = ce.conversation_id
  WHERE c.schema_name = '<schema>'
    AND ce.tenant_id = '<tenant_id>'
    AND ce.created_at >= '<from>'::timestamptz
    AND ce.created_at < '<to>'::timestamptz
)
SELECT
  c.id AS conversation_local_id,
  c.phone_number AS session_id,
  c.client_id,
  c.vendedor_id,
  COALESCE(cli.razon_social, cli.nombre, v.nombre) AS display_name,
  cli.etiqueta,
  pv.geo_zone_id,
  gz.name AS geo_zone_name,
  pv.vendedor_id AS pdv_vendedor_id,
  CASE
    WHEN c.vendedor_id IS NOT NULL THEN 'seller'
    WHEN c.client_id IS NOT NULL THEN 'client'
    ELSE 'unknown'
  END AS actor_profile,
  c.updated_at AS last_conv_update
FROM "<schema>".conversations c
JOIN active_sessions a ON a.session_id = c.phone_number
LEFT JOIN "<schema>".clients cli ON cli.id = c.client_id
LEFT JOIN "<schema>".puntos_venta pv ON pv.id = cli.pdv_id
LEFT JOIN "<schema>".geo_zones gz ON gz.id = pv.geo_zone_id
LEFT JOIN "<schema>".vendedores v ON v.id = c.vendedor_id
WHERE 1=1
  -- SEGMENTO vendedores:
  -- AND c.vendedor_id IS NOT NULL
  -- SEGMENTO clientes:
  -- AND c.client_id IS NOT NULL AND c.vendedor_id IS NULL
  -- SEGMENTO zona geo (id):
  -- AND pv.geo_zone_id = 5
  -- SEGMENTO etiqueta:
  -- AND cli.etiqueta ILIKE '%VIP%'
  -- SEGMENTO vendedor asignado al PDV:
  -- AND pv.vendedor_id = 3
ORDER BY c.updated_at DESC;
```

### Listar zonas (desambiguar "zona 5")

```sql
SELECT id, name, zone_type, codigo_ruta, active
FROM "<schema>".geo_zones
ORDER BY id;
```

---

## 3. Hilo de mensajes (una sesión) — core

```sql
SELECT
  ce.id,
  ce.created_at,
  CASE
    WHEN ce.event_type = 'user_message' THEN 'human'
    ELSE 'ai'
  END AS msg_type,
  COALESCE(ce.event_payload->>'text', ce.event_payload->>'transcription') AS content
FROM core.conversation_events ce
JOIN core.conversations c ON c.id = ce.conversation_id
WHERE c.schema_name = '<schema>'
  AND ce.tenant_id = '<tenant_id>'
  AND c.session_id = '<session_id>'
  AND ce.event_type IN ('user_message', 'assistant_message', 'outbound_message')
  AND ce.created_at >= '<from>'::timestamptz
  AND ce.created_at < '<to>'::timestamptz
ORDER BY ce.created_at ASC, ce.id ASC;
```

> Fallback legacy (n8n): `SELECT h.id, h.created_at, h.message->>'type', h.message->>'content' FROM "<schema>".n8n_chat_histories h WHERE h.session_id = '<session_id>' ORDER BY h.id ASC;`

---

## 4. Eventos del agente (memoria core)

```sql
SELECT
  ce.id,
  ce.request_id,
  ce.event_type,
  ce.event_payload,
  ce.created_at
FROM core.conversations cc
JOIN core.conversation_events ce ON ce.conversation_id = cc.id
WHERE cc.tenant_id = '<tenant_id>'::uuid
  AND cc.session_id = '<session_id>'
  AND ce.created_at >= '<from>'::timestamptz
  AND ce.created_at < '<to>'::timestamptz
ORDER BY ce.id ASC;
```

Texto usuario/asistente: `event_payload->>'text'` en `user_message` / `assistant_message`.

---

## 5. Tools y errores (lab / traza)

```sql
SELECT
  at.session_id,
  at.request_id,
  at.actor_type,
  atr.tool_name,
  atr.status,
  atr.error_summary,
  atr.latency_ms,
  atr.rag_query,
  atr.rag_match_count,
  atr.created_at
FROM core.agent_tool_runs atr
JOIN core.agent_turns at ON at.id = atr.turn_id
WHERE atr.tenant_id = '<tenant_id>'::uuid
  AND atr.created_at >= '<from>'::timestamptz
  AND atr.created_at < '<to>'::timestamptz
  AND at.session_id = ANY(ARRAY['<session_id_1>', '<session_id_2>']::text[])
ORDER BY atr.created_at ASC;
```

### Errores agregados por tool

```sql
SELECT
  atr.tool_name,
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE atr.status = 'error') AS errores,
  ROUND(AVG(atr.latency_ms)::numeric, 0) AS avg_ms,
  ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY atr.latency_ms)::numeric, 0) AS p95_ms
FROM core.agent_tool_runs atr
WHERE atr.tenant_id = '<tenant_id>'::uuid
  AND atr.created_at >= '<from>'::timestamptz
  AND atr.created_at < '<to>'::timestamptz
GROUP BY atr.tool_name
ORDER BY errores DESC, total DESC;
```

---

## 6. Búsquedas sin producto útil (RAG)

```sql
SELECT
  at.session_id,
  atr.id AS tool_run_id,
  atr.rag_query,
  atr.rag_match_count,
  COUNT(arc.id) FILTER (WHERE arc.included_in_tool_result) AS included_in_result,
  atr.created_at
FROM core.agent_tool_runs atr
JOIN core.agent_turns at ON at.id = atr.turn_id
LEFT JOIN core.agent_rag_candidates arc ON arc.tool_run_id = atr.id
WHERE atr.tenant_id = '<tenant_id>'::uuid
  AND atr.tool_name = 'search_products'
  AND atr.status = 'ok'
  AND atr.created_at >= '<from>'::timestamptz
  AND atr.created_at < '<to>'::timestamptz
GROUP BY at.session_id, atr.id, atr.rag_query, atr.rag_match_count, atr.created_at
HAVING COUNT(arc.id) FILTER (WHERE arc.included_in_tool_result) = 0
ORDER BY atr.created_at DESC
LIMIT 50;
```

> Si `core.agent_tool_runs` no tiene filas para el tenant (traza deshabilitada), inferir desde mensajes IA + keywords y tools mencionadas en `event_type = 'tool_invocation'`.

---

## 7. Keywords de frustración (muestreo)

```sql
SELECT
  c.session_id,
  ce.created_at,
  LEFT(ce.event_payload->>'text', 200) AS excerpt
FROM core.conversation_events ce
JOIN core.conversations c ON c.id = ce.conversation_id
WHERE c.schema_name = '<schema>'
  AND ce.tenant_id = '<tenant_id>'
  AND ce.created_at >= '<from>'::timestamptz
  AND ce.created_at < '<to>'::timestamptz
  AND ce.event_type = 'user_message'
  AND ce.event_payload->>'text' ~* '(no entend|incorrect|error|olvidate|no sirve|reclamo|equivoc|no es eso|ya te dije|no funciona|p[eé]simo|mal)'
ORDER BY ce.created_at DESC
LIMIT 100;
```

Cruzar cada `session_id` con cohorte para aplicar segmentos.

---

## 8. Tickets IA en ventana

```sql
SELECT
  t.id,
  t.client_id,
  t.status,
  t.description,
  t.created_at,
  cli.phone_number
FROM "<schema>".ia_tickets t
LEFT JOIN "<schema>".clients cli ON cli.id::text = t.client_id
WHERE t.created_at >= '<from>'::timestamptz
  AND t.created_at < '<to>'::timestamptz
ORDER BY t.created_at DESC;
```

---

## 9. Sesiones prioritarias (ranking automático)

Combina señales para elegir qué leer en detalle:

```sql
WITH cohort AS (
  -- pegar query §2 sin ORDER BY (active_sessions vía core)
  SELECT c.phone_number AS session_id, c.client_id, c.vendedor_id
  FROM "<schema>".conversations c
  JOIN (
    SELECT DISTINCT cc.session_id
    FROM core.conversation_events ce
    JOIN core.conversations cc ON cc.id = ce.conversation_id
    WHERE cc.schema_name = '<schema>'
      AND ce.tenant_id = '<tenant_id>'
      AND ce.created_at >= '<from>'::timestamptz AND ce.created_at < '<to>'::timestamptz
  ) a ON a.session_id = c.phone_number
),
tool_signals AS (
  SELECT at.session_id,
         COUNT(*) FILTER (WHERE atr.status = 'error') AS tool_errors,
         COUNT(*) FILTER (WHERE atr.tool_name = 'search_products') AS searches
  FROM core.agent_turns at
  JOIN core.agent_tool_runs atr ON atr.turn_id = at.id
  WHERE at.tenant_id = '<tenant_id>'::uuid
    AND atr.created_at >= '<from>'::timestamptz
    AND atr.created_at < '<to>'::timestamptz
  GROUP BY at.session_id
),
frustration AS (
  SELECT DISTINCT c.session_id
  FROM core.conversation_events ce
  JOIN core.conversations c ON c.id = ce.conversation_id
  WHERE c.schema_name = '<schema>'
    AND ce.tenant_id = '<tenant_id>'
    AND ce.created_at >= '<from>'::timestamptz
    AND ce.created_at < '<to>'::timestamptz
    AND ce.event_type = 'user_message'
    AND ce.event_payload->>'text' ~* '(no entend|incorrect|error|reclamo|equivoc|no es eso)'
)
SELECT
  co.session_id,
  COALESCE(ts.tool_errors, 0) AS tool_errors,
  CASE WHEN f.session_id IS NOT NULL THEN 1 ELSE 0 END AS frustration_flag
FROM cohort co
LEFT JOIN tool_signals ts ON ts.session_id = co.session_id
LEFT JOIN frustration f ON f.session_id = co.session_id
ORDER BY
  COALESCE(ts.tool_errors, 0) DESC,
  CASE WHEN f.session_id IS NOT NULL THEN 1 ELSE 0 END DESC,
  co.session_id
LIMIT 30;
```

---

## 10. Contexto seller (si aplica)

```sql
SELECT
  sc.conversation_id,
  cc.session_id,
  sc.seller_id,
  sc.last_selected_client_id,
  sc.pending_client_candidates,
  sc.updated_at
FROM core.seller_context sc
JOIN core.conversations cc ON cc.id = sc.conversation_id
WHERE sc.tenant_id = '<tenant_id>'::uuid
  AND sc.updated_at >= '<from>'::timestamptz;
```

---

## Tablas clave (recordatorio)

| Schema | Tabla | Uso |
|--------|-------|-----|
| `core` | `conversation_events` (+ `conversations`) | **Hilo WhatsApp completo (canónico, spec 013)** |
| `{tenant}` | `n8n_chat_histories` | Hilo legacy (fallback si el tenant no migró) |
| `{tenant}` | `conversations` | client_id / vendedor_id por teléfono |
| `{tenant}` | `clients`, `puntos_venta`, `geo_zones`, `vendedores` | Segmentación |
| `{tenant}` | `ia_tickets` | Reclamos/tickets |
| `core` | `conversations`, `conversation_events` | Memoria agente / hilo |
| `core` | `agent_turns`, `agent_tool_runs`, `agent_rag_candidates` | Trazas tools/RAG |
| `core` | `seller_context` | Estado vendedor |
