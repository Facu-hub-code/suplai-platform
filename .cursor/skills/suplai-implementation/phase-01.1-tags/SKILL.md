---
name: suplai-implementation-phase-01-1
description: Fase 1.1 Tags jerárquicos — Consumir propose-taxonomy y aplicar tags propuestos. Usar tras carga exitosa de Fase 1.
---

# Fase 1.1 — Tags Jerárquicos

Prerequisito: Fase 1 catálogo `cargado` en el manifest.

## Input

- [ ] Catálogo de productos insertado en Supabase (Fase 1 completada).
- [ ] Acceso HTTP activo al backend de Suplai.

## Output

1. **`phase-01-1-propuesta-tags.json`** (obligatorio) — JSON guardado en `implementacion/{schema}/outputs/` que contiene la taxonomía estructurada en 4 niveles propuesta por la IA.

## Proceso de Ejecución

### 1. Solicitar Propuesta de Tags
Hacer una petición HTTP POST al endpoint del backend para obtener la propuesta de tags para los productos cargados:
- **URL**: `https://web-production-f544f.up.railway.app/{schema}/tags/propose-taxonomy`
- **Método**: `POST`
- **Body**:
  ```json
  {
    "limit": 500
  }
  ```
- **Respuesta**: Guardar la respuesta JSON (de estructura `{"schema": "{schema}", "products": [...]}`) en el archivo de salida `implementacion/{schema}/outputs/phase-01-1-propuesta-tags.json`.

### 2. Aplicar Propuesta
Enviar la propuesta guardada para que el backend cree y asocie los tags jerárquicos en la base de datos:
- **URL**: `https://web-production-f544f.up.railway.app/{schema}/tags/apply-proposed-taxonomy`
- **Método**: `POST`
- **Body**: El contenido del archivo JSON obtenido en el paso 1 (con la lista de productos y sus tags).
- **Validación**: Validar que la respuesta retorne exitosa (`200 OK`) con el resumen de inserciones.

## Cierre de la Fase

- Registrar en `manifest.yaml`:
  - `fases["01.1"].estado = cargado`
  - `fases["01.1"].cargado_at = {timestamp_actual}`
- Invitar a la Fase 2 (Promociones).
