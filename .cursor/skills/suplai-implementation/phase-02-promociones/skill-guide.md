# Guía de Uso — Fase 2: Promociones (suplai-implementation-phase-02)

Esta guía detalla el proceso para diseñar, generar e insertar 4 promociones mock activas vinculadas a los productos de mayor rotación del catálogo del tenant.

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Si eres un agente de IA leyendo esta guía, recuerda que **puedes y debes realizar este flujo de forma autónoma** para el usuario.
> Genera el CSV de promociones a partir del catálogo procesado en la Fase 1, pídele confirmación rápida al usuario mostrando los títulos comerciales redactados y luego ejecuta la inserción vía MCP.
>
> **Grafo Comercial (Efecto Cruzado)**:
> Al elegir y redactar las promociones, asegúrate de que la **Promo 1** (primer producto del top de rotación) se asocie a la `marca_lider` del tenant. Esta misma marca/producto se usará posteriormente en las alertas de calidad e insights de la Fase 8 para generar un flujo de simulación coherente (efecto cruzado).

---

## 📋 Requisitos Previos

1. **Fase 1 completada**: El catálogo de productos debe estar insertado en la base de datos (con estado `cargado` en `manifest.yaml`).
2. **Productos con rotación**: Existencia de `outputs/phase-01-productos.csv` con valores válidos en la columna `rotacion_index` and `product_code`.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Identificación del Top de Productos
- Leer el archivo `outputs/phase-01-productos.csv` de la carpeta de outputs del tenant.
- Filtrar y ordenar los productos de forma descendente utilizando la columna `rotacion_index`.
- Seleccionar los **4 productos con mayor índice de rotación** (Top 1, Top 2, Top 3 y Top 4).

### 2. Generación de la Matriz de Promociones
Para los 4 productos seleccionados, construir las promociones siguiendo este diseño:

| ID Promo | Producto | Tipo de Descuento (`discount_kind`) | Valor (`discount_value`) | Lista de Precios Afectada (`lista_precios_id`) | Cantidad Mínima UMV (`min_qty_umv`) |
|---|---|---|---|---|---|
| **1** | Top 1 | `percent_off` (Porcentaje) | `10` o `15` | `1` (Lista Base) | `1` |
| **2** | Top 2 | `total_off` (Monto Fijo de Descuento) | `500` o `1000` | `2` (Lista Minorista) | `1` |
| **3** | Top 3 | `fixed_price` (Precio Promocional Fijo) | `precio_lista_1 * 0.88` | `1` (Lista Base) | `3` o `5` |
| **4** | Top 4 | `percent_off` (Porcentaje) | `20` | `3` (Lista Mayorista) | `1` |

#### Parámetros Generales:
- `fecha_inicio`: Fecha actual del sistema menos 7 días (formato ISO `YYYY-MM-DD`).
- `fecha_fin`: Fecha actual del sistema más 30 días (formato ISO `YYYY-MM-DD`).
- `activa`: `true`
- `is_mock`: `true`
- **Títulos y Descripciones Comerciales**: Usar el LLM para generar textos creativos y atrayentes (ej. *"¡Super Descuento Semanal! 15% OFF en [Nombre del Producto]"* o *"Imperdible: precio mayorista llevando más de 3 unidades"*).

---

## 📂 Entregables (Outputs)

Generar el archivo en la ruta del tenant:
**`implementacion/{schema}/outputs/phase-02-promociones.csv`**

- **Columnas**: `promo_id`, `product_code`, `titulo`, `descripcion`, `discount_kind`, `discount_value`, `lista_precios_id`, `min_qty_umv`, `fecha_inicio`, `fecha_fin`, `activa`, `is_mock`.

---

## 💾 Carga a la Base de Datos (MANDATORIO — Usar Script)

Para aplicar las promociones de forma segura y consistente, evitando conflictos con las restricciones de la base de datos, se **debe ejecutar obligatoriamente** el script de carga automatizado:

```bash
python scripts/fase-02-promociones/cargar_promociones.py --esquema <nombre_esquema>
```

Este script se encargará de:
1. Eliminar las promociones mock o remanentes del esquema.
2. Resolver el nombre real del producto en base al catálogo actual.
3. Formatear la descripción agregando el título.
4. Mapear de forma precisa el tipo de descuento y su respectiva columna en la base de datos (`descuento_percent`, `descuento_nominal` o `precio_promocional`).

---

## 🔍 Verificación Post-Carga

El script de carga realizará de forma automática la verificación imprimiendo las promociones cargadas. Si se desea verificar manualmente:
```sql
SELECT id, product_code, product_name, discount_kind, precio_promocional, descuento_percent, descuento_nominal, lista_precios_id
FROM <nombre_esquema>.promociones_semanales
ORDER BY id ASC;
```

---

## 🏁 Cierre de la Fase

1. Modificar el archivo `implementacion/{schema}/manifest.yaml`:
   - Cambiar `fases["02"].estado` a `cargado`.
   - Establecer `fases["02"].filas_csv = 4`.
   - Registrar `fases["02"].cargado_at` al timestamp actual.
2. Invitar al usuario a avanzar a la **Fase 3 (Cross-sell y Up-sell)**.
