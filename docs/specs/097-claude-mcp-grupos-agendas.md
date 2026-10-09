# 097 — Claude MCP: grupos y agendas sobre una plantilla

**Estado:** Borrador  
**Fecha:** 2026-10-08  
**Repos:** `backend-supabase` (tools, scope, preview), `suplai-sales-claude-plugin` (skills), `suplai-platform` (este spec)  
**Ramas sugeridas:** `feat/claude-mcp-agendas` en backend y en el plugin  
**Serie:** [objetivos de capacidades](../claude-mcp/objetivos-capacidades.md), caso 2.1. Depende del [096](./096-claude-mcp-plantillas.md). La carga de clientes es el [095](./095-claude-mcp-carga-clientes-productos.md).  
**Relaciona:** `routers/grupos.py` (`_validate_grupo_modes`), `routers/agenda.py` (`_validate_target`, `_validate_create_body`), `models/grupos.py`, `models/agenda.py`.

---

## Objetivo

El usuario elige una plantilla, dice a quién escribirle y cuándo. Claude arma el grupo, muestra cuántos comercios entran y deja la agenda apuntando a esa plantilla. El WhatsApp lo sigue mandando el sender de agenda. Claude no envía los mensajes uno por uno.

La agenda nace inactiva. Se prende en el mismo confirm solo si el usuario lo pide y la plantilla ya está aprobada en Meta.

### Métricas de éxito

- Un grupo sin ningún eje no se crea. Etiquetas, lista y días se combinan con AND. Geo-zona y un grupo especial no se mezclan con esos ejes.
- La agenda tiene `grupo_id` o `client_id`, nunca los dos, y la plantilla es del mismo tenant.
- Si la plantilla promociona, el grupo filtra por una lista de esa promoción. Sin eso no hay preview.
- Confirmar deja la agenda inactiva salvo un sí explícito a activarla, y ese sí no alcanza si Meta todavía no la aprobó.
- En `demo`, el preview dice el conteo y hasta cinco razones sociales, sin teléfonos.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Quién elige la audiencia | El grupo. La plantilla no define a quién le llega | Así está armado el sender: resuelve los miembros con la misma membresía que el preview del grupo. | Meter los filtros en la plantilla. |
| Escritura | `previsualizar_agenda` y `confirmar_agenda` | El conteo y el horario que el usuario acepta quedan guardados. Confirmar no reinterpreta la frase. | Crear grupo y agenda en la primera tool. |
| Scope | `agenda:escribir`, aparte de `plantillas:escribir` | Programar un envío es otra autorización que redactar un texto. El consentimiento lo dice en su línea. `required_scopes` sigue en `pedidos:leer`. Si el token no trae el scope, la tool pide reconectar. | Reusar `plantillas:escribir`. Quien aprobó “crear plantillas” no aprobó “mandarlas todos los martes”. |
| Destino | Exactamente uno: `grupo_id` o `client_id`. Se reusa `_validate_target` | Es la regla del `POST /agenda`. Los dos a la vez, o ninguno, no tienen un sender definido. | Una agenda “a toda la cartera”. El API ya rechaza el grupo vacío por eso. |
| Ejes del grupo | Los de `_validate_grupo_modes` | Etiquetas + lista + días de visita se combinan con AND. Dentro de las etiquetas alcanza una, incluidas las hijas. Dentro de los días alcanza que `dia_de_visita` sea uno de los elegidos. Un `vendedor_id` puede sumarse. Geo-zona no se mezcla con esos ejes. `open_cart`, `recent_orders` y `churn_risk` no se mezclan con nada de lo anterior ni entre sí. | Inventar un modo “todos los clientes activos”. |
| Quién entra al conteo | `lifecycle = client` y `activo_ai` distinto de false, la misma consulta del listado de grupos | Los prospectos no están en la cartera que visita el vendedor. El preview lo dice si el usuario habló de prospectos. | Contar `v_prospectos`. |
| Grupo existente | Si el usuario nombra uno y los ejes coinciden, se reusa el id. Si el nombre existe y los ejes son otros, no hay preview: hay que usar ese grupo tal cual o elegir otro nombre | Actualizar el grupo cambiaría las agendas que ya lo apuntan. Duplicar el nombre confunde al sender y al backoffice. | Hacer upsert del grupo. |
| Orden al confirmar | Primero el grupo, después la agenda. Si la agenda falla, el grupo queda y el error dice que no se programó | El grupo ya tiene nombre y miembros; el usuario puede reintentar la agenda sin perderlo. El objetivo lo pide así. | Una transacción que borra el grupo si la agenda falla. Esconde un objeto que ya se puede volver a usar. |
| Plantilla | `meta_plantilla_id` del mismo tenant, el chequeo que ya hace `_check_meta_plantilla_tenant` | Una plantilla de otro tenant filtraría mal o no saldría. | Aceptar el nombre y buscar en cualquier WABA. |
| Activa | Confirmar inserta `activo = false`, aunque el default del API sea true. `activar = true` en el mismo confirm la prende solo si el estado en Meta es `APPROVED` | Una agenda activa con plantilla en revisión el sender la tomaría y Meta la rechaza, o peor, sale con otro texto. El preview muestra el primer horario y el conteo antes de ese sí. | Respetar el default `activo = true` del `AgendaCreate`. |
| En revisión | Se puede guardar inactiva y el preview lo dice. No se parte ni se “preactiva” | El 096 acaba de crear plantillas que Meta todavía no aprobó. Guardarlas apagadas deja el trabajo hecho. | Negarse a crear la agenda hasta la aprobación. El usuario tendría que volver a describir el grupo. |
| Promo | Si viene `promocion_id`, el grupo tiene que filtrar por una `lista_precios_id` de esa promo. Si la promo es por `codigo_cliente`, el destino es ese cliente, no un grupo por lista | Es la regla del caso 2: otra lista hace que el agente no vea el precio. El 096 no guarda el objetivo en `meta_plantillas`; el cuerpo vive en Meta. Esta tool exige el id cuando Claude dice que es una promo, y el preview, si no viene id, dice en una línea “esta agenda no está atada a una promoción”. | Leer el cuerpo en Meta y detectar precios con una regex. Falla en los dos sentidos. |
| Variables fijas | `dynamic_params` solo puede pisar la posición cuya columna es `producto` | El modelo de agenda manda una lista de strings que tapa las variables para todo el envío. Pisar `nombre` o `razon_social` le escribe el mismo comercio a toda la ruta. | Dejar que Claude mande el nombre de la promo en la posición del nombre del cliente. |
| Cupo | El preview informa `remaining_today` del guard del 096. Si el grupo es más grande, no se parte | Partir la agenda en varios días cambia el horario que el usuario pidió. Lo advierte y el usuario achica el grupo o elige días. El cupo de hoy no bloquea una agenda de otro día. | Rechazar el confirm cuando el conteo supera el cupo de hoy. |
| Horario | Recurrente: días `lunes`…`domingo` (con tilde en miércoles y sábado; sin tilde se normaliza) y hora `HH:MM` opcional. Puntual: una fecha, sin días | Es `_validate_create_body`. Las dos cosas juntas el API las rechaza. | Aceptar “todos los días hábiles” como un tipo nuevo. |
| Muestra | Hasta cinco `razon_social`, más el total. Sin teléfonos, emails ni CUIT en la respuesta | El listado de grupos hoy devuelve la fila entera de `clients`. Claude la repetiría en el chat. | Reusar el JSON del `GET /grupos`. |
| Auditoría | `preview_id`, ids de grupo, plantilla y promo, conteo, `activar`, resultado. Sin nombres ni teléfonos | Misma regla que el 095 y el 096. | Guardar la muestra de comercios. |
| Conexión | Pool de la API | `mcp_connector` no tiene INSERT en `grupos` ni en `agenda`. | Ampliar el rol del conector. |

