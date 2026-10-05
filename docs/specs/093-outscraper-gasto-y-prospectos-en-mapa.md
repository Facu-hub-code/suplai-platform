# 093 — Gasto de Outscraper acotado y prospectos de la zona en el mapa

**Estado:** Borrador  
**Fecha:** 2026-10-05  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Rama:** `feat/outbound-meta-whatsapp`  
**Relaciona:** [090](./090-proveedor-directorio-outscraper.md) (proveedor, grilla, precio por comercio), [083](./083-campana-outbound-mapas.md) (campaña por zona), [089](./089-validacion-whatsapp-previa.md) (`core.phone_whatsapp_check`).

---

## Objetivo

Una búsqueda de comercios en la zona tiene que poder juntar contactos útiles sin facturar decenas de miles de lugares que caen afuera. Y, con la zona elegida, el mapa tiene que mostrar esos prospectos —con teléfono y sin teléfono— junto con filtros para clientes, teléfono y WhatsApp validado.

### Métricas de éxito

- Una zona del tamaño de Caballito o Florida Oeste no puede lanzar todas las celdas y todos los tipos de una sola vez.
- Antes de la primera llamada a Outscraper, la pantalla muestra el techo (queries, lugares máximos, dólares) y el servidor aborta si ese techo supera el tope configurado. En ese caso el costo real es US$ 0.
- Con el radio acotado a la celda, la mayoría de los lugares devueltos cae dentro del polígono. La prueba de una sola celda tiene que demostrarlo antes de habilitar una zona entera.
- En el mapa de la zona se ven los prospectos de la última búsqueda, incluidos los que no tienen teléfono. Los filtros de teléfono y de WhatsApp validado achican ese conjunto; no hace falta otra búsqueda.

---

## Cómo funciona hoy

Outscraper cobra por lugar devuelto, no por llamada. US$ 0,003 por lugar después de los primeros 500 del mes. El código ya usa ese precio (`QUERY_LIMIT` y `cost_cap` en `directory_search_service.py`).

### La llamada

Un solo cliente: `OutscraperProvider.submit` en `backend-supabase/services/directory_outscraper.py`. La clave sale de `OUTSCRAPER_API_KEY`.

El pedido es `POST https://api.app.outscraper.com/google-maps-search` (no el `GET /maps/search-v3`). El body lleva:

| Campo | Valor hoy |
|---|---|
| `query` | Lista de textos, uno por tipo de comercio (`kiosco`, `almacén`, …) |
| `organizationsPerQueryLimit` | **100** fijo (`QUERY_LIMIT`) |
| `coordinates` | `"lat,lng"` del centro de la celda, **sin zoom** |
| `language` / `region` | `es-419` / `AR` |
| `dropDuplicates` | `true` (solo dentro de ese pedido) |
| `async` | `true`. El id se lee después con `GET /requests/{id}` |
| `enrichment` | No se envía |

`start` parte la zona en una grilla de 1 km y se queda con las celdas cuyo cuadrado toca el polígono. Por cada celda hace un POST con **todos** los tipos juntos. El `for` espera la respuesta HTTP, pero esa respuesta es solo el id: Outscraper ejecuta todas las celdas a la vez. No hay lote, ni pausa, ni corte a mitad de grilla.

El resultado de cada pedido se copia a `core.directory_search_job.collected` cuando el wizard hace polling o cuando llega el webhook. Outscraper los guarda unas 2 horas. Estas corridas sí se guardaron. El descarte de duplicados entre celdas, de comercios cerrados, de los que caen fuera del polígono y de los que ya están en `clients` ocurre en `finalize`, **después de pagar**. `dropDuplicates` no cruza celdas. `is_already_known` no evita la llamada.

### Qué frena el gasto hoy, y qué no

| Control | Qué hace |
|---|---|
| Zona grande | Pide confirmación solo si hay **más de 200 celdas** |
| Anillo | Pide confirmación solo si el anillo de afuera puede pasar de **US$ 10** |
| Techo mostrado | `celdas × tipos × 100 × 0,003`. Es un máximo. La primera pasada de la zona no aborta por dólares |
| Tope de lista | 2.000 prospectos en la respuesta del wizard. No baja lo que Outscraper ya cobró |

Una zona de 53 celdas y 5 tipos tiene techo de US$ 79,50 y arranca sola.

### Qué se facturó

Corridas `done` del tenant `demo` el 3 de octubre de 2026:

