# 084 — Agente de prospección y funnel de chats

**Estado:** Borrador  
**Fecha:** 2026-09-28  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `agente-conversacional-multi_tenant`, `product-management-app`  
**Ramas sugeridas:** `feat/agente-prospeccion-funnel` en los cuatro  
**Relaciona:** [071](./071-maps-icp-prospeccion-decisor.md) (alta antes del HSM, tool decisor), [083](./083-campana-outbound-mapas.md) (campaña, ICP snapshot, funnel de margen en el mapa), [070](./070-whatsapp-estado-webhook-agenda.md).

El mapa ya encuentra comercios y les escribe. Este spec es lo que pasa **después**, en el chat: un agente que no vende, un tablero que muestra si del otro lado hay una persona y quién decide la compra, y el pase al agente vendedor solo cuando ese decisor está interesado.

---

## Objetivo

Cuando un comercio scrapeado (directorio del mapa, hoy Google Places) responde al primer mensaje, lo atiende un **agente de prospección**. Su trabajo termina cuando hay un **decisor interesado** en comprar lo que esa campaña ofrece, o cuando hace falta una persona. No arma carrito, no pasa precios y no confirma pedidos.

El decisor interesado es quien compra para ese comercio los productos del ICP de **esta** campaña. No es “el dueño de un kiosco”. Una distribuidora puede prospectar librerías por resmas y, en otra campaña, carnicerías o fiambrerías por papel para separar alimentos. El agente habla del recorte del ICP que corresponde a **ese** lugar.

En Conversaciones, el kanban pasa a tener dos funnels:

- **Ventas** (el de hoy): No responde → Responde → Carrito → Pedido.
- **Prospección** (el de la imagen): Mensaje enviado → Respuesta automática → En conversación → Decisor identificado, y la salida **Necesita a alguien**.

El webhook no adivina quién es. El teléfono ya está en la base porque el alta del mapa ocurrió **antes** del HSM (071 / 083). El router elige el grafo según esa fila y según si el prospecto ya fue pasado a ventas.

### Métricas de éxito

