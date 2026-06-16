---
name: suplai-implementation-phase-05
description: Fase 5 flags clientes — ERP, prospectos y estado WhatsApp. Usar tras Fase 4 con los scripts de `scripts/fase-05-clientes-flags/`.
---

# Fase 5 — Flags de clientes

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Input

- `phase-04-clientes.csv` (códigos cliente)
- Distribución fija del flujo

## Output

`implementacion/{schema}/outputs/phase-05-clientes-flags.csv`

| phone_number | razon_social | codigo_erp | whatsapp_estado | whatsapp_validado_at | etiqueta | is_prospect |
|--------------|--------------|------------|------------------|----------------------|----------|-------------|
| 40 filas ERP | texto | numérico autoincremental desde 25001 | validado / existente | timestamp solo para validado | vacío | false |
| 10 filas prospecto | texto | 0 | mezcla | timestamp solo si validado | `PROSPECTO` | true |

## Mapeo WhatsApp (schema real)

Usar columnas del tenant:

- Validado → `whatsapp_validado_at` NOT NULL y/o `whatsapp_estado` según convención del backoffice
- Sin validar → `whatsapp_estado` = `sin_validar` o equivalente

**MUST** verificar valores enum válidos con `SELECT DISTINCT whatsapp_estado` o documentación MCP antes de UPDATE.

## Carga MCP

La fase se ejecuta en dos pasos obligatorios:

1. Generar el CSV local con:
   `python scripts/fase-05-clientes-flags/preparar_clientes_flags.py --esquema <schema>`
2. Cargarlo al tenant con:
   `python scripts/fase-05-clientes-flags/cargar_clientes_flags.py --esquema <schema>`

El script de carga hace el `UPDATE {schema}.clients` por `phone_number` y deja trazabilidad en consola.

- Prospectos: `codigo = 0` y etiqueta PROSPECTO si existe campo `etiqueta`
- ERP: `codigo` numérico único

No INSERT nuevos clientes en esta fase.

## Verificación

- COUNT prospectos ≈ 10
- COUNT codigo > 0 ≈ 40

## Cierre

manifest fase `05` → `cargado`
