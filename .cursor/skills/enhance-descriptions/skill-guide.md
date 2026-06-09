# Guía de Uso — Enriquecimiento de Catálogos (enhance_descriptions)

Esta guía sirve como fuente de verdad para entender, preparar y ejecutar el flujo de enriquecimiento de descripciones y alias de productos en los catálogos de los tenants de Suplai.

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Si eres un agente de IA leyendo esta guía, recuerda que **puedes y debes ejecutar estos pasos de forma autónoma** para el usuario. 
> Explícale al usuario que puedes encargarte de todo el flujo (buscar candidatos, enriquecer catálogo, mostrar vista previa y aplicar cambios a Supabase) si en su siguiente prompt te indica:
> 1. El **esquema del tenant** (ej. `gonzales`).
> 2. Si utilizará un **CSV de entrada** (Opción A) o si prefiere realizar **Auto-detección** (Opción B) desde la base de datos.
> 
> **MANDATORIO**: Antes de iniciar la ejecución, **debes preguntar activamente al usuario** si desea configurar parámetros de búsqueda específicos para el rubro (como `--dominios` específicos de ferretería o pinturería, o un `--sufijo-fallback` personalizado) y el modo de detalle de descripción deseado (`--modo-contexto` como `reducido` o `ampliado`).
> 
> Antes de ejecutar comandos, **realiza un autochequeo (self-check)** verificando la existencia y configuración de los siguientes elementos en el entorno local (puedes leer archivos o listar el directorio):
> - El archivo `.env` en la raíz del proyecto.
> - La presencia de las variables `OPENAI_API_KEY`, `SERPAPI_API_KEY` y `SUPABASE_DB_URL` en dicho `.env` (si faltan, avísale al usuario qué variables debe agregar).
> - Que las dependencias en `requirements.txt` estén instaladas o que puedas ejecutar scripts de Python.
> - La existencia de los scripts [buscar_candidatos.py](../../../scripts/buscar_candidatos.py) y [enriquecer_catalogo.py](../../../scripts/enriquecer_catalogo.py).
>
> Si el autochequeo es exitoso, infórmale al usuario que todo está listo y configurado, y procede a ejecutar las herramientas directamente según el flujo. Si falta algo, pídele al usuario que lo complete antes de iniciar.

---

## 📋 Requisitos Previos

Antes de ejecutar la skill, asegúrate de cumplir con los siguientes prerrequisitos en el entorno local:

### 1. Entorno de Python
Deberás contar con **Python 3.10+** instalado en el sistema.

### 2. Instalación de Dependencias
Instala las librerías de Python requeridas ejecutando el siguiente comando en la raíz del proyecto:
```bash
pip install -r requirements.txt
```
Las dependencias principales que se instalarán son:
- `asyncpg`: Para conectar de forma asíncrona con PostgreSQL/Supabase.
- `requests`: Para interactuar con las APIs de SerpAPI y OpenAI.
- `python-dotenv`: Para cargar variables de entorno desde el archivo `.env`.
- `pydantic`: Para estructuración de datos.

### 3. Configuración de Variables de Entorno (`.env`)
Debes tener un archivo `.env` configurado en la raíz del proyecto (`suplai-platform/`) con las siguientes credenciales:
```env
# OpenAI para la reescritura de descripciones y extracción de alias
OPENAI_API_KEY=tu-api-key-de-openai
OPENAI_MODEL=gpt-4o-mini

# Proveedor de búsqueda web (serper o serpapi). Se recomienda serper por ser más barato.
SEARCH_PROVIDER=serper

# API Key para Serper (requerido si SEARCH_PROVIDER=serper)
SERPER_API_KEY=tu-api-key-de-serper

# API Key para SerpAPI (requerido si SEARCH_PROVIDER=serpapi)
SERPAPI_API_KEY=tu-api-key-de-serpapi

# URL de conexión directa a la base de datos PostgreSQL de Supabase
SUPABASE_DB_URL=postgresql://<usuario>:<password>@<host>:<puerto>/postgres

# URL del backend para disparar la re-vectorización en RAG (Opcional, default: producción)
BACKEND_URL=https://web-production-f544f.up.railway.app
```

### 4. Configuración por Esquema (`config.json`) (Altamente Recomendado)
Para evitar ingresar los parámetros por consola en cada ejecución y forzar reglas específicas del catálogo al LLM, podés configurar un archivo `config.json` por distribuidora. El agente de IA **debe verificar activamente si existe o crearlo** si no lo encuentra.

El archivo debe vivir en: `implementacion/{esquema}/config.json`

**Estructura del archivo `config.json` (ejemplo para Vadra, distribuidora de vinos):**
```json
{
  "dominios": "losfenicios.com.ar,mercadolibre.com.ar,carrefour.com.ar",
  "sufijo_fallback": "vino bebida argentina",
  "modo_contexto": "ampliado",
  "instrucciones_extra": "REGLAS ADICIONALES PARA VINOS:\n1. OBLIGATORIEDAD DE MARCA/BODEGA: Es mandatorio incluir explícitamente la bodega productora (ej. Domaine Bousquet, Alta Yari) y la marca o línea comercial específica en la descripción técnica.\n2. ALIAS DE BODEGA: En los alias locales, incluye siempre el nombre de la bodega y de la línea del vino (ej. 'domaine bousquet', 'alta yari', 'ameri', 'gaia') además de los sinónimos comunes."
}
```
*Si un parámetro se pasa explícitamente por CLI (consola), este tendrá prioridad sobre el valor configurado en el `config.json`.*

