# 099 — Claude MCP: estrategias, conversaciones y aliases

**Estado:** Borrador  
**Fecha:** 2026-10-08  
**Repos:** `backend-supabase` (tools, scopes, preview), `suplai-sales-claude-plugin` (skills), `suplai-platform` (este spec)  
**Serie:** [objetivos de capacidades](../claude-mcp/objetivos-capacidades.md), caso 4. Depende del [095](./095-claude-mcp-carga-clientes-productos.md), el [096](./096-claude-mcp-plantillas.md) y el [097](./097-claude-mcp-grupos-agendas.md).  
**Ramas sugeridas:** `feat/claude-mcp-estrategias` en backend y en el plugin  
**Relaciona:** `services/estrategias_service.py::create_estrategia`, `routers/etiquetas.py`, `routers/metricas.py` (`/agente`), `core.agent_tool_runs` (spec 024, `rag_query` y `rag_match_count`), `productos_aliases`.

---

## Objetivo

Con clientes, una plantilla y una agenda ya armados, el gerente deja en Claude la operación recurrente: una estrategia que apunta a ese grupo y a esa agenda, y, si hace falta, una etiqueta sobre esos comercios. También pregunta qué está pasando en las conversaciones. A partir de búsquedas que el agente no resolvió, propone sinónimos y, con un sí, los agrega al catálogo.

Claude reconoce el patrón sobre los números que devuelve la tool. No hay un modelo nuevo. No se reescribe el prompt del agente.

### Métricas de éxito

- No se crea una estrategia si la plantilla de esa agenda no está `APPROVED` en Meta.
- Si la persona marca la estrategia como promo, el grupo tiene que filtrar por la lista de esa promoción.
- Confirmar una estrategia no apaga ni prende la agenda. El horario sigue siendo el del [097](./097-claude-mcp-grupos-agendas.md).
- Las métricas de conversaciones no traen teléfono, nombre ni cuerpo del mensaje.
- Un alias se inserta solo para un SKU que existe. Si ese texto ya apunta a otro SKU, la fila se rechaza. Confirmar re-vectoriza esos códigos.
- En `demo`, una estrategia de prueba queda creada una sola vez y un alias rechazado no aparece en `productos_aliases`.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Partir el caso | Una entrega con tres familias: estrategia (y etiqueta), lectura de conversaciones, aliases | El objetivo es una sola operación comercial. Partirlo en tres specs atrasaría el cierre de la serie sin cambiar las reglas. | Tres specs. El 4 ya dice que conviene partir el trabajo, y acá se parte en tools, no en documentos. |
| Scopes | `estrategias:escribir` para estrategia, etiqueta y métricas. `aliases:escribir` para las búsquedas sin match y el alta de sinónimos | Una estrategia manda mensajes recurrentes: merece su línea en el consentimiento. Un alias mal puesto cambia lo que el agente vende, y no es lo mismo que programar un envío. `required_scopes` sigue en `pedidos:leer`. | Un solo scope para todo el caso 4. Quien acepta “ver cómo van las charlas” no aceptó agregar sinónimos. |
| Estrategia | `previsualizar_estrategia` y `confirmar_estrategia`. El confirm llama `create_estrategia` con el `meta_plantilla_id` de la agenda | El servicio exige grupo, agenda y una salida. La salida de esta v1 es la plantilla que la agenda ya tiene, no la biblioteca de skeletons. | `salida_skeleton_ids`. Es otro producto (presupuesto, temas, gates). |
| Activo | Se crea como la deja el servicio (`activo = true`) y no se llama `toggle_activo` | Apagar la estrategia con ese toggle también apaga la agenda si nadie más la usa. El horario lo decidió el 097. El preview dice que la estrategia nace activa y que el sender solo dispara si la agenda también lo está. | Crear y después apagar “por las dudas”. Rompe el horario que la persona ya había aceptado. |
| Plantilla | La de `agenda.meta_plantilla_id`, del mismo tenant, estado `APPROVED` | El objetivo lo pide. Una plantilla en revisión no tiene estrategia. | Guardar la estrategia igual y prenderla cuando Meta apruebe. No hay job para eso en esta v1. |
| Promo | Si viene `promocion_id`, `grupo.lista_precios_id` tiene que ser una lista de esa promo. Si no viene, el preview dice que no está atada a una promoción | Es la misma regla del 096 y del 097. La estrategia no guarda el objetivo de la plantilla. | Inferir la promo leyendo el cuerpo en Meta. |
| Modo | `puntual`, o `ciclo` con cadence `14_dias` o `1_mes` | Son los valores que ya valida `EstrategiaCreate`. El ancla de semana queda en el lunes de `America/Argentina/Buenos_Aires` salvo que la persona nombre otro día. | `smart_timing`, presupuesto y follow-up. |
| Etiqueta | `listar_etiquetas` y un preview/confirm que asigna una etiqueta existente a los clientes del grupo, o crea una etiqueta de un solo nombre si no existe | Sin eso, el grupo del 097 no puede filtrar por una etiqueta que el gerente acaba de nombrar. Se asignan solo los miembros de ese grupo, no la cartera. | `assign-hierarchical-bulk` sobre códigos sueltos. Es fácil etiquetar de más. |
| Conversaciones | `metricas_conversaciones` devuelve los agregados de `GET /metricas/agente` y, como ejemplo, hasta cinco filas con fecha, nombre de plantilla y si hubo respuesta | El texto crudo es sensible. El detalle del backoffice trae teléfono. Acá no. Los patrones los arma Claude con esos números. | El historial de `conversation_events`. |
| Búsquedas sin match | `busquedas_sin_match` lee `core.agent_tool_runs` con `tool_name = search_products` y `rag_match_count = 0`, agrupado por `rag_query`, últimos 30 días, tope 20 | Ahí está la consulta y el conteo (spec 024). `core.agent_tool_executions` no guarda el texto a propósito. | Inventar búsquedas desde el log liviano, que no tiene args. |
| Sin traza | Si el tenant no tiene `metadata.implementation_debug.trace_enabled`, la tool responde `disponible: false` | Esa tabla solo se llena con la traza del lab. Una lista vacía parecería que el agente encuentra todo. | Prender la traza desde el conector. Cambia observabilidad del tenant. |
| Aliases | Preview y confirm. Insert `productos_aliases` como la carga del 095 (`alias_norm`, `alias_raw`, peso 1) y vectorización de esos SKU | El agente matchea alias y vector. Un `ON CONFLICT` no pisa un alias que ya apunta a otro código: esa fila se rechaza y se explica. | Reescribir `alias_norm` hacia el SKU nuevo. Un sinónimo cambiado de producto es un error de venta. |
| Prompt | No hay tool. La skill dice que el cambio de prompt se hace en el backoffice | El objetivo lo deja afuera de la escritura del MCP. | Un update de `distribuidoras` con el system prompt. |
| Preview | Misma tabla `mcp_accion_previews`, tipos `estrategia`, `etiqueta` y `aliases` | Mismo lock de 30 minutos. Confirmar dos veces no duplica. | Una tabla por familia. |
| Auditoría | Ids, conteos, `preview_id`. Sin nombres de comercio, teléfonos ni el texto de la búsqueda en `parametros` | La búsqueda puede nombrar un producto de un cliente. El resultado de la tool sí lleva el texto, porque Claude tiene que proponer el alias. | Auditar la frase completa. |

