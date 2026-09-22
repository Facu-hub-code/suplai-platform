# 080 — Supervisor virtual: agendas Pareto y seguimiento en audio

**Estado:** Borrador  
**Fecha:** 2026-09-22  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `agente-conversacional-multi_tenant`, `product-management-app`  
**Ramas sugeridas:** `feat/supervisor-virtual-agendas`  
**Relaciona:** Pareto de la [077](./077-metricas-pareto-y-label-semana.md) (`en_franja_pareto`, `monto_en_riesgo`). Agenda de clientes en `{schema}.agenda` (`origen` ya existe; el destino es grupo **o** cliente, nunca los dos). Podcast actual en `field_podcast_jobs` (único `(vendedor_id, fecha)`) y envío en `services/field_podcast/`. El orden de PDV, si está, es el de la [078](./078-field-ruta-sugerida.md). El reporte de ejecución del equipo es la [079](./079-vendedores-herramientas-y-reporte.md), aparte de estas agendas.

---

## Contexto

El supervisor humano se va el día persiguiendo vendedores y decidiendo a qué comercios escribir. El producto ya tiene las dos puntas sueltas: un briefing de audio a la mañana, y una franja Pareto de clientes en caída. No hay una agenda que las use, ni un cupo que limite cuántos clientes se contactan.

### Por qué el audio de la mañana no llega (el_gigante)

No es el TTS. En `el_gigante.field_podcast_jobs`, los últimos días: 27 jobs `FAILED` con `Credenciales WhatsApp no configuradas` y 18 `READY` sin `SENT`.

`send_job` pide `whatsapp.long_live_token` y `whatsapp.phone_id` en `public.tenant_secrets`. Ese tenant no tiene secretos con nombre WhatsApp, así que el envío falla antes del teléfono. La ventana de `dispatch_ready_jobs` además corta a las 10:00 (`after_send_window`): un `READY` de la mañana no se reintenta a la tarde.

Los 9 vendedores activos tienen `telefono` cargado, y los nueve son de 1 o 2 dígitos. El sender solo salta el teléfono vacío. Con credenciales, Meta rechazaría igual esos números.

Este spec no carga el token ni reescribe teléfonos. Sí deja de insistir: teléfono con menos de 10 dígitos queda `SKIPPED` con error `Teléfono de vendedor inválido`, sin reintento. El envío al vendedor pasa a ser una plantilla con botón, que abre la ventana de 24 h cuando la persona toca.

---

## Objetivo

Dos agendas, con cupos distintos.

1. **Clientes.** Desde Métricas, con los filtros de la pantalla, armar una agenda recurrente a la franja Pareto. Cada corrida rearma la audiencia. Si no entran en el cupo diario de reglas de negocio, entran los de mayor `monto_en_riesgo`.
2. **Vendedores.** Una agenda especial, 1, 2 o 3 veces en la jornada, manda una plantilla fija con el botón **Escuchar seguimiento**. El toque hace que el agente mande un audio corto de tareas y objetivos. El audio no sale solo a las 06:30.

### Métricas de éxito

