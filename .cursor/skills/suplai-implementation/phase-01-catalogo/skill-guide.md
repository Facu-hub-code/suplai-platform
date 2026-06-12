# Guía de Uso — Fase 1: Catálogo (suplai-implementation-phase-01)

Esta guía sirve como fuente de verdad para entender, preparar, ejecutar y validar la Fase 1 del Onboarding Agéntico de un tenant en la plataforma Suplai Sales.

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Si eres un agente de IA leyendo esta guía, recuerda que **puedes y debes ejecutar estos pasos de forma autónoma** para el usuario. 
> Explícale al usuario que te encargas de:
> 1. Analizar y consolidar el Excel original.
> 2. Generar el archivo de productos y los archivos independientes de listas de precios.
> 3. Ejecutar las inferencias comerciales y estructuración.
> 4. Cargar la información a Supabase (usando herramientas MCP).
>
> **MANDATORIO**: Antes de iniciar la carga a la base de datos, **debes pedir la confirmación explícita del usuario** mostrando el conteo de filas y una vista previa del CSV de productos generado.
> 
> **Autochequeo (Self-check)**:
> - Confirmar que la Fase 0 (`preflight`) se haya completado con éxito (`manifest.fases["00"].estado = cargado`).
> - Verificar la existencia del Excel en `implementacion/{schema}/inputs/`.
> - Validar que la conexión MCP a Supabase esté activa y configurada en modo escritura (sin `&read_only=true` en `.cursor/mcp.json` temporalmente).

---

## 📋 Requisitos Previos

Antes de ejecutar la Fase 1, asegúrate de contar con los siguientes elementos:

1. **Estructura del Tenant**: Directorio creado en `implementacion/{schema}/` y `manifest.yaml` inicializado.
2. **Archivo Excel de Origen**: Colocado en `implementacion/{schema}/inputs/` (ej. `lista-productos.xlsx`).
3. **Columna de Precio**: Confirmar con el implementador qué columna representa el **Precio Final** (venta/reventa al cliente final). Si el implementador indica "Neto", se usará Neto como base.
4. **Librerías de Python**: Entorno con `pandas` y `openpyxl` instalados en caso de requerir ejecuciones de scripts de procesamiento local.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Lectura y Consolidación del Excel
- Leer el archivo Excel provisto.
- En caso de hojas múltiples (por ejemplo, en el caso de distribuidores como Colormix), consolidar todas las filas en una única estructura de datos unificada, mapeando la hoja origen al campo `fuente_hoja`.

### 2. Procesamiento e Inferencias Comerciales
Por cada producto (fila), aplicar las siguientes reglas para completar los campos enriquecidos:

- **Unidades por Bulto**: 
  - Si el nombre del producto incluye patrones como `(B/12)`, `x12` o `12x`, extraer el número (en este caso `12`) y asignarlo a `unidades_por_bulto`.
  - Si no se detecta ningún patrón, establecer `unidades_por_bulto = 1`.
- **Valores por Defecto**:
  - `unidad_minima_de_venta = 1`
  - `umv_tipo = "unidad"`
  - `en_catalogo = true`
- **Estructura de Categorías**:
  - `categoria_1`: Nombre de la hoja de Excel o rubro principal.
  - `categoria_2` a `categoria_4`: Derivados mediante análisis NLP / patrones en el nombre del producto.
- **Priorización e Índice de Rotación**:
  - Identificar marcas líderes del rubro (ej. Sika, Alba, etc.). Asignar a estas marcas líderes un `rotacion_index` alto (entre `0.75` y `0.95`).
  - Para el resto de marcas, aplicar una distribución Pareto descendente con base en `0.1`.
- **Enriquecimiento con LLM**:
  - Generar `aliases` comerciales en formato texto separado por tuberías (`|`) (ej. `sika 1 | sika impermeabilizante | sika uno`).
  - Crear una `descripcion` comercial limpia y atractiva para RAG.
  - Asignar un `image_url` placeholder descriptivo basado en la categoría.
- **Stock por Defecto**: Si el Excel no provee stock real, asignar valores simulados de stock entre `10` y `500` unidades según el índice de rotación.
- **Flag de Simulación**: Establecer `is_mock = true` para diferenciar los datos de prueba de los reales de producción.

### 3. Generación de Listas de Precios Mock
Si el Excel solo incluye una columna de precio (Precio Lista 1), se deben simular **4 listas de precios independientes** aplicando multiplicadores fijos sobre el precio base:

| ID de Lista | Nombre Comercial | Multiplicador sobre Lista 1 |
|---|---|---|
| **1** | Lista Base (Público) | 1.00 |
| **2** | Lista Minorista Sugerido | 1.15 |
| **3** | Lista Mayorista Especial | 0.90 |
| **4** | Lista Gran Distribuidor | 0.85 |

---

## 📂 Entregables (Outputs)

Al finalizar el procesamiento, se deben escribir los siguientes archivos en la carpeta de salida `implementacion/{schema}/outputs/`:

1. **`phase-01-productos.csv`**
   - Contiene la información principal de los productos.
   - Columnas: `product_code`, `nombre`, `descripcion`, `categoria_1`, `categoria_2`, `categoria_3`, `categoria_4`, `rotacion_index`, `stock`, `unidades_por_bulto`, `unidad_minima_de_venta`, `umv_tipo`, `en_catalogo`, `aliases`, `image_url`, `is_mock`.
2. **`phase-01-lista-precios-{lista_precios_id}.csv`** (Un archivo individual por cada lista de precios, ej. `phase-01-lista-precios-1.csv`, `phase-01-lista-precios-2.csv`, etc.).
   - Columnas: `product_code`, `precio_unidad`, `is_mock`.

---

## 💾 Carga a la Base de Datos (MCP Supabase)

Una vez que el implementador ha revisado y confirmado el contenido de los CSVs generados, el agente de IA debe aplicar la carga ejecutando las siguientes sentencias de inserción (vía Supabase MCP):

### 1. Inserción de Listas de Precios
Asegurar la existencia de las 4 listas de precios en la tabla del esquema correspondiente:
```sql
INSERT INTO {schema}.listas_precios (id, nombre, descripcion, is_mock) 
VALUES 
  (1, 'Lista 1', 'Lista Base (Público)', true),
  (2, 'Lista 2', 'Lista Minorista Sugerido', true),
  (3, 'Lista 3', 'Lista Mayorista Especial', true),
  (4, 'Lista 4', 'Lista Gran Distribuidor', true)
ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre;
```

### 2. Inserción de Productos
Insertar el catálogo desde `phase-01-productos.csv` a la tabla `{schema}.productos` en lotes optimizados para evitar sobrecargar la conexión.

### 3. Inserción de Precios
Por cada archivo `phase-01-lista-precios-{id}.csv` generado (del 1 al 4), insertar los registros en la tabla `{schema}.precios_productos` asociándolos al `lista_precios_id` correspondiente.

### 4. Inserción de Aliases
Para cada producto, descomponer el campo `aliases` (separado por `|`) e insertar cada término como una fila en `{schema}.productos_aliases`.

### 5. Re-vectorización del Catálogo (CRÍTICO)
Una vez guardados todos los productos y aliases en Supabase, el agente **debe disparar la re-vectorización** en el backend para generar los embeddings en la base vectorial (PGVector/Supabase). Sin esto, las búsquedas semánticas del agente de WhatsApp no funcionarán.

- **Método**: HTTP `POST`
- **URL**: `https://web-production-f544f.up.railway.app/{schema}/productos/vectorize` (o `BACKEND_URL` configurada en el `.env`)
- **Body**: Un array JSON con los `product_code` cargados.
  ```json
  [
    "SKU-001",
    "SKU-002",
    "SKU-003"
  ]
  ```
- **Validación**: Comprobar que el backend retorne `200 OK` (que indica que se encolaron los trabajos de vectorización con éxito).

---

## 🔍 Verificación Post-Carga

El agente debe ejecutar consultas de verificación para certificar la integridad de la carga:
- **Conteo total**:
  ```sql
  SELECT COUNT(*) FROM {schema}.productos;
  ```
  Debe coincidir exactamente con el número de filas del archivo `phase-01-productos.csv`.
- **Muestra cruzada de precios**:
  ```sql
  SELECT p.product_code, p.nombre, pp.lista_precios_id, pp.precio_unidad 
  FROM {schema}.productos p 
  JOIN {schema}.precios_productos pp ON p.product_code = pp.product_code 
  LIMIT 6;
  ```

---

## 🏁 Cierre de la Fase

Una vez verificados los datos en base de datos:
1. Actualizar el archivo `implementacion/{schema}/manifest.yaml`:
   - `fases["01"].estado = "cargado"`
   - `fases["01"].filas_csv = {cantidad_productos}`
   - `fases["01"].cargado_at = {timestamp_actual}`
   - `marca_lider = "{marca_mas_repetida}"` (identificar la marca con mayor cantidad de SKUs cargados).
2. Invitar formalmente al usuario a continuar con la **Fase 2 (Promociones)**.
