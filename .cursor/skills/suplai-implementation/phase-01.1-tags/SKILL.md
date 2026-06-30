---
name: suplai-implementation-phase-01-1
description: Fase 1.1 Categorías jerárquicas — Consumir categorias/propose-taxonomy y aplicar categorías propuestas directamente en la tabla categorias. Usar tras carga exitosa de Fase 1.
---

# Fase 1.1 — Categorías Jerárquicas (SPEC-060)

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

> **Nota:** A partir de SPEC-060, los nuevos tenants usan `categorias` + `product_categories` directamente.
> La tabla `tags` es de uso **interno exclusivo** (backoffice, field objetivos, promociones) y NO se crea en esta fase.

## Input

- [ ] Catálogo de productos insertado en Supabase (Fase 1 completada).
- [ ] Acceso HTTP activo al backend de Suplai.

## Output

1. **`phase-01-1-propuesta-categorias.json`** (obligatorio) — JSON guardado en `implementacion/{schema}/outputs/` que contiene la taxonomía estructurada en 4 niveles propuesta por la IA.

## Proceso de Ejecución

### Ejecutar el Script de Taxonomía
Para realizar esta fase de forma automatizada y consistente, se puede ejecutar el script genérico `scripts/fase-01-catalogo/aplicar_taxonomia.py`:
```bash
python scripts/fase-01-catalogo/aplicar_taxonomia.py --esquema {schema} --limite 300
```

Este script se encargará de:
1. Llamar `POST /{schema}/categorias/propose-taxonomy` para obtener la propuesta de IA.
2. Guardar la propuesta en `implementacion/{schema}/outputs/phase-01-1-propuesta-categorias.json`.
3. Solicitar confirmación interactiva antes de aplicar.
4. Llamar `POST /{schema}/categorias/apply-proposed-taxonomy` para crear `categorias` + `product_categories` en Supabase y disparar el rebuild del RAG en background.

### Aplicar una Propuesta Modificada
Si el implementador edita el JSON propuesto (por ejemplo, para eliminar niveles redundantes), se debe usar el script `scripts/fase-01-catalogo/aplicar_propuesta_guardada.py`:
```bash
python scripts/fase-01-catalogo/aplicar_propuesta_guardada.py --esquema {schema}
```

## Cierre de la Fase

- Registrar en `manifest.yaml`:
  - `fases["01.1"].estado = cargado`
  - `fases["01.1"].cargado_at = {timestamp_actual}`
- Invitar a la Fase 2 (Promociones).
