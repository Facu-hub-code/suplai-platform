---
name: suplai-supabase-mcp
description: >-
  Use when querying Suplai production data via Supabase MCP (execute_sql,
  list_tables): tenants, schemas, envíos, pedidos, conversaciones, catálogo,
  o cualquier pregunta de "qué hay en la base". Also when the user mentions
  Gonzales, del_corro, tonadita, cordoba_frost, demo, HSM, agendas, or
  schema_name.
when-to-use: supabase, MCP, tenant, schema, SQL, gonzales, envíos, pedidos
---

# Suplai — MCP Supabase

## Conexión

| Dato | Valor |
|------|--------|
| Proyecto | `cvlbietibaaehgeimxgw` (Suplai-east) |
| Tool SQL | `execute_sql` con `project_id: cvlbietibaaehgeimxgw` |
| Tool esquema | `list_tables` con `verbose: true` |

MCP caído / timeout: decilo. No completes números de memoria.

## Mapa de schemas

| Schema | Qué hay |
|--------|---------|
| `public` | `distribuidoras` (tenant maestro: `id`, `nombre`, `schema_name`) y `meta_plantillas` (`tenant_id`, `template_name`, `category`, `variable_columns`, `media_url`) |
| `core` | Conversaciones del agente: `conversations` (`schema_name`, `session_id`, `tenant_id`), `conversation_events` |
| `{tenant}` | Operación: `clients`, `agenda`, `grupos`, `envios_plantillas`, `pedidos`, `productos`, `n8n_chat_histories` (legacy) |

Resolver tenant siempre:

```sql
SELECT id::text AS tenant_id, nombre, schema_name
FROM public.distribuidoras
WHERE schema_name = '<schema>'
LIMIT 1;
```

Tenants habituales: `gonzales`, `demo`, `del_corro`, `tonadita`, `cordoba_frost`. Alias "Gonzalez Garcia" / "Gonzales" → `gonzales`.

## Reglas de query

1. `list_tables` en `public` + `core` + `{schema}` si no estás seguro de columnas.
2. Una llamada con SQL consolidado (varios `SELECT` separados por `;` o un `json_build_object`).
3. Filtro temporal en timestamptz con ventana ART, no `created_at::date` (eso es UTC):

```sql
-- "ayer" en Argentina
AND col >= (CURRENT_DATE AT TIME ZONE 'America/Argentina/Buenos_Aires' - INTERVAL '1 day')
AND col <  (CURRENT_DATE AT TIME ZONE 'America/Argentina/Buenos_Aires')
```

4. Teléfono: `right(regexp_replace(COALESCE(phone,''), '[^0-9]', '', 'g'), 10)` para joinear `session_id` ↔ `clients.phone_number`.
5. Pedidos vivos: `deleted_at IS NULL`.
6. Default read-only. Escritura solo con pedido explícito + schema repetido en voz alta.

## Errores frecuentes

| Error | Qué hacer |
|-------|-----------|
| columna no existe | `list_tables` verbose; no adivinar |
| schema no existe | listar `schema_name` en `distribuidoras` |
| timeout MCP | reintentar 1 vez; si falla, informar |
| números de un dump local | ignorar; la fuente es MCP |

## Output

Lead with the answer. Citar schema, ventana (ART), y conteos. Separar **hecho SQL** vs **hipótesis**.
