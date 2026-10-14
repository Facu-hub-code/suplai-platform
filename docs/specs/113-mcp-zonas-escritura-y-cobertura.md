# 113 — Conector: terminar el mapa y administrar zonas

**Estado:** Borrador  
**Fecha:** 2026-10-14  
**Repos:** `backend-supabase` (cierre del 111, tools de escritura, cobertura del bot), `suplai-sales-claude-plugin` (skill), `suplai-platform` (este spec)  
**Rama de este documento:** `feat/mcp-zonas-escritura`  
**Relaciona:** [111](./111-mcp-geozonas-mapa.md), [110](./110-mcp-crud-vendedores-y-notificaciones.md), backend [040](../../../backend-supabase/docs/specs/040-territorio-geo-zonas-vendedores-pdv.md), [017](./017-b2c-fulfillment-delivery-pickup.md).

---

## Objetivo

Cerrar lo que el spec 111 dejó a medias y sumar, en el mismo conector, las operaciones de zona que hoy solo existen en el backoffice. El bot de delivery tiene que usar los mismos polígonos de reparto que el mapa muestra.

### Criterios de aceptación

- El mapa y las tools de zona están habilitados en todas las distribuidoras. No existe `MCP_MAPA_SCHEMAS`. La receta `zonas` nombra `listar_geozonas` y `mapa_zonas`. Las descripciones conservan `geozona_id`, `agrupar_por geozona` y `estado_compra`.
- Los chips del mapa nombran `estado_compra en_riesgo` y `metricas_conversaciones`. Comparar dispara `chip_usado`. Hay un control de pantalla completa. Los chips miden 44 px.
- Crear, agrandar, achicar, asignar vendedores, asignar clientes y desactivar una zona se escribe recién en `confirmar`. El preview no toca la base.
- Una zona nueva armada con el anillo de clientes es el `ST_ConvexHull` de las ubicaciones primarias, cerrado, con el buffer en metros que se pidió.
- Agrandar o achicar usa `ST_Buffer` en metros sobre la geometría guardada. Si el achique deja el polígono vacío, el preview es inválido y no hay `preview_id`.
- Asignar clientes en bulk solo mueve puntos de venta con `geo_zone_asignacion = auto`, con el mismo `ST_Contains` que ya usa el backoffice. Los manuales quedan.
- En Córdoba Frost, un punto dentro de Zona Monte Cristo Colonia o Zona Río Segundo (las dos son `delivery` y están activas) deja de recibir el mensaje de fuera de cobertura. Un punto solo dentro de Zona Carlos Paz o Zona Norte (las dos son `sales`) sigue fuera de reparto.
- El monto de una zona en `mapa_zonas` sigue coincidiendo con `consultar_pedidos` para el mismo id y el mismo período.

---

## Operaciones de mapa

### Las que ya existen

El backoffice y el API ya administran el territorio. El conector, en el 111, solo lee, y en producción esa lectura está apagada: `MCP_MAPA_SCHEMAS` no está definida en el servicio MCP.

| Operación | Dónde está hoy | Qué hace |
|---|---|---|
| Listar zonas y ver el polígono | `GET /{schema}/geo-zones` y `/geojson` | Polígono, tipo, activa, filtro por vendedor |
| Crear, reemplazar, editar, desactivar | `POST`, `PUT`, `PATCH`, `DELETE /geo-zones` | GeoJSON `Polygon` o `MultiPolygon`. La baja es `active = false` |
| Asignar vendedores | `PUT /geo-zones/{id}/vendedores` | Reemplaza filas de `vendedor_geo_zones` |
| Asignar clientes por el punto | `POST /geo-zones/recompute-pdv-assignments` | `ST_Contains` de la ubicación primaria. Solo `geo_zone_asignacion = auto` |
| Leer desde Claude | `listar_geozonas`, `mapa_zonas`, `geozona_id`, `agrupar_por=geozona`, `estado_compra` | Escrito. Oculto si el schema no está en `MCP_MAPA_SCHEMAS` |
| Decir si hay reparto | `quote_delivery` | Mira un solo `delivery_zone_id` de tipo `delivery` |

