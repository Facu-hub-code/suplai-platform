# 105 — Conector: apagar sin trabas, listar lo que envía, y completar secuencias

**Estado:** Implementado. Migración 158 y script de higiene de `demo` aplicados el 2026-10-11. Sin merge.  
**Fecha:** 2026-10-11  
**Repos:** `backend-supabase` (tools, sender, migración del check, script manual de `demo`). Las recetas viven en ese repo.  
**Rama sugerida:** `feat/mcp-crud-higiene`  
**Relaciona:** [104](./104-mcp-agendas-plantillas-deprecar-estrategias.md), [097](./097-claude-mcp-grupos-agendas.md)

---

## Objetivo

Después del spec 104 se puede editar y borrar una agenda, pero apagar una fila rota o duplicada sigue fallando, el listado esconde envíos que están activos, y una secuencia se puede confirmar sin ver el texto. Este spec cierra ese CRUD y deja un script, aparte de la migración, para limpiar las filas de prueba de `demo`.

### Métricas de éxito

- `previsualizar_editar_agenda` con `activo=false` y sin otro cambio apaga la agenda aunque la plantilla no exista, no esté aprobada o haya otra igual.
- Una agenda inactiva no bloquea la edición de otra. Dos activas iguales sí: para salir del círculo hay que apagar una, y ese apagado no se frena.
- `previsualizar_agenda` con `grupo_id` no descarta en silencio un nombre o unos días distintos. Avisa y manda a `previsualizar_editar_grupo`.
- Una puntual deja de estar activa el día después de su fecha, o en cuanto quedó enviada. Deja de bloquear el borrado del grupo.
- `listar_envios` con el filtro por defecto muestra toda agenda activa, tenga o no grupo, esté o no vencida, y trae nombre de plantilla, estado de Meta y si es usable.
- Confirmar un borrado de grupo cuya foto ya no coincide con la base se niega y pide otro preview.
- `listar_plantillas` trae el motivo de rechazo de Meta. Un estado `REJECTED` no se describe como “todavía no aprobada”.
- Una secuencia con mensaje en blanco no genera preview. Crear y borrar muestran el texto. Se puede prender o apagar con `previsualizar_editar_secuencia`.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Apagar | Si `activo=false` y no cambian plantilla, tipo, días, hora ni fecha, el preview y el confirmar solo hacen `UPDATE activo = false` | La 12 no se puede apagar hoy: la plantilla no está en `meta_plantillas` y la validación corta antes. Apagar es lo que desbloquea el grupo | Seguir validando “por las dudas”. Impide corregir la fila que justamente está mal |
| Duplicados | Solo una agenda **activa** ocupa el horario. La inactiva se menciona en `avisos`, no frena | La 21, inactiva, frena a las 22–25. La 18 y la 19, las dos activas, se frenan entre sí. Apagar una de las activas tiene que ser el camino de salida | Borrar la inactiva automáticamente. Puede ser un borrador que el operador quiere conservar |
| Editar grupo | Tool nueva `previsualizar_editar_grupo` (`nombre`, `dias_visita`, `etiqueta_ids`, `lista_precios_id`, `vendedor_id`, `geo_zone_id`, `dynamic_condition`). Si `previsualizar_agenda` trae `grupo_id` y alguno de esos campos **difiere** del grupo guardado, error con `campo` y el nombre de la tool | Hoy `_resolver_destino` con `grupo_id` devuelve la fila y tira el resto. El modelo cree que renombró | Meter el update del grupo en el mismo preview de la agenda. Un confirmar escribiría dos cosas y el rollback queda a medias |
| Puntual vencida | Al marcar `enviado_at`, el sender también pone `activo=false`. Al empezar la corrida, apaga las puntuales con `fecha_programada` anterior a hoy en `America/Argentina/Buenos_Aires` | Siguen `activo: true` después de enviarse, el listado las esconde y el borrado del grupo las trata como vigentes. El reintento del mismo día se conserva: la query actual sigue siendo `fecha <= hoy` y `enviado_at` nulo | Sacarlas solo del bloqueo de borrado y dejarlas activas. El listado y el borrado dirían cosas distintas |
| Listado | Con `solo_activas=true` (el default) no se aplican `incluir_sin_grupo` ni `incluir_vencidas`. Esas flags siguen valiendo cuando se pide el histórico | La 5 está enviando y no aparece. Una puntual vencida y activa tampoco, y sí bloquea el grupo | Cambiar el default de las dos flags a true para siempre. El histórico inactivo se volvería enorme |
| Plantilla en el listado | Join a `public.meta_plantillas` del mismo tenant. Campos `plantilla`, `estado_plantilla`, `usable_en_agenda`, `motivo_no_usable`. Si el id no está en la tabla, usable false y motivo “La plantilla no está en esta distribuidora.” | Hoy solo vuelve el uuid. La 12 y `prueba_variables` se descubren cruzando a mano | Otra llamada a `listar_plantillas` por cada agenda. Son N lecturas a Meta |
| Preview viejo | El payload de borrar grupo guarda la lista ordenada de ids de agenda. Al confirmar, si el grupo no está o la lista cambió, `valido: false` y hay que previsualizar de nuevo. No se borra | El QA confirmó un grupo después de que la agenda ya no existía. El preview describía otra foto | Borrar igual si no quedaron activas. El operador confirma un texto que ya no es cierto |
| Agenda 12 | No es una plantilla viva de otro tenant. `demo.agenda` id 12 guarda `ea58f489-e238-489c-aed6-2b9d05e6d473` y esa fila no está en `public.meta_plantillas` | El join da `template_name` nulo y `schema_duena` nulo. El agujero es que el alta acepta cualquier uuid, no que hoy haya un cruce de WABA | Tratarla como fuga entre tenants y rotar credenciales. No hay fila ajena que leer |
| Aislamiento | Crear o cambiar la plantilla de una agenda exige que `meta_plantillas.tenant_id` sea el de la distribuidora. El apagado solo no mira esa tabla | Sin esa chequeo el uuid colgado se puede volver a escribir | Una FK. `meta_plantillas` es de `public` y la agenda es por schema; la FK no expresa el tenant |
| Motivo de rechazo | `listar_plantillas` copia `rejected_reason` de Meta al campo `motivo_rechazo`. Si el estado es `REJECTED`, `motivo_no_usable` dice “Meta la rechazó” y agrega ese texto. `PENDING` sigue con “Meta todavía no la aprobó” | El QA vio `test_crud_mcp` rechazada en segundos y el conector decía que faltaba aprobar | Guardar el motivo solo en la fila local. El listado ya lee Meta en vivo; la columna local puede ir atrasada |
| Idioma | Las plantillas creadas por el conector salen en `es_AR` | Las de sistema de la misma cuenta están en `es_AR`. `es` es otro idioma para Meta y entra a otra revisión | Dejar `es`. Es lo que acaba de rechazar la prueba, y no coincide con el resto de la WABA |
| Uso | Si el nombre ya cae en Reactivación, Prospección, Campañas o Avisos, se queda esa etiqueta. Si no, `UTILITY` es Contacto y `MARKETING` es Promoción. `Otras` queda para lo que no tiene categoría | `uso_de` mira el nombre. `test_crud_mcp` no matchea ninguno y el objetivo `contactar` se pierde, aunque la categoría guardada sea `UTILITY` | Mapear todo `UTILITY` a Contacto. Las de sistema de un pedido dejarían de figurar como Avisos |
| Campo del error | “No encuentro esa plantilla” lleva `campo: "template_name"` | Hoy el campo sale null y el resto de los rechazos sí nombran la clave | Un mensaje más largo sin campo. El modelo no sabe qué argumento corregir |
| Mensaje de secuencia | `mensaje.strip()` vacío es `AccionError` con `campo: "mensaje"`, antes de armar el preview | El modelo acepta la acción con el texto ya recortado a `""`. La guía lo llama error común y el servidor no lo es | Rechazarlo solo en el confirmar. El preview ya se mostró como válido |
| Texto en el preview | Crear y borrar devuelven `mensaje` (y, si existe, `mensaje_con_carrito`). La guía ya pide mostrarlo | El operador confirma un borrado o un alta sin ver la frase | Confiar en que el modelo recuerda el argumento. En el borrado ni siquiera lo recibió |
| Secuencia 102 | No se toca. Es el seed `followup_fin_de_dia_16hs`: `trigger_after_seconds = 0` porque dispara a las 16:00 (`daily_time_equals`), no por silencio. En `demo` está `enabled: true` | El mínimo de 60 segundos es de `previsualizar_secuencia`, que arma un seguimiento `always_true`. El backoffice y el seed pueden tener espera 0 | Forzar 60 en las filas viejas. Rompe el disparo de las 16:00 |
| Editar secuencia | `previsualizar_editar_secuencia` cambia `enabled` y `trigger_after_seconds`. Muestra el mensaje y las condiciones. Si hay `daily_time_equals`, la espera puede ser 0. Si no, sigue el rango 60–86400 | Falta prender y apagar. Reescribir el cuerpo es otro producto: la guía dice borrar y crear | Editar también el texto en esta entrega. El QA pidió como mínimo el interruptor y la espera |
| Limpieza de `demo` | Script SQL manual, una vez, no va dentro de la migración del check | Borrar agendas en la migración las vuelve a borrar si alguien replaya el archivo, y mezcla DDL con datos de un solo tenant | Hacerlo solo con las tools nuevas. Parte de la higiene (la 12, las duplicadas) es lo que las tools hoy no dejan apagar |

