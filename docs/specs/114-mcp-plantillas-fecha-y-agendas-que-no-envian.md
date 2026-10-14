# 114 — Conector: fecha de la plantilla, agendas usables y envío best effort

**Estado:** Borrador  
**Fecha:** 2026-10-14  
**Repos:** `backend-supabase` (tools, validador, sender), `suplai-platform` (este spec)  
**Rama de este documento:** `feat/mcp-zonas-escritura`  
**Rama de implementación:** `feat/mcp-zonas-escritura` en `backend-supabase`, la misma del mapa de zonas.  
**Relaciona:** [096](./096-claude-mcp-plantillas.md), [104](./104-mcp-agendas-plantillas-deprecar-estrategias.md), [105](./105-mcp-crud-higiene-agendas-plantillas-secuencias.md), [070](./070-whatsapp-estado-webhook-agenda.md).

El backoffice no entra en esta entrega. El scheduler sí, porque es el que manda las agendas que se arman desde el conector.

---

## Objetivo

Desde el conector se puede ver cuándo se registró cada plantilla, y una agenda deja de figurar como inutilizable cuando sus variables sí salen de una columna del cliente. Si un comercio falla, el resto de la audiencia igual se envía, y `listar_envios` muestra cuántos salieron y por qué fallaron los otros.

### Criterios de aceptación

- `listar_plantillas` trae `created_at` en ISO-8601 por cada plantilla que tiene fila en `public.meta_plantillas`. Si no hay fila local, el campo es null.
- Con `creada_desde` y `creada_hasta` (AAAA-MM-DD, día en `America/Argentina/Buenos_Aires`) el listado queda recortado a ese rango. Sin esas fechas, la respuesta es la de hoy más `created_at`.
- En Campi (`del_corro`), `listar_envios` de las agendas #348, #358, #283, #370, #368, #288 y #371 deja de devolver `usable_en_agenda: false` con el motivo que lista caracteres (`[`, `"`, `n`, `o`, `m`, `b`, `r`, `e`). Si la plantilla está `APPROVED` y la única variable es `nombre`, `usable_en_agenda` es true y `motivo_no_usable` es null.
- `motivo_rechazo` es null cuando Meta manda `NONE`. No vuelve el string `"NONE"`.
- `previsualizar_agenda` y `listar_envios` clasifican la misma plantilla igual. El preview ya da `se_puede_activar: true` en la #371; el listado tiene que coincidir.
- Un fallo de un comercio no corta al resto de esa agenda ni a las agendas siguientes del mismo tenant en esa corrida.
- Después de una corrida, `listar_envios` trae `ultimo_resultado` con `enviados`, `fallidos`, `omitidos` y hasta 20 motivos (`cliente_id` y texto). Sin teléfono y sin nombre.
- Una puntual que no llegó a Meta (`enviados = 0`, `fallidos > 0`) sigue activa el mismo día, con `enviado_at` null, para que la corrida siguiente reintente. Al día siguiente se apaga como hoy, y el resultado queda visible aunque ya esté inactiva.
- Los envíos del 12/10 y del 13/10 no se reintentan solos.

---

## Cómo está hoy

Medido el 2026-10-14 en Suplai-east, schema `del_corro` (Campi).

### Fecha de la plantilla

`public.meta_plantillas` tiene `created_at` (timestamptz) y no tiene `updated_at`. El listado de Meta pide `id,name,status,category,language,rejected_reason,components,quality_score`. Ahí no viene ni la fecha de alta ni la del cambio de estado. `listar_plantillas` (`services/mcp_plantillas.py`) no copia `created_at` aunque `_locales_por_nombre` ya lee la fila.

### El listado recorre el JSON como texto

`variable_columns` de las plantillas de estas agendas es un array jsonb de verdad, no un string guardado dos veces:

| Agenda | Plantilla | `jsonb_typeof(variable_columns)` | Valor |
|---|---|---|---|
| #371 | `plantilla_opciones` | array | `["nombre"]` |
| #348 | `clientes_perdidos` | array | `["nombre"]` |
| #368 | `feriado_nueva` | array | `["nombre"]` |
| #370 | `vendedor_faltante_v2` | array | `["nombre"]` |
| #283, #288, #358 | `opciones_carrusel_2` | array | `[]` |

`listar_plantillas` y `previsualizar_agenda` hacen `json.loads` si asyncpg devuelve el jsonb como `str` (`_locales_por_nombre`, `_plantilla_del_tenant`). `listar_envios` no: pasa ese string a `_variables`, y el `for` recorre cada carácter. `["nombre"]` produce el motivo «Las variables no salen de una columna del cliente: [, ", n, o, m, b, r, e, ", ]». `[]` produce «[, ]». Por eso todas las agendas, activas e inactivas, salen `usable_en_agenda: false` aunque el preview de la #371 haya dicho que se puede activar.