### Las que este spec agrega

| Operación | Tool | Escritura |
|---|---|---|
| Armar el anillo con los clientes que se nombran y, si hace falta, separarlo N metros | `previsualizar_zona` | `confirmar` inserta en `geo_zones` |
| Agrandar o achicar una zona que ya existe, en metros | `previsualizar_ajustar_zona` | `confirmar` reemplaza `geometry` |
| Elegir qué vendedores cubren la zona | `previsualizar_vendedores_zona` | `confirmar` llama `replace_zone_vendedores` |
| Pasar los clientes a la zona según su geopunto | `previsualizar_asignar_clientes_zona` | `confirmar` corre el recompute auto |
| Desactivar la zona | `previsualizar_desactivar_zona` | `confirmar` pone `active = false` |
| Que el bot cubra todas las zonas `delivery` activas | Sin tool. Cambia `quote_delivery` | No |

---

## Cómo está hoy

### Lo que falta del 111

El código de lectura está en `mcp_server/geozonas_tools.py`, `services/metricas_zona.py` y `mcp_server/ui/mapa-zonas.html`. La allowlist de `mcp_server/mapa_acceso.py` esconde las dos tools y los argumentos, pero deja publicada la receta `mcp_server/guias/zonas.md` y las frases de `geozona_id` en `mcp_server/descripciones.py`. Claude sigue la receta, manda los argumentos igual y recibe «El mapa de zonas no está habilitado en esta distribuidora».

En el HTML, el segundo chip no nombra `estado_compra en_riesgo`, el cuarto no nombra `metricas_conversaciones`, comparar no emite `chip_usado`, la pantalla completa se pide sola al abrir y los botones miden 36 px. Esos huecos, la receta y las descripciones se cierran en esta entrega. El iframe viaja en cada operación de zona y la página queda oculta hasta que hay zonas para pintar.

`GOOGLE_MAPS_API_KEY` y `GOOGLE_MAPS_MAP_ID` no están en el servicio MCP de producción. Sin esas variables el iframe no pinta aunque el schema entre en la allowlist.

### Córdoba Frost, medido el 2026-10-14

Cinco zonas activas. Las tres de reparto y las dos de venta tienen días de entrega.

| Id | Nombre | Tipo | Km² | Vértices | Clientes en la zona |
|---:|---|---|---:|---:|---:|
| 1 | Zona Sur | delivery | 200 | 24 | 20 |
| 4 | Zona Monte Cristo Colonia | delivery | 114 | 30 | 0 |
| 5 | Zona Río Segundo | delivery | 181 | 8 | 0 |
| 2 | Zona Norte: Daniel | sales | 213 | 17 | 0 |
| 3 | Zona Carlos Paz | sales | 192 | 30 | 0 |

`reglas_negocio.order_fulfillment.delivery.delivery_zone_id` es `1`. `quote_delivery` hace `ST_Contains` solo contra esa fila. Monte Cristo y Río Segundo están dibujadas, activas y marcadas `delivery`, y el bot no las consulta. Si el punto cae afuera de Zona Sur, la tool devuelve `OUT_OF_DELIVERY_ZONE` y el agente lee `out_of_zone_message`, que dice que el reparto cubre Córdoba Capital y alrededores.

De 902 clientes de cartera, 84 tienen ubicación primaria. 66 caen dentro de algún polígono. 7 quedan a menos de 3 km de alguno, afuera. Río Segundo tiene 8 vértices para 181 km²: un anillo así deja pueblos de al lado afuera aunque el nombre de la zona los sugiera.

