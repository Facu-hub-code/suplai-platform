# Claude MCP — objetivos de capacidades

Documento de trabajo para consultar antes de redactar un spec por caso. No es un spec: fija el objetivo, la factibilidad contra el sistema actual y el orden sugerido.

**Fecha:** 2026-10-08  
**Repos que van a tocar los specs:** `suplai-sales-claude-plugin` (skills), `backend-supabase` (tools MCP, scopes, servicios), `suplai-platform` (este doc y los specs).

## Línea de base

El conector (`https://mcp.suplaisales.com/mcp`) autentica al usuario del backoffice y expone **una** herramienta de solo lectura: `consultar_pedidos`. El scope OAuth es `pedidos:leer`. El rol de base `mcp_connector` tiene `SELECT` sobre `pedidos`, `items_pedido`, `clients` y `puntos_venta`. Cada llamada queda en `public.mcp_auditoria`.

El plugin `suplai-sales-claude-plugin` ya tiene una skill (`consultar-pedidos`) que enseña a Claude cómo traducir la pregunta y cómo mostrar el resultado. Las instrucciones del servidor dicen que las herramientas son de solo lectura para el gerente comercial.

El objetivo de esta serie es que ese mismo usuario configure Suplai desde Claude, con las reglas del negocio ya cargadas, sin pasar por un implementador para cada carga o cada plantilla.

## Reglas que aplican a todos los casos

Estas decisiones valen para los specs que salgan de acá. Cada spec puede ajustar el detalle, no el principio.

| Decisión | Por qué |
|---|---|
| La skill enseña; la tool ejecuta | Claude puede leer un Excel o explicar una plantilla sin una tool. Cualquier dato de la distribuidora entra o sale por una tool autenticada. |
| Escritura en dos pasos | Primero un preview (qué filas entran, cuáles se rechazan, qué va a cambiar). Recién después, con confirmación explícita del usuario en el chat, se persiste. |
| Scopes nuevos, no ampliar `pedidos:leer` | Cada familia de escritura tiene su scope (`catalogo:escribir`, `plantillas:escribir`, `erp:escribir`, etc.). El usuario ve qué está autorizando. |
| Las tools llaman servicios de la API | El rol `mcp_connector` sigue siendo de lectura. No se le da `INSERT`/`UPDATE`. |
| Nada de inventar precio, stock ni teléfono | Si el Excel no trae el dato, la fila se rechaza y se explica. No se completa con un valor “razonable”. |
| El Excel no viaja al MCP | Claude lo lee en el chat y manda lotes ya normalizados. Hay que topear el tamaño del lote. |
| La auditoría que ya existe cubre las tools nuevas | Misma tabla, misma forma: usuario, tenant, herramienta, parámetros, resultado. |

Queda fuera de esta serie: conectar credenciales de ERP, tokens de WhatsApp, cambiar el prompt del agente y borrar datos en masa.

## Orden sugerido

0. Manual (skill) → 1. Carga de clientes y productos → 2. Plantillas → 2.1 Grupos y agendas sobre esa plantilla → 3. Lectura de ERP, y después las promociones controladas → 4. Estrategias, conversaciones y mejora del agente.

El 0 se puede escribir ya, en el plugin, sin esperar tools nuevas. El 2.1 espera una plantilla del caso 2. El 4 espera el 1, el 2 y una agenda del 2.1.

---

## 0. Manual de usuario

**Factibilidad: alta.** No hace falta una tool nueva para la primera versión.

### Objetivo

El usuario le pregunta a Claude qué puede hacer con Suplai y cómo se hace. Claude responde con el alcance real del conector (lo que las tools permiten hoy), no con una lista inventada de pantallas del backoffice.

### Cómo

Una skill del plugin, al estilo de `skills/consultar-pedidos/SKILL.md`. Cubre:

- Qué pregunta responde cada tool y un ejemplo de frase.
- Qué no puede hacer todavía (para no prometer carga, plantillas o ERP antes de que existan).
- Cómo pedir una acción de escritura: Claude arma el preview y espera el “sí” antes de ejecutar.

La skill se actualiza en el mismo cambio que agrega una tool. Si más adelante la lista de tools crece mucho, una tool de solo lectura `explicar_capacidades` puede devolver el catálogo vivo y la skill queda como guía de tono. Eso no es necesario en v1.

### Spec que saldría

Corto, solo en el plugin. Criterio de aceptación: ante “¿qué podés hacer?” Claude enumera las tools reales y un ejemplo por cada una, y dice en una línea qué todavía no está.

---

## 1. Carga de clientes y productos

**Factibilidad: media-alta.** Los servicios de carga ya existen en el backend. Falta la superficie MCP (scope, preview, confirmación, mensajes de error por fila).

### Objetivo