`ficha_meta` guarda `rejected_reason` crudo. `listar_plantillas` lo pasa por `explicar_motivo_rechazo`, que convierte `NONE` en null. `listar_envios` no, y el campo sale `"NONE"`.

El único doble encode de esta muestra está en `dynamic_params` de la #348: jsonb de tipo string, valor `"[]"`. El resto de esas agendas tiene `dynamic_params` como array `[]`.

### El scheduler no usa ese validador

`services/agenda_sender.py` hace un `json.loads` y, si el resultado sigue sin ser lista, lo reemplaza por `[]`. Con un array jsonb normal eso alcanza y arma el parámetro `nombre`. El `usable_en_agenda` del listado no frena el cron. Corregir solo el listado no explica por sí solo que el lunes y el martes no hayan salido.

Lo que sí tira envíos abajo:

- El cron corre cada 15 minutos (`CronTrigger(minute="*/15")`). La ventana es de 30 minutos: entra si `hora_envio < fin de la ventana`. Una puntual de las 03:30 entra en las corridas de las 03:30 y las 03:45, hora Argentina, y deja de entrar a las 04:00.
- El `for` de agendas del tenant no tiene `try`. Una excepción en una agenda corta las siguientes de esa corrida. La #371 es la de id más alto: si algo anterior revienta, ella no corre en ese tick.
- Meta que responde error devuelve `(False, mensaje)` y no se inserta fila en `envios_plantillas`. `sent_today` sigue en 0 y el conector no tiene dónde leer el motivo.
- Si nadie se envió, `enviado_at` queda null y la puntual se reintenta el mismo día. A la mañana siguiente `_apagar_puntuales_vencidas` la apaga igual (`fecha_programada < hoy`), sin haber enviado. Así quedaron la #368 y la #370: `activo false`, `enviado_at` null.
- Un grupo vacío (`attempted_sends == 0`) se marca completado. No es el caso de estas: la #371 es el cliente #64296 (`activo_ai`, WhatsApp `validado`, con teléfono y nombre). Las de grupo tienen audiencia por etiqueta (la #368 tiene 367, la #370 tiene 50, la #288 tiene 28, la #283 tiene 47, la #348 tiene 2). La #358 tiene 187 de 200 `client_ids`.

`opciones_carrusel_2` tiene 10 filas en `envios_plantillas` el 2026-10-10 13:00 UTC, con `wamid`, y ninguna el 12 ni el 13. El número GREEN no entra en este spec: el usuario ya lo descartó.

