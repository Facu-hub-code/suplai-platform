---
name: suplai-implementation-phase-01-1
description: Fase 1.1 Tags jerárquicos — Consumir propose-taxonomy y aplicar tags propuestos. Usar tras carga exitosa de Fase 1.
---

# Fase 1.1 — Tags Jerárquicos

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Input

- [ ] Catálogo de productos insertado en Supabase (Fase 1 completada).
- [ ] Acceso HTTP activo al backend de Suplai.

## Output

1. **`phase-01-1-propuesta-tags.json`** (obligatorio) — JSON guardado en `implementacion/{schema}/outputs/` que contiene la taxonomía estructurada en 4 niveles propuesta por la IA.

## Proceso de Ejecución

### Ejecutar el Script de Taxonomía
Para realizar esta fase de forma automatizada y consistente, se puede ejecutar el script genérico `scripts/fase-01-catalogo/aplicar_taxonomia.py`:
```bash
python scripts/fase-01-catalogo/aplicar_taxonomia.py --esquema {schema} --limite 300
```

Este script se encargará de:
1. Realizar la petición HTTP POST al endpoint `propose-taxonomy`.
2. Guardar la propuesta devuelta por la IA en `implementacion/{schema}/outputs/phase-01-1-propuesta-tags.json`.
3. Solicitar confirmación interactiva en la consola antes de aplicar los tags a Supabase.

### Aplicar una Propuesta Modificada
Si el implementador decide editar el JSON propuesto (por ejemplo, para eliminar niveles redundantes), se debe usar el script `scripts/fase-01-catalogo/aplicar_propuesta_guardada.py` para impactar los cambios editados en Supabase:
```bash
python scripts/fase-01-catalogo/aplicar_propuesta_guardada.py --esquema {schema}
```

## Cierre de la Fase

- Registrar en `manifest.yaml`:
  - `fases["01.1"].estado = cargado`
  - `fases["01.1"].cargado_at = {timestamp_actual}`
- Invitar a la Fase 2 (Promociones).
