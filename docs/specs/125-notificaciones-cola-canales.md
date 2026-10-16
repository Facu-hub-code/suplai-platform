# 125 — Notificaciones: cola, reintentos y canal

**Estado:** Borrador. El diseño de cola está aprobado. El destinatario es un canal libre y cada destino elige sus tipos de aviso. Si ese destino es un vendedor, los pedidos pueden limitarse a su cartera.  
**Fecha:** 2026-10-16  
**Repos:** `backend-supabase` (cola, worker, envíos, tools), `agente-conversacional-multi_tenant` (deja de hablar con Meta para estos avisos), `suplai-sales-claude-plugin` (skill y manual), `suplai-platform` (este spec).  
**Rama sugerida:** `feat/notificaciones-cola`  
**Relaciona:** [072](./072-notificacion-pedidos-cartera-vendedor.md), [110](./110-mcp-crud-vendedores-y-notificaciones.md), backend [003](../../../backend-supabase/docs/specs/003-notificaciones-eventos-whatsapp.md), [021](../../../backend-supabase/docs/specs/021-order-confirmation-email-brevo-pdf.md), [115](../../../backend-supabase/docs/specs/115-order-confirmed-ia-ticket-fallback.md), [130](../../../backend-supabase/docs/specs/130-notificacion-pedidos-cartera-vendedor.md), agente [047](../../../agente-conversacional-multi_tenant/docs/specs/047-notificacion-confirmacion-pedido-vendedores.md), [065](../../../agente-conversacional-multi_tenant/docs/specs/065-seller-notify-meta-cutover-fallback.md).

---

## Objetivo

Los avisos de la distribuidora salen por un solo emisor, el backend, con reintento y un registro de por qué canal y a qué destino llegó cada uno. Desde el conector se dan de alta mails y teléfonos libres. Cada uno elige qué tipos de aviso recibe, y se puede apagar sin tocar a los demás.

Hoy hay tres avisos y ninguno tiene cola:

- **Pedido confirmado.** El agente manda WhatsApp a los vendedores y, en paralelo, pega al webhook. El backend manda el PDF por Brevo y, si el origen es tienda o Field, también el WhatsApp. Un fallo de Meta se anota en el log y se termina. El texto suelto de respaldo sigue siendo WhatsApp, así que un corte por falta de pago no llega a ningún lado útil.
- **Asistencia humana.** Al crear un `ia_ticket` que no es error de sistema, el observer manda la plantilla al vendedor en el mismo request. Si Meta falla, queda un `failed` en el log.
- **Error de Meta por falta de pago.** El tag `[META_BUSINESS_PAYMENT_ERROR]` dispara la plantilla `suplai_error_sistema_vendedor_v1` por el mismo WhatsApp que acaba de rechazar el envío. No hay mail.

El canal viejo `notification_event_config` + `profiles.is_whatsapp_subscribed` no tiene configs activas de `order_confirmed` (auditoría del 12 de agosto de 2026). Esta entrega no lo revive.

### Criterios de aceptación

- Confirmar un pedido, desde el agente, la tienda o Field, crea un solo trabajo `order_confirmed`. La clave es el tenant más el id del pedido. Un segundo aviso del mismo pedido no crea otro trabajo.
- El worker avisa a cada suscripción prendida cuyo `eventos` incluye ese tipo. Un teléfono puede recibir los tres tipos y otro solo pedidos. Un mail puede recibir solo pedidos y otro solo errores de sistema. No hace falta que el teléfono sea de un vendedor ni que el mail sea de un usuario.
- Si el destino coincide con un vendedor y el alcance de pedidos es `cartera`, ese destino recibe un pedido solo cuando el cliente está en su cartera. Asistencia y error de sistema no se filtran por cartera. Un destino que no es vendedor, o un vendedor con alcance `all`, recibe todos los pedidos del tipo al que está suscripto.
- El PDF del pedido sigue yendo al mail del cliente cuando existe. Los mails suscriptos a `order_confirmed` van en el mismo envío. Un mail suscripto solo a `error_sistema` no recibe ese PDF.
- Cada destino queda en `notification_deliveries` con canal (`whatsapp` o `email`), destino (teléfono o mail), estado e intento.
- Un timeout, un HTTP 429 o un 5xx se reintenta hasta cinco envíos en total. El primero es inmediato; los siguientes esperan 30 s, 2 min, 10 min y 30 min. El quinto fallo deja esa fila `dead`. Un teléfono inválido, una plantilla no aprobada o un `131042` no se reintenta por WhatsApp.
- Un `131042` (o el ticket `[META_BUSINESS_PAYMENT_ERROR]`) no llama a Graph. El aviso llega por mail a las direcciones suscriptas a `error_sistema`. Un WhatsApp suscripto a ese tipo queda `skipped` / `meta_billing`. El pedido sigue confirmado. No hay texto suelto de respaldo.
- Apagar una suscripción (`enabled: false`) la conserva y deja de enviarle. El resto de los destinos no cambia. Volver a prenderla no exige cargarla de nuevo.
- `ver_notificaciones`, `previsualizar_notificaciones` y `ver_envios_notificacion` operan sobre el tenant del token. Confirmar guarda la suscripción y no envía ningún mensaje.
- La inyección al ERP no entra en la cola y sigue corriendo en el pipeline de confirmación.