- Con la franja más grande que el cupo, se agenda exactamente el cupo, y son los de mayor monto en riesgo.
- Al día siguiente la audiencia puede cambiar sin que nadie edite el grupo a mano.
- Con la agenda de vendedor prendida, a la hora configurada sale la plantilla y no el audio. El audio sale después del botón, en menos de 90 segundos de guion, y solo con números del dossier.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Pareto | El de la spec 077, ya calculado: clientes en caída de frecuencia, techo 20% por ticket, ordenados por `monto_en_riesgo` | Es el filtro que el supervisor ve en Métricas. Otro corte (“top 50 por facturación”) es Prioridad 1, que ya puede estar aplicado como filtro de la pantalla. | Un índice nuevo que sume las cuatro alarmas: no está definido el peso de cada una y duplicaría la 077. Top 75 de facturación: mide tamaño, no plata que se está yendo. |
| Audiencia cliente | Una sola agenda recurrente por tenant, `origen = 'pareto_supervisor'`, más `filtro_json`. Antes de cada envío, el sender vacía y rellena **ese** grupo con la franja del momento, recortada al cupo. El `origen` vive en la agenda; el grupo solo guarda miembros | `{schema}.agenda` ya manda plantillas a un grupo. Reescribir los miembros justo antes conserva “agenda recurrente” y no congela la lista del día en que se creó. Una sola agenda evita dos refrescos pisándose el mismo grupo. | Grupo estático al crear: a la semana siguiente persigue a quien ya volvió a comprar. Varias agendas Pareto: el segundo refresh pisa al primero. Calcular la franja dentro del sender sin grupo: un segundo camino de audiencia al lado de `grupo_id`. |
| Ventana de la franja | Se guarda `ventana_dias` (largo del rango de fechas que había en Métricas al crear). Cada corrida usa `[hoy - ventana_dias, hoy]` más vendedor, zona, etiquetas y Prioridad 1 guardados | Una agenda recurrente no puede quedar atada al calendario que el operador tenía abierto el martes. | Reusar las fechas absolutas del alta: al mes el rango quedó en el pasado. |
| Cupo clientes | `reglas_negocio.outreach.mensajes_clientes_por_dia` (entero ≥ 1). Se lee en cada envío, no se copia al crear la agenda | El dueño cambia el cupo en reglas y la próxima corrida obedece. Es el cruce “Pareto × mensajes habilitados por día”. | Cupo fijo en la agenda: hay que acordarse de editarlo en los dos lados. Sin cupo: la franja de un tenant grande dispara un HSM por cliente. |
| Sin cupo configurado | La herramienta de Métricas no crea la agenda y explica que falta el número en reglas de negocio | Un default alto manda de más; un default de cero no manda y parece roto. | Default 50: el dueño no lo eligió. |
| Plantilla de clientes | La elige el supervisor al crear la agenda, entre las de Meta ya aprobadas. Días y hora, igual que el gestor de agenda | El mensaje al comercio es una campaña, no un texto fijo del producto. | Plantilla única de sistema: cada distribuidora habla distinto a sus clientes. |
| Cupos separados | El cupo de clientes no cuenta los envíos a vendedores | Son dos presupuestos. El seguimiento del equipo no tiene que competir con la campaña a los PDV. | Un solo número para los dos: el día que la franja llena el cupo, el vendedor se queda sin audio. |
| Agenda vendedor | Config en `reglas_negocio.field_seguimiento`: `enabled`, `veces_por_dia` (1, 2 o 3), `horarios` (array de `HH:MM`, largo = veces). Defaults al prender: `["08:30"]`, `["08:30","13:00"]` o `["08:30","13:00","17:00"]` | Es una regla de la jornada, no un grupo de clientes. Meter vendedores en `agenda` choca con el check `grupo_id` XOR `client_id`. | Filas en `{schema}.agenda` con los dos destinos nulos: hay que romper ese check y el sender de clientes. |
| Opt-in | Con `field_seguimiento.enabled = true`, ese tenant no empuja el audio de las 06:30. El cron de las horas configuradas manda solo la plantilla. Con `enabled` apagado, el podcast actual sigue igual | Otros tenants pueden seguir con el push. El Gigante deja de depender de la ventana de 24 h para oír el audio. | Apagar el push en todos los tenants el día del merge: corta un briefing que otros sí reciben. |
| Plantilla vendedor | Una sola, de sistema, nombre `field_seguimiento`, idioma `es_AR`. Cuerpo: `Hola {{1}}. Hay un seguimiento de tu día a la {{2}}.` Botón de respuesta rápida con texto exacto `Escuchar seguimiento`. `{{1}}` nombre, `{{2}}` `mañana` / `mediodía` / `tarde` según el slot | El botón tiene que llegar al webhook como ese texto. El parser ya lee `button` y `button_reply`. Una plantilla por vendedor no entra en los límites de Meta. | Audio adjunto en la plantilla: vuelve al problema de generar el archivo antes de saber si lo van a oír, y a las 13:00 estaría viejo. |
| Quién arma el audio | El canal seller, determinístico, si el texto normalizado (minúsculas, sin acentos) es `escuchar seguimiento`. Llama al backend. El modelo no redacta números | El guion tiene que salir del dossier. Un LLM suelto inventa puntos y objetivos. | Dejar que el prompt del vendedor “note” el botón: a veces contesta con texto y no manda audio. |
| Cuándo se genera | En el toque, no de madrugada. Slot = el horario de esa agenda cuya hora local ya pasó y es el más reciente. Primer toque del slot: dossier + TTS + envío. Otro toque del mismo slot el mismo día: reenvía el archivo ya generado | A las 13:00 las tareas pendientes no son las de las 08:30. Precalcular los tres audios a la noche miente en el segundo y el tercero. | Cron que sube el audio junto con la plantilla: otra vez la ventana de 24 h, y el vendedor recibe el audio sin haberlo pedido. |
| Job | Se reusa `field_podcast_jobs` con columna `slot` (`manana`, `mediodia`, `tarde`). Único `(vendedor_id, fecha, slot)` | Ahí ya están el audio, el guion, el bucket y el evento de conversación. | Tabla paralela de seguimientos: dos pipelines de TTS. |
| Teléfono corto | Menos de 10 dígitos, o vacío: `SKIPPED`, error `Teléfono de vendedor inválido`, sin llamada a Meta y sin reintento | En El Gigante los teléfonos son códigos de 1–2 dígitos. Reintentar solo llena `FAILED`. | Mandar igual y leer el error de Graph: gasta la ventana de reintentos y no dice que el dato está mal. |
| Largo del audio | 140–180 palabras (unos 60–90 segundos). Sin listar SKU | En la calle no entra el guion de 3–5 minutos (500–800 palabras) de la spec 012. El detalle está en Field. | Leer la ruta completa: es la densidad que este pedido vino a evitar. |
| Qué PDV nombra | Hasta 3. Primero, de la ruta de hoy, los que están en la franja Pareto de ese vendedor, por `monto_en_riesgo`. Si faltan, completa con pendientes en `orden_sugerido` de la spec 078. Si la 078 no está, completa por nombre | El audio invita a abrir la app en los comercios que más duelen, no en el primero del alfabeto. | Los 3 de mayor facturación histórica: otra vez tamaño, no riesgo. |
| Link | `https://field.suplaisales.com/{schema}?wp={telefono}` al cierre de cada audio | Es el deep link que Field ya usa. El audio no reemplaza la ficha. | Link a un PDV profundo: el teléfono de 1–2 dígitos ni siquiera loguea, y el orden de la ruta lo mira él en la app. |

