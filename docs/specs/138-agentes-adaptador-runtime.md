# 138 — Equipo de agentes: runtime en Google Cloud

**Estado:** Borrador. Decisiones del 27/10/2026: los bots corren en Google Cloud, con Cloud Run jobs y Claude Agent SDK sobre Claude en Vertex. Es una prueba de concepto para aprender la infraestructura de agentes en GCP, no software de producción.
**Fecha:** 2026-10-27
**Repos:** `backend-supabase` (`services/agentes_runtime/`), `suplai-platform` (`infra/gcp/agentes/` con Terraform y `agentes-runtime/` con la imagen, mientras dure la prueba).
**Rama sugerida:** `feat/agentes-runtime-gcp` en backend y en platform.
**Relaciona:** [134](./134-mvp-equipo-de-agentes.md), [137](./137-agentes-eventos-webhooks-scheduler.md) (eventos), [139](./139-agentes-tools-mcp.md) (MCP de agentes y token por run), [140](./140-agentes-bots-mvp.md) (instrucciones de los bots). Comparación de opciones: [runtime-agentes-opciones-2026-10-27](../producto/runtime-agentes-opciones-2026-10-27.md).
**Reemplaza:** la versión anterior de este spec, que corría los bots en Cursor Cloud Agents con Grok. Se descartó porque las conexiones MCP de Cursor son de toda la cuenta y cualquier agente podía usar el token de otro bot.

---

## Objetivo

Que el backend lance, siga, cancele y reciba el estado de un bot sin saber dónde corre. En esta prueba, cada run de un bot es una ejecución nueva de un Cloud Run job: un contenedor limpio con el harness, que habla solo con el MCP de agentes y con Vertex, y se destruye al terminar.

### Criterios de aceptación

- Fuera de `services/agentes_runtime/` no hay ningún import ni nombre de Cloud Run ni de Vertex (principio 6). Un test lo verifica con grep.
- La interfaz tiene `lanzar`, `cancelar`, `estado` y el parseo del aviso de fin. `seguir` lanza una ejecución nueva.
- **Una ejecución por bot.** El jefe de cuenta y cada analista corren en ejecuciones separadas, cada una con su token por run. Nunca dos bots en el mismo contenedor.
- La cuenta de servicio del job no tiene permiso sobre el bucket de agentes. El bot solo baja archivos con la URL firmada que le da el MCP.
- El job no tiene salida libre a internet: solo llega al MCP de agentes, a Vertex y a Cloud Storage por URL firmada.
- Toda la infraestructura está en Terraform. Nada se crea a mano en la consola, salvo lo que el propio Terraform necesita para arrancar (ver «Arranque»).
- Un run sin aviso de fin después del tiempo máximo queda `vencido` y se trata como error.

---

## Las tres capas de un bot

| Capa | Qué es | En esta prueba |
|------|--------|----------------|
| Modelo | Lee, razona y elige qué tool usar | Claude en Vertex. Es un campo de cada bot |
| Harness | El loop que llama al modelo, ejecuta las tools y le devuelve los resultados: instrucciones, lista de tools, manejo de contexto y topes | Claude Agent SDK, con versión fija, configurado con archivos versionados |
| Máquina | Donde corren la terminal, los archivos y Python | Un contenedor por run en Cloud Run jobs |

No escribimos el loop: el harness ya resuelve contexto, tools y reintentos. Lo que controlamos es su configuración.

---

## Arquitectura

