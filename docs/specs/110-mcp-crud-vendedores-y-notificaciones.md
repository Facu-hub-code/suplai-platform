# 110 — Conector: CRUD de vendedores y a quién avisar de un pedido

**Estado:** Implementado en `backend-supabase` rama `feat/mcp-vendedores-notificaciones` y en el plugin `suplai-sales-claude-plugin` misma rama. Sin merge.  
**Fecha:** 2026-10-12  
**Repos:** `backend-supabase` (tools, scopes, check de previews, envío de mail), `suplai-sales-claude-plugin` (skill y manual), `suplai-platform` (este spec)  
**Rama sugerida:** `feat/mcp-vendedores-notificaciones`  
**Relaciona:** [006](./006-vendedores-unificados-backoffice.md), [072](./072-notificacion-pedidos-cartera-vendedor.md), [094](./094-claude-mcp-manual.md)–[107](./107-mcp-explorar-ocultar-productos.md), backend [025](../../../backend-supabase/docs/specs/025-validar-unicidad-telefono-cliente-vendedor.md), [040](../../../backend-supabase/docs/specs/040-territorio-geo-zonas-vendedores-pdv.md), [021](../../../backend-supabase/docs/specs/021-order-confirmation-email-brevo-pdf.md), [130](../../../backend-supabase/docs/specs/130-notificacion-pedidos-cartera-vendedor.md), agente [047](../../../agente-conversacional-multi_tenant/docs/specs/047-notificacion-confirmacion-pedido-vendedores.md) y [065](../../../agente-conversacional-multi_tenant/docs/specs/065-seller-notify-meta-cutover-fallback.md), backoffice [069](../../../product-management-app/doc/specs/069-order-notification-meta-template-ui.md). Catálogo del conector: `backend-supabase/docs/mcp/README.md`.

---

## Objetivo

Desde Claude se puede armar el equipo de ventas y elegir quién se entera cuando se confirma un pedido. Hoy las dos cosas existen, pero el conector no las muestra.

El alta, la edición y la baja de vendedores ya están en `routers/vendedores.py` y en el backoffice (`use-vendedores-management.tsx`, spec 006). El WhatsApp a vendedores ya se configura por tenant, sin deploy, en `reglas_negocio.order_notification`. El conector (`https://mcp.suplaisales.com/mcp`) no tiene ninguna tool de las dos.

El mail del pedido es el hueco de verdad: hoy sale al email del cliente y en copia a todos los usuarios del tenant. No hay forma de elegir uno o varios.

### Criterios de aceptación

- `listar_vendedores` trae id, nombre, teléfono, email, activo, zonas y cuántos clientes tiene en cartera. El tenant es el del token.
- Un alta o una edición se escribe recién en `confirmar`. El teléfono queda en dígitos. Si no se puede normalizar, o si ese número ya es de un cliente o de un vendedor, el preview vuelve `valido: false` y no hay `preview_id`.
- Desactivar pone `activo = false`. La cartera y las geo-zonas quedan. El preview avisa que ese teléfono deja de entrar a Field.
- Asignar o desasignar usa las mismas funciones que el API: tocan `vendedores_clientes` y el texto `clients.vendedor`. Cambiar el nombre del vendedor deja ese texto como estaba.
- `ver_notificaciones_pedido` muestra la config de WhatsApp y la de mail sin abrir un preview.
- Confirmar WhatsApp guarda vendedores que ya existen en ese schema, con estrategia y alcance, en `reglas_negocio.order_notification`.
- Confirmar mail guarda `email_recipients` en el mismo JSON. Esa lista pasa a ser la copia. El mail del cliente sigue como destinatario principal si lo tiene. Una lista vacía no inventa direcciones.
- Confirmar la config no manda ningún mensaje. El aviso sigue saliendo cuando se confirma el pedido, por los caminos que ya existen.

---

## Cómo está hoy

**Vendedores.** Cada tenant tiene `{schema}.vendedores`. La baja del API ya es lógica: `DELETE` pone `activo = false`. El teléfono se normaliza a dígitos y no puede repetirse entre vendedores y clientes (`check_phone_exists`, spec backend 025). La cartera vive en `vendedores_clientes` y, además, el nombre del vendedor se copia a `clients.vendedor`. Ese texto es el que leen grupos, plantillas y el aviso por cartera.

