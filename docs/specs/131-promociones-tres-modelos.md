# 131 — Promociones: tres modelos según cómo las maneja cada distribuidora

**Estado:** Borrador. El modelo A está implementado en ramas locales y probado contra almaro. B y C están relevados.
**Prioridad:** los tenants Arcor (modelo A: almaro y gonzales) son el foco. B y C se tienen en cuenta en el diseño, pero no se implementan en esta entrega.
**Fecha:** 2026-10-24
**Repos:** `backend-supabase`, `wholesale-catalog-app`, `agente-conversacional-multi_tenant`, `suplai-platform` (este spec).
**Relaciona:** [130](./130-gev-promos-cabecera-y-precio.md) (el clasificador por reglas que este spec reemplaza para GEV), backend-suplai#329 (filtro de canal DEPOT/AASS), plan de prueba `implementacion/almaro/outputs/plan-prueba-combos-cerrados-20261023.md`.

---

## Objetivo

Cada distribuidora arma sus promociones de una forma distinta, y Suplai las tiene que mostrar y cobrar igual que su ERP. Hay tres modelos:

| Modelo | Cómo es | Tenants (24 oct 2026) | ERP |
|---|---|---|---|
| **A. Combos cerrados** (modo Arcor) | La promo es un combo con su propio código. Se pide tal cual, como un SKU. El precio lo da el ERP. | `almaro`, `gonzales` | `gev` (Xionico) |
| **B. Promociones dentro del catálogo** (como Dimer) | La promo es un producto más del ERP, con su SKU y su precio. Se reconoce por el nombre («Promo …»). | `dimer` | `odoo` |
| **C. Reglas de descuento sobre productos** (como Campi) | La promo es una regla: «10 % llevando 3 de limpieza». Se carga a mano en Suplai sobre un grupo de productos. | `del_corro` (Campi) | `gescom_onprem` |

### Criterios de aceptación

- Todo cliente tiene una lista de precios válida y activa; como mínimo, la lista por defecto del tenant. Un cliente sin lista, o con una lista que no existe, no puede ver precios ni promos coherentes con el ERP.
- Para el mismo cliente y la misma compra, la tienda, el agente y el ERP dan el mismo total (±$0,05 por línea).
- El modelo de cada tenant se decide por configuración, no por el nombre del tenant.
- **A:** el combo se agrega como una línea con su código. Cuesta lo mismo que en el pedido real de GEV, y viaja al ERP como combo con sus componentes.
- **B:** el SKU «Promo …» aparece en Promociones con su precio de lista (o el de la lista por defecto, si la del cliente no lo tiene). Se pide como un SKU normal.
- **C:** la regla rebaja los productos del grupo cuando se llega al mínimo, en la tienda y en el agente. No cambia nada respecto de hoy.

---

## Cómo se identifica el modelo de cada tenant

`public.distribuidoras.metadata.promociones.modelo`: `combos_cerrados` | `sku_catalogo` | `reglas`.

Si la clave no está, se deriva así:

| Conector (`core.erp_connector_configs.connector`) | Modelo por defecto |
|---|---|
| `gev` | `combos_cerrados` |
| `odoo` con `metadata.promociones.prefijo_sku` configurado | `sku_catalogo` |
| cualquier otro o sin ERP | `reglas` |

Un tenant puede tener reglas (C) además de A o B: las reglas cargadas a mano siguen funcionando en todos.

---

## Modelo A — Combos cerrados (almaro, gonzales)

### Qué se hizo

El combo de GEV es un producto de Suplai:

- Su código es el del combo (`112271`).
- Se llama por lo que trae («COMBO 25 TURRON OBLEA ARCOR…»).
- Tiene un precio por lista y el stock que alcanzan sus componentes.
- Lo acompaña una promo `promo_scope='combo'` con `product_code` = código del combo, que guarda los componentes para mostrarlos y para inyectar el pedido.

**Precio por lista** (`erp/services/gev_combo_sku.py`). Sale de `getDetalleCombos` y de los precios de lista de Suplai, que ya son finales (neto × 1,21):