La agenda fija (`fixed_delivery_schedule`) no está prendida. El mensaje que ve el cliente de WhatsApp sale de `quote_delivery`, no de `resolve_delivery_schedule`.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Qué cuenta como cubierto para el bot | La unión de las `geo_zones` con `zone_type = delivery` y `active`. El nombre que vuelve es el de la zona que contiene el punto. Si hay dos, gana la de menor área. Desaparece el error `DELIVERY_ZONE_AMBIGUOUS` de cuando hay varias zonas y ningún `delivery_zone_id`. | El supervisor dibujó varias zonas de reparto y el bot solo lee `delivery_zone_id`. En Frost ese id es Zona Sur, y Monte Cristo y Río Segundo quedan mudas. | Seguir con un solo id y pedirle que fusione los polígonos a mano. El mapa ya las muestra como reparto. |
| Zonas `sales` | No entran en `quote_delivery` | Carlos Paz y Zona Norte son territorio de visita. Meterlas en el reparto prometería envío donde el tipo de zona dice venta. | Tratar cualquier polígono activo como cobertura. |
| `delivery_zone_id` | Deja de ser el único polígono. Sigue siendo un dato de configuración, no el filtro de `ST_Contains`. El origen del precio sigue siendo `delivery.origin`. | El costo se calcula desde el depósito, no desde el centro de la zona. | Borrar el campo en esta entrega. Otros tenants lo tienen cargado y el preview de fulfillment lo muestra. |
| Mensaje de fuera de cobertura | Se usa solo cuando el punto no cae en ninguna zona `delivery` activa. El texto lo sigue eligiendo el tenant. | Con la unión, Monte Cristo deja de disparar el mensaje. El texto de Frost habla de Capital: corregirlo es configuración, no código. | Reescribir el mensaje desde el conector. |
| Anillo de clientes | `ST_ConvexHull` de las ubicaciones primarias, más `ST_Buffer` en metros si pidieron margen. Mínimo 3 puntos. El anillo se cierra. | Es estable y se puede explicar: el polígono más chico que envuelve esos clientes, y N metros de más. | Que Claude mande vértices GeoJSON. Se equivoca de anillo y choca con el tope de 10.000 vértices del modelo. Un hull cóncavo cambia de forma con pocos puntos. |
| Agrandar y achicar | `ST_Buffer` de la geometría guardada, en metros, sobre `geography`. Positivo agranda, negativo achica. | Es la operación que pide el supervisor cuando el pueblo de al lado quedó justo afuera. No rehace la zona desde cero. | Redibujar el hull cada vez. Pierde el polígono que alguien dibujó en el backoffice. |
| Achique vacío | Preview inválido, sin `preview_id` | Confirmar un polígono vacío apagaría el reparto sin decirlo. | Guardar la zona y dejar que PostGIS la invalide. |
| Asignación de clientes | El recompute que ya existe: `ST_Contains` de `client_locations` primaria, menor área, y no toca `geo_zone_asignacion = manual` | Es la misma regla que el botón del backoffice. El bulk por latitud y longitud ya está escrito. | Un `UPDATE` que pise también los manuales. Una asignación a mano dejaría de respetarse. |
| Escritura | Preview y `confirmar`, igual que vendedores. Las funciones son las de `GeoZonesService` y `TerritorioService`. | El conector no escribe geometría en la primera llamada. El backoffice y Claude quedan en la misma regla. | Un tool que haga el `INSERT` directo. |
| Scope | `vendedores:escribir` para las cinco tools de escritura. La lectura sigue en `pedidos:leer`. | El territorio ya vive con los vendedores (spec 040) y el scope existe. Un scope `zonas:escribir` obliga a otro consentimiento. | Scope nuevo. |
| Receta | El tema `zonas` nombra las tools en todas las distribuidoras. Las descripciones conservan `geozona_id`, `agrupar_por geozona` y `estado_compra`. | Sin allowlist no hay tools ocultas que la receta pudiera nombrar de más. | Una receta corta que diga que el mapa no está habilitado. |
| Allowlist | No hay. `MCP_MAPA_SCHEMAS` se elimina. Todas las distribuidoras ven el mapa y las tools de zona. | El filtro dejaba a Campi y a Frost sin el mapa que ya usan en el backoffice. | Abrir de a un schema (`esekau`, después Frost). |
| Vértices a mano | Fuera de esta entrega | El backoffice ya dibuja el polígono. El conector agrega el anillo y el buffer. | Un tool que reciba el anillo coordenada por coordenada. |
| Iframe | `listar_geozonas`, `mapa_zonas`, las cinco previsualizaciones y `confirmar` de una zona devuelven el mapa. El HTML pinta el polígono propuesto en azul. | El supervisor tiene que ver el anillo antes de decir que sí, no solo el texto. | Mostrar el mapa solo cuando piden `mapa_zonas`. |
| Pantalla de permisos | Cuatro frases: ver, editar, ensayar y reportar. `offline_access` no se lista. | Claude pide todos los scopes y la pantalla era un recuadro por permiso. | Un scope nuevo de zonas, que alargaba el consentimiento otra vez. |

