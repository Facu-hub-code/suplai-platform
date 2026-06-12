# Guía de Uso — Fase 3: Cross-sell y Up-sell (suplai-implementation-phase-03)

Esta guía sirve para diseñar, mapear e impactar relaciones mock inteligentes de venta cruzada (Cross-sell) y venta incremental (Up-sell) asociadas a los productos del tenant.

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Como agente de IA, lee el catálogo generado en la Fase 1 (`outputs/phase-01-productos.csv`) y usa lógica semántica/LLM para estructurar los mapeos. Evita generar mapeos puramente aleatorios; deben tener coherencia comercial para no romper la experiencia en la tienda del cliente.

---

## 📋 Requisitos Previos

1. **Fase 1 completada**: El catálogo de productos debe estar cargado.
2. **tenant_id**: Debe estar registrado en el archivo `manifest.yaml` para mapear los registros en las tablas públicas globales.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Definición de Mapeos
Analizar el archivo `outputs/phase-01-productos.csv` para proponer:
- **Cross-sell (Venta Cruzada)**: 8 a 15 pares. Relaciones de complementariedad lógica (ej. Pintura Látex + Pincel/Rodillo, Diluyente + Esmalte sintético, Clavos + Martillo).
- **Up-sell (Venta Incremental)**: 5 a 10 pares. Relaciones del mismo producto en un empaque/tamaño más grande o línea premium (ej: Pintura 1L → Pintura 4L o Pintura 10L; Taladro 500W → Taladro Percutor Profesional 800W).

*Asegurarse de incluir al menos una relación cruzada que involucre a la `marca_lider` identificada en el manifest.*

### 2. Formato del CSV de Salida
Guardar los resultados en las rutas locales:
1. `implementacion/{schema}/outputs/phase-03-cross-sell.csv`
2. `implementacion/{schema}/outputs/phase-03-up-sell.csv`

Columnas: `base_product_code`, `related_product_code`, `reason`, `is_mock`.

---

## 💾 Carga a la Base de Datos (MCP Supabase)

Insertar los registros en la base de datos Supabase utilizando la conexión MCP.
> [!IMPORTANT]
> Estas tablas están en el esquema `public`, no en el esquema del cliente. Requieren el `tenant_id` UUID guardado en el manifest.

```sql
-- Insertar Cross-sell
INSERT INTO public.tenant_cross_sell_mappings (tenant_id, base_product_code, related_product_code, score, is_mock)
VALUES ('{tenant_id}', 'SKU_BASE', 'SKU_RELACIONADO', 1.0, true);

-- Insertar Up-sell
INSERT INTO public.tenant_up_sell_mappings (tenant_id, base_product_code, related_product_code, score, is_mock)
VALUES ('{tenant_id}', 'SKU_BASE', 'SKU_RELACIONADO', 1.0, true);
```

---

## 🔍 Verificación Post-Carga
Comprobar los registros insertados:
```sql
SELECT COUNT(*) FROM public.tenant_cross_sell_mappings WHERE tenant_id = '{tenant_id}';
SELECT COUNT(*) FROM public.tenant_up_sell_mappings WHERE tenant_id = '{tenant_id}';
```

---

## 🏁 Cierre de la Fase
1. Establecer `fases["03"].estado = "cargado"` y agregar `cargado_at` en el `manifest.yaml`.
2. Solicitar al implementador la **ciudad base** (ej. "Rosario", "Mendoza") para la Fase 4 si no está presente en el manifest.
