---
name: suplai-implementation-phase-09
description: Fase 9 purga mock — borrar datos de simulación. Solo con is_mock en BD y confirmación PURGE MOCK.
---

# Fase 9 — Purga mock (destructiva)

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Gate estricto

**NO ejecutar** si:

- `manifest.blocked.is_mock_migration` = true
- El implementador no escribió exactamente: `PURGE MOCK {schema_name}`

Si gate falla → explicar que ingeniería debe agregar columna `is_mock` y endpoint de purga.

## Input

- Frase confirmación: `PURGE MOCK colormix` (schema exacto)
- Segunda confirmación: "sí, borrar todos los datos de prueba"

## Output

`phase-09-purga-log.csv` — `tabla,filas_borradas,ok,notas`

## Orden de borrado (cuando exista is_mock)

Hijos primero (evitar FK):

1. items_pedido / messages / n8n_chat_histories
2. pedidos, ia_tickets
3. clients, vendedor_geo_zones, geo_zones, vendedores
4. promociones, precios_productos, productos_aliases, productos
5. public.tenant_*_mappings WHERE tenant_id = manifest.tenant_id

Solo `DELETE ... WHERE is_mock = true` por tabla.

Si **no** hay `is_mock`: **STOP** — no usar DELETE masivo sin discriminador.

## Alternativa sin migración

Registrar en purga-log: `ok=false`, `notas=requiere migración is_mock` y escalar a ingeniería.

## Cierre

- manifest fase `09` → `cargado` o `bloqueado`
- Verificar COUNT productos = 0 y clients = 0
- Recordar restaurar `read_only=true` en mcp.json
