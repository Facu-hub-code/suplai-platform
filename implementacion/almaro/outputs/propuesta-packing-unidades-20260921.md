# Almaro — regla de nombres y packing (2026-09-21)

**Tenant:** `almaro`  
**Path:** `implementacion/almaro/` (sin rama)  
**CSV:** `outputs/propuesta-packing-unidades-20260921.csv`

El precio GEV no trae UMV. El packing está en el **nombre** (`4X15X150G`). Esta propuesta completa huecos; no pisa packing ya coherente.

## Convención Arcor `A x B x W`

Tres números al final del nombre:

`AGUILA TAZA FAMILIAR 4X15X150G` → A=4, B=15, W=150 g

| Si la UMV es… | A | B | Unidades por bulto |
|---|---|---|---|
| **unidad** (se vende la tableta/bolsa) | displays por bulto | unidades por display | A × B |
| **display** (se vende la caja) | displays por bulto = UMV por bulto | unidades adentro del display | A |

Dos números `32X150G`: A = unidades por bulto, **no hay display**.

## Cómo se eligió unidad vs display

1. Si Gonzales ya tiene packing, se copia el `umv_tipo`.
2. Si el `unidades_por_bulto` actual ya es igual a **A** → forma display (no multiplicar A×B).
3. Si el bulto actual ya es **A×B** → forma unidad.
4. Sin packing (bulto=1):
   - Keyword **unidad**: taza, familiar, pasta, bolsa, tomate, block, aireado…
   - Keyword **display**: mentho, topline, chicle, barrita, gomita, chupetín…
   - `Nx3x` / `Nx2x` de galletitas (Formis, Rumba, Hogareñas) → display del pack interno
   - Peso ≥ 50 g → unidad
   - Peso < 20 g → display
   - Resto → **unidad** (sesgo conservador: el precio GEV es por ítem, no por caja)

Ejemplo pedido: Chocolate Taza Águila 150 g = SKU `12901`.

| Campo | Hoy | Propuesto |
|---|---|---|
| umv_tipo | unidad | unidad (precio por tableta 150 g) |
| unidades_por_display | 15 | 15 |
| displays_por_bulto | vacío | **4** |
| unidades_por_bulto | 60 | 60 |

## Conteos del CSV

| Acción | Filas | Qué hace |
|---|---:|---|
| `cargar_packing_desde_nombre` | 1162 | SKU GEV con bulto=1: parsea A/B del nombre |
| `completar_unidades_por_display` | 235 | Ya era display; faltaba cuántas unidades trae |
| `completar_displays_por_bulto` | 130 | Ya era unidad con upd+upb; faltaba A (ej. 12901) |
| `revisar_ajuste` | 30 | Ajuste menor / umv |
| `copiar_gonzales_y_completar` | 1 | `1009` Rocklets Chico: UMV display (hoy figura unidad) |
| **Total** | **1558** | |

Confianza: 1280 alta, 277 media, 1 baja (`13339` BARRA COFL MANI 6X20X45G: Gonzales tiene bulto 20, el nombre implica 120).

No entran SKUs sin patrón (`6367` taza 250 g) ni los que ya están completos (`11658` Rocklets Mini Bolsa 32×150, unidad, sin display).

## Carga (2026-09-21)

Confirmado: **confirmar carga packing almaro**. Solo confianza alta.

| Dato | Valor |
|---|---|
| Schema | `almaro` |
| Tabla | `almaro.productos` |
| Filas actualizadas | **1280 / 1280** alta |
| Omitidas | 277 media + 1 baja (`13339`) |
| Vectorize | 1107 SKU encolados |
| Log | `outputs/carga-packing-unidades-20260921-log.csv` |

Verificación `12901`: `umv_tipo=unidad`, 15 un/display, **4 displays/bulto**, 60 un/bulto. `15506` taza 225 g: 12 / 3 / 36. `1009` Rocklets Chico: UMV display 24 / 12 / 12.

Catálogo post-carga: 3244 SKUs · 383 display · 2861 unidad · 540 con unidades/display · 678 con displays/bulto.
