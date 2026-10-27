# 137 — Equipo de agentes: eventos, webhooks y scheduler

**Estado:** Borrador.
**Fecha:** 2026-10-27
**Repos:** `backend-supabase` (`services/agentes_eventos.py`, `routers/agentes_webhooks.py`, jobs en `main.py`), `agente-conversacional-multi_tenant` (solo si `conversacion.cerrada` necesita una señal del agente, ver abajo).
**Rama sugerida:** `feat/agentes-eventos`.
**Relaciona:** [134](./134-mvp-equipo-de-agentes.md), [136](./136-agentes-modelo-de-datos.md), [138](./138-agentes-adaptador-runtime.md) (quién consume los eventos), [132](./132-mcp-para-agentes-y-humanos.md) (`core.mcp_eventos`), [125](./125-notificaciones-cola-canales.md) (envío de avisos).

---

## Objetivo

Que los bots despierten solo por un evento o por una agenda, nunca preguntando cada tanto si hay algo nuevo. Cada evento se emite una vez, se entrega al menos una vez y se procesa una sola vez.

### Criterios de aceptación

- Los siete eventos de la tabla se emiten desde el servicio de dominio, en la misma transacción que el cambio que los origina (outbox).
- Ningún bot llama a una tool para preguntar si hay novedades. `buscar_eventos` del 132 sigue para lecturas, pero ningún prompt del 140 lo usa como bucle.
- Un evento entregado dos veces no lanza dos runs ni duplica un correo.
- El webhook entrante del runtime se rechaza si la firma HMAC sobre el cuerpo crudo no coincide.
- Un webhook repetido con el mismo id de run y el mismo estado no hace nada.
- Las agendas diaria y semanal corren en horario de Argentina y solo para tenants con `metadata.agentes.habilitado`.
- Si el dispatcher o el runtime fallan, el agente de WhatsApp y los jobs existentes del backend siguen igual (principio 8).

---

## Eventos

| Evento | Lo emite | Despierta a | Agrupa |
|--------|----------|-------------|--------|
| `trabajo.creado` | `encargar_analisis` (MCP humano) o backoffice | Jefe de cuenta | No |
| `trabajo.paso` | `registrar_traza` | Nadie. Stream SSE de la pantalla Trabajos | No |
| `pregunta.creada` | `crear_pregunta` | Aviso al humano según su banda | Por banda |
| `contexto.aportado` | `aportar_contexto`, `responder_pregunta`, backoffice | El bot que preguntó; si no hay pregunta, el jefe de cuenta | No |
| `reporte.listo` | `publicar_reporte` | Correo al humano | No |
| `conversacion.cerrada` | Job de cierre (ver abajo) | Analista de conversaciones | Sí, en lote |
| `agenda.diaria`, `agenda.semanal` | Scheduler | Jefe de cuenta | No |
| `trabajo.delegado` | `delegar` del jefe de cuenta | El bot delegado | No |
| `trabajo.cancelado` | Backoffice | Adaptador: cancela runs vivos | No |
| `run.terminado` | Aviso de fin del contenedor | Backend: cierra o reintenta | No |

`trabajo.delegado` no está en la tabla del documento de producto: lo suma este spec para el paso «reparte el trabajo». `trabajo.cancelado` y `run.terminado` son internos; no los recibe un bot. Cuando un analista termina, el dispatcher despierta al jefe de cuenta con `run.terminado` solo si ya no queda ningún analista corriendo en el trabajo.

### Forma de un evento

```json
{
  "id": "evt_01JB…",
  "tipo": "contexto.aportado",
  "tenant": "cordoba_frost",
  "ocurrido_at": "2026-11-04T14:02:11-03:00",
  "trabajo_id": "…",
  "destino": {"bot_rol": "analista_ventas", "run_id": "…"},
  "datos": {"contexto_id": "…", "pregunta_id": "…"},
  "version": 1
}
```

`datos` lleva ids, no contenido: el bot lee el contenido con la tool (`leer_contexto`), así el permiso lo aplica el MCP y no el evento.

---

## Outbox y entrega

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Emisión | Tabla `core.agentes_eventos` (outbox), insertada en la transacción del cambio | Si el cambio no se guarda, el evento no existe; si se guarda, el evento no se pierde | Llamar al runtime dentro de la transacción |
| Despertar del dispatcher | `NOTIFY agentes_eventos` al insertar; el dispatcher del backend hace `LISTEN` | Entrega inmediata sin consultar la tabla en bucle | Un job cada 30 s |
| Barrido | Job cada 5 min que reentrega lo que quedó `pendiente` o `fallido` con backoff vencido | Cubre un reinicio del proceso o un `NOTIFY` perdido. Es reintento del backend, no polling de un bot | Confiar solo en `NOTIFY` |
| Consumidor | `services/agentes_dispatcher.py` en el proceso del backend | El adaptador del 138 corre ahí. Un solo lugar decide qué despierta | Un worker aparte en el MVP |
| Relación con `core.mcp_eventos` | Se mantiene para los eventos de negocio del 132; el dispatcher puede generar `agenda.*` con un resumen de ellos | El 132 los lee por cursor; el MVP no los toca | Fusionar las dos tablas ahora |

### `core.agentes_eventos`

`id` (texto, ULID), tenant, `tipo`, `trabajo_id`, `destino` (jsonb), `datos` (jsonb), `estado` (`pendiente`, `entregado`, `agrupado`, `descartado`, `fallido`), `intentos`, `proximo_intento_at`, `error`, `clave_idempotencia` (única por tenant), `created_at`, `entregado_at`.

### Idempotencia y reintentos

