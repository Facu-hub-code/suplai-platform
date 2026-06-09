---
name: enhance_descriptions
description: Proponer y aplicar descripciones comerciales optimizadas y alias locales para catálogos de productos a través de SerpAPI y OpenAI, eliminando el ruido de marketing para RAG.
---

# Catálogo — Enriquecer Descripciones y Alias (enhance_descriptions)

Este flujo permite auditar y reescribir las descripciones de los productos y generar alias regionales de calidad para un tenant en Supabase. Elimina el ruido gramatical/publicitario (como *"Descubre..."*, *"Ideal para tu negocio..."*, *"Te traemos..."*) para que el RAG del agente identifique los productos con mayor velocidad y precisión.

> [!IMPORTANT]
> **REGLA DE OBLIGADA LECTURA PARA EL AGENTE**: Antes de ejecutar cualquier paso de esta skill, el agente **DEBE LEER obligatoriamente** la guía de uso detallada en [skill-guide.md](./skill-guide.md). Esto asegura que se realicen los auto-chequeos correctos, se apliquen los guardrails contra alucinaciones locales y se comprenda el flujo de validación proactiva.

---

## 1. Identificar el Esquema y Origen

1. Preguntar al implementador por el **`esquema`** del tenant (ej: `gonzales`).
2. Determinar la fuente de productos:
   - **Opción A (CSV del Usuario)**: El usuario provee una ruta a un CSV con las columnas `codigo_producto`, `nombre`, `descripcion` de los productos que desea enriquecer.
   - **Opción B (Auto-Detección)**: El agente analiza la base de datos del tenant (vía Supabase MCP `list_tables` con `verbose=true` para inspeccionar productos/aliases o queries directas) para seleccionar automáticamente hasta **N productos** (50 por defecto, o configurable mediante `--limite`) que considere ambiguos, confusos para RAG (ej: marcas/chocolates sin el sustantivo "chocolate", jugos sin "jugo") o que carezcan de alias y sustantivos de categoría.

---

## 2. Preparación de Candidatos (Solo Opción B)

1. Si no hay CSV de entrada provisto, el agente debe ejecutar el script `scripts/buscar_candidatos.py` para recopilar automáticamente los productos más ambiguos o desclasificados del catálogo del tenant. Se puede pasar el parámetro opcional `--limite` (ej: `--limite 100`):
   ```bash
   python scripts/buscar_candidatos.py --esquema {esquema} [--limite {limite}]
   ```
2. Este script consultará la base de datos y escribirá la lista propuesta de candidatos en un CSV temporal:
   `implementacion/{esquema}/inputs/candidatos_a_enriquecer.csv`
   - Formato requerido generado automáticamente por el script:
     ```csv
     codigo_producto,nombre,descripcion
     12397,COFLER RELLENA YOGURT FRUTILLA,"Descubre el sabor..."
     ```
3. Presentar los candidatos al implementador y pedir confirmación:
   > *"Detecté {limite} productos en la base de datos que se beneficiarían de mejores descripciones y alias (ej: carecen de categoría o contienen relleno). ¿Confirmás iniciar la generación?"*

---

## 3. Ejecutar Enriquecimiento (Dry Run)

Una vez confirmados los candidatos o especificado el CSV de entrada:

1. Ejecutar el script `scripts/enriquecer_catalogo.py` con los argumentos:
   ```bash
   python scripts/enriquecer_catalogo.py --esquema {esquema} --csv-entrada implementacion/{esquema}/inputs/candidatos_a_enriquecer.csv --csv-salida implementacion/{esquema}/outputs/vista_previa_enriquecimiento.csv
   ```
2. El script consultará **Serper** (opción preferida y más barata, requiere configurar `SEARCH_PROVIDER=serper` y `SERPER_API_KEY` en el archivo `.env`) o **SerpAPI** (Google restringido a `mercadolibre.com.ar` y `carrefour.com.ar`) y **OpenAI** (`gpt-4o-mini` por defecto) para generar descripciones B2B factuales y alias limpios para el contexto de la distribuidora.
3. El resultado se guardará en `implementacion/{esquema}/outputs/vista_previa_enriquecimiento.csv`.

---

## 4. Revisión Manual por el Implementador

> [!TIP]
> **Validación Proactiva por el Agente**:
> Antes de presentar el resultado final al usuario, lee el archivo de vista previa generado (`implementacion/{esquema}/outputs/vista_previa_enriquecimiento.csv`). Si detectas alucinaciones obvias o errores groseros del LLM de fondo (por ejemplo, clasificar un producto comestible o golosina como un spray de pintura, herramienta industrial o software debido a su marca), edita el CSV proactivamente de forma directa para corregir la descripción y alias. Informa al usuario en tu respuesta sobre qué correcciones proactivas realizaste para ahorrarle trabajo.

1. Informar al implementador del éxito de la generación:
   > *"Terminé de generar la propuesta de descripciones. Podés revisarla abriendo el archivo en Excel:*
   > *[vista_previa_enriquecimiento.csv](implementacion/{esquema}/outputs/vista_previa_enriquecimiento.csv)*
   > 
   > *Instrucciones para la revisión:*
   > *- Podés editar la columna `descripcion_mejorada` o `alias_propuestos` (separados por `|`).*
   > *- Cambiá el valor de `accion` a `OMITIR` en cualquier fila que NO desees actualizar en la base de datos.*
   > *- Cuando termines, guardá el archivo y decime: **aplicar cambios** o **confirmar catálogo**."*

---

## 5. Aplicar Cambios en Supabase

Cuando el implementador dé el visto bueno:

1. Asegurar que las variables de base de datos están configuradas en `.env` (particularmente `SUPABASE_DB_URL`).
2. Ejecutar la actualización masiva utilizando el flag `--aplicar`:
   ```bash
   python scripts/enriquecer_catalogo.py --esquema {esquema} --aplicar --csv-entrada implementacion/{esquema}/outputs/vista_previa_enriquecimiento.csv
   ```
3. El script actualizará las tablas `{esquema}.productos` y `{esquema}.productos_aliases`.
4. El script encolará la re-vectorización en el backend llamando a `POST /{schema}/productos/vectorize` (usando `BACKEND_URL`).
5. Mostrar un resumen con los totales de productos y alias modificados, y reportar explícitamente al usuario si la re-vectorización en el backend se encoló con éxito o si hubo algún error.