Franjas del cuerpo de la plantilla: hora &lt; 12 → `mañana`; hora &lt; 16 → `mediodía`; si no, `tarde`. Esas mismas etiquetas son el `slot` (`manana`, `mediodia`, `tarde`). Dos horarios el mismo lado del corte (08:00 y 11:00) no están permitidos: el alta de la regla responde 422 si dos horarios caen en el mismo slot. Con eso el único `(vendedor_id, fecha, slot)` alcanza para 1, 2 o 3 envíos.

---

## Alcance explícito

### Incluido (v1)

- Clave `reglas_negocio.outreach.mensajes_clientes_por_dia`.
- Clave `reglas_negocio.field_seguimiento` (`enabled`, `veces_por_dia`, `horarios`).
- Herramienta en Métricas: “Armar agenda de la franja”. Pide plantilla aprobada, días y hora. Hay una sola agenda activa con `origen = 'pareto_supervisor'` por tenant. La primera vez crea el grupo `Supervisor — franja Pareto` y la agenda. Si esa agenda ya existe, el alta actualiza filtro, plantilla, días y hora, y sigue usando el mismo `grupo_id`.
- `filtro_json` y `ventana_dias` en `{schema}.agenda`.
- Refresh de miembros del grupo en el sender cuando `origen = 'pareto_supervisor'`, recorte al cupo, orden `monto_en_riesgo` descendente.
- Plantilla `field_seguimiento` y cron de envío de esa plantilla a vendedores activos en los horarios configurados.
- Handler determinístico del botón y generación on-demand del audio.
- `slot` en `field_podcast_jobs` y `SKIPPED` por teléfono inválido.
- Con la agenda de vendedor prendida, no se ejecuta el push de audio de las 06:30 para ese tenant.
- Guion según el slot (abajo).