---

## Cómo está hoy

**Pedido.** `reglas_negocio.order_notification` guarda si el WhatsApp está prendido, la estrategia y los vendedores (`scope`, `weight`). El mail usa `email_recipients` cuando la clave existe; si no existe, la copia son todos los usuarios del tenant. El agente envía en `send_order_confirmation_notification` y además llama a `POST /{schema}/notifications/events`. Tienda y Field llaman a `run_order_confirmed_full_effects`. El evento `order_notification_sent` en `core.conversation_events` alimenta round-robin y weighted, y solo se escribe si hay conversación. El MCP de la spec 110 edita ese JSON con vendedores y con mails que tienen que ser de un usuario del tenant.

**Asistencia y error de sistema.** `on_ia_ticket_created` lee `custom_ia_tickets_notification` o `system_errors_notification` y llama a `send_template_message` en el request que creó el ticket. El único código de `SYSTEM_ERROR_TYPES` es `META_BUSINESS_PAYMENT_ERROR`. El ticket lo abre el agente, desde el dispatcher de pedidos o desde el webhook de estados de WhatsApp, con deduplicación en `create_meta_payment_error_ticket_if_needed`.

**Proceso.** No hay outbox. El webhook responde 202 y el envío corre en una `BackgroundTasks` de ese proceso. Si el proceso muere a mitad, el aviso no se retoma.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Emisor | Solo el backend. Agente, tienda y Field publican el evento | El reintento y el registro quedan en un lugar. El doble camino (agente manda WhatsApp, webhook manda mail) es el que duplica y el que pierde fallos | Dejar al agente mandando WhatsApp y limitar la cola al mail |
| Cola | Outbox en Postgres. El worker del backend toma con `FOR UPDATE SKIP LOCKED` | El estado sobrevive a un deploy. Varias réplicas no se pisan. El volumen no justifica otro sistema, y el proceso ya corre un scheduler | Redis, una cola de Railway o Temporal |
| Dónde corre el worker | `AsyncIOScheduler` del backend, cada 10 segundos, batch de 10. Respeta `SCHEDULER_ENABLED` | Mismo proceso que agenda y ERP. No suma un servicio ni otro pool | Un worker aparte con su propio pool, que comería conexiones del límite de 60 |
| Conexión | El claim y el update usan el pool de la app. La conexión se suelta antes de llamar a Meta o a Brevo | Un HTTP de Graph no puede retener una sesión del pooler | Mandar el mensaje con la transacción abierta |
| Quién recibe | Una suscripción por destino: canal, mail o teléfono, prendido o no, y la lista de tipos | El mismo mail puede enterarse solo de pedidos y otro solo de errores. El mismo esquema vale para un teléfono. Apagar uno no toca al resto | Una política por evento con una lista común, donde todos los de ese canal reciben lo mismo |
| Canal libre | El destino se guarda igual si no es de nadie del sistema. El teléfono queda en dígitos y el mail en minúsculas. No se exige un usuario ni un vendedor | Hace falta avisar a un número suelto o a un inbox que no es usuario. Si el número es el de un cliente, entra igual | Exigir `vendedor_id` para poder guardar, o exigir que el mail sea de un usuario del tenant |
| Vínculo con vendedor | Si el teléfono coincide con un solo `vendedores.telefono`, o el mail con un solo `vendedores.email`, la suscripción guarda ese `vendedor_id`. Si no coincide con ninguno, queda libre. Si coincide con más de uno, no se adivina | La cartera es del vendedor, no del número. El vínculo se resuelve al confirmar y se vuelve a mirar al enviar, por si cambió el teléfono del vendedor | Pedir el `vendedor_id` a mano, o atar todo destino a un vendedor |
| Cartera | Solo en pedidos, y solo si hay `vendedor_id` y `order_scope = cartera`. El cliente del pedido tiene que estar en la cartera de ese vendedor, con el mismo criterio que la spec 072. Si no está, no se crea delivery: no es un fallo | Es la funcionalidad que ya tienen los vendedores. Asistencia y error de sistema no son "pedidos de su cartera" | Aplicar cartera a los tres tipos, o dejar que un `scope = cartera` pase a ver todos los pedidos |
| Alcance `all` | Un vendedor con `order_scope = all`, y cualquier destino sin vendedor, recibe todos los pedidos del tipo al que está suscripto | "Solo su cartera" es opt-in. El número libre no tiene cartera que consultar | Tratar todo teléfono de vendedor como cartera aunque el operador haya pedido todos los pedidos |
| Qué tipos hay | `order_confirmed`, `asistencia_humana`, `error_sistema`. La lista de un destino es un subconjunto. Vacía y prendida no se guarda | Son los tres avisos que existen hoy. "Todo" es marcar los tres. "Solo órdenes" es marcar `order_confirmed` | Tipos nuevos, o un tipo genérico `sistema` que mezcle asistencia y error |
| A quién le llega un aviso | A cada suscripción prendida que incluye ese tipo, y que pasa el filtro de cartera si corresponde. No se elige uno entre varios | Un número puede recibir todo y otro solo pedidos, los dos a la vez | Round-robin, weighted o random. Eso elige un solo destino y no es lo que se pidió |
| Fuente de verdad | `notification_subscriptions`. El worker no lee `reglas_negocio` para elegir destinatarios | Si el JSON y la tabla se escriben los dos, el último gana y un número libre se pierde cuando alguien guarda la pantalla vieja | Espejar cada PATCH del backoffice hacia la tabla |
| Pantalla vieja y tools de la spec 110 | Siguen guardando el JSON. No cambian suscripciones | Esa pantalla y esas tools solo saben de vendedores y de mails de usuarios. Pisaban la lista libre | Hacer que el confirmar viejo reescriba los teléfonos de los vendedores y borre el resto |
| Pedido, mail | Un solo llamado a Brevo. El cliente va en Para si tiene mail. Cada mail suscripto a `order_confirmed` va en copia, o en Para si el cliente no tiene. Una fila de delivery por dirección | El PDF del cliente no es una suscripción. Los avisos sí. Un solo PDF, y queda registrado a qué mail salió | Un mail distinto por suscriptor, o exigir que el cliente esté suscripto para recibir su PDF |
| `131042` | No se llama a Graph para `error_sistema`. En pedido y asistencia, ese código marca el WhatsApp `skipped` (`meta_billing`), no hay texto suelto, y se abre el ticket si no hay uno reciente | La plantilla sale por la misma cuenta que acaba de rechazar el pago. El texto de respaldo también es WhatsApp | Reintentar la plantilla, o caer al texto como hace hoy el agente |
| Mail del error de sistema | Lo reciben las direcciones suscriptas a `error_sistema`. El backfill se las agrega a los usuarios del tenant, prendido | Si nace sin nadie, el corte de pago no avisa hasta que alguien configure el MCP. Después se puede sacar un mail o apagarlo | Mandarlo solo a vendedores, o dejar el mail apagado el día del deploy |
| WhatsApp del error de sistema | Si un teléfono está suscripto a `error_sistema` y el código es de facturación, la fila queda `skipped` / `meta_billing` y no se llama a Graph | El operador ve por qué ese número no se enteró. El mail suscripto a ese tipo sí sale | Intentar la plantilla `suplai_error_sistema_vendedor_v1` igual |
| Mail de asistencia | Solo si ese mail tiene `asistencia_humana` en su lista. El backfill no suscribe a nadie | No hay un fallback implícito. Quien quiera el mail lo agrega, con ese tipo y no con otros | Copiar a todo el staff, o mandar mail automático cuando falla el WhatsApp |
| Reintento | Cinco envíos como máximo. El primero es inmediato. Después se espera 30 s, 2 min, 10 min y 30 min. Solo timeout, 429 y 5xx. El quinto fallo deja la fila `dead` | Un 4xx de negocio no se arregla esperando. El espaciado evita martillar Graph. Cinco esperas habrían sido un sexto envío | Reintento inmediato en el mismo request, o reintentar también el `131042` |
| A quién se reintenta | Solo las filas que no están `sent`. Una dirección que ya salió no se vuelve a mandar | El segundo intento de un batch no puede duplicar el WhatsApp del que sí llegó | Reenviar el trabajo entero |
| Trabajos trabados | Si `processing` tiene `locked_at` de más de 5 minutos, vuelve a `pending` | Un deploy a mitad del HTTP no puede dejar el aviso colgado | Un lock sin vencimiento |
| Idempotencia | `(tenant_id, idempotency_key)` única. Claves: `order_confirmed:{order_id}`, `asistencia_humana:{ticket_id}`, `error_sistema:{ticket_id}` | Agente y tienda pueden publicar el mismo pedido. El ticket de pago ya se deduplica, y el trabajo también | Un trabajo nuevo por cada llamada |
| Webhook viejo | `POST /{schema}/notifications/events` con `order_confirmed` encola con esa clave y sigue disparando el ERP y el ticket de fallback del pedido. No llama a `process_notification_event` | Hay que conservar el ERP de los callers actuales. El canal de perfiles suscriptos está vacío y un retry por ahí duplicaría efectos | Borrar el endpoint en esta entrega, o seguir usándolo como envío |
| ERP | Sigue en el pipeline de confirmación, fuera de la cola | No es un aviso. Meterlo en la cola atrasaría la inyección detrás de un mail | Encolar el ERP como un canal más |
| Mensaje al cliente en el chat | Sigue en el agente | Es la respuesta de la tool, no un aviso a la distribuidora | Pasarlo por la cola |
| Capas | Tool MCP → servicio de dominio → `data_access`. El worker llama a los envíos de plantilla y de Brevo que ya existen | La tool no escribe SQL ni arma el body de Meta. El router no es la fachada del MCP | SQL en `mcp_server/`, o que la tool llame al router |
| MCP no envía | `confirmar` guarda la suscripción | Un mensaje de prueba le escribiría a ese teléfono o a ese inbox | Un botón de envío de prueba |
| Auditoría del preview | Canal, cantidad de tipos, si queda prendido, si es un alta o un apagado. Sin el teléfono y sin el mail | El destino se ve en `ver_notificaciones` y en las deliveries. La auditoría no es el inbox | Guardar el destino en `mcp_auditoria` |
| Lectura | `ver_notificaciones` y `ver_envios_notificacion` sí muestran el destino | Sin el mail o el teléfono no se puede revisar la suscripción ni el envío | Ocultarlos también en la lectura |
| Apagar | `enabled: false` deja la fila y la lista de tipos. No envía. `quitar: true` borra esa suscripción y ninguna otra | "Enterarse y después apagarlo" no tiene que obligar a cargar el número de nuevo, ni a rearmar el resto | Borrar la fila para apagar, o apagar el canal entero |

