# 087 — Salud del número y métricas por plantilla

**Estado:** Implementado en ramas, sin merge (ver «Implementación y desvíos»)  
**Fecha:** 2026-09-30  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `agente-conversacional-multi_tenant`, `product-management-app`  
**Ramas sugeridas:** `feat/salud-numero-metricas-plantillas`  
**Serie:** Prospección outbound v2 (087 a 092). Este es el primero porque protege el número antes de subir el volumen de envíos.  
**Relaciona:** [083](./083-campana-outbound-mapas.md) (resguardos de envío, % respuesta Meta vs Suplai), [070](./070-whatsapp-estado-webhook-agenda.md) (webhook de estados), [089](./089-validacion-whatsapp-previa.md) (validación previa del teléfono).

---

## Objetivo

Antes de mandar plantillas a comercios que no nos conocen, el operador tiene que ver **en Plantillas** cómo responde cada plantilla y **cuánto aguanta el número**. El envío outbound se frena solo cuando Meta avisa que el número o la plantilla están en riesgo, sin que nadie cargue la calidad a mano.

### Métricas de éxito

- En la lista de Plantillas, cada plantilla aprobada muestra enviados, % entregados, % leídos y % respuesta Suplai de los últimos 30 días, además de la calidad que le da Meta.
- El modal de Plantillas tiene una sección **Salud del número** con la calidad, el límite de mensajes, el estado y lo que pasó en los últimos 30 días.
- Un `phone_number_quality_update` o un `message_template_status_update = PAUSED` frena los envíos outbound en menos de un minuto, sin intervención humana.

---

## Qué expone Meta (investigación)

Fuente: documentación de Graph API v25 (septiembre 2026). Hay que verificarlo con una llamada real antes de implementar.

### Número (`GET /{phone_number_id}`)

| Campo | Qué es | Uso en Suplai |
|-------|--------|---------------|
| `quality_rating` | `GREEN`, `YELLOW`, `RED`, `NA`. Se calcula con los bloqueos y reportes de los últimos 7 días | Semáforo principal. Ya lo trae `fetch_phone_billing_health` |
| `status` | `CONNECTED`, `FLAGGED`, `RESTRICTED`, `PENDING`, `DISCONNECTED`, etc. | `FLAGGED` o `RESTRICTED` bloquean el outbound |
| `whatsapp_business_manager_messaging_limit` | `TIER_250`, `TIER_2K`, `TIER_10K`, `TIER_100K`, `TIER_UNLIMITED` | Cuántos usuarios únicos por día se pueden iniciar. **`messaging_limit_tier` está deprecado** |
| `throughput.level` | `STANDARD` o `HIGH` (mensajes por segundo) | Informativo |
| `health_status` | `can_send_message` y errores por entidad (número, WABA, app, business) | Ya lo usamos para el medio de pago |
| `name_status`, `verified_name` | Estado del display name | Informativo |

**El límite se calcula por business portfolio, no por número.** Todos los números del mismo portfolio comparten el cupo. Si Suplai es el Tech Provider y el tenant tiene su propio portfolio, el cupo es del tenant. Si en algún caso compartimos portfolio entre tenants, un tenant podría consumir el cupo de otro: hay que relevar qué tenants están en qué portfolio.

Para subir de 250 a 2.000, Meta pide verificar el negocio o haber entregado 2.000 mensajes fuera de la ventana de 24 h a usuarios únicos en 30 días **con plantillas de calidad alta**. De 2.000 para arriba, Meta sube el cupo solo si la calidad es alta y se usó al menos la mitad del cupo en los últimos 7 días. Por eso el outbound mal hecho no solo arriesga el número: también frena el crecimiento del cupo de la distribuidora.

### Plantilla

- `GET /{template_id}?fields=quality_score,status,category` devuelve `quality_score` (`GREEN`, `YELLOW`, `RED`, `UNKNOWN`).
- Una plantilla con feedback negativo pasa por `FLAGGED`, después a `PAUSED` (`FIRST_PAUSE` de 3 h, `SECOND_PAUSE` de 6 h) y, si sigue, a `DISABLED`.

### Métricas de plantilla (`GET /{waba_id}/template_analytics`)

- Los `metric_types` documentados son `SENT`, `DELIVERED`, `READ`, `CLICKED` y `COST`, con granularidad `DAILY`, hasta 10 plantillas por request y 90 días por rango.
- **`replied` no está documentado.** `sync_template_metrics` en `backend-supabase/services/meta_api_service.py` lo guarda igual en `meta_template_stats_daily`. En `del_corro` llega con valores (560 sobre 10.223 enviados, febrero a septiembre 2026). En `gonzales` llega en 0. No es una métrica garantizada, y Meta puede sacarla sin aviso.
- `CLICKED` solo cuenta botones URL y quick reply de plantillas marketing o utility.