| Zona | Pedidos HTTP | Queries (celdas × tipos) | Devueltos | Dentro del polígono | Costo guardado |
|---|---:|---:|---:|---:|---:|
| Caballito | 12 | 72 (6 tipos) | 6.850 | 109 | US$ 20,55 |
| Florida Oeste | 53 | 265 (5 tipos) | 25.721 | 616 | US$ 77,16 |
| **Total** | **65** | | **32.571** | **725** | **US$ 97,71** |

Florida Oeste promedia 485 lugares por pedido, pegado al techo de 5 × 100. Caballito, 6 tipos, promedia 571. El “cerca de 500 por consulta” es la suma de una llamada, no un límite de 500 ignorado. Con los 500 lugares gratis del mes, `(32.571 − 500) × 0,003 = US$ 96,21`.

Adentro del polígono quedó el 2 %. El otro 98 % se pagó porque `coordinates` no lleva zoom: cada centro trae comercios de un radio mucho mayor que la celda de 1 km, y la celda vecina los repite.

El 1 de octubre ya había otras seis búsquedas `done` (Villa Crespo, Caballito, Belgrano, Monserrat dos veces, Palermo): 23.736 lugares más. No entran en los 32.571, pero son el mismo mecanismo.

### El mapa hoy

Los prospectos que dibuja el mapa salen de zonas blancas (`POST /geo-zones/{id}/white-zones`), flujo de Places que esta rama apaga. La búsqueda de la campaña deja la lista en el wizard y en `directory_search_job.results`. Esos puntos no se dibujan en el mapa. El wizard puede ocultar los que no tienen teléfono; el dato sí está guardado. El estado de WhatsApp de un teléfono validado queda en `core.phone_whatsapp_check`.

---

## Qué cambia

### Gasto

1. **Cada pedido mira solo su celda.** `coordinates` pasa a incluir zoom 15 (el tamaño de la grilla de 1 km), en el formato que Outscraper ya acepta (`@lat,lng,15` o la URL de Google Maps equivalente). Sin eso, bajar el límite solo achica la factura y sigue trayendo comercios de afuera.
2. **Límite 20 por tipo.** `organizationsPerQueryLimit` deja de ser 100. Un valor mayor tiene que venir explícito en el pedido de búsqueda. En un kilómetro no hace falta llenar 100 fichas del mismo rubro.
3. **Un tipo por vez.** Se deja de mandar todos los tipos en el mismo POST. El orden es el que eligió la persona. El tipo siguiente solo se pide si, terminado el anterior, todavía no se llegó a la meta de WhatsApp válidos.
4. **Una celda por vez, y se para.** No se encolan las 53. Se pide una celda, se guardan los lugares, se cuentan los que caen adentro, no son clientes y tienen teléfono, y se validan solo esos teléfonos nuevos. Si los WhatsApp válidos ya cubren la meta, no se pide otra celda ni otro tipo.
5. **Tope duro antes de cualquier llamada.** Variables `OUTSCRAPER_MAX_PLACES_PER_RUN` y `OUTSCRAPER_MAX_USD_PER_RUN`. El techo de la corrida es `celdas a pedir × tipos a pedir × límite × 0,003`, calculado con lo que realmente se va a mandar (un tipo, las celdas que faltan, límite 20). Si supera cualquiera de los dos topes, la API responde el cálculo y **no llama a Outscraper**.
6. **La búsqueda real es explícita.** Calcular y mostrar el techo no llama a la API. El wizard manda `execute: true` solo cuando la persona aprieta Buscar, y el servidor rechaza el POST si ese flag no está. Así un cliente de la API no dispara gasto por estimar.

La primera corrida paga después de este cambio es **una celda, un tipo, límite 20**. Si la mayoría de los lugares no cae en esa celda, el zoom no sirvió y no se habilita la zona entera.

### Mapa de la zona

Con una zona seleccionada, el panel de la zona muestra filtros y el mapa dibuja los puntos. No se vuelve a llamar a Outscraper para pintar.

Fuente de los prospectos: lugares **dentro del polígono** de los jobs `done` de esa zona (la pasada y los anillos ya corridos), unidos por `place_id`. Entran los que no tienen teléfono. No entran los que ya son clientes o prospectos en `{schema}.clients` (siguen viéndose como clientes). El tope de 2.000 de la lista del wizard no esconde un punto que sí se pagó y está adentro: el mapa lee el conjunto dentro del polígono, no solo el recorte de la lista.

Filtros, en este orden, en el panel de la zona:

| Filtro | Qué muestra | Default |
|---|---|---|
| Clientes | Clientes de la cartera cuyo punto cae en la zona | Prendido |
| Prospectos | Todos los prospectos encontrados de esa zona, con teléfono y sin teléfono | Prendido si hay una búsqueda |
| Con teléfono | Subfiltro de Prospectos. Solo los que tienen teléfono | Apagado |
| WhatsApp validado | Subfiltro de Con teléfono. Solo los que en `core.phone_whatsapp_check` tienen `has_whatsapp` | Apagado |

