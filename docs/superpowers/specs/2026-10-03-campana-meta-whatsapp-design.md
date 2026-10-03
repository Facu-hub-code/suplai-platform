# Campaña outbound: meta de WhatsApp y anillos de búsqueda

**Estado:** aprobado en chat el 2026-10-03  
**Fecha:** 2026-10-03  
**Repos:** `backend-supabase`, `product-management-app`, `suplai-platform`  
**Rama:** `feat/outbound-meta-whatsapp`

## Objetivo

La campaña outbound pide cuántos contactos con WhatsApp válido hay que reunir. Busca primero dentro de la zona. Si no alcanza, agranda de a 1 km por fuera, sin repetir lo ya buscado, y frena si el anillo siguiente puede costar más de US$ 10. Los comercios que ya son clientes o prospectos no entran en la lista. El envío lo confirma la persona.

## Criterios de aceptación

- Al armar la campaña hay un número obligatorio: contactos con WhatsApp válido a reunir.
- La primera búsqueda es la zona, con el mismo tope de “zona muy grande” que hoy.
- Un comercio no aparece si su teléfono o su `google_place_id` ya está en `{schema}.clients`, sea `lifecycle = client` o `prospect`. Tampoco si el teléfono está en `outbound_opt_out`.
- Después de validar WhatsApp, el contador es “válidos de meta”. Si faltan, se busca el anillo siguiente.
- El anillo solo cubre celdas nuevas. No se vuelve a pedir el centro.
- Si el techo de costo del anillo siguiente es mayor a US$ 10, la búsqueda no arranca hasta que la persona confirme. El techo se muestra.
- Se para al llegar a la meta, si la persona rechaza el costo, o si un anillo no suma ningún WhatsApp válido nuevo.
- La última ronda puede dejar más contactos que la meta. No se descartan.
- Si Outscraper o la validación fallan, queda lo ya reunido y se puede reintentar. No sale ningún mensaje por ese error.
- Al reabrir la campaña se ve la meta, el contador y la ronda en curso.
- El envío sigue siendo manual. El tope de 50 mensajes por día del número del agente no cambia.

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Qué cuenta la meta | Contactos con WhatsApp válido, los que se pueden tildar | El problema es terminar con pocos enviables después del filtro, no con pocos comercios listados | Contar comercios con teléfono antes de validar, o disparar los mensajes hasta la meta |
| Cómo se completa | Rondas: zona y después anillos de 1 km | El rendimiento de WhatsApp solo se conoce después de validar. Cada anillo se decide con el resultado real | Adivinar los anillos y pagarlos todos de una, o un botón manual “buscar más” |
| Área de cada anillo | Celdas de 1 km que tocan la zona ensanchada N km y no tocan la zona ensanchada N−1 km. N = 0 es la zona | Outscraper no recibe polígonos. La grilla ya existe y así no se paga dos veces el centro | Repetir toda la búsqueda con un límite más alto |
| Freno de costo | Confirmar si el techo del anillo siguiente supera US$ 10. El techo es celdas × tipos × 100 × precio por comercio | Es el mismo cálculo de hoy y es un máximo, no el costo real. Un anillo barato sigue solo | Seguir sin tope, o un solo anillo y parar |
| Primera búsqueda | Sigue la confirmación de zona grande (`LARGE_ZONE_CELLS`, 200 celdas) | Esa confirmación ya existe y no es el tope de US$ 10 | Aplicar US$ 10 también a la zona y cambiar el flujo actual |
| Clientes conocidos | Teléfono (solo dígitos, el mismo criterio de la campaña) o `metadata.google_place_id` | Un cliente del ERP suele tener teléfono y no lugar de Google. Un prospecto viejo puede tener el lugar y otro teléfono | Solo el lugar de Google, o nombre y dirección parecidos |
| A quién aplica el descarte | Cualquier fila de `clients`, cliente o prospecto, más `outbound_opt_out` por teléfono | No hay que volver a escribirle a alguien que ya está en Suplai ni a quien pidió que no | Descartar solo la cartera y dejar mezclados los prospectos viejos |
| Sobrantes de la última ronda | Se quedan en la lista | Cortar a mitad de un anillo ya pagado tira contactos útiles | Pedir a Outscraper un límite exacto para no pasarse |
| Quién orquesta las rondas | El panel, apoyado en el estado guardado de la campaña y de cada job | La validación y el polling ya viven ahí. Al volver a abrir se retoma sin un proceso en segundo plano | Un worker que siga buscando con la pestaña cerrada |
| Envío | Sigue igual: la persona tilda y confirma | La meta es reunir volumen, no mandar solo | Enviar automáticamente hasta la meta, repartido en días |

## Alcance explícito

Incluido:

- Campo de meta en el alta de la campaña y en el panel.
- Búsqueda por rondas, con estado para retomar.
- Descarte por teléfono o lugar de Google antes de contar y de mostrar.
- Confirmación cuando el anillo siguiente supera US$ 10 de techo.
- Contador “válidos de meta” y texto de la ronda (“buscando a 2 km”).
- Parada por meta, rechazo de costo o anillo sin WhatsApp nuevo.
- Tests de geometría del anillo, descarte, parada y confirmación de costo.