---

## Alcance

### Incluido

- Tablas `notification_subscriptions`, `notification_jobs` y `notification_deliveries`, con backfill desde el JSON vigente.
- Worker en el scheduler del backend, reintentos y el barrido de trabajos `processing` vencidos.
- Publicar `order_confirmed` desde el agente, la tienda y Field, con una sola clave por pedido.
- Publicar `asistencia_humana` y `error_sistema` desde el observer, en lugar de enviar en el request.
- Suscripciones libres: varios mails y varios teléfonos, cada uno con su subconjunto de tipos, con alta, edición, apagado y baja desde el MCP.
- Alcance `all` o `cartera` en los pedidos, cuando el destino es un vendedor. El backfill copia el `scope` que cada vendedor tiene hoy.
- Mail del error de sistema a las direcciones suscriptas a ese tipo. El backfill se lo agrega a los usuarios del tenant. WhatsApp de ese tipo no llama a Graph cuando el código es de facturación.
- Tools `ver_notificaciones`, `previsualizar_notificaciones` y `ver_envios_notificacion`, con los scopes `notificaciones:leer` y `notificaciones:escribir`.
- El agente deja de llamar a `send_order_confirmation_notification`.
- Tests de encolado, idempotencia, suscripciones por tipo, ruteo de `131042`, reintento y de que confirmar no envía.
- Texto del plugin para las tools nuevas.

