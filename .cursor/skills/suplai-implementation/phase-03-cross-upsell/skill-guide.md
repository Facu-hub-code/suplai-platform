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

## 💾 Carga a la Base de Datos (MANDATORIO — Usar Script)

Para aplicar las relaciones de forma segura y evitar inconsistencias o alucinaciones de códigos, se **debe ejecutar obligatoriamente** el script de carga automatizado:

```bash
python scripts/fase-03-cross-upsell/cargar_cross_upsell.py --esquema <nombre_esquema>
```

Este script se encargará de:
1. Leer el `tenant_id` del manifest del cliente.
2. Limpiar las relaciones previas (cross-sell y up-sell) del tenant para evitar duplicados.
3. Verificar que cada código de producto exista en la tabla `{schema}.productos` antes de insertar.
4. Mapear de forma precisa las prioridades y flags correspondientes en las tablas públicas globales `public.tenant_cross_sell_mappings` y `public.tenant_up_sell_mappings`.

---

## 🔍 Verificación Post-Carga

El script de carga realizará de forma automática la verificación imprimiendo los registros insertados. Si se desea verificar manualmente:
```sql
SELECT COUNT(*) FROM public.tenant_cross_sell_mappings WHERE tenant_id = '{tenant_id}';
SELECT COUNT(*) FROM public.tenant_up_sell_mappings WHERE tenant_id = '{tenant_id}';
```

---

## 🏁 Cierre de la Fase

1. Modificar el archivo `implementacion/{schema}/manifest.yaml`:
   - Cambiar `fases["03"].estado` a `cargado`.
   - Establecer `fases["03"].filas_csv` a la cantidad de filas del CSV de cross-sell (ej. `11`).
   - Registrar `fases["03"].cargado_at` al timestamp actual.
2. Invitar al usuario a avanzar a la **Fase 4 (Red Comercial)**. Pedir la **ciudad base** (ej. "Rosario", "Mendoza") si no está presente en el manifest (para `al_fuego` ya se cuenta con "Valle Escondido, Córdoba, Argentina").

