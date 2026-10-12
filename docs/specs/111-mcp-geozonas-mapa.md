# 111 — Conector: geozona como dimensión y mapa comercial

**Estado:** Borrador  
**Fecha:** 2026-10-12  
**Repos:** `backend-supabase` (servicio compartido, tools, recurso UI, grants), `suplai-sales-claude-plugin` (skill de una línea), `suplai-platform` (este spec y cuatro filas en el 073)  
**Rama de este documento:** `feat/mcp-vendedores-notificaciones`  
**Rama de implementación:** `feat/mcp-vendedores-notificaciones` en los tres repos, el mismo PR que vendedores.  
**Relaciona:** [094](./094-claude-mcp-manual.md)–[110](./110-mcp-crud-vendedores-y-notificaciones.md), [073](./073-mixpanel-analytics.md), [088](./088-clientes-vs-prospectos.md), backend [040](../../../backend-supabase/docs/specs/040-territorio-geo-zonas-vendedores-pdv.md). Catálogo: `backend-supabase/docs/mcp-tools-visibles.md`. Spec de MCP Apps: `modelcontextprotocol/ext-apps` `specification/2026-01-26/apps.mdx`. SDK: `App.sendMessage` y `App.updateModelContext` en `src/app.ts`.

---

## Objetivo

La geozona es una dimensión de las tools que ya calculan ventas, conversaciones y clientes. El mapa es la capa para ver dónde pasa cada cosa y elegir qué analizar. El análisis lo hace Claude con esas tools, filtradas por `geozona_id`. El mapa y las tools leen las mismas funciones. No hay un segundo motor de métricas.

### Criterios de aceptación

- "¿Cómo viene la zona norte?", sin pedir mapa: Claude llama `listar_geozonas`, después `consultar_pedidos` y `metricas_conversaciones` con `geozona_id`, y `explorar_clientes` si la pregunta es de clientes. El mapa no aparece.
- "Mostrame el mapa de mis zonas": aparece el mapa. Un clic en una zona y un chip dejan en el chat un pedido en lenguaje natural con id, nombre y período. Claude responde con las tools existentes. La app no muestra un análisis propio.
- "Accionar sobre los clientes en riesgo" termina en una previsualización de etiqueta o de envío. La app no ejecuta la acción.
- El monto y la cantidad de una zona en `mapa_zonas` coinciden con `consultar_pedidos` para el mismo `geozona_id` y el mismo período.
- Sin los argumentos nuevos, `consultar_pedidos`, `metricas_conversaciones` y `explorar_clientes` responden como hoy.
- `metricas_whatsapp` no cambia de firma ni de números.
- En el tenant de prueba, la consola del mapa no muestra bloqueos de CSP.
- Los cuatro eventos de Mixpanel llegan a Live View, sin teléfono ni nombre de comercio.
- Con la versión nueva, la pantalla de admin marca reconectar y lista `listar_geozonas` y `mapa_zonas`.

---

## Cómo está hoy

### Tools y convenciones

El conector vive en `backend-supabase/mcp_server`. Las descripciones largas están en `mcp_server/descripciones.py` (el admin puede pisarlas con `public.mcp_tool_textos`). Cada una cierra con "Cuándo no:" y nombra la tool que sí corresponde.

| Tool | Handler | Cálculo | Fechas y página |
|---|---|---|---|
| `consultar_pedidos` | `mcp_server/main.py` | `services/mcp_pedidos_query.py` `consultar_pedidos` y `build_filters`, sobre el pool del MCP | `fecha_desde` / `fecha_hasta`. Si faltan, hasta hoy y 30 días hacia atrás (`DEFAULT_DAYS = 30`). `agrupar_por`: `pedido` (default) o `cliente`. `limite` default 20, máximo 100. `pedido_id` ignora el resto de los filtros. Sin estado, excluye `abierto`. |
| `metricas_conversaciones` | `mcp_server/estrategias_tools.py` | Resumen: `services/mcp_estrategias.py` `metricas_conversaciones` → `services/metricas_service.py` `get_metricas_agente`. Kanban: `services/mcp_operacion.py` `reporte_kanban` → `get_pipeline`. | Las dos fechas o ninguna. El resumen, si no hay fechas, usa 29 días (`ultimos_30_dias`). El kanban, si no hay fechas, usa 30. `vista`: `resumen`, `kanban` o `ambas`. |
| `explorar_clientes` | `mcp_server/pantallas_tools.py` | `services/mcp_pantallas.py` `explorar_clientes` / `fila_cliente`. La zona que ya muestra es el nombre `geo_zone_name`. | `pagina` desde 1, `tamano` default 50, máximo 100. No tiene fechas. |
| `buscar_clientes` | catálogo de clientes | Resuelve un comercio por nombre, razón social o código. | No se toca en esta entrega. |
| `metricas_whatsapp` | `mcp_server/consolidar_tools.py` | `salud_whatsapp` más `services/mcp_plantillas.py` `metricas_plantillas` → `template_metrics`. | Default 30 días. Tope interno de 89. |
| `guia_suplai` | `mcp_server/guia_tools.py` | Un markdown por tema en `mcp_server/guias/`. Frontmatter `tema` y `titulo`. Cuerpo con las cinco secciones fijas. | Sin tema, el índice. Con tema, una receta. |

