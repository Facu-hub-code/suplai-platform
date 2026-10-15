# 118 — GEV: lectura cruda (Gonzales)

**Estado:** Borrador  
**Fecha:** 2026-10-15  
**Repos:** `backend-supabase` (`erp/connectors/gev.py`)  
**Rama sugerida:** la del [117](./117-mcp-canal-erp-o-carga.md), si `extra` todavía no trae la fila de GEV  
**Relaciona:** [117](./117-mcp-canal-erp-o-carga.md), [116](./116-mcp-pedidos-crud.md)  
**Tenant de prueba:** `gonzales`. El otro GEV es `almaro`, misma prueba si hace falta repetir.

---

## Objetivo

`traer_*` en Gonzales devuelve lo que la API de GEV ya tiene. El precio que ve Claude es el final (neto + IVA 21%), calculado en `GEVConnector.fetch_prices`. La tool no hace esa cuenta. La carga de un faltante usa el [116](./116-mcp-pedidos-crud.md).

### Criterios de aceptación

- `traer_pedidos_erp` devuelve `ErpOrder` y, en `extra`, la fila original de GEV.
- `traer_precios_erp` sale de `getListaPrecios` y `getDetallePrecios` con el `id_vendedor` del conector.
- `traer_promociones_erp` devuelve combos, porque GEV implementa `fetch_promotions`.
- Ninguna de esas llamadas escribe `erp_orders_raw` ni `pedidos_externos`.
- `push_orders_enabled` sigue en falso.

## Claves, página y validación

La página y la vista están en el [117](./117-mcp-canal-erp-o-carga.md): hasta 5000 claves por llamado, detalle de a 100.

| Dato | Clave GEV | Tiene que existir en |
|---|---|---|
| Producto | `CODIGO_ARTICULO` → `sku` | `productos.product_code` |
| Cliente | el id de cliente que el conector ya mapea a `erp_partner_id` o a `codigo` | `clients` |
| Precio | `CODIGO_ARTICULO` + `ID_LISTA_PRECIO` | el producto y `listas_precios.erp_list_id` |
| Promo | `CODIGO_COMBO` y el `CODIGO_ARTICULO` de cada componente. Hoy el DTO no trae lista: el conector tiene que poner `lista_id` en `extra` si la API lo manda. Sin lista, la promo se rechaza al cargar | la lista vinculada y cada producto |
| Pedido | identificador de cliente del comprobante y `CODIGO_ARTICULO` de cada renglón | el cliente y cada producto |

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Precio | Neto sin impuestos × 1.21 dentro del conector | GEV no manda el final. Suplai concilia contra el final | Multiplicar en la tool |
| Listas | Cabecera `ID_LISTA_PRECIO`. Detalle filtrado por `id_vendedor` | Sin ese id el detalle no es el de Gonzales | Traer todas las listas del holding |
| Promociones | `fetch_promotions` de GEV | Es el único conector que hoy las expone | Devolver `[]` y decir que no hay |
| Escritura | [116](./116-mcp-pedidos-crud.md) con los faltantes que arme Claude | El pull de lectura no persiste | `sync_orders_to_raw` |

---

## Alcance

### Incluido

Lectura de pedidos, clientes, productos, precios y promociones para `connector = gev`.

### Fuera de alcance

- Push.
- Cargar el histórico completo en `pedidos_externos` durante la prueba.
- Cambiar credenciales o `id_vendedor`.

---

## Orden de implementación

Si `GEVConnector` ya llena `extra`, este sub-spec no tiene PR propio: lo cubre el [117](./117-mcp-canal-erp-o-carga.md). Si `extra` viene vacío, un PR chico solo en `gev.py`.

---

## Migración de base de datos

Sin migración.

---

## Plan de prueba en CI/CD

Una fila GEV con neto 100 llega al DTO en 121. `traer_pedidos_erp` no llama `sync_orders_to_raw`.

---

## Plan de prueba humana

Tenant `gonzales`. El mismo recorrido sirve en `almaro`: los dos son GEV. MCP del entorno de prueba, scope `erp:leer`. No confirmar una carga masiva.

1. `traer_productos_erp` en claves. El maestro entero, si entra en 5000, llega en un llamado, incluidos los sku que Suplai no tiene.
2. `traer_precios_erp` en claves para una lista. Previsualizar la carga de esos precios. Si faltan productos, la respuesta trae los sku en `faltantes.productos` y no inserta la lista ni el producto.
3. Con esos sku, `traer_productos_erp` en detalle. Previsualizar el alta de productos. Confirmar solo con un sí. Repetir la lista de precios: esos sku ya no salen en `faltantes`.
4. `traer_pedidos_erp` y `traer_clientes_erp`. Un precio de muestra tiene que ser el final, no el neto.
5. `traer_promociones_erp`. Si GEV devolvió combos, se ven. Si la API vino vacía, la tool dice lista vacía con `soportado: true`.
6. Las lecturas no agregan filas en `erp_orders_raw` ni en `pedidos_externos`.
7. Elegir un comprobante que no esté en Suplai. `previsualizar_carga_pedidos` con esa sola fila. Si el cliente o un producto faltan, vienen en `faltantes`. Confirmar el pedido solo cuando ya coinciden, y solo con un sí.
8. Pedir el push de un pedido. No se ofrece.
