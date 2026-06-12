---
name: suplai-implementation-phase-07
description: Fase 7 conversaciones — historial mock en n8n_chat_histories y resumen CSV. Usar tras Fase 6.
---

# Fase 7 — Conversaciones

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Input

- Subset de clientes (50)
- Textos de promos Fase 2

## Output

`phase-07-conversaciones-resumen.csv` — **solo resumen por cliente** (no exportar burbujas completas al CSV).

Columnas: `client_phone,cantidad_mensajes,ultimo_mensaje_at,is_unread,live_feed,is_mock`

## Distribución

| Grupo | Cantidad | live_feed | is_unread | ultimo_mensaje_at |
|-------|----------|-----------|-----------|-------------------|
| Respondieron hoy | 10–15 | true | true | NOW() − 0–12h |
| Resto | 35–40 | false | false | NOW() − 13h a 2 días |

## Mensajes (carga BD, no CSV detallado)

Por cliente seleccionado, insertar 3–5 filas en `{schema}.n8n_chat_histories`:

- Saludo agente
- Empuje promo volumen (texto de promo Fase 2)
- Respuesta comercio corta ("Buen día", "Anítame una caja")

**MUST** verificar columnas reales (`session_id`, `message`, `type`, etc.) con `list_tables` verbose.

## Sandbox

Indicar al implementador: probar agente en backoffice/lab con datos del tenant; RAG acotado al catálogo cargado.

## Verificación

- COUNT filas chat > 0
- 10–15 clientes con `live_feed=true` en CSV resumen

## Cierre

manifest fase `07` → `cargado`
