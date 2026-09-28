# 083 — Campaña outbound por zona (directorio de comercios + plantillas)

**Estado:** Borrador  
**Fecha:** 2026-09-27  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`, `agente-conversacional-multi_tenant`  
**Ramas sugeridas:** `feat/campana-outbound-mapas`  
**Diseño:** [Suplai Sales · Campañas por zona](https://www.figma.com/design/kxhYfCkXazqA5JYElB4xvD/Suplai-Sales-%C2%B7-Campa%C3%B1as-por-zona) — pantallas `02 Panel de zona · Outbound` (`5:2`), `05 Wizard · Outbound` (`6:135`), `03 Funnel de la zona` (`5:128`) y modelo de datos (`8:195`).  
**Contexto de negocio:** tablero Miro [Ciclo de vida del cliente](https://miro.com/app/board/uXjVHj-XzZA=/), etapa 2 del workflow de campaña.  
**Relaciona:** [071](./071-maps-icp-prospeccion-decisor.md) (prospección, ICP guardado, alta antes del HSM, tool decisor), [070](./070-whatsapp-estado-webhook-agenda.md) (estados de plantilla), [073](./073-mixpanel-analytics.md).

Esta entrega es **solo el input outbound**. El anuncio de Meta (inbound) no se construye acá.

---

## Objetivo

Desde el mapa comercial, el operador arma una **campaña outbound de una zona**: define el cliente ideal, busca comercios en un directorio, elige plantillas ya aprobadas y les escribe con el mismo número de WhatsApp del agente. El panel de la zona y el funnel muestran si esa inversión se paga en margen.

El directorio de v1 es Google Places. El producto no puede quedar atado a ese precio ni a esa API: cambiar de proveedor no reescribe campaña, funnel ni atribución.

### Métricas de éxito

- Un operador publica una campaña outbound sin crear plantillas en el wizard y sin salir del mapa, salvo el salto a Plantillas si no hay ninguna aprobada.
- El ICP usado queda en la memoria del tenant y en la campaña, y la próxima apertura lo prellena.
- El panel muestra, para cada plantilla, el % de respuesta de Meta y el % de respuesta de Suplai, con fuente visible.
- Cada etapa del funnel de outbound tiene valor, tasa sobre la etapa anterior, costo por unidad cuando aplica, texto «Qué mide» y «Fuente».

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Alcance | Solo canal `outbound` | El pedido es la etapa 2 (mapas). Inbound Meta es otro input | Construir el wizard de 5 pasos completo del Figma, incluido Anuncio |
| Directorio | Interfaz `PlaceDirectoryProvider`. v1 implementa `google_places` | El precio de Places cambia y puede dejar de cerrar. Campaña y funnel hablan de «comercios encontrados» y `provider_id`, no de Google | Llamar Places desde el front; hardcodear el SKU de Google en la UI |
| Precio | Tabla de precio por proveedor (`price_per_request_usd`), editable sin deploy de UI | El costo estimado y el CAC tienen que seguir al precio real del proveedor | Fijar US$ 0,032 o el «US$ 1,10» del boceto en el cliente |
| ICP | Texto + tipos del proveedor, obligatorio si el outbound está prendido. Se guarda en memoria del tenant y se copia a la campaña | El agente necesita el texto cuando el prospecto responde. Los chips solos no alcanzan para la próxima campaña | Solo chips del boceto; ICP solo en el onboarding; estado local del wizard |
| Tipos de lugar | El proveedor traduce sus tipos. v1 reusa Table A de Places (spec 071). Se persiste `provider_id` + ids del proveedor | Otro directorio no tiene los mismos enums | Guardar `includedType` de Google como columna de negocio |
| Plantillas | Se **eligen** entre las ya creadas en Plantillas, estado `APPROVED`, categoría marketing. Máximo dos (A y B) | Crear y mandar a aprobación de Meta dentro del wizard es otro producto (1–2 días, editor, variables) | La nota del Figma que dice «se envían a aprobación al crear la campaña»; el chat de Sofía del 071 dentro de este wizard |
| A/B | Si hay dos plantillas, asignación 50/50 aleatoria por prospecto, estable (mismo prospecto no cambia de variante). Si hay una, va el 100% | El panel del boceto compara A y B. No hace falta un motor de experimentos | Optimizar el tráfico hacia la ganadora en v1; crear el texto A/B en el wizard |
| Ganadora | Se marca la de mayor **% respuesta Suplai**, solo si cada variante tiene al menos 30 envíos aceptados. No se reasigna el tráfico | Con menos envíos el % miente. La decisión de quedarse con una la toma el operador en la próxima campaña | Marcar ganadora por el `replied` de Meta; auto-pausar la perdedora |
| % de respuesta | Dos números, siempre juntos y etiquetados | Meta cuenta su `replied` con sus reglas. Suplai cuenta un mensaje del comercio en nuestra conversación. No son el mismo hecho | Un solo % «de respuesta» mezclando las dos fuentes |
| Funnel | Seis etapas del ciclo de vida, tasa **sobre la etapa anterior**, cohorte explícita. v1 abre solo la pestaña Outbound | El boceto ya lo pide («Qué mide» y «Fuente» siempre visibles). Sin cohorte los % no se pueden auditar | Un KPI suelto de «pedidos / mensajes»; calcular la tasa siempre sobre captación |
| Alta | El prospecto se persiste **antes** del HSM, igual que 071 | Si Graph falla, el comercio ya está y el inbound no cae al recepcionista | Mandar el HSM y crear el cliente solo si responde |
| Número | El mismo Phone Number ID del agente (`whatsapp.phone_id`). Tope 50 mensajes de plantilla nuevos por día (timezone del tenant). Pausa de envíos nuevos si la calidad del número no es alta | No hay un segundo número: el agente ya es el canal de la distribuidora. El tope y la pausa por calidad son el resguardo | Pedir un `outbound.phone_number_id` distinto y bloquear si coincide con el de atención |
| Opt-out | Un «no» (o pedido de baja) corta esa campaña y bloquea el teléfono para todo outbound futuro del tenant | El Miro pide salida inmediata. Reescribirle quema el número | Opt-out solo de esa plantilla |
| Margen | `margen_pct` del tenant. Si no está cargado, el resultado no inventa un múltiplo | En el Miro el 15% y los 6 meses son hipótesis. Mostrar «11,5x» sin margen configurado es falso | Usar 15% por defecto |
| Decisor | Reusar `refer_decision_maker` (071). El toggle de la campaña lo habilita para esos prospectos | La tool ya existe. Este spec no redefine el swap de primario | Prospecto hijo en otra tabla desconectada del PDV |
| Materialización | `funnel_daily` por día, zona, campaña y canal. El GET lee el agregado | Abrir el modal no puede recomputar pedidos e historial de chat | Query en vivo sobre `pedidos` + `conversation_events` en cada apertura |

---

## Alcance explícito

### Incluido (v1)

- Panel de zona en el mapa, pestaña **Outbound** (la pestaña Zona sigue siendo la actual).
- Wizard de campaña outbound con la zona ya elegida: cliente ideal, búsqueda, selección de plantillas, publicar.
- Memoria de ICP del tenant y snapshot en la campaña.
- Proveedor de directorio intercambiable; implementación Google Places; costo estimado antes de buscar y costo real al confirmar.
- Alta de prospectos con teléfono, exclusión de clientes actuales, primer HSM con la variante A o B.
- Resguardos: número separado, tope diario, pausa por calidad, opt-out.
- Toggle identificar decisor (tool ya existente).
- Panel: KPIs, prueba de plantillas con los dos %, costo y margen, «Ver funnel», «Buscar más comercios».
- Modal de funnel, pestaña Outbound, con las seis etapas definidas abajo.
- Eventos de agente para calificación y atribución de la campaña.

### Fuera de alcance

- Input inbound (anuncio Meta, pestaña Inbound, pestaña Total del funnel, `ad_spend`, `ctwa_clid`). El switch Inbound del panel queda visible y deshabilitado, con texto «Todavía no está disponible».
- Crear, editar o mandar a aprobar plantillas desde este wizard. Eso vive en Plantillas.
- Paso Promoción y paso Anuncio del stepper del Figma.
- Derivación al vendedor (`handoff_request`, pantalla 06).
- Reasignar tráfico a la plantilla ganadora, o más de dos variantes.
- Selector de tamaño de PdV (sigue el default de 071).
- Margen real por categoría. Hasta validar esa hipótesis del Miro, solo entra `margen_pct` del tenant.
- Proyección a 6 meses como número oficial. Si se muestra, va etiquetada «proyección, no medida».
- Cambiar el proveedor en producción en esta entrega. La interfaz y el `provider_id` sí quedan; la segunda implementación no.

---

## Superficie (Figma, recortada a outbound)

Archivo `kxhYfCkXazqA5JYElB4xvD`.

### Panel de zona · Outbound (`5:2`)

Mismo panel lateral de la zona. Switch **Zona | Inbound | Outbound**. Inbound deshabilitado en esta entrega.

Con outbound activo, el panel muestra:

- Estado: «Outbound activo · número del agente» (o el motivo por el que no se puede enviar).
- KPIs: comercios encontrados, primeros mensajes, tasa de respuesta **Suplai**, decisores identificados, pedidos, costo por cliente nuevo.
- Prueba de plantillas: nombre corto, `% respuesta Suplai · N envíos`, pill Ganadora o En prueba. Debajo, en tipo más chico, `% respuesta Meta`.
- Resguardos: tope diario, calidad del número, opt-out.
- Resultado: costo total desglosado (directorio + mensajes) y margen / múltiplo solo si hay `margen_pct`.
- Acciones: **Ver funnel**, **Buscar más comercios** (reabre el wizard con el ICP de la campaña).

Estado vacío: no hay campaña outbound en la zona. Un botón **Nueva campaña outbound**.

### Wizard (`6:135`, solo la parte outbound)

El stepper del archivo tiene Zona → Promoción → Anuncio → Outbound → Publicar. Esta entrega usa:

1. Zona (ya seleccionada, solo lectura).
2. Cliente ideal.
3. Plantillas.
4. Publicar.

El toggle del boceto («Sumar outbound a esta campaña») no aplica: la campaña **es** outbound. No hay campaña inbound a la cual sumarle.

**Cliente ideal**

- Texto del ICP (obligatorio). Se prellena con el último guardado en memoria.
- Chips de tipos del proveedor, sugeridos desde el texto (reuso de `suggest-channels` de 071). Sin ningún tipo elegido no se busca.
- «Excluir clientes actuales» prendido y no se puede apagar en v1.
- «Solo comercios con teléfono publicado» prendido por defecto. Si se apaga, los sin teléfono se ven y no se pueden tildar.
- Al buscar, el backend estima el costo **antes** de llamar al proveedor y lo muestra. Confirmar gasta. El resultado lista nombre, tipo y si el teléfono está verificado, más el total («312 comercios encontrados en {zona}»).
- Al confirmar el paso, el texto y los tipos se guardan en memoria y en el borrador de campaña.

**Plantillas a probar**

- Dos slots, A obligatorio para publicar, B opcional.
- Cada slot abre el listado de Plantillas en modo elegir. Solo filas `APPROVED` de categoría marketing, del tenant.
- Se muestra categoría, estado y cuerpo. No hay editor, no hay «Crear con Sofía», no hay borrador.
- Si no hay ninguna aprobada: estado vacío y link a Plantillas. Publicar queda deshabilitado.
- Copy fijo: con dos plantillas, «Se envía al 50% de los prospectos». Con una, «Se envía al 100%».
- Toggle **Identificar decisor**, con el texto del boceto.
- Caja de resguardos, no editable: mismo número del agente, 50 mensajes por día, baja inmediata ante un no, pausa si la calidad baja de alta.

**Publicar**

- Resumen: zona, ICP, cantidad a contactar, costo de búsqueda ya incurrido, plantillas, tope del día.
- Confirmar persiste prospectos y dispara el HSM (o agenda si el tope del día no alcanza; el resto queda en cola para el día siguiente, mismo tope).

### Funnel (`5:128`)

Modal «Funnel de {zona}». Subtítulo: nombre de campaña · Outbound. Ventanas **30 días | 90 días | 6 meses**. Pestañas Inbound y Total visibles y deshabilitadas.

Cada etapa muestra valor, pill de tasa o costo, barra relativa a captación, y dos líneas siempre visibles: **Qué mide** y **Fuente**. A la derecha, evolución semanal de la etapa tocada (default: Conversión) y costos del período. En outbound los costos son directorio + mensajes. Publicidad Meta no se muestra en esta pestaña.

---

## Cómo se mide el funnel (outbound)

### Cohorte

La cohorte de una ventana (30 días, 90 días o 6 meses) son los prospectos outbound de esa zona cuyo **primer mensaje fue aceptado por Meta dentro de la ventana**.

Las etapas de adelante se cuentan sobre esa misma cohorte, aunque el pedido caiga después del último día, con estos topes:

- Calificación y conversión: sin tope extra dentro de la vida de la campaña. El pedido tiene que ser el primero de ese prospecto y quedar atribuido a la campaña.
- Activación: el segundo pedido tiene que caer **dentro de los 30 días** del primero. Si el primero tiene menos de 30 días de antigüedad al momento de la consulta, ese prospecto figura como «activación todavía no observable» y **no entra** al denominador de la tasa de activación.
- Retención: un activado está retenido si tiene al menos un pedido en los 30 días anteriores al cierre de la ventana. Si la ventana todavía no deja ver esos 30 días post-activación, misma regla: no entra al denominador.

Un prospecto cuenta una vez. Un segundo HSM (decisor) no abre otra captación: sigue en el mismo prospecto (`parent` es el mismo PDV).

`funnel_daily` guarda los conteos del día en que ocurrió el hecho (aceptación, calificación, pedido). El GET suma los días de la ventana y arma la cohorte. No recalcula leyendo chats en el request.

### Etapas

La tasa es **sobre la etapa anterior**, como el boceto. Captación no tiene tasa: tiene costo por unidad. Resultado no es un porcentaje de retención: es margen dividido inversión.

| # | Etapa | Valor | Tasa o costo | Qué mide | Fuente |
|---|--------|--------|----------------|----------|--------|
| 1 | Captación | Prospectos de la cohorte | Costo por captación = (costo directorio + costo mensajes de esas campañas en la ventana) / captación | Comercios a los que Meta **aceptó** el primer mensaje de la campaña. No es una conversación iniciada por el comercio | Suplai: fila de envío aceptado (`envios_plantillas` o equivalente) ligada a `campaign_prospect`. Costo: `campaign_cost_daily` |
| 2 | Calificación | De la cohorte, los que tienen decisor identificado y comercio confirmado en zona de reparto | calificación / captación | El agente confirmó que es un comercio de la zona y ya habla con quien compra (el contacto original o el decisor) | Eventos del agente `qualified` y `decision_maker_found` con `campaign_id`. El swap de `refer_decision_maker` emite `decision_maker_found`. Sin los dos eventos no entra |
| 3 | Conversión | De los calificados, los que tienen primer pedido `confirmado` o `descargado` atribuido | conversión / calificación. Pill secundaria: CAC = inversión de la ventana / conversiones | El primer pedido quedó en el ERP (o en pedidos Suplai) atado a esta campaña | `pedidos` del cliente del prospecto, `origen` cualquiera, estado `confirmado` o `descargado`, `campaign_id` en el pedido o en `campaign_prospect.first_order_id` |
| 4 | Activación | De los convertidos observables, los que tienen un segundo pedido dentro de los 30 días del primero | activación / convertidos observables. Texto auxiliar: mediana de días entre pedido 1 y 2 | Volvió a comprar dentro de los 30 días. Es la señal del Miro de que se queda | Pedidos del mismo cliente, misma regla de estado. El denominador excluye a quien todavía no cumplió 30 días desde el primero |
| 5 | Retención | De los activados observables, los que tuvieron al menos un pedido en los 30 días previos al fin de la ventana | retención / activados observables. Auxiliar: churn = 1 − esa tasa | Sigue en la cartera de bajo ticket. El agente lo atiende solo; esta etapa no exige un mensaje humano | Pedidos del cliente. Misma exclusión si el tramo de 30 días todavía no cerró |
| 6 | Resultado | Margen estimado / inversión | Múltiplo. Si no hay `margen_pct`, se muestra la inversión y la venta atribuida, y la pill dice «margen no configurado» | El margen de los pedidos atribuidos a la cohorte paga directorio y mensajería | Margen = suma del total de esos pedidos × `margen_pct` del tenant. Inversión = `places_cost` + `message_cost` de `campaign_cost_daily` en la ventana, campañas outbound de la zona. `ad_spend` no entra |

Costo por cliente nuevo del panel = inversión outbound de la zona en la ventana default (30 días) / conversiones de esa cohorte. Si conversiones = 0, se muestra la inversión y «sin clientes nuevos», no un cero que parezca gratis.

La evolución semanal cuenta el **valor** de la etapa elegida por semana de ocurrencia (no la tasa). Al tocar Conversión, las barras son primeros pedidos por semana.

### Qué no entra en el número

- Búsqueda sin publicar (preview) no suma captación. El costo de esa búsqueda sí entra a `places_cost` cuando el operador la confirmó.
- Envío rechazado por Meta no es captación ni envío de la plantilla.
- Mensaje gratis (`free_entry_point` u otro flag del webhook de pricing) suma al conteo de mensajes y entra a `message_cost` en 0, separado en el desglose («mensajes sin cargo»).
- Pedido de un cliente de la zona que no salió de esta campaña no entra, aunque el comercio esté en el mapa.
- Opt-out no borra la captación: el mensaje ya se aceptó. Sí impide etapas que dependerían de un contacto futuro que ya no vamos a hacer. Si igual compra, la conversión cuenta.

---

## % de respuesta de las plantillas

Se muestra **por variante** (A y B), en el wizard no (todavía no hay envíos) y en el panel sí.

Hay dos porcentajes. Los dos usan el mismo denominador para poder compararlos: **entregados** según Meta. Si Meta todavía no informó ninguna entrega, el denominador de respaldo es **envíos aceptados** y la UI lo dice («sobre envíos aceptados, entregas todavía no informadas»).

| Métrica | Numerador | Denominador | Fuente |
|---------|-----------|-------------|--------|
| Envíos aceptados | Prospectos de la variante con envío aceptado por Meta | — | Suplai. Fila escrita solo cuando Graph devuelve ok. Un rechazo no suma |
| Entregados | Esos envíos con estado `delivered` | — | Meta. Webhook de estados |
| Leídos | Esos envíos con estado `read` | — | Meta. Webhook de estados. No se usa como % de respuesta |
| % respuesta Meta | `replied` de la plantilla en las stats de Meta, acotado a los envíos de esta campaña y variante | Entregados (o envíos aceptados si no hay entregas) | Meta. `meta_template_stats_daily` o el campo de respuesta del webhook, **solo** si se puede atribuir a estos `wamid`. Si Meta solo da el total de la plantilla en el WABA y no por campaña, no se prorratea: se muestra «Meta no parte esta plantilla por campaña» y no un % inventado |
| % respuesta Suplai | Prospectos de la variante con al menos un `user_message` en los **48 horas** siguientes al envío aceptado, en el hilo de ese teléfono | El mismo denominador | Suplai. `core.conversation_events` (fallback al historial de chat del tenant si el evento no está). Un mensaje nuestro no cuenta. Un opt-out sí cuenta como respuesta |

El número grande del panel y el que define la pill **Ganadora** es el **% respuesta Suplai**. El % Meta va al lado, con la etiqueta «Meta».

La pill Ganadora aparece en una sola variante cuando las dos tienen al menos 30 envíos aceptados y sus % Suplai difieren. Empate o muestra chica: las dos quedan «En prueba». No se frena el envío de la perdedora.

La tasa de respuesta del KPI del panel (el 21% del boceto) es el % respuesta Suplai de **todos** los primeros mensajes de la zona en la ventana, no el promedio de los % de A y B.

---

## Proveedor de directorio

```text
PlaceDirectoryProvider
  id                         # "google_places" en v1
  estimate(zone, types)      # requests previstos + USD, sin llamar al directorio si el precio es local
  search(zone, types, page)  # comercios: provider_place_id, nombre, tipos, teléfono?, lat/lng
