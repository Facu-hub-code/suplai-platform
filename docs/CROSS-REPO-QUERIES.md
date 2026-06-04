# Queries e investigaciones cruzadas

Guía para responder preguntas que involucran UI, API, agente, tienda, ML y datos.

## Patrón recomendado

1. **Acotar el tenant** (`schema_name`, ej. `gonzales`).
2. **MCP Supabase** (stack principal): confirmar tablas en `public`, `core` y tenant.
3. **Identificar qué BD** aplica: Supabase principal vs Postgres del sniffer.
4. **Código**: seguir el flujo desde la capa que dispara el síntoma.

## Escenarios frecuentes

### "El back office muestra X pero el agente hace Y"

1. UI: `backoffice/components/`
2. Proxy: `backoffice/app/api/.../route.ts`
3. Backend: router + service
4. Agente: `agent/app/agent/tools/`
5. BD: MCP `execute_sql`

### "El link de tienda no funciona o el pedido web falla"

1. Agente: `agent/app/agent/tools/catalog.py` (URL `tienda.suplaisales.com/{schema}?wp=...`)
2. Tienda: routing por schema en URL, `lib/tienda-api.ts`
3. Backend: `/login-tienda`, `/{schema}/tienda/productos`, pedidos
4. MCP: productos `en_catalogo`, pedido abierto del cliente

### "Recomendación de combo / frecuencia de compra incorrecta"

1. Sales Engine: `POST .../predict-combo`, debug en `GET .../models/debug`
2. MCP: `{tenant}.pedidos`, `{tenant}.items_pedido` — historial del `cliente_id`
3. Verificar último retrain: ventana `since_days`, peso 90 días recientes
4. Agente: tools `suggest_order_boost*` si consume el motor

### "Analizar conversación real de un vendedor (Kommo)"

1. **No usar MCP Supabase principal** salvo correlación manual.
2. Sniffer: `sniffer/docs/arqui-kommo.md`, tablas `kommo_*`
3. UI: `/admin/kommo/conversations` o API JSON
4. Webhook: `POST /webhook/kommo`

### "¿Por qué falló este pedido/conversación del agente?"

1. MCP: `core.conversations`, `core.agent_turns`
2. Agente: tools de pedido
3. Backend: si pasó por API tienda o back office

### "Agregar campo configurable desde back office al agente"

1. Spec + migración en `backend/`
2. UI en `backoffice/`
3. Consumo en `agent/`
4. MCP para verificar persistencia

## SQL útil — Supabase principal

```sql
-- Distribuidora por schema
SELECT id, nombre, schema_name, activa
FROM public.distribuidoras
WHERE schema_name = 'gonzales';

-- Historial de pedidos de un cliente (sales-engine / agente)
SELECT p.id, p.fecha, p.estado, p.cliente_id
FROM gonzales.pedidos p
WHERE p.cliente_id = '4'
ORDER BY p.fecha DESC
LIMIT 20;

-- Productos en catálogo tienda/agente
SELECT product_code, nombre, en_catalogo
FROM gonzales.productos
WHERE en_catalogo IS TRUE
LIMIT 10;
```

## SQL útil — Sniffer (Postgres espejo, si mismo MCP no aplica)

Consultar en la BD del sniffer (ver `sniffer/.env`):

```sql
SELECT id, talk_id, updated_at
FROM kommo_conversations
ORDER BY updated_at DESC
LIMIT 10;
```

## Referencias OpenAPI

- Backend live: `https://web-production-f544f.up.railway.app/openapi.json`
- Copia local back office: `backoffice/doc/openapi.json`
- Tienda: skill `tienda/.cursor/skills/suplai-tienda-api/SKILL.md`

## Skill del workspace

`.cursor/skills/cross-repo-investigation/SKILL.md`