1. Si la cabecera trae un %: precio de lista × factor × (1 − % del renglón, o el de la cabecera si el renglón no trae).
2. Si no, y el renglón trae `PRECIO_UNITARIO`: ese precio × 1,21.
3. Si no: precio de lista × factor × (1 − % del renglón).

Contra 970 líneas de combo de pedidos reales (15–22 oct 2026), 115 de 128 pares combo-lista dan el mismo precio con ±$0,05. Los 13 restantes tienen explicación:

- 12 son jugos: Almaro les sumó un regalo a $0,10 el 23/10, después de esos pedidos.
- El otro es Halloween: el precio cambió, y el cálculo coincide con el actual.

**Pedido.** Se agrega una línea del combo × N. Un combo con SKU propio no rebaja los componentes sueltos: el combo se compra solo como combo.

**Inyección.** Es igual que la app de GEV:

- Una línea en `listadoDetallePedido`, con `CODIGO_COMBO`, `CANTIDAD_PEDIDA` = N y `PRECIO_UNITARIO_LISTA` = total neto de la línea.
- Los componentes van en `listadoDetallePedidoCombo`, con el mismo `ID_DETALLE_PEDIDO`.
- Un regalo del mismo SKU que se paga (2x1) no viaja: lo agrega el depósito. Un regalo de otro SKU sí viaja.

**Qué no se publica:**

- Códigos que no están en `getCombos` (`MATECLUBGO`).
- Combos de canal `DEPOT`/`DPEOT`/`AASS`: solo se venden con las listas `99` y `02`, y esos clientes no están cargados en Suplai.
- Ya no hay tope del 90 % ni clasificación en %, pack, 2x1 o regalo.

### Resultado de la prueba (24 oct 2026, almaro, lista 20, cliente 79)

El sync real con este código corrió de 09:32 a 09:53 UTC. Después se revirtió con el sync de `main` y se sacaron los productos combo del catálogo.

| Caso | Combo | N | Tienda (API) | Agente | Pedido real GEV |
|---|---|---|---|---|---|
| C1 | 112271 turrón 15 % × 25 | 2 | $11.082,96 | $11.082,96 | $11.082,96 |
| C2 | 112422 jugo manzana | 2 | $9.489,24 | pregunta Arcor o BC | $9.488,02 (+$1,22 por el regalo nuevo) |
| C3 | 112429 jugo multifruta | 1 | $4.744,62 | — | $4.744,07 (+$0,55, ídem) |
| C4 | 112528 papas 80 g 2x1 | 15 | $29.818,95 | $29.818,95 | $29.819,01 |
| C5 | 113181 turrón 50 + Rocklets | 1 | $10.431,47 | $10.431,47 | $10.431,47 |
| C6 | 121962 pan dulce | 12 | $119.428,56 | $119.428,56 | $119.428,57 |
| C7 | 113183 ramen pollo | 5 | $9.788,05 | $9.788,05 («de 70») | $9.788,05 |
| C8 | 112424 jugo durazno 50 % | 1 | $2.790,59 | pregunta Arcor o BC | $2.790,60 |
| C9 | 113014 choclo 50 % | 5 | $4.863,30 | — | $4.863,30 |
| C10 | AG14356 bolsa caramelos | 3 | $2.399,97 | no carga: stock 0 | $2.399,97 |
| C11 | 121963 Halloween | 1 | $65.411,65 | $65.411,65 | $65.411,66 |

- **UI de la tienda:** con «turrón» aparecen el combo `112271` a $5.541,48 (tachado $6.519,50) y el `113181` a $10.431,47. «Agregar» escribió una línea `112271` × 1. La Caja Navidad Chica da $17.828,36, igual que el Excel.
- **Payload a GEV:** se armó con los componentes de la base y el HTTP interceptado (no se envió). `113181` lleva $8.621,05 neto, el mismo valor que el pedido real. `112528` lleva $24.643,76, contra $24.643,81 real (redondeo).

### Pendientes del modelo A

