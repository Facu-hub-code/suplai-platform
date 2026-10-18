# 126 — MCP: menos tools y una sola agenda

**Estado:** Borrador. El diseño está aprobado.  
**Fecha:** 2026-10-18  
**Repos:** `backend-supabase` (superficie, sender, agendas), `suplai-sales-claude-plugin` (skills que nombran tools viejas), `suplai-platform` (este spec y la regla de conciliación si una receta cambia).  
**Rama sugerida:** `feat/mcp-una-agenda` en backend y en el plugin. Este documento vive en `docs/mcp-una-agenda` de platform.  
**Relaciona:** [097](./097-claude-mcp-grupos-agendas.md), [104](./104-mcp-agendas-plantillas-deprecar-estrategias.md), [117](./117-mcp-canal-erp-o-carga.md). No entra en el PR que saca `traer_pedidos_erp`.

---

## Objetivo

Claude deja de elegir entre decenas de tools que se llaman igual salvo por el verbo, y una agenda pasa a ser el único envío programado. El mensaje puede ser el mismo para todo el grupo, o un texto por comercio con hasta dos productos de ese cliente.

Hoy el catálogo visible tiene 70 tools (`mcp_server/superficie.py`, `VISIBLES`). Unas cuarenta empiezan con `previsualizar_` y se parten en alta, edición y baja. `list_tools` las devuelve todas si el token tiene el scope. `guia_suplai` ordena el flujo y no achica el menú. La variable `producto` de una agenda clásica es un texto fijo para toda la audiencia. El producto distinto por cliente lo arma el motor de estrategias (`estrategia_id` en la agenda, `resolve_body_params`), y el conector ya no crea estrategias.

### Criterios de aceptación

- El catálogo visible no tiene dos tools de la misma entidad que solo se distingan por alta, edición o baja. Esas acciones entran en una tool con `accion`.
- Los nombres viejos (`previsualizar_editar_agenda`, `previsualizar_eliminar_etiqueta`, y el resto de la tabla de familias) no están registrados. Llamarlos no hace el trabajo por un alias oculto.
- `guia_suplai` y las descripciones nombran la tool nueva y la `accion`.
- `list_tools` sigue devolviendo todas las tools visibles del token. No se recorta a seis.
- Las seis de uso seguido (`guia_suplai`, `confirmar`, `consultar_pedidos`, `explorar_productos`, `buscar_clientes`, `previsualizar_agenda`) quedan marcadas `carga: siempre`. El resto queda `carga: diferida` y con descripción de una línea que apunta al tema de `guia_suplai`.
- `previsualizar_agenda` acepta `modo` `fijo` o `por_cliente`.
- En `fijo`, un valor de `dynamic_params` solo puede ocupar la posición `producto`. Las posiciones vacías se llenan con el dato de cada comercio. El nombre no sale vacío si el cliente lo tiene.
- En `por_cliente` no se pide plantilla ni producto. El preview dice a cuántos llega y que cada uno puede recibir hasta dos productos propios. Confirmar escribe una agenda que el sender ya despacha por `estrategia_id`. Si el tenant no tiene plantillas de salida aprobadas, el preview vuelve `valido: false` y no crea nada.
- `listar_envios` muestra `modo`. Una agenda con `estrategia_id` sale `por_cliente`. Una sin ese id sale `fijo`.
- No existe `previsualizar_estrategia`. Confirmar un preview viejo de estrategia sigue respondiendo que está deprecado.

---

## Cómo está hoy

`VISIBLES` tiene 70 nombres. El test de superficie exige ese número y que el conjunto registrado sea exactamente esa tupla. `SIEMPRE` tiene cinco: `guia_suplai`, `confirmar`, `consultar_pedidos`, `explorar_productos`, `buscar_clientes`. `aplicar_meta` escribe `carga: siempre` o `diferida` en `tool.meta.suplai`. `filtrar_visibles` recorta por scope, no por esa marca.

`guia_suplai` lee un markdown por tema en `mcp_server/guias/`. Sin tema devuelve el índice. Con tema, una receta. El tema `estrategias` está deprecado y fuera del índice.