---

## Alcance

### Incluido

Tres tools con scope `agenda:escribir`. `listar_grupos` y `previsualizar_agenda` no escriben. `confirmar_agenda` no es idempotente.

**`listar_grupos`**

- Id, nombre, ejes (lista, días, etiquetas, geo, condición, vendedor) y `total_clientes`.
- Sin la lista de teléfonos.

**`previsualizar_agenda`**

- Plantilla por id local.
- Destino: un `grupo_id` existente, un `client_id`, o la definición de un grupo nuevo (`nombre` y al menos un eje).
- `tipo` `recurrente` o `puntual`, con días u hora, o con fecha.
- `promocion_id` opcional. Obligatorio en la práctica cuando la skill marcó la plantilla como promo: sin él el preview existe, pero la línea de “no está atada a una promoción” va en el resumen y la skill no debe pedir el sí de una promo en ese estado.
- `dynamic_params` opcional, solo en posiciones `producto`.
- Guarda el payload 30 minutos en `public.mcp_accion_previews` con `tipo = grupo_agenda`.
- Respuesta: `preview_id`, conteo, hasta cinco razones sociales, nombre del grupo (nuevo o reusado), plantilla y si está `APPROVED`, horario, cupo restante de hoy, y si al confirmar va a quedar inactiva.
- No inserta grupo ni agenda.

**`confirmar_agenda`**

- Recibe `preview_id` y `activar` (default false).
- Crea el grupo solo si el preview no reusa uno. Después crea la agenda con `activo = false`.
- Si `activar` es true y el estado es `APPROVED`, un update deja `activo = true`. Si no está aprobada, queda inactiva y la respuesta lo dice.
- Consume el preview cuando la agenda quedó insertada, activa o no.
- Si el grupo se creó y la agenda no, el preview no se consume y el error nombra el `grupo_id` que sí quedó.