### Webhooks de gestión (campos del WABA)

| Campo | Qué avisa | Hoy |
|-------|-----------|-----|
| `phone_number_quality_update` | Cambio de calidad o de límite del número (`event`: `FLAGGED`, `UNFLAGGED`, `DOWNGRADE`, `UPGRADE`; `current_limit`) | **No se procesa.** El webhook del agente solo lee `field = messages` (`app/services/meta_whatsapp_webhook_parse.py`) |
| `message_template_quality_update` | `previous_quality_score` → `new_quality_score` de una plantilla | No se procesa |
| `message_template_status_update` | `APPROVED`, `FLAGGED`, `PAUSED`, `DISABLED`, `REINSTATED`, etc., con `other_info.title` (`FIRST_PAUSE`, `SECOND_PAUSE`, `RATE_LIMITING_PAUSE`, `UNPAUSE`) | No se procesa |
| `business_capability_update` | Cambio de cupo (`max_daily_conversations_per_business`) | No se procesa |
| `account_update` | Restricciones o baneos del WABA | No se procesa |

### Señales que Meta **no** expone

- No hay tasa de bloqueos ni de reportes por número ni por plantilla. Solo el semáforo, que ya los incluye.
- Proxies propios, que ya llegan en el webhook de estados (`app/services/meta_whatsapp_status_webhook.py`):
  - `131026`: el destinatario no tiene WhatsApp o no puede recibir. Hoy marca `clients.whatsapp_estado = no_existente`.
  - `131049`: Meta frenó el marketing a ese usuario por el límite del ecosistema.
  - `131050`: el usuario frenó el marketing de esta empresa. Es casi un opt-out.
  - `131047`: fuera de la ventana de 24 h (no aplica a plantillas).
  - `131056`: demasiados mensajes al mismo usuario en poco tiempo.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Fuente de la calidad del número | Snapshot en BD (`core.whatsapp_phone_health`) actualizado por el webhook `phone_number_quality_update` más un poll cada 6 h | El webhook avisa rápido; el poll corrige si se pierde un webhook. El guard de envío lee la BD, no Graph en cada envío | Leer `metadata.outbound.quality` cargado a mano, como hoy; consultar Graph antes de cada HSM |
| Guard de envío | `outbound_guard` bloquea si `quality_rating` es `RED`, si `status` es `FLAGGED` o `RESTRICTED`, o si `can_send_message` es falso. Con `YELLOW` baja el tope diario a la mitad y avisa | 083 pausaba con cualquier calidad distinta de alta. Con `YELLOW` cortar todo frena la campaña por una señal temprana; seguir igual la empeora | Cortar con `YELLOW`; no hacer nada hasta `RED` |
| Guard por plantilla | Una variante con `quality_score = RED` o estado `PAUSED`, `FLAGGED` o `DISABLED` deja de recibir envíos nuevos. Si era la única, la campaña se pausa | Meta pausa la plantilla por feedback. Seguir mandando la otra variante no quema el número | Pausar toda la campaña ante cualquier cambio de una variante |
| % respuesta | El número principal es el **% respuesta Suplai** (inbound dentro de las 48 h del envío aceptado, mismo cálculo que 083). `replied` de Meta se muestra solo si viene distinto de null, con la etiqueta «Meta (no documentado)» | `replied` no está en la API documentada. Basar una decisión en un campo que puede desaparecer es frágil | Mostrar solo `replied` de Meta; esconderlo del todo aunque venga |
| Alcance de las métricas | Por plantilla y por tenant, en los últimos 30 días, sin partir por campaña | La lista de Plantillas no sabe de campañas. El corte por campaña ya existe en el panel de 083 | Repetir el A/B de 083 en Plantillas |
| Webhooks de gestión | Se suscriben en la app de Meta y los procesa el agente (mismo endpoint que `messages`), que despacha por `field` y resuelve el tenant por `entry.id` (WABA ID) | El webhook ya llega a ese servicio. Abrir un segundo endpoint obliga a otra configuración en Meta | Recibirlos en el backend con otra URL |
| Historial | Tabla de eventos append-only (`core.whatsapp_health_events`) | Para ver «bajó a amarillo el martes» hace falta la historia, no solo el último valor | Solo el snapshot |
| Errores de envío | Conteo de `131026`, `131049`, `131050` y `131056` de los últimos 7 días por número, desde los estados que ya se persisten | Es lo más parecido a la tasa de bloqueo que tenemos, y ya está en la BD | Pedir a Meta un dato que no expone |

