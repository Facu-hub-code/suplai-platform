---
name: suplai-implementation-phase-07
description: Fase 7 conversaciones — historial mock en n8n_chat_histories y resumen CSV. Usar tras Fase 6 con scripts deterministas en `scripts/fase-07-conversaciones/`.
---

# Fase 7 — Conversaciones

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Input

- Subset de clientes (50)
- Textos de promos Fase 2
- Pedidos y líneas de la Fase 6 (`phase-06-pedidos.csv` y `phase-06-items-pedido.csv`)

## Output

`phase-07-conversaciones-resumen.csv` — **solo resumen por cliente** (no exportar burbujas completas al CSV).

Columnas: `client_phone,cantidad_mensajes,ultimo_mensaje_at,is_unread,live_feed,is_mock`

Además, el preparador genera un archivo auxiliar de detalle:

- `phase-07-mensajes.csv` — historial plano de mensajes listo para cargar en BD.

## Distribución

| Grupo | Cantidad | live_feed | is_unread | ultimo_mensaje_at |
|-------|----------|-----------|-----------|-------------------|
| Respondieron hoy | 10–15 | true | true | NOW() − 0–12h |
| Resto | 35–40 | false | false | NOW() − 13h a 2 días |

## Mensajes (carga BD, usando scripts)

La fase debe ejecutarse con:

1. `python scripts/fase-07-conversaciones/preparar_conversaciones.py --esquema <schema>`
2. `python scripts/fase-07-conversaciones/cargar_conversaciones.py --esquema <schema>`

Por cliente seleccionado, insertar 4–5 filas en `{schema}.n8n_chat_histories`:

- Saludo agente
- Empuje promo volumen o discusión sobre pedidos de la Fase 6 (simulando que el agente tomó el pedido de ese cliente).
- Respuestas y consultas del cliente.
- **Mensajes de Quejas**: Simular quejas y reclamos para un subgrupo de clientes (por ejemplo, demoras, errores de facturación, o productos faltantes) para dar soporte a la creación de tickets en la Fase 8.
- **Restricción Obligatoria de Cierre**: Toda conversación **DEBE** terminar obligatoriamente con un mensaje de tipo `ai` (`sender_type` = 'ai'). Si el último mensaje natural es del cliente (`human`), se debe inyectar una respuesta de contingencia (ej. saludo formal, confirmación de pedido recibido o cierre de contacto).

**MUST** verificar columnas reales (`session_id`, `message` como `jsonb`, `created_at`, `is_mock`) con introspección de esquema antes de escribir.

## Sandbox

Indicar al implementador: probar agente en backoffice/lab con datos del tenant; RAG acotado al catálogo cargado.

## Verificación

- COUNT filas chat > 0
- 10–15 clientes con `live_feed=true` en CSV resumen
- Ninguna conversación finaliza con `sender_type = 'human'` o `type = 'human'`.

## Cierre

manifest fase `07` → `cargado`