**WhatsApp al confirmar.** Se puede avisar a uno o a varios vendedores. Con estrategia `all` llegan todos los tildados. Con `random`, `round_robin` o `weighted` se elige uno del grupo. Cada uno puede ver todos los pedidos (`scope: all`) o solo los de su cartera (`scope: cartera`). La pantalla está en Configuración de notificaciones y la API es `PATCH /{schema}/distribuidora/config`. El suscriptor tiene que ser un `vendedor_id` existente: no se carga un número a mano.

**Mail al confirmar.** `send_order_confirmation_emails` arma un solo correo. El destinatario principal es `clients.email`. La copia son todos los usuarios del tenant. Si el cliente no tiene mail, el destinatario principal pasa a ser todo el staff. El interruptor es de proceso (`ORDER_CONFIRMATION_EMAIL_ENABLED`), no una lista por distribuidora.

El aviso corre al confirmar el pedido, no al crearlo abierto. El agente avisa por su lado. Tienda y Field avisan por el backend, y no vuelven a mandar el WhatsApp si el origen ya fue el agente.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Quién escribe | `VendedorService` y las funciones de cartera que ya usa el API, detrás de preview y `confirmar` | Ahí están el 409 del teléfono y la copia del nombre a `clients.vendedor`. El rol `mcp_connector` solo puede leer | SQL directo, o un POST al router de vendedores. Ese router no mostró auth de usuario, y el schema lo elegiría el modelo |
| Tenant | Solo el schema del JWT | Es la regla del conector. El token ya resolvió la distribuidora | Un argumento `schema` o un header armado por el modelo |
| Permisos | `vendedores:leer` / `vendedores:escribir` y, aparte, `notificaciones:leer` / `notificaciones:escribir`. Los de escritura entran en `CONFIRMAR_SCOPES` | Listar no tiene que poder confirmar. Elegir quién recibe los pedidos es otro permiso que editar el equipo | Meter el alta en `carga:escribir`, o colgar las notificaciones de `vendedores:escribir` |
| Baja | `activo = false` | Hay conversaciones con `ON DELETE RESTRICT`. En varios tenants la cartera tiene `ON DELETE CASCADE` y un delete físico se la llevaría. Field solo entra con un vendedor activo | Borrar la fila |
| Teléfono | Solo dígitos. Si no queda ninguno, el preview no se guarda | El índice único del teléfono crudo no está en todos los schemas. La regla de negocio es `check_phone_exists`. Hoy un teléfono vacío se saltea ese chequeo | Guardar el texto tal como lo escribió la persona |
| Choque de teléfono | El preview dice de quién es el número y no genera `preview_id` | El operador tiene que ver el conflicto antes de confirmar | Que explote el `confirmar` con un 409, cuando el chat ya dio el alta por hecha |
| Cartera | Las funciones `bulk_assign` y `bulk_unassign` | Prenden o apagan la fila puente y escriben o limpian `clients.vendedor`. El resto del producto lee ese texto | Tocar solo `vendedores_clientes` y dejar el texto viejo |
| Cambio de nombre | En esta entrega no se reescribe `clients.vendedor` | El API tampoco lo hace. El preview avisa, para que no parezca que la cartera ya muestra el nombre nuevo | Hacerlo solo en el conector y dejar el backoffice con otra regla |
| Columnas que no se tocan | `codigo_ruta`, `erp_codigo`, `is_mock`, avatar, geo-zonas y geocode | El código de ERP lo carga el sync y no existe en todos los schemas. El avatar es un archivo. Las zonas ya se asignan en el backoffice | Un CRUD de todas las columnas |
| WhatsApp | La misma config que el backoffice: vendedores existentes, estrategia y alcance, guardada en `order_notification` | Ya funciona por tenant, sin deploy. Un número suelto no es un suscriptor | Aceptar un teléfono escrito a mano, o usar el canal viejo de perfiles del backoffice, que en producción está vacío |
| Mail | Una lista `email_recipients` en el mismo JSON. Cada mail tiene que ser de un usuario de esa distribuidora | Hoy no hay lista: la copia es “todos”. Sin este campo la tool solo podría describir el comportamiento actual | Una tabla nueva. Habría que migrar, poner RLS y enseñarle al PATCH de config un segundo lugar |
| Qué cambia el mail | Si la lista está guardada, reemplaza la copia a todo el staff. El mail del cliente se mantiene. Si el cliente no tiene mail, el destinatario principal pasa a ser esa lista. Si la lista está vacía, no se inventa nadie | El operador elige uno o varios. Seguir copiando a todo el staff deja la lista sin efecto | Seguir copiando a todos los usuarios |
| Distribuidoras que no usan la tool | Si la clave `email_recipients` no está en el JSON, el mail sigue como hoy | El deploy no puede callar los avisos que ya salen | Tratar “clave ausente” como lista vacía el día que se publica |
| La tool no envía | `confirmar` solo guarda la config. El mensaje sigue saliendo al confirmar el pedido | El doble envío entre agente y backend ya está resuelto. Un mensaje de prueba le escribiría al vendedor | Disparar un envío desde `confirmar` |
| Auditoría | Se guardan ids, estrategia, alcance y cantidades. El teléfono y el mail quedan afuera | El preview puede nombrar un comercio o un inbox. La tabla de auditoría no es el lugar de ese dato | Guardar el JSON completo de `order_notification` |