---

## Alcance explícito

### Incluido (v1)

- Columnas de métricas en la lista de Plantillas (`components/meta-templates-modal.tsx`): enviados, % entregados, % leídos, % respuesta Suplai, % respuesta Meta (si existe) y pill de calidad de la plantilla.
- Sección **Salud del número** en el mismo modal: calidad, estado, límite de mensajes, cupo usado hoy (envíos outbound del día contra el límite), errores de envío de los últimos 7 días e historial de eventos de 30 días.
- Procesamiento de `phone_number_quality_update`, `message_template_quality_update`, `message_template_status_update` y `business_capability_update`.
- Poll cada 6 h del número y de `quality_score` de las plantillas aprobadas.
- `outbound_guard` alimentado por el snapshot, y guard por variante de plantilla.
- Aviso en el panel outbound del mapa (083) cuando la campaña se frena por salud.

### Fuera de alcance

- Notificar por WhatsApp o por mail al operador. Se ve en el backoffice; la notificación se evalúa después.
- Apelar una plantilla o un número desde Suplai.
- Rotar a otro número cuando el principal baja de calidad. Sigue la regla de 083: un solo número.
- Métricas de campañas de Meta Ads (inbound).

---

## Superficie

### Lista de Plantillas

Por fila (solo aprobadas; las otras muestran «—»):

| Columna | Cálculo | Fuente |
|---------|---------|--------|
| Enviados 30 d | Suma de `sent` | `meta_template_stats_daily` (Meta) |
| % entregados | `delivered / sent` | Meta |
| % leídos | `read / delivered` | Meta |
| % respuesta Suplai | Destinatarios con al menos un inbound dentro de las 48 h del envío aceptado / entregados | Suplai (`core.conversation_events` y envíos del tenant) |
| % respuesta Meta | `replied / delivered`, solo si `replied` no es null | Meta, con tooltip «Campo no documentado por Meta» |
| Calidad | Pill verde, amarilla, roja o gris con `quality_score`; y el estado si es `PAUSED` o `FLAGGED` | Meta |

Con menos de 30 entregados, los porcentajes van en gris con la etiqueta «muestra chica», igual que la regla de ganadora de 083.

### Sección «Salud del número»

- Semáforo grande con `quality_rating` y una línea que diga qué significa («Verde: podés enviar normal», «Amarillo: bajamos el tope de hoy a la mitad», «Rojo: frenamos los envíos a comercios nuevos»).
- Estado del número y `can_send_message`.
- Límite: «Hasta 2.000 conversaciones nuevas por día (compartido con todos los números de tu cuenta de Meta)». Barra con lo usado hoy.
- Errores de los últimos 7 días: sin WhatsApp (`131026`), frenados por Meta (`131049`), el comercio frenó el marketing (`131050`). Cada uno con conteo y % sobre envíos.
- Historial: lista de eventos de 30 días (fecha, qué cambió, de qué a qué).
- Medio de pago: lo que ya existe hoy.

---

## Requisitos funcionales

- `RF-1` El agente despacha los webhooks por `field`. `messages` sigue igual. Los cuatro campos de gestión se resuelven al tenant por WABA ID y se escriben en `core.whatsapp_health_events` y en el snapshot.
- `RF-2` Job cada 6 h: `GET /{phone_id}?fields=quality_rating,status,whatsapp_business_manager_messaging_limit,throughput,health_status` y `quality_score` de las plantillas aprobadas del tenant. Si el valor cambió, escribe evento con `source = poll`.
- `RF-3` `outbound_guard` lee el snapshot. Reglas: `RED`, `FLAGGED`, `RESTRICTED` o `can_send_message = false` bloquean; `YELLOW` baja el tope diario a la mitad; sin snapshot se comporta como hoy (lee `metadata.outbound.quality`, vacío = alta) y lo loguea.
- `RF-4` Guard por variante: una plantilla `RED`, `PAUSED`, `FLAGGED` o `DISABLED` no recibe envíos nuevos. Si ninguna variante queda disponible, la campaña pasa a `paused_health`.
- `RF-5` `GET /{schema}/plantillas-meta/metrics?days=30` devuelve las métricas de todas las plantillas en una sola respuesta.
- `RF-6` `GET /{schema}/plantillas-meta/phone-health` devuelve snapshot, cupo usado hoy, errores de 7 días e historial de 30 días. Reemplaza a `billing-health`, que queda como alias.
- `RF-7` El sync de `template_analytics` pide los `metric_types` explícitos y guarda `replied` como null (no 0) cuando no viene.