### Fuera de alcance

- Cargar credenciales de WhatsApp ni corregir teléfonos de `el_gigante` (dato de tenant y de Meta).
- Cambiar la fórmula Pareto de la 077.
- Que el audio liste SKU, deudas o stock.
- Mezclar el cupo de clientes con el de vendedores.
- UI nueva de playback: el evento sigue cayendo en Conversaciones, como el podcast actual.
- Opt-out por vendedor.

---

## Guion del audio

Solo cifras y nombres que estén en el dossier del momento (`dossier_builder`) más la franja Pareto y, si existe, `orden_sugerido`. Si un número no está, esa frase no se dice.

| Slot | Qué dice | Qué no dice |
|------|----------|-------------|
| `manana` | Saludo con el nombre. Cuántas tareas pendientes hay, agrupadas por tipo en palabras (“reactivar”, “reposición”, “mix”). Hasta 3 comercios, como en la decisión de PDV. El objetivo vigente con mayor % y todavía bajo 100, con unidades y meta. Cierre con el link de Field. | SKU, puntos del torneo, lista de la ruta. |
| `mediodia` | Cuántas tareas siguen pendientes desde la mañana. Los mismos 3 comercios si siguen con tarea pendiente; si uno ya se completó, no se nombra y entra el siguiente. El objetivo, igual que a la mañana, con el avance actual. Link. | Repetir la ruta entera. |
| `tarde` | Tareas que siguen sin completar. Brecha del objetivo más cercano (`meta - unidades`, y el %). Link. | Un resumen del día ya cerrado: a esa hora las pendientes importan más que lo hecho. |

Si no hay tareas pendientes, el guion lo dice y deja el link. Si no hay objetivo vigente, omite ese párrafo. Persona, voz e idioma siguen en la config de podcast que ya edita el backoffice.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `backend-supabase` | `feat/supervisor-virtual-agendas` | Migración `slot` + columnas de agenda. Reglas. Refresh Pareto en el sender. Cron de la plantilla. On-demand del audio. Skip de teléfono. Apagar el push de audio si `field_seguimiento.enabled` |
| 2 | `agente-conversacional-multi_tenant` | `feat/supervisor-virtual-agendas` | Match determinístico de `escuchar seguimiento` → endpoint on-demand. Merge después del endpoint |
| 3 | `product-management-app` | `feat/supervisor-virtual-agendas` | Campos en reglas de negocio. Herramienta en Métricas para crear la agenda. La tarjeta Podcast de la spec 079 sigue editando voz y persona |

La 078 no bloquea el merge: sin `orden_sugerido`, el audio completa los 3 comercios por nombre. La 077 sí: sin `en_franja_pareto` y `monto_en_riesgo` la herramienta de Métricas no tiene a quién agrupar.

---

## Migración de base de datos

En cada schema con `field_podcast_jobs`:

