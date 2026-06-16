---
name: suplai-implementation-phase-02
description: Fase 2 promociones — 4 promos mock activas desde top rotación. Usar tras Fase 1 cargada.
---

# Fase 2 — Promociones

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

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
- `titulo` / `descripcion`: LLM con gancho comercial + nombre producto
- `is_mock` = true

## Generación (MANDATORIO — Usar Script)

Para preparar el archivo CSV de promociones aplicando la alineación de la `marca_lider` y la redacción comercial de OpenAI:
```bash
python scripts/fase-02-promociones/preparar_promociones.py --esquema {schema}
```
Esto generará `implementacion/{schema}/outputs/phase-02-promociones.csv`.

## Carga a la Base de Datos (MANDATORIO — Usar Script)

Para aplicar las promociones de forma segura respetando las restricciones de base de datos (`promociones_semanales_fields_chk`):
```bash
python scripts/fase-02-promociones/cargar_promociones.py --esquema {schema}
```
Este script limpiará las promociones mock/template anteriores, buscará los nombres reales de los productos en la base de datos, mapeará los tipos de descuento (`percent`, `nominal`, `fixed_price`) e insertará los registros.

## Verificación

El script de carga realizará de forma automática la verificación imprimiendo los registros insertados. Si se desea verificar manualmente:
```sql
SELECT id, product_code, product_name, discount_kind, precio_promocional, descuento_percent, descuento_nominal FROM {schema}.promociones_semanales LIMIT 4;
```

## Cierre

- manifest fase `02` → `cargado`
- `filas_csv` = 4
- Asegurar que la Promo 1 se asocie a la `marca_lider` (manejado automáticamente por el script).
