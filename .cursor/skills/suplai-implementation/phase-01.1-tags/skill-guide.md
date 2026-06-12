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

Una vez guardado y validado el archivo JSON con la propuesta, se debe enviar de vuelta al backend para crear los tags (si no existen) y asociar la taxonomía a cada producto.

- **Endpoint**: `POST {BACKEND_URL}/{schema}/tags/apply-proposed-taxonomy`
- **Headers**: `Content-Type: application/json`
- **Body**: El contenido completo de `phase-01-1-propuesta-tags.json` (`{"products": [...]}`).

#### Ejemplo de llamada usando un script rápido de Python:
```python
import json
import requests

schema = "colormix"
backend_url = "https://web-production-f544f.up.railway.app"

# 1. Cargar JSON propuesto
with open(f"implementacion/{schema}/outputs/phase-01-1-propuesta-tags.json", "r", encoding="utf-8") as f:
    proposal_data = json.load(f)

# 2. Hacer POST al endpoint de aplicación
apply_url = f"{backend_url}/{schema}/tags/apply-proposed-taxonomy"
response = requests.post(apply_url, json={"products": proposal_data["products"]})
response.raise_for_status()

print("Resultado de la aplicación:", response.json())
```

- **Validación del Agente**: 
  - Asegurar un código de respuesta HTTP `200 OK`.
  - El backend devolverá un resumen (`summary`) con la cantidad de asignaciones y tags creados. Informar este resultado al implementador.

---

## 🏁 Cierre de la Fase

1. Modificar el archivo `implementacion/{schema}/manifest.yaml`:
   - Cambiar `fases["01.1"].estado` a `cargado`.
   - Establecer `fases["01.1"].cargado_at` al ISO timestamp actual.
2. Indicar al implementador que las etiquetas jerárquicas han sido configuradas correctamente y que está listo para proceder a la **Fase 2 (Promociones)**.