- Un prospecto abierto no recibe tools de pedido. Si pide precio o quiere encargar, el agente registra interés y pasa el hilo al vendedor.
- Una respuesta de contestador, horario o catálogo automático cae en **Respuesta automática** y no cuenta como “respondió una persona”.
- La columna **Decisor identificado** muestra nombre, rol y WhatsApp de quien compra, y solo entra si el interés es sobre el ICP de esa campaña.
- El agente puede dictar el número de WhatsApp de la distribuidora (la misma línea) para que se lo pasen al decisor. El modelo no inventa el número.
- El próximo mensaje de un hilo pasado a ventas lo atiende el agente vendedor, con el contexto de la prospección, sin volver a preguntar quién es.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Grafo | `StateGraph` nuevo `prospect`, al lado de `seller`, `registration` y `coach` | El grafo vendedor tiene rieles de carrito, promo y confirmación. Un prompt que diga “no vendas” con esas tools igual vende. El límite tiene que ser el grafo, no una frase | Un flag dentro de `SellerState`; un modo del mismo ReAct |
| Router | En el webhook, el turno entra a **un** grafo | Así está armado el agente hoy (recepcionista vs vendedor vs coach) y no hay checkpointer de LangGraph. El pase es el turno **siguiente**, no un subgraph de ventas en el mismo invoke | `Command(goto=seller)` en el mismo turno: el vendedor puede mandar catálogo antes de que la persona lea el puente |
| Quién entra | Cliente ya resuelto por teléfono, `is_prospect = true`, sin `handed_off_at` | El usuario lo pidió: el scraping ya marcó la fila. Un desconocido sigue en el recepcionista. Un cliente de cartera sigue en ventas | Router nuevo por texto del mensaje; crear el cliente recién cuando responde |
| Hechos del turno | Nodo `load_facts` lee campaña, ICP, tipos del lugar, zona y estado. El LLM no escribe la etapa | Mismo criterio que `SellerState`: la fase de pedido no la escribe el modelo. Si la escribe, el tablero miente | Dejar que el modelo elija la columna en prosa |
| Clasificador | Nodo propio, salida estructurada, **antes** del ReAct | “Respuesta automática” vs “hay una persona” no se infiere de “hubo un inbound”. El contestador también escribe. Clasificar y contestar en el mismo llamado mezcla las dos tareas | Una sola llamada con tools; regex sola de “horario de atención” |
| Duda del clasificador | Si no está seguro, es persona (`en_conversacion`) | Esconder un lead en “respuesta automática” es peor que mostrar un bot en “en conversación” | Default a automática para no ensuciar el tablero |
| Tools | Allowlist corta. Cero tools de pedido, catálogo, promo o confirmación | El objetivo es encontrar al interesado, no venderle | Reusar el pack del vendedor “y que el prompt no las llame” |
| Decisor | Una tool `capture_decision_maker(nombre, rol, phone \| null, interest)` | La columna de la imagen muestra nombre **y** rol (dueño, encargada de ventas) y el WhatsApp. 071 solo pide nombre y teléfono, y manda al vendedor apenas hay número | Seguir con `refer_decision_maker` pelada; columna solo con el teléfono |
| Interés | Enum `interested` / `maybe` / `no`, lo setea la tool, lo confirma el nodo de commit | “Decisor identificado” en este producto es un decisor **interesado en comprar**. Un nombre sin interés no es la columna verde | Texto libre; entrar a la columna con solo el teléfono |
| Otro número | Si el teléfono es otro, la tool reutiliza el HSM y el swap de 071 | El copy y el swap de primario ya existen y el funnel de margen de 083 no debe abrirse de nuevo | Un segundo PDV; un HSM redactado por el modelo |
| Mismo número | Si quien habla es el decisor, no hay segundo HSM | Mandarle la plantilla “me pasaron tu número” a la misma persona es ruido | Siempre disparar `refer_decision_maker` |
| Número de la distribuidora | Tool `share_line_number` lee el teléfono visible de la línea del agente | “Compartí el WhatsApp” no puede depender de que el modelo recuerde dígitos. Es la misma línea de 083, no un número nuevo | Pedir un `outbound.phone_number_id` distinto; hardcodear el número en el prompt |
| ICP | Snapshot de la campaña (`icp_text` + `provider_types` del lugar), no un libreto de kiosco | El ICP cambia por campaña: librería y carnicería no escuchan el mismo producto. El snapshot no se mueve si el operador edita la memoria para la campaña siguiente (083) | Prompt fijo “almacenes y kioscos”; un mapa cerrado lugar → SKU |
| Recorte | El prompt habla solo del tramo del ICP que coincide con los tipos de **este** lugar | Una misma frase de ICP puede nombrar papeles de librería y papel separador de fiambre. Pitchar los dos a cualquiera quema el chat | Hacer que el modelo elija productos del catálogo y arme un pedido |
| Etapa en BD | Columna nueva `chat_stage` en `campaign_prospect`, más evento en `core.conversation_events` | `campaign_prospect.stage` ya significa el funnel de margen (`alta`, `captacion`, `opt_out`). Reusarla mezcla dos tableros | Etiquetas mutex como el CRM de ventas; recalcular solo con “hubo inbound” |
| Tablero | Kanban exclusivo, solo lectura. El agente avanza; no se arrastra la tarjeta para cambiar la etapa | Arrastrar pelea con el clasificador del próximo mensaje. El CRM de ventas ya tiene “a mano” para pausar al agente | Drag-and-drop como fuente de verdad |
| Avance | Solo hacia adelante en el camino feliz. `necesita_alguien`, `no_interesado` y `opt_out` son salidas | Un contestador que después escribe una persona tiene que subir. Una persona no vuelve a “mensaje enviado” | Reclasificar desde cero cada día |
| Pase a ventas | `handed_off_at` cuando `interest = interested` y hay nombre, rol y teléfono (el de la línea o el otro) | El usuario pidió pasar al vendedor al interesado, no al primer “hola” | Pasar en cuanto hay cualquier respuesta; pasar solo si hay pedido |
| Contexto del pase | El vendedor recibe un paquete (ICP, nombre, rol, interés, último intercambio) en el system del primer turno | Si no, el vendedor vuelve a preguntar “¿con quién hablo?” y se pierde el trabajo del otro grafo | Que el vendedor lea el hilo crudo y lo resuma solo |
| Funnel del mapa | El panel de la zona muestra las cinco etapas de chat y quién es el decisor. Además se emiten `qualified` y `decision_maker_found` | El operador mira el mapa para saber si la campaña está encontrando gente. El funnel de margen de 083 sigue al lado | Reemplazar el funnel de margen; dejar las etapas solo en Conversaciones |
| Filtro de chats | Tres audiencias: prospecto (`etiqueta = prospect` o fila de campaña), cliente y vendedor | Hoy "clientes" mezcla la cartera con los comercios scrapeados. El supervisor tiene que poder ver solo una | Un cuarto kanban como único lugar donde se distinguen |
| Checkpointer | No se agrega `PostgresSaver` | El proceso no lo usa. La continuidad ya está en los eventos y en la fila del prospecto. Un checkpointer nuevo es otro almacén de estado | Persistir el `ProspectState` completo en LangGraph |
| Tope | Como máximo 2 vueltas de tools por turno y 8 turnos de persona sin avance de etapa → `necesita_alguien` (`loop_cap`) | Un grafo con ciclo ReAct sin tope se queda charlando. La columna naranja de la imagen es exactamente “el agente no pudo solo” | Confiar en el recursion limit genérico sin una etapa visible |
| HITL | `manual_control` ya existente pausa al agente. No hay `interrupt()` de LangGraph | El operador mira el tablero del backoffice, no un resume de grafo | `interrupt_before` esperando un approve en el proceso del agente |

---

## Alcance explícito

### Incluido (v1)

