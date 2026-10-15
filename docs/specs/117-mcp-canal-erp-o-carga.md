# 117 — Conector: conciliar el ERP, con API y sin API

**Estado:** Borrador. Índice de la conciliación. El alta y la edición de un pedido operativo de Suplai no entran.  
**Fecha:** 2026-10-15  
**Repos:** `backend-supabase`  
**Rama sugerida:** `feat/mcp-conciliacion-erp` desde `origin/main`  
**Relaciona:** [116](./116-mcp-pedidos-crud.md), [095](./095-claude-mcp-carga-clientes-productos.md), [098](./098-claude-mcp-erp.md), regla `.cursor/rules/backend-capas.mdc`, regla `.cursor/rules/erp-mcp-conciliacion.mdc`, skill `agregar-erp-mcp`  
**Sub-specs:** [118 GEV](./118-mcp-erp-gev.md), [119 Odoo](./119-mcp-erp-odoo.md), [120 Cianbox](./120-mcp-erp-cianbox.md), [121 Galileo](./121-mcp-erp-galileo.md), [122 Sistel](./122-mcp-erp-sistel.md), [123 GESCOM](./123-mcp-erp-gescom.md)

---

## Objetivo

Claude puede saber si Suplai tiene al día los clientes, productos, precios, promociones y pedidos del ERP, y cargar solo lo que falta.

Sin API, la fuente es el Excel. Con API, la fuente es una tool de lectura que llama al conector y devuelve el dato. En los dos casos la escritura de pedidos es la misma tool, la del [116](./116-mcp-pedidos-crud.md). Esa lectura no corre `sync_orders_to_raw` ni escribe `erp_orders_raw`.

### Criterios de aceptación

- En Del Corro, `traer_pedidos_erp` dice que no hay API y no llama `fetch_orders`.
- En Gonzales, `traer_pedidos_erp` devuelve pedidos de GEV y no inserta en `pedidos_externos` ni en `erp_orders_raw`.
- Claude, con ese resultado, llama `previsualizar_carga_pedidos` solo con los que faltan. Confirmar persiste esos.
- `traer_clientes_erp`, `traer_productos_erp`, `traer_precios_erp` y `traer_promociones_erp` siguen la misma regla: leen, no escriben.
- Un ERP sin promociones devuelve lista vacía y lo dice. No inventa combos.

---

## Los dos canales

Fila viva en `core.erp_connector_configs` (2026-10-15).

| Canal | Conector | Tenant de prueba | Lectura | Escritura de pedidos |
|---|---|---|---|---|
| API | `gev` | `gonzales` (el otro es `almaro`) | `traer_*` | [116](./116-mcp-pedidos-crud.md), solo faltantes |
| API | `odoo` | `benfresh` (el otro es `dimer`) | `traer_*` | la misma |
| API | `cianbox` | `cordoba_frost` | `traer_*` | la misma |
| API | `galileo` | `el_gigante` | `traer_*` | la misma |
| API | `sistel` | `rawson` | `traer_*` | la misma |
| Archivo | `gescom_onprem` | `del_corro` | no hay endpoint; entra el Excel | la misma |
| Archivo | sin fila | — | igual que GESCOM | la misma |

`sap` y `custom_rest` no tienen tenant. No entran hasta que haya uno. El alta de un conector nuevo sigue la skill `agregar-erp-mcp`.

## Sync automático que ya corre

El job `run_erp_sync_job` dispara cada 6 horas (`hour="*/6"` en `main.py`). La lectura del MCP no lo reemplaza ni lo apaga.

Precios y stock son un paso aparte, `run_sync_for_schema`. No dependen de si el tenant baja pedidos o clientes. Corren cuando pasó el `sync_frequency` de ese tenant desde `last_sync_at`. Hoy ese intervalo es 6 horas en Gonzales, Almaro, El Gigante, Benfresh, Dimer y Rawson. Córdoba Frost está en 24 horas. Del Corro en 1 día. El precio se escribe en `precios_productos` solo si el sku ya existe y la lista ya está vinculada. `auto_create_price_lists_on_sync` está en falso en todos los perfiles. El stock se escribe en `productos.stock` solo para un `product_code` que ya existe. No se da de alta el producto.

El resto de las bajadas no mira `sync_frequency`. Si la capability del perfil está prendida, corren en cada pasada del job.