El usuario sube un Excel a Claude. Claude acomoda columnas al formato de Suplai, muestra qué filas están listas y cuáles no, y —cuando el usuario confirma— carga contactos y productos para que el agente de WhatsApp pueda usarlos.

### Qué tiene que quedar válido

**Contacto.** El teléfono se guarda en dígitos, sin `+`, espacios ni guiones (`normalize_phone`). Para Argentina el destino de WhatsApp es `549` + característica sin `0` + número sin `15`. Un teléfono que no normaliza se rechaza en el preview, no se inserta a medias. Que el número exista en WhatsApp es otro paso (validación previa, spec 089): el formato correcto no alcanza para garantizar entrega.

El alta de clientes ya tiene `bulk_upsert` con teléfono, razón social, lista de precios, código, día de visita y etiqueta. Hay que respetar `clients.lifecycle` (cartera vs prospecto) y no pisar un teléfono que ya es de un vendedor.

**Producto visible para el agente y la tienda.** Hace falta, a la vez:

- `en_catalogo = true`
- precio de unidad mayor a 0 en una lista activa y pública (`listas_precios.activa` y `es_publica`)
- vectorización del SKU, si no el agente no lo encuentra por lenguaje natural
- alias en `productos_aliases` cuando el Excel o el nombre traen sinónimos (bulto, marca, nombre de fantasía)

El stock no es siempre un filtro de catálogo. La tienda oculta SKUs sin stock solo si el tenant tiene `show_products_without_stock` en falso (el default es mostrarlos). Una promoción de un SKU sí exige stock mayor a 0 y `en_catalogo`. El preview tiene que decir las tres cosas por separado: “entra al catálogo”, “tiene precio en la lista X”, “tiene stock / la tienda de este tenant igual lo muestra sin stock”.

### Qué ya existe

- `POST /{schema}/clientes` bulk upsert y chequeo de existencia por teléfono o código.
- `POST /{schema}/productos` bulk upsert, bulk de precios y de stock, y `POST /{schema}/productos/vectorize`.
- La fase 1 de implementación ya define columnas de producto, listas de precios y aliases. Esa skill es referencia interna: Claude no debe copiar la parte que estima stock cuando el Excel no lo trae.

### Huecos para el spec

- Tools de preview y de confirmación, con scope propio.
- Tope de filas por llamada y reporte fila por fila (columna de origen, valor recibido, motivo).
- Resolución de lista de precios: si el Excel trae un solo precio, una lista; si trae varias, el usuario elige el mapeo en el preview.
- No marcar `is_mock`. Esta carga es operativa, no la demo del onboarding (spec 036).

### Fuera de este caso

Imágenes, taxonomía automática con LLM, y inventar descripciones comerciales. Se pueden sumar después. La v1 acomoda columnas, valida y carga.

---

## 2. Configuración de WhatsApp (plantillas)

**Factibilidad: media.** Explicar, listar y medir es alto. Crear con reglas de negocio es medio. Editar el texto de una plantilla ya aprobada no es un objetivo: Meta no lo permite y el `PUT` local solo guarda categoría, motivo de rechazo, columnas de variables y media.

### Objetivo

Claude sabe para qué sirve una plantilla, qué no se puede cambiar, de dónde sale cada variable y cuándo una plantilla de promoción va a confundir al agente. Puede proponer una plantilla nueva (promocionar o contactar), crearla tras confirmación, y leer cómo rindió.

### Reglas que la skill y las tools tienen que respetar

- **No se edita el cuerpo.** Para cambiar el texto se crea otra plantilla (otro nombre) y, si corresponde, se da de baja la anterior.
- **Variables.** Solo columnas de la whitelist de `clients`: teléfono, nombre, razón social, código, día de visita, día de entrega, email, CUIT, vendedor, y `producto` (oferta). El listado vive en `GET /{schema}/plantillas-meta/columns-clients`. Si el Excel del cliente no tiene ese dato, la variable va a salir vacía en el envío.
- **Aprobación.** Crear en Meta deja la plantilla en revisión. Claude tiene que decir eso y no tratarla como enviable hasta que el estado sea aprobado.
- **Promoción.** Una plantilla que nombra un precio o un descuento solo se crea si ya existe la promoción para la audiencia. `PromocionCreate` exige `lista_precios_id` o `codigo_cliente`. La tienda muestra la promo de un SKU solo si el producto está en catálogo y tiene stock. Si la promo está en otra lista que la del cliente, el agente no la ve y la conversación se contradice. La tool de creación tiene que negarse, y explicar qué falta: promoción, lista, o stock.
- **Rendimiento y cupo.** Ya están la salud del número, el límite de mensajes y las métricas por plantilla (spec 087). Eso se expone en lectura antes de sugerir más envíos.

### Qué ya existe