---

## Alcance

### Incluido

- Atajo de apagado, duplicados solo activos, edición de grupo, puntuales que se apagan, listado con plantilla y sin esconder activas.
- Confirmación de borrado que compara la foto del preview.
- Chequeo de que la plantilla pertenece al tenant, salvo en el apagado.
- `motivo_rechazo`, texto de `REJECTED`, idioma `es_AR`, uso por categoría, `campo: template_name`.
- Mensaje obligatorio y visible en secuencias, y edición de `enabled` y espera.
- Recetas `grupos-y-agendas`, `plantillas` y `secuencias`.
- Script manual de higiene sobre `demo`, con la tabla de más abajo.

### Fuera de alcance

- Reescribir el cuerpo de `prueba_variables` o `hola_cliente_pedido` para asociarles columnas. Se apagan o se borran las agendas que las usan.
- Borrar en Meta los pares casi iguales (`promo_bebidas` / `test_carousel`, demos v1 y v2, holiday v4 y v5, `quienes_no_responden_3` / `no_responden_2`). `promo_bebidas` sigue referenciada por agendas que se conservan. El aviso de cuerpo parecido del spec 104 alcanza. Borrarlas es una decisión en el panel, de a una.
- Apagar o reescribir la secuencia 102.
- Borrar la agenda 5. Es recurrente, sin grupo, al cliente 16, jueves 14:00, plantilla `presentacion_agente`. El producto ya permite agenda de un cliente. El listado la va a mostrar con el aviso de “sin grupo”.
- Estrategias. Siguen como en el spec 104.
- Editar el texto de una secuencia o de una plantilla ya aprobada.

