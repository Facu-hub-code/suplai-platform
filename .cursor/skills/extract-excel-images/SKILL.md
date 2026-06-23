---
name: extract_excel_images
description: Extraer imágenes de productos embebidas en las celdas de un archivo de Excel (.xlsx), subirlas a Supabase Storage y asociarlas de forma genérica mediante auto-detección inteligente de columnas.
---

# Catálogo — Extraer y Cargar Imágenes desde Excel (extract_excel_images)

Este flujo permite extraer de forma masiva las imágenes reales embebidas en las hojas de cálculo de Excel (`.xlsx`) provistas por los clientes, subirlas a un bucket de almacenamiento público dedicado en Supabase Storage, y actualizar sus URLs públicas tanto en la base de datos como en los archivos CSV locales.

El script cuenta con un **motor de auto-detección inteligente** diseñado para funcionar de manera genérica con cualquier estructura de Excel (las columnas de nombres, códigos e imágenes varían en cada distribuidora).

---

## 1. Requisitos Previos

1. **Dependencias del Entorno**:
   - `openpyxl`: Para leer el archivo Excel e inspeccionar las imágenes incrustadas.
   - `pillow`: Para validar y procesar formatos de imagen si es necesario.
   - `asyncpg`: Para la conexión y batch updates a PostgreSQL.
   - Instalar las dependencias ejecutando:
     ```bash
     pip install openpyxl pillow asyncpg requests python-dotenv
     ```
2. **Esquema y Bucket**:
   - Tener definido el `esquema` del tenant (ej: `distribuidora_lyl`, `vadra`, `el_gigante`).
   - Tener cargado previamente el catálogo de productos base en la base de datos (para poder hacer la coincidencia semántica de nombres).
   - Tener configurado el archivo `.env` en la raíz con:
     * `SUPABASE_DB_URL`: Para actualizar la tabla de productos.
     * `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`: Para la creación del bucket y la subida de las imágenes.
     * `BACKEND_URL`: Para disparar el encolamiento de re-vectorización.

---

## 2. Funcionamiento de la Auto-detección Genérica

Cuando se ejecuta el script para un esquema, este realiza los siguientes pasos de forma automatizada:
1. **Descarga de catálogo**: Recupera de la base de datos los códigos y nombres de productos cargados.
2. **Análisis de imágenes**: Escanea la hoja activa y cuenta cuántas imágenes están ancladas en cada columna. La columna con mayor densidad es elegida como la **Columna de Imágenes**.
3. **Mapeo de Nombres**: Toma una muestra de hasta 200 filas y evalúa qué columna tiene mayor similitud léxica (normalizada) con los nombres de productos existentes en la base de datos. Dicha columna se marca como la **Columna de Nombres**.
4. **Mapeo de Códigos**: Analiza qué columna coincide con los códigos exactos del catálogo en la base de datos para marcarla como la **Columna de Códigos** (si aplica).
5. **Asociación**: Asocia cada imagen encontrada a su producto correspondiente comparando el nombre de la fila con el catálogo de base de datos.

---

## 3. Ejecución de la Carga Masiva

Para realizar la asociación de imágenes para una nueva distribuidora:

```bash
python scripts/fase-01-catalogo/cargar_imagenes_excel.py --esquema {esquema}
```

### Argumentos de Configuración Opcionales:
* `--excel`: Ruta al archivo Excel si no sigue el patrón estándar (`implementacion/{esquema}/inputs/lista-productos.xlsx`).
* `--col-nombre`: Forzar una columna manual para el nombre (ej: `--col-nombre C` o `--col-nombre 3`).
* `--col-codigo`: Forzar una columna manual para el código (ej: `--col-codigo A`).
* `--fila-inicio`: Fila donde comienzan los productos en el Excel (por defecto es 1).
* `--forzar-prefijo`: Si deseas mapear de forma secuencial ordenada utilizando un prefijo de producto (ej: `--forzar-prefijo LYL` para asociar en el orden secuencial en el que fueron inicialmente importados).

---

## 4. Ejemplos de Uso

### Caso A: Carga estándar (Auto-detecta columnas por coincidencia léxica con DB)
```bash
python scripts/fase-01-catalogo/cargar_imagenes_excel.py --esquema distribuidora_lyl
```

### Caso B: Forzando columnas manuales si hay ambigüedad en las cabeceras
```bash
python scripts/fase-01-catalogo/cargar_imagenes_excel.py --esquema distribuidora_lyl --col-nombre C --col-codigo A
```

### Caso C: Forzando mapeo secuencial ordenado para un nuevo esquema
```bash
python scripts/fase-01-catalogo/cargar_imagenes_excel.py --esquema distribuidora_lyl --forzar-prefijo LYL
```