## Requisitos no funcionales

- `RNF-1` El guard no llama a Graph. Lee una fila.
- `RNF-2` Las métricas de la lista salen en una query agregada, no una por plantilla.
- `RNF-3` El sync de `template_analytics` agrupa de a 10 plantillas por request.
- `RNF-4` Pooler 6543, `statement_cache_size=0`.
- `RNF-5` Logs con `schema`, `phone_id` y el evento. Sin teléfonos de destinatarios.

---

## Criterios de aceptación

### `AC-1` El webhook frena el outbound

- **Given** una campaña outbound activa y el número en `GREEN`.
- **When** llega `phone_number_quality_update` con calidad `RED`.
- **Then** el siguiente lote de la cola no sale, la campaña muestra «Frenada por salud del número» y el evento queda en el historial.

### `AC-2` Amarillo baja el tope

- **Given** tope diario 50 y calidad `YELLOW`.
- **When** corre la cola.
- **Then** salen como máximo 25 primeros mensajes ese día.

### `AC-3` Plantilla pausada

- **Given** una campaña con variantes A y B.
- **When** llega `message_template_status_update` con `PAUSED` para A.
- **Then** los envíos nuevos van todos a B, y el panel lo dice. Si B tampoco está disponible, la campaña queda en `paused_health`.

### `AC-4` `replied` ausente

- **Given** que Meta no devuelve `replied` para una plantilla.
- **When** se abre la lista.
- **Then** la columna % respuesta Meta muestra «—» y la de % respuesta Suplai muestra su valor.

### `AC-5` Salud del número visible

- **Given** un tenant con número configurado.
- **When** se abre el modal de Plantillas.
- **Then** se ven calidad, estado, límite, cupo de hoy, errores de 7 días e historial.

---

## Casos borde

- `CB-1` Tenant sin WhatsApp configurado: la sección muestra «Número no configurado» y la lista no muestra métricas de Meta.
- `CB-2` Webhook de un WABA que no está en ningún tenant: se loguea y se descarta.
- `CB-3` Dos tenants en el mismo portfolio: el límite se muestra con la leyenda «compartido». El cupo usado hoy suma solo lo del tenant, y eso se aclara.
- `CB-4` `quality_rating = NA` (número nuevo sin historial): se trata como `GREEN` pero se muestra «Sin calificación todavía».
- `CB-5` Meta devuelve error en el poll: no se pisa el snapshot; se loguea y se reintenta en el próximo ciclo.

---

## Migración de base de datos

Tablas nuevas en `core` (el número y el WABA son del tenant, pero los webhooks llegan sin schema; se resuelven por WABA ID):

- `core.whatsapp_phone_health`: `schema_name`, `phone_id` (PK), `waba_id`, `quality_rating`, `status`, `messaging_limit`, `throughput_level`, `can_send_message`, `updated_at`, `source` (`webhook` | `poll`).
- `core.whatsapp_health_events`: `id`, `schema_name`, `phone_id`, `waba_id`, `field`, `template_id` null, `previous_value`, `new_value`, `payload` jsonb, `received_at`. Índice por `(schema_name, received_at desc)`.
- `core.whatsapp_template_health`: `schema_name`, `template_id` (PK), `template_name`, `language`, `quality_score`, `status`, `updated_at`.

En cada tenant, `meta_template_stats_daily.replied` pasa a admitir null (`ALTER COLUMN replied DROP NOT NULL` si aplica). No se borran los valores históricos.

**Backfill:** el primer poll llena el snapshot. No hay historia previa que migrar.

**Orden:** migración → backend (poll, endpoints, guard) → agente (despacho de webhooks) → backoffice.

**Rollback:** el guard vuelve a leer `metadata.outbound.quality` si no hay snapshot. Las tablas nuevas pueden quedar.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `suplai-platform` | `feat/prospeccion-outbound-v2` | Este spec |
| 2 | `backend-supabase` | `feat/salud-numero-metricas-plantillas` | Migración, poll, endpoints `metrics` y `phone-health`, guard |
| 3 | `agente-conversacional-multi_tenant` | `feat/salud-numero-metricas-plantillas` | Despacho de webhooks de gestión |
| 4 | `product-management-app` | `feat/salud-numero-metricas-plantillas` | Columnas en Plantillas y sección Salud del número |

**Tarea manual en Meta:** suscribir los campos de gestión en la configuración del webhook de la app (App Dashboard → WhatsApp → Configuration). Sin eso, solo funciona el poll.

**Suscripto hoy en demo:** `phone_number_quality_update` y `message_template_quality_update`. `message_template_status_update`, `business_capability_update` y `account_update` los cubre el poll de 6 h hasta que se suscriban; el agente ya los procesa si llegan.

