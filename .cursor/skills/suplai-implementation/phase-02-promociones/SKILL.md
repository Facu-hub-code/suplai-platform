---
name: suplai-implementation-phase-02
description: Fase 2 promociones — 4 promos mock activas desde top rotación. Usar tras Fase 1 cargada.
---

# Fase 2 — Promociones

Prerequisito: Fase 1 `cargado`, `phase-01-productos.csv` con `rotacion_index`.

## Input

- Top 4 `product_code` por `rotacion_index` DESC del CSV Fase 1
- `tenant_id` en manifest

## Output

`implementacion/{schema}/outputs/phase-02-promociones.csv`

## Matriz fija (4 filas)

| promo_id | producto | discount_kind | discount_value | lista_precios_id | min_qty_umv |
|----------|----------|---------------|----------------|------------------|-------------|
| 1 | Top 1 | percent_off | 10 o 15 | 1 | 1 |
| 2 | Top 2 | total_off | 500 o 1000 | 2 | 1 |
| 3 | Top 3 | fixed_price | precio_lista_1 * 0.88 | 1 | 3 o 5 |
| 4 | Top 4 | percent_off | 20 | 3 | 1 |

- `fecha_inicio` = hoy − 7 días
- `fecha_fin` = hoy + 30 días
- `activa` = true
- `titulo` / `descripcion`: LLM con gancho comercial + nombre producto (ver flujo-agentico-resumen)
- `is_mock` = true

## Carga MCP

Tabla `{schema}.promociones_semanales`:

- Mapear `discount_kind` → `discount_kind`, `descuento_percent` o `descuento_nominal` o `precio_promocional` según columnas reales (verificar MCP).
- `product_name` desde catálogo
- `lista_precios_id` numérico

## Verificación

`SELECT id, product_code, descripcion, fecha_inicio, fecha_fin FROM {schema}.promociones_semanales LIMIT 4`

## Cierre

- manifest fase `02` → `cargado`
- Mencionar que la promo 1 debe alinearse con `marca_lider` para efecto cruzado Fase 8
