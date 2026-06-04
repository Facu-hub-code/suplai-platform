---
name: suplai-implementation-phase-00
description: Fase 0 preflight — verificar tenant vacío y listo para implementación Suplai. Usar antes de cargar catálogo.
---

# Fase 0 — Preflight

## Input (pedir al implementador)

- [ ] `schema_name` (ej. `colormix`)
- [ ] Ruta del Excel en `implementacion/{schema}/inputs/` (o confirmar que lo copiará)
- [ ] Confirmación verbal: "es un tenant nuevo / vacío"

## Output (único artefacto)

Guardar en `implementacion/{schema}/outputs/phase-00-preflight.csv`:

```csv
check_id,descripcion,resultado,evidencia
```

### Checks obligatorios

| check_id | descripcion | resultado esperado |
|----------|-------------|-------------------|
| distribuidora_existe | Registro en public.distribuidoras | ok |
| schema_existe | Tablas en {schema} | ok |
| productos_vacio | COUNT productos = 0 | ok (o escalAR) |
| clients_vacio | COUNT clients = 0 | ok (o escalAR) |
| mcp_conectado | MCP supabase responde | ok |
| carpeta_implementacion | manifest.yaml presente | ok |
| is_mock_column | Columna is_mock en productos | ok / pendiente |
| excel_presente | Archivo en inputs/ | ok / pendiente |

## Procedimiento MCP

1. `SELECT id, schema_name, nombre FROM public.distribuidoras WHERE schema_name = '{schema}'`
2. Guardar `tenant_id` en `manifest.yaml`
3. `SELECT COUNT(*) FROM {schema}.productos` y `{schema}.clients`
4. `list_tables` schemas: `{schema}`

## Gate

- Si `productos` o `clients` > 0 sin acuerdo explícito → **STOP**, `resultado=fallo`, no avanzar a Fase 1.

## Cierre

- Actualizar `manifest.yaml` fase `00` → `csv_listo` o `cargado` (preflight no inserta datos).
- Decir al implementador: "Preflight OK. Siguiente: **Fase 1 — Catálogo**."
