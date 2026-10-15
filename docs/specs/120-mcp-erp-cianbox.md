# 120 — Cianbox: lectura cruda (Córdoba Frost)

**Estado:** Borrador  
**Fecha:** 2026-10-15  
**Repos:** `backend-supabase` (`erp/connectors/cianbox.py`)  
**Rama sugerida:** la del [117](./117-mcp-canal-erp-o-carga.md)  
**Relaciona:** [117](./117-mcp-canal-erp-o-carga.md), [116](./116-mcp-pedidos-crud.md)  
**Tenant de prueba:** `cordoba_frost`

---

## Objetivo

`traer_precios_erp` usa `GET /productos/listas` (`id`, `lista`, `vigente`) y los precios que `normalize_cianbox_prices` saca de `GET /productos`. No aplica IVA de GEV ni lee `product.pricelist`. Las promociones no están en el conector: la tool lo dice.

### Criterios de aceptación

- La cabecera trae el id de Cianbox como `erp_list_id`.
- `traer_pedidos_erp` no escribe el espejo ni llama `push_order`.
- `traer_promociones_erp` responde `soportado: false`.

## Claves, página y validación

Misma página del [117](./117-mcp-canal-erp-o-carga.md): hasta 5000 claves, detalle de a 100. El id de `/productos/listas` es `lista_id`. El producto de `/productos` es el `sku`. Un precio se rechaza si ese sku no está en `productos` o si la lista no está vinculada. Un pedido se rechaza si el cliente o algún renglón no coinciden. No hay promociones que validar.

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Listas | `/productos/listas` dentro de `CianboxConnector` | El campo se llama `lista`, no `name` ni `DESCRIPCION_LISTA_PRECIO` | Un mapeo genérico en la tool |
| Precios | Embebidos en `/productos`, normalizados en el conector | No hay detalle por vendedor | `getDetallePrecios` |
| Promociones | No implementadas | El default de la base es `[]` | Inventarlas |
| Escritura | [116](./116-mcp-pedidos-crud.md) | Misma carga | `sync_orders_to_raw` desde el MCP |

---

## Alcance

### Incluido

Lectura de las cinco entidades para `connector = cianbox`.

### Fuera de alcance

- Push (la config lo tiene prendido para el job; esta tool no lo dispara).
- Carga masiva.

---

## Orden de implementación

La cubre el [117](./117-mcp-canal-erp-o-carga.md). PR aparte solo si falta `extra` en el conector.

---

## Migración de base de datos

Sin migración.

---

## Plan de prueba en CI/CD

Una lista y un producto de muestra producen cabecera y precio sin × 1.21 y sin `product.pricelist`. La lectura no llama `sync_orders_to_raw`.

---

## Plan de prueba humana

Tenant `cordoba_frost`.

1. `traer_precios_erp`. El nombre coincide con Cianbox.
2. `traer_pedidos_erp`, `traer_clientes_erp`, `traer_productos_erp`.
3. `traer_promociones_erp` dice que no están soportadas.
4. Sin filas nuevas en `erp_orders_raw` ni en `pedidos_externos`.
5. Una fila faltante por el [116](./116-mcp-pedidos-crud.md), confirmar solo con un sí.