---

## Higiene de `demo` (script manual)

Se corre una vez, después de leer el resultado, no al deployar. Cada `DELETE` va con el `id` y la firma, para no llevarse una fila nueva que reutilice el número.

| Qué | Acción | Por qué |
|---|---|---|
| Agenda 12, grupo 8 “Test 3 (Martes)” | Borrar | Uuid de plantilla inexistente. Manda los miércoles y el grupo visita los martes. No queda nada que alinear |
| Grupo 5, martes y viernes 09:00, `hola_cliente_pedido` | Borrar 13, 14 y 15. Dejar la 16 y ponerla `activo=false` | Son cuatro iguales. La que queda usa una plantilla sin columnas |
| Grupo 10, lunes a viernes 09:00, `promo_bebidas` | Borrar 19. Dejar la 18 activa | Par activo. Se conserva la de id menor |
| Grupo 10, lunes, miércoles y viernes 09:00, `promo_bebidas` | Borrar 21, 23, 24 y 25. Dejar la 22 activa | La 21 está inactiva y hoy bloquea el duplicado. Las otras tres repiten a la 22 |
| Grupo 10, `prueba_variables` | Borrar 30. Poner `activo=false` en 27 y 28 | 27 y 30 son el mismo horario. 28 es otro (lunes y sábado) pero la plantilla no se puede llenar |
| Agenda 56, grupo 7 | `activo=false` | `prueba_variables`, y además envía los martes con visita los lunes. No se corrige el día mientras siga apagada |
| Grupos 34, 35 y 36 | Borrar solo si la audiencia en vivo es 0 y no tienen agendas | Etiquetas 23, 24 y 25. Si alguien cargó esas etiquetas, el script no los toca |
| Agenda 5 | No tocar | Un cliente, sin grupo. Ver alcance |

El script primero `SELECT` y aborta si alguna firma no coincide (otro `template_name`, otro horario, `activo` distinto del esperado).