- Grafo `prospect` con `load_facts` → clasificador → ReAct acotado o salida directa → `commit_stage`.
- Router del webhook: prospecto abierto → ese grafo; prospecto con handoff o cliente de cartera → vendedor; desconocido → recepcionista (igual que hoy).
- Tools: `capture_decision_maker`, `share_line_number`, `request_human`, `mark_not_interested`. Reuso interno del swap/HSM de `refer_decision_maker` cuando el teléfono es otro.
- Persistencia de `chat_stage`, decisor (nombre, rol, teléfono), interés y `handed_off_at`.
- Eventos de auditoría y los dos eventos que el funnel de 083 ya consume (`qualified`, `decision_maker_found`).
- Paquete de contexto para el primer turno del vendedor.
- Kanban **Prospección** en Conversaciones, al lado del kanban de ventas, con las cinco columnas de la imagen, KPIs y filtros.
- Filtro de la lista de Conversaciones con tres audiencias exclusivas: prospectos, clientes de cartera y vendedores. "Clientes" no incluye prospectos.
- En el panel outbound del mapa, el funnel de chat (las cinco etapas y el nombre, rol y WhatsApp de cada decisor). No reemplaza el funnel de margen.
- El agente habla en el idioma de la distribuidora, en prosa corta, sin lista de productos ni link de tienda.

### Fuera de alcance

- Segundo número de WhatsApp para prospección. Sigue la línea del agente (083).
- Reescribir el funnel de margen del mapa (captación → resultado). Esas seis etapas siguen en el panel de la zona.
- Elegir SKUs, precios, stock o armar pedido desde este grafo.
- Un mapa fijo lugar → rubro de catálogo. El texto del ICP de la campaña es la fuente. Cruzar tags de producto queda para después: hoy no hay una relación estable “carnicería → estos SKUs” y forzarla mete al agente a vender.
- Copilot de barrio (069) y el wizard de zonas blancas (071). No se rediseñan.
- Arrastrar tarjetas para cambiar la etapa.
- Crear la campaña, buscar en el directorio o mandar el primer HSM. Eso ya es 071/083.
- Visita presencial, presupuesto por mail armado por el modelo, o tarea de Field. Si lo piden, la tarjeta va a **Necesita a alguien**.
- Checkpointer de LangGraph y HITL con `interrupt()`.

---

## Cómo está armado el grafo

Un turno, un grafo. El estado vive en la base; `load_facts` lo rehidrata.

```text
START
  → load_facts
  → classify_inbound          # structured output, sin tools
       ├─ opt_out        → close_opt_out → END
       ├─ auto_reply     → reply_short   → commit_stage → END
       ├─ not_interested → close_no      → commit_stage → END
       └─ human          → react         → commit_stage → END
```

`react` solo existe si el clasificador dijo que hay una persona. Ahí el modelo puede llamar las cuatro tools. Si no llama ninguna, `commit_stage` igual corre y deja la etapa en `en_conversacion` (o en la que ya estaba, si era más adelante).

`commit_stage` es determinístico. Lee el resultado de la tool y el clasificador. El modelo no devuelve el nombre de la columna.

### Estado (`ProspectState`)

| Campo | Quién lo escribe | Para qué |
|--------|------------------|----------|
| `messages` | reducer `add_messages` | El hilo del turno |
| `facts` | `load_facts` | ICP, tipos del lugar, nombre del comercio, zona, campaña, nombre de la distribuidora, teléfono visible de la línea, etapa actual, decisor parcial |
| `inbound_kind` | clasificador | `auto_reply`, `human`, `opt_out`, `not_interested` |
| `capture` | la tool | nombre, rol, teléfono o “esta línea”, `interest` |
| `share_line` | la tool | verdadero si este turno dictó el número |
| `human_request` | la tool | motivo enum |
| `chat_stage` | solo `commit_stage` | la columna |
| `handoff` | solo `commit_stage` | el próximo turno va al vendedor |

### Clasificador

Salida estructurada, una etiqueta:

| Etiqueta | Entra cuando | No entra cuando |
|----------|----------------|-----------------|
| `auto_reply` | Contestador, horario, “gracias por escribirnos”, menú de opciones, catálogo automático, fuera de oficina | Hay una pregunta de la persona, un nombre, un “no me interesa” o un “pasame con el dueño” |
| `human` | Escribe una persona, aunque sea corta (“hola”, “decime”, “soy el encargado”) | — |
| `opt_out` | Pide que no le escriban más, “baja”, “equivocado y no insistas” | Un “ahora no” sin pedido de baja (`not_interested` o `maybe`) |
| `not_interested` | “No compramos eso”, “no es mi rubro”, rechazo del producto del ICP | “Hablá con mi socio” (eso es `human`: falta el decisor, no es un no) |

Si el modelo del clasificador falla o devuelve otra cosa, se trata como `human`.

### Camino de la etapa

Solo avanza. La etapa nueva es el máximo entre la actual y la que corresponde a este turno.

| Situación | Etapa |
|-----------|--------|
| HSM aceptado, nadie escribió | `mensaje_enviado` (la deja el envío, no este grafo) |
| `auto_reply` y todavía no hubo persona | `respuesta_automatica` |
| `human` y aún no hay decisor interesado | `en_conversacion` |
| `human` después de una automática | sube a `en_conversacion` |
| Tool con nombre, rol, teléfono e `interest = interested` | `decisor_identificado` y handoff |
| `interest = maybe` o falta rol / nombre | se queda en `en_conversacion`; el dato parcial se guarda para la tarjeta |
| Tool `request_human`, o 8 turnos de persona sin cambio de etapa | `necesita_alguien` |
| `not_interested` | `no_interesado` (no es columna; es filtro) |
| `opt_out` | `opt_out` y la baja de 083 |