`POST` y `DELETE` de plantillas Meta, sync desde la WABA, métricas, salud del número y facturación, test de envío, y CRUD de `promociones_semanales`.

### Huecos para el spec

- Skill de usos (contactar vs promocionar) y de la regla promoción ↔ lista ↔ stock.
- Tools de lectura (plantillas, estado, métricas, columnas de variables).
- Tool de creación que arma el body, elige categoría y mapea variables, siempre después del preview.
- Chequeo previo: si el objetivo es promocionar, la promoción tiene que existir para las listas de los destinatarios.

### Fuera de este caso

Subir el volumen de una campaña, comprar medios, y editar una plantilla aprobada. Armar el grupo y la agenda que disparan el envío es el caso 2.1.

---

## 2.1 Grupos y agendas a partir de una plantilla

**Factibilidad: media-alta.** Crear grupo y crear agenda ya son endpoints del backend. Falta la tool de MCP que los arme juntos, con un preview de a quién le va a llegar la plantilla y cuándo.

### Objetivo

El usuario elige una plantilla (recién creada o ya aprobada) y dice a quién y cuándo escribirle. Claude arma el grupo, muestra cuántos clientes entran, y deja la agenda apuntando a esa plantilla. El envío lo sigue haciendo el sender de agenda; Claude no manda los WhatsApp uno por uno.

### Cómo se arma

La plantilla no define la audiencia. El grupo define quién entra. La agenda une las dos cosas con un horario.

1. **Plantilla.** Tiene que existir en el tenant. Para dejar la agenda activa, el estado en Meta tiene que ser aprobado. Si sigue en revisión, la agenda se puede guardar inactiva y decirlo.
2. **Grupo.** Al menos un eje. Etiquetas, lista de precios y días de visita se combinan con AND: el cliente entra si cumple todos los ejes que el grupo tenga. Dentro de las etiquetas alcanza con una (incluidas las hijas). Dentro de los días, alcanza con que `dia_de_visita` sea uno de los elegidos. Geo-zona y los grupos especiales (`open_cart`, `recent_orders`, `churn_risk`) no se mezclan con esos ejes ni entre sí. Un vendedor puede sumarse como filtro junto al grupo manual. Sin ningún eje el API rechaza el alta: un grupo vacío no es “todos los clientes”.
3. **Agenda.** Destino único: `grupo_id` o `client_id`, nunca los dos. `meta_plantilla_id` obligatorio y del mismo tenant. Recurrente: lista de días y, si el usuario lo dice, hora `HH:MM`. Puntual: una fecha, sin días de la semana.

### Reglas que la skill tiene que aplicar antes de confirmar

- **Misma lista que la promoción.** Si la plantilla promociona, el grupo tiene que filtrar por la lista de esa promoción. Un grupo sin lista mezcla clientes que no ven el precio y el agente se contradice en el chat.
- **Variables.** Las de columnas de cliente (`nombre`, `razon_social`, `dia_de_visita`, etc.) salen de cada contacto. `dynamic_params` las pisa con un valor fijo para todo el envío: solo usarlo cuando la variable es la misma para el grupo (por ejemplo el nombre de la promo), no para el nombre del comercio.
- **Cupo y salud del número.** El preview dice cuántos clientes entran hoy y recuerda el límite del número (caso 2). Si el grupo es más grande que el cupo del día, la agenda no se parte sola en esta v1: Claude lo advierte y el usuario achica el grupo o elige días.
- **Activa recién con el sí.** El default del API es `activo = true`. La tool de confirmación crea la agenda inactiva, muestra el primer horario y la cantidad, y la prende solo si el usuario lo pide en el mismo paso.

### Qué ya existe

- `POST /{schema}/grupos` con la validación de modos de arriba, y el preview de miembros en el listado.
- `POST /{schema}/agenda`: valida que la plantilla sea del tenant, que el grupo o el cliente existan, y que el tipo recurrente o puntual traiga días o fecha.
- El sender resuelve los miembros con la misma membresía que el preview del grupo.

### Huecos para el spec

- Tool de preview: definición del grupo, conteo, muestra de nombres (sin teléfonos en el texto que Claude repite de más), plantilla, días y hora, y si la plantilla ya está aprobada.
- Tool de confirmación que crea grupo y agenda en ese orden. Si la agenda falla, el grupo queda nombrado y el error dice que no llegó a programarse.
- Reusar un grupo existente si el usuario nombra uno, en vez de duplicarlo.

### Fuera de este caso

La agenda Pareto del supervisor (spec 080), que rearma sola la audiencia cada corrida. El calendario mensual de una estrategia (spec 031). Seguir o pausar un envío que ya salió.

---

## 3. Configuración del ERP

**Factibilidad: media.** Mirar el estado es alto. Promover productos, clientes y listas es medio, porque los endpoints ya están y el efecto es grande. Conectar el ERP queda afuera.