La #371 se creó el 2026-10-14 06:16 UTC (03:16 ART) para las 03:30. El guard de «creada hoy con hora anterior a la creación» no la excluye. A las 03:36 ART seguía activa, con 0 filas de `plantilla_opciones` desde el 10/10. O la corrida de las 03:30 no la alcanzó, o Meta rechazó el envío y no quedó registro.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Fecha que se muestra | `public.meta_plantillas.created_at`, ISO-8601. Es el alta en Suplai, no la aprobación de Meta. | Es la columna que ya existe y alcanza para ver qué se creó después del fix de envío. | Pedirle a Meta un timestamp que los fields actuales no traen, o agregar `updated_at` vacío. |
| Filtro | Argumentos opcionales `creada_desde` y `creada_hasta`. El día se interpreta en `America/Argentina/Buenos_Aires`. Una sola fecha filtra ese día. Sin fechas, no se recorta. Las que no tienen fila local no entran en un listado filtrado; la respuesta dice `sin_fecha` con esa cuenta solo cuando hay filtro. | El pedido es encontrar las recientes sin cambiar el listado de siempre. | Filtrar en el modelo después de bajar toda la WABA y tirar las viejas en silencio. |
| Lectura del jsonb | Una función, la misma que `_coerce_dynamic_params` de `routers/agenda.py`: hasta 32 `json.loads` mientras el valor sea `str`, y al final tiene que ser `list`. La usan `_variables`, el sender (`variable_columns`, `dynamic_params`, `carousel_config`) y el listado de agendas. | El listado itera el texto. El sender, con un solo `loads`, convierte un string residual en `[]` y manda la plantilla sin parámetros. La #348 ya tiene `dynamic_params` doble-encoded. | Arreglar solo `_variables`. El cron seguiría pudiendo vaciar el mapeo. |
| Si no se puede decodificar | Esa agenda no se envía en esa corrida. `ultimo_resultado.motivos` dice que el mapeo no es una lista. No se manda con parámetros vacíos. | Un `[]` forzado hace que Meta rechace cada comercio de una plantilla con `{{1}}` y no queda rastro. | Mandar igual. Es el comportamiento de hoy cuando el `loads` no alcanza. |
| `motivo_rechazo` | `listar_envios` usa `explicar_motivo_rechazo`. `NONE` y vacío pasan a null. | El listado de plantillas ya lo hace. El de agendas muestra un rechazo que no existe. | Dejar `"NONE"` y documentarlo en la receta. |
| Aislamiento | `try` por agenda y `try` por comercio. Un error se anota y se sigue. | Hoy una excepción corta el tenant. La prueba de un solo contacto en Campi no puede llevarse puesta la corrida, y un comercio malo no puede frenar a los demás. | Best effort solo dentro del `for` de comercios, dejando el `for` de agendas como está. |
| Qué es fallo y qué es omisión | Sin teléfono, o duplicado en la misma corrida: `omitidos`. Error de Meta o excepción al armar el mensaje: `fallidos`, y se sigue. | El usuario pidió mandar a todos los que se pueda y reportar los malos. Un teléfono vacío no es un rechazo de Meta. | Contar el teléfono vacío como fallo de la plantilla. |
| Dónde se ve el reporte | Columna nueva `{schema}.agenda.ultimo_resultado` jsonb. `listar_envios` la devuelve. Tope de 20 motivos, cada uno `{cliente_id, motivo}`. | El conector ya mira ese listado para saber si la agenda sirve. El log de Railway no lo lee Claude. | Insertar el fallo en `envios_plantillas`. Esa tabla es el envío aceptado por Meta (spec 070) y `metricas_whatsapp` la cuenta. |
| Puntual que falló | El mismo día no se apaga ni se le pone `enviado_at`. La corrida siguiente reintenta. Al día siguiente `_apagar_puntuales_vencidas` la apaga igual que ahora. El `ultimo_resultado` queda. | La #368 y la #370 se apagaron solas sin haber salido, y no había forma de ver el error. Reintentar al día siguiente un feriado ya pasado manda el mensaje tarde. | Dejarlas activas hasta que alguien las apague. |
| Recurrente con algún envío | Si hubo al menos un `enviado`, se avanza `proxima_fecha_envio` como hoy. Los fallidos van en `ultimo_resultado` y no se reintentan al día siguiente. | Si no se avanza, mañana se le vuelve a escribir a quien ya recibió. | Reintentar solo los `cliente_id` fallidos. Hace falta otra tabla de pendientes. |
| Recurrente con cero envíos y algún fallo | No se avanza `proxima_fecha_envio`. Sigue activa. El mismo día las corridas siguientes reintentan; al día siguiente la query de día de semana ya no la toma. | Es el mismo criterio que hoy cuando todos los HTTP fallan, más el reporte. | Avanzarla igual. El lunes que no salió no se recupera, y el reporte quedaría como si la corrida hubiera cerrado bien. |
| Histórico del 12 y 13 | No se reenvía. | Esas fechas ya pasaron. La #368 era un feriado. Reactivarlas manda el mensaje fuera de día. | Un script que les ponga `activo = true` y `fecha_programada = hoy`. |
| Backoffice | No se toca la UI. Si el API de agendas pasa por el mismo coerce, hereda el decode. No es criterio de esta entrega. | El pedido es usar las agendas desde el conector. | Arreglar la pantalla de agendas del backoffice en el mismo PR. |

### Forma de `ultimo_resultado`

```json
{
  "cuando": "2026-10-14T03:30:00-03:00",
  "enviados": 0,
  "fallidos": 1,
  "omitidos": 0,
  "motivos": [
    {"cliente_id": 64296, "motivo": "texto que devolvió Meta o la excepción"}
  ]
}
```

`cuando` es el inicio de la corrida en `America/Argentina/Buenos_Aires`. Si los fallidos son más de 20, `motivos` trae 20 y `motivos_recortados` es true. El motivo se recorta a 300 caracteres. No lleva teléfono, nombre ni razón social.

### `listar_plantillas`

Cada ítem suma `created_at`. La firma de la tool suma `creada_desde` y `creada_hasta`, los dos opcionales. La descripción larga de `mcp_server/descripciones.py` dice que están y que `motivo_rechazo` null significa que Meta no la rechazó. La descripción corta del decorador no hace falta cambiarla: el admin publica la de `descripciones.py`.

---

## Alcance

### Incluido

- `created_at` y el filtro de fechas en `listar_plantillas`.
- Coerce compartido de jsonb string, usado por el listado de agendas y por el sender.
- `motivo_rechazo` null cuando el valor es `NONE`.
- Aislamiento por agenda y por comercio, y `ultimo_resultado` en `listar_envios`.
- Tests del coerce, de la clasificación, del filtro de fechas y de que un fallo no corta al siguiente.

