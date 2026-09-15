# 070 — WhatsApp: estado automático por webhook + exclusión en agenda

**Estado:** En implementación  
**Fecha:** 2026-09-14  
**Tipo:** Cross-repo (agente + backend; backoffice opcional v1.1)  
**Extiende:** [backend 039 — estado WhatsApp del contacto](https://github.com/suplai-sales/backend-supabase/blob/main/docs/specs/039-cliente-whatsapp-estado.md)  
**Relaciona:** agente `006-webhook-v2`, backend `034` agenda sender, platform `026` ciclo estrategias  

**Ramas sugeridas (hub, no worktree):**

| Repo | Rama | PR |
|------|------|-----|
| `agente-conversacional-multi_tenant` | `feat/wa-estado-webhook` | TBD |
| `backend-supabase` | `feat/wa-estado-webhook` | TBD |
| `suplai-platform` | `feat/wa-estado-webhook` | este spec |

---

## Objetivo

Cerrar el loop que 039 dejó a medio implementar: **usar el webhook de delivery de Meta** (`statuses`) para marcar si un teléfono tiene WhatsApp, y **dejar de incluir `no_existente` en agenda y estrategias**, para no ensuciar métricas (`envios_plantillas`, presupuesto, reply rate).

Hoy el webhook **sí llega** al agente. No se persiste el estado ni se filtra la audiencia.

---

## Hallazgo (estado actual)

### Sí escuchamos el webhook

Meta pega `POST /webhook/v2` (y a veces `POST /`) con `object: whatsapp_business_account`. Si el payload trae solo `statuses` (sin `messages`), el agente hace ack `200` y **no** corre el grafo.

Evidencia: `app/api/webhook_v2.py` → `_handle_meta_cloud_payload`; spec agente `006` §4.2.

### Qué capturamos hoy

`app/services/meta_whatsapp_status_webhook.py` parsea `sent` / `delivered` / `failed` + código Graph.

- **`failed`** con códigos conocidos (incl. **131026**, **131051**, 131049, 131042, …) → **solo log WARN** `whatsapp_delivery_status_failed` / `WHATSAPP_DELIVERY_FAILED`.
- **131042** (pago WABA) → ticket interno. Nada de clientes.
- **`delivered` / `read` / `sent`** → se parsean y **se descartan** (`if update.status != "failed": continue`).

No hay `UPDATE` a `{schema}.clients.whatsapp_estado`.

### Qué hace el backend (039, incompleto)

Existe el enum y el servicio:

| Valor | Semántica 039 |
|-------|----------------|
| `no_validado` | default, sin evidencia |
| `existente` | hay cuenta WA (sin confirmar negocio) |
| `no_existente` | evidencia de que **no** hay WA |
| `validado` | WA + confirmación humana |

`WhatsappClienteEstadoService.marcar_por_envio` se llama desde `agenda_sender` y el test-send de plantillas **en el HTTP 200 de Graph**, no en el webhook.

`send_template_message` trata **HTTP 200 = éxito**. Meta acepta el request a números sin WhatsApp y el `131026` llega **después**, asíncrono. Resultado:

1. Números muertos se marcan `existente` (falso positivo).
2. Casi nunca se llega a `no_existente` por 131026.
3. `agenda_sender._get_clientes_del_grupo` / `_get_cliente_individual` filtran `activo_ai`, **no** `whatsapp_estado`.
4. `estrategias_dispatch_service` hace commit de presupuesto + `INSERT envios_plantillas` en el mismo HTTP 200. Las métricas (funnel 48h, “no responden”, costo del ciclo) cuentan envíos que nunca se entregaron.

`estrategias_salida.py` **no** llama `marcar_por_envio`.

---

## Semántica de “no válido”

**No** se excluye `no_validado`. Ese es el default de todo contacto nuevo; si se los salteara, nunca se haría el primer envío que genera evidencia.

Se bloquea solo **`no_existente`** (webhook `failed` 131026 / 131051, o error síncrono inequívoco de recipiente).

`validado` no se degrada automáticamente.

---

## Decisiones de diseño técnico (con el *por qué*)

| Tema | Decisión | Por qué (alternativa descartada) |
|------|----------|----------------------------------|
| Fuente de verdad de existencia | Webhook `statuses`: `delivered`/`read` → `existente`; `failed` 131026 o 131051 → `no_existente` | Cloud API no tiene check-exists. HTTP 200 no prueba entrega. Descartado: seguir usando `marcar_por_envio(envio_exitoso=HTTP 200)`. |
| Quién escribe el estado | **Agente** al procesar el webhook (ya resuelve tenant por `display_phone_number` / `phone_number_id`) | Evita hop HTTP agente→backend por cada status. Descartado: endpoint interno en cada evento (latencia + auth). Las reglas de transición viven duplicadas en un módulo chico del agente **espejo** de `WhatsappClienteEstadoService` (tabla de códigos en este spec). |
| Match contacto | `recipient_id` normalizado a dígitos = `clients.phone_number` normalizado, en el schema del tenant | El webhook no trae `client_id`. Descartado: exigir `wamid` persistido en v1 (útil después; no bloquea). Si hay varios contactos con el mismo teléfono, actualizar **todos**. |
| `sent` | No cambia estado | Solo “aceptado por Meta”. |
| 131049 / 131048 / 131056 / 131047 / 130472 / 131042 | Log (ya existe). **No** `no_existente` | El número puede ser válido (tope marketing, rate limit, ventana 24h, billing). |
| 131050 (opt-out marketing) | v1: no mutar `whatsapp_estado`. Log. | Es preferencia, no “sin WhatsApp”. Enum nuevo / flag marketing queda v1.1. |
| `validado` + 131026 | No degradar. Ticket `ia_tickets` (tag `WHATSAPP_VALIDADO_UNDELIVERABLE`) | Conflicto de datos; lo resuelve un humano. |
| Inbound usuario | Si llega `messages[]` de ese teléfono → `existente` (salvo `validado`) | El contacto escribió: hay WA. Desbloquea agenda al ciclo siguiente. |
| Audiencia agenda | `AND c.whatsapp_estado IS DISTINCT FROM 'no_existente'` en `_get_clientes_del_grupo` y `_get_cliente_individual` | Un filtro, mismo patrón que `activo_ai`. Descartado: borrar del grupo (pierde CRM). |
| Audiencia estrategias | Antes de `send_template_message`, si `no_existente` → `skipped` + release presupuesto (no `sent`/`failed`) | No debe sumar `envios_plantillas` ni `sends_without_reply` ni costo. |
| Métricas `envios_plantillas` | Insertar **solo** cuando el webhook trae `delivered` (o `read`), no en HTTP 200 | El funnel 48h y “no responden” usan esa tabla. Descartado: insertar y borrar (carrera). v1: dejar de insertar en sender; insertar desde el handler de `delivered` (agente o job backend). |
| HTTP 200 `marcar_por_envio(True)` | **Dejar de marcar `existente`** en agenda y test-send | Es el bug. El error síncrono que matchee `is_recipient_not_on_whatsapp` **sí** puede marcar `no_existente` (pocos casos). |
| Lookup silencioso (Whapi, etc.) | Fuera de alcance | Viola ToS Meta. |
| UI backoffice | v1: el campo `whatsapp_estado` ya está en BFF/PATCH. Sin pantalla nueva. | El valor operativo es el filtro de send. Badge / conteo “omitidos sin WA” en el run de agenda = v1.1. |

---

## Alcance explícito

### Incluido (v1)

- Persistir transiciones desde el webhook Meta `statuses` → `{schema}.clients.whatsapp_estado`.
- Inbound (`user_message`) → `existente` si no está `validado`.
- Dejar de tratar HTTP 200 como “tiene WhatsApp”.
- Excluir `no_existente` de agenda (grupo y unipersonal) y de dispatch de estrategias.
- Skips de estrategias: no commit de presupuesto, no `envios_plantillas`, status `skipped` (o `skipped_no_whatsapp` si el enum de dispatch lo permite sin migración; si no, reusar `skipped` + log).
- `envios_plantillas`: alta recién en `delivered`/`read`.
- Logs estructurados ya existentes + `schema_name` / `recipient_id` / `meta_error_code`.
- Tests unitarios de parse + transiciones + filtro SQL de audiencia.

### Fuera de alcance (v1)

- Endpoint Meta de check-exists (no existe en Cloud API).
- Terceros de lookup.
- Nuevo valor de enum (`marketing_opt_out`, etc.).
- Degradar `validado` en automático.
- Excluir `no_validado` (rompería el primer contacto).
- UI nueva de “bloqueados por WhatsApp” / counters en el modal de agenda (v1.1).
- Persistencia de historial de cada `wamid` (tabla de delivery events) — v1.1 si hace falta auditoría.
- Cambiar n8n.
- Backfill masivo histórico (no hay status guardados; solo logs).

---

## Orden de implementación

Merge: **agente (escribe estado + envios en delivered)** y **backend (deja de marcar existente en 200 + filtra audiencia)** pueden ir en paralelo; **backend primero o al mismo tiempo**, porque si el agente empieza a marcar `no_existente` y el sender no filtra, no hay daño (solo no se aprovecha). Si el backend filtra antes de que el agente persista, el filtro no hace nada hasta que haya datos.

1. **Backend** — `marcar_por_envio`: quitar promoción a `existente` por HTTP 200; conservar `no_existente` por error síncrono 131026. Filtro audiencia agenda + skip estrategias. Dejar de `INSERT envios_plantillas` en send OK.
2. **Agente** — en `log_meta_whatsapp_delivery_statuses` (renombrar a `apply_…`): transiciones + insert `envios_plantillas` en delivered (hace falta `template_name`; ver migración / lookup).
3. **Agente** — inbound pipeline: `existente` al primer `user_message` de un teléfono de `clients`.
4. Tests + este spec.

**Problema `envios_plantillas.template_name`:** la tabla guarda `session_id` + `template_name`. El webhook de status **no** trae el nombre de plantilla. Opciones:

| Opción | v1 |
|--------|-----|
| A. Guardar `wamid` + `template_name` al send (columna o tabla puente) y al `delivered` insertar/confirmar | Correcto; pide migración chica |
| B. Insertar en HTTP 200 **y** borrar/ignorar en métricas si llega `failed` 131026 | Más frágil (métricas entre send y webhook) |
| C. Insertar en delivered con `template_name = 'unknown'` | Rompe performance por plantilla |

**v1 elige A:** al send persistir `provider_message_id` (ya lo hace `estrategia_dispatches`; falta en agenda/`envios_plantillas`). Ver migración.

---

## Migración de base de datos

Sí, mínima, en **backend**:

1. `{schema}.envios_plantillas`
   - `provider_message_id text NULL` (wamid)
   - `delivery_status text NOT NULL DEFAULT 'accepted'` — valores: `accepted` \| `delivered` \| `failed`
   - índice único parcial o unique `(provider_message_id)` donde not null (idempotencia del webhook)
2. Al send: `INSERT` con `delivery_status='accepted'` + wamid (si Graph lo devolvió). **Las queries de métricas (`metricas_service`, “no responden”, funnel 48h) filtran `delivery_status = 'delivered'`.** Así un accepted que nunca entrega no suma ruido. Un `failed` webhook actualiza a `failed` y tampoco entra al funnel.
3. Opcional: `whatsapp_ultimo_error_code int` / `whatsapp_ultimo_status_at` en `clients` — **no** en v1; alcanza el enum.

**Backfill:** filas viejas de `envios_plantillas` sin status → tratarlas como `delivered` (comportamiento histórico) **o** como `accepted` (más conservador para métricas futuras). **Decisión: `delivered`** para no reescribir historia de reportes ya vistos.

**Rollback:** dejar de filtrar en SQL de métricas; columna puede quedar. El filtro de audiencia se revierte en código.

Si el unique de wamid es difícil (envíos viejos sin id): unique solo `WHERE provider_message_id IS NOT NULL`.

---

## Requisitos funcionales

- `RF-1`: Payload `statuses` con `delivered` o `read` → contactos del tenant con ese teléfono pasan a `existente` si estaban en `no_validado` o `no_existente`. No toca `validado`.
- `RF-2`: `failed` + código 131026 o 131051 → `no_existente` si no está `validado`.
- `RF-3`: `failed` con otros códigos conocidos → log only.
- `RF-4`: `validado` + 131026 → sin cambio de enum + ticket.
- `RF-5`: Inbound de usuario → `existente` (misma regla que RF-1).
- `RF-6`: Agenda no selecciona `no_existente`. El resto del grupo se envía. La agenda no queda trabada si el grupo queda vacío de enviables (034 RF-5 sigue: avanzar ciclo).
- `RF-7`: Dispatch estrategias: `no_existente` → skipped, release de reserve, sin `sends_without_reply++`.
- `RF-8`: Métricas de plantillas / no-responden / presupuesto comprometido **no** cuentan `accepted` ni `failed`.
- `RF-9`: HTTP 200 ya no pone `existente`.
- `RF-10`: Idempotencia: el mismo `wamid` `delivered` dos veces no duplica `envios_plantillas`.

---

## Criterios de aceptación

### AC-1 — Webhook delivered marca existente

- **Given** cliente `no_validado`, se envió una plantilla, Graph 200.
- **When** llega `statuses[]` `delivered` para ese `recipient_id`.
- **Then** `whatsapp_estado = existente` y `envios_plantillas.delivery_status = delivered`.

### AC-2 — 131026 marca no_existente y no vuelve a salir

- **Given** cliente en el grupo de una agenda recurrente, estado `no_validado` o `existente`.
- **When** webhook `failed` código 131026.
- **Then** `whatsapp_estado = no_existente`. El siguiente ciclo de agenda **no** llama a Graph para ese cliente. No hay fila nueva neta en métricas delivered. Los demás del grupo sí se envían.

### AC-3 — HTTP 200 solo no valida

- **Given** cliente `no_validado`.
- **When** `send_template_message` retorna 200 y **aún no** hay webhook.
- **Then** sigue `no_validado`. Hay `envios_plantillas` `accepted` (invisible a métricas).

### AC-4 — 131049 no invalida

- **When** `failed` 131049 (tope marketing).
- **Then** el estado del contacto no cambia; el próximo ciclo puede reintentar.

### AC-5 — Inbound rehabilita

- **Given** `no_existente`.
- **When** el número escribe al agente.
- **Then** `existente` y vuelve a ser seleccionable en agenda.

### AC-6 — validado protegido

- **Given** `validado`.
- **When** 131026.
- **Then** sigue `validado` y hay ticket.

### AC-7 — Métricas

- **Given** 10 accepted, 6 delivered, 4 failed 131026.
- **When** se consulta performance / no-responden.
- **Then** el denominador de envíos es 6, no 10.

---

## Plan de prueba en CI/CD

### Agente

- Extender `tests/test_webhook_v2.py`: payload solo `statuses` `failed` 131026 → se invoca persistencia (mock DB) con `no_existente`.
- Caso `delivered` → `existente`.
- Caso 131049 → no update de estado.
- Caso `validado` + 131026 → no update + ticket mock.
- Inbound: mensaje usuario dispara `existente`.

### Backend

- `test_whatsapp_cliente_estado_service.py`: `marcar_por_envio(True)` **ya no** pasa a `existente`.
- `test_agenda_sender_envio_plantilla.py`: audiencia excluye `no_existente`; grupo mixto envía solo válidos.
- `test_estrategias_dispatch_service.py`: cliente `no_existente` incrementa `skipped`, no `sent`, release budget.
- `test_metricas_service.py` (o el que cubra funnel): filas `accepted`/`failed` no entran al conteo.
- Checks existentes verdes; smoke de migración  `envios_plantillas` en tenant de test si el pipeline aplica SQL.

Sin e2e Meta real en CI (no hay Graph de prueba). El e2e es el plan humano.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000`, backoffice `3000` (si se mira el contacto), agente local o staging con webhook Meta (ngrok / Railway preview). Tenant `demo` o sandbox.

1. Contacto A: teléfono **sin** WhatsApp (número de prueba conocido). Estado `no_validado`. Meterlo en un grupo de agenda puntual chica.
2. Disparar agenda (o test-send). Graph 200. En BD: sigue `no_validado`; `envios_plantillas.delivery_status=accepted`.
3. Esperar webhook (segundos). Loki/logs: `whatsapp_delivery_status_failed` 131026. BD: `no_existente`. Fila `failed`.
4. Volver a correr la agenda: A no debe ir a Meta. Un contacto B del mismo grupo **con** WhatsApp sí.
5. Contacto B: tras `delivered`, `existente` y métricas del BO (performance plantilla / no responden) **no** incluyen a A.
6. Contacto C `validado`: forzar 131026 si se puede (difícil). Si no, test unitario basta; en humano verificar que PATCH a `validado` no lo pisa un send.
7. Contacto A escribe al WA del agente (o webhook inbound simulado) → `existente` y el ciclo siguiente lo vuelve a incluir.
8. Estrategia con presupuesto: A en audiencia → al dispatch, skipped, `budget_remaining` no baja por A.

OK: cero envíos Graph a A en el segundo ciclo; métricas sin A; B cobrado/contado solo si delivered.

---

## Impacto técnico (archivos)

**Agente**

- `app/services/meta_whatsapp_status_webhook.py` — aplicar transiciones, no solo log.
- `app/api/webhook_v2.py` / `app/services/webhook_inbound.py` — inbound → existente.
- `tests/test_webhook_v2.py`

**Backend**

- `services/whatsapp_cliente_estado_service.py` — RF-9.
- `services/agenda_sender.py` — filtro + no métricas delivered.
- `services/estrategias_dispatch_service.py` — skip.
- `services/plantillas_meta_test_send.py` — alinear.
- `services/metricas_service.py` — filtro `delivery_status`.
- `sql/` nueva migración `envios_plantillas`.
- Tests listados arriba.

**Backoffice:** sin cambio v1 (BFF ya expone `whatsapp_estado`).

---

## Riesgos

- Webhook `delivered` atrasado: ventana en que el contacto sigue `no_validado` y puede recibir otro HSM el mismo día. Aceptable v1 (el segundo también entregará o fallará).
- `recipient_id` vs `phone_number` (AR/MX, 9 extra): reutilizar `normalize_phone` del backend / `_normalize_wa_phone` del agente; documentar mismatch como CB.
- Duplicar reglas agente vs backend: copiar la tabla de códigos de este spec; test de ambos lados con los mismos fixtures de códigos.
- Calidad de plantilla Meta: excluir 131026 **mejora** quality rating (menos failed). No hay riesgo de “dejar de hablarle a alguien que sí tiene WA” salvo 131026 bucket (ToS / app vieja). Mitigación: inbound rehabilita (AC-5).