---

## Alcance

### Incluido

- Listar, crear, editar, reactivar y desactivar vendedores del tenant del token, con preview y `confirmar`.
- Asignar y desasignar clientes, con el mismo efecto sobre `clients.vendedor` que el API.
- Ver y cambiar los destinatarios de un pedido confirmado, por WhatsApp y por mail.
- La lista `email_recipients` dentro de `reglas_negocio.order_notification`, y el cambio del envío de mail para usarla cuando la clave existe.
- Scopes, textos de consentimiento, recetas del conector y la skill del plugin.
- El check de tipos de preview, sumando los cuatro tipos nuevos y dejando los que ya acepta `sql/159`.

### Fuera de alcance

- Avatares, geocode y el alta o la asignación de geo-zonas.
- `codigo_ruta`, `erp_codigo`, `is_mock`, y el sync de Galileo u Odoo.
- Reescribir `clients.vendedor` cuando se cambia el nombre.
- Borrar la fila del vendedor, o soltar la cartera al desactivarlo.
- Editar el prompt, las plantillas de Meta o las agendas. El aviso usa la plantilla que el tenant ya tiene.
- El canal viejo (`notification_event_config`, `profiles.is_whatsapp_subscribed`) y n8n.
- Otro evento que no sea el pedido confirmado.
- Mandar un WhatsApp o un mail de prueba desde la tool.
- El flag de proceso `ORDER_CONFIRMATION_EMAIL_ENABLED`. Si está apagado, el preview lo dice y la lista igual se puede guardar: el envío sigue dependiendo de ese flag.
- Una pantalla nueva en Field. Field no crea vendedores.

---

## Tools

El tenant no es un argumento. Un preview dura 30 minutos. `confirmar` sigue siendo la única tool que escribe, y confirmar dos veces el mismo preview no vuelve a escribir.

### `listar_vendedores`

Scope `vendedores:leer`.

Filtros opcionales: texto, activo o no, y un límite (20 por defecto, 100 como máximo). Si hay más filas, la respuesta trae `hay_mas: true`.

Cada fila trae id, nombre, teléfono, email, si está activo, los nombres de sus geo-zonas y cuántos clientes activos tiene en cartera. Si no tiene geo-zonas, se muestra el texto libre `vendedores.zona`, que en algunos tenants es el único dato. El orden es el del listado del API, `id` descendente.

### `previsualizar_vendedor`

Scope `vendedores:escribir`.

Sin `vendedor_id` es un alta. Con id es una edición, y ahí también se reactiva: `activo: true`. Los datos son nombre, teléfono, email y activo.

El preview muestra el teléfono ya en dígitos y el diff contra la fila actual. En un alta, el diff dice que se va a crear. Si cambia el nombre, avisa que el texto de la cartera queda como está.

`confirmar` llama a `VendedorService.create` o `VendedorService.update` con nombre, teléfono, email y activo. El alta no nombra `erp_codigo`, porque esa columna existe solo en siete schemas.

### `previsualizar_desactivar_vendedor`

Scope `vendedores:escribir`. Input: `vendedor_id`.

El preview dice quién es, cuántos clientes le siguen asignados, que las geo-zonas no se tocan y que ese teléfono deja de entrar a Field. `confirmar` pone `activo = false`. Si el id no existe, `valido: false` y el campo es `vendedor_id`.