La escritura pasa por `previsualizar_*` y un solo `confirmar`. `validar_dynamic_params` permite un texto fijo solo en la columna `producto`. El sender, si `dynamic_params` tiene algún valor, manda esa lista completa y no completa los huecos con el cliente (`agenda_sender.py`, rama de `dynamic_params`). Un hueco vacío de `nombre` llega vacío a Meta.

El producto por cliente está en el mismo cron. Si la agenda tiene `estrategia_id`, el sender elige un tema y llama a `resolve_body_params`: razón social, contexto y dos productos (carrito, quiebre, historial, clima). Si no hay productos, usa textos genéricos. Ese camino no está en el catálogo MCP.

La API de Anthropic puede diferir tools con `defer_loading` en el request del Messages API, o en el `mcp_toolset` de quien arma ese request. El servidor MCP no publica ese flag. Sacarle tools a `list_tools` las vuelve inllamables: la búsqueda de Claude necesita las definiciones en el request, y Claude.ai las arma desde `list_tools`.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Este spec y el PR de pedidos | Spec y PRs aparte. El PR que saca `traer_pedidos_erp` se mergea solo | Son dos pruebas distintas. Un diff mezclado no se puede revertir por partes | Meter el colapso de tools en ese PR |
| Qué se junta | Alta, edición y baja de la misma entidad, en una tool con `accion` | El modelo confunde `previsualizar_editar_etiqueta` con `previsualizar_eliminar_etiqueta`. El esquema de cada familia ya es el mismo objeto | Una tool `ejecutar` con todas las entidades. El esquema mezcla campos que no corresponden |
| Qué no se junta | Carga, stock, precios, listas, corrección, ocultar, sección de prompt, reporte y carga de pedidos | Cada una valida otra cosa. Juntarlas recrea la tool única | Un `previsualizar_catalogo` con un enum enorme |
| Nombres viejos | Se borran del registro en el mismo cambio que la tool nueva | Un alias registrado vuelve a sumar al menú | Dejar las tools viejas “ocultas”. Si están registradas, `list_tools` las puede devolver |
| Primera lista de seis | El servidor no la impone. Marca `carga` y acorta la descripción de las diferidas. Un spike mira si el conector de Claude.ai acepta `defer_loading` por tool | Esconderlas de `list_tools` las saca también de la búsqueda. El flag `defer_loading` lo pone quien arma el request a la API, no el servidor MCP | Filtrar `list_tools` a las seis |
| Descripciones | Completas en todas las tools, con `accion`, el campo y cuándo no usarla | Claude y la persona tienen que poder armar el envío sin adivinar. Una línea no alcanza para `dynamic_params` ni para el modo de prueba | Acortar las diferidas a una línea, como pedía la entrega 2 |
| Prueba de plantilla | `previsualizar_plantilla` con `accion=probar` y un teléfono. Lee `clients.metadata.top_products`. Si está vacío, calcula los 5 productos de pedidos confirmados de 90 días y, al confirmar, los guarda ahí | El supervisor prueba el mensaje en su teléfono y ve de qué campo salen los productos antes de mandar al grupo | Pedir los SKUs en el chat, o mandar la prueba con los fallback genéricos |
| Agenda | Un objeto, `modo` `fijo` o `por_cliente` | El supervisor pide “una agenda”. La estrategia es otra pantalla para el mismo envío | Volver a exponer `previsualizar_estrategia` |
| Dónde vive `modo` | Se deriva. `estrategia_id` presente es `por_cliente`. Ausente es `fijo` | La columna ya existe y el sender ya bifurca ahí | Una columna `modo` que pueda desmentir al `estrategia_id` |
| `por_cliente` sin pool aprobado | El preview es `valido: false` | Esas plantillas las aprueba Meta por tema. Claude no puede inventar un HSM y mandarlo el mismo día | Crear skeletons y esperar la aprobación dentro del confirmar |
| Producto en `fijo` | El sender mezcla: el texto fijo solo en `producto`; el resto, columna del cliente | Hoy un `dynamic_params` con un hueco vacío pisa el nombre | Seguir reemplazando la lista entera |
| Productos en `por_cliente` | Los elige `resolve_body_params`, hasta dos, con el fallback que ya tiene | Es la lógica que ya corre en las agendas con estrategia. El operador no elige SKUs | Un mapa cliente → SKU armado en el chat |
| Estrategias del panel | Siguen enviando. En `listar_envios` se leen como agendas `por_cliente` | Apagarlas corta envíos que no pidió este spec | Migrarlas o borrarlas en esta entrega |
| Capas | La tool llama al servicio de agendas. El sender no se copia en `mcp_server/` | La decisión de modo y el armado de parámetros viven en dominio | SQL o el resolver dentro de la tool |

