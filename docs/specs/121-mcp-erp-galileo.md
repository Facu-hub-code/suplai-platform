# 121 — Galileo: lectura cruda (El Gigante)

**Estado:** Borrador  
**Fecha:** 2026-10-15  
**Repos:** `backend-supabase` (`erp/connectors/galileo.py`)  
**Rama sugerida:** la del [117](./117-mcp-canal-erp-o-carga.md)  
**Relaciona:** [117](./117-mcp-canal-erp-o-carga.md), [116](./116-mcp-pedidos-crud.md)  
**Tenant de prueba:** `el_gigante`

---

## Objetivo

`traer_*` lee el espejo MySQL de Galileo (`SUPLAI_LISTAS_PRECIOS` y las tablas que el conector ya consulta). La conexión la abre `GalileoConnector`. La tool no importa el driver. Las promociones no están implementadas.

### Criterios de aceptación

- Las listas activas (`activa = 1`) aparecen como cabeceras.
- Los pedidos de Galileo entran por el job. `consultar_pedidos` los muestra con `origen=erp`. La lectura del MCP no escribe `erp_orders_raw`.
- `traer_promociones_erp` responde `soportado: false`.

## Claves, página y validación

Misma página del [117](./117-mcp-canal-erp-o-carga.md): hasta 5000 claves, detalle de a 100. `lista_id` es `lista_id` de `SUPLAI_LISTAS_PRECIOS`. El sku es el del producto en el espejo MySQL. Precio, pedido y cliente se rechazan en la carga si ese identificador no está en Suplai. No hay promociones que validar.

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Origen | MySQL dentro de `GalileoConnector` | No es el REST de GEV ni el XML-RPC de Odoo | Un `fetch` HTTP común |
| Listas | `SUPLAI_LISTAS_PRECIOS` con `activa = 1` | Es el filtro que el conector ya aplica | Filtrar listas inactivas en la tool |
| SQL | Solo en el conector | Ese MySQL no es el Postgres de Suplai. No va a `data_access/` ni a la tool | Pegar el `SELECT` en `erp_lectura_service` |
| Escritura | [116](./116-mcp-pedidos-crud.md) | Misma carga | Sync del job disparado por el MCP |

---

## Alcance

### Incluido

Lectura para `connector = galileo`.

### Fuera de alcance

- Credenciales del MySQL.
- Push.
- Promociones, hasta que el conector las implemente.

---

## Orden de implementación

La cubre el [117](./117-mcp-canal-erp-o-carga.md).

---

## Migración de base de datos

Sin migración en Supabase. El MySQL no se altera.

---

## Plan de prueba en CI/CD

Un cursor falso devuelve solo listas activas. La tool no importa `aiomysql`. La lectura no llama `sync_orders_to_raw`.

---

## Plan de prueba humana

Tenant `el_gigante`.

1. `traer_precios_erp`. Solo listas activas.
2. `consultar_pedidos` (`origen=erp`), `traer_clientes_erp`, `traer_productos_erp`.
3. `traer_promociones_erp` dice que no están soportadas.
4. Sin filas nuevas en `erp_orders_raw` ni en `pedidos_externos`.
5. Una fila faltante por el [116](./116-mcp-pedidos-crud.md), confirmar solo con un sí.