```sql
ALTER TABLE {schema}.field_podcast_jobs
  ADD COLUMN IF NOT EXISTS slot text NOT NULL DEFAULT 'manana';

ALTER TABLE {schema}.field_podcast_jobs
  DROP CONSTRAINT IF EXISTS field_podcast_jobs_unique;

ALTER TABLE {schema}.field_podcast_jobs
  ADD CONSTRAINT field_podcast_jobs_unique UNIQUE (vendedor_id, fecha, slot);

ALTER TABLE {schema}.field_podcast_jobs
  DROP CONSTRAINT IF EXISTS field_podcast_jobs_slot_chk;

ALTER TABLE {schema}.field_podcast_jobs
  ADD CONSTRAINT field_podcast_jobs_slot_chk
  CHECK (slot IN ('manana', 'mediodia', 'tarde'));
```

Los jobs ya creados quedan en `manana`. No se reenvían.

En cada schema con `agenda`:

```sql
ALTER TABLE {schema}.agenda
  ADD COLUMN IF NOT EXISTS filtro_json jsonb,
  ADD COLUMN IF NOT EXISTS ventana_dias integer;
```

`origen = 'pareto_supervisor'` usa el valor de texto que ya permite la columna `origen`. Sin backfill de grupos.

`reglas_negocio` es JSON en `public.distribuidoras`: no hay DDL. Ausencia de las claves = cupo sin configurar y seguimiento apagado.

Rollback: volver a único `(vendedor_id, fecha)` solo si no hay dos slots el mismo día; si los hay, hay que borrar los slots extra antes. Dejar de leer `filtro_json` apaga el refresh y la agenda sigue mandando a quien esté en el grupo en ese momento.

Riesgo: el cambio de único en `field_podcast_jobs` es el punto delicado. En tenants con el push viejo, un solo job por día sigue entrando (`slot` default `manana`).

---

## Contrato

Reglas:

```json
{
  "outreach": { "mensajes_clientes_por_dia": 40 },
  "field_seguimiento": {
    "enabled": true,
    "veces_por_dia": 2,
    "horarios": ["08:30", "13:00"]
  }
}
```

`veces_por_dia` distinto del largo de `horarios`, horario repetido, o dos horarios en el mismo slot: 422.

Alta desde Métricas (body):

```json
{
  "meta_plantilla_id": "uuid",
  "dias": ["mon", "tue", "wed", "thu", "fri"],
  "hora": "10:00",
  "filtros": {
    "vendedor_ids": [],
    "zone_ids": [],
    "etiqueta_ids": [],
    "prioridad_1": false,
    "ventana_dias": 30
  }
}
```

Respuesta: `{ "agenda_id", "grupo_id", "cupo", "clientes_en_franja", "clientes_agendados" }`. `clientes_agendados = min(franja, cupo)`.

On-demand (lo llama el agente, no el vendedor):

`POST /{schema}/field/seguimiento/audio` con `vendedor_id` y el teléfono ya resuelto. El backend elige el slot. Respuesta: `{ "job_id", "slot", "status": "SENT" | "SKIPPED" }` y el audio ya salió por WhatsApp, o `SKIPPED` con `error`.

---

## Plan de prueba en CI/CD

Backend:

- Franja de 10 y cupo 3 → el grupo queda con los 3 de mayor `monto_en_riesgo`.
- Cupo mayor que la franja → entran todos los de la franja.
- Franja vacía → el grupo queda vacío y el sender no marca la agenda como fallida.
- Sin `mensajes_clientes_por_dia` → el alta responde 422 y no crea agenda.
- `field_seguimiento` con dos horarios en `manana` → 422.
- Teléfono de 2 dígitos → job `SKIPPED`, el mock de Meta no se llama.
- `enabled: true` → `dispatch_ready_jobs` no manda audio.
- Primer toque del slot genera; el segundo no vuelve a llamar al TTS y reenvía el mismo `audio_path`.
- El armador de guion, con un dossier fijo, no agrega cifras que no estén en el JSON, y el de la tarde no enumera SKU.

Agente:

