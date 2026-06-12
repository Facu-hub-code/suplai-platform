---
name: suplai-implementation-phase-01.1
description: Fase 1.1 tags jerárquicos — Envía el catálogo a propose-taxonomy y guarda la propuesta en outputs/phase-01-1-propuesta-tags.json.
---

# Fase 1.1 — Tags Jerárquicos (Taxonomía)

Prerequisito: Fase 1 `cargado` o `csv_listo`.

## Pasos de Ejecución

1. **Obtener Propuesta de Taxonomía**:
   - Llamar al endpoint del backend `POST /{schema}/tags/propose-taxonomy` enviando como base el listado de productos de la Fase 1.
   - Guardar el JSON resultante de la propuesta en:
     `implementacion/{schema}/outputs/phase-01-1-propuesta-tags.json`
2. **Revisión Manual**:
   - El implementador/desarrollador debe abrir y revisar el archivo `phase-01-1-propuesta-tags.json` para validar las etiquetas asignadas.
3. **Aplicar Taxonomía**:
   - Una vez revisado, enviar el archivo JSON al endpoint del backend `POST /{schema}/tags/apply-proposed-taxonomy` para impactar la base de datos de tags jerárquicos.

## Cierre

- `manifest.fases["01.1"].estado = cargado`
- `manifest.fases["01.1"].cargado_at = ISO Timestamp`
