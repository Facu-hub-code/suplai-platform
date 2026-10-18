# 122 — Sistel: lectura cruda (Rawson)

**Estado:** Borrador  
**Fecha:** 2026-10-15  
**Repos:** `backend-supabase` (`erp/connectors/sistel.py`)  
**Rama sugerida:** la del [117](./117-mcp-canal-erp-o-carga.md)  
**Relaciona:** [117](./117-mcp-canal-erp-o-carga.md), [116](./116-mcp-pedidos-crud.md)  
**Tenant de prueba:** `rawson`

---

## Objetivo

`traer_precios_erp` usa la vista del alias del conector. Si esa vista no está, el conector arma una sola lista con `PrecioFinal` y la respuesta lo dice (`extra.synthetic`). El precio es el final: no se multiplica por 1.21. Las promociones no están implementadas. El push de Rawson sigue apagado.

### Criterios de aceptación

- Con vista, `erp_list_id` sale de `IDLista`.
- Sin vista, el preview de precios dice que la lista es sintética.
- Los pedidos de Sistel entran por el job. `consultar_pedidos` los muestra con `origen=erp`. La lectura del MCP no escribe el espejo.
- `traer_promociones_erp` responde `soportado: false`.

## Claves, página y validación

Misma página del [117](./117-mcp-canal-erp-o-carga.md): hasta 5000 claves, detalle de a 100. Con vista, `lista_id` sale de `IDLista` y el sku de `IDProducto`. En la lista sintética, `lista_id` es el id único del conector y el sku sigue siendo `IDProducto`. Un precio de esa lista se rechaza si el producto no está, o si esa lista sintética no fue vinculada en Suplai. No hay promociones que validar.

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Listas | Vista, y si viene vacía la lista sintética, ambas dentro de `SistelConnector` | Rawson puede no tener maestro de listas | Exigir `product.pricelist` |
| Precio | `PrecioFinal` | Sistel manda el final | IVA de GEV |
| Alias | Lo resuelve el conector | Es credencial, no un argumento de Claude | Pedir el nombre de la vista en la tool |
| Escritura | [116](./116-mcp-pedidos-crud.md) | Misma carga | Sync desde el MCP |

---

## Alcance

### Incluido

Lectura para `connector = sistel`, diciendo si la lista es de la vista o sintética.

### Fuera de alcance

- Configurar el alias.
- Push.
- Promociones.

---

## Orden de implementación

La cubre el [117](./117-mcp-canal-erp-o-carga.md).

---

## Migración de base de datos

Sin migración.

---

## Plan de prueba en CI/CD

Con vista, `PrecioFinal` 50 llega como 50. Sin vista, `extra.synthetic` es verdadero. La lectura no llama `sync_orders_to_raw`.

---

## Plan de prueba humana

Tenant `rawson`.

1. `traer_precios_erp`. Anotar si la lista es de la vista o sintética.
2. `consultar_pedidos` (`origen=erp`), `traer_clientes_erp`, `traer_productos_erp`.
3. `traer_promociones_erp` dice que no están soportadas.
4. Sin filas nuevas en `erp_orders_raw` ni en `pedidos_externos`.
5. Una fila faltante por el [116](./116-mcp-pedidos-crud.md), confirmar solo con un sí.