```text
 RAILWAY (sin cambios)                          GOOGLE CLOUD (proyecto suplai-agentes)
 ┌────────────────────────────┐                ┌──────────────────────────────────────┐
 │ Backend                    │  1. ejecuta    │ Cloud Run job "agente-run"           │
 │  scheduler y dispatcher    │ ─────────────▶ │  una ejecución por run de un bot     │
 │  firma el token del run    │   job con      │  ┌────────────────────────────────┐  │
 │                            │   overrides    │  │ entrypoint.py                  │  │
 │ MCP de agentes             │                │  │ Claude Agent SDK               │  │
 │  /agentes/mcp              │ ◀───────────── │  │ bash, archivos, Python         │  │
 │                            │ 2. tools con   │  └────────────────────────────────┘  │
 │ /agentes/runs/{id}/fin     │    el token    │     │ 3. modelo                      │
 │                            │ ◀───────────── │     ▼                                │
 └─────────────┬──────────────┘ 4. aviso de    │  Vertex AI (Claude)                  │
               │                   fin + HMAC  │                                      │
 ┌─────────────▼──────────────┐                │  Cloud Storage "suplai-agentes-datos"│
 │ Supabase (Postgres)        │                │   solo por URL firmada               │
 └────────────────────────────┘                │  Artifact Registry: imagen           │
                                               │  Secret Manager: secreto HMAC        │
                                               └──────────────────────────────────────┘
```

### Flujo de un run

1. El dispatcher del [137](./137-agentes-eventos-webhooks-scheduler.md) recibe el evento que despierta a un bot (`trabajo.creado`, `trabajo.delegado`, `contexto.aportado`).
2. El backend crea la fila en `core.agentes_runs` y firma el token del run ([139](./139-agentes-tools-mcp.md)).
3. `lanzar` ejecuta el job con overrides de esa ejecución: variables `RUN_ID`, `TRABAJO_ID`, `BOT_ROL`, `MCP_URL`, `MCP_TOKEN`, `MODELO`, `TIEMPO_MAX_MIN` y `FIN_URL`. El nombre de la ejecución queda como `id_externo`.
4. El entrypoint arma la configuración del harness: instrucciones del rol, MCP de agentes con `Authorization: Bearer ${MCP_TOKEN}`, tools permitidas, modelo y topes.
5. El bot trabaja. Lee datos por el MCP; los archivos de `exportar_lote` los baja con la URL firmada y calcula con Python en el contenedor.
6. Si el bot necesita al humano, abre la pregunta y termina el run. No se queda esperando: cuando llega `contexto.aportado`, el backend lanza otro run.
7. Al terminar, el entrypoint llama a `FIN_URL` con el resultado, firmado con HMAC. El backend revoca el token y cierra el run.

### Por qué una ejecución por bot

Con los tres bots como subagentes en un contenedor, el MCP vería un solo cliente con un solo token: tendría que darle los permisos de los tres, y lo que separa a cada analista quedaría en la configuración del harness. Es el principio 1 al revés. Con una ejecución por bot, cada token lleva solo los scopes del certificado de ese bot y el servidor hace cumplir la separación.

El jefe de cuenta delega con la tool `delegar`; el backend lanza la ejecución del analista. Cuando el analista termina, el dispatcher despierta al jefe con otra ejecución.

---

## Interfaz

```python
class RuntimeAgentes(Protocol):
    nombre: Literal["gcp_cloud_run", "fake"]

    async def lanzar(self, pedido: PedidoRun) -> RunLanzado: ...
    async def cancelar(self, run: RunRef) -> None: ...
    async def estado(self, run: RunRef) -> EstadoRun: ...
    def parsear_fin(self, headers: Mapping[str, str], cuerpo: bytes) -> FinRun | None: ...
```

| Tipo | Campos |
|------|--------|
| `PedidoRun` | `run_id`, `trabajo_id`, `tenant`, `bot` (rol, modelo, certificado vigente), `token_run`, `mensaje_inicial`, `tiempo_max_min` |
| `RunLanzado` | `id_externo` (nombre de la ejecución), `inicio` |
| `RunRef` | `run_id`, `id_externo` |
| `EstadoRun` | `estado` normalizado (`lanzando`, `corriendo`, `terminado`, `error`, `cancelado`) |
| `FinRun` | `run_id`, `resultado` (`ok` o `error`), `resumen`, `consumo` (tokens y costo estimado), `firma_valida` |

