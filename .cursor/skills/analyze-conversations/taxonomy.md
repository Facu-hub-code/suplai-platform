# Taxonomía de hallazgos — conversaciones

Clasificar cada issue en **una categoría primaria**. Agregar tags secundarios si aplica.

## Categorías primarias

| ID | Nombre | Descripción | Señales típicas |
|----|--------|-------------|-----------------|
| `product_not_found` | Producto no encontrado | Usuario pidió SKU/nombre y el agente no lo resolvió | `search_products` sin candidatos incluidos; "no encontré", "no tenemos"; RAG vacío |
| `wrong_product` | Producto incorrecto | Agente ofreció/ agregó otro artículo | Usuario corrige ("no era ese", "pedí X"); mismatch SKU en `create_order` |
| `price_or_list_error` | Precio / lista | Precio ausente, lista equivocada, mínimo mal comunicado | `no_price_for_list`, error en tool de precio; queja de total |
| `order_logic_error` | Lógica de pedido | Cantidades, confirmación prematura, edición incorrecta | Confirmó sin tool; duplicó ítems; no reflejó pedido abierto |
| `seller_client_selection` | Selección de cliente (vendedor) | Vendedor no pudo operar sobre el cliente correcto | Desambiguación fallida; `resolve_client_for_seller` error; contexto seller stale |
| `user_frustration` | Desconformidad / frustración | Usuario expresa enojo, abandono, reclamo | "no entendés", "olvidate", insultos, silencio tras error repetido |
| `tool_error` | Error técnico de tool | Falla explícita en runtime | `agent_tool_runs.status = 'error'`; timeout; excepción en logs |
| `unnecessary_escalation` | Escalamiento innecesario | Ticket o derivación cuando el agente podía resolver | Ticket por consulta simple; "te paso con un humano" sin intento |
| `missing_capability` | Capacidad ausente | Usuario pide algo fu fuera de tools | Foto no procesada, pago, tracking — agente no tiene tool |
| `latency_ux` | Latencia / UX | Respuesta muy lenta o demasiado verbosa | Turno >45s; usuario pregunta "¿se colgó?" |
| `prompt_violation` | Incumplimiento de reglas | Agente contradice reglas del tenant o plataforma | Inventó código; confirmó pedido sin `confirm_order`; tono inadecuado |
| `registration_flow` | Flujo de registro | Problemas en onboarding WhatsApp | Eventos `registration_*` fallidos o abandonados |
| `data_gap` | Brecha de datos maestros | Cliente/vendedor/zona mal cargados en BD | Sesión sin match en `conversations`; PDV sin `geo_zone_id` |

## Tags secundarios (opcionales)

- `repeat_issue` — mismo usuario, mismo problema en >1 sesión
- `catalog_gap` — producto existe en ERP pero no en catálogo vectorizado
- `alias_gap` — nombre coloquial no cubierto por alias
- `seller_mode` / `client_mode`
- `free_text_order` — lista pegada / foto simulada
- `after_hours` — fuera de horario comercial declarado

## Keywords de frustración (español rioplatense)

Usar como **heurística**, no como única prueba:

```
no entendés, no me entendés, mal, incorrecto, error, qué carajo, olvidate,
no sirve, inútil, pesimo, pésimo, horrible, no funciona, otra vez,
ya te dije, te lo repetí, no es eso, equivocado, enojado, reclamo,
devolución, devolver, nunca llegó, no me llegó
```

Buscar en `core.conversation_events` con `event_type = 'user_message'` (texto en `event_payload->>'text'`). Fallback legacy: mensajes `type` ∈ (`human`, `user`) de `n8n_chat_histories`.

## Prioridad

| Nivel | Criterio |
|-------|----------|
| 🔴 Alta | Bloquea venta, genera ticket/reclamo, error técnico recurrente, dato incorrecto en pedido confirmado |
| 🟡 Media | Fricción repetida pero con workaround; RAG mejorable; latencia molesta |
| 🟢 Baja | Estilo, verbosidad, mejora marginal de wording |

## Acciones sugeridas por categoría

| Categoría | Acciones típicas |
|-----------|------------------|
| `product_not_found` | `enhance-descriptions`, alias, re-vectorizar, revisar query RAG |
| `wrong_product` | prompt desambiguación, tool `search_products` top-k, casos E2E |
| `price_or_list_error` | healthcheck listas, `default_lista_precios`, reglas mínimo |
| `order_logic_error` | prompt confirmación, snapshot pedido abierto, tests E2E secuenciales |
| `seller_client_selection` | prompt seller, `clear_seller_context`, datos vendedor-cliente |
| `user_frustration` | leer hilo completo; puede ser síntoma de otra categoría |
| `tool_error` | fix código agente/backend; revisar Loki |
| `prompt_violation` | `analyze-system-prompt`, editar `system_prompt` |
| `latency_ux` | desactivar tools, acortar prompt, revisar waterfall Grafana |