“Con teléfono” no se puede prender si Prospectos está apagado. “WhatsApp validado” no se puede prender si “Con teléfono” está apagado. Apagar el padre apaga y deshabilita los hijos.

Un teléfono sin fila en `phone_whatsapp_check` no cuenta como validado. El marcador de prospecto se distingue del de cliente. Al tocarlo se ve el nombre, si tiene teléfono y si el WhatsApp está validado, sin validar, o no tiene. Si la zona no tiene ninguna búsqueda `done`, los filtros de prospectos se ven y el mapa no agrega puntos: el texto es “Todavía no hay una búsqueda en esta zona”.

Los clientes que están fuera de la zona siguen la capa actual del mapa. Estos filtros solo afectan lo que cae en la zona elegida.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Radio de cada pedido | Zoom 15 junto con el centro de la celda | El 98 % del gasto del 3 de octubre fue gente de afuera del polígono. El límite solo no lo corrige | Seguir con `lat,lng` pelado y bajar el límite a 20 |
| Límite por tipo | 20. Más alto solo si el pedido lo dice | En 1 km el rubro no llena 100 fichas cuando el radio es la celda. 100 × varios tipos × muchas celdas fue el techo que se llenó | Dejar 100 “por si la zona es densa” |
| Tipos en el POST | Uno por pedido | Varios tipos en la misma llamada multiplican `organizationsPerQueryLimit` y se pagan todos aunque el primero ya alcance | Un POST con todos los tipos, como hoy |
| Orden de la grilla | Una celda, guardar, validar teléfonos nuevos, decidir la siguiente | La meta es de WhatsApp válidos y eso solo se sabe después de validar. Disparar 53 ids en segundos no permite parar | Lanzar todas las celdas en paralelo y cortar la lista al final |
| Tope | Variables de entorno, chequeadas en el servidor antes del POST | La UI se puede saltear. Si el techo supera lugares o dólares, cero llamadas | Confiar en el texto “hasta US$ X” del wizard |
| Ejecución | `execute: true` solo en Buscar | Estimar tiene que ser gratis. El botón es el consentimiento | Un modo dry run de script suelto, desconectado del wizard |
| Prueba de una celda | Obligatorio antes de una zona entera | Si el endpoint viejo ignora el zoom, repetimos la factura. Una celda a límite 20 cuesta como mucho US$ 0,06 | Confiar en la documentación y barrer Florida Oeste |
| Qué se dibuja | Lugares dentro del polígono de jobs `done`, con y sin teléfono | La persona pidió ver los encontrados, no solo los que se pueden tildar para el HSM | Volver a buscar para pintar el mapa; dibujar también los de afuera que ya se pagaron |
| WhatsApp en el mapa | Lectura de `core.phone_whatsapp_check` | La validación ya persiste ahí. No hace falta otra tabla | Guardar el sí/no solo en el estado de React del wizard |
| Filtros anidados | Teléfono debajo de prospectos, WhatsApp debajo de teléfono | Es el recorte que pidió: todos, los que tienen número, y de esos los que tienen WhatsApp | Tres toggles independientes que se pueden combinar en estados vacíos o contradictorios |
| Anillo de US$ 10 y zona de 200 celdas | Siguen | Siguen siendo frenos de la pasada grande. Este spec agrega el tope por corrida y el corte por meta; no los reemplaza | Borrar esos controles porque ahora hay variables de entorno |

---

## Alcance explícito

### Incluido

- Zoom en la coordenada, límite 20 por defecto, un tipo y una celda por pedido.
- Parar al llegar a la meta de WhatsApp válidos, sin pedir el resto de la grilla ni el tipo siguiente.
- Tope por lugares y por dólares, con abort antes de llamar y el cálculo en la respuesta.
- `execute: true` obligatorio para buscar. La estimación no llama a Outscraper.
- Prueba de una celda como compuerta antes de buscar una zona entera.
- Filtros de la zona y marcadores de prospectos (con y sin teléfono, teléfono, WhatsApp validado) más clientes de la zona.

### Fuera de alcance

- Cambiar el precio de Outscraper ni el de la validación de WhatsApp. Este spec deja de pedir celdas de más; no renegocia la validación.
- Enriquecimientos de Outscraper (emails, contactos, redes). Siguen apagados.
- Directorio compartido entre tenants (092). La segunda distribuidora de la misma zona, en esta entrega, vuelve a pagar si busca.
- Volver a dibujar zonas blancas de Places.
- Mostrar en el mapa los lugares que cayeron fuera del polígono.
- Enviar mensajes desde el filtro del mapa. El envío sigue en el wizard, manual.