| Pendiente | Detalle |
|---|---|
| Caja Navidad Mediana `111271` | La tienda muestra $23.568,00 y el Excel $23.141,41. No hay pedido real para comparar. |
| Stock entre canales | La tienda deja agregar `AG14356` con stock 0; el agente no. Hay que alinear. |
| Inyección real | `push_orders_enabled = false` en almaro y gonzales. El payload se validó sin enviar. Falta un pedido real a GEV con un combo. |
| Ambigüedad de sabores | «jugo de manzana» encuentra Arcor y BC. El agente pregunta, y está bien. |
| Línea suelta tras el cambio | La línea `4013` × 25 del pedido 945 quedó a precio de lista. Con el revert vuelve el 15 % en la próxima edición del pedido. |

---

## Listas de precios de los clientes

Regla: todo cliente tiene asignada una lista de precios que existe y está activa. Si el ERP no la trae, se asigna la lista por defecto del tenant (`distribuidoras.default_lista_precios`).

Auditoría del 24 oct 2026:

- **gonzales:** los 863 clientes tienen una lista válida.
- **almaro:** 1 de 150 clientes (id 85, código 5147) apunta a la lista 1, que no existe. Sus pedidos se cobraron casi todos con la lista 20, que es la lista por defecto de almaro. Corregido el 24 oct 2026: ahora tiene la 20.

A futuro, el alta y el sync de clientes tienen que caer en la lista por defecto cuando la del ERP no existe en Suplai.

## Modelo B — Promociones dentro del catálogo (Dimer)

### Qué hay hoy

En Odoo, Dimer tiene productos que son la promo misma. No tienen marca de promo ni una categoría propia: solo el nombre empieza con «Promo».

| SKU | Nombre | Precio Suplai (lista 2) | Producto base | Pedidos reales |
|---|---|---|---|---|
| 121127051 | Promo LITRO CHOCOLATE SUIZO | $12.014 | 12112705 a $15.017 (−20 %) | 120, todos a $12.014 |
| 120183581 | Promo LITRO PASAS AL RON | $12.014 | 12018358 a $15.017 | 97 a $12.014 |
| 50031391 | Promo 2 POLLO ENTERO CONGELADO | $24.907 | — | 30 a $24.907 |
| 541641 | Promo 1 MEDIA PECHUGA DESHUESADA | $27.108 | — | 27 a $27.108 |
| 5416412 | Promo 2 MEDIA PECHUGA DESHUESADA | $26.471 | — | 14 |
| 541651 | Promo 1 FILETITO IQF | $27.434 | 54165 a $28.462 | 7 |
| 5416512 | Promo 2 FILETITO IQF | $26.788 | 54165 a $28.462 | 14 |
| 50031811 | Promo POLLO ENTERO SADIA | $4.202 | 5003181 a $7.594 | 21 (stock 0) |

- **Precio:** el precio de la promo existe solo en las listas 2 («Default ERP») y 3. El 87 % de los clientes está en la lista 34. Dimer tiene `price_fallback_to_default = true` y su lista por defecto es la 2. Por eso un cliente de la lista 34 ya recibe $12.014, el mismo precio que cobra Odoo en los pedidos reales.
- **Visibilidad:** los 8 SKUs están ocultos (`en_catalogo = false`, `motivo_baja = "oculto desde el conector"`). Alguien los ocultó desde el conector de Claude, así que hoy no aparecen en la tienda ni en el agente.
- **Pedidos de Suplai:** antes de ocultarse se vendieron 2: `50031391` llegó a Odoo (`enviado_erp`) y `5416412` quedó en `error_sync` el 20/10. Hay que revisar ese error antes de volver a publicarlos.
- **Promociones:** `dimer.promociones_semanales` está vacía.

### Diseño propuesto

- Una promo se reconoce por el prefijo del nombre en el ERP, configurable en `metadata.promociones.prefijo_sku` (para Dimer, `"Promo"`).
- El SKU es la promo. Se publica como promo `single_sku`, con `discount_kind='fixed_price'` y el precio de lista del cliente, o el de la lista por defecto si la del cliente no lo tiene.
- El tachado es el precio del producto base, si se encuentra uno con el mismo nombre sin el prefijo («Promo 1 », «Promo 2 »). Si no hay base, no se tacha.
- Se muestra en Promociones y en la búsqueda. El agente la lista y la carga como un SKU normal, y se inyecta a Odoo como cualquier producto.
- Se arma con un paso del sync de productos de Odoo: cada corrida reconcilia las promos de esos SKUs, con alta, actualización de precio y baja si el SKU desaparece o queda sin stock.