### `previsualizar_cartera_vendedor`

Scope `vendedores:escribir`. Inputs: `vendedor_id`, de 1 a 100 `cliente_ids`, y la acción `asignar` o `desasignar`.

El preview separa los clientes que existen de los que no, y dice qué nombre va a quedar en `clients.vendedor`. Al desasignar, el texto se limpia solo donde todavía es el nombre de ese vendedor: es lo que ya hace el API.

Un vendedor inactivo se puede usar. El API de cartera tampoco exige que esté activo, y el preview lo avisa.

### `ver_notificaciones_pedido`

Scope `notificaciones:leer`. Sin argumentos.

Para el pedido confirmado muestra si el WhatsApp está prendido, la estrategia, y cada suscriptor con id, nombre, alcance y peso. El teléfono no sale. También dice si existe `email_recipients` y, si existe, cuáles son. Si la clave no está, la lista vuelve `null` y un aviso explica que la copia sigue siendo todo el staff. Incluye si el mail de proceso está habilitado.

### `previsualizar_notificaciones_pedido`

Scope `notificaciones:escribir`.

El canal es `whatsapp` o `email`. El evento, en esta entrega, es solo `order_confirmed`. Se manda si queda habilitado y la lista de destinatarios.

**WhatsApp.** La lista son vendedores del schema, cada uno con alcance y, si la estrategia es `weighted`, un peso. La estrategia es `all`, `random`, `round_robin` o `weighted`. Se valida con el mismo contrato que el PATCH de config (`OrderNotificationConfig`). El preview muestra nombre y alcance, sin teléfono. Si queda habilitado y la lista está vacía, avisa que el pedido se confirma y nadie recibe WhatsApp.

**Mail.** La lista son direcciones de usuarios de esa distribuidora. Una que no matchea no genera preview. El preview explica que esa lista reemplaza la copia a todo el staff, que el mail del cliente se mantiene si existe, y qué pasa si la lista está vacía.

`confirmar` hace merge sobre el `order_notification` que ya está guardado. No pisa la plantilla de Meta ni el otro canal: guardar el mail no borra los suscriptores de WhatsApp, y al revés.

---

## Orden de implementación

El código de producto es un PR de `backend-supabase`. El plugin nombra tools que tienen que existir, así que se mergea después. Este documento puede mergearse cuando se quiera.

| Repo | Rama sugerida | Qué entra | Orden de merge |
|---|---|---|---|
| `suplai-platform` | `feat/mcp-vendedores-notificaciones` | Este spec | Cuando se quiera |
| `backend-supabase` | `feat/mcp-vendedores-notificaciones` | Check de previews, scopes, tools, envío de mail, tests y recetas | Primero |
| `suplai-sales-claude-plugin` | `feat/mcp-vendedores-notificaciones` | Skill y una línea en el manual del conector | Después del backend |

Dentro del PR de backend:

1. Migración del check de `mcp_accion_previews.tipo`. El número libre siguiente a `sql/162`; hoy sería `sql/163`.
2. Scopes, `TOOL_SCOPE`, `CONFIRMAR_SCOPES` y las etiquetas de la pantalla de consentimiento.
3. Tools de vendedores, registradas como el resto (`register_*`, `superficie.py`, `build_server()`).
4. Tools de notificaciones y el cambio de `send_order_confirmation_emails` para usar `email_recipients` cuando la clave está presente.
5. Handlers nuevos en el dispatch de `confirmar`.
6. Tests.

---

## Migración de base de datos

No hay tabla nueva ni columna nueva.

La lista de mails vive en `public.distribuidoras.reglas_negocio`, que ya es JSON, en `order_notification.email_recipients`. El WhatsApp sigue en las claves que el PATCH de config ya escribe.

Sí cambia un constraint: `mcp_accion_previews_tipo_check` tiene que aceptar `vendedor`, `desactivar_vendedor`, `cartera_vendedor` y `notificaciones_pedido`, y seguir aceptando todos los tipos de `sql/159`. Si al implementar ya existe un `sql/163`, se usa el número libre siguiente y se copia el check vigente.

Rollback del check: volver al listado de `sql/159`. Si quedaron previews de los tipos nuevos, hay que consumirlos o borrarlos antes, porque el check viejo no los acepta. Eso no borra vendedores ni toca `reglas_negocio`.