`necesita_alguien` no se pisa con un mensaje siguiente del agente. Ahí ya está pausado para una persona (`manual_control`), salvo que el operador lo devuelva.

Motivos de `request_human`: `email_quote`, `visit`, `price_unknown`, `loop_cap`, `other`. Precio y pedido **siempre** son `price_unknown` o handoff por interés: el agente no contesta el número.

### Tools

**`capture_decision_maker`**

- `nombre` (obligatorio), `rol` (obligatorio, texto corto: dueño, encargada de compras, encargado de ventas), `phone` vacío si es esta misma línea, `interest`: `interested` | `maybe` | `no`.
- Teléfono distinto: valida como 071, swap de primario, HSM `suplai_decisor_encontrado_v1`. No fusiona si el número es de otro PDV (409, la tool lo dice y no hay handoff).
- Teléfono vacío: no manda HSM.
- `interest = no` no captura decisor: el commit va a `no_interesado`.
- Guardar rol e interés no alcanza para la columna verde. Hace falta `interested`.

**`share_line_number`**

- Devuelve el teléfono visible de la línea (el que ve el comercio), leído de la config del tenant. Si no está cargado, la tool falla y el mensaje de ese turno no incluye dígitos. La etapa no cambia por ese fallo.
- Se usa cuando la persona va a reenviar el contacto (“pasale este WhatsApp”) o junto con “lo contactamos por ese número” cuando el decisor es otro.
- Evento `whatsapp_line_shared`. No es un HSM extra.

**`mark_not_interested`** y **`request_human`**

- La primera cierra sin handoff. La segunda mueve a la columna naranja y prende `manual_control` de esa conversación.

Ninguna tool crea pedido, lista de precios ni link de tienda.

### Prompt (contrato, no el texto final)

`load_facts` mete en el system, en este orden:

1. Sos el agente de prospección de {distribuidora}. No tomás pedidos, no das precios, no mandás el catálogo.
2. Este comercio es {nombre}. Tipos del directorio: {provider_types}. Zona: {zona}.
3. ICP de esta campaña, textual: {icp_text}. Hablá solo del tramo que corresponde a estos tipos. Si el ICP nombra más de un rubro, ignorá los otros.
4. Si no podés decir si el lugar entra en el ICP, una pregunta (“¿ustedes trabajan con {tramo}?”) y nada más.
5. Objetivo: saber si hay alguien que compre eso, su nombre, su rol y su WhatsApp. Si es esta persona, el teléfono es el de la línea. Si no, pedilo.
6. Cuando haya interés, decí que por este mismo WhatsApp lo sigue el equipo de ventas y, si corresponde, dictá el número que devolvió la tool.
7. No asumas kiosco, almacén ni dietética.

Ejemplos que el prompt tiene que poder cumplir sin una lista cerrada de rubros:

- Campaña “papeles y resmas para librerías y papeleras”, lugar `book_store`: habla de papel de librería. No menciona fiambre.
- Campaña “papel para separar alimentos en carnicerías y fiambrerías”, lugar `butcher_shop`: habla de ese papel. No ofrece resmas.
- Campaña cuyo texto nombra los dos, lugar librería: solo el tramo librería.
- Lugar que no encaja (un gimnasio en una campaña de papel): una pregunta. Si dicen que no, `mark_not_interested`. No fuerces el pitch.

### Pase al vendedor

`commit_stage` escribe `handed_off_at` y el evento `prospect_handoff` con `campaign_id`, `customer_id`, nombre, rol, teléfono, `interest_summary` de una línea y el tramo de ICP que se usó.

El mensaje de puente lo manda **este** grafo, en este turno (“Perfecto, {nombre}. Por este WhatsApp te escribe el equipo de {distribuidora}.”). No hay un segundo mensaje proactivo del vendedor en el mismo segundo.

El turno siguiente de ese teléfono (el primario nuevo, si hubo swap) entra al grafo vendedor. `load_facts` del vendedor, si existe `prospect_handoff` y todavía no hubo un turno de ventas, antepone el paquete. El vendedor no repregunta nombre ni rol. Puede vender.

`is_prospect` no se apaga en el handoff. Se apaga cuando ya no es un prospecto de negocio (primer pedido, como hoy). El router mira `handed_off_at`, no el flag pelado: si no, el 071 manda al vendedor en el primer “hola”.

### Qué ve el funnel de margen (083)

| Hecho de este spec | Evento que 083 ya espera |
|--------------------|---------------------------|
| Primera vez que un turno queda en `en_conversacion` y el lugar sigue en la zona | `qualified` |
| Entrada a `decisor_identificado` | `decision_maker_found` |
| HSM al otro número | no es otra captación; el prospecto es el mismo PDV |

Un `maybe` no emite `decision_maker_found`.

---

## Tablero en Conversaciones

La vista lista no cambia: siguen todos los chats. En la vista kanban (el botón que hoy abre el CRM) hay un switch **Ventas | Prospección**.

Ventas queda como está: `no_responde`, `responde`, `carrito`, `pedido`.