---

## Modelo C — Reglas de descuento (Campi / `del_corro`)

### Qué hay hoy

Son reglas semanales cargadas a mano, de tipo `sku_group`, `forma='combinable'`, por porcentaje y con mínimo. Se cargan dos veces, una para la lista 1 y otra para la 7. Ejemplos:

| Regla | % | Mínimo | Productos | Vigencia |
|---|---|---|---|---|
| Descuento en bebidas con alcohol | 6 | 6 | 9 | 1–10 oct |
| Descuento especial en premezcla | 6 | 6 | 20 | 29–30 sep |
| Veneziana | 10 | 6 | 25 | 14–21 sep |
| Limpieza | 10 | 3 | 85 | 24–31 ago |
| Semana Antojos | 10 | 10 | 74 | 17–23 ago |

Ninguna está vigente hoy. El motor existe (precio de grupo en la tienda y en el agente, armado de la combinable) y no cambia con este spec.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Modelo por tenant | `metadata.promociones.modelo`, con un valor por defecto derivado del conector | Un tenant nuevo con GEV funciona sin configurar nada. Un caso raro se fuerza a mano. | Usar el nombre del tenant: no escala. |
| A: el combo es un producto | Una fila en `productos` con el código del combo, su precio por lista y una promo `combo` con `product_code` | La tienda y el agente ya validan y cobran SKUs. No hacen falta excepciones ni migración. | Una línea de pedido sin producto: había que tocar cada validación de catálogo. |
| A: precio calculado por Suplai | Renglones de `getDetalleCombos` y precios de lista de Suplai | GEV no publica el precio del combo antes del pedido, y Xionico es lento para cambiar la API. | Esperar un endpoint de precio de combo. |
| A: sin tope del 90 % | Entra todo combo con precio mayor a 0 que esté en `getCombos` | El tope dejaba afuera combos que se venden, como la bolsa de caramelos. | Mantener las reglas del spec 130. |
| A: inyección como combo | `CODIGO_COMBO` y `listadoDetallePedidoCombo` | Es lo que manda la app de GEV en los pedidos reales. El ERP lo reconoce. | Mandar los componentes sueltos: GEV los cobraría a lista. |
| A: canal DEPOT/AASS | No se sincronizan | Se venden solo con las listas `99` y `02`, sin clientes en Suplai. | Publicarlos en todas las listas: pisaban precios (turrón al 25 %). |
| B: identificar por prefijo | `prefijo_sku` en metadata | Odoo no trae marca de promo ni categoría propia. | Una lista manual de SKUs: se desactualiza. |
| B: precio con fallback | Lista del cliente, si no la por defecto | Ya es el comportamiento de Dimer y coincide con Odoo en 120 pedidos. | Recalcular contra el producto base: no es lo que cobra Odoo. |
| C: sin cambios | Se mantiene el motor de grupos | Funciona y Campi lo opera a mano. | — |

---

## Alcance

### Incluido

- **A:** sync de combos como SKU, precio por lista, stock, tienda (una línea por combo), agente (lista, carga y búsqueda por nombre, etiqueta GEV o tamaño), inyección como combo, filtro de canal.
- **B:** identificación por prefijo, publicación como promo `single_sku` de precio fijo, tachado contra el producto base y reconciliación en el sync de Odoo.
- Identificación del modelo por tenant.

### Fuera de alcance

- Cambiar la API de Xionico o pedirles un endpoint de precio de combo.
- Clientes de canal (listas `99` y `02` de GEV).
- Cargar automáticamente las reglas de Campi desde Gescom: hoy se cargan a mano y no hay fuente en el ERP.
- El regalo en depósito del 2x1: lo agrega GEV, Suplai no lo carga.

---

## Orden de implementación