### Objetivo

El usuario pregunta cómo está la sync y, con un preview, incorpora al catálogo de Suplai lo que el ERP ya trajo y todavía no está promovido: productos nuevos, clientes y listas de precios.

### Qué ya existe

En `/{schema}/erp`: config, `dependency-health`, sync de precios y de pedidos, carga de productos, clientes y listas, diff de precios, cola de alta de clientes (aprobar, vincular, descartar) y `promote-products-bulk` con `dry_run`. El teléfono de un cliente ERP pasa por propuestas antes de promoverse, justamente para no chocar con un contacto existente.

### Cómo partir el spec

1. **Lectura.** Estado de la última sync, pendientes de promover, listas sin vincular, clientes en cola. Scope de lectura, sin confirmación.
2. **Promoción.** Reusar el `dry_run` de productos y el preview de la cola de clientes. La confirmación del chat dispara el apply. Un cliente sin teléfono normalizable no se promueve: se lista el motivo.
3. **Listas.** Vincular una lista del espejo a una lista de Suplai y alinear precios. Mismo preview.

El token OAuth hoy corresponde a cualquier perfil del backoffice que no sea waitlist. El spec de escritura tiene que definir qué rol puede promover. Hasta eso, el default seguro es el mismo perfil que en el backoffice puede operar Integraciones.

### Fuera de este caso

`/connect`, tokens de ingesta, paquete del bridge y empujar pedidos al ERP. Eso mueve credenciales o documentos comerciales ya confirmados.

---

## 4. Onboarding y capacitación

**Factibilidad del paquete: media-baja.** Conviene partirlo. Depende de los casos 1, 2 y 2.1: sin contactos, plantilla, grupo y agenda, una estrategia no tiene a quién ni cuándo escribirle.

### Objetivo

Con los datos cargados, el usuario arma en Claude la operación comercial recurrente: etiquetar, agrupar, elegir una plantilla y dejar una estrategia. Además puede preguntar qué está pasando en las conversaciones y proponer mejoras de búsqueda (aliases) a partir de lo que el agente no encontró.

### Partes

| Parte | Factibilidad | Notas para el spec |
|---|---|---|
| Etiquetas y estrategias de envío | Media | El grupo y la agenda se arman en el caso 2.1. Acá la estrategia los ata (`grupo_id` + `agenda_id`) y suma ciclo o seguimiento. Solo si la plantilla de esa agenda está aprobada y, si promociona, la promo cubre la lista del grupo. |
| Analizar conversaciones | Media | Hay métricas de conversaciones iniciadas y respondidas. El texto crudo es sensible: la v1 devuelve agregados y ejemplos acotados, no el historial completo. |
| Reconocer patrones | Alta, sobre esos agregados | Lo hace Claude con los datos que devuelve la tool. No hace falta un modelo nuevo. |
| Mejorar búsqueda y aliases | Media | El agente matchea `productos_aliases` y el vector del catálogo. Una tool de solo lectura puede listar búsquedas sin match (logs de tools, spec 024). Claude propone aliases; el usuario confirma; se insertan y se re-vectoriza. |
| Cambiar el prompt o apagar tools del agente | Baja para esta serie | Queda como propuesta que el usuario aplica en el backoffice. No es una tool de escritura del MCP en v1. |

### Fuera de este caso

Reentrenar el modelo de sales-engine, reescribir el system prompt y disparar el WhatsApp desde el chat. El horario queda en la agenda del caso 2.1; la estrategia solo la referencia.

---

## Specs que salen de este documento

| Spec | Caso | Depende de |
|---|---|---|
| [094 — Manual del conector](../specs/094-claude-mcp-manual.md) | 0 | Nada |
| [095 — Carga de clientes y productos](../specs/095-claude-mcp-carga-clientes-productos.md) | 1 | Reglas de escritura de este doc. El plugin se mergea después del backend |
| [096 — Plantillas de WhatsApp](../specs/096-claude-mcp-plantillas.md) | 2 | 0. La parte de promo puede esperar a tener listas (caso 1) si el tenant carga por Excel |
| [097 — Grupos y agendas](../specs/097-claude-mcp-grupos-agendas.md) | 2.1 | 2. El conteo del grupo es más útil si el caso 1 ya cargó clientes |
| [098 — Estado del ERP y promoción](../specs/098-claude-mcp-erp.md) | 3 | Reglas de escritura. La lectura no espera al caso 1 |
| [099 — Estrategias, conversaciones y aliases](../specs/099-claude-mcp-estrategias-aliases.md) | 4 | 1, 2 y 2.1 |

Al redactar cada spec, usar las secciones obligatorias del workspace (decisiones, alcance, orden, migración, prueba en CI y prueba humana).