Prospección es el tablero de la imagen.

### Cohorte del tablero

Filas de `campaign_prospect` con `send_status = accepted` (el primer mensaje lo aceptó Meta), del período que el operador eligió (Hoy / 7 días / 30 días; default Hoy, timezone del tenant). El ancla del período es `template_sent_at`, no el último mensaje. Así “Hoy” significa “les escribimos hoy”, que es lo que muestra la imagen.

Prospectos de 071 que tengan cliente `is_prospect` y un HSM de primer contacto, pero no fila de campaña: entran igual, con `chat_stage` en el cliente (`clients.metadata.prospeccion_chat`) hasta que exista campaña. La lectura del tablero unifica las dos fuentes en el endpoint. No se deja afuera al flujo viejo del mapa.

Después del handoff la tarjeta **sigue** en Decisor identificado. El kanban de ventas la muestra además, en la etapa de ventas que ya calcula el pipeline actual. Son dos lecturas del mismo cliente, no un mudanza que la borra.

### Columnas

Exclusivas. Una tarjeta, una columna.

| Columna | Qué mide | Qué se ve en la tarjeta |
|---------|----------|-------------------------|
| Mensaje enviado | Meta aceptó el primer mensaje y no hubo ni persona ni contestador | Nombre del comercio, teléfono, “Se mandó el primer mensaje…” |
| Respuesta automática | El clasificador vio un contestador y todavía no escribió una persona | “Contestó un bot o una respuesta armada…” |
| En conversación | Escribió una persona y todavía no hay decisor interesado | Última línea del agente. Si ya hay nombre parcial: “Falta confirmar interés” |
| Decisor identificado | Nombre, rol, WhatsApp e `interest = interested` | Nombre del comercio, debajo **Nombre (Rol)**, teléfono del decisor, “Lo contactamos por ese número” o el puente si es la misma línea |
| Necesita a alguien | El agente se frenó | Motivo en prosa corta: mail, visita, o se agotaron los reintentos |

Porcentajes del encabezado de columna: cantidad de la columna / conversaciones de la cohorte. Decisor identificado es el número verde. Necesita a alguien no entra en la tasa de éxito.

### KPIs (franja de arriba)

| KPI | Cálculo |
|-----|---------|
| Conversaciones | Cohorte |
| Respondió una persona | Tarjetas en En conversación + Decisor identificado + Necesita a alguien. La respuesta automática no suma |
| Decisor identificado | Columna verde |
| Tiempo a decisor | Mediana de horas entre `template_sent_at` y el evento del decisor, solo sobre los que llegaron. Si no hay ninguno, “—” |
| Necesitan a alguien | Columna naranja |
| Trabadas | En conversación, sin mensaje de la persona y sin cambio de etapa en 3 días. El 3 es constante de v1, no un setting |

### Filtros

- Buscar por nombre del comercio, teléfono o nombre del decisor.
- Necesitan atención: `necesita_alguien` o `manual_control` activo.
- Trabadas: la definición del KPI.
- Para reactivar: `maybe` guardado y sin handoff.
- A mano: `manual_control` activo.
- Respondieron: “respondió una persona”.

No se arrastra. “A mano” usa el control manual que ya pausa al agente.

### Búsqueda y paginación

Misma idea que el pipeline de ventas: una query, tope por columna, “Cargar más”. Sin un query por columna.

---

## Orden de implementación

Cross-repo. El humano mergea. Orden: **backend → agente → backoffice**. El spec de platform puede mergear cuando se acepte el texto; no bloquea el código.

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `suplai-platform` | `feat/agente-prospeccion-funnel` | Este doc |
| 2 | `backend-supabase` | `feat/agente-prospeccion-funnel` | Migración, escritura de etapa, `GET /{schema}/conversaciones/pipeline-prospeccion` |
| 3 | `agente-conversacional-multi_tenant` | `feat/agente-prospeccion-funnel` | Grafo, router, tools, paquete de handoff |
| 4 | `product-management-app` | `feat/agente-prospeccion-funnel` | Switch Ventas \| Prospección y el tablero |

El agente no se despliega antes que el endpoint de escritura: si no, el turno no tiene dónde dejar la etapa. El backoffice puede mergear después; hasta entonces el grafo ya corre y el tablero viejo no se rompe.

---

## Migración de base de datos

Sí. Sobre el schema de cada tenant activo, en el estilo de `sql/130_campana_outbound.sql`.

En `{schema}.campaign_prospect`, columnas nuevas, todas nullable salvo la etapa con default:

- `chat_stage text NOT NULL DEFAULT 'mensaje_enviado'` con check `mensaje_enviado | respuesta_automatica | en_conversacion | decisor_identificado | necesita_alguien | no_interesado | opt_out`.
- `chat_stage_at timestamptz`.
- `decision_maker_name text`, `decision_maker_role text`, `decision_maker_phone text`.
- `interest text` check `interested | maybe | no` o null.
- `needs_human_reason text`.
- `handed_off_at timestamptz`.
- `human_turns integer NOT NULL DEFAULT 0`.

No se toca `campaign_prospect.stage` (funnel de margen).