`agrupar_por` hoy es el enum `["pedido", "cliente"]` (`tests/test_mcp_tool_schema.py`). El default sigue siendo `pedido`.

### Dónde se calcula cada número

El monto y la cantidad de pedidos ya están en un solo lugar: `build_filters` + el `SELECT` de `consultar_pedidos`. El mapa tiene que llamar esa función. El SQL de stats de zona (`data_access/geo_zones.py`, categorías VIP / CHURN_RISK / LOST y solo `confirmado`/`descargado`) es otra definición y no se reutiliza.

Las charlas del resumen salen de `get_metricas_agente` (envíos de plantilla, ventana de 48 h, respuestas en `core.conversation_events`). Ese SQL no filtra zona. El pipeline del kanban sí acepta `geo_zone_id` (`services/conversaciones_pipeline.py`, predicado `pv.geo_zone_id`), pero `reporte_kanban` no se lo pasa.

La frecuencia en días ya existe como función pura: `median_days_between_orders` en `services/field_combo_utils.py` (mediana de los días entre pedidos ordenados). `is_client_inactive` es otra regla (2× la mediana, o 45 días) y no se usa para `estado_compra`.

### Geozonas y coordenadas

Medido el 2026-10-12 en Suplai-east, schema `demo` como muestra de columnas (el resto de los tenants activos tiene las mismas tablas):

| Dato | Dónde | Tipo |
|---|---|---|
| Polígono | `{schema}.geo_zones.geometry` | `geometry`, `MULTIPOLYGON`, SRID 4326. También `id` (int8), `name`, `active`, `zone_type`. |
| Zona del cliente | `{schema}.puntos_venta.geo_zone_id` | int8, más `geo_zone_asignacion` (`auto` o `manual`). El cliente llega por `clients.pdv_id`. |
| Coordenada | `{schema}.client_locations` | `latitude` y `longitude` (float8) y `location` (geometry). Se usa la fila `is_primary = true`. |

**Cómo se asigna.** La dimensión de esta entrega es el valor guardado en `puntos_venta.geo_zone_id`. La asignación automática lo escribe con `ST_Contains` de la ubicación primaria contra zonas `active`, el polígono de menor área, y el día de visita cuando la zona lo tiene (`data_access/territorio.py`, `RECOMPUTE_ALL_AUTO_PDVS_SQL`). La asignación `manual` queda aunque el punto haya quedado afuera del polígono. Grupos, pipeline y el nombre que ya devuelve `explorar_clientes` leen ese id.

El stats de zona del backoffice también cuenta un cliente si el punto primario cae adentro aunque el id guardado sea otro. Esa lectura puede poner el mismo cliente en dos zonas. Estas tools no la usan.

**Cobertura** (`lifecycle = 'client'`, ubicación primaria, 2026-10-12):

| Schema | Clientes | Con coordenadas | Con zona | Zonas activas |
|---|---:|---:|---:|---:|
| `esekau` | 239 | 239 (100 %) | 239 (100 %) | 5 |
| `demo` | 109 | 3 (2,8 %) | 0 (0 %) | 4 |
| `almaro` | 149 | 141 (94,6 %) | 22 (14,8 %) | — |
| `del_corro` | 6.462 | 4.453 (68,9 %) | 5.700 (88,2 %) | 138 |

El tenant de prueba del mapa es `esekau`: todas las zonas y todos los puntos están. `demo` tiene polígonos y casi ningún cliente ubicado, así que el mapa sale vacío. `del_corro` es el caso de volumen (cerca del tope de 5.000 marcadores, 138 zonas).

### MCP Apps

`mcp_server/ui_apps.py` y `mcp_server/ui/app.html` son el experimento anterior. `register_ui` no se llama desde `main.py`. Ese HTML no se vuelve a registrar. El mapa es un recurso nuevo.

Nombres verificados en la spec `2026-01-26` y en el SDK (`src/app.ts`), que es el que ya usa `app.html`:

| Qué | Método | Notas |
|---|---|---|
| Recurso | URI `ui://…`, MIME `text/html;profile=mcp-app` | El tool lo apunta con `_meta.ui.resourceUri`. El formato plano `_meta["ui/resourceUri"]` está deprecado. |
| CSP del recurso | `_meta.ui.csp`: `connectDomains`, `resourceDomains`, `frameDomains`, `baseUriDomains` | El host arma `connect-src` con `connectDomains` y `script-src` / `style-src` / `img-src` / `font-src` con `resourceDomains`. Acepta `https://*.ejemplo.com`. |
| Dominio del iframe | `_meta.ui.domain` | `dominio_claude()` ya lo calcula: SHA-256 de la URL pública del MCP, 32 hex, más `.claudemcpcontent.com`. |
| Arranque | `ui/initialize` | `protocolVersion: "2026-01-26"`. Después la vista manda `ui/notifications/initialized`. |
| Resultado | `ui/notifications/tool-result` | El host lo manda con el `CallToolResult`. La app lee `structuredContent`. |
| Argumentos y tema | `ui/notifications/tool-input`, `ui/notifications/host-context-changed` | Tema, safe area y nombre de la tool. |
| Mensaje al chat | `ui/message` | SDK: `App.sendMessage({ role: "user", content: ContentBlock[] })`. El contenido es un array de bloques. |
| Contexto del modelo | `ui/update-model-context` | SDK: `App.updateModelContext({ content, structuredContent })`. Pisa el contexto anterior. El host lo adjunta en el próximo turno, incluido el `ui/message` que sigue. No dispara una respuesta por sí solo. |
| Alto y modo | `ui/notifications/size-changed`, `ui/request-display-mode` | Modos `inline` y `fullscreen`. |

`tools/call` existe y el HTML viejo lo usa para recargar pantallas. El mapa no lo usa.

### WhatsApp por zona

`metricas_whatsapp` muestra la salud del número y, por plantilla, enviados, entregados y leídos. Esos enviados salen de Meta (`template_metrics`: `sent` / `delivered` / `read`). El campo `enviados_registrados` también es un total por plantilla, no por comercio.