---

## Implementación y desvíos

Migración `backend-supabase/sql/137_whatsapp_health.sql`. Servicio `services/whatsapp_health_service.py`, job `whatsapp_health` cada 6 h (minuto 40). Agente: `app/services/meta_whatsapp_health_webhook.py`. Backoffice: `components/meta-templates/whatsapp-health.tsx`.

| Tema | Spec original | Implementado | Por qué |
|------|---------------|--------------|---------|
| Payload de `phone_number_quality_update` | Traía la calidad | Solo trae `event` (`ONBOARDING`, `THROUGHPUT_UPGRADE`; los viejos `FLAGGED`, `DOWNGRADE`) y el límite (`max_daily_conversations_per_business`; `current_limit` se retiró en febrero de 2026) | Referencia de Meta actualizada al 2026-05-21. La calidad sale del poll. |
| Quién llama a Graph | Agente y backend | Solo el backend. El agente guarda el evento, aplica lo que dice el payload (límite; `FLAGGED` marca el estado) y pone `checked_at = NULL`. La próxima lectura (panel, publicar campaña) relee Graph | Una sola implementación del parser de Graph y sin llamada interna agente → backend con secreto por tenant |
| `metric_types` (RF-7) | Explícitos | Se omiten | Con `metric_types` explícitos Meta deja de mandar `replied`, que es justo el dato que queremos conservar donde exista (del_corro). `replied` se guarda null cuando no viene |
| WABA desconocido (CB-2) | Se descarta | Se guarda el evento con `schema_name = NULL`; el primer poll del tenant lo reasigna por `waba_id` | No perder el evento si el webhook llega antes que el primer poll |
| `paused_health` (RF-4) | Estado de campaña | No se agregó. Al publicar: A bloqueada → 409 `TEMPLATE_BLOCKED`; B bloqueada → sale todo por A con `variant_warning` | No hay proceso que drene la cola (`queued_for`); el único punto de envío es publicar. El CHECK de `campaign.status` queda igual |
| `billing-health` (RF-6) | Alias | Queda como estaba; `phone-health` incluye `payment_method_ok` | Lo usa `contexts/system-alerts-context.tsx` |
| Columnas en la lista | Tabla | Franja de métricas en cada tarjeta | La lista es una grilla de tarjetas |
| % respuesta Suplai | Inbound 48 h | Envíos de `envios_plantillas` + `campaign_prospect` aceptados, con un turno en `core.agent_turns` del mismo teléfono (últimos 10 dígitos) dentro de 48 h | `core.inbound_messages` no guarda el remitente |
| Errores de 7 días | — | El webhook de estados guarda en `core.whatsapp_health_events` (`field = delivery_error`) los fallos 131026, 131049, 131050 y 131056, en un savepoint | No abortar el resto del procesamiento de estados si falla el insert |

---

## Plan de prueba en CI/CD

- **Backend:** guard con snapshot `GREEN`, `YELLOW`, `RED`, `FLAGGED` y sin snapshot. Guard por variante con A pausada. Métricas en una query, con `replied` null. Parser del poll con fixtures de Graph.
- **Agente:** despacho por `field` con fixtures de los cuatro webhooks. `messages` no cambia (los tests existentes siguen verdes). WABA desconocido se descarta.
- **Backoffice:** `tsc --noEmit`. La lista renderiza «—» sin datos.
- Gap: no hay webhooks reales de Meta en CI. Se prueban con payloads guardados.

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`), agente local. Tenant `demo` con número y plantillas aprobadas con envíos.

1. Abrir Plantillas. Ver las columnas nuevas y la pill de calidad. Comparar enviados y entregados contra WhatsApp Manager.
2. Abrir Salud del número: calidad, límite y errores de 7 días coinciden con WhatsApp Manager.
3. Con `curl`, mandar al webhook local (`POST /webhook/v2`) un `phone_number_quality_update` con `event: FLAGGED` para el WABA de `demo`. Responde `echo: meta_management_ack`. En `core.whatsapp_phone_health` el estado queda `FLAGGED` con `checked_at` null, y el historial muestra el evento. Al abrir Salud del número se relee Graph: manda lo que diga Meta (con un curl simulado vuelve al estado real).
4. Mandar `message_template_quality_update` con `new_quality_score: RED` para la variante B. Publicar sale todo por A y la respuesta trae `variant_warning`.
5. «Actualizar» en Salud del número relee Graph y, si Meta dice verde, el bloqueo se levanta.

OK: los pasos 3 a 5 se ven en el backoffice sin mirar logs.