Aplicado el 2026-10-11 en Suplai-east. Quedaron borradas 12, 13, 14, 15, 19, 21, 23, 24, 25 y 30. Quedaron apagadas 16, 27, 28 y 56. Siguen activas 5, 18 y 22. Los grupos 34, 35 y 36 no se borraron: las etiquetas 23, 24 y 25 tienen clientes.

---

## Orden de implementación

1. `backend-supabase`, rama `feat/mcp-crud-higiene` desde `origin/main`.
2. `sql/158_mcp_preview_editar_grupo_secuencia.sql`: el check de `mcp_accion_previews.tipo` suma `editar_grupo` y `editar_secuencia`. El resto de los tipos queda igual, incluido `estrategia`.
3. Código de agendas, plantillas, secuencias y sender. Recetas en el mismo PR.
4. Tests.
5. Con el backend desplegado, correr el script manual en `demo` y pegar el `SELECT` de control en el PR.

El plugin no cambia de tool nueva salvo que la skill de agendas todavía diga que el nombre del grupo se manda en `previsualizar_agenda`. Si es así, una línea en el mismo estilo del PR 5 del plugin.

---

## Migración de base de datos

`sql/158` solo reescribe el `CHECK`. No borra filas ni cambia columnas.

Rollback: volver al check de `sql/157`. Si ya hay previews `editar_grupo` o `editar_secuencia`, hay que consumirlos o borrarlos antes, porque el check viejo no los acepta.

La higiene de `demo` es otro archivo, corrido a mano, con transacción y el `SELECT` de guarda. No forma parte del runner de migraciones.

---

## Plan de prueba en CI/CD

- Apagar una agenda cuya plantilla no está en `meta_plantillas` devuelve preview y el confirmar deja `activo=false` sin llamar a Meta.
- Una inactiva con la misma firma no entra en `_agendas_identicas` cuando la otra se edita. Dos activas sí, excepto en el atajo de apagado.
- `previsualizar_agenda` con `grupo_id` y `dias_visita` distintos responde `valido: false` y nombra `previsualizar_editar_grupo`.
- El sender, al completar una puntual, escribe `enviado_at` y `activo=false`.
- `listar_agendas` con defaults incluye `grupo_id` nulo y una puntual con fecha pasada si `activo` es true, y trae `plantilla`.
- Confirmar borrado de grupo con una lista de ids distinta a la del payload no ejecuta el `DELETE`.
- `clasificar_plantilla` con estado `REJECTED` no contiene “todavía no la aprobó”.
- `uso_de` más la categoría: un nombre desconocido con `UTILITY` es Contacto.
- `previsualizar_secuencia` con `"   "` no guarda preview.
- El preview de borrar secuencia incluye el mensaje.
- El check de `sql/158` cubre los tipos del confirmar.

---

## Plan de prueba humana (antes del PR)

Backend en `8000`. Conector reconectado. Tenant `demo`.

1. `previsualizar_editar_agenda` sobre la 12 con `activo=false` y nada más. Tiene que previsualizar. No confirmar todavía si el script de higiene la va a borrar: alcanza con ver que ya no rechaza la plantilla.
2. `previsualizar_editar_agenda` sobre la 22 (o la 18) cambiando solo la hora, con la gemela todavía activa. Tiene que nombrar a la otra y no guardar. Repetir el llamado sobre una de las dos con `activo=false`: ahí sí preview.
3. `previsualizar_agenda` con `grupo_id` de un grupo existente y `dias_visita` distintos. El error nombra `previsualizar_editar_grupo`.
4. `listar_envios` sin flags extra. La agenda 5 aparece, con aviso de sin grupo, y cada fila trae el nombre de la plantilla.
5. Previsualizar el borrado de un grupo sin agendas activas, borrar una agenda inactiva por otro lado, confirmar el primer preview. Tiene que negarse.
6. `listar_plantillas`: `test_crud_mcp` muestra `motivo_rechazo` y un `motivo_no_usable` que dice que fue rechazada.
7. `previsualizar_secuencia` con mensaje `"   "`. Respuesta `valido: false`, sin `preview_id`.
8. `previsualizar_eliminar_secuencia` de una secuencia cualquiera. La respuesta incluye el texto.
9. `listar_envios` con `entidad=secuencia`. La 102 se ve con disparo de horario y espera 0, y sigue habilitada.