| Entidad | Dónde escribe | Condición | Quién la tiene hoy |
|---|---|---|---|
| Precio operativo | `precios_productos` | `sync_frequency` vencido. Sku y lista ya vinculados | Todos los que tienen config. El reloj es el de arriba |
| Stock | `productos.stock` | El mismo paso que el precio | El mismo |
| Productos al espejo | `erp_products_raw` | `pull_products` | Todos menos Del Corro. No crea filas en `productos` |
| Listas al espejo | `erp_price_lists_raw` | `pull_price_list_headers` | Todos los perfiles, incluido GESCOM. El fetch de GESCOM vuelve vacío |
| Precios al espejo | espejo de precios | Encima, `pull_prices` | Igual que las cabeceras |
| Pedidos al espejo | `erp_orders_raw` | `pull_orders` | GEV, Odoo, Cianbox, Galileo, Sistel. No GESCOM |
| Pedidos proyectados | `pedidos` | Después del pull, solo si el conector está en la proyección automática | Galileo, Odoo, GEV, Sistel. Cianbox baja el espejo y no proyecta |
| Clientes al espejo | `erp_customers_raw` | `pull_customers` | Los mismos que bajan pedidos, menos el matiz de GESCOM que está apagado. No crea `clients` |
| Cola de clientes nuevos | cola de onboarding | `customer_onboarding_queue` | Odoo, Galileo, Sistel |
| Stub de cliente al proyectar | `clients` con teléfono `gev-*` | `create_stub_customers_on_project` | El perfil GEV lo tiene prendido. Almaro lo apaga en el override. Gonzales lo deja prendido |
| Vendedores | vendedores y cartera | `pull_sellers` | GEV, Galileo, Sistel |
| Promociones | promos de GEV | `pull_promotions` y conector `gev` | Gonzales y Almaro |
| Push de pedidos Suplai | el ERP | `push_orders_enabled` en la config, no en la capability | Córdoba Frost, El Gigante, Benfresh, Dimer. Apagado en GEV, Sistel y GESCOM |

Del Corro además tiene `ingest_from_agent`: el catálogo entra por el bridge, no por estos pull.

---

## Capas

| Capa | Dónde | Hace |
|---|---|---|
| MCP | `mcp_server/erp_lectura_tools.py` | Scope `erp:leer`, auditoría de conteos, llama al servicio |
| Dominio | `services/erp_lectura_service.py` | Resuelve el conector del schema y llama `fetch_*`. No decide qué falta. No inserta |
| Conector | `erp/connectors/<vendor>.py` | Traduce el ERP al DTO común y guarda el documento del vendor en `extra` |
| Datos | la carga del [116](./116-mcp-pedidos-crud.md) y las cargas que ya existen | Persiste recién en el confirmar |

La tool no importa el conector. El servicio de lectura no llama `sync_orders_to_raw`, `sync_prices_for_schema` ni `sync_customers_to_raw`. Esas funciones siguen para el job del backoffice. Este camino no las usa.

El DTO común es el de `erp/connectors/base.py` (`ErpOrder`, `Customer`, `Product`, `Price`, `PriceListHeader`, `ErpPromotion`). `extra` lleva el documento del vendor (`sale.order` en Odoo, la fila de GEV). Claude arma la fila de carga con el DTO. Si `extra` no está, el conector de ese ERP está incompleto para esta conciliación.

---

## Tools de lectura

Todas con `erp:leer`, `readOnlyHint = true`. Los topes están en límites y parámetros. Sin teléfonos en la auditoría.

| Tool | Método del conector |
|---|---|
| `traer_pedidos_erp` | `fetch_orders` |
| `traer_clientes_erp` | `fetch_customers` |
| `traer_productos_erp` | `fetch_products` |
| `traer_precios_erp` | `fetch_price_list_headers` y `fetch_prices` |
| `traer_promociones_erp` | `fetch_promotions` |

Sin API (`gescom_onprem` o sin config) las cinco responden que no hay endpoint. No disfrazan el `[]` de GESCOM como “el ERP no tiene pedidos”.

### Límites y parámetros

La lectura de claves y el detalle no tienen el mismo tope. Una clave es un identificador. El detalle es el producto, con el documento del ERP.

