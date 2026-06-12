---
name: suplai-implementation-phase-08
description: Fase 8 insights — 15-20 tickets ia_tickets con efecto cruzado en chat. Usar tras Fase 7.
---

# Fase 8 — Insights y notificaciones

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Input

- Producto/marca líder (reclamo coherente)
- Clientes con `live_feed=true` del CSV Fase 7

## Output

`phase-08-notificaciones.csv`

`ticket_ref,categoria,status,description,client_phone,mensaje_cruzado_incoming,is_mock`

## Volumen y estados

- 15–20 tickets total
- 60% `status` abierto (ej. `Abierto`)
- 40% cerrado
- Fechas abiertas: hoy − 0–3 días; cerradas: hoy − 5–20 días

## Categorías (4)

| categoria | ejemplo description |
|-----------|---------------------|
| Calidad | Reclamo caja incompleta de {producto marca líder} |
| Logística | No recibió mercadería el viernes |
| Comercial | Pide hablar con encargado |
| Administración | Corregir apellido en sistema |

## Efecto cruzado (obligatorio)

Para tickets **abiertos** de Calidad o Logística:

1. Crear ticket en `{schema}.ia_tickets` con `description` del CSV
2. **INSERT** mensaje entrante en chat del mismo `client_phone` con texto de `mensaje_cruzado_incoming` (debe narrar el mismo incidente)

Ejemplo: ticket "prepizza partida" ↔ mensaje "me llegó la prepizza partida...".

Usar producto real del catálogo Colormix si aplica (ej. esmalte, látex).

## Carga MCP

Verificar `ia_tickets`: `client_id`, `description`, `status`, `created_at`.

## Verificación

- COUNT tickets 15–20
- Para 3 tickets abiertos Calidad: existe mensaje incoming vinculado

## Cierre

manifest fase `08` → `cargado`  
Onboarding mock completo. Ofrecer prueba agente; Fase 9 solo si `is_mock` en BD.