### Fuera de alcance

- Inyección al ERP, y el mensaje de éxito que el agente le escribe al cliente en el chat.
- Avisos de estrategias (`notify_pool_created` y el resto). Esos tickets no pasan a ser asistencia humana: el observer solo encola los que hoy ya notificaría.
- Pantalla nueva en el backoffice, y que la pantalla actual escriba suscripciones. Sigue editando el JSON. El worker no la lee.
- Que `ver_notificaciones_pedido` y `previsualizar_notificaciones_pedido` escriban suscripciones. Siguen el contrato de la spec 110 sobre el JSON.
- Round-robin, weighted y random. Esos modos eligen un solo destino. La cartera no entra en esa lista: sigue, por suscripción, para los pedidos de un vendedor.
- Retirar `notification_event_config` y el flag `is_whatsapp_subscribed`. Esta entrega deja de llamarlos.
- Un envío de prueba desde el conector.
- Apagar `ORDER_CONFIRMATION_EMAIL_ENABLED`. Si el flag de proceso está apagado, el worker no manda el PDF del pedido y esas filas quedan `skipped` con `email_proceso_apagado`. No afecta el mail de asistencia ni el de error de sistema. La suscripción igual se puede guardar.

---

## Modelo

### `public.notification_subscriptions`

Una fila por tenant, canal y destino. Única en `(tenant_id, channel, destination)`.

| Columna | Uso |
|---|---|
| `channel` | `whatsapp` o `email` |
| `destination` | Teléfono solo dígitos, o mail en minúsculas |
| `enabled` | Si es false, el worker no le envía ningún tipo |
| `event_types` | Subconjunto de `order_confirmed`, `asistencia_humana`, `error_sistema`. Sin duplicados |
| `vendedor_id` | Null si el destino no es un vendedor. Si no, el id en `{schema}.vendedores`. No hay FK: esa tabla vive en el schema del tenant |
| `order_scope` | `all` o `cartera`. Null equivale a `all`. Solo filtra `order_confirmed` |

No hay `cliente_id` ni `profile_id`. No hay estrategia.

Backfill, por distribuidora activa. Si el mismo destino aparece en más de un JSON, se unen los tipos en una sola fila. El `order_scope` de un teléfono de vendedor sale de su suscriptor de pedidos: si no tiene `scope`, queda `all`.