---

## Orden de implementación

Misma rama de prueba: `feat/outbound-meta-whatsapp`.

| Orden | Repo | Qué |
|---|---|---|
| 1 | `backend-supabase` | Tope, `execute`, límite 20, zoom, un tipo, una celda, corte por meta. Tests sin red |
| 2 | `product-management-app` | El wizard muestra el techo nuevo y manda `execute` solo al buscar. No se busca una zona entera hasta que la prueba de una celda dé bien |
| 3 | `backend-supabase` | Lectura de prospectos de la zona (dentro del polígono, teléfono, WhatsApp) para el mapa |
| 4 | `product-management-app` | Filtros y marcadores |

El paso 2 no se mergea a `main` detrás de una búsqueda real de zona entera. Primero la celda de prueba.

---

## Migración de base de datos

Sin migración de BD. El tope vive en variables de entorno. El límite por pedido ya tiene columna `query_limit` en `core.directory_search_job`. Los prospectos y el WhatsApp se leen de `directory_search_job` y de `core.phone_whatsapp_check`.

Rollback: volver el límite a 100 y sacar el zoom reabre el gasto. No hace falta tocar datos viejos. Los jobs ya pagados quedan como están.

---

## Plan de prueba en CI/CD

En `tests/test_directory_outscraper.py`, con el proveedor falso, sin red:

- El techo usa límite 20 y un solo tipo. Si supera `OUTSCRAPER_MAX_PLACES_PER_RUN` o `OUTSCRAPER_MAX_USD_PER_RUN`, `submit` no se llama y la respuesta trae celdas, tipos, límite y dólares.
- Sin `execute: true`, `submit` no se llama.
- La coordenada que se manda incluye el zoom.
- Después de una celda cuya validación cubre la meta, no hay un segundo `submit`.
- El segundo tipo no se pide si el primero ya cubrió la meta.
- Los tests actuales de anillo (US$ 10) y de zona de 200 celdas siguen verdes.

No hay test de CI contra la API real de Outscraper. Ese hueco lo cubre la prueba humana de una celda. El mapa se cubre con el filtro de la lista (prospecto sin teléfono visible, con teléfono, con WhatsApp) sobre un job fixture, sin mapa de Google, si el componente del filtro se puede probar así. Si no, el mínimo del PR de UI es la prueba humana de abajo.

---

## Plan de prueba humana (antes del PR)

Servicios: backend en `8000`, backoffice en `3000`. Tenant `demo`. No buscar Caballito ni Florida Oeste enteras.

1. Abrir el mapa, elegir una zona chica que ya tenga clientes.
2. En el wizard, llegar a la estimación. Comprobar que muestra celdas, un tipo, límite 20 y el techo en dólares. En el log del backend no tiene que aparecer `google-maps-search` todavía.
3. Bajar a mano el tope de entorno por debajo de ese techo, apretar Buscar y comprobar que no hay llamada y que la pantalla muestra el cálculo.
4. Con el tope holgado, buscar **una celda y un tipo**. El costo máximo es 20 × US$ 0,003. Mirar en la base `returned` e `inside_polygon` de ese job. Si casi todo cae afuera, parar: el zoom no alcanzó.
5. Si la celda dio bien, buscar la zona con una meta chica (por ejemplo 5 WhatsApp). Confirmar que los pedidos HTTP paran al llegar a la meta y que no salen los otros tipos.
6. Cerrar el wizard. En el panel de la zona, con Prospectos prendido y los subfiltros apagados, los puntos aparecen en el mapa, incluidos los sin teléfono.
7. Prender Con teléfono: se ocultan los que no tienen número. Prender WhatsApp validado: quedan solo los que la validación marcó con WhatsApp. Apagar Prospectos: no queda ningún prospecto, aunque los subfiltros hubieran estado prendidos.
8. Prender y apagar Clientes y comprobar que los de la zona aparecen y desaparecen, y que un cliente de otra zona no se esconde por este filtro.

---

## Criterios de aceptación

- Estimar no llama a Outscraper. Buscar sin `execute: true` tampoco.
- Si el techo supera el tope de lugares o de dólares, no hay ninguna llamada y la respuesta muestra el cálculo.
- Cada pedido lleva zoom, un solo tipo y límite 20, salvo un límite explícito mayor.
- Al cubrir la meta de WhatsApp válidos no se piden más celdas ni el tipo siguiente.
- El mapa de la zona muestra los prospectos de adentro, con y sin teléfono, y los cuatro estados de filtro de arriba, anidados como está escrito.
