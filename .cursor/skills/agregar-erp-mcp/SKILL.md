---
name: agregar-erp-mcp
description: >-
  Agregar un conector ERP al MCP de Suplai para conciliar clientes, productos,
  precios, promociones y pedidos. Usar cuando se sume un ERP nuevo, un
  fetch_orders, fetch_prices o fetch_promotions, o cuando Claude tenga que
  leer el ERP en crudo y cargar solo los faltantes.
---

# Agregar un ERP al conector MCP

Leé la regla `.cursor/rules/erp-mcp-conciliacion.mdc` y el spec `docs/specs/117-mcp-canal-erp-o-carga.md` antes de escribir código.

## Qué tiene que pasar

Claude llama `traer_*` para clientes, productos, precios y promociones. Los pedidos de un ERP con API no se leen por tool: los baja el job y Claude los consulta con `consultar_pedidos` (`origen` = `erp`, `suplai` o `tienda`). La lectura no escribe el espejo.

## Checklist

1. Identificá el tipo (`odoo`, `gev`, …) y el tenant real de prueba. Si no hay tenant, no abras el sub-spec de producción.
2. Implementá en `erp/connectors/<vendor>.py`, no en la tool:
   - `fetch_products`, `fetch_prices`, `fetch_price_list_headers`, `fetch_customers`, `fetch_orders`
   - `fetch_promotions` si el ERP las tiene. Si no, devolve `[]`
   - el documento del vendor dentro de `extra` (el `sale.order`, la fila de GEV, la vista de Sistel)
3. La respuesta de `traer_*` en `vista=claves` sale de a 5000 e incluye los ids que Suplai no tiene. El detalle, con `ids`, de a 100.
4. Registrá el conector en `ConnectorFactory` si todavía no está.
5. No llames `sync_orders_to_raw`, `sync_prices_for_schema` ni `sync_customers_to_raw` desde `erp_lectura_service` ni desde `mcp_server/`.
6. No mapees columnas del vendor en `mcp_server/` ni en `services/mcp_*`.
7. La escritura de pedidos sigue en `previsualizar_carga_pedidos` (spec 116). No crees una tool de insert por ERP. Si falta un cliente o un producto, devolvé el id en `faltantes` y no lo insertes en ese confirmar. Claude lo carga con la tool de esa entidad y repite.
8. Sumá un sub-spec `docs/specs/1xx-mcp-erp-<vendor>.md` con las seis secciones obligatorias, las claves de identificador y la prueba humana en el tenant real.
9. Sumá el tenant a la tabla del spec 117.
10. Test de servicio: la lectura llama `fetch_*` y no llama `sync_*_to_raw`. 1200 claves entran en una respuesta. Un precio rechazado trae el sku en `faltantes` y no inserta el producto. Sin red. Sin rol `mcp_connector`.

## Prueba humana mínima

En el tenant de ese tipo, con el MCP de prueba:

1. `traer_clientes_erp`, `traer_productos_erp`, `traer_precios_erp`, `traer_promociones_erp`. Los pedidos se miran con `consultar_pedidos` y el campo `origen`.
2. Confirmar que esa lectura no escribió filas nuevas en `erp_orders_raw` ni en `pedidos_externos`.
3. Armar un lote de una fila faltante y previsualizar la carga. Confirmar solo si la persona dice que sí.
4. Si el ERP no tiene API, el paso 1 tiene que decirlo, y la carga sale de un Excel.

## Fuera de este skill

- Push de pedidos.
- Alta o edición de un carrito Suplai.
- Partir `erp_sync_service.py`.