---

## Alcance

### Incluido

Entrega 1, verbos.

- Una tool por familia, con `accion`. El confirmar sigue siendo el único que escribe.
- Familias: zonas, etiquetas, secuencias, plantillas, agenda, grupos, vendedores, notificaciones, sinónimos, categorías, tags de producto, promociones.
- Recetas de `guia_suplai`, descripciones y tests de superficie alineados a los nombres nuevos.
- Skills del plugin que citan un nombre viejo, en el PR del plugin de la misma entrega.

Entrega 2, peso del prompt.

- `carga: siempre` en las seis. `carga: diferida` en el resto.
- Las descripciones quedan completas. No se acortan a una línea.
- Spike, escrito en el PR: si el conector de Claude.ai permite diferir tools del MCP, cómo se configura y cuáles quedan siempre cargadas. Si no se puede, el PR lo dice y no esconde tools.

Entrega 3, agenda.

- `modo` en `previsualizar_agenda` (alta) y en `listar_envios`. `accion=editar` no cambia el modo: para pasar de `fijo` a `por_cliente` se borra y se crea de nuevo.
- `fijo`: arreglo del sender para no mandar vacío el nombre cuando `dynamic_params` solo trae el producto.
- `por_cliente`: preview y confirmar apoyados en el pool de salida ya aprobado y en el sender que ya mira `estrategia_id`.
- Lectura de las agendas que ya tienen `estrategia_id` como `por_cliente`.
- `previsualizar_plantilla` con `accion=probar` y un teléfono. La respuesta dice el campo `clients.metadata.top_products`, de dónde salieron los productos y los `dynamic_params` para una agenda `fijo`.

### Fuera de alcance

- El PR de `traer_pedidos_erp` y la proyección de pedidos.
- Elegir SKUs por cliente desde el chat.
- Crear o aprobar en Meta las plantillas de los temas. Si no están aprobadas, el modo `por_cliente` se niega.
- Apagar, migrar o reescribir las estrategias que ya corren. El panel las sigue administrando.
- Un `defer_loading` emitido por el servidor MCP. El protocolo no lo transporta en `list_tools`.
- Juntar carga, stock, precios, listas, corrección, ocultar, prompt, reporte o carga de pedidos.
- Cambiar el cupo, el dedup por teléfono o la regla de que `confirmar` es la única escritura.

---

## Familias