Sí hay un registro propio por destinatario: `{schema}.envios_plantillas` (`session_id` es el teléfono, `template_name`, `created_at`, `delivery_status`). Con eso se podría filtrar envíos por la zona del cliente. No es el número que la tool muestra hoy. Sumarle `geozona_id` o bien no cambiaría el desglose de Meta, o bien reemplazaría esa métrica por otra. **En esta entrega `metricas_whatsapp` no se toca.** Si más adelante se quiere el corte por zona, es una tool o una vista nueva sobre `envios_plantillas`, con el mismo predicado de zona, y se decide aparte.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Qué es la geozona | Una dimensión: `geozona_id` opcional y, en pedidos, `agrupar_por = geozona` | El supervisor pregunta por una zona con las tools que ya sabe usar. El mapa solo elige la zona. | Un servicio nuevo que recalcule ventas, charlas y clientes para el mapa. |
| Id de zona | `puntos_venta.geo_zone_id` del `clients.pdv_id` | Es el valor que ya muestran grupos, el pipeline y `explorar_clientes`. La asignación auto o manual ya quedó escrita ahí. | Volver a calcular `ST_Contains` en cada lectura. Un cliente manual, o un punto en el borde de dos polígonos, no coincidiría con el backoffice. |
| Stats de zona del backoffice | No se llama | Mezcla el id guardado con el punto dentro del polígono y clasifica VIP / riesgo / perdido a 45 y 150 días. | Reutilizar `GET /geo-zones/{id}/stats`. |
| Monto y cantidad | `build_filters` + el agregado de `consultar_pedidos` | El test de coincidencia exige el mismo total. Sin estado, sigue afuera `abierto`. | Contar solo `confirmado` y `descargado`, que es lo que hace el mapa del backoffice. |
| `estado_compra` | Función pura nueva, con la mediana que ya existe | La regla (1,5×, 3×, 60 días, menos de 3 pedidos) no es `is_client_inactive` ni las categorías del mapa. | Llamar `get_client_frequency` por cliente. Es un query por fila y aplica la regla de 2× / 45 días. |
| Frecuencia | `median_days_between_orders` sobre pedidos `confirmado` y `descargado`, `deleted_at IS NULL` | Es la mediana que Field ya usa. Se excluye el borrado para no inflar el hábito. | La `frecuencia` de métricas comerciales, que es la cantidad de pedidos del período, no un intervalo en días. |
| Texto al modelo en el mapa | Un resumen corto por zona en `content`. Polígonos, puntos y estados en `structuredContent`. | El modelo tiene que ofrecer dos o tres análisis, no redactar el diagnóstico con el GeoJSON. | Devolver el GeoJSON también en el texto. |
| La app no llama tools | `ui/update-model-context` y después `ui/message` | El análisis y la previsualización los hace Claude con las tools que ya auditan y piden confirmación. | `tools/call` a `consultar_pedidos` o a `previsualizar_agenda` desde el iframe. |
| Toggle de métrica | Cada zona trae monto, pedidos y clientes activos, con su variación. `metrica` solo elige el color. | El toggle no necesita otro round-trip ni otra fórmula. | Volver a llamar `mapa_zonas` al cambiar el toggle. |
| `metricas_whatsapp` | Sin `geozona_id` | El número visible es de Meta, a nivel plantilla. El registro por teléfono existe y queda para una decisión posterior. | Filtrar esa tool y mostrar un total que Meta no parte por zona. |
| Defaults | Los argumentos nuevos son opcionales. Los defaults de fechas, `agrupar_por`, `limite`, `pagina` y `tamano` quedan. `pedido_id` sigue ignorando los demás filtros, incluido `geozona_id`. | El enum gana el valor `geozona` y el schema test se actualiza. Quien no lo manda sigue en `pedido` y en `limite` 20. | Subir el `limite` default para que entren las 138 zonas de Del Corro. El mapa no usa ese límite: devuelve todas las zonas activas. |
| Ventana del mapa | La de `consultar_pedidos`: hoy y 30 días hacia atrás si no hay fechas. | El criterio de coincidencia se prueba sin pasar fechas. | Unificar con los 29 días del resumen de conversaciones. Ese default no se toca. |
| Marcadores y cobertura | `clients.lifecycle = 'client'` | Es una consulta nueva de cartera. | Meter prospectos en el mapa. Los pedidos no filtran lifecycle: si no, el total dejaría de coincidir con `consultar_pedidos`. |
| UI vieja | Recurso nuevo `ui://suplai/mapa-zonas.html` | El HTML anterior está deprecado y no está registrado. | Reabrir `ui://suplai/app.html`. |
| Quién lee la base | El pool del MCP (`mcp_connector`, `statement_cache_size=0`, `max_size=2`) | `consultar_pedidos` ya corre ahí. El mapa usa la misma conexión. | Abrir el pool de la API desde el proceso MCP. |
| Alta | Allowlist `MCP_MAPA_SCHEMAS` | Primero `esekau`, con capturas. Fuera de la lista, las tools nuevas no están en `tools/list` y los argumentos nuevos tampoco. El handler responde que la función no está habilitada en esa distribuidora. | Publicar los filtros para todos los tenants el día del deploy. |
| Conector | Scope existente `pedidos:leer` para `listar_geozonas` y `mapa_zonas`. Sin scope nuevo. | Listar zonas y ver el mapa es lectura. El consentimiento no cambia. La versión sí, para el aviso de reconectar. | Un scope `mapa:leer` que obligue a reconectar para aceptar un permiso. |

### `estado_compra`

Vive en un módulo compartido, por ejemplo `services/estado_compra.py`. Constantes:

| Constante | Valor | Uso |
|---|---|---|
| `MIN_PEDIDOS` | 3 | Por debajo, el estado es `nuevo`. |
| `FACTOR_ACTIVO` | 1,5 | Tope de días para seguir `activo`. |
| `FACTOR_DORMIDO` | 3 | Por encima, `dormido`. |
| `DIAS_DORMIDO` | 60 | También `dormido`, aunque el ciclo sea más largo. |

`frecuencia_habitual_dias` es `median_days_between_orders`. Los pedidos son `confirmado` y `descargado`, con `deleted_at IS NULL`, sin recortar por el período del mapa. `dias_desde_ultimo_pedido` usa el mismo conjunto.

Orden, y el primero que aplica gana:

1. Menos de 3 pedidos, o mediana nula o ≤ 0 → `nuevo`. Un cliente con un solo pedido hace 90 días sigue en `nuevo`.
2. Los días superan `FACTOR_DORMIDO × frecuencia` o superan `DIAS_DORMIDO` → `dormido`.
3. Los días superan `FACTOR_ACTIVO × frecuencia` → `en_riesgo`.
4. El resto → `activo`.

Un cliente que compra cada 90 días entra en `dormido` a los 61, aunque siga dentro de 1,5 ciclos. Es la regla pedida. Las cuatro constantes se pueden cambiar sin tocar el mapa.