La skill `skills/grupos-agendas/SKILL.md` aplica las reglas de ejes, de la misma lista que la promo, de `dynamic_params` y de no activar sin un sí. `manual-conector` suma estas tools. Estrategias, Pareto y el calendario mensual siguen en “todavía no”.

### Fuera de alcance

- La agenda Pareto del supervisor (spec 080), que rearma la audiencia en cada corrida.
- El calendario mensual de una estrategia (spec 031) y el alta de la estrategia. El caso 4 la ata a un `grupo_id` y un `agenda_id` que esta entrega deja creados.
- Pausar, reanudar o cancelar un envío que ya salió.
- Mandar el WhatsApp desde el chat, aunque sea un test-send.
- Partir un grupo que no entra en el cupo del día.
- Editar los ejes de un grupo que ya existe.
- Etiquetar clientes. Si la etiqueta no existe, el preview lo dice y no la crea.

---

## Orden de implementación

1. El 096 mergeado, con `public.mcp_accion_previews` ya creada.
2. `backend-supabase`, rama `feat/claude-mcp-agendas` desde `origin/main`. Amplía el check de `tipo`, suma el scope y las tools.
3. Aplicar esa migración antes de probar el confirm.
4. Merge del backend.
5. Plugin, misma rama: `skills/grupos-agendas/SKILL.md` y el renglón del manual. Después del backend.

Quien ya reconectó para el 096 tiene que reconectar de nuevo: el token viejo no trae `agenda:escribir`.

---

## Migración de base de datos

`sql/148_mcp_accion_previews_grupo_agenda.sql`.

Amplía el check de `public.mcp_accion_previews.tipo` para aceptar `grupo_agenda` además de `plantilla`. Misma tabla, mismo RLS, sin GRANT nuevo.

Sin columnas nuevas en `grupos` ni en `agenda`.

Rollback: volver el check a solo `plantilla` después de borrar las filas `grupo_agenda`. No borra grupos ni agendas ya confirmados.

Si el 096 todavía no se aplicó, esta migración no corre sola: la tabla nace en el 096.

---

## Plan de prueba en CI/CD

Pytest en `backend-supabase`:

- Grupo sin ejes → sin `preview_id`, código equivalente a `GRUPO_MODE_REQUIRED`.
- Etiquetas y geo-zona en el mismo payload → sin preview.
- `open_cart` junto con una lista → sin preview.
- `grupo_id` y `client_id` juntos, o ninguno cuando no hay definición nueva → sin preview.
- Recurrente sin días, o puntual sin fecha, o los dos tipos de dato a la vez → sin preview.
- Plantilla de otro tenant → sin preview.
- `promocion_id` cuya lista no es la del grupo → sin preview.
- `dynamic_params` en la posición de `razon_social` → sin preview. En la de `producto` → preview.
- Nombre de grupo ya usado con otros ejes → sin preview. Mismos ejes → el payload guarda el id existente y confirmar no inserta otro grupo.
- Confirmar con `activar = true` y estado distinto de `APPROVED` → fila de agenda con `activo = false`.
- Confirmar con `activar = false` y plantilla aprobada → igual queda inactiva.
- Preview vencido, ajeno o consumido → cero inserts.
- La muestra de la respuesta no trae `phone_number`.
- La auditoría no trae razones sociales.
- Annotations y scope en el schema de las tools.

El CI (`pytest`) sigue verde. No hay llamada a Meta en estos tests: el estado de la plantilla se inyecta.

Gap: el plugin no tiene CI. Se revisa a mano contra las tools del backend.

---

## Plan de prueba humana

Tenant `demo`. No usar un tenant de un cliente. Claude reconectado, con el permiso de agendas en el consentimiento. Backend `8000` y MCP `8100` en local, o los dos servicios ya deployados.

Hace falta una plantilla del `demo` en estado aprobado y, para el caso de promo, una promoción vigente de una lista que tenga clientes. Si la única plantilla nueva es la del 096 y sigue en revisión, la prueba de “activar” tiene que mostrar que la agenda queda apagada. No hace falta esperar a Meta para dar OK a este spec.

Pasos:

1. “Armame un envío de los martes a las 9 para la lista X con la plantilla Y.” Ver conteo, hasta cinco comercios sin teléfono, el horario y que va a quedar inactiva.
2. Decir que no. No hay grupo nuevo ni fila en `demo.agenda`.
3. Repetir y decir que sí, sin pedir que la active. La agenda existe con `activo = false` y el grupo tiene al menos un eje.
4. Pedir activarla en el mismo confirm de otra prueba, con una plantilla en revisión. Sigue `activo = false` y la respuesta lo explica.
5. Pedir una promo y un grupo de otra lista. No hay preview.
6. Pedir un grupo “de todos”. No hay preview.
7. Nombrar un grupo que ya existe, con los mismos ejes. El confirm no duplica el id.
8. Confirmar el mismo preview por segunda vez. No aparece otra agenda.

OK: nada salió por WhatsApp durante la prueba, la agenda nueva está inactiva, y el manual ya incluye grupos y agendas.