| Familia | Hoy | Después | `accion` |
|---|---|---|---|
| Zonas | `previsualizar_zona`, `previsualizar_ajustar_zona`, `previsualizar_vendedores_zona`, `previsualizar_asignar_clientes_zona`, `previsualizar_desactivar_zona` | `previsualizar_zona` | `alta`, `ajustar`, `vendedores`, `clientes`, `desactivar` |
| Etiquetas | `previsualizar_etiqueta`, `previsualizar_editar_etiqueta`, `previsualizar_eliminar_etiqueta` | `previsualizar_etiqueta` | `alta`, `editar`, `baja` |
| Secuencias | `previsualizar_secuencia`, `previsualizar_editar_secuencia`, `previsualizar_eliminar_secuencia` | `previsualizar_secuencia` | `alta`, `editar`, `baja` |
| Plantillas | `previsualizar_plantilla`, `previsualizar_probar_plantilla`, `previsualizar_eliminar_plantilla` | `previsualizar_plantilla` | `alta`, `probar`, `baja` |
| Agenda | `previsualizar_agenda`, `previsualizar_editar_agenda`, `previsualizar_eliminar_agenda` | `previsualizar_agenda` | `alta`, `editar`, `baja` |
| Grupos | `previsualizar_editar_grupo`, `previsualizar_eliminar_grupo` | `previsualizar_grupo` | `editar`, `baja` |
| Vendedores | `previsualizar_vendedor`, `previsualizar_cartera_vendedor`, `previsualizar_desactivar_vendedor` | `previsualizar_vendedor` | `alta`, `cartera`, `desactivar` |
| Notificaciones | `previsualizar_notificaciones_pedido`, `previsualizar_notificaciones` | `previsualizar_notificaciones` | `pedido`, `canales` |
| Sinónimos | `previsualizar_aliases`, `previsualizar_ajuste_busqueda` | `previsualizar_aliases` | `alta`, `ajuste` |
| Categorías | `previsualizar_categoria`, `previsualizar_eliminar_categoria` | `previsualizar_categoria` | `alta`, `baja` |
| Tags | `previsualizar_tag_producto`, `previsualizar_eliminar_tag_producto` | `previsualizar_tag_producto` | `alta`, `baja` |
| Promociones | `previsualizar_promocion`, `previsualizar_eliminar_promocion` | `previsualizar_promocion` | `alta`, `baja` |

El alta de un grupo nuevo sigue naciendo dentro de `previsualizar_agenda` con `accion=alta`, como hoy. `previsualizar_grupo` edita o borra un grupo que ya existe.

Conteo de partida: 70 en `VISIBLES`. Estas familias bajan 20 nombres. El catálogo queda en 50 si no se suma ninguna tool. La entrega 3 no suma una tool de estrategia.

---

## Agenda

`previsualizar_agenda` con `accion=alta` o `editar`.

**`modo=fijo`.** Hace falta `meta_plantilla_id` de una plantilla `usable_en_agenda`. `dynamic_params` sigue pudiendo traer texto solo en la posición `producto`. Al enviar, cada posición vacía se resuelve con `_client_body_param` de ese comercio. Una posición con texto y columna distinta de `producto` sigue rechazándose en el preview.

**`modo=por_cliente`.** No se aceptan `meta_plantilla_id` ni `dynamic_params`. El preview cuenta la audiencia y dice que el texto y los productos salen del motor que ya usa `estrategia_id`. Confirmar crea o actualiza la agenda con el `estrategia_id` del pool de salida aprobado de ese tenant. Si no hay pool aprobado, `valido: false` y el mensaje indica que hay que usar `modo=fijo` o aprobar las plantillas en el panel. No se llama a Meta para crear skeletons.

`accion=baja` no pide modo. Apagar (`activo=false` en `editar`) tampoco exige que la plantilla siga usable, igual que hoy.

`listar_envios` agrega `modo` en cada agenda. No cambia el filtro de audiencia.

---

## Orden de implementación

1. Mergear el PR de pedidos (`fix/mcp-sin-traer-pedidos`) sin este spec.
2. Backend, entrega 1, rama `feat/mcp-una-agenda`. Tests de superficie en el mismo PR. Merge a `main`.
3. Plugin, enseguida, con las skills que citan nombres viejos. Si el backend sale antes y el plugin no, Claude sigue un nombre que ya no existe: el PR del plugin se abre en el mismo día y no se anuncia el conector nuevo hasta que esté mergeado.
4. Backend, entrega 2, sobre la misma rama o una siguiente que salga de `main` ya con la entrega 1. Incluye el resultado del spike de `defer_loading`.
5. Backend, entrega 3. El arreglo del sender va en este PR, con tests, antes de habilitar `modo=por_cliente` en el catálogo.
6. Recetas de `guia_suplai` en el PR de la entrega que cambia el nombre o el modo. Platform solo si hace falta tocar la regla `erp-mcp-conciliacion` o este spec.