---

## Alcance

### Incluido

**Estrategia y etiqueta** (`estrategias:escribir`)

- `listar_etiquetas`: id y nombre. Sin la lista de clientes.
- `previsualizar_etiqueta` / `confirmar_etiqueta`: una etiqueta (existente o nombre nuevo) y un `grupo_id`. El preview dice cuántos clientes de cartera del grupo la recibirían. Confirmar crea la etiqueta solo si el nombre no existe y asigna esos clientes. No borra otras etiquetas.
- `previsualizar_estrategia` / `confirmar_estrategia`: `nombre`, `grupo_id`, `agenda_id`, `modo` (`puntual` o `ciclo`) y, si es ciclo, la cadence. `promocion_id` opcional. El preview muestra el nombre de la plantilla, si está aprobada, si la agenda está activa, el conteo del grupo y la línea de promo. Sin `preview_id` si la plantilla no está aprobada, si la agenda no es de ese grupo, o si la promo no coincide con la lista.
- Confirmar no llama `toggle_activo`.

**Conversaciones** (`estrategias:escribir`)

- `metricas_conversaciones`: rango opcional `fecha_desde` y `fecha_hasta` (los dos o ninguno). Conteos de iniciadas, únicas, respondidas, carritos y pedidos confirmados. Hasta cinco ejemplos `{fecha, plantilla, respondio}`.
- La skill dice que el patrón lo redacta Claude con esos datos y no pide otra tool para “detectar patrones”.

**Aliases** (`aliases:escribir`)

- `busquedas_sin_match`: frases y cuántas veces volvieron vacías. Si no hay traza, lo dice.
- `previsualizar_aliases` / `confirmar_aliases`: filas `{alias, product_code}`. Hasta 100. El SKU tiene que existir. Si el alias ya es de otro código, la fila se rechaza. Confirmar inserta las aceptadas y encola la vectorización. No llama `ai_backfill_productos`.

