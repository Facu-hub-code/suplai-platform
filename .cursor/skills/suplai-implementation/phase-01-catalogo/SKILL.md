---
name: suplai-implementation-phase-01
description: Fase 1 catálogo — Excel a CSV de productos enriquecidos y carga a Supabase. Usar tras preflight OK.
---

# Fase 1 — Catálogo

Prerequisito: Fase 0 `cargado` o `csv_listo` con gate OK.

## Input

- [ ] Excel en `implementacion/{schema}/inputs/`
- [ ] Confirmar columna de precio: **Precio Final** (reventa) salvo que el implementador diga Neto
- [ ] Para multi-hoja (Colormix): consolidar todas las hojas

## Output

1. **`phase-01-productos.csv`** (obligatorio) — headers en `implementacion/_template/outputs/phase-01-productos.csv`
2. **`phase-01-listas-precios.csv`** (obligatorio si solo hay un precio en Excel)

## Inferencia (por fila)

| Regla | Campo |
|-------|--------|
| `(B/12)`, `x12`, `12x` en nombre | `unidades_por_bulto` |
| Sin patrón | `1` |
| Default | `unidad_minima_de_venta=unidad`, `umv_tipo=unidad`, `en_catalogo=true` |
| Hoja Excel | `categoria_1`, `fuente_hoja` |
| NLP en nombre | `categoria_2`..`categoria_4` |
| Top ~20% marcas líderes del rubro | `rotacion_index` 0.75–0.95 |
| Resto | Pareto hacia 0.1 |
| LLM | `aliases` (pipe-separated en CSV), `descripcion`, `image_url` placeholder |
| Sin stock en Excel | `stock` 10–500 según rotación |
| Simulación | `is_mock=true` en CSV |

## Listas de precios mock

Crear 4 listas con multiplicadores 1.00, 1.15, 0.90, 0.85 sobre `precio_lista_1` por SKU.

## Validación antes de carga

- SKUs únicos
- `precio_lista_1` > 0
- Contar filas → anotar en manifest

Pedir: **"Revisá phase-01-productos.csv y confirmá carga"**.

## Carga MCP (tras confirmación)

Orden sugerido:

1. `INSERT` `{schema}.listas_precios` (4 filas) — anotar IDs
2. `INSERT` `{schema}.productos` en lotes
3. `INSERT` `{schema}.precios_productos` desde phase-01-listas-precios.csv
4. `INSERT` `{schema}.productos_aliases` (un alias por fila o split)

Contrastar columnas con `list_tables` verbose. No insertar columnas inexistentes.

## Verificación

- `COUNT(*)` productos = filas CSV (± rechazos documentados)
- `SELECT product_code, nombre, precio_unidad FROM {schema}.precios_productos pp JOIN {schema}.productos p LIMIT 3`

## Cierre

- `manifest.fases.01.estado = cargado`
- Detectar **marca_lider** (marca con más SKUs) → `manifest.marca_lider`
- Invitar Fase 2

## Colormix

Ver `docs/implementacion/colormix-notas.md`.