- Pedido, WhatsApp prendido: el teléfono de cada vendedor suscripto, tipo `order_confirmed`, con su `vendedor_id` y su `scope`. Sin teléfono, no se crea fila. La estrategia (`all`, `round_robin`, `weighted`, `random`) no se copia.
- Pedido, mail: si existe `email_recipients`, esas direcciones con `order_confirmed`, prendidas salvo que `email_enabled` sea false. Si la clave no existe, cada mail de usuario del tenant (`fetch_staff_emails`) con `order_confirmed`. Lista explícita vacía: nadie.
- Asistencia, WhatsApp prendido: el teléfono de cada vendedor de `custom_ia_tickets_notification`, tipo `asistencia_humana`. Mail: nadie.
- Error de sistema, mail: cada mail de usuario del tenant suma `error_sistema`, prendido. WhatsApp: el teléfono de cada vendedor de `system_errors_notification` suma el tipo, pero un código de facturación no llama a Graph.

Un tenant sin ninguna de esas claves queda sin suscripciones de pedido. El mail de error de sistema igual se backfillea si hay usuarios con mail.

### `public.notification_jobs`

Única en `(tenant_id, idempotency_key)`.

Estados: `pending`, `processing`, `done`, `dead`.

`attempts`, `max_attempts` (5), `available_at`, `locked_at`, `last_error`, `payload`. El payload trae el id de negocio (`order_id` o `ticket_id`), el `source` del pedido y, en el error de sistema, el `error_code`. El destino se lee de la suscripción al enviar, no se copia al job.

Insertar la misma clave es un no-op y devuelve el trabajo que ya existe.

### `public.notification_deliveries`

Una fila por canal y destino de ese trabajo. Estados: `sent`, `failed`, `skipped`, `dead`.

Guarda `destination` (teléfono en dígitos o mail), `destination_role` (`cliente`, `aviso`), `attempt`, `provider_code`, `error_code` (`meta_billing`, `timeout`, `rate_limited`, `provider_5xx`, `invalid_phone`, `template_rejected`, `no_recipients`, `email_proceso_apagado`, `suscripcion_apagada`) y `sent_at`.

El PDF al cliente usa rol `cliente`. Todo lo que sale por suscripción usa rol `aviso`.

---

## Flujo

```text
confirmación de pedido / alta de ia_ticket
        │
        ▼
  notification_jobs          clave única por pedido o ticket
        │
        ▼
  worker cada 10 s           SKIP LOCKED, batch 10, suelta la conexión
        │
        ├─ suscripciones prendidas que incluyen ese tipo
        ├─ pedido con alcance cartera → solo si el cliente es de ese vendedor
        ├─ 131042 o error de sistema por facturación → no llama a Graph
        ▼
  notification_deliveries    una fila por destino
        │
        ├─ WhatsApp (plantillas que ya existen)
        └─ mail (Brevo: PDF del pedido, o texto del error / la asistencia)
```

**Pedido.** Quien confirma inserta el trabajo y después corre el ERP. El worker toma las suscripciones prendidas a `order_confirmed`. Si `order_scope` es `cartera`, vuelve a buscar un vendedor por ese teléfono o ese mail. Con uno solo, envía solo cuando el cliente del pedido está en su cartera (`vendedores_clientes`, el mismo criterio que la spec 072). Sin coincidencia, o con más de una, no crea delivery. Con `order_scope` `all` o null, envía el pedido. No usa round-robin ni escribe `order_notification_sent`. El mail del PDF sigue la misma regla: un mail de vendedor con alcance `cartera` entra en copia solo si el cliente es de su cartera. El mail del cliente, si existe, va en Para igual. Si Graph responde `131042`, esa fila queda `skipped` / `meta_billing`, no hay texto suelto, y se crea el ticket de pago si el dedupe lo permite. Ese ticket encola `error_sistema`.

**Asistencia.** El observer, si la config vieja hubiera notificado o si ya hay alguna suscripción a `asistencia_humana`, inserta `asistencia_humana:{ticket_id}` y vuelve. El worker manda la plantilla `suplai_ticket_asistencia_vendedor_v1` a los teléfonos suscriptos, y un mail de texto a los mails suscriptos a ese tipo. Un ticket que hoy no notificaría y que no tiene suscripciones no inserta job.

**Error de sistema.** El observer inserta `error_sistema:{ticket_id}`. El worker no llama a `send_template_message`. Cada teléfono suscripto a ese tipo queda `skipped` / `meta_billing`. Cada mail suscripto recibe un correo con el id del ticket, el código y el detalle, en texto plano, sin PDF.

**Loop.** El mail de error de sistema no llama a Graph, así que no puede volver a abrir el ticket. El worker, al ver `131042` en un WhatsApp de pedido o de asistencia, usa el mismo dedupe que ya tiene el alta del ticket.

**Reintento.** Una fila `failed` con error transitorio sube `attempt` y pone el trabajo en `pending`. La espera es 30 s, 2 min, 10 min y 30 min según el fallo número 1 a 4. El quinto fallo deja la fila `dead` y no programa otro envío. Si no queda ninguna fila reintentable, el trabajo queda `done` (hubo algún `sent` o solo `skipped`) o `dead` (todo terminó muerto).