### Fuera de alcance

- Fecha de aprobación o rechazo en Meta, y una columna `updated_at`.
- Reenviar las agendas del 12/10 y del 13/10, ni cambiarles `activo`.
- Pantallas del backoffice.
- Contar los fallos dentro de `metricas_whatsapp` o de `envios_plantillas`.
- Reintentar al día siguiente solo los comercios que fallaron.
- Cambiar la ventana de 30 minutos ni el cron de 15.

---

## Orden de implementación

| Orden | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `suplai-platform` | `feat/mcp-zonas-escritura` | Este spec. |
| 2 | `backend-supabase` | `feat/mcp-zonas-escritura` | Migración de `ultimo_resultado`. Después el coerce y el listado. Después el sender. Los tests van con cada paso. |

El plugin de Claude no cambia: la tool sigue llamándose `listar_plantillas` y `listar_envios`.

---

## Migración de base de datos

`ALTER TABLE {schema}.agenda ADD COLUMN IF NOT EXISTS ultimo_resultado jsonb;`

En cada schema activo, y en el template que clona tenants nuevos (`install` / `LIKE` no copia columnas agregadas después: el alta tiene que incluir la columna, igual que el resto de `agenda`).

No toca `clients`. No se dropean `v_cartera` ni `v_prospectos`.

Rollback: `ALTER TABLE {schema}.agenda DROP COLUMN IF EXISTS ultimo_resultado;`. El sender deja de escribir el reporte. Los envíos no dependen de esa columna para salir.

Riesgo: bajo. La columna nace null. Una corrida anterior no se reescribe.

No hay backfill de las agendas que ya fallaron: no hay motivo guardado para inventarlo.

---

## Plan de prueba en CI/CD

En `backend-supabase`, junto a `tests/test_mcp_plantillas_agendas.py` y los tests del sender:

- `_variables('["nombre"]')` es `["nombre"]`. `_variables('[]')` es `[]`. Un doble `json.dumps` de `["nombre"]` también es `["nombre"]`. Un texto que no es JSON es lista vacía y el sender no dispara el HTTP de esa agenda.
- Clasificar `["nombre"]` con cuerpo `Hola {{1}}` y estado `APPROVED` da `usable_en_agenda` true. Clasificar el string `'["nombre"]'` sin coerce da el bug; el test fija el coerce, no el bug.
- `explicar_motivo_rechazo("NONE")` es null, y el armado de ítem de agenda usa ese null.
- `listar_plantillas` con fechas deja afuera una plantilla cuya `created_at` local está fuera del rango, y conserva una de adentro. Sin fechas, no filtra.
- Sender con dos comercios: el primero hace fallar `send_template_message`, el segundo se llama igual. `ultimo_resultado.fallidos` es 1 y `enviados` es 1. `proxima_fecha_envio` avanza.
- Sender con una sola agenda que lanza antes del HTTP: la agenda siguiente igual se procesa.
- Los checks de plantillas, agendas y `agenda_sender` que ya existen quedan verdes.

---

## Plan de prueba humana

Backend en `8000`, MCP en `8100`. Tenant Campi, schema `del_corro`. No hace falta el backoffice. No reactivar la #368 ni la #370.

1. `listar_plantillas` sin fechas. `plantilla_opciones` trae `created_at` y `variable_columns: ["nombre"]`. `motivo_rechazo` no es `"NONE"`.
2. `listar_plantillas` con `creada_desde` y `creada_hasta` cubriendo el 2026-10-13 (el día del fix de idioma y ejemplos). Aparecen las plantillas creadas ese día y no una vieja como `plantilla_opciones` (alta local 2026-06-25).
3. `listar_envios` con `solo_activas=false`. La #371 y la #348 tienen `usable_en_agenda` true si Meta sigue en `APPROVED`. El motivo ya no lista caracteres. `motivo_rechazo` es null.
4. Crear una puntual nueva, para un solo cliente de prueba, con hora dentro de la ventana de 30 minutos que todavía no cerró (la corrida es cada 15 minutos). `previsualizar_agenda` y, después de confirmar, `listar_envios` coinciden en usable.
5. Esperar la corrida. `listar_envios` muestra `ultimo_resultado`. Si Meta aceptó, `enviados` es 1. Si rechazó, `fallidos` es 1, el motivo es el texto de Meta, la agenda sigue activa y `enviado_at` es null.
6. Para el best effort, el test de CI del punto anterior es la prueba de dos comercios. En Campi no se arma una audiencia grande.
