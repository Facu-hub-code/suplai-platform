# Notas de implementación — Colormix

Tenant piloto: **`colormix`** (pinturería / reventa). Schema creado por registro web; partió vacío.

## Excel de entrada

| Campo | Valor |
|-------|--------|
| Archivo | `COLORMIX-REVENTA - 01-06-2026.xlsx` (copiar a `implementacion/colormix/inputs/`) |
| Estructura | ~57 hojas, una por marca/rubro (ej. `ALBA-HOGAR`, `RUST-OLEUM`, `SIKA`) |
| Columnas | `Articulo`, `Denominacion`, `Precio Neto`, `Precio Final` |
| Título lista | "Lista exclusiva para clientes de Reventa" |

## Mapeo recomendado (Fase 1)

| Excel | Campo Suplai |
|-------|----------------|
| `Articulo` | `product_code` (validar unicidad al consolidar hojas) |
| `Denominacion` | `nombre` (limpiar espacios y prefijos `***`) |
| `Precio Final` | `precio_lista_1` (reventa; confirmar con implementador si usan Neto) |
| Nombre de hoja | `categoria_1` / `fuente_hoja` |

## Particularidades pinturería

- Pocos productos traen `(B/12)`; predominan litros y `CM3` → **`unidades_por_bulto` = 1** salvo patrón explícito.
- `unidad_minima_de_venta`: "lata", "balde", "botella" según denominación; default `unidad`.
- Categorías: nivel 1 = hoja Excel; niveles 2–4 inferidos (ej. `Pinturas` → `Látex exterior` → `Albalux`).
- Aliases: jerga ferretería/pinturería (ej. "latex celeste 4L", "esmalte albalux").
- Imágenes mock: `/assets/mocks/categories/pinturas.png` o similar por rubro de hoja.
- Marcas líderes para Pareto: `ALBA`, `SIKA`, `PLAVICON`, `RUST-OLEUM` (ajustar según volumen de filas por hoja).

## Ciudad base sugerida

Pedir al implementador la ciudad real de la distribuidora Colormix (ej. Córdoba, Buenos Aires). Se usa en Fase 4 para dispersar clientes y nombres de zonas.

## Carpeta de trabajo

```text
implementacion/colormix/
  manifest.yaml
  inputs/   ← Excel aquí
  outputs/  ← CSV por fase
```

## Comandos útiles en Cursor

- "Implementar colormix" → skill orquestador
- "Colormix fase 1" → catálogo desde Excel
- Siempre revisar CSV antes de confirmar carga a Supabase