No hay dependencia de backoffice para las entregas 1 y 2. La entrega 3 no cambia la pantalla de estrategias.

---

## Migración de base de datos

Sin migración de BD en las entregas 1 y 2.

La entrega 3 no agrega columna. `modo` se lee de `agenda.estrategia_id`. No hay backfill: las filas que ya tienen `estrategia_id` pasan a verse como `por_cliente` el día del deploy. Rollback de código: el sender sigue entendiendo `estrategia_id` como hoy; el campo `modo` del MCP desaparece con el revert.

---

## Plan de prueba en CI/CD

Entrega 1.

- `tests/test_mcp_superficie.py` afirma el conjunto de nombres, no un número suelto copiado a mano. El largo de `VISIBLES` es el de ese conjunto.
- Un test por familia: `accion` inválida vuelve `valido: false`; `alta`, `editar` y `baja` llegan al servicio que ya existía.
- Los nombres viejos no están en `list_tools`.
- El job `test` del backend queda verde.

Entrega 2.

- Las seis tienen `carga: siempre`. Una tool de zona o de etiqueta tiene `carga: diferida` y la descripción menciona `guia_suplai`.
- `list_tools` sin filtro de scope devuelve las 50, no las 6.
- El spike queda en el cuerpo del PR. No hay un test de red contra Claude.ai.

Entrega 3.

- `validar_dynamic_params(["nombre", "producto"], ["", "Yerba"])` sigue siendo válido.
- Un test del sender: con esas columnas y ese `dynamic_params`, el cuerpo del cliente usa su nombre y el texto `Yerba`. Con `dynamic_params` vacío, el producto no inventa un SKU: cae al fallback que ya tiene `_client_body_param` para una columna que el cliente no trae.
- `modo=fijo` deja `estrategia_id` nulo. El sender, con `dynamic_params` `["", "Yerba"]`, manda el nombre del cliente y `Yerba`.
- Hueco de esta entrega: no hay test automático de que `por_cliente` sin pool se niegue, ni de que con pool persista `estrategia_id`. Eso se mira en la prueba humana de Gonzales.

El plugin no tiene el pytest del backend. El mínimo del PR de skills es que ningún `SKILL.md` cite un nombre de la columna “Hoy”.

---

## Plan de prueba humana

Tenant **Gonzalez Garcia**, schema `gonzales`. Foto del 18 oct 2026, cartera `lifecycle = client`:

| Dato | Valor |
|---|---|
| Cartera | 840 |
| WhatsApp `existente` o `validado` | 72 |
| `no_existente` | 2 |
| Sin chequear (`null` o `no_validado`) | 766 |
| Con `metadata.top_products.items` | 0 |
| Estrategia | id `1`, nombre `VISITA JUEVES`, 2 plantillas rotables en `approved` o `skipped` |

El trabajo de esta semana es ese: chequear WhatsApp, guardar el producto más comprado de cada cliente y dejar un envío por día, con la audiencia más grande que el cupo y el WhatsApp permitan. No se activa ninguna agenda amplia antes de los pasos 1 y 2.

Servicios: backend de esta rama en `8000` (`uvicorn main:app --reload --host 0.0.0.0 --port 8000`) y el MCP de la misma rama, local o el staging de ese PR. Si se abre el backoffice, puerto `3000`.

### 1. WhatsApp

El sender de la agenda deja afuera solo `whatsapp_estado = no_existente`. Los 766 sin chequear **entrarían** en un grupo amplio. Por eso el chequeo va primero.

1. En Claude, `explorar_clientes` con `whatsapp=existente` y otra vez con `whatsapp=validado`. La suma tiene que dar 72 antes del chequeo. `whatsapp=no_existente` da 2.
2. Correr la skill `validar-telefonos-checknumber` sobre `gonzales`: `self-test`, `extraer`, mostrar costo y lote, y frenar. `enviar` solo después de un **confirmar envío**. `aplicar` solo después de un **confirmar carga**. No pisa un `validado`. No pasa un `no_existente` a `existente`.
3. Volver a contar. La audiencia de la semana es `existente` + `validado`. `no_existente` queda afuera aunque el grupo los incluya.