| Vista | Default | Tope | Qué viaja |
|---|---|---|---|
| `claves` | 5000 | 5000 | Solo identificadores. Un maestro de mil productos entra en un llamado. El cursor sigue solo si el total pasa de 5000 |
| `detalle` | — | 100 | DTO y `extra`. Se pide con `ids`. Cien productos completos, con todas las listas, ya pasan el medio millón de caracteres |

`vista=detalle` sin `ids` es error y no llama al ERP. La respuesta de claves trae `total`, `hay_mas`, `cursor` y `filas`. Esas filas son las del ERP, también las que Suplai todavía no tiene. Si la página escondiera los ids que faltan, Claude no podría pedirlos ni cargarlos.

`vista=claves` por entidad:

| Tool | Claves de cada fila |
|---|---|
| `traer_productos_erp` | `sku` |
| `traer_clientes_erp` | `erp_partner_id` y, si el conector lo tiene, `codigo` |
| `traer_precios_erp` | `product_sku`, `lista_id` |
| `traer_promociones_erp` | `codigo_combo`, `lista_id`, `sku` de cada ítem |
| `traer_pedidos_erp` | `erp_order_id`, identificador de cliente, `sku` de cada renglón |

Sin nombres, sin montos y sin `extra` en `claves`.

### Validaciones y faltantes

Las aplica el servicio de dominio al previsualizar la escritura. Una fila que no cierra se rechaza, el lote sigue, y la respuesta junta los identificadores que faltan.

| Dato | Tiene que coincidir con | Si no coincide |
|---|---|---|
| Pedido | El identificador de cliente resuelve a un `clients` de ese schema (`codigo` numérico o `partner_erp_id`). Cada `sku` del renglón existe en `productos.product_code` | La fila del pedido se rechaza. `faltantes.clientes` y `faltantes.productos` traen los ids |
| Precio | `product_sku` existe en `productos.product_code`. `lista_id` es el `erp_list_id` de una `listas_precios` ya vinculada | Esa fila de precio se rechaza. `faltantes.productos` y `faltantes.listas` traen los ids |
| Promoción | `lista_id` es una lista ya vinculada. Cada `sku` del combo existe en `productos.product_code` | La promo se rechaza. Mismos `faltantes`. Si el conector no manda `lista_id`, también |

El confirmar de precios no crea el producto. El de pedidos no crea el cliente. Claude, con esos ids, llama `traer_productos_erp` o `traer_clientes_erp` en `vista=detalle` y después la carga que ya existe para esa entidad. Recién ahí repite la lista de precios o los pedidos.

Caso: en Almaro se actualiza una lista y faltan productos. El preview de precios devuelve los sku. Claude pide el detalle de esos sku, previsualiza el alta de productos y, con el sí, los carga. Después vuelve a previsualizar la lista. Cien clientes nuevos con sus pedidos siguen entrando por la carga de a 100 filas. Eso no cambia.

La clave de cada ERP está en su sub-spec. El dominio compara esas claves ya normalizadas por el conector. No compara el nombre del cliente ni la descripción del producto.