```

- La campaña guarda `provider_id`. El prospecto guarda `provider_id` + `provider_place_id`. No hay columna `google_place_id` nueva; el id de Google vive como `provider_place_id` cuando el proveedor es `google_places`. Al leer datos viejos de 071 (`metadata.google_place_id`) se tratan como `google_places`.
- El precio sale de configuración del proveedor: `price_per_request_usd` y moneda. Cambiar el precio de Google es un cambio de config, no de código de campaña.
- v1 implementa la búsqueda con Places API (New) Text Search, field mask mínimo, dentro del polígono de la zona, tope y dedupe como 071 (teléfono normalizado o `provider_place_id` ya cliente).
- El front no llama a Google. No muestra la marca como si fuera la única: el toggle y los títulos dicen «buscar comercios». El detalle de costo puede decir «Google Places» como nombre del proveedor activo.
- Una segunda implementación entra registrando otro `id` y otro precio. Campaña, funnel y plantillas no se tocan.

El costo estimado se muestra antes de confirmar la búsqueda. Al confirmar, se guarda el costo real (`requests × price_per_request_usd` de ese momento) en `campaign_cost_daily.places_cost`. Si el precio cambia al día siguiente, lo ya gastado no se reescribe.

---

## ICP en memoria

Dos copias, a propósito:

1. **Memoria del tenant.** `metadata.prospeccion.icp_saved`, la lista que ya define 071: `{id, text, provider_id, provider_types[], updated_at}`, tope 8, dedupe por texto. El wizard prellena el último y deja elegir otro guardado. Se escribe al confirmar el paso de cliente ideal, también si el operador no llega a publicar.
2. **Snapshot de la campaña.** `campaign.icp_text` + `campaign.provider_types`. No se actualiza cuando el operador edita la memoria para la campaña siguiente. El agente, al tomar la respuesta, usa el snapshot de **esta** campaña (texto del ICP, zona, promo si más adelante existe). Así la memoria sirve para no reescribir el ICP, y la campaña no cambia de definición a mitad de los envíos.

Sin texto, o sin al menos un tipo, no hay búsqueda.

---

## Plantillas

- Origen único: la app de Plantillas (`public.meta_plantillas` del tenant).
- El wizard solo selecciona. Persiste `template_variant.meta_plantilla_id` (UUID local) y el nombre de Meta.
- Publicar exige la variante A en `APPROVED`. B, si está, también. Una plantilla que pasa a otro estado después de publicar no recibe envíos nuevos; los ya aceptados siguen en el funnel.
- Variables: el backend solo llena las que ya sabe (`distribuidora`, y si la plantilla la pide, nombre del comercio). Si la plantilla tiene otra cantidad de variables, no se puede elegir. No se manda texto libre.
- Asignación A/B: hash estable de `campaign_id + teléfono`, 50/50. No es `random()` por request.

---

## Resguardos de envío

- El envío usa el Phone Number ID del agente (`tenant_secrets` `whatsapp.phone_id`). Sin ese secreto, publicar está bloqueado.
- Tope: 50 primeros mensajes de plantilla por día por ese número, timezone del tenant. La cola sigue al día siguiente. Un HSM de decisor cuenta para el mismo tope.
- Calidad: si el rating del número en Meta no es el nivel alto (verde), se pausan los envíos nuevos y el panel lo dice. No se reintenta en loop.
- Opt-out: frase de baja o tool de opt-out marca el teléfono en una lista del tenant. Ninguna campaña outbound futura lo incluye. La baja es inmediata, sin segundo mensaje.

---

## Requisitos funcionales

- `RF-1` Panel de zona con pestaña Outbound y estado vacío.
- `RF-2` Wizard: ICP texto + tipos, búsqueda con costo estimado previo, lista, exclusión de clientes actuales.
- `RF-3` Confirmar el paso de ICP escribe memoria del tenant y snapshot en el borrador.
- `RF-4` Reabrir el wizard prellena el último ICP de memoria. «Buscar más» prellena el snapshot de esa campaña.
- `RF-5` Elegir plantilla A (y B opcional) solo desde Plantillas aprobadas. Sin creación en el flujo.
- `RF-6` Publicar: alta de tildados con teléfono antes del HSM, variante estable, respeto del tope diario.
- `RF-7` Inbound de un teléfono ya dado de alta entra al agente comercial, con contexto de campaña (ICP, zona). No entra al recepcionista.
- `RF-8` Toggle decisor usa `refer_decision_maker`. Apagado: la tool no se ofrece en esas conversaciones.
- `RF-9` Opt-out persiste y excluye el teléfono de búsquedas y envíos posteriores.
- `RF-10` Panel de plantillas con % Suplai, % Meta, envíos, y pill Ganadora según la regla de 30.
- `RF-11` `GET /{schema}/zones/{id}/funnel?channel=outbound&period=30d|90d|6m` devuelve etapas con valor, tasa, costo, qué mide, fuente y serie semanal. `channel=inbound` responde 404 o vacío explícito en v1, no números de outbound.
- `RF-12` Job diario que llena `funnel_daily` y `campaign_cost_daily.message_cost` desde los webhooks de pricing.

---

## Requisitos no funcionales

- `RNF-1` El front no recibe la API key del directorio. Places no se llama en CI.
- `RNF-2` Pooler 6543, `statement_cache_size=0`. La búsqueda y el alta de lote no abren una conexión por prospecto.
- `RNF-3` Header `x-schema-name`. Campañas, memoria de ICP y opt-out son del tenant.
- `RNF-4` Logs con `zone_id`, `campaign_id`, `provider_id`, conteos y `template_id`. Sin teléfonos.
- `RNF-5` Fallo de Graph después del alta: el prospecto queda, el envío figura rechazado, no es captación.

---

## Criterios de aceptación

### `AC-1` ICP queda en memoria

- **Given** una zona y un texto de ICP nuevo con dos tipos.
- **When** el operador confirma el paso de cliente ideal y cierra el wizard sin publicar.
- **Then** al reabrir, el texto y los tipos están prellenados, y `icp_saved` tiene esa entrada.

### `AC-2` Costo antes de buscar

- **Given** el precio configurado del proveedor.
- **When** el operador pide buscar.
- **Then** ve el costo estimado y todavía no hay llamadas al directorio. Al confirmar, la búsqueda corre y `places_cost` usa el precio vigente, no un número fijo del boceto.

### `AC-3` No se crea plantilla en el wizard

- **Given** el paso de plantillas.
- **When** el operador elige una plantilla.
- **Then** solo puede tomar una `APPROVED` existente. No hay acción de crear, editar ni enviar a Meta.

### `AC-4` Alta antes del HSM y A/B estable

- **Given** dos plantillas aprobadas y 4 teléfonos.
- **When** publica.
- **Then** existen 4 prospectos antes de Graph, cada uno con variante A o B, y repetir el proceso no les cambia la variante.

### `AC-5` Dos % de respuesta

- **Given** 10 entregados de la variante A, Meta informa 2 replied, y Suplai ve 3 `user_message` dentro de las 48 h.
- **When** se abre el panel.
- **Then** se lee 20% Meta y 30% Suplai, cada uno con su fuente. El número grande es 30%.

### `AC-6` Ganadora solo con muestra

- **Given** A al 40% Suplai con 10 envíos y B al 10% con 10 envíos.
- **When** se renderiza la prueba.
- **Then** ninguna dice Ganadora. Con 30 y 30, la mayor % Suplai sí.

### `AC-7` Funnel auditable

- **Given** 10 captados, 4 calificados, 2 con primer pedido, 1 con segundo pedido a los 20 días, y el otro primer pedido hecho ayer.
- **When** se abre el funnel a 30 días.
- **Then** captación 10, calificación 40% de captación, conversión 50% de calificación, activación 100% de **1** observable (el de ayer no está en el denominador). Qué mide y Fuente están en cada etapa.

### `AC-8` Sin margen no hay múltiplo

- **Given** un tenant sin `margen_pct`.
- **When** se mira el resultado.
- **Then** se ve la inversión y no un «11,5x».

### `AC-9` Opt-out

- **Given** un prospecto que pide no ser contactado.
- **When** otra campaña de la misma distribuidora busca o envía.
- **Then** ese teléfono no sale ni se le escribe.

### `AC-10` Otro proveedor no rompe la campaña

- **Given** un prospecto guardado con `provider_id=google_places`.
- **When** existe un segundo provider registrado y no se usa.
- **Then** el funnel y el panel de esa campaña siguen leyendo `provider_place_id` y costos ya guardados, sin columnas de Google.

---

## Casos borde

- `CB-1` Zona sin polígono o proveedor sin precio: no se busca; error accionable.
- `CB-2` Sin WhatsApp del agente: publicar bloqueado. Si el número existe, el outbound sale por ese mismo id.
- `CB-3` Teléfono ya cliente o ya en opt-out: no entra a la lista tildeable.
- `CB-4` Tope de 50 alcanzado: el resto queda en cola con fecha el día siguiente. No se fuerza el envío.
- `CB-5` Plantilla con variables que el backend no llena: no aparece como elegible.
- `CB-6` Meta no puede partir `replied` por campaña: se omite el % Meta y se deja el % Suplai. No se reparte el total del WABA.
- `CB-7` Calidad del número deja de ser alta a mitad del día: se paran los envíos nuevos; los ya aceptados siguen en las métricas.
- `CB-8` El decisor es un PDV que ya existe: se mantiene el 409 de 071, sin fusionar.

---

## Migración de base de datos

Tablas nuevas en el schema del tenant (nombres orientativos; la migración vive en `backend/`):

- `campaign`: `id`, `zone_id`, `channel` (`outbound` en v1), `status`, `provider_id`, `icp_text`, `provider_types` (jsonb), `identify_decision_maker` (bool), `starts_at`, `ends_at`. Sin `meta_campaign_id` / presupuesto de ads en esta entrega.
- `campaign_prospect`: `id`, `campaign_id`, `provider_id`, `provider_place_id`, `phone`, `business_name`, `stage`, `variant` (`A`|`B`), `customer_id`, `first_order_id`, `template_sent_at`, `opted_out_at`.
- `campaign_template`: `campaign_id`, `variant`, `meta_plantilla_id`.
- `campaign_cost_daily`: `campaign_id`, `date`, `places_cost`, `message_cost`, `message_cost_free`, `currency`. `ad_spend` no se usa en v1.
- `funnel_daily`: `date`, `zone_id`, `campaign_id`, `channel`, conteos de las seis etapas más `activacion_observable` y `retencion_observable` (denominadores) y `margin_estimated`.
- `outbound_opt_out`: `phone`, `campaign_id` de origen, `created_at`. Unique por teléfono en el tenant.

Config:

- `core.directory_provider`: precio por request del directorio, igual para todos los tenants. `google_places` es el SKU Text Search Enterprise (teléfono + rating), US$ 0,035. Un override opcional vive en `metadata.places_providers.google_places.price_per_request_usd` solo si el contrato de esa distribuidora es otro.
- `public.distribuidoras.metadata` (jsonb ya existente):
  - `prospeccion.icp_saved` se extiende con `provider_id` y `provider_types`. Los registros viejos de 071 se leen como `google_places`.
  - `economia.margen_pct` (nullable, dato del cliente; sin él no hay múltiplo).
  - No hay `outbound.phone_number_id`. El envío usa `whatsapp.phone_id` del agente.
  - `outbound.quality` opcional. Vacío se lee como `HIGH`.

**Seed / backfill:** no se migran campañas históricas: 071 no creó entidad campaña. Los `google_place_id` viejos se interpretan al leer, sin backfill masivo.

**Orden:** migración → API de provider, campaña y funnel → panel y wizard. Rollback: no registrar rutas; las tablas nuevas pueden quedar vacías. No se borra `icp_saved` viejo.

**Riesgo:** atribuir mal un pedido de cartera al primer outbound. El pedido solo cuenta si el cliente nació de `campaign_prospect` o si el primer pedido posterior al alta sigue sin otro `campaign_id`. Un cliente ERP previo excluido de la búsqueda no debería entrar.

---

## Orden de implementación

Cross-repo. El humano mergea. Orden: **backend → backoffice → agente**.

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `suplai-platform` | `feat/campana-outbound-mapas` | Esta spec |
| 2 | `backend-supabase` | `feat/campana-outbound-mapas` | Migración, provider, campaña, costos, funnel, opt-out, tope |
| 3 | `product-management-app` | `feat/campana-outbound-mapas` | Panel Outbound, wizard, modal de funnel, picker de Plantillas en modo elegir |
| 4 | `agente-conversacional-multi_tenant` | `feat/campana-outbound-mapas` | Contexto de campaña al responder; eventos `qualified` y `decision_maker_found`; opt-out |

El picker reusa el modal de Plantillas. No se abre un PR de creación de plantillas.

---

## Impacto técnico

| Capa | Qué tocar |
|------|-----------|
| Backend | Provider de directorio al lado de la búsqueda de 071; rutas de campaña y `GET .../funnel`; job de `funnel_daily`; webhook de estados ya usado por 070, sumando costo y `wamid` de la campaña |
| Backoffice | Panel del mapa comercial; wizard nuevo de outbound; modal funnel; Plantillas solo como selector |
| Agente | Contexto al entrar un inbound de prospecto; emisión de eventos; `refer_decision_maker` solo si el toggle de la campaña está prendido |

Mixpanel: si se agregan eventos de UI, se documentan en el spec 073 en el mismo cambio (`snake_case`, sin PII, sin duplicar `pedido_confirmado`). No se define una taxonomía paralela acá.

---

## Plan de prueba en CI/CD

- **Backend:** provider fake (estimate no llama red; search devuelve 3 filas; el precio sale de config). Dedupe contra cliente y opt-out. A/B estable. Tope 50 parte la cola. Funnel con la cohorte de `AC-7` (denominador observable). % Suplai y % Meta no se mezclan. Sin `margen_pct` no hay múltiplo. Stats de Meta a nivel WABA no se prorratean. Migración aplica en el smoke de schema de test.
- **Backoffice:** `tsc --noEmit`. El wizard no renderiza crear plantilla. Inbound del funnel deshabilitado. Panel muestra las dos etiquetas de fuente.
- **Agente:** evento `decision_maker_found` al usar la tool; con toggle apagado la tool no está. Opt-out no dispara otro HSM.
- Checks ya verdes de 071 (alta antes del HSM, 409 de otro PDV) siguen verdes.
- Gap: sin e2e de browser en CI. Places y Graph van mockeados.

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenant `demo` con una zona poligonal, lista pública, WhatsApp del agente configurado, y al menos una plantilla marketing `APPROVED`. `margen_pct` cargado en una pasada y vacío en otra.

1. Mapa → zona → pestaña Outbound vacía → **Nueva campaña outbound**.
2. Escribir un ICP, sugerir tipos, confirmar el paso, cerrar. Reabrir: el ICP está prellenado.
3. Buscar: aparece el costo estimado antes de la lista. Confirmar y ver comercios con y sin teléfono. Los sin teléfono no se tildan. Un cliente ya cargado no aparece.
4. Elegir plantilla A desde Plantillas. Comprobar que no hay botón de crear. Publicar 2 teléfonos de prueba.
5. Ver en el panel envíos aceptados, y —cuando Meta mande estados— entregados, % Meta y % Suplai por separado.
6. **Ver funnel.** Pestaña Outbound con Qué mide y Fuente. Inbound no abre números. Repetir con el tenant sin `margen_pct`: no hay múltiplo.
7. Pedir baja desde el teléfono de prueba. Una segunda búsqueda no lo ofrece.

OK: los pasos 2, 4, 5 y 6 se pueden explicar con la tabla de etapas sin mirar el código.