### 2. Producto más comprado

El campo es `clients.metadata.top_products`: ventana de 90 días, pedidos `confirmado` o `descargado`, hasta 5 ítems con nombre y código. Hoy está vacío en los 840. Si la variable `producto` va vacía y el campo también, el mensaje manda `-`.

1. Un teléfono de prueba (el de Facundo o un cliente de los 72). `previsualizar_plantilla` con `accion=probar`, el nombre de una plantilla aprobada que tenga `{{nombre}}` y `{{producto}}`, y ese `telefono`. Leer `campo_productos`, `origen_productos`, `productos`, `dynamic_params` y `ejemplo`.
2. `confirmar` ese único envío. Si `origen_productos` era `pedidos_90_dias`, el confirmar guarda el top en ese cliente. El WhatsApp tiene que traer el nombre del comercio y el primer producto, no un SKU escrito en el chat y no `-`.
3. El resto no se llena desde el MCP. `POST /gonzales/clientes/enrich-memory/step-batch` con `step=top_products`, de a 20 `client_ids`, solo sobre la audiencia con WhatsApp. Repetir hasta cubrirla.
4. Un cliente sin pedidos en 90 días sigue vacío. No entra en el grupo de la semana: si entra, su mensaje dice `-`.

### 3. Envios de todos los días

`modo=fijo`. La plantilla es la misma de la prueba. `dynamic_params` deja vacía la posición `producto` (por ejemplo `["", ""]` si las columnas son nombre y producto) para que cada comercio use su propio top. Un texto en esa posición le manda el mismo producto a todos.

1. `previsualizar_agenda` con `accion=alta`, `tipo=recurrente`, `activar=false`. Una agenda por día (`dia_semana` de a uno) o una sola con los siete días, si el cupo del día alcanza para toda la audiencia. Hora de envío la que use el supervisor.
2. El preview tiene que mostrar la audiencia con WhatsApp y con top, no 840. Si el envío es hoy, mirar `remaining_today`. Si la audiencia supera ese cupo, partir el grupo. Un día futuro no gasta el cupo de hoy.
3. Activar (`accion=editar`, `activo=true`) solo después de que el WhatsApp de prueba se vea bien. `listar_envios` muestra `modo: fijo` y `estrategia_id` nulo.
4. `modo=por_cliente` con `estrategia_id=1` es otro mensaje: hasta dos productos del resolver de `VISITA JUEVES` (carrito, quiebre, historial, clima), no el campo `top_products`. El pool de esa estrategia ya está aprobado. Usarlo solo si se quiere ese texto. Preview con `activar=false` y un solo `client_id` antes de prenderla. `editar` no cambia el modo: para pasar de uno a otro, `accion=baja` y un alta nuevo.

### 4. Catálogo, en el mismo PR

- `list_tools` no trae `previsualizar_editar_agenda`, `previsualizar_eliminar_agenda`, `previsualizar_probar_plantilla` ni `previsualizar_desactivar_vendedor`. Sí trae `previsualizar_agenda`, `previsualizar_plantilla` y `previsualizar_vendedor`.
- `guia_suplai` tema `grupos-y-agendas` nombra `previsualizar_agenda` con `accion`.
- En el admin, las seis de siempre dicen carga siempre y una tool de zona dice diferida. En un chat nuevo de Claude, pedir una baja de etiqueta y anotar si el modelo igual vio el catálogo completo.

---

## Riesgo

La entrega 1 corta los nombres que las conversaciones viejas y las skills ya aprendieron. Por eso el plugin sale en la misma ventana y no se dejan alias. La entrega 2 puede no achicar lo que Claude ve si el conector no difiere tools: el achique seguro es el de los 20 nombres y el de las descripciones. La entrega 3 no manda productos por cliente en un tenant sin plantillas aprobadas, y no hay que prometerlo en el chat.
