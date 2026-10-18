# 123 — Sin API: GESCOM (Del Corro)

**Estado:** Borrador  
**Fecha:** 2026-10-15  
**Repos:** `backend-supabase`  
**Rama sugerida:** la del [116](./116-mcp-pedidos-crud.md), después de la compuerta del [117](./117-mcp-canal-erp-o-carga.md)  
**Relaciona:** [117](./117-mcp-canal-erp-o-carga.md), [116](./116-mcp-pedidos-crud.md), [095](./095-claude-mcp-carga-clientes-productos.md), `erp/connectors/gescom_onprem.py`  
**Tenant de prueba:** `del_corro`

---

## Objetivo

Del Corro no tiene endpoint que Railway pueda consultar. `GescomOnpremConnector.fetch_*` devuelve `[]` a propósito. Las tools `traer_*` no llaman ese método: responden que no hay API. El catálogo que ya entra lo sigue trayendo el bridge (`POST /erp/ingest`). Lo que falta se carga a mano: clientes y productos con el [095](./095-claude-mcp-carga-clientes-productos.md), pedidos con el [116](./116-mcp-pedidos-crud.md).

### Criterios de aceptación

- En `del_corro` no hay API: las tools de lectura lo dicen y no llaman `fetch_orders`.
- Un Excel de 3 pedidos (uno con código malo) previsualiza aceptada, rechazada y, si aplica, ya existe.
- En `gonzales` los pedidos de métricas no salen de este Excel: los escribe la proyección y se consultan con `consultar_pedidos`.

## Claves, página y validación

No hay `traer_*` que paginar. El Excel entra de a 5000 filas, como el [116](./116-mcp-pedidos-crud.md). Cada pedido tiene que traer el `codigo` de `clients` y, si hay renglones, el `product_code` de `productos`. Si el cliente o un producto no coinciden, el pedido se rechaza. Un Excel de más de cinco mil comprobantes se parte en dos tandas. Precios y promos del archivo siguen la misma regla de identificadores cuando se cargan por las tools que ya existen.

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Lectura | La compuerta corta antes del `fetch_*` | Un `[]` de GESCOM parece “no hay pedidos” y no lo es | Llamar `fetch_orders` y mostrar lista vacía |
| Pedidos | Excel → [116](./116-mcp-pedidos-crud.md) | No hay `sale.order` ni JSON de GEV | Inventar un cliente HTTP de GESCOM |
| Catálogo | Bridge para el CSV. [095](./095-claude-mcp-carga-clientes-productos.md) para el alta que falta | El chat no reemplaza al bridge | Obligar a pasar todo el catálogo por el MCP |
| Push | Sigue apagado. `push_order` ya lanza `NotImplementedError` | No hay API de ida | Habilitarlo desde el chat |

---

## Alcance

### Incluido

Compuerta sin API y la carga del [116](./116-mcp-pedidos-crud.md) en `del_corro`.

### Fuera de alcance

- Un `fetch_*` nuevo contra GESCOM.
- Reemplazar el bridge.
- Alta de un pedido Suplai `abierto`.

---

## Orden de implementación

1. Compuerta del [117](./117-mcp-canal-erp-o-carga.md).
2. Carga del [116](./116-mcp-pedidos-crud.md).

---

## Migración de base de datos

La de `pedidos_externos` está en el [116](./116-mcp-pedidos-crud.md). Este sub-spec no agrega otra.

---

## Plan de prueba en CI/CD

`gescom_onprem` no llama `fetch_orders`. El preview de carga sí acepta una fila válida. `gev` puede usar la misma carga, pero su lectura no devuelve el mensaje de “no hay API”.

---

## Plan de prueba humana

Tenant `del_corro`. Excel de 3 comprobantes: uno válido y nuevo, uno con código que no está en `clients`, uno repetido o ya cargado si hay datos.

1. `traer_clientes_erp` (y el resto de `traer_*`). La respuesta dice que no hay API.
2. Subir el Excel. Ver el preview: el código malo rechazado, el válido aceptado.
3. No confirmar. `pedidos_externos` no tiene la fila.
4. Confirmar. Ver la fila. Confirmar otra vez: no duplica.
5. `traer_clientes_erp` en `gonzales` sí devuelve clientes. Eso prueba que la compuerta no se quedó pegada en “sin API”.
