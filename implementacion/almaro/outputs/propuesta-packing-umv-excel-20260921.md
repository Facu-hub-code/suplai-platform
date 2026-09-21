# Almaro — criterio UMV endurecido con maestro Excel (2026-09-21)

**Fuente:** `productos 19092026.xls` (Claudia Romero, 19-sep-2026)  
**Extracto:** `inputs/productos-19092026-umv.csv` (21.955 filas)  
**Correcciones vs catálogo actual:** `outputs/propuesta-packing-umv-excel-20260921.csv`  
**Tenant:** `almaro` (sin rama)  
**Carga:** 2026-09-21 — 1.749 SKUs actualizados (`outputs/carga-packing-umv-excel-20260921-log.csv`)

El Excel de Almaro trae la UMV real. El nombre `12X24X20G` y Gonzales **no** alcanzan: por eso Rocklets Chico quedó como display y el precio es por unidad.

## Campos del maestro

| Excel | Significado | Campo Suplai |
|---|---|---|
| `UM de Ventas` (UN / DI / BU) | Cómo piden / arman el pedido | conversión display/bulto, no el precio |
| `UM Precio Sugerido` (UN / DI / BU) | Unidad del precio | **`umv_tipo`** |
| `DI-UN` | Unidades dentro de un display | `unidades_por_display` (si > 1) |
| `BU-DI` | Displays dentro de un bulto | `displays_por_bulto` (si hay display real) |
| `BU-UN` | Unidades dentro de un bulto | `unidades_por_bulto` si UMV=unidad |
| `Cant.Mínima de Venta` | Mínimo en UM de ventas | `cantidad_minima_de_venta` (pasado a UMV) |

En el archivo: 19.709 UN, 2.041 DI, 203 BU de ventas. El precio es UN en 20.989 filas.

## Regla (precio manda)

Suplai guarda `precio_unidad` = precio GEV por UMV. Hay que alinear UMV con **`UM Precio Sugerido`**, no con cómo se picking.

1. **Precio UN** → `umv_tipo=unidad`. El agente cotiza la tableta/bolsa/unidad. Si además `UM Ventas=DI`, “1 display” se convierte con `DI-UN`.
2. **Precio DI** → `umv_tipo=display`. 1 UMV = 1 display; `unidades_por_bulto = BU-DI`.
3. **Precio BU** → no hay UMV bulto: `unidad` con mínimo = `BU-UN` (pocos, sobre todo helados).
4. `DI-UN = 1` → no hay display interno: no llenar `unidades_por_display`.

### El caso taza 150 g y Rocklets Chico

| SKU | Excel UM ventas/precio | DI-UN | BU-DI | BU-UN | Qué hacer |
|---|---|---:|---:|---:|---|
| `12901` Águila taza 150 g | UN / UN | 15 | 4 | 60 | Ya está bien (no sale en el CSV de corrección) |
| `1009` Rocklets Chico | UN / UN | 24 | 12 | **288** | Hoy display ×12 → **unidad**, bulto 288 |
| `6408` Águila barrita | UN / UN | 24 | 24 | **576** | Hoy display ×24 → **unidad**, bulto 576 |
| `11658` Mini bolsa | UN / UN | 1 | 32 | 32 | Ya está bien (sin display) |

## Delta vs catálogo actual (3.244 SKUs)

| | n |
|---|---:|
| Match con Excel | 3.043 |
| Sin Excel (códigos no Arcor / internos) | 201 |
| Ya alineados | 1.294 |
| **A corregir** | **1.749** |
| display → unidad (precio UN) | 248 |
| unidad → display (precio DI) | 547 |
| Cambia unidades por bulto | 1.353 |

Cargado 2026-09-21. Catálogo: 3.244 SKUs, **682 display / 2.562 unidad**. Vectorize encolado 1.749.