- Cada emisión trae `clave_idempotencia` armada por el emisor: `trabajo.creado:{trabajo_id}`, `contexto.aportado:{contexto_id}`, `agenda.semanal:{tenant}:{iso_semana}`. Un insert repetido no crea otro evento.
- El dispatcher marca `entregado` solo cuando el adaptador confirma el lanzamiento (`lanzar` devolvió `id_externo`) o la entrega del aviso (el job de notificación quedó creado).
- Reintentos: 1 min, 5 min, 30 min, 2 h, 6 h. Al sexto fallo queda `fallido`, el trabajo pasa a `fallido` con un evento de traza `error` y se avisa al humano.
- Un evento para un bot `pausado` queda `descartado` con motivo; se ve en la traza.

---

## Webhooks salientes

En el MVP no hay webhook saliente a un tercero: «despertar al runtime» es la llamada del adaptador a la API de Cloud Run para ejecutar el job ([138](./138-agentes-adaptador-runtime.md)). Si en el futuro un runtime se dispara por webhook, el cuerpo se firma así:

- Header `X-Suplai-Signature: sha256=<hex>`, HMAC-SHA256 del cuerpo crudo con un secreto por tenant (`AGENTES_WEBHOOK_SECRET_<SCHEMA>` o en `public.distribuidoras` cifrado).
- Header `X-Suplai-Event-Id` con el `id` del evento, para que el receptor deduplique.
- Header `X-Suplai-Timestamp`; el receptor rechaza más de 5 min de diferencia.

---

## Aviso de fin del run

Ruta `POST /agentes/runs/{run_id}/fin`. La llama el entrypoint del contenedor al terminar ([138](./138-agentes-adaptador-runtime.md)).

1. Leer el cuerpo crudo antes de parsear.
2. Verificar `X-Suplai-Firma: sha256=<hex>`: HMAC-SHA256 del cuerpo crudo con el secreto de Secret Manager, comparado con `hmac.compare_digest`. Rechazar si el timestamp tiene más de 5 min. Si falla, 401 y log sin el cuerpo.
3. Buscar el run. Si no existe o el `run_id` del cuerpo no coincide con el de la ruta, 404.
4. Si el run ya tiene `fin_recibido_at`, 200 sin hacer nada (idempotencia por run).
5. Guardar el resultado, cerrar el run (con eso se revoca su token) y emitir `run.terminado` en la misma transacción. Responder 200 enseguida; el resto lo hace el dispatcher.

Si el contenedor muere sin avisar, el job `agentes_runs_vencidos` consulta la ejecución en Cloud Run y cierra el run como `error`.

Al procesar `run.terminado`, el backend:

- Cierra el run (`terminado` o `error`) con `resumen_runtime`.
- Si el bot era responsable del trabajo y terminó sin `publicar_reporte`, registra traza `error` («El jefe de cuenta terminó sin publicar el reporte») y relanza una vez con ese aviso en el prompt. Al segundo, el trabajo pasa a `fallido`.
- Si fue `ERROR`, reintenta una vez; después, `fallido`.

---

## Scheduler

APScheduler ya corre en `main.py` del backend (`agenda_send`, `erp_sync`, etc.). Se suman:

| Job | Cuándo | Qué hace |
|-----|--------|----------|
| `agentes_agenda_diaria` | 08:00 America/Argentina/Buenos_Aires | Emite `agenda.diaria` por tenant habilitado. El jefe de cuenta decide si hay algo que hacer; si no, termina sin trabajo |
| `agentes_agenda_semanal` | Lunes 07:30 | Emite `agenda.semanal`. En la prueba 2 crea el trabajo de análisis de conversaciones de la semana anterior |
| `agentes_lote_diario` | 18:00 | Junta avisos de banda `lote_diario` en un correo |
| `agentes_resumen_semanal` | Viernes 17:00 | Resumen semanal: trabajos, preguntas abiertas, propuestas pendientes |
| `agentes_cierre_conversaciones` | Cada 30 min | Detecta conversaciones cerradas y emite el lote |
| `agentes_barrido_outbox` | Cada 5 min | Reentrega pendientes |
| `agentes_runs_vencidos` | Cada 15 min | Marca `vencido` el run sin webhook después del tiempo máximo del 138 y lo trata como `ERROR` |

Los horarios son defaults; se guardan en `metadata.agentes.agenda` y se editan en el backoffice. Cada job toma un advisory lock por nombre para no correr dos veces si hay dos réplicas.

### `conversacion.cerrada`

Hoy no hay un evento de cierre de conversación. Definición para el MVP: una conversación del tenant cuyo último mensaje tiene más de 12 horas y no tenía evento de cierre. El job las junta y emite un solo `conversacion.cerrada` con la lista de ids (`agrupado` para las individuales). El analista no se despierta por cada charla: el jefe de cuenta lo lanza con la agenda semanal, o con un lote cuando la cantidad pasa un umbral (`metadata.agentes.umbral_conversaciones`, default 50). Esto evita lanzar un contenedor por cada charla.

---

## Fuera de alcance

- Webhooks hacia sistemas del cliente.
- Eventos de la prueba 3 (activación): se suman en su spec con el mismo outbox.

## Plan de prueba

- Unit: emitir dentro de una transacción que hace rollback no deja evento.
- Dispatcher: el mismo evento entregado dos veces lanza un solo run.
- Aviso de fin: firma mala → 401; aviso repetido → un solo cambio; cuerpo re-serializado → firma inválida.
- Scheduler: con dos procesos, `agenda.semanal` se emite una vez por tenant y semana.
- Caída: con la API del runtime devolviendo 500, los eventos quedan `pendiente` con backoff y el agente de WhatsApp responde normal.
