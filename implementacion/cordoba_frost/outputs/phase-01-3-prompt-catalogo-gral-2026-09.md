# Córdoba Frost — prompt catálogo GRAL (propuesta Fase 1.3)

Schema: `cordoba_frost`  
Teléfono del agente (no tocar): `5493518633611`  
Qué corre en producción: `system_prompt` (v2) + `agent_base_prompt_client`

## Qué cambia

Antes el WhatsApp vendía **solo 6 combos**. Ahora el catálogo tiene **285 SKUs** en tienda (`ENVIO-DOM` oculto). El agente pasa a vender el catálogo completo y deja los combos como opción, no como único producto.

Se conservan: Martín, tono cordobés, sucursal Solares 1163, horario, solo provincia de Córdoba, retiro vs envío con tools, pago sin CBU, handoff a vendedores.

No se pisan: `reglas_negocio` (fulfillment + notificación) ni el teléfono.

## system_prompt propuesto

Ver `phase-01-3-prompt-config.json` → `system_prompt`.