---

## 🚀 Formas de Ejecución

Existen dos formas o caminos principales para preparar y enriquecer un catálogo:

### Opción A: A partir de un CSV provisto por el usuario
Usa esta opción cuando el implementador o el cliente ya posean un archivo CSV con los productos a procesar.

1. **Estructura del CSV de entrada**: Debe contener al menos las columnas `codigo_producto`, `nombre` y `descripcion` (o `product_code`, `name` y `description`).
2. **Ejecutar el enriquecimiento**:
   ```bash
   python scripts/enriquecer_catalogo.py --esquema <nombre_esquema> --csv-entrada <ruta_al_csv_de_entrada> --csv-salida <ruta_al_csv_de_salida_preview> [--dominios <dominios>] [--sufijo-fallback <sufijo>] [--modo-contexto <modo>]
   ```

---

### Opción B: Auto-Detección desde la Base de Datos
Usa esta opción cuando no haya un CSV de entrada y quieras auditar la base de datos para identificar automáticamente productos ambiguos, desclasificados o con exceso de texto publicitario (fluff) utilizando un sistema inteligente de puntuación de ambigüedad RAG.

1. **Obtener los candidatos**:
   Corre el script detector de candidatos pasando el esquema del tenant deseado. Puedes usar el parámetro opcional `--limite` (50 por defecto, o cualquier número, ej: 100):
   ```bash
   python scripts/buscar_candidatos.py --esquema <nombre_esquema> [--limite <cantidad>]
   ```
   *Esto generará automáticamente la lista en:*
   `implementacion/{nombre_esquema}/inputs/candidatos_a_enriquecer.csv`

2. **Ejecutar el enriquecimiento (Dry Run)**:
   ```bash
   python scripts/enriquecer_catalogo.py --esquema <nombre_esquema> --csv-entrada implementacion/{nombre_esquema}/inputs/candidatos_a_enriquecer.csv --csv-salida implementacion/{nombre_esquema}/outputs/vista_previa_enriquecimiento.csv [--dominios <dominios>] [--sufijo-fallback <sufijo>] [--modo-contexto <modo>]
   ```

---

## 🔍 Revisión Manual por el Implementador
El paso intermedio obligatorio antes de persistir los cambios:

> [!TIP]
> **Validación Proactiva por el Agente**:
> Antes de presentar el resultado de la vista previa al usuario, lee el archivo CSV generado en la ruta `<csv_salida>`. Si detectas alucinaciones obvias (como clasificar un producto comestible o golosina como un spray de pintura, herramienta industrial o software debido al nombre o marca), edita el CSV proactivamente de forma directa para corregir la descripción y alias. Informa al usuario sobre qué correcciones proactivas aplicaste para ahorrarle trabajo.

1. El implementador abre el archivo generado en la ruta `<csv_salida>` (ej. `implementacion/{nombre_esquema}/outputs/vista_previa_enriquecimiento.csv`) usando Excel o Google Sheets para facilitar la edición.
2. Revisa y ajusta los valores necesarios en las siguientes columnas:
   - `descripcion_mejorada`: Ajusta el texto de la descripción comercial final.
   - `alias_propuestos`: Modifica o agrega alias locales (separados por la tubería `|`).
   - `accion`: Cambia el valor de `ACTUALIZAR` a `OMITIR` en cualquier producto cuyos datos originales desees mantener intactos.
3. Guarda y exporta de nuevo el archivo como CSV, reemplazando el archivo original en la misma ruta dentro de la base de código (`implementacion/{nombre_esquema}/outputs/vista_previa_enriquecimiento.csv`).
4. Una vez guardado el archivo editado en la base de código, le indica al agente aplicar los cambios (ej. *"aplicar cambios"* o *"confirmar catálogo"*).

---

## 💾 Aplicar Cambios a la Base de Datos y Re-vectorización

Una vez que el archivo CSV revisado ha sido guardado de vuelta en la base de código, el agente ejecutará el comando con el flag `--aplicar` para leer las modificaciones y persistir los cambios en las tablas `{esquema}.productos` y `{esquema}.productos_aliases` de Supabase:

```bash
python scripts/enriquecer_catalogo.py --esquema <nombre_esquema> --aplicar --csv-entrada implementacion/<nombre_esquema>/outputs/vista_previa_enriquecimiento.csv
```
Al finalizar la ejecución, el script:
1. Reportará un resumen con la cantidad exacta de productos y alias actualizados de forma exitosa en la base de datos.
2. Disparará una solicitud al endpoint `POST /productos/vectorize` del backend (usando la variable `BACKEND_URL`) para encolar la re-vectorización de los productos modificados y reportará si esta solicitud fue exitosa o falló.