**Trabajo vencido.** Un `processing` con `locked_at` anterior a 5 minutos vuelve a `pending` sin sumar intento. El envío que sí llegó ya tiene fila `sent` y no se repite.

---

## Tools

El tenant no es un argumento. Un preview dura 30 minutos. `confirmar` sigue siendo la única tool que escribe. Los scopes son los que ya existen: `notificaciones:leer` y `notificaciones:escribir`.

`ver_notificaciones_pedido` y `previsualizar_notificaciones_pedido` siguen guardando el JSON de la spec 110. No leen ni escriben `notification_subscriptions`. La guía del conector lo dice así: si preguntan qué mails o teléfonos reciben avisos, la única lectura es `ver_notificaciones`. La tool vieja puede responder que no hay lista de mails aunque esa tabla tenga filas.

Cada suscripción de WhatsApp puede guardar una plantilla por tipo, en `plantillas` (`order_confirmed` y `asistencia_humana`), con el id de `public.meta_plantillas` de ese tenant. `plantilla_pedido` y `plantilla_asistencia` en el preview. Si no hay, el pedido usa la plantilla que ya tenía el tenant y la asistencia usa la plantilla fija. El mail no lleva plantilla de Meta. Un string vacío saca esa clave.

### `ver_notificaciones`

Scope `notificaciones:leer`. Sin argumentos.

Lista las suscripciones del tenant. Cada una trae canal, destino, si está prendida y sus tipos. Si está vinculada a un vendedor, trae su id, su nombre y el alcance de pedidos (`all` o `cartera`). Un teléfono se muestra en dígitos. Incluye `mail_proceso_habilitado`, que solo afecta el PDF del pedido. Si no hay filas, la lista va vacía.

### `previsualizar_notificaciones`

Scope `notificaciones:escribir`.

Argumentos: `canal` (`whatsapp` o `email`), `destino`, `enabled`, `eventos`, `alcance` (`all` o `cartera`, default `all`), `plantilla_pedido`, `plantilla_asistencia` y `quitar` (default false).

`eventos` es una lista con uno o más de `order_confirmed`, `asistencia_humana`, `error_sistema`. Con `enabled: true` hace falta al menos un tipo. Con `enabled: false` se puede mandar la lista que queda guardada, o vacía si solo se apaga.

No se exige que el destino exista de antemano. Un teléfono queda en dígitos; si no quedan entre 8 y 15, no hay `preview_id`. Un mail tiene que tener forma de dirección; se guarda en minúsculas. Después de normalizar, se busca en `vendedores`: el teléfono contra `telefono`, el mail contra `email`. Una sola coincidencia guarda ese `vendedor_id` y el preview dice el nombre. Ninguna coincidencia deja `vendedor_id` null. Más de una no se adivina. `alcance = cartera` sin un vendedor único no genera `preview_id`. `alcance` solo se guarda si `eventos` incluye `order_confirmed`; si no, queda null. El mismo destino y canal actualiza la fila que ya existe. Otro destino del mismo canal no se toca.

`quitar: true` borra solo esa suscripción. El preview lo dice.

El preview muestra el destino, los tipos, el vendedor cuando hay uno, el alcance de pedidos y si va a quedar prendido, y dice que confirmar no envía.

`confirmar` hace el upsert o el delete. No escribe `reglas_negocio`.

Tipo de preview nuevo: `notificaciones`. Entra en `mcp_accion_previews_tipo_check` junto con todos los tipos que ya acepta `sql/168`.

### `ver_envios_notificacion`

Scope `notificaciones:leer`.

Filtros opcionales: `evento`, `estado`, `limite` (20 por defecto, 100 como máximo). Orden `created_at` descendente. Cada fila trae evento, canal, destino, rol, estado, intento, `error_code` y `sent_at`. Si hay más, `hay_mas: true`.

---

## Orden de implementación

Este documento puede mergearse cuando se quiera. El agente publica en un endpoint que tiene que existir. El plugin nombra tools que tienen que existir.

| Repo | Rama sugerida | Qué entra | Orden de merge |
|---|---|---|---|
| `suplai-platform` | `feat/notificaciones-cola` | Este spec | Cuando se quiera |
| `backend-supabase` | `feat/notificaciones-cola` | Migración, dominio, worker, productores, tools, tests | Primero |
| `agente-conversacional-multi_tenant` | `feat/notificaciones-cola` (desde `origin/master`) | Deja de enviar el WhatsApp del pedido y publica el trabajo | Después del backend |
| `suplai-sales-claude-plugin` | `feat/notificaciones-cola` | Skill y una línea en el manual | Después del backend |

Dentro del PR de backend:

1. Migración: las tres tablas, el backfill y el check de previews. El número libre siguiente a `sql/168`.
2. `data_access` de jobs, deliveries y suscripciones. El servicio encola, elige destinos por tipo y guarda suscripciones. El worker solo orquesta.
3. Enganchar el scheduler y el barrido de `processing` vencido.
4. Cambiar el webhook, `run_order_confirmed_full_effects` y `on_ia_ticket_created` para que publiquen en vez de enviar. El ERP queda en el pipeline.
5. Tools nuevas, scopes ya existentes, handler de `confirmar`, superficie y textos. Las tools de la spec 110 no se enganchan a la tabla.
6. Tests.