La mediana en SQL (`percentile_cont`) se prueba contra la función de Python con la misma lista de fechas. `explorar_clientes` y `mapa_zonas` llaman el mismo clasificador. El filtro `estado_compra` corre en el `WHERE`, antes de paginar, para que `total` sea el de esa página.

Valores del filtro en `explorar_clientes`: `todos` (default), `activo`, `en_riesgo`, `dormido`. `nuevo` no es un filtro de esta entrega: el estado igual viaja en la fila cuando corresponde, así no se esconde.

---

## Tools

### 1. `consultar_pedidos`

Argumento nuevo `geozona_id` (entero, opcional). `agrupar_por` acepta `geozona` además de `pedido` y `cliente`.

Con `geozona`, cada fila trae `geozona_id`, `geozona` (nombre, o "Sin zona" si el punto de venta no tiene), `cantidad_pedidos` y `monto`. Entra en `limite` y `hay_mas` como el agrupado por cliente. La suma de los grupos, siguiendo las páginas, cierra con `total_pedidos` y `monto_total`.

Descripción, una línea más: "geozona_id filtra una zona. agrupar_por geozona resume cantidad y monto por zona." El "Cuándo no:" actual queda.

### 2. `metricas_conversaciones`

Argumento nuevo `geozona_id` (opcional). Si no viene, el SQL del resumen es el de hoy. Si viene, un `EXISTS` hacia el cliente del teléfono y `puntos_venta.geo_zone_id`. No es un `JOIN` que duplique sesiones. El kanban le pasa el mismo id a `get_pipeline`, que ya filtra por esa columna. Fechas y `vista` no cambian.

Descripción, una línea más: "geozona_id deja solo la zona de ese punto de venta."

### 3. `explorar_clientes`

`geozona_id` opcional y `estado_compra` con default `todos`. Cada fila suma, sin renombrar `zona`:

- `geozona_id`
- `dias_desde_ultimo_pedido`
- `frecuencia_habitual_dias`
- `estado_compra`

`pagina` y `tamano` siguen en 1 y 50. Descripción, una línea más: "geozona_id filtra la zona. estado_compra: todos, activo, en_riesgo o dormido."

### 4. `listar_geozonas`

Sin UI. Scope `pedidos:leer`. Argumento opcional `texto` (coincidencia por nombre). Devuelve zonas `active`: `id`, `nombre`, `clientes` (`lifecycle = 'client'` con ese `geo_zone_id`) y `con_coordenadas` (de esos, los que tienen ubicación primaria).

Descripción: "Resolvé a qué zona se refiere la persona antes de filtrar otras tools. Cuándo no: no da ventas ni métricas. Para eso, consultar_pedidos o metricas_conversaciones con geozona_id."

### 5. `mapa_zonas`

Con UI. Scope `pedidos:leer`. Entrada: `fecha_desde`, `fecha_hasta` (el default de `consultar_pedidos`), `metrica` opcional (`monto` default, `pedidos`, `clientes_activos`) y `geozona_ids` opcional.

Salida, toda del servicio compartido:

1. **Por geozona activa**, más una fila "Sin zona" si hay clientes de cartera sin id. `id`, `nombre`, polígono simplificado (`ST_SimplifyPreserveTopology` y después GeoJSON), las tres métricas y la variación de cada una contra el período anterior de la misma cantidad de días (el anterior termina el día previo a `fecha_desde`; si el anterior es 0, la variación va null). Conteos `activo`, `en_riesgo`, `dormido`, `nuevo`.
2. **Clientes con coordenadas:** `id`, `nombre`, `lat`, `lng`, `geozona_id`, `estado_compra`, `monto` del período. Tope 5.000. Si hay más, `clientes` viene vacío, `clientes_omitidos: true`, y siguen los agregados por zona.
3. **Cobertura:** `clientes`, `con_coordenadas`, `sin_zona`.

`content` (lo que lee el modelo) es solo el resumen: período, métrica elegida, una línea de números por zona y la cobertura. Sin adjetivos ni conclusión. `structuredContent` es el payload del mapa. La descripción de la tool le dice al modelo que, después de mostrarlo, ofrezca dos o tres análisis concretos y pregunte cuál quiere.

Descripción: "Muestra dónde está pasando cada cosa para elegir qué analizar. Después de mostrarlo, ofrecé dos o tres análisis concretos y preguntá cuál quiere. Cuándo no: no sirve para concluir sobre una zona. Para analizar, usá consultar_pedidos, metricas_conversaciones y explorar_clientes con geozona_id."

El período anterior y el actual pasan por `build_filters`. `clientes_activos` es el conteo `estado_compra = activo` de esa zona, el mismo clasificador.

---

## Interfaz