| Paso | Repo | Rama | Estado |
|---|---|---|---|
| 1 | backend | `feat/gev-promos-sin-canal` (#329 + combos SKU) | Commits locales. Falta push. |
| 2 | tienda | `feat/tienda-combo-sku` | Commit local |
| 3 | agente | `fix/agente-promo-plural` | Commits locales |
| 4 | backend | modelo B (paso del sync de Odoo) | Después de Arcor |
| 5 | backend + backoffice | `metadata.promociones.modelo` y su edición | Después de Arcor |

Todo va sobre esas tres ramas, sin abrir ramas nuevas: al final hay un solo PR por repo. Primero se mergea el backend, después la tienda y el agente. El modelo A no se puede activar en producción si la tienda y el agente no están desplegados: con `main`, los combos aparecerían como productos sueltos.

---

## Migración de base de datos

Sin migración de BD. Todo usa columnas existentes:

- `productos`: la descripción con el prefijo `Combo GEV` marca la fila como combo.
- `precios_productos`.
- `promociones_semanales`: `promo_scope='combo'` y `product_code`.
- `promocion_componentes`.
- `metadata` (JSON).

Rollback del modelo A: correr el sync con el código anterior y ejecutar `UPDATE {schema}.productos SET en_catalogo=false, stock=0 WHERE descripcion LIKE 'Combo GEV%'`. Se aplicó el 24/10 en almaro.

---

## Plan de prueba en CI/CD

- **backend:**
  - `tests/test_gev_combo_sku.py`: 10 combos reales de almaro (definición GEV, precios de la lista 20 y pedido real) para precio y componentes; reglas de 2x1, cabecera y stock.
  - `tests/test_erp_promociones_sync.py`: combo por lista, sin precio, sin tope, persistencia y retiro.
  - `tests/erp/connectors/test_gev_connector.py`: payload como la app de GEV.
  - `tests/test_promociones_pricing_service.py`: el combo SKU no rebaja sueltos.
  - Suite: 2115 passed, 1 skipped.
- **tienda:** `lib/promo-combo-sku.test.ts` (línea del combo, precio, tachado, stepper). Pasan 28 tests de `lib` y el typecheck.
- **agente:** `tests/test_promo_dialog_busqueda.py` (combos reales: % y cantidad del nombre, regalo, etiqueta GEV, tamaño, sin match no ofrece otra promo, el riel pide todas las vigentes) y `tests/test_promociones_grupo.py`. Suite: 1527 passed, 4 skipped.
- **B:** tests del reconocimiento por prefijo, del fallback de precio y del tachado contra el base, con los 8 SKUs reales de Dimer.

---

## Plan de prueba humana

Servicios: backend `8000`, agente `8001` (`simulate-turn`, sin WhatsApp) y tienda `3000`. No confirmar pedidos.

### A — almaro, cliente de la lista 20

1. Sync de almaro con la rama.
2. En la tienda, Promociones, buscar «turron»: aparece `112271` a $5.541,48 con tachado $6.519,50.
3. «Agregar» deja una línea `112271` × 1. El «−» la saca.
4. Con el agente: «Quiero 2 combos de turrones del 15% llevando 25» carga 2 × $5.541,48.
5. Correr C1–C11 del plan; los totales tienen que coincidir con la tabla.
6. Payload: armarlo con HTTP interceptado y comparar contra el pedido real.
7. Al terminar, si producción sigue en `main`: revertir (ver Migración).

### B — Dimer, cliente de la lista 34

Requiere decidir antes si se vuelven a publicar los 8 SKUs, que alguien ocultó a propósito, y revisar el `error_sync` del 20/10.

1. Publicar `121127051` en una prueba controlada.
2. En la tienda, Promociones: «Promo LITRO CHOCOLATE SUIZO» a $12.014, tachado $15.017.
3. Agregar 1: la línea es $12.014, igual que en los pedidos de Odoo.
4. Con el agente: «quiero la promo de chocolate suizo» carga `121127051` × 1 a $12.014.
5. Volver a ocultar si la decisión es no publicarla.

### C — Campi

1. Crear una regla de prueba como la 156 («6 % llevando 6 bebidas con alcohol», lista 1) con vigencia de un día, para un cliente de prueba.
2. En la tienda, agregar 6 unidades mezcladas del grupo: cada línea al 6 %. Con 5 unidades, a lista.
3. Repetir con el agente («quiero la promo de bebidas con alcohol»): abre el armado y no reparte solo.
4. Borrar la regla de prueba.