El PR del agente sale cuando el endpoint de alta de trabajos está en el backend mergeado, o detrás de un flag que en local apunta al backend de la rama. Hasta ese merge, el agente en `master` sigue enviando como hoy: por eso el backend se mergea primero y el corte del agente es el paso que apaga el doble envío. El endpoint nuevo es idempotente, así que un agente viejo que todavía envía por su cuenta y además pega al webhook no crea un segundo trabajo; sí puede seguir mandando el WhatsApp directo hasta que se mergee el PR del agente. Esa ventana hay que mantenerla corta.

---

## Migración de base de datos

Tablas nuevas en `public`:

- `notification_subscriptions`
- `notification_jobs`
- `notification_deliveries`

`notification_subscriptions.plantillas` (jsonb) guarda el id de plantilla de WhatsApp por tipo de aviso. Entra en la migración siguiente a la de las tres tablas.

No se altera `{tenant}.clients`. No se tocan `v_cartera` ni `v_prospectos`.

Backfill en la misma migración, solo `distribuidoras.activa = true`, con las reglas de la sección Modelo. El JSON de `reglas_negocio` no se modifica.

También se agrega el tipo `notificaciones` al check de `mcp_accion_previews`, copiando la lista vigente (la de `sql/168` al momento de implementar; si ya existe un número posterior, se parte de ese).

Rollback: dropear las tres tablas en orden `notification_deliveries`, `notification_jobs`, `notification_subscriptions`. Eso borra el historial de envíos y las suscripciones de esta entrega. Hay que revertir el código en el mismo rollback. El JSON no se tocó, así que el comportamiento viejo vuelve cuando vuelve el código viejo.

Rollback del check: restaurar la lista de tipos anterior. Si quedaron previews `notificaciones`, consumirlos o borrarlos antes, porque el check viejo no los acepta.

---

## Plan de prueba en CI/CD

Pytest en `backend-supabase`, junto a `tests/test_order_notification_seller_dispatcher.py`, `tests/test_ticket_notification_observer.py`, `tests/test_mcp_vendedores_notificaciones.py` y `tests/test_mcp_superficie.py`. En el agente, los tests de `send_order_confirmation_notification` pasan a afirmar que no se llama a Graph y que se publica un trabajo (cliente HTTP mockeado).

La migración se aplica en el camino de tests que ya corre SQL de `sql/`, o el test de repositorio arma las tablas contra el schema de prueba. No hace falta un smoke manual de DDL fuera de eso.

- Dos altas con la misma clave dejan un solo job.
- Un pedido de tienda encola y no llama a `send_seller_order_notification` ni a `send_order_confirmation_emails` en el request. El ERP se sigue invocando.
- Con un teléfono suscripto a los tres tipos y otro solo a `order_confirmed`, el worker del pedido les escribe a los dos. El de asistencia le escribe solo al primero. Esos dos pueden no existir en `vendedores` ni en `clients`.
- Un vendedor con `order_scope = cartera` recibe el pedido si el cliente está en su `vendedores_clientes`, y no lo recibe si está en la de otro. No se crea delivery en el segundo caso. El mismo vendedor, suscripto a `asistencia_humana`, recibe ese aviso aunque el cliente no sea de su cartera.
- Un destino con `order_scope = all` recibe el pedido aunque el cliente no esté en ninguna cartera. `alcance = cartera` sobre un teléfono que no es de un vendedor no guarda preview.
- Un mail suscripto solo a `order_confirmed` entra en el PDF. Otro suscripto solo a `error_sistema` no entra en ese PDF y sí recibe el mail del error. Un tercer mail apagado no recibe nada. Los tres pueden no ser usuarios del tenant.
- El PDF sigue yendo al mail del cliente, con rol `cliente`, aunque esa dirección no tenga suscripción. Sin mail de cliente y sin suscriptos a `order_confirmed`, no se inventa un destinatario.
- `ORDER_CONFIRMATION_EMAIL_ENABLED` en false deja el PDF en `skipped` / `email_proceso_apagado` y no llama a Brevo. El mail de `error_sistema` sí se manda.
- Confirmar dos veces el mismo teléfono y canal actualiza tipos y no crea otra fila. Confirmar otro teléfono no borra el primero. `quitar` borra solo el que se nombró. `enabled: false` deja la fila y el worker no le envía.
- Un teléfono con menos de 8 dígitos, o un mail sin forma de dirección, no guarda preview. Un mail que no es de un usuario del tenant sí guarda preview.
- Un 503 de Graph deja la fila `failed` / `provider_5xx` y el job `pending` con `available_at` a 30 s. La fila que ya está `sent` no se reenvía. Al quinto fallo la fila queda `dead`.
- Un body de Graph con `131042` deja el WhatsApp del pedido en `skipped` / `meta_billing`, no llama a `send_text_message`, y encola `error_sistema` una sola vez.
- El worker de `error_sistema` no llama a `send_template_message`. El teléfono suscripto a ese tipo queda `skipped` / `meta_billing`. Cada mail suscripto tiene su fila. Sin ninguno, el job queda `done` con `no_recipients`.
- Un ticket que hoy no notifica y que no tiene suscripciones a `asistencia_humana` no inserta job.
- `processing` con `locked_at` de más de 5 minutos vuelve a `pending`.
- Confirmar la tool no llama a Meta ni a Brevo. La auditoría no guarda el teléfono ni el mail. `ver_notificaciones` sí muestra el destino.
- Confirmar la tool vieja de notificaciones de pedido no inserta ni cambia filas de `notification_subscriptions`.
- `ver_envios_notificacion` recorta a 100 y sí devuelve el destino.
- Las tools nuevas están en la superficie y exigen el scope que ya existe.