La escritura de clientes y productos sigue en el [095](./095-claude-mcp-carga-clientes-productos.md). La de listas y la promoción del espejo siguen en el [098](./098-claude-mcp-erp.md). La de pedidos es el [116](./116-mcp-pedidos-crud.md). Después de un `traer_*`, Claude llama esa escritura solo con lo que falta.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Quién concilia | Claude, con la lectura y con lo que ya hay en Suplai | El faltante depende de comparar dos listas. El server no adivina el Excel ni el recorte | `sync_orders_to_raw` como camino del MCP |
| Escritura de pedidos | Una tool para los dos canales | El alta del comprobante es la misma fila. Cambia la fuente, no el insert | Un insert distinto si el dato vino de Odoo |
| Lectura | Servicio nuevo `erp_lectura_service` | El sync existente escribe el espejo y, cada vez que vence `sync_frequency`, precio y stock. Esta tool tiene que poder mostrar el dato sin persistirlo y sin frenar ese job | Reusar `sync_*_to_raw` y después leer la tabla |
| Forma del dato | DTO común + `extra` del vendor, y solo en `vista=detalle` | Claude necesita ver `sale.order` y también un campo estable para armar la carga | Devolver el JSON del ERP sin DTO, o solo el DTO sin `extra` |
| Página de claves | Tope 5000. Default 5000 | Mil sku son un payload chico. Partirlos de a 100 son diez idas al MCP para poder ver qué falta | Dejar el tope en 100 también para las claves |
| Página de detalle | Tope 100, solo con `ids` | Cien productos con todas las listas ya superan el medio millón de caracteres. El detalle se pide para los que faltan, no para el maestro | Subir el detalle al mismo tope que las claves |
| Faltantes | El preview de la escritura devuelve los ids que no están en Suplai | Sin esos ids Claude no puede pedir el producto al ERP ni cargarlo antes de repetir la lista | Rechazar la fila y no decir cuál sku faltó |
| Quién carga el faltante | Claude, con `traer_*` en detalle y la carga que ya existe para esa entidad | El sí de productos y el sí de precios quedan separados. Cien clientes con pedidos en Almaro siguen siendo una carga de pedidos | Que el confirmar de precios inserte el producto solo |
| Promociones | `fetch_promotions`. Vacío explícito si el conector no las implementa | Hoy solo GEV las trae. El resto hereda `[]` de la base | Omitir la tool hasta que todos tengan combos |
| Push | Esta etapa no lo llama | Gonzales y Almaro lo tienen apagado. Benfresh lo tiene prendido y no se toca desde acá | Un confirmar de lectura que haga `push_order` |
| Pedido operativo | Fuera | Crear y editar un carrito `abierto` es otro flujo | Meter `previsualizar_pedido` en esta entrega |

---

## Alcance

### Incluido

- Las cinco tools de lectura y la compuerta sin API.
- El índice de sub-specs, con la prueba humana de un tenant por conector.
- La regla y la skill para el próximo ERP.

### Fuera de alcance

- Alta, edición y confirmación de un pedido Suplai (`abierto` → `confirmado`).
- Disparar el sync del backoffice desde el MCP.
- Prender o apagar `push_orders_enabled`.
- `sap` y `custom_rest` sin tenant.

---

## Orden de implementación

| Orden | Qué |
|---|---|
| 1 | `erp_lectura_service` + tools de lectura + compuerta. Tests sin red |
| 2 | [116](./116-mcp-pedidos-crud.md), la carga compartida |
| 3 | Cada sub-spec solo si el conector todavía no llena `extra` o no expone una de las cinco lecturas |

El 095 y el 098 no se reescriben.

---

## Migración de base de datos

Sin migración para la lectura. La tabla de la carga está en el [116](./116-mcp-pedidos-crud.md).

---

## Plan de prueba en CI/CD

Pytest sin red y sin rol `mcp_connector`:

- `gev` → `traer_pedidos_erp` llama `fetch_orders` y no llama `sync_orders_to_raw`.
- `gescom_onprem` → no llama `fetch_orders` y el texto dice que no hay API.
- `traer_promociones_erp` con el default de la base devuelve `soportado: false` y lista vacía.
- `vista=claves` con 1200 sku devuelve las 1200 en un llamado, `hay_mas` en falso. Con 6000 devuelve 5000, `hay_mas` y un `cursor`. `vista=detalle` sin `ids` no llama al conector. `vista=detalle` con 101 ids se rechaza.
- Un precio cuyo sku no está en `productos` sale `rechazada` y `faltantes.productos` trae ese sku. Un pedido con cliente o renglón desconocido llena `faltantes.clientes` o `faltantes.productos`. Una promo sin lista o sin producto hace lo mismo. El confirmar de precios no inserta en `productos`.
- La auditoría no lleva teléfono, nombre, CUIT ni montos.

---

## Plan de prueba humana

Una corrida real por tipo, en el tenant de la tabla. Primero solo lectura. El confirmar de una carga, solo si la persona dice que sí y el lote es de una fila de prueba, no el histórico entero. El paso a paso está en cada sub-spec.

| Tipo | Tenant | Spec |
|---|---|---|
| GEV | `gonzales` | [118](./118-mcp-erp-gev.md) |
| Odoo | `benfresh` | [119](./119-mcp-erp-odoo.md) |
| Cianbox | `cordoba_frost` | [120](./120-mcp-erp-cianbox.md) |
| Galileo | `el_gigante` | [121](./121-mcp-erp-galileo.md) |
| Sistel | `rawson` | [122](./122-mcp-erp-sistel.md) |
| Sin API | `del_corro` | [123](./123-mcp-erp-gescom.md) |
