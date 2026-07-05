---
name: suplai-implementation-phase-08
description: Fase 8 insights — 15-20 tickets ia_tickets con efecto cruzado en chat e inserción limpia vía script. Usar tras Fase 7.
---

# Fase 8 — Insights y notificaciones

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Input

- Catálogo real e información de la marca líder del tenant (mapeado dinámicamente)
- Archivo CSV de la Fase 7 (`phase-07-conversaciones-resumen.csv` y `phase-07-mensajes.csv`) para priorizar clientes con quejas registradas.

## Output

`phase-08-notificaciones.csv` — Resumen determinista de tickets con su respectivo mensaje cruzado para el chat.

Columnas: `ticket_ref,categoria,status,description,client_phone,mensaje_cruzado_incoming,created_at,closed_at,is_mock`

## Volumen y estados

- 15–20 tickets en total (configurables vía `config.json` del tenant).
- **Efecto Cruzado Obligatorio**: ~60% `status` abierto (`open`). Para los tickets abiertos de las categorías **Calidad** o **Logística**, se debe inyectar el mensaje entrante correspondiente en el historial de chat del cliente.
- Fechas consistentes basadas en la configuración de ejecución (`fecha_base`).

## Carga en Base de Datos (usando scripts)

La fase debe ejecutarse secuencialmente mediante los siguientes comandos en la terminal:

1. `python scripts/fase-08-insights/preparar_insights.py --esquema <schema>`
2. `python scripts/fase-08-insights/cargar_insights.py --esquema <schema>`

### Reglas de Impacto en BD:

- **Tickets (`{schema}.ia_tickets`)**: Insertar las filas mapeando las columnas reales del sistema:
  - `description` <- Detalle del incidente.
  - `client_id` <- Resuelto a partir del `client_phone` del CSV.
  - `status` <- 'open' o 'closed'.
  - `created_at` y `closed_at` <- Fechas e ISO timestamps generados.
  - `is_mock` <- true.
- **Chat (`core.conversation_events` — spec 013)**: Si el ticket es abierto y pertenece a Calidad o Logística, el script de carga **DEBE** insertar en `core.conversation_events` (enlazado a `core.conversations` por `session_id`) el `mensaje_cruzado_incoming` como `user_message` y la respuesta del agente como `assistant_message`, ambos con `event_payload.origin = 'fase-08-insights'` e `is_mock = true`.

> [!NOTE]
> `{schema}.n8n_chat_histories` queda deprecada para carga (spec 013). El backoffice lee core.

## Verificación

- El conteo total de filas en `{schema}.ia_tickets` que posean `is_mock = true` debe estar estrictamente entre 15 y 20.
- Verificar que para cada ticket abierto de Calidad o Logística exista el correspondiente `user_message` con `event_payload->>'origin' = 'fase-08-insights'` en `core.conversation_events`.

## Cierre

manifest fase `08` → `cargado`
Onboarding mock completo. Ofrecer prueba de agente en el backoffice/lab usando los datos consolidados del tenant. Fase 9 solo si `is_mock` está validado en la BD.