Fuera de alcance:

- Envío automático. El mensaje lo confirma la persona.
- Cambiar el tope de 50 mensajes por día.
- Matchear por nombre o dirección parecidos. Mezcla comercios distintos que se llaman igual.
- Reescribir el proveedor de Outscraper ni el precio por comercio devuelto.
- Seguir buscando con la pestaña cerrada.

## Cómo funciona

1. La persona carga el texto del cliente ideal, los tipos de comercio y la meta (entero ≥ 1).
2. Se scrapea la zona (`buffer_m = 0`), igual que hoy.
3. De esa ronda se sacan duplicados del propio resultado, cerrados, los que caen fuera del área de la ronda, los conocidos y los opt-out.
4. Se valida WhatsApp de los teléfonos nuevos. Los de rondas anteriores no se vuelven a validar.
5. Si los válidos llegan a la meta, se muestra la lista y se para.
6. Si faltan, se calcula el anillo de 1 km siguiente y su techo. Si el techo es mayor a US$ 10, se espera confirmación. Si no, o si confirman, se busca solo ese anillo.
7. Se suma a la lista y se repite desde el paso 3.

Paradas:

- Válidos ≥ meta.
- La persona no confirma el costo. Queda la lista parcial.
- El anillo, ya validado, no suma ningún WhatsApp válido que no estuviera. Queda “22 de 40” y la lista.
- Outscraper o la validación fallan. Queda lo ya reunido. No se abre otro anillo hasta reintentar esa ronda. Reintentar no vuelve a pedir las celdas que ya terminaron bien.

La lista muestra los comercios que pasaron el descarte, con su estado de WhatsApp. Solo los válidos se pueden tildar, igual que hoy. El contador no incluye a los que todavía se están validando.

## Orden de implementación

| Orden | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `suplai-platform` | `feat/outbound-meta-whatsapp` | Este spec |
| 2 | `backend-supabase` | `feat/outbound-meta-whatsapp` | Migración, descarte, anillos, estado de la búsqueda |
| 3 | `product-management-app` | `feat/outbound-meta-whatsapp` | Input de la meta, contador, confirmación del anillo |

El backoffice se mergea después del backend. Si el front sale antes, el alta de campaña no puede guardar la meta.

## Migración de base de datos

Archivo nuevo en `backend-supabase/sql/`. Usar **144** si `143_disable_google_places.sql` ya existe en la rama de Places. Si no, el siguiente número libre. No chocar con 143.

- `{schema}.campaign.target_whatsapp integer NULL`. Las campañas viejas quedan en NULL y siguen con una sola pasada de la zona. El alta nueva exige un entero ≥ 1.
- `core.directory_search_job.buffer_m integer NOT NULL DEFAULT 0`. 0 es la zona. 1000 es el primer anillo, 2000 el segundo, y así.
- No se borran filas. No hay backfill.
- Orden: agregar las columnas, después desplegar el código que las lee.
- Rollback: dejar las columnas. El código viejo las ignora si tienen default. Quitarlas solo si ningún job nuevo escribió `buffer_m` distinto de 0.

## Plan de prueba en CI/CD

En `backend-supabase`:

- Una celda del anillo de 1 km no está en el conjunto de la zona, y una celda del centro no entra en el anillo.
- Un comercio con el mismo teléfono que un cliente, o el mismo `google_place_id`, no queda en el resultado. Uno desconocido sí. El opt-out sigue afuera.
- Con meta 2 y dos WhatsApp válidos, no se arma otro anillo.
- Un anillo que no suma ningún válido nuevo deja la búsqueda parada, con la lista parcial.
- Techo del anillo > US$ 10 sin confirmación no llama a Outscraper. Con confirmación, sí.
- `tests/test_directory_outscraper.py` sigue verde.

El backoffice no tiene runner de tests. El mínimo del PR es `tsc` sobre los archivos tocados, sabiendo que el proyecto ya tiene errores previos ajenos a este cambio.

La migración se revisa en el PR. No se aplica a producción en el mismo paso que el código, salvo pedido explícito.

## Plan de prueba humana

Servicios: backend en `8000`, backoffice en `3000`. Tenant `demo`.

1. Abrir el mapa, elegir una zona y crear una campaña con meta 5 (o el número que se quiera probar).
2. Buscar. El contador muestra válidos de 5. No aparece un cliente de la zona cuyo teléfono ya esté cargado.
3. Si con la zona no se llega, y el anillo siguiente pasa de US$ 10, la pantalla pide confirmación y muestra el techo. Sin confirmar, no hay otra búsqueda.
4. Confirmar o, si el anillo es barato, dejarlo seguir. La lista suma contactos y no repite los de la zona.
5. Llegar a la meta, rechazar el costo o agotar un anillo. En los tres casos se puede tildar y el mensaje no sale solo.
6. Cerrar y volver a abrir la campaña. Se ven la meta y lo ya encontrado.