Backfill: filas con `send_status = accepted` y sin inbound quedan en `mensaje_enviado`. El resto no se adivina: se queda en `mensaje_enviado` hasta el próximo turno del agente. No se reclasifica historia con un LLM en la migración.

Prospectos sin fila de campaña (071): `clients.metadata.prospeccion_chat` con las mismas claves. El endpoint lee las dos. No hay tabla nueva.

Eventos nuevos en `core.conversation_events` (sin migración de esa tabla; el `event_type` es texto): `prospect_stage`, `prospect_handoff`, `whatsapp_line_shared`, `qualified`, `decision_maker_found`.

**Rollback:** el router vuelve a mandar todo cliente al vendedor si se revierte el agente. Las columnas nuevas se pueden dejar; el kanban de ventas no las lee. Borrarlas es un `ALTER` posterior, no parte del rollback del PR.

**Riesgo:** un backfill agresivo metería contestadores viejos en “en conversación”. Por eso el backfill no interpreta mensajes.

---

## Requisitos funcionales

- `RF-1` Webhook: teléfono ya cliente, `is_prospect`, sin handoff → grafo `prospect`. El handoff se lee de `campaign_prospect.handed_off_at` o, si no hay fila de campaña, de `clients.metadata.prospeccion_chat.handed_off_at`. Con handoff → vendedor. Si no es cliente → recepcionista. Vendedor de la distribuidora (`actor_type = seller`) no entra a este grafo.
- `RF-2` `load_facts` trae el snapshot de la campaña del prospecto (`icp_text`, `provider_types` del lugar, zona, `identify_decision_maker`). Sin campaña, usa el ICP guardado en la memoria del tenant solo como respaldo y lo marca en el log. Sin ningún texto de ICP, el agente hace una pregunta abierta de rubro y no inventa productos.
- `RF-3` El clasificador corre antes de cualquier tool. Fallo → `human`.
- `RF-4` El ReAct del prospecto no tiene tools de pedido, búsqueda de catálogo, promo, tienda, agenda de entrega ni confirmación.
- `RF-5` `capture_decision_maker` persiste nombre, rol, teléfono e interés. Teléfono nuevo pasa por la validación y el HSM de 071. 409 de otro PDV no hace swap ni handoff.
- `RF-6` La columna verde solo con `interest = interested` más nombre, rol y teléfono. `maybe` deja la tarjeta en En conversación.
- `RF-7` `share_line_number` usa el teléfono visible de la config. Si falta, no hay número en el mensaje.
- `RF-8` `commit_stage` no retrocede. Escribe `chat_stage`, el evento y, si corresponde, `handed_off_at`, `qualified` y `decision_maker_found`.
- `RF-9` Ocho turnos de persona (`human_turns`) sin cambio de etapa → `necesita_alguien` / `loop_cap` y `manual_control`.
- `RF-10` Opt-out llama la baja de 083 y corta el grafo.
- `RF-11` El primer turno del vendedor después del handoff incluye el paquete. No hay mensaje proactivo extra de ese grafo en el turno del pase.
- `RF-12` `GET /{schema}/conversaciones/pipeline-prospeccion` devuelve KPIs, cinco columnas y los filtros. Una sola query. Header `x-schema-name`.
- `RF-13` El switch Ventas | Prospección solo cambia el kanban. La lista de chats queda.
- `RF-14` Si la campaña tiene `identify_decision_maker = false`, no se pide otro teléfono (la tool no manda HSM ni hace swap). Igual hace falta nombre, rol e `interested` de quien ya habla para la columna verde y el handoff. Sin eso, la tarjeta se queda en En conversación.

---

## Requisitos no funcionales

- `RNF-1` Pooler 6543, `statement_cache_size=0`. El tablero no hace un query por columna ni un query por tarjeta.
- `RNF-2` Multi-tenant. Nada de etapa en memoria de proceso.
- `RNF-3` Logs: `schema`, `client_id`, `campaign_id`, `inbound_kind`, `chat_stage`, `handoff`. Sin volcar el teléfono completo en info; sí en la fila, que es el dato del tablero.
- `RNF-4` Tope de 2 tool-calls por turno en el ReAct de prospección.
- `RNF-5` El clasificador y el ReAct son llamadas distintas. No se fusionan “para ahorrar”.

---

## Criterios de aceptación

### `AC-1` No vende

- **Given** un prospecto abierto que escribe “¿a cuánto el bulto?”.
- **When** corre el grafo.
- **Then** no hay tool de pedido ni de precio; la respuesta no trae un importe; si hay interés de seguir, queda el camino de handoff.

### `AC-2` Contestador

- **Given** el primer inbound es “Nuestro horario es de 9 a 18. Dejanos tu consulta”.
- **When** corre el clasificador.
- **Then** `chat_stage = respuesta_automatica` y el KPI “respondió una persona” no lo cuenta.

### `AC-3` Persona después del contestador

- **Given** la etapa es `respuesta_automatica` y el mensaje nuevo es “hola, soy Carla, decime”.
- **When** corre el turno.
- **Then** la etapa sube a `en_conversacion` y no vuelve atrás.

### `AC-4` ICP de librería

