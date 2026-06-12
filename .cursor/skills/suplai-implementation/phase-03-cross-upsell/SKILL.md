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

## Carga MCP

Tablas `public` (requieren `tenant_id` UUID):

- `tenant_cross_sell_mappings`
- `tenant_up_sell_mappings`

Columnas típicas: `tenant_id`, `base_product_code`, `related_product_code`, pesos/flags según MCP.

**MUST** usar `tenant_id` de manifest, no inventar.

## Verificación

```sql
SELECT COUNT(*) FROM public.tenant_cross_sell_mappings WHERE tenant_id = '{tenant_id}';
```

## Cierre

manifest fase `03` → `cargado`; invitar Fase 4 (pedir `ciudad_base` si falta).