---

## Plan de prueba humana (antes del PR)

Backend en el puerto `8000`. Conector en `8100` (`uvicorn mcp_server.main:app --port 8100`). Agente local solo para el paso del corte, contra ese backend. Tenant `demo`. El scheduler del backend tiene que estar prendido (`SCHEDULER_ENABLED`). No hace falta el backoffice. No hace falta forzar un corte de pago real en Meta: ese caso lo cubre el test, y en local se puede insertar un `ia_ticket` de `demo` con el tag.

1. `ver_notificaciones` en `demo`. Aparecen los teléfonos que el backfill sacó de los vendedores, con su nombre y el alcance que tenían (`all` o `cartera`), y los mails de usuarios suscriptos a pedidos y a error de sistema.
2. Confirmar un teléfono que no es de un vendedor ni de un cliente de `demo`, con los tres tipos, prendido. Confirmar el teléfono de un vendedor de `demo` que tenga cartera, solo `order_confirmed`, con `alcance = cartera`. Confirmar dos mails que no son usuarios: uno solo con `order_confirmed` y otro solo con `error_sistema`. `ver_notificaciones` muestra esas filas además de las del backfill. Pedir `alcance = cartera` con el teléfono libre: no hay `preview_id`. Apagar un teléfono (`enabled: false`) y volver a leer: la fila sigue, apagada.
3. Confirmar un pedido de un cliente que esté en la cartera de ese vendedor, y otro de un cliente que no lo esté. En el primero, el WhatsApp del vendedor y el número libre aparecen en las deliveries. En el segundo, el número libre aparece y el del vendedor no. El PDF incluye el mail del cliente, si tiene, y el mail suscripto a pedidos. El mail que solo tiene `error_sistema` no está en ese envío. Confirmar el mismo pedido otra vez no agrega otro job.
4. `ver_envios_notificacion` lista esas filas con canal, destino y estado.
5. Crear en `demo` un ticket cuya descripción empiece con `[META_BUSINESS_PAYMENT_ERROR]`. Aparece un job `error_sistema`. El mail suscripto a ese tipo tiene una delivery de mail. El teléfono suscripto a los tres tipos tiene una delivery WhatsApp `skipped`. En los logs de ese job no hay llamada a la plantilla `suplai_error_sistema_vendedor_v1`.
6. Pedir un envío de prueba. La tool no manda nada.
7. `previsualizar_notificaciones_pedido` sigue guardando vendedores en el JSON. Después de confirmarla, `ver_notificaciones` muestra las mismas suscripciones que antes de ese confirmar.

---

## Riesgos

- Entre el merge del backend y el del agente, un pedido del agente puede generar el WhatsApp viejo (envío directo) y además el trabajo nuevo si el webhook sigue pegándole al backend. El webhook nuevo no manda otro WhatsApp: encola, y la clave única evita dos jobs. El WhatsApp directo se apaga recién con el PR del agente. Mergear los dos PRs seguidos.
- El mail de error de sistema, prendido en el backfill para los usuarios del tenant, les escribe la primera vez que Meta rechace por pago. Es el aviso que se busca. Después se saca un mail o se apaga desde el MCP. Un tenant sin usuarios con mail y sin una suscripción cargada a mano queda en `no_recipients`.
- La estrategia `round_robin`, `weighted` o `random` deja de elegir un solo destino: cada suscripción prendida recibe el aviso que le corresponde. El alcance `cartera` sí se copia en el backfill y se sigue aplicando al enviar, leyendo la cartera vigente. Cambiar ese alcance en la pantalla vieja o en las tools de la spec 110 no cambia el envío: queda en el JSON. El cambio se hace con `alcance` en `previsualizar_notificaciones`. Mover un cliente de vendedor sí cambia el próximo pedido, sin tocar la suscripción.
- `order_notification_sent` deja de escribirse. Quien contara esos eventos para round-robin deja de tener señal nueva. El registro pasa a ser `notification_deliveries`.
- Si el proceso muere después de que Meta o Brevo aceptaron el envío y antes de escribir la fila `sent`, el reintento puede repetir ese destino. La fila que ya está `sent` no se reenvía. Es el costo de no retener la conexión de Postgres durante el HTTP.
