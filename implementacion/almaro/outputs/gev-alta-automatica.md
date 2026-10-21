# Almaro — alta automática de productos GEV

**Fecha:** 2026-10-20  
**Tenant:** `almaro`

## Qué se comparó

`POST /almaro/erp/load-products` volvió a bajar la API de GEV y dejó el espejo al día (`synced_at` 2026-10-20 12:30 UTC).

| Origen | Cantidad |
|---|---|
| Artículos que devolvió la API en esta bajada | 3311 |
| Filas en `erp_products_raw` | 3315 |
| Filas del espejo refrescadas en esta bajada | 3311 |
| Filas en `productos` antes del alta | 3302 |
| En la API y no en `productos` | 13 |

Las 4 filas del espejo que no vinieron en esta bajada ya estaban en `productos`. No son un hueco. El listado de los 13 está en `outputs/gev-productos-faltantes-20261020.csv`.

`POST /almaro/erp/promote-products-bulk` dio de alta esos 13 (`created: 13`, `vectorized: 13`, sin errores). No pisa SKU que ya existían. Después del alta, la API y `productos` quedan alineados en ese diff.

## Por qué no entran solos

El job de las 6 horas llama `load_products_to_raw`. Eso hace upsert en `erp_products_raw` y no inserta en `productos`.

El alta al catálogo es `promote_erp_products_bulk` (`POST /{schema}/erp/promote-products-bulk`, o el confirm del MCP). Solo crea el SKU que está en el espejo y todavía no está en `productos`. No pisa uno que ya existe. Escribe descripción corta desde el nombre, UMV unidad y vectoriza. `en_catalogo` queda en el default `true`.

Nada de ese job llama al promote. Un producto nuevo de GEV queda en el espejo y el agente de WhatsApp no lo ve hasta que alguien dispara el alta.

## Qué haría falta para que sea automático

No se resuelve con datos del tenant. Hace falta un cambio en `backend/`: al terminar `load_products_to_raw` dentro de `run_erp_sync_job`, llamar `promote_erp_products_bulk` para los SKU que sigan sin fila en `productos`. El filtro de no pisar existentes ya está. Eso pide rama y PR. No se hizo en este paso.
