# Almaro — catálogo, listas y precios GEV

**Tenant:** `almaro`  
**Fecha:** 2026-09-16  
**Path:** `implementacion/almaro/` (sin rama)

Bajado vía API Railway (`POST /almaro/erp/load-*`, `promote-products-bulk`, `price-lists-raw/{id}/link`, `sync-prices`, `sync`). Sin INSERT directo a `productos`. Mock **no** se purgó. `onboarding-apply` no se usó.

## Probe / espejo

| Origen | Resultado |
|---|---|
| `getListaPrecios` (vía `load-price-lists`) | 16 cabeceras |
| `getArticulos` (vía `load-products`) | 3244 SKUs |
| `getDetallePrecios/?id_vendedor=1463` (vía `load-prices`) | 51517 filas |

Precios GEV: neto × 1.21 IVA. Token fuera de git.

## Operativo (después de promover)

| Tabla | Count |
|---|---|
| `erp_products_raw` | 3244 |
| `erp_price_lists_raw` | 16 |
| `erp_prices_raw` | 51517 |
| `productos` | 3300 (943 mock + 2357 altas; 887 SKU overlap; 56 mock-only) |
| `listas_precios` | 21 (5 mock sin `erp_list_id` + 16 GEV nuevas) |
| `precios_productos` | 54992 (3772 mock + 51220 GEV) |

`sync-prices`: 51220 creados, 0 errores, **297** bloqueados (SKU en detalle de precios sin fila en `productos` / `getArticulos`).  
`/sync`: 3244 stock, 0 errores precios (las listas mock siguen sin `erp_list_id`).

Promote HTTP 502 a ~300 s (timeout Railway); el worker terminó: `pending=0`.

## Listas GEV (ids 6–21)

| id | nombre | erp_list_id | filas precio |
|---|---|---|---|
| 6 | arcorencasa | CASA | 3191 |
| 7 | AUTOSERV Y ORIENTALE | 02 | 3211 |
| 8 | CLUB ARCOR | LCA | 3198 |
| 9 | CONSUPASCUAS | CPAS | 3208 |
| 10 | INTERIOR | 07 | 3211 |
| 11 | KIPP-GA | 05 | 3257 |
| 12 | LISTA ARCOR | LA | 3259 |
| 13 | LISTA D | 99 | 3211 |
| 14 | lista p petroleras | BRA | 3200 |
| 15 | NO | TRAD | 3204 |
| 16 | NO USAR | LAASS | 3251 |
| 17 | PETRO | 91 | 3211 |
| 18 | PETRO YPF | PETRO | 3211 |
| 19 | SUPERMERCADO | LP | 3211 |
| 20 | TRADICIONAL | 06 | 3216 |
| 21 | TRADICIONAL CADENIZA | 01 | 3267 |

Listas mock 1–5 (`Lista 1`–`4`, `Default`) intactas, sin vínculo ERP.

## Muestra

Overlap mock ∩ GEV: `1002` Cereal Mix (stock 4552), `10057` Mentho Plus (353), `1009` Rocklets (470).  
SKUs nuevos GEV: `0102` Sugus Max ananá, `0104` Sugus Max frutilla, `0105` Sugus Max tutti frutti (stock 0). También se dio de alta `0000` Saldos Iniciales (artículo GEV).

## Fuera de este paso

Clientes/vendedores no se reasignaron a las listas GEV. PdV mock siguen en listas 1–5.