`seguir` desaparece de la interfaz: retomar es lanzar un run nuevo del mismo trabajo, con el resumen del anterior y el contexto nuevo en `mensaje_inicial`. Lo arma el dispatcher.

`fake` es una implementación en memoria para tests y para correr el backend sin GCP.

---

## Implementación `gcp_cloud_run`

| Operación | Cómo |
|-----------|------|
| `lanzar` | Cloud Run Admin API: `jobs.run` del job `agente-run` con `overrides.containerOverrides[0].env` y `timeout`. Cuenta de servicio `railway-lanzador` |
| `cancelar` | `executions.cancel` de la ejecución y revocación del token |
| `estado` | `executions.get`. Solo para el job de vencidos y para diagnóstico, nunca en bucle |
| `parsear_fin` | Header `X-Suplai-Firma: sha256=<hex>`, HMAC-SHA256 del cuerpo crudo con el secreto de Secret Manager, comparado en tiempo constante. Header `X-Suplai-Run` y timestamp con tolerancia de 5 min |

Si la ejecución termina con error y nunca llamó a `FIN_URL` (el contenedor murió, OOM, timeout), el job de vencidos del 137 la detecta con `executions.get` y cierra el run como `error`.

Las variables de los overrides se ven en la consola de GCP para quien tenga permiso de ver el job. Se acepta en la prueba porque el token dura 3 horas y se revoca al cerrar el run.

---

## La imagen del run

Vive en `suplai-platform/agentes-runtime/` durante la prueba.

```text
agentes-runtime/
  Dockerfile
  entrypoint.py
  requirements.txt          versiones fijas
  config/
    topes.yaml              tiempo y gasto máximo por rol
    tools.yaml              tools del MCP que el harness habilita por rol
```

- Base Python con Node (el Agent SDK lo necesita). Claude Agent SDK, pandas y numpy con versión fija.
- Usuario sin privilegios. Ninguna credencial dentro de la imagen.
- Las instrucciones de cada rol **no** viven en la imagen: el entrypoint las pide al MCP al arrancar (`leer_instrucciones`, [139](./139-agentes-tools-mcp.md)), armadas por el backend con el certificado vigente ([140](./140-agentes-bots-mvp.md)). Así cambiar una instrucción no exige una imagen nueva.

### Entrypoint

1. Lee las variables de la ejecución y espera hasta 2 minutos a que el MCP responda: con Direct VPC egress la red tarda unos segundos en quedar programada al arrancar (en la prueba del 28/10/2026, 13 s).
2. Configura el harness:
   - Modelo por Vertex: `CLAUDE_CODE_USE_VERTEX=1`, proyecto y región del job. La credencial de Vertex es la cuenta de servicio del job; no hay claves.
   - Un solo MCP, el de agentes, con el header `Authorization: Bearer ${MCP_TOKEN}`.
   - Tools del harness: bash, lectura y escritura de archivos. `WebFetch` y `WebSearch` apagadas.
   - Tope de turnos y de tiempo según `topes.yaml`.
3. Arranca el bot con `mensaje_inicial`.
4. Corta si pasa el tope de tiempo o de gasto estimado.
5. Llama a `FIN_URL` con el resultado firmado.
6. Sale con código distinto de cero si algo falló, para que el estado de la ejecución lo muestre.

---

## Infraestructura (Terraform)

En `suplai-platform/infra/gcp/agentes/`. Estado de Terraform en un bucket con versionado.