- **Given** `icp_text` de papeles para librerías y tipos `book_store`.
- **When** la persona pregunta qué ofrecen.
- **Then** la respuesta habla de ese papel y no de kiosco, almacén ni fiambre.

### `AC-5` ICP mixto, lugar carnicería

- **Given** un ICP que nombra resmas para librerías y papel separador para carnicerías, y el lugar es carnicería.
- **When** el agente responde.
- **Then** habla del papel separador y no ofrece resmas.

### `AC-6` Decisor en otro número

- **Given** “las compras las hace Axel, el dueño, su WhatsApp es {número nuevo}” y el interés es comprar.
- **When** la tool corre y el número no es de otro PDV.
- **Then** Axel queda primario, sale el HSM de 071, la tarjeta muestra “Axel (Dueño)” y ese teléfono, hay `handed_off_at`, y el próximo mensaje de Axel lo toma el vendedor.

### `AC-7` Decisor es quien escribe

- **Given** “soy Ludmila, encargada de ventas, sí, mandame info por acá”.
- **When** cierra el turno.
- **Then** no hay segundo HSM; la tarjeta verde usa el teléfono de la línea; el mensaje de puente no inventa otro número; el próximo turno es del vendedor y no repregunta el nombre.

### `AC-8` Interés flojo

- **Given** “soy el dueño, ahora no, escribinos el mes que viene”.
- **When** corre la tool con `maybe`.
- **Then** la columna sigue siendo En conversación, no hay handoff, y el filtro Para reactivar la encuentra.

### `AC-9` Número de la línea

- **Given** “pasame el WhatsApp así se lo doy”.
- **When** el modelo llama `share_line_number` y la config tiene el teléfono visible.
- **Then** el mensaje contiene ese teléfono y el evento `whatsapp_line_shared`. Si la config no tiene teléfono, el mensaje no contiene dígitos inventados.

### `AC-10` Otro PDV

- **Given** el WhatsApp del supuesto decisor ya es cliente de otro PDV.
- **When** se llama la tool.
- **Then** 409, sin swap, sin handoff, la etapa no salta a verde.

### `AC-11` Necesita a alguien

- **Given** “mandame el presupuesto por mail” o el octavo turno de persona sin cambio de etapa.
- **When** cierra el turno.
- **Then** la tarjeta está en Necesita a alguien, el agente queda en control manual, y un inbound siguiente no lo contesta el grafo hasta que el operador lo suelte.

### `AC-12` Router

- **Given** el mismo teléfono, antes y después de `handed_off_at`.
- **When** entra un mensaje.
- **Then** antes va a `prospect`; después va a `seller`. Un cliente con `is_prospect = false` nunca entra a `prospect`.

### `AC-13` Tablero

- **Given** la cohorte de hoy con una tarjeta en cada columna.
- **When** el operador abre Conversaciones → kanban → Prospección.
- **Then** ve las cinco columnas, los KPIs de la franja, y Ventas sigue mostrando Carrito y Pedido sin esas tarjetas mezcladas en las columnas de prospección. La tarjeta verde sigue visible en Prospección después del handoff y también entra al kanban de Ventas por la regla de ventas.

### `AC-14` Funnel del mapa

- **Given** una campaña de 083.
- **When** el chat llega a persona y después a decisor interesado.
- **Then** existen `qualified` y `decision_maker_found` con `campaign_id`, y la captación de esa campaña no se duplica.

---

## Casos borde

- `CB-1` Sin texto de ICP y sin tipos: una pregunta de rubro. No lista “kioscos, almacenes, dietéticas”.
- `CB-2` `identify_decision_maker = false`: no se pide otro número ni hay HSM. Sigue haciendo falta nombre, rol e interés para la columna verde y el handoff (RF-14).
- `CB-3` Plantilla de decisor no APPROVED: igual que 071, no hay swap; la tool lo explica; la etapa se queda en conversación.
- `CB-4` Mensaje vacío, sticker o audio sin transcripción: se trata como `human` si ya había persona; si es el primer inbound y no hay texto, se queda en `mensaje_enviado` y no se llama al ReAct. No se clasifica un audio mudo como contestador.
- `CB-5` Dos campañas activas para el mismo teléfono: manda la más reciente (`campaign_prospect.created_at`). El ICP es el de esa fila.
- `CB-6` El operador tiene control manual: el webhook no invoca el grafo, igual que hoy con el vendedor.
- `CB-7` Opt-out a mitad de un decisor ya identificado: gana el opt-out, no se manda otro HSM, `handed_off_at` no se setea si todavía no estaba.

---

## Impacto técnico

| Capa | Dónde |
|------|--------|
| Backend | Migración tenant; servicio del pipeline de prospección; endpoint al lado de `GET /pipeline`; escritura que el agente llama (o el agente escribe por su conexión de tenant, una sola transacción, sin N queries) |
| Agente | `app/agent/prospect/` (`state`, `graph`, `nodes`, tools); rama en `webhook_inbound.py`; allowlist distinta de `seller`; paquete en el `load_facts` del vendedor |
| Backoffice | Switch en `conversations-view.tsx`; tablero hermano de `components/conversations/crm/`; tipos en `types/conversations.ts` |

