# 119 — Odoo: lectura cruda (Benfresh)

**Estado:** Borrador  
**Fecha:** 2026-10-15  
**Repos:** `backend-supabase` (`erp/connectors/odoo.py`)  
**Rama sugerida:** la del [117](./117-mcp-canal-erp-o-carga.md)  
**Relaciona:** [117](./117-mcp-canal-erp-o-carga.md), [116](./116-mcp-pedidos-crud.md)  
**Tenant de prueba:** `benfresh`. El otro Odoo es `dimer`.

Gonzales no se prueba acá. Es GEV.

---

## Objetivo

`traer_*` devuelve listas y pedidos de Odoo. La lista es `product.pricelist` y el precio sale de `product.pricelist.item`. No se multiplica por 1.21. `extra` de un pedido trae el `sale.order`. `fetch_promotions` de la base devuelve vacío: la tool dice que Odoo no expone promociones en este conector.

### Criterios de aceptación

- `erp_list_id` es el id numérico de `product.pricelist`, con moneda.
- Un ítem de precio fijo llega con ese importe, sin IVA de GEV.
- `traer_pedidos_erp` no escribe `erp_orders_raw` ni llama `push_order`.
- `traer_promociones_erp` responde `soportado: false`.

## Claves, página y validación

La página está en el [117](./117-mcp-canal-erp-o-carga.md). Hasta 5000 claves por llamado. El detalle, de a 100 ids.

| Dato | Clave Odoo | Tiene que existir en |
|---|---|---|
| Producto | `default_code` → `sku` | `productos.product_code` |
| Cliente | `res.partner` id → `erp_partner_id` | `clients.partner_erp_id` |
| Precio | ítem de `product.pricelist.item` + id de `product.pricelist` | el producto y `listas_precios.erp_list_id` |
| Promo | Este conector no las expone. No hay clave que validar | — |
| Pedido | `partner_id` del `sale.order` y el producto de cada línea | el cliente y cada producto |

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Listas | `product.pricelist` + `product.pricelist.item` en `OdooConnector` | Una regla puede ser fija, porcentaje o fórmula. GEV no tiene ese modelo | `getDetallePrecios` |
| Pedido crudo | `extra` conserva el `sale.order` | Claude tiene que ver el nombre que usa Odoo | Solo el DTO, sin el documento |
| Promociones | No implementadas en este conector | La base devuelve `[]`. Hay que decirlo | Inventar combos desde las reglas de precio |
| Push | No se llama. La config de Benfresh sigue en true para el job | Este confirmar es de carga de faltantes, no de push | Empujar en el mismo sí |
| Escritura | [116](./116-mcp-pedidos-crud.md) | Misma fila que Del Corro y que Gonzales | Un insert “odoo” distinto |

---

## Alcance

### Incluido

Lectura de las cinco entidades para `connector = odoo`, con promociones marcadas como no soportadas.

### Fuera de alcance

- Cambiar `push_orders_enabled`.
- Implementar `fetch_promotions` de Odoo en esta entrega.
- Carga del histórico.

---

## Orden de implementación

Junto con el [117](./117-mcp-canal-erp-o-carga.md). PR de `extra` en `odoo.py` solo si el `sale.order` no está ahí.

---

## Migración de base de datos

Sin migración.

---

## Plan de prueba en CI/CD

Un `product.pricelist` falso con precio fijo 80 llega al DTO en 80. `traer_promociones_erp` devuelve `soportado: false`. La lectura no llama `push_order` ni `sync_orders_to_raw`.

---

## Plan de prueba humana

Tenant `benfresh`. Solo lectura, y como máximo una fila de carga.

1. `traer_precios_erp`. El nombre de la lista es el de Odoo y trae moneda.
2. `traer_pedidos_erp`. En `extra` se reconoce un `sale.order` (id, name, amount_total o el campo que el conector haya guardado).
3. `traer_clientes_erp` y `traer_productos_erp`.
4. `traer_promociones_erp` dice que no están soportadas.
5. Esas lecturas no agregan filas a `erp_orders_raw` ni a `pedidos_externos`.
6. Un faltante, una sola fila, `previsualizar_carga_pedidos`. Confirmar solo con un sí.
