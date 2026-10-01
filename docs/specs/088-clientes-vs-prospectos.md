# 088 — Clientes y prospectos, bien separados

**Estado:** Borrador. Opción B confirmada (2026-09-30).  
**Fecha:** 2026-09-30  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`, `agente-conversacional-multi_tenant`  
**Ramas sugeridas:** `feat/clientes-vs-prospectos`  
**Serie:** Prospección outbound v2 (087 a 092).  
**Relaciona:** [071](./071-maps-icp-prospeccion-decisor.md) (alta de prospecto antes del HSM), [083](./083-campana-outbound-mapas.md), [084](./084-agente-prospeccion-funnel.md) (router por `is_prospect` y audiencia de conversaciones), [089](./089-validacion-whatsapp-previa.md), [091](./091-enriquecimiento-web-prospecto.md).

---

## Objetivo

En la sección Clientes, el supervisor tiene que ver **por un lado su cartera** y **por otro lado los prospectos** que consiguió el agente, sin que se mezclen. Cuando un prospecto compra por primera vez, pasa solo a la cartera.

### Definición

- **Cliente:** está cargado en el sistema de la distribuidora (vino del ERP, de una importación o lo cargó una persona) **o** tiene al menos un pedido `confirmado` o `descargado`.
- **Prospecto:** lo consiguió Suplai (directorio del mapa, decisor referido por el agente, alta por el agente) y todavía no compró.

### Métricas de éxito

- La tabla de Clientes, por defecto, muestra solo clientes. En `demo`, hoy muestra 249, de los cuales 183 son prospectos.
- Un prospecto con su primer pedido confirmado aparece en Clientes sin intervención humana.
- Métricas, grupos, estrategias y Field no cuentan prospectos salvo que se pida.

---

## Diagnóstico (datos de producción, septiembre 2026)

- No hay tabla de prospectos. El prospecto es una fila de `{schema}.clients` con `etiqueta = 'prospect'` (texto libre). Se escribe en `clientes_service.py` y `pdv_service.py` cuando llega `is_prospect = true`.
- La etiqueta no es consistente. En `demo`: 67 filas sin etiqueta y 183 con grafías de prospecto (`prospect`, `PROSPECTO`); 14 de esas ya tienen pedido confirmado.
- **No hay promoción.** En `demo`, 14 filas marcadas como prospecto ya tienen pedidos `confirmado` o `descargado` y siguen como prospecto.
- La audiencia de Conversaciones (`backend-supabase/data_access/conversaciones.py`) ya separa prospecto, cliente y vendedor: `etiqueta = 'prospect'` o fila en `campaign_prospect`. El router del agente (`app/agent/prospect/store.py`) usa la misma regla.
- **11 tablas del tenant tienen FK a `clients`:** `agenda`, `client_locations`, `client_operating_profiles`, `cliente_producto_favorito`, `clientes_aliases`, `estrategia_cohort_members`, `estrategia_dispatch_replies`, `estrategia_dispatches`, `estrategia_member_state`, `estrategia_schedule_decisions` y `field_tasks`. Además, sin FK declarada: `pedidos.cliente_id`, `conversations.client_id` y `campaign_prospect.customer_id`.

---

## Tabla física separada o no

Tu propuesta fue trabajar los prospectos en tablas distintas. Hay dos formas de hacerlo:

| | A. Tabla `prospects` aparte | B. Misma `clients`, ciclo de vida explícito y perfil aparte (**recomendada**) |
|---|---|---|
| Qué es | Los prospectos viven en `{schema}.prospects`. Al primer pedido se copian a `clients` y se borran de `prospects` | `clients` sigue siendo la identidad (teléfono, nombre, ubicación). Una columna `lifecycle` (`prospect` o `client`) dice qué es. Todo lo que es solo de prospección va a una tabla 1:1 `prospect_profiles` |
| Conversaciones del agente | `conversations.client_id` tiene que apuntar a una de dos tablas, o hay que duplicar la columna | Igual que hoy |
| Ubicación en el mapa | `client_locations` tiene FK a `clients`: hace falta una tabla de ubicaciones de prospectos o una FK polimórfica | Igual que hoy |
| Decisor (071, 084) | El swap de primario y el HSM operan sobre `clients`: hay que reescribirlos | Igual que hoy |
| Promoción | Mover la fila y **reescribir los ids** en conversaciones, eventos, campaña, ubicaciones y agenda. Si algo falla a mitad, el historial queda partido | Un `UPDATE lifecycle = 'client'` |
| Pedido de un prospecto | El pedido necesita un `cliente_id` antes de que el prospecto sea cliente: hay que promoverlo en la misma transacción del pedido, y el agente vendedor necesita que ya exista | Funciona como hoy |
| Separación en la UI | Total | Total: dos vistas con endpoints y columnas propias |
| Riesgo de mezclar | Nulo | Bajo, si todas las consultas de cartera filtran `lifecycle = 'client'` (se centraliza en una vista SQL) |
| Esfuerzo | Alto: toca 14 relaciones, el agente, el mapa y Field | Medio: columna, backfill, filtro centralizado, UI |

**Recomendación: B.** La diferencia que querés ver (dos tablas en la UI, con datos distintos) se logra igual, y se evita partir la identidad del comercio en dos lugares justo en el momento más delicado, que es cuando compra por primera vez. Los datos propios del prospecto (fuente, campaña, validación de WhatsApp, enriquecimiento, `icp_fit`) sí van a una tabla aparte, `prospect_profiles`, así que «tablas distintas» se cumple para lo que es solo de prospección.

**Decisión (2026-09-30): opción B.**

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Modelo | Opción B: `clients.lifecycle` más `prospect_profiles` 1:1 | Ver la comparación de arriba | Tabla `prospects` separada |
| Fuente de verdad | `lifecycle` es una columna con check (`prospect` o `client`), no la etiqueta | `etiqueta` es texto libre de uso comercial y ya tiene dos grafías | Seguir usando `etiqueta = 'prospect'` |
| Origen | Columna `origen_alta` en `clients`: `erp`, `import`, `manual`, `directorio`, `decisor`, `agente` | Para la regla «cargado en sistema» hace falta saber de dónde vino. Hoy no se guarda | Inferirlo por `codigo` o `partner_erp_id` |
| Regla de `lifecycle` al alta | `erp`, `import` y `manual` nacen `client`. `directorio`, `decisor` y `agente` nacen `prospect` | Es la definición: lo cargó la distribuidora o lo consiguió Suplai | Todo nace prospecto |
| Promoción | Trigger en `pedidos`: al pasar a `confirmado` o `descargado`, si el cliente es `prospect`, pasa a `client` con `promoted_at` y `promoted_by_pedido_id`. También promueve si el sync del ERP lo trae con código | Tiene que pasar siempre, venga el pedido del agente, de la tienda, de Field o del ERP. Un trigger no depende de que cada camino se acuerde | Promover desde el servicio de pedidos (hay varios caminos de escritura) |
| Sin vuelta atrás | Un `client` no vuelve a `prospect` | Una vez que compró es cartera, aunque deje de comprar (eso es churn, otro concepto) | Volver a prospecto después de N días sin compra |
| Alta por el recepcionista | Un comercio que escribe por su cuenta y se registra con el agente nace `prospect` (`origen_alta = agente`) hasta su primer pedido | Coincide con la definición: no está cargado y no compró | Nacer `client` |
| Filtro central | Vistas `{schema}.v_cartera` (`lifecycle = 'client'`) y `{schema}.v_prospectos` | Métricas, grupos, estrategias y Field consumen la vista y no repiten la condición | Agregar `WHERE` en cada consulta |
| `etiqueta` | Se deja de escribir `prospect` como etiqueta. Las existentes se migran a `lifecycle` y se limpian | Una sola señal | Mantener las dos sincronizadas |
| Router del agente y audiencia | Pasan a leer `lifecycle` (más `campaign_prospect`, como hoy) | Misma lógica, fuente limpia | — |

---

## Alcance explícito

### Incluido (v1)

- Columnas `lifecycle`, `origen_alta`, `promoted_at`, `promoted_by_pedido_id` en `clients`, y tabla `prospect_profiles`.
- Backfill desde `etiqueta` y pedidos.
- Trigger de promoción.
- Vistas `v_cartera` y `v_prospectos`, y su uso en Métricas, grupos, estrategias, Field y el filtro «Solo importantes».
- Toggle **Clientes | Prospectos** en la barra de la tabla (`components/clients-table/clients-table-view.tsx`, la franja de «Desliza horizontalmente… 249 clientes»), con el contador de cada lado.
- Columnas propias de la vista Prospectos: comercio, fuente, campaña, etapa del chat (084), WhatsApp validado (089), encaje con el ICP (091), decisor, días desde el primer mensaje.
- Acción «Pasar a cliente» manual, para casos en que la distribuidora lo carga en su sistema sin pedido todavía (queda `origen_alta` original y `promoted_by = operador`).
- Router del agente y audiencia de Conversaciones leyendo `lifecycle`.

### Fuera de alcance

- Tabla física separada (opción A), descartada.
- Borrar prospectos viejos o inactivos automáticamente.
- Cambios en la tienda: un prospecto que entra a la tienda y compra se promueve por el trigger, sin cambio en la tienda.

---

## Superficie

### Toggle

En la franja de la tabla: `Clientes (81) | Prospectos (169)` (valores de `demo` después del backfill). Default: Clientes. El toggle queda en la URL (`?vista=prospectos`) para poder compartir el link.

### Vista Prospectos

| Columna | Fuente |
|---------|--------|
| Comercio y teléfono | `clients` |
| Fuente | `origen_alta` (Mapa, Decisor referido, Escribió por WhatsApp) |
| Campaña y zona | `campaign_prospect` → `campaign` |
| Etapa del chat | `campaign_prospect.chat_stage` (084) |
| Decisor | nombre y rol (084) |
| WhatsApp | `whatsapp_estado` y si es Business (089) |
| Encaje con el ICP | `campaign_prospect.icp_fit` (091) |
| Primer mensaje | Cuerpo interpolado (`rendered_body`) + `template_sent_at` + fuente del saludo (`greeting_name_source`) (091). Si no hay cuerpo guardado, solo la fecha. |

Filtros: campaña, zona, etapa, encaje, «respondieron», «necesitan a alguien».

### Vista Clientes

La tabla de hoy, con la misma lista de columnas, leyendo `v_cartera`. Una columna opcional «Llegó por Suplai» (prospectos promovidos) con la fecha de promoción, para ver cuántos clientes trajo la prospección.

---

## Requisitos funcionales

- `RF-1` Todo alta de cliente escribe `origen_alta` y `lifecycle` según la regla. `is_prospect = true` en la API equivale a `origen_alta` de prospección.
- `RF-2` El trigger promueve a `client` al primer pedido `confirmado` o `descargado`, en la misma transacción.
- `RF-3` El sync del ERP promueve a `client` si trae el comercio con código de cliente.
- `RF-4` `GET /{schema}/bff/clients?lifecycle=client|prospect` filtra, y devuelve los dos contadores.
- `RF-5` Métricas, grupos, estrategias y Field usan `v_cartera`. Un grupo o estrategia puede pedir prospectos explícitamente.
- `RF-6` El router del agente usa `lifecycle = 'prospect'` (más `campaign_prospect`) para mandar al grafo `prospect`, igual que 084.
- `RF-7` «Pasar a cliente» manual registra quién y cuándo.

## Requisitos no funcionales

- `RNF-1` El trigger es un `UPDATE` de una fila; no llama a nada externo.
- `RNF-2` Índice por `(lifecycle)` en `clients`.
- `RNF-3` La tabla de prospectos pagina del lado del servidor con una sola query (join a `campaign_prospect` y `prospect_profiles`).

---

## Criterios de aceptación

### `AC-1` Separación por defecto

- **Given** `demo` después del backfill: 81 clientes (67 sin etiqueta más 14 prospectos que ya compraron) y 169 prospectos.
- **When** se abre Clientes.
- **Then** el toggle dice `Clientes (81) | Prospectos (169)` y la tabla solo trae cartera.

### `AC-2` Promoción

- **Given** un prospecto de campaña.
- **When** su primer pedido pasa a `confirmado`.
- **Then** sale de Prospectos, aparece en Clientes con «Llegó por Suplai» y `promoted_by_pedido_id`.

### `AC-3` Backfill de los que ya compraron

- **Given** los 14 prospectos de `demo` con pedidos confirmados.
- **When** corre la migración.
- **Then** quedan como `client`.

### `AC-4` Métricas sin prospectos

- **Given** el filtro «Solo importantes».
- **When** se calcula.
- **Then** no incluye prospectos.

### `AC-5` Router igual que antes

- **Given** un prospecto abierto y un cliente de cartera.
- **When** escriben.
- **Then** el prospecto va al grafo `prospect` y el cliente al vendedor, igual que en 084.

---

## Casos borde

- `CB-1` Un cliente del ERP que también apareció en una búsqueda del mapa: 083 ya excluye clientes actuales; si igual se da de alta por decisor, gana `client` porque existe en el ERP.
- `CB-2` Pedido cancelado después de confirmado: el comercio queda `client` (no hay vuelta atrás).
- `CB-3` Filas con `etiqueta = 'PROSPECTO'` u otras grafías: el backfill las trata como prospecto.
- `CB-4` Prospecto sin fila en `campaign_prospect` (alta de 071 vieja o registro por el agente): aparece en Prospectos con fuente y sin campaña.

---

## Migración de base de datos

En cada tenant:

- `clients.lifecycle text not null default 'client' check (lifecycle in ('prospect','client'))`.
- `clients.origen_alta text` (check con los seis valores; null en filas viejas sin dato).
- `clients.promoted_at timestamptz`, `clients.promoted_by_pedido_id bigint`, `clients.promoted_by text`.
- `prospect_profiles`: `client_id` (PK, FK a `clients`), `source`, `place_ref` (092), `first_campaign_id`, `enrichment_summary` jsonb, `created_at`.
- Trigger `after update of estado on pedidos` (y `after insert`) que promueve.
- Vistas `v_cartera` y `v_prospectos`.

**Backfill (en este orden):**

1. `lifecycle = 'prospect'` donde `lower(etiqueta) in ('prospect','prospecto')` o hay fila en `campaign_prospect`.
2. De esos, `lifecycle = 'client'` si tienen pedido `confirmado` o `descargado`, con `promoted_at` = fecha del primer pedido.
3. `origen_alta = 'directorio'` para los que tienen `campaign_prospect` o `metadata.google_place_id`; el resto de prospectos queda `agente`; los clientes quedan null (dato histórico desconocido).
4. `etiqueta = null` donde era `prospect` o `PROSPECTO`.

**Orden:** migración y backfill → backend (vistas en los servicios, BFF) → agente (router) → backoffice (toggle). El agente puede seguir leyendo la etiqueta hasta mergear su PR solo si el paso 4 del backfill se corre **después** del deploy del agente; por eso el paso 4 va en una migración aparte.

**Rollback:** las columnas quedan; el router vuelve a la etiqueta solo si no se corrió el paso 4. Por eso el paso 4 se corre cuando los tres PRs están en producción.

**Riesgo:** una consulta de cartera que no pase a `v_cartera` sigue mezclando. Mitigación: buscar en backend todas las lecturas de `clients` para Métricas, grupos, estrategias y Field, y listarlas en el PR.

**Riesgo — vistas atadas a `clients`:** `v_cartera` y `v_prospectos` son `SELECT *`, así que dependen de todas las columnas de `clients`. Una migración futura con `ALTER COLUMN … TYPE`, `DROP COLUMN` o `RENAME COLUMN` falla o deja la vista desfasada si no borra y recrea las dos vistas en la misma migración. Nunca destrabar con `CASCADE`. Documentado en `backend-supabase/docs/db-structure/clients-lifecycle.md`, en la cabecera de `sql/138` y en la regla `.cursor/rules/clients-lifecycle-views.mdc`.

**Riesgo — tenants nuevos:** el alta de tenants clona con `LIKE … INCLUDING ALL`, que no copia triggers, FKs ni vistas. `core/tenancy.py::install_clients_lifecycle_objects` los instala; sin eso un tenant nuevo no promovería prospectos con el primer pedido.

---

## Implementación (desvíos y decisiones tomadas al construir)

| Decisión | Por qué | Alternativa descartada |
|----------|---------|------------------------|
| Trigger `BEFORE INSERT OR UPDATE` en `clients` que deriva `lifecycle` y `origen_alta` de la etiqueta | Todos los caminos de alta (backend, agente, scripts de onboarding) escriben `etiqueta = 'prospect'`. El trigger cubre los que no se tocaron y se retira junto con el paso 4 | Cambiar cada `INSERT` y dejar huecos |
| El mismo trigger no deja volver de `client` a `prospect` | CB-2 y «dejar de comprar es churn» | Chequearlo en cada servicio |
| RF-3 se resuelve en el trigger: un prospecto que **recibe** `codigo` o `partner_erp_id` pasa a `client` con `promoted_by = 'erp'` | El sync del ERP no necesita cambios. Se mira el cambio (de vacío a valor), no la presencia, para no promover en cada `UPDATE` por datos que ya estaban | Tocar `erp_sync_service` |
| Los predicados usan `c.lifecycle = 'client'` en lugar de leer `v_cartera` | Es el mismo filtro, las consultas quedan con su alias y joins, y el diff es de una línea por consulta. Las vistas quedan para SQL manual y dashboards | Reescribir cada `FROM clients` como `FROM v_cartera` |
| Las lecturas que entran por `pedidos` confirmados no se tocan | Por el trigger de promoción, todo comercio con pedido confirmado ya es `client` | Filtrar dos veces |
| El vínculo prospecto ↔ campaña usa `customer_id` o, si falta, `provider_place_id = metadata.google_place_id` | En `demo` `campaign_prospect.customer_id` está vacío en las 34 filas; por `place_id` casan las 34 | Backfill de `customer_id` (queda: el agente lo completa al guardar la etapa) |
| El alta por el agente nace `prospect` con `origen_alta = 'agente'` salvo que dé código de cliente; el router solo manda al grafo `prospect` a los que tienen campaña u origen `directorio` / `decisor` | CB-4 pide que aparezcan en Prospectos, pero quien escribió solo vino a comprar y tiene que atenderlo el vendedor. Con el primer pedido se promueve | Mandar todo prospecto al grafo de calificación |
| «Pasar a cliente» guarda `promoted_by = 'operador:<email>'` | El backend no tiene usuario autenticado en los routers; el backoffice manda el email del operador logueado | Columna nueva para el actor |
| `GET /bff/clients` sin `lifecycle` sigue trayendo todo | El backend se deploya antes que el backoffice; la pantalla actual no cambia hasta que llega el toggle | Default `client` en backend |
| Filtros de la vista Prospectos en v1: búsqueda. El endpoint ya acepta campaña, etapa, «respondieron» y «necesitan a alguien» | La UI de filtros va con 089/091, cuando haya encaje ICP y WhatsApp validado | Hacer la barra completa ahora |
| El pedido de prospectos explícitos en grupos y estrategias (RF-5, segunda parte) queda para después | Nadie lo pide hoy y el default seguro es cartera | — |

### Consumidores que pasan a cartera (`lifecycle = 'client'`)

| Archivo | Consultas |
|---------|-----------|
| `data_access/comercial_metrics.py` | `prioridad_universe` (resumen, series, detalle y candidatos de «Solo importantes»), `assigned_clients` |
| `data_access/pdvs_metrics.py` | `assigned_clients` (métricas por PDV y resumen) |
| `data_access/vendedores_metrics.py` | cartera asignada por vendedor |
| `data_access/comercial_alarms.py` | universo de prioridad y listas de alarmas |
| `routers/grupos.py` | preview y miembros por etiqueta, lista y días, zona, condición dinámica y conteos (los ids explícitos no se filtran: el operador los eligió) |
| `services/copilot/grupo_action.py` | preview de grupo del copiloto |
| `services/estrategias_service.py`, `services/estrategias_cycle_service.py` | `_GROUP_CLIENTS_SQL` (audiencia de la estrategia) |
| `services/agenda_sender.py` | audiencia por zona y por filtros (ids explícitos sin filtro) |
| `services/vendedor_app_service.py` | cartera del vendedor en Field |
| `services/conversacion_audiencia.py`, `data_access/conversaciones.py` | tipo de contacto `prospect` / `client` por `lifecycle` |

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `suplai-platform` | `feat/prospeccion-outbound-v2` | Este spec |
| 2 | `backend-supabase` | `feat/clientes-vs-prospectos` | Migración (pasos 1 a 3), trigger, vistas, BFF, consumidores |
| 3 | `agente-conversacional-multi_tenant` | `feat/clientes-vs-prospectos` | Router y altas con `lifecycle` y `origen_alta` |
| 4 | `product-management-app` | `feat/clientes-vs-prospectos` | Toggle, vista Prospectos, «Pasar a cliente» |
| 5 | `backend-supabase` | `feat/clientes-vs-prospectos-cleanup` | Paso 4 del backfill |

Se puede hacer en paralelo con 087 a 092. Las columnas de 089 y 091 aparecen vacías hasta que esos specs estén.

---

## Plan de prueba en CI/CD

- **Backend:** backfill sobre fixture con las tres grafías y con prospectos con pedido. Trigger: `confirmado` promueve, `cancelado` no. Un `client` no vuelve. BFF devuelve contadores. Métricas y grupos no traen prospectos.
- **Agente:** router con `lifecycle` (prospecto abierto, con handoff, cliente). Los tests de 084 siguen verdes.
- **Backoffice:** `tsc --noEmit`. El toggle cambia la query.
- Smoke de la migración en schema de test.

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`), agente local. Tenant `demo`.

1. Correr la migración en `demo`. Contar: 81 en Clientes (67 más los 14 promovidos) y 169 en Prospectos.
2. Abrir Clientes: por defecto se ven solo clientes; el toggle muestra los dos contadores.
3. Pasar a Prospectos: ver campaña, etapa, decisor y WhatsApp.
4. Con un prospecto de prueba, hacer un pedido por la tienda y confirmarlo. Recargar: pasó a Clientes con «Llegó por Suplai».
5. Abrir Métricas con «Solo importantes»: no aparecen prospectos.
6. Escribir desde el WhatsApp de un prospecto abierto: lo atiende el agente de prospección, como antes.