Rollback de la lista de mails: sacar la clave `email_recipients` del JSON de ese tenant. Sin la clave, el envío vuelve a copiar a todo el staff.

---

## Plan de prueba en CI/CD

Pytest junto a `tests/test_mcp_superficie.py` y los de preview que ya existen. El test de superficie incluye los nombres nuevos. El check de tipos cubre los handlers de `confirmar`.

- `listar_vendedores` no trae `is_mock` ni teléfonos de clientes, y recorta a 100.
- Un teléfono `"abc"` o `"---"` no guarda preview. El campo del error es `telefono`.
- Un teléfono que ya es de un cliente o de un vendedor vuelve `valido: false` con `PHONE_ALREADY_EXISTS_IN_CLIENTS` o `PHONE_ALREADY_EXISTS_IN_VENDEDORES`.
- Confirmar un alta deja el teléfono en dígitos y el `INSERT` no nombra `erp_codigo`.
- Confirmar una desactivación deja `activo = false` y la misma cantidad de filas de cartera activas.
- Confirmar un cambio de nombre no toca `clients.vendedor`.
- Confirmar `asignar` deja `clients.vendedor` igual al nombre del vendedor. `desasignar` lo limpia solo donde el texto era ese nombre.
- Más de 100 clientes no guarda preview.
- Un `vendedor_id` de otro schema no entra a los suscriptores de WhatsApp.
- Un mail que no es de un usuario del tenant no guarda preview.
- Con `email_recipients` presente y vacía, el envío no arma copia. Si el cliente tiene mail, ese es el destinatario. Si no tiene, no se inventa uno.
- Sin la clave `email_recipients`, la copia sigue siendo los usuarios del tenant.
- Confirmar el mail no borra los suscriptores de WhatsApp, ni al revés.
- La auditoría del preview de mail y del de vendedor no guarda el teléfono ni la dirección.
- Las tools de notificaciones no llaman a `send_seller_order_notification` ni a `send_order_confirmation_notification`.

---

## Plan de prueba humana (antes del PR)

Backend en el puerto `8000` y conector en `8100` (`uvicorn mcp_server.main:app --port 8100`), o el MCP de staging con un usuario de backoffice del tenant. Tenant `demo`. Un vendedor de prueba y un cliente cuyo teléfono se conoce, para ver el choque. El flag de mail puede estar apagado: alcanza con mirar el JSON.

1. `listar_vendedores` con activos. Aparecen los de `demo`, con la cantidad de cartera.
2. Alta con el teléfono de un cliente que ya existe. El preview es inválido, no hay `preview_id`, y el texto dice que el número es de un cliente.
3. Alta con un teléfono nuevo, escrito con espacios o un `+`. El preview muestra solo dígitos. Confirmar. El listado lo trae activo.
4. Editar el nombre. El preview avisa que el texto de la cartera no cambia. Confirmar. Un cliente ya asignado sigue con el nombre anterior en `clients.vendedor`.
5. Asignar un cliente de `demo` y confirmar. Ese cliente queda con el nombre del vendedor. Desasignar y confirmar: el texto se limpia.
6. Desactivar. El preview dice cuántos clientes siguen asignados y que Field no va a entrar. Confirmar. El listado de activos ya no lo muestra. Volver a activarlo con `activo: true`.
7. `ver_notificaciones_pedido`. Si `demo` no tiene `email_recipients`, la respuesta lo dice y aclara que la copia sigue siendo todo el staff. Los suscriptores de WhatsApp, si hay, salen con nombre y sin teléfono.
8. Configurar WhatsApp con un vendedor de `demo`, estrategia `all`, alcance `cartera`, habilitado. Confirmar. La lectura muestra esa fila. Repetir con un id que no existe: no hay preview.
9. Configurar mail con una dirección que no es de un usuario de `demo`. El preview es inválido. Repetir con un mail de un usuario del tenant y confirmar. En el JSON está `email_recipients` y los suscriptores del paso anterior siguen. Confirmar de nuevo con la lista vacía: el preview dice que nadie del staff va en copia y que el mail del cliente se mantiene si lo tiene.
10. Pedir un envío de prueba. La tool explica que el aviso sale cuando se confirma un pedido, y no manda WhatsApp ni mail.