Archivo nuevo `mcp_server/ui/mapa-zonas.html`. El servidor lo registra con `@mcp.resource` solo junto con la tool, para los schemas de la allowlist. Mismo lenguaje que `app.html`: verde `#1F8A0C` (en oscuro `#39FF14`), logos que ya están en `mcp_server/ui/`, variables de tema del host, bordes y chips de 44 px.

1. Google Maps JavaScript API con Map ID de Cloud (`GOOGLE_MAPS_MAP_ID`). El estilo de marca se configura en Google Cloud. Con Map ID, el array `styles` del script no pinta el mapa.
2. Polígonos coloreados por la métrica elegida y por el signo de su variación (verde si sube, gris si no hay base, ámbar si baja). Hover: nombre, valor y variación.
3. Marcadores con clustering. El clusterer va inline en el HTML, sin CDN. Color por estado: activo verde, en riesgo ámbar, dormido gris, nuevo azul. Toggles: mostrar u ocultar clientes, y cambiar la métrica. El toggle no llama al servidor.
4. Franja superior con el total del período (el mismo que `consultar_pedidos` sin zona) y un aviso corto de cobertura.
5. Clic en una zona abre un panel con sus números y estos chips:
   - "Analizá esta zona y decime qué está pasando"
   - "¿Qué clientes conviene recuperar?"
   - "Compará esta zona con la de mejor rendimiento"
   - "¿Cómo viene el agente de WhatsApp acá?"
6. Al tocar un chip, la app llama `ui/update-model-context` con `structuredContent` `{ geozona_id, nombre, fecha_desde, fecha_hasta }` y después `ui/message` con el pedido en castellano, incluyendo id, nombre y fechas. El segundo chip nombra `estado_compra en_riesgo`. El cuarto nombra `metricas_conversaciones`.
7. Dos zonas se pueden marcar para comparar. El mensaje nombra los dos id, los dos nombres y el período.
8. "Accionar sobre los clientes en riesgo" manda un mensaje para que Claude arme la audiencia con `explorar_clientes` (`geozona_id`, `estado_compra=en_riesgo`) y la previsualice con `previsualizar_etiqueta` o `previsualizar_agenda`, y espere el sí antes de `confirmar`. La app no llama esas tools.
9. El ancho es el del chat. Por debajo de 480 px el panel pasa debajo del mapa y los chips pasan de línea. Hay un control que pide `ui/request-display-mode` `fullscreen`.

---

## Receta `guia_suplai`

Archivo `mcp_server/guias/zonas.md`. Frontmatter `tema: zonas`, `titulo: Analizar una zona`. Las cinco secciones de siempre.

Pasos de la receta:

1. `listar_geozonas` con el texto de la zona. Si hay varias, preguntar cuál.
2. `consultar_pedidos` con `geozona_id` para el período, y otra llamada para el período anterior de la misma cantidad de días.
3. `consultar_pedidos` con `geozona_id` y `agrupar_por` `cliente`, para ver quién explica la variación.
4. `metricas_conversaciones` con `geozona_id`, para el rol del agente.
5. `explorar_clientes` con `geozona_id` y `estado_compra` `en_riesgo`, para candidatos a recuperar.
6. Cerrar proponiendo una acción y previsualizarla. `confirmar` solo después del sí.
7. `mapa_zonas` solo si la persona quiere ver el mapa o elegir la zona en el mapa.

La skill del plugin, si se agrega, es una línea: llamar `guia_suplai` con tema `zonas`. Se mergea después de que la receta esté en el MCP.

---

## Google Maps y CSP

La key y el Map ID son variables del servicio MCP (`GOOGLE_MAPS_API_KEY`, `GOOGLE_MAPS_MAP_ID`). El HTML las recibe al armar el recurso, como los logos. No van al repo.

Restricciones de la key, en Google Cloud:

- API: solo Maps JavaScript API.
- Cuota diaria con tope.
- Referrer HTTP: `https://6cdd153d64bc079aa7c439570283ebea.claudemcpcontent.com/*`

Ese host es `dominio_claude()` para `MCP_PUBLIC_URL=https://mcp.suplaisales.com/mcp` (SHA-256 en hex, primeros 32 caracteres). Si cambia la URL pública, cambia el referrer y hay que actualizar la key. El iframe de Claude no es `localhost`.

CSP del recurso, dominios que pide la guía de CSP de Maps JavaScript API, repartidos en los campos que el host sí aplica:

| Campo | Orígenes |
|---|---|
| `resourceDomains` | `https://maps.googleapis.com`, `https://maps.gstatic.com`, `https://fonts.googleapis.com`, `https://fonts.gstatic.com`, `https://*.googleapis.com`, `https://*.gstatic.com`, `https://*.google.com`, `https://*.googleusercontent.com`, `https://*.ggpht.com` |
| `connectDomains` | `https://maps.googleapis.com`, `https://*.googleapis.com`, `https://*.gstatic.com`, `https://*.google.com`, y los de Mixpanel de la sección de eventos |
| `frameDomains` | `https://*.google.com` |

El host, según `apps.mdx`, no declara `worker-src blob:` ni `'unsafe-eval'`. La guía de Google los pide. La prueba humana mira la consola: si el mapa no arranca por una de esas dos directivas, se frena y se reporta. No se cambia de proveedor de mapa dentro de esta entrega.

Todo el SQL filtra por el schema del token. No hay argumento `schema`.

---

## Rendimiento

`mapa_zonas` responde en menos de 3 segundos para 3.000 clientes con coordenada. Una sola ida a la base del tenant: agregados por zona (las tres métricas, los dos períodos y los cuatro estados) y los puntos con `LIMIT 5001`. Polígono ya simplificado. Si el plan en `del_corro` no entra en ese tiempo, se agrega el índice que el `EXPLAIN` muestre, sin duplicar el cálculo.

---

## Alcance

### Incluido

- `geozona_id` en `consultar_pedidos`, `metricas_conversaciones` y `explorar_clientes`.
- `agrupar_por=geozona` en pedidos.
- `estado_compra` en `explorar_clientes`, con las columnas de la fila.
- `listar_geozonas` y `mapa_zonas`, el HTML y el registro `ui://`.
- Receta `zonas` y la línea de skill del plugin.
- `GRANT SELECT` de `geo_zones` y `client_locations` para `mcp_connector`.
- Allowlist, versión, changelog, catálogo del admin.
- Tests de coincidencia y los cuatro eventos.
- Las cuatro filas nuevas en el spec 073.

### Fuera de alcance

- `metricas_whatsapp` y un corte de envíos por zona sobre `envios_plantillas`.
- `buscar_clientes`.
- Editar polígonos, reasignar zonas o correr el recompute automático.
- Cambiar los defaults de fechas, `limite`, `pagina` o `tamano`.
- Unificar los 29 días del resumen de conversaciones con los 30 de pedidos.
- Reabrir el HTML deprecado.
- Llamar tools de métricas o de previsualización desde el mapa.
- Habilitar la función para todos los tenants antes de las capturas en `esekau`.

---

## Orden de implementación

| Orden | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `suplai-platform` | `feat/mcp-vendedores-notificaciones` | Este spec. |
| 2 | `backend-supabase` | `feat/mcp-vendedores-notificaciones` | Grants y alta de tenant. Después el servicio compartido. Después los argumentos de las tools existentes. Después `listar_geozonas` y `mapa_zonas` con el HTML. Al final versión, changelog y allowlist. |
| 3 | `suplai-sales-claude-plugin` | `feat/mcp-vendedores-notificaciones` | Skill que apunta a `guia_suplai` tema `zonas`. Mismo PR que el MCP. |
| 4 | `suplai-platform` | `feat/mcp-vendedores-notificaciones` | Cuatro filas de eventos en el spec 073, en el mismo PR que este spec. |

El backoffice no cambia: el admin lee el catálogo del servidor.

---

## Migración de base de datos

No hay tablas ni columnas nuevas.

`GRANT SELECT` sobre `{schema}.geo_zones` y `{schema}.client_locations` para `mcp_connector`, en los schemas activos, con el mismo loop que `sql/145_mcp_oauth.sql`. `grant_mcp_connector_on_schema` en `core/tenancy.py` suma esas dos tablas a la lista que hoy es `pedidos`, `items_pedido`, `clients`, `puntos_venta`, para que un tenant nuevo nazca con el permiso.

Rollback: `REVOKE SELECT` de esas dos tablas. Las tools dejan de poder leer polígonos y puntos. Los filtros por `puntos_venta.geo_zone_id` siguen, porque esa tabla ya estaba concedida.

Riesgo: bajo. Es lectura. No reescribe asignaciones.

---

## Plan de prueba en CI/CD

En `backend-supabase`, un módulo nuevo junto a `tests/test_mcp_tool_schema.py` y `tests/test_mcp_consultar_pedidos.py`:

- Sin `geozona_id` y con `agrupar_por` default, el resultado de pedidos coincide con el de hoy (el test de schema espera el enum `pedido`, `cliente`, `geozona`, y el default sigue en `pedido`).
- `pedido_id` sigue ignorando fechas y `geozona_id`.
- El monto y la cantidad de una zona en `mapa_zonas` son los de `consultar_pedidos` con el mismo id y el mismo período, incluidos los defaults de fecha.
- La suma de `agrupar_por=geozona`, con la página de "Sin zona", cierra con `total_pedidos`.
- `estado_compra`: 2 pedidos → `nuevo`; dentro de 1,5× → `activo`; por encima de 1,5× y por debajo de 3× y de 60 días → `en_riesgo`; por encima de 3× → `dormido`; 61 días con un ciclo largo → `dormido`; 1 pedido y 90 días → `nuevo`.
- La mediana SQL coincide con `median_days_between_orders` en una lista fija.
- Más de 5.000 puntos: `clientes_omitidos` true y `clientes` vacío, con agregados presentes.
- `metricas_whatsapp` no gana parámetros.
- El catálogo del admin (`tests/test_admin_mcp_catalog.py`) incluye las dos tools nuevas cuando el schema está en la allowlist, y no las incluye cuando no está.
- `guia_suplai` con tema `zonas` devuelve la receta y el índice la lista.

Los checks que ya cubren pedidos, pantallas y conversaciones quedan verdes. No hay smoke de migración de datos: el GRANT se puede afirmar leyendo `information_schema.role_table_grants` en el test de tenancy si ese test ya crea un schema.

---

## Plan de prueba humana

Antes de abrir el PR de backend, y otra vez en staging antes de sacar la allowlist.

1. Backend en `8000` y MCP en `8100` (`uvicorn mcp_server.main:app --port 8100`). `MCP_MAPA_SCHEMAS=esekau`. Key de Maps con el referrer del host de Claude. Backoffice en `3000` solo para mirar el admin del conector.
2. Entrar a Claude con un usuario de `esekau`.
3. "¿Cómo viene la zona …?" con el nombre de una de las cinco. No tiene que aparecer el mapa. Tienen que aparecer `listar_geozonas` y las tools con `geozona_id`.
4. "Mostrame el mapa de mis zonas." El mapa carga, los polígonos se ven, el hover muestra números. En la consola del iframe no hay errores de CSP.
5. Clic en una zona, un chip, y la respuesta de Claude usa las tools. El chip de comparar marca dos zonas.
6. "Accionar sobre los clientes en riesgo" llega a un preview de etiqueta o de agenda. No se confirma.
7. Repetir el mapa en un ancho chico (el del chat en el teléfono, o la ventana por debajo de 480 px): chips y panel se leen enteros.
8. Admin del conector: versión nueva, aviso de reconectar, y las dos tools en el grupo Métricas.
9. Mixpanel Live View: los cuatro eventos, con `tenant_schema=esekau` y sin teléfono.
10. Capturas del mapa, del panel con chips y del preview. Con esas capturas se decide si `MCP_MAPA_SCHEMAS` pasa a todos los schemas. `demo` no sirve para la captura: tiene 4 zonas y 0 clientes asignados.

En `del_corro`, contra staging, medir que `mapa_zonas` responde en menos de 3 segundos. No hace falta el recorrido de chips ahí.

---

## Mixpanel

Eventos desde el iframe, con `mixpanel-browser`, token inyectado como la key (no se commitea). `distinct_id`: `claude:{schema}:{usuario_id}`. `app=claude`. Sin teléfono, mail ni nombre de comercio.

| Evento | Cuándo | Props |
|---|---|---|
| `mapa_abierto` | Llegó `ui/notifications/tool-result` y el mapa se pintó | `tenant_schema`, `metrica`, `zonas` |
| `zona_clickeada` | Clic en un polígono | `tenant_schema`, `geozona_id` |
| `chip_usado` | Clic en un chip de pregunta o en comparar | `tenant_schema`, `geozona_id`, `chip` |
| `accionar_usado` | Clic en accionar | `tenant_schema`, `geozona_id` |

`connectDomains` suma `https://api.mixpanel.com` y `https://api-js.mixpanel.com`. Estas cuatro filas se agregan a la taxonomía del spec 073.

La auditoría `public.mcp_auditoria` sigue registrando la llamada a la tool. Los clics no pasan por ahí.

---

## Versión del conector

Al implementar, subir `mcp_server/version.py` a la versión siguiente a la que haya en `main` (hoy el borrador de vendedores usa `2026.10.12`; esta entrega no reutiliza ese número). Una entrada en `mcp_server/changelog_claude.json`. `estado_de` marca `requiere_reconexion` cuando la versión guardada del usuario difiere. Las tools entran en `VISIBLES`, en `DESCRIPCIONES`, en `grupos_panel.py` (grupo Métricas) y en `docs/mcp-tools-visibles.md`.