`manual-conector` suma estas tools. Sigue sin editar el prompt, sin borrar y sin disparar el WhatsApp desde el chat.

### Fuera de alcance

- Reentrenar sales-engine.
- Cambiar el system prompt o apagar tools del agente. La skill indica el backoffice.
- Skeletons de salida, presupuesto, `smart_timing` y secuencias de follow-up.
- El calendario mensual (spec 031) y la agenda Pareto (spec 080).
- Historial completo de mensajes y ejemplos con teléfono o cuerpo.
- Prender `trace_enabled`.
- Desasignar etiquetas o etiquetar por código suelto fuera de un grupo.
- Mandar el mensaje de la estrategia desde el chat.

---

## Orden de implementación

1. Mergeados el 095, el 096 y el 097. Tiene que existir `mcp_accion_previews` y una agenda con plantilla.
2. `backend-supabase`, rama `feat/claude-mcp-estrategias` desde `origin/main`. Migración del check, scopes, tools, tests.
3. Aplicar la migración antes de probar el confirm.
4. Merge del backend.
5. Plugin, misma rama: skills `estrategias`, `conversaciones` y `aliases`, y el manual. Después del backend.

Reconectar para recibir `estrategias:escribir` y `aliases:escribir`.

---

## Migración de base de datos

`sql/150_mcp_accion_previews_estrategias.sql`.

Amplía el check de `public.mcp_accion_previews.tipo` con `estrategia`, `etiqueta` y `aliases`. Misma tabla y el mismo RLS. Sin GRANT a `mcp_connector`.

Sin columnas nuevas en `estrategias`, `etiquetas`, `productos_aliases` ni `core.agent_tool_runs`.

Rollback: restaurar el check anterior y borrar las filas de estos tipos. No borra una estrategia ya confirmada.

---

## Plan de prueba en CI/CD

Pytest en `backend-supabase`:

- Plantilla de la agenda en estado distinto de `APPROVED` → sin `preview_id`.
- Agenda de otro grupo, o plantilla de otro tenant → sin preview.
- `promocion_id` con lista distinta a la del grupo → sin preview.
- Confirmar no llama `toggle_activo`. El payload que llega a `create_estrategia` trae el `meta_plantilla_id` de la agenda y no trae `salida_skeleton_ids`.
- Confirmar dos veces el mismo preview no crea otra estrategia.
- `metricas_conversaciones` no incluye claves `phone`, `telefono` ni `body` en el JSON de respuesta.
- Sin `trace_enabled`, `busquedas_sin_match` responde `disponible: false` y no lee `args_json`.
- Alias de un SKU inexistente, o ya usado por otro código → fila rechazada y fuera del payload.
- Confirmar aliases encola vectorización y no llama `ai_backfill_productos`.
- La auditoría de aliases no incluye el texto del alias.
- Annotations y scopes en el schema de las tools.

El CI (`pytest`) sigue verde. Meta, la traza y los inserts se mockean.

Gap: el plugin no tiene CI. Se revisa a mano.

---

## Plan de prueba humana

Tenant `demo`. No usar un tenant de un cliente. Claude reconectado, con los dos permisos nuevos. Backend `8000` y MCP `8100` en local, o los dos servicios deployados.

Hace falta un grupo, una agenda y una plantilla aprobada del `demo`, los del 097. Si la única plantilla sigue en revisión, el preview de estrategia se niega y eso es el OK de ese paso.

Pasos:

1. “¿Cómo vienen las conversaciones?” muestra conteos y, si hay ejemplos, fecha y plantilla, sin teléfono.
2. Pedir una estrategia semanal sobre ese grupo y esa agenda. Ver plantilla, conteo y que va a nacer activa sin cambiar el horario.
3. Decir que no. No hay fila nueva en `demo.estrategias`.
4. Decir que sí. Existe una. La agenda conserva el `activo` que tenía.
5. Pedir la misma confirmación otra vez. No se duplica.
6. “¿Qué no está encontrando el agente?” Si `demo` no tiene traza, la respuesta lo dice. Si tiene, aparecen frases y conteos.
7. Proponer un alias para un SKU que existe y otro para un código inventado. El inventado se rechaza. El válido, después del sí, está en `productos_aliases` y la vectorización quedó encolada.
8. “Cambiá el prompt del agente.” Claude indica el backoffice y no llama una tool de escritura.

OK: la estrategia no se duplicó, el alias rechazado no se guardó y el manual ya incluye estrategias y sinónimos.
