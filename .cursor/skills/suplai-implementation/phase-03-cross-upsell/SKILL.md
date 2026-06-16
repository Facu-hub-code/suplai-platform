---
name: suplai-implementation-phase-03
description: Fase 3 cross-sell y up-sell — relaciones mock coherentes por marca. Usar tras Fase 1.
---

# Fase 3 — Cross-sell y Up-sell

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Input

- Catálogo Fase 1 (`categoria_1`, `product_code`, `nombre`)
- `marca_lider` del manifest

## Output

1. `phase-03-cross-sell.csv` — `base_product_code,related_product_code,reason,is_mock`
2. `phase-03-up-sell.csv` — misma estructura

## Reglas de relaciones

- **Cross-sell:** productos complementarios misma obra (ej. látex + rodillo, esmalte + diluyente). Misma `categoria_1` o rubro compatible.
- **Up-sell:** mismo producto en formato mayor (ej. 1L → 4L) o línea premium misma marca.
- Incluir al menos 1 relación que involucre producto estrella de `marca_lider`.
- Generar 8–15 pares cross y 5–10 pares up (no aleatorio puro).
- `is_mock=true`

## Generación (MANDATORIO — Usar Script)

Para preparar los mapeos de venta cruzada (Cross-sell) e incremental (Up-sell) cruzando el catálogo real y utilizando la lógica comercial y semántica de OpenAI:
```bash
python scripts/fase-03-cross-upsell/preparar_cross_upsell.py --esquema {schema}
```
Esto creará los archivos `phase-03-cross-sell.csv` y `phase-03-up-sell.csv` en la carpeta `outputs` del tenant.

## Carga a la Base de Datos (MANDATORIO — Usar Script)

Para limpiar mapeos anteriores y cargar los nuevos de forma segura y validada:
```bash
python scripts/fase-03-cross-upsell/cargar_cross_upsell.py --esquema {schema}
```
Este script leerá el `tenant_id` del manifest, verificará que los códigos de producto referenciados existan en la tabla `{schema}.productos`, y realizará la inserción en las tablas públicas globales `public.tenant_cross_sell_mappings` y `public.tenant_up_sell_mappings`.

## Verificación

El script de carga realizará de forma automática la verificación imprimiendo los registros insertados. Si se desea verificar manualmente:
```sql
SELECT COUNT(*) FROM public.tenant_cross_sell_mappings WHERE tenant_id = '{tenant_id}';
SELECT COUNT(*) FROM public.tenant_up_sell_mappings WHERE tenant_id = '{tenant_id}';
```

## Cierre

- manifest fase `03` → `cargado`
- `filas_csv` = Cantidad de filas en `phase-03-cross-sell.csv`
- invitar Fase 4 (pedir `ciudad_base` si falta).