### Preview de cada tool

Todas devuelven `valido`, un resumen en castellano y, si `valido` es true, `preview_id`. `confirmar` solo recibe ese id.

`previsualizar_zona`. Entrada: `nombre`, `cliente_ids` (mínimo 3 con ubicación primaria), `zone_type` (`delivery` o `sales`), `metros` opcional (default 0, no negativo en el alta), `dias_de_entrega` opcional. El preview dice cuántos clientes entraron al hull, cuántos se descartaron por no tener punto, el área en km² y el tipo. Si el tipo es `delivery`, el resumen dice que el bot la va a tomar como zona de reparto.

`previsualizar_ajustar_zona`. Entrada: `geozona_id`, `metros` distinto de 0. El preview muestra el área anterior y la nueva. Negativo que vacía el polígono: `valido: false`.

`previsualizar_vendedores_zona`. Entrada: `geozona_id` y `vendedor_ids`. Reemplaza la lista, como el `PUT` del API. El preview nombra a quién suma y a quién saca.

`previsualizar_asignar_clientes_zona`. Sin id, recorre todas las zonas activas, igual que el endpoint de recompute. Con `geozona_id`, el preview igual muestra el efecto global del recompute y resalta cuántos quedan en esa zona: el algoritmo elige la zona de menor área, no fuerza el id. El preview cuenta cuántos puntos `auto` cambiarían de zona y cuántos `manual` no se tocan.

`previsualizar_desactivar_zona`. Entrada: `geozona_id`. El preview dice que el bot deja de cubrirla si era `delivery`, y que la cartera y los vendedores quedan vinculados a una zona inactiva.

---

## Alcance

### Incluido

- Cierre del 111: receta y descripciones alineadas con la allowlist, chips, `chip_usado` al comparar, control de pantalla completa, alto de 44 px, y los tres tests que faltan.
- Las cinco tools de escritura y la receta `zonas` actualizada para quien está en la allowlist.
- `quote_delivery` sobre la unión de zonas `delivery` activas, devolviendo el nombre de la zona que contuvo el punto.
- Grants de escritura para `mcp_connector`.
- Una línea en la skill del plugin.

### Fuera de alcance

- Dibujar vértices a mano desde el chat.
- Incluir zonas `sales` en la cobertura de reparto.
- Cambiar el texto `out_of_zone_message` de Córdoba Frost. Cuando el punto entre en una zona `delivery`, ese texto deja de usarse.
- `resolve_delivery_schedule`. Sigue exigiendo `dias_de_entrega`. Frost no lo tiene prendido.
- Pisar asignaciones `manual`.
- Reabrir `metricas_whatsapp` por zona.
- Habilitar el mapa para todos los tenants antes de las capturas de `esekau`.
- `GOOGLE_MAPS_API_KEY` en el repo. Va en el servicio MCP, con el referrer del 111.

---

## Orden de implementación

| Orden | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `suplai-platform` | `feat/mcp-zonas-escritura` | Este spec. |
| 2 | `backend-supabase` | `feat/mcp-zonas-escritura` | Primero el cierre del 111 (receta, descripciones, HTML, tests). Después los grants. Después el servicio de anillo y buffer. Después las tools. Al final `quote_delivery`. |
| 3 | `suplai-sales-claude-plugin` | `feat/mcp-zonas-escritura` | La skill de `zonas` nombra las tools de preview y recuerda que `confirmar` escribe. |
| 4 | Operación | — | Key y Map ID de Google Maps en el servicio MCP, para que el iframe pinte en todas las distribuidoras. |