| Recurso | Configuración |
|---------|---------------|
| Proyecto `suplai-agentes` | Separado del resto. APIs: Cloud Run, Artifact Registry, Cloud Storage, Vertex AI, Secret Manager, IAM, Logging, Compute (para la red) |
| Artifact Registry | Repositorio Docker `agentes` |
| Cloud Run job `agente-run` | Imagen del registro, 2 vCPU y 4 GiB para empezar, una tarea, **sin reintentos** (los decide el backend), timeout por defecto de 2 h (el máximo de Cloud Run jobs es 168 h) |
| Cuenta de servicio `agente-run` | Usar Vertex AI (`roles/aiplatform.user`) y escribir logs. **Nada** sobre el bucket |
| Red | El job sale por una VPC (Direct VPC egress, todo el tráfico). Vertex y Cloud Storage por Private Google Access, sin pasar por internet. Hacia internet, Cloud NAT con una regla de firewall por nombre de dominio (Cloud NGFW, objetos FQDN) que deja pasar solo el host del MCP de agentes. Todo lo demás, bloqueado |
| Bucket `suplai-agentes-datos` | Acceso uniforme, sin acceso público, borrado de objetos a los 7 días |
| Cuenta de servicio `railway-lanzador` | Rol propio con solo `run.jobs.runWithOverrides`, `run.executions.get` y `run.executions.cancel` sobre ese job, más firmar URLs del bucket. Clave JSON como variable secreta en Railway (Railway no ofrece la identidad que pide Workload Identity Federation) |
| Secret Manager | Secreto HMAC del aviso de fin. Lo lee la cuenta del job y la de Railway |
| Presupuesto | Alertas al 50, 90 y 100 %. Avisa, no frena: el tope real está en el entrypoint |

### Arranque (a mano, una sola vez)

1. Crear el proyecto y asociarle la facturación.
2. Habilitar Claude en el Model Garden de Vertex y pedir cuota para los modelos de [140](./140-agentes-bots-mvp.md).
3. Crear la cuenta de servicio `terraform` con los roles para crear lo de la tabla, y darle a Faka permiso de suplantarla. Terraform corre como esa cuenta, nunca como owner.

### Región

Cloud Run y el bucket en `us-east4` (Virginia), cerca de Supabase (`Suplai-east`) y de Railway. Vertex por el endpoint de Claude que tenga cuota (`global` o `us-east5`). Se confirma al pedir la cuota.

---

## Tiempos y consumo

| Parámetro | Default | Dónde |
|-----------|---------|-------|
| `tiempo_max_min` jefe de cuenta | 60 | `config/topes.yaml` y override de timeout |
| `tiempo_max_min` analistas | 90 | idem |
| Runs simultáneos por tenant | 3 | `metadata.agentes.runtime_limites` |
| Runs por trabajo | 10 | idem; al pasarlo, el trabajo queda `fallido` |

El costo por run lo informa el entrypoint en el aviso de fin (tokens de entrada y salida por modelo) y se guarda en `consumo_estimado`.

---

## Fuera de alcance

- Proxy de salida que agregue el `Authorization` afuera del contenedor, para que el token nunca entre a la máquina. Va antes de activar una segunda distribuidora.
- Más libertad de red para los bots (web, otras APIs). La red cerrada es una decisión de la POC; se revisa cuando un bot necesite salir a otro destino, sumando ese host a la regla por nombre de dominio.
- GKE Agent Sandbox, para muchos runs en paralelo.
- Navegador en la imagen.
- Migrar el backend o Supabase a GCP: cuando pase, cambia `MCP_URL` y nada más.

## Plan de prueba

- Test de arquitectura: grep de `run_v2`, `google.cloud.run` y `vertex` fuera de `services/agentes_runtime/` falla el CI.
- `fake` para los tests del dispatcher y de las tools.
- `parsear_fin`: firma mala, timestamp viejo y cuerpo re-serializado se rechazan.
- Manual, en este orden:
  1. Ejecutar el job a mano con un bot de prueba que llama una sola tool (`registrar_traza`) y termina.
  2. Desde el contenedor, un `curl` a un dominio cualquiera falla por la red.
  3. Desde el contenedor, leer el bucket con la cuenta del job falla por permisos.
  4. El backend lanza, cancela y recibe el fin de un run sin intervención manual.