- Texto `Escuchar seguimiento` (y la variante con mayúsculas o acento en la ó) dispara el endpoint y no pasa por el LLM.
- Otro texto del vendedor sigue el canal de siempre.

Checks del PR en verde. Smoke de migración: un job viejo sigue siendo único con `slot = manana`.

Gap: no hay test de punta a punta con Graph. El mínimo del PR es mock de `send_template_message` y de `send_audio_message`.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000`, backoffice `3000`, agente local apuntando a ese backend. Tenant con Pareto visible (spec 077) y, para el audio, un vendedor con teléfono real de WhatsApp y secretos `whatsapp.long_live_token` / `whatsapp.phone_id`. `el_gigante` hoy no cumple eso: los teléfonos son de 1–2 dígitos y no hay secretos. Conviene probar el audio en un tenant que sí tenga número, o después de cargar esos datos.

1. Reglas de negocio: cupo de clientes en un número chico (por ejemplo 3) y seguimiento en 2 horarios, 08:30 y 13:00.
2. Métricas, con Prioridad 1 si se quiere achicar el universo: “Armar agenda de la franja”. Elegir una plantilla aprobada. La respuesta dice `clientes_agendados` ≤ 3 y ≤ el tamaño de la franja.
3. En el gestor de agenda, la fila es recurrente, origen de esta spec, y el grupo tiene como máximo el cupo.
4. Forzar el refresh (o esperar la hora): si un cliente de la franja dejó de estar en caída, sale del grupo sin editarlo a mano.
5. Con el seguimiento prendido, a la hora de prueba llega la plantilla con el botón y no un audio.
6. Tocar **Escuchar seguimiento**: llega un audio corto, nombra como máximo tres comercios, dice un objetivo solo si hay uno vigente, y cierra con el link de Field. En Conversaciones se puede reproducir.
7. Tocar de nuevo en el mismo tramo: llega el mismo audio, no uno distinto.
8. Un vendedor con teléfono de 2 dígitos no genera error de Meta; el job queda `SKIPPED` con el texto de teléfono inválido.
9. Apagar `field_seguimiento.enabled`: el push de las 06:30 de un tenant que ya lo usaba vuelve a poder mandar audio.

---

## Criterios de aceptación

### AC-1 El cupo recorta la franja

- **Given** cupo 3 y una franja de más de 3 clientes con montos distintos.
- **When** se crea la agenda y corre el refresh.
- **Then** el grupo tiene 3 clientes y son los de mayor `monto_en_riesgo`.

### AC-2 La audiencia no queda congelada

- **Given** la agenda ya creada y un cliente que al día siguiente ya no está en la franja.
- **When** corre el refresh.
- **Then** ese cliente no está en el grupo. No hizo falta editar la agenda.

### AC-3 El botón abre el audio

- **Given** seguimiento prendido, credenciales y un teléfono de al menos 10 dígitos.
- **When** el vendedor toca **Escuchar seguimiento**.
- **Then** recibe un audio de ese slot y el job queda `SENT`. La plantilla de esa hora no iba acompañada de audio.

### AC-4 El push de las 06:30 no se duplica

- **Given** `field_seguimiento.enabled = true`.
- **When** corre el cron que antes mandaba el audio de la mañana.
- **Then** no se sube audio a WhatsApp por ese camino.

### AC-5 Teléfono inválido no llama a Meta

- **Given** un vendedor activo con teléfono de menos de 10 dígitos.
- **When** toca el horario de la plantilla o el botón.
- **Then** el job queda `SKIPPED` con `Teléfono de vendedor inválido`.

### AC-6 Una sola agenda Pareto

- **Given** ya existe una agenda con `origen = 'pareto_supervisor'`.
- **When** se vuelve a armar la franja desde Métricas con otros filtros.
- **Then** sigue habiendo una sola agenda de ese origen, el `grupo_id` no cambia, y `filtro_json` es el nuevo.
