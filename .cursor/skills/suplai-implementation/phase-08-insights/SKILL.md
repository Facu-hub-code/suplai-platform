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
- **Chat (`{schema}.n8n_chat_histories`)**: Si el ticket es abierto y pertenece a Calidad o Logística, el script de carga **DEBE** realizar un `INSERT` adicional en la tabla de chats inyectando el `mensaje_cruzado_incoming` como un mensaje de tipo `human` para garantizar la trazabilidad cruzada.

> [!NOTE]
> El script debe usar introspección previa para validar los tipos de datos exactos (ej: asegurar que el payload del mensaje se guarde correctamente si la columna exige un formato `jsonb`).

## Verificación

- El conteo total de filas en `{schema}.ia_tickets` que posean `is_mock = true` debe estar estrictamente entre 15 y 20.
- Verificar que para cada ticket abierto de Calidad o Logística exista el correspondiente mensaje con `sender_type = 'human'` o `type = 'human'` en `n8n_chat_histories`.

## Cierre

manifest fase `08` → `cargado`
Onboarding mock completo. Ofrecer prueba de agente en el backoffice/lab usando los datos consolidados del tenant. Fase 9 solo si `is_mock` está validado en la BD.