Sin feature flag de UI. El router nuevo es el cambio de comportamiento: hasta que el PR del agente está en producción, los prospectos siguen con el vendedor.

---

## Plan de prueba en CI/CD

- **Agente:** grafo sin tools de pedido (assert de la lista); clasificador con fixtures (horario → `auto_reply`, “soy el dueño” → `human`, “no me escribas más” → `opt_out`, salida inválida → `human`); `commit_stage` no retrocede; handoff solo con `interested` + nombre + rol + teléfono; `share_line_number` sin config no devuelve dígitos; ICP de librería y de carnicería en el system de `load_facts` (test del armado del prompt, no una llamada real al modelo); router: prospecto abierto / con handoff / cliente de cartera.
- **Backend:** check de `chat_stage`; el update no pisa `stage` de margen; pipeline arma las cinco columnas y los KPI en una query (fixture SQL); “respondió una persona” excluye `respuesta_automatica`; mediana de tiempo a decisor; backfill deja `mensaje_enviado`.
- **Backoffice:** `tsc --noEmit`. El switch no desmonta el pipeline de ventas.
- Checks de 071 (refer-decision-maker) y de 083 (captación, opt-out) siguen verdes.
- Gap: sin e2e de WhatsApp ni de Places. El clasificador en CI usa la función de parseo y casos fijos; la llamada al modelo se mockea. El juicio fino del clasificador se mira en la prueba humana.

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`), agente local apuntando a ese backend. Tenant `demo` con zona, campaña outbound (o un prospecto `is_prospect` dado de alta por el mapa), plantilla de primer contacto y `suplai_decisor_encontrado_v1` en APPROVED, teléfono visible de la línea cargado.

1. Publicar o reutilizar una campaña cuyo ICP diga papeles para librerías. Alta de un teléfono de prueba. Escribir desde ese WhatsApp un texto de horario (“atendemos de 9 a 18”). En kanban → Prospección, la tarjeta está en Respuesta automática y “Respondió una persona” no sube.
2. Escribir “hola, soy Ana de la librería”. La tarjeta pasa a En conversación. El agente no manda precios ni link de tienda. Si preguntás “¿qué me vendés?”, habla de papel de librería.
3. Decir que las compras las hace Axel, dueño, y pasar un segundo teléfono de prueba, con ganas de comprar. Llega el HSM de decisor. La tarjeta verde dice Axel (Dueño) y ese número. El próximo mensaje desde el teléfono de Axel lo atiende el agente de ventas y no pregunta “¿quién sos?”.
4. Repetir con otra línea de prueba: “soy yo la que compra, mandame por acá”. No sale un segundo HSM. El mensaje cita el WhatsApp de la distribuidora solo si pediste el número; los dígitos coinciden con la config, no con otra línea.
5. “Mandame el presupuesto por mail”. La tarjeta va a Necesita a alguien y el agente deja de contestar hasta soltar el control manual.
6. Kanban Ventas: Carrito y Pedido siguen. La lista de chats muestra los hilos de siempre.
7. Una campaña (o un texto de ICP) que nombre librería y carnicería, contra un prospecto marcado como carnicería: el agente habla del papel separador y no de resmas.
8. Cliente que ya compra (`is_prospect` falso): sigue en el agente vendedor. Un número desconocido sigue en el recepcionista.

---

## Observabilidad y rollback

- Eventos `prospect_stage`, `prospect_handoff`, `whatsapp_line_shared`, `qualified`, `decision_maker_found`.
- Rollback: revertir el PR del agente devuelve los prospectos al vendedor. El tablero nuevo se esconde revirtiendo el backoffice. Las columnas de la migración pueden quedar.

---

## Riesgos

| Riesgo | Mitigación |
|--------|------------|
| El clasificador marca una persona como bot | Default a `human` ante la duda |
| El modelo vende igual, sin tools, dictando un precio de memoria | AC-1 y el prompt; si igual aparece un importe en la prueba humana, se corta el PR del agente |
| Misma línea para prospectar y vender, calidad de Meta | Sigue el tope de 50 HSM/día de 083. Este grafo no manda HSM salvo el del decisor |
| 071 decía que el inbound del prospecto va al vendedor | Este spec lo reemplaza mientras no haya handoff (RF-1) |
| ICP ambiguo en un solo texto | El prompt recorta por los tipos de este lugar; si no alcanza, una pregunta, no un catálogo |
| Historia vieja mal clasificada | El backfill no interpreta chats |

---

## Ideas que quedan para después

No entran en v1. Están acá para no perderlas y para no meterlas “ya que estamos”.

- **Familias del catálogo, sin vender.** Cuando exista una relación explícita campaña → familias (no un LLM mirando el catálogo), `load_facts` puede nombrar una o dos familias (“resmas”, “papel separador”) sacadas de esa relación. Hoy el ICP escrito por el operador cumple ese rol.
- **Audio.** Transcribir y clasificar. v1 no trata un audio como contestador ni como decisor.
- **Tiempo a decisor por variante A/B** de la plantilla, cruzado con el panel de 083.
- **Devolver una tarjeta** de Necesita a alguien a En conversación cuando el operador suelta el control manual, con un motivo. v1 la deja quieta hasta ese release.
