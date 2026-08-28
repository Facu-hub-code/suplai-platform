---
name: check-hsm-sends
description: >-
  Use when the user asks if WhatsApp template / HSM / Meta carousel sends
  went out, failed, or got replies for a tenant (agendas, plantillas,
  carrusel, envíos de ayer/hoy, Gonzalez, gonzales). Do not use for Kommo
  sniffer or Field tasks.
when-to-use: HSM, plantilla Meta, carrusel, envíos, agenda, WhatsApp template, gg_carousel
---

# Chequear envíos de plantillas Meta (HSM)

## Qué significa "salieron bien"

`{schema}.envios_plantillas` **solo se inserta si Meta aceptó el send** (`ok=True` en `agenda_sender`). No guarda fallos.

| Señal | Significado |
|-------|-------------|
| Fila en `envios_plantillas` | Meta devolvió 200 / mensaje aceptado |
| `agenda.enviado_at` seteado | Hubo ≥1 OK en ese ítem (o no había destinatarios) |
| `enviado_at` NULL en puntual que debía salir | Todos los intentos fallaron, o el job no corrió |
| Hueco esperado vs enviados | Fallos Meta, sin teléfono, o `activo_ai=false` |
| `meta_template_stats_daily` | Delivered/read/replied de Meta (puede estar vacío o atrasado) |
| Reply en 48h | Engagement, no entrega |

Un martes con error Meta `#132018` (params/carrusel) puede tener **0 filas** y `enviado_at` NULL aunque el cron sí corrió.

## Flujo

Leer `reference.md` de esta skill para el SQL. Orden:

1. Resolver `schema` + `tenant_id`.
2. Ventana ART ("ayer" / "hoy" / rango).
3. Plantillas: `public.meta_plantillas` del tenant. Carrusel = nombre `*carousel*`/`*carrusel*` **o** `agenda.carousel_config` array no vacío.
4. Agendas que tocaban ese día: puntual `fecha_programada = dia`, recurrente con ese weekday en `dia_semana`.
5. Conteos de `envios_plantillas` en la ventana, por `template_name` y por slot (`hora_envio`).
6. Destinatarios esperados del grupo vs `session_id` enviados (ver SQL de grupo).
7. Replies 48h en `core.conversation_events` (`user_message`); fallback `{schema}.n8n_chat_histories`.
8. Si esperado >> enviado: decirlo. Los fallos no están en SQL; pedir Loki (`WHATSAPP_TEMPLATE_SEND_FAILED`, `tenant_name={schema}`) o revisar Grafana. No inventar el error code.

## Carrusel (Gonzales)

Plantillas típicas: `gg_carousel_promos_arcor_v1`, `gg_carousel_promos_arcor_v2`. El job usa `carousel_config` de la **agenda** (cards con `header_image_url`). Si el array está vacío, Meta puede rechazar (`#132018`).

Puede haber **dos olas el mismo día** (recurrente mañana + puntual tarde) al mismo grupo: contar destinos distintos, no solo filas.

## Veredicto

- **OK:** enviados ≈ esperados con teléfono, `enviado_at` seteado, plantilla la pedida.
- **Parcial:** algunos destinos sin fila.
- **Falló:** 0 envíos de esa plantilla y/o puntual sin `enviado_at`.
- **Entrega vs aceptación:** sin `sent/delivered` en stats, no afirmar "llegó al teléfono"; afirmar "Meta aceptó N envíos".

## Output

```
Veredicto: OK | parcial | falló
Tenant / plantilla / ventana ART
Agendas (id, tipo, hora, enviado_at, grupo)
Enviados: N filas / M destinos vs esperados
Respuestas 48h: K destinos
Huecos / riesgos (doble ola, stats vacíos, fallos no logueados en SQL)
```

No listar todos los teléfonos salvo que lo pidan. Nombres de PDV sí.