El agente no cambia: ya muestra el `message` de `quote_delivery`.

---

## Migración de base de datos

No hay tablas ni columnas nuevas.

`GRANT` para `mcp_connector`, en los schemas activos y en `grant_mcp_connector_on_schema`:

- `INSERT`, `UPDATE` sobre `{schema}.geo_zones`.
- `SELECT`, `INSERT`, `UPDATE`, `DELETE` sobre `{schema}.vendedor_geo_zones`. El `DELETE` es el que ya hace `replace_zone_vendedores` al reemplazar la lista.
- `UPDATE` sobre `{schema}.puntos_venta` (`geo_zone_id` y `geo_zone_asignacion`). El `SELECT` ya está.

Rollback: `REVOKE` de esos privilegios. Las tools de escritura fallan. La lectura del 111 y el API del backoffice siguen.

Riesgo: bajo. No reescribe polígonos al aplicar el grant. El primer polígono cambia cuando alguien confirma un preview.

---

## Plan de prueba en CI/CD

En `backend-supabase`, junto a `tests/test_mcp_geozonas.py`:

- Sin variable de allowlist, `mapa_habilitado` es true para `del_corro` y para `cordoba_frost`. El listado conserva `mapa_zonas`, `previsualizar_zona` y el argumento `geozona_id`. La receta nombra las tools.
- El monto y la cantidad de una zona en el armado de `mapa_zonas` son los de `consultar_pedidos` con el mismo id y el mismo período.
- La suma de `agrupar_por=geozona`, incluida la fila «Sin zona», cierra con `total_pedidos`.
- El catálogo incluye `listar_geozonas` y `mapa_zonas` para cualquier schema.
- Hull de tres puntos: el polígono contiene los tres. Un punto a 100 m afuera queda afuera con `metros = 0` y adentro con `metros = 200`.
- Buffer negativo que vacía el polígono: `valido` es false y no hay `preview_id`.
- Recompute: un punto `auto` dentro del polígono cambia de zona; uno `manual` no.
- `quote_delivery` con dos zonas `delivery`: el punto de la segunda devuelve `in_zone` true y el nombre de la segunda. Un punto solo dentro de una zona `sales` devuelve `OUT_OF_DELIVERY_ZONE`.
- Los checks de pedidos, pantallas y fulfillment que ya existen quedan verdes.

---

## Plan de prueba humana

Backoffice en `3000`, backend en `8000`, MCP en `8100`. No hace falta `MCP_MAPA_SCHEMAS`. La escritura se confirma solo en una zona de prueba, y se desactiva al final. En Frost no se confirma ninguna escritura.

1. En Campi y en Córdoba Frost, pedir «mostrame las zonas». Claude llama `listar_geozonas` en las dos. La receta nombra las tools.
2. «¿cómo viene la zona …?» filtra por `geozona_id`. «Mostrame el mapa» carga polígonos, sin error de CSP. El chip de recuperar nombra `en_riesgo`. El del agente nombra `metricas_conversaciones`. Comparar dos zonas y accionar llegan a un mensaje, sin confirmar envío.
3. En el schema de prueba, nombrar tres clientes con coordenada y pedir una zona de reparto con 500 metros de margen. El preview muestra el área. Recién el sí escribe la fila. El mapa del backoffice muestra el polígono nuevo.
4. Pedir achicar esa zona 5 km. Si el preview dice que desaparece, no hay botón de confirmar útil: `valido` es false.
5. Asignar un vendedor y correr la asignación de clientes. Un cliente `manual` no se mueve.
6. Desactivar la zona. `quote_delivery` de un punto que solo caía ahí vuelve a decir fuera de zona.
7. Recién con eso visto, en staging, contra una copia o con un punto de prueba de Frost: una coordenada dentro de Zona Monte Cristo Colonia cotiza adentro y el nombre de la zona es ese. Una coordenada dentro solo de Zona Carlos Paz sigue afuera. No se confirma ninguna escritura sobre Frost en esta prueba.
