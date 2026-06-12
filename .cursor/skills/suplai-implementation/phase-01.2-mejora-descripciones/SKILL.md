---
name: suplai-implementation-phase-01.2
description: Fase 1.2 mejora de descripciones — Corre la skill enhance-descriptions para optimizar descripciones y alias locales en Supabase.
---

# Fase 1.2 — Mejora de descripciones

Prerequisito: Fase 1.1 `cargado` o `csv_listo`.

Esta fase actúa como un puente hacia la skill principal de reescritura y optimización de descripciones comerciales ([enhance-descriptions](../../enhance-descriptions/SKILL.md)).

## Pasos de Ejecución

1. **Auto-detección y Selección de Candidatos**:
   - Preguntar activamente al implementador cuántos productos desea mejorar.
   - Brindar la estimación de tiempo correspondiente en base a **~3 segundos por producto** (ej. 100 productos toman aproximadamente **5 minutos**).
   - Ofrecer la creación de un archivo de configuración en `implementacion/{schema}/config.json` para definir reglas de rubro personalizadas (y proponer una configuración sugerida de forma automática si se tiene contexto del rubro de la distribuidora).
   - Correr la recopilación de candidatos con el límite elegido (por defecto 100):
     ```bash
     python scripts/buscar_candidatos.py --esquema {schema} --limite {limite}
     ```
2. **Ejecutar Enriquecimiento (Dry Run)**:
   - Ejecutar el script `scripts/enriquecer_catalogo.py` para generar descripciones y alias de calidad:
     ```bash
     python scripts/enriquecer_catalogo.py --esquema {schema} --csv-entrada implementacion/{schema}/inputs/candidatos_a_enriquecer.csv --csv-salida implementacion/{schema}/outputs/vista_previa_enriquecimiento.csv
     ```
3. **Revisión Manual por el Implementador**:
   - Abrir el archivo `implementacion/{schema}/outputs/vista_previa_enriquecimiento.csv` para ajustar o filtrar descripciones/alias.
4. **Persistir Cambios y Re-vectorizar**:
   - Aplicar los cambios a la base de datos de Supabase y encolar la re-vectorización en el backend:
     ```bash
     python scripts/enriquecer_catalogo.py --esquema {schema} --aplicar --csv-entrada implementacion/{schema}/outputs/vista_previa_enriquecimiento.csv
     ```

## Cierre

- `manifest.fases["01.2"].estado = cargado`
- `manifest.fases["01.2"].cargado_at = ISO Timestamp`
