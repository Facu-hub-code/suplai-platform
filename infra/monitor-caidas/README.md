# Monitor de caídas (DEV-20)

Monitor externo que avisa cuando se cae el backend, el agente o el MCP. Corre en
**GitHub Actions** (fuera de Railway) cada 5 minutos: si Railway se cae, el
monitor sigue vivo.

- Script: [`monitor.py`](monitor.py), solo biblioteca estándar de Python.
- Workflow: [`.github/workflows/monitor-caidas.yml`](../../.github/workflows/monitor-caidas.yml).
- Tests: [`test_monitor.py`](test_monitor.py), con mocks (sin red).

## Qué chequea

| Servicio | URL | Endpoint en el código |
|----------|-----|-----------------------|
| `backend` | `https://web-production-f544f.up.railway.app/health` | `backend-supabase/main.py` |
| `agente` | `https://agente-conversacional-multitenant-production.up.railway.app/health` | `agente-conversacional-multi_tenant/app/api/health.py` |
| `mcp` | `https://mcp.suplaisales.com/health` | `backend-supabase/mcp_server/main.py` |

Todos devuelven `200 {"status": "ok"}` cuando están bien.

## Cómo decide

1. Pega a los tres `/health` (timeout 15 s).
2. Si alguno falla, espera 60 s y lo vuelve a chequear. **Caído = dos fallos seguidos**; un error suelto no avisa.
3. Por cada servicio busca en el proyecto P3 una issue abierta con la línea `clave: health:<servicio>`:

| Situación | Qué hace |
|-----------|----------|
| Caído y no hay issue abierta | Crea issue en P3 (prioridad Urgente, etiquetas `Detectada`, `infra`, `Bug`) y manda mail |
| Caído y la issue dice `estado: recuperado` | Comenta la nueva caída en esa issue y manda mail |
| Caído y la issue ya dice `estado: caido` | Nada (ya avisó; no repite cada 5 minutos) |
| Responde y la issue dice `estado: caido` | Comenta la recuperación. **No cierra la issue** |
| Responde y no hay nada pendiente | Nada |

No hay base de datos: el estado vive en la issue. Cada comentario del monitor
termina en `estado: caido` o `estado: recuperado`, y manda el último. La issue
recién creada cuenta como `caido`. Cuando Faka cierra la issue, la próxima caída
abre una nueva.

El mail va a `facundo@suplaisales.com` por la API transaccional de Brevo (la
misma que usa el backend en `services/brevo_send.py`).

## Qué tiene que cargar Faka

En GitHub → `Facu-hub-code/suplai-platform` → Settings → Secrets and variables → Actions.

**Secrets** (pestaña *Secrets*):

| Nombre | Valor |
|--------|-------|
| `LINEAR_API_KEY` | API key personal de Linear (Settings → Security & access → Personal API keys). Con permiso de lectura y escritura de issues y comentarios. |
| `BREVO_API_KEY` | La misma `BREVO_API_KEY` del backend en Railway, o una nueva de Brevo → SMTP & API → API keys. |

**Variables** (pestaña *Variables*; no son secretas):

| Nombre | Valor |
|--------|-------|
| `LINEAR_TEAM_ID` | `a5142f86-4b58-4a43-a83a-666cbbb39122` (TECHNICAL TEAM) |
| `LINEAR_PROJECT_ID` | `bf009d94-406d-4574-9654-3b29afb343bc` (P3 - Nivel 3 · Escalamiento a Faka) |
| `BREVO_SENDER_EMAIL` | Remitente verificado en Brevo; el mismo que `ORDER_CONFIRMATION_FROM_EMAIL` del backend |
| `MONITOR_CAIDAS_ENABLED` | `true` para prender el cron. Sin esta variable el cron no corre |

Si falta un secret o una variable, el script no chequea nada y termina con error
(la corrida queda en rojo en Actions).

## Cómo activarlo

1. Mergear el PR (los workflows con `schedule` solo corren desde `main`).
2. Cargar los secrets y las variables de arriba, **menos** `MONITOR_CAIDAS_ENABLED`.
3. Probar en seco y después forzando una caída (ver abajo).
4. Crear la variable `MONITOR_CAIDAS_ENABLED=true`. Desde ahí corre cada 5 minutos.

Para apagarlo: borrar la variable o ponerla en `false`.

## Cómo probarlo

### Local, sin tocar nada

```bash
python -m unittest discover -s infra/monitor-caidas -v
```

Dry-run contra las URLs reales (solo hace los GET a `/health`; no llama a Linear ni a Brevo):

```bash
MONITOR_DRY_RUN=1 python infra/monitor-caidas/monitor.py
```

Forzando una caída del agente con una URL que no responde:

```bash
MONITOR_DRY_RUN=1 MONITOR_RETRY_DELAY=2 MONITOR_URL_AGENTE=http://127.0.0.1:9/health python infra/monitor-caidas/monitor.py
```

Tiene que mostrar `[dry-run] agente: caído: ... → crear_issue+mail`. En macOS con el
Python de python.org, si todo sale `SSLCertVerificationError`, corré antes
`Install Certificates.command` o agregá `SSL_CERT_FILE=/etc/ssl/cert.pem`.

### En GitHub Actions

Actions → *Monitor de caídas* → *Run workflow*:

1. Con **dry_run** tildado y `url_agente` = `https://httpbin.org/status/503`. Con
   `LINEAR_API_KEY` cargada, el dry-run además lee Linear (busca la issue abierta)
   pero no escribe. El log dice qué haría.
2. Prueba de punta a punta: **dry_run** destildado y la misma URL caída. Tiene que
   crear una sola issue en P3 y mandar un mail. Volver a correrlo sin URL pisada:
   tiene que comentar la recuperación en esa issue. Después cerrá la issue a mano.

## Variables opcionales del script

| Variable | Default | Para qué |
|----------|---------|----------|
| `MONITOR_DRY_RUN` | vacío | `1` = no crea issues ni manda mails |
| `MONITOR_URL_BACKEND`, `MONITOR_URL_AGENTE`, `MONITOR_URL_MCP` | URLs de producción | Pisar una URL para probar |
| `MONITOR_RETRY_DELAY` | `60` | Segundos entre el primer y el segundo chequeo |
| `MONITOR_TIMEOUT` | `15` | Timeout de cada request |
| `MONITOR_MAIL_TO` | `facundo@suplaisales.com` | Destinatario del mail |

## A tener en cuenta

- **El repo es público: los logs de Actions también.** El script solo loguea el
  servicio, el código HTTP o el tipo de error y el identificador de la issue;
  nunca cuerpos de respuesta ni claves. Las URLs de `/health` ya son públicas.
- GitHub no garantiza el horario del cron: con carga puede atrasarse varios
  minutos. Para caídas de Railway (que suelen durar más) alcanza.
- GitHub desactiva los workflows programados de un repo público tras 60 días
  sin commits. Si el repo queda quieto, Actions avisa por mail y se reactiva
  con un clic.
- Si Linear o Brevo fallan, la corrida queda en rojo y GitHub le avisa al dueño
  del repo por mail (aviso de respaldo).
