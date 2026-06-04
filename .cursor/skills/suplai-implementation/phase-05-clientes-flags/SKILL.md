---
name: suplai-implementation-phase-05
description: Fase 5 flags clientes — ERP, prospectos y estado WhatsApp. Usar tras Fase 4.
---

# Fase 5 — Flags de clientes

Prerequisito: Fase 4 `cargado`, 50 clientes en BD.

## Input

- `phase-04-clientes.csv` (códigos cliente)
- Distribución fija del flujo

## Output

`implementacion/{schema}/outputs/phase-05-clientes-flags.csv`

| cliente_codigo | codigo_erp | is_prospect | whatsapp_status |
|----------------|------------|-------------|-----------------|
| 40 filas | numérico autoincremental desde 25001 | false | validado (30) / existe o sin_validar (20) |
| 10 filas | 0 | true | mezcla |

## Mapeo WhatsApp (schema real)

Usar columnas del tenant:

- Validado → `whatsapp_validado_at` NOT NULL y/o `whatsapp_estado` según convención del backoffice
- Sin validar → `whatsapp_estado` = `sin_validar` o equivalente

**MUST** verificar valores enum válidos con `SELECT DISTINCT whatsapp_estado` o documentación MCP antes de UPDATE.

## Carga MCP

`UPDATE {schema}.clients` por `cliente_codigo` o id interno (join por phone desde CSV Fase 4).

- Prospectos: `codigo = 0` y etiqueta PROSPECTO si existe campo `etiqueta`
- ERP: `codigo` numérico único

No INSERT nuevos clientes en esta fase.

## Verificación

- COUNT prospectos ≈ 10
- COUNT codigo > 0 ≈ 40

## Cierre

manifest fase `05` → `cargado`
