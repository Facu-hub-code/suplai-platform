# Guía de Uso — Fase 1.1: Mapeo de Tags de Productos (suplai-implementation-phase-01-1)

Esta guía detalla el proceso para estructurar y asociar la taxonomía jerárquica de 4 niveles en el catálogo de productos de un tenant recién cargado.

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Si eres un agente de IA leyendo esta guía, recuerda que **puedes y debes realizar este flujo de forma autónoma** consumiendo los endpoints correspondientes mediante scripts locales de Python o herramientas de consulta HTTP.
>
> **MANDATORIO**: Antes de aplicar las etiquetas, **debes informar al usuario** del total de productos para los cuales la IA propuso etiquetas y pedir confirmación para aplicar.

---

## 📋 Requisitos Previos

1. **Fase 1 completada**: El catálogo de productos debe estar insertado en la base de datos (con estado `cargado` en `manifest.yaml`).
2. **Backend de Suplai**: El backend debe estar operativo. La URL base por defecto es `https://web-production-f544f.up.railway.app` (se puede parametrizar usando la variable `BACKEND_URL` en el archivo `.env`).

---

## 🚀 Paso a Paso de la Ejecución

El proceso se compone de dos llamadas clave al backend de Suplai Sales:

### Paso 1: Obtención de la Taxonomía Propuesta (Propose Taxonomy)

Consiste en invocar el endpoint generativo que analiza los nombres de los productos recién cargados para estructurarlos en 4 niveles (Departamento, Categoría, Subcategoría, Tipo de Producto).

- **Endpoint**: `POST {BACKEND_URL}/{schema}/tags/propose-taxonomy`
- **Headers**: `Content-Type: application/json`
- **Body**:
  ```json
  {
    "limit": 500
  }
  ```
  *(Ajustar `limit` de acuerdo al total de productos en el CSV de la Fase 1).*

- **Acción del Agente**:
  Realizar la petición y guardar la respuesta completa en el archivo local:
  `implementacion/{schema}/outputs/phase-01-1-propuesta-tags.json`

#### Estructura esperada del JSON generado:
```json
{
  "schema": "nombre_esquema",
  "products": [
    {
      "product_code": "SKU-100",
      "nombre": "Producto Ejemplo",
      "tags": {
        "1": "Construcción",
        "2": "Ferretería",
        "3": "Adhesivos",
        "4": "Sellador Silicona"
      }
    }
  ]
}
```

---

### Paso 2: Aplicación e Impacto en la Base de Datos (Apply Proposed Taxonomy)

Una vez guardada y validada la propuesta de taxonomía en el archivo JSON, se debe enviar de vuelta al backend para crear los tags (si no existen) y asociar la taxonomía a cada producto.

#### Uso de los scripts genéricos:

1. **Flujo Interactivo / Automático**:
   Se puede utilizar el script genérico provisto en `scripts/fase-01-catalogo/aplicar_taxonomia.py`:
   ```bash
   python scripts/fase-01-catalogo/aplicar_taxonomia.py --esquema {schema} --limite 300
   ```
   Este script automatiza tanto la llamada a `propose-taxonomy` (Paso 1) como la llamada a `apply-proposed-taxonomy` (Paso 2) tras solicitar confirmación interactiva en la consola.

2. **Flujo con Modificación Manual**:
   Si el implementador edita el archivo JSON generado en el Paso 1 (por ejemplo, para eliminar categorías redundantes o corregir jerarquías), debe utilizar el script `scripts/fase-01-catalogo/aplicar_propuesta_guardada.py` para subir los datos corregidos al backend y de allí a Supabase:
   ```bash
   python scripts/fase-01-catalogo/aplicar_propuesta_guardada.py --esquema {schema}
   ```

- **Validación**:
  - Ambos scripts informarán sobre el resultado de la aplicación.
  - Asegurar que la ejecución termine correctamente con un status code exitoso.

---

## 🏁 Cierre de la Fase

1. Modificar el archivo `implementacion/{schema}/manifest.yaml`:
   - Cambiar `fases["01.1"].estado` a `cargado`.
   - Establecer `fases["01.1"].cargado_at` al ISO timestamp actual.
2. Indicar al implementador que las etiquetas jerárquicas han sido configuradas correctamente y que está listo para proceder a la **Fase 2 (Promociones)**.
