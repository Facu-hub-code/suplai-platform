# Dónde corren los bots del equipo de agentes: opciones

**Fecha:** 2026-10-27
**Para:** decidir el runtime de la prueba en Córdoba Frost y revisar las decisiones 1 y 2 del [134](../specs/134-mvp-equipo-de-agentes.md).
**Afecta:** [138](../specs/138-agentes-adaptador-runtime.md) (adaptador) y [139](../specs/139-agentes-tools-mcp.md) (token del MCP de agentes).

> **Decisión (27/10/2026):** opción B, en Google Cloud: Cloud Run jobs con Claude Agent SDK y Claude en Vertex, una ejecución por bot y token por run. El costo no es una restricción y la infraestructura de Suplai va a migrar a GCP. Es una prueba de concepto para aprender la infraestructura de agentes. El detalle está en el [138](../specs/138-agentes-adaptador-runtime.md).

---

## El problema

Con Cursor Cloud Agents, las conexiones MCP del dashboard son de toda la cuenta. Cualquier cloud agent puede usar el token fijo de cualquier bot. Con un solo tenant eso cruza bots; con dos tenants en la misma cuenta, cruza distribuidoras. Además Cursor nos ata a Grok y a un pool compartido con el uso de código.

## Lo que pide el runtime

| Requisito | Por qué |
|-----------|---------|
| Corre en segundo plano, horas si hace falta | Un análisis de un año no entra en un request |
| Despierta por evento y avisa por webhook firmado | Principio 3: nada por polling |
| Una máquina donde el bot ejecute código | El analista calcula sobre el archivo de `exportar_lote` |
| La credencial del MCP la pone el runtime, no el modelo | El bot no puede leer ni cambiar el token, aunque sufra una inyección en el texto de una conversación |
| Una credencial por run, no por bot | Si se filtra, vale para un trabajo, un bot y un rato |
| Tope de gasto por run | Un loop no puede quemar el presupuesto |
| Modelo a elección | No quedar atados a un proveedor |

## La pieza que vale para cualquier runtime: token por run

El aislamiento entre distribuidoras lo pone **nuestro** MCP, no el runtime. El runtime solo decide cómo llega la credencial. Cambio propuesto al 139, sin importar qué runtime elijamos:

- El backend firma, al lanzar cada run, un token corto (JWT, 3 horas) con `distribuidora_id`, `bot_id`, `trabajo_id`, `run_id` y los scopes del certificado vigente.
- `/agentes/mcp` toma tenant, bot y run de ese token. Ningún parámetro de una tool puede cambiarlos. El `run_id` deja de ser un parámetro.
- El token se revoca al cerrar el run, al cancelar el trabajo o al pausar el bot.
- El token fijo por bot queda solo para Cursor, si lo seguimos usando.

Con esto, la pregunta del runtime se reduce a una sola: **¿puede inyectar un token distinto en cada run sin que el modelo lo vea?**

---

## Opciones

### A. Claude Managed Agents (Anthropic)

Anthropic corre el loop del agente y le da a cada sesión un contenedor propio. En el contenedor el bot ejecuta bash y Python sobre archivos.

| Requisito | Cómo lo cubre |
|-----------|---------------|
| Segundo plano | Sesiones largas, con compactación de contexto automática |
| Evento y webhook | Abrimos una sesión con la API cuando llega el evento. Webhooks de cambio de estado firmados con HMAC (`webhook-signature`), que se verifican con el SDK |
| Código | Contenedor por sesión con bash, archivos y Python |
| Credencial fuera del modelo | Vaults: una credencial `static_bearer` asociada a la URL de `/agentes/mcp`. La inyecta un proxy de Anthropic al salir del contenedor; nunca entra al sandbox |
| Token por run | Un vault por sesión con el token del run (`vault_ids` se fija al crear la sesión) |
| Tope de gasto | `budget` en dólares por sesión: al llegar al tope la sesión se pausa, no se corta |
| Red | Red `limited`: solo nuestro MCP y el bucket |
| Agenda | Hay deployments programados por cron, pero conviene usar nuestro scheduler (137), que ya sabe de tenants |
| Modelo | Solo Claude. Cada bot es un agente versionado con su modelo |

En contra: es beta, no está en Google Cloud (solo en la API de Claude y en Claude Platform on AWS) y solo corre modelos Claude. La traza propia de Anthropic queda en su Console; la nuestra sigue siendo `registrar_traza`.

Costo: tokens a precio de lista más $0.08 por hora de sesión activa.

### B. Google Cloud: ADK en Cloud Run (el loop lo escribimos nosotros)

Agent Development Kit (ADK) es el framework de agentes de Google. El worker corre en Cloud Run: un worker pool que consume Pub/Sub, o Cloud Run jobs para lo asíncrono.

| Requisito | Cómo lo cubre |
|-----------|---------------|
| Segundo plano | Cloud Run jobs o worker pool con Pub/Sub. Nosotros manejamos tiempos y reintentos |
| Evento y webhook | El backend publica en Pub/Sub; el worker avisa al terminar llamando a nuestro backend |
| Código | No conviene correr el código del modelo en el mismo worker. Code Execution de Agent Engine (sandbox aislado, preview) o un sandbox aparte |
| Credencial fuera del modelo | `McpToolset` con `header_provider`: arma el `Authorization` en cada llamada desde el estado de la sesión, no desde el texto del modelo |
| Token por run | Sí: el worker recibe el token del run en el mensaje de Pub/Sub |
| Tope de gasto | Lo programamos nosotros |
| Modelo | Gemini en Vertex, o Claude en Vertex. Con Claude en Vertex no hay MCP connector ni code execution de Anthropic: el loop y las tools son nuestros |

En contra: es lo que más hay que construir. Es casi la implementación `xai` del 138, con otro proveedor y la infraestructura en GCP. Hoy no tenemos nada en GCP (backend en Railway, base en Supabase).

### C. Vertex AI Agent Engine

El runtime administrado de Google para agentes ADK: deploy, sesiones, memoria y Code Execution (preview, sandboxes que duran hasta 14 días). No encontré documentación que confirme soporte de MCP remoto dentro de Agent Engine. Hay que verificarlo antes de considerarlo; si no lo tiene, cae en la opción B.

### D. Loop propio en el backend de Railway

Lo que el 138 llama implementación `xai`, con cualquier proveedor: ponemos el token del run en cada llamada y no hay riesgo de credenciales. Falta el sandbox para el código del modelo, que habría que contratar aparte. Es la opción con más control y la que más tarda.

### E. Cursor Cloud Agents (plan actual)

Sin costo por token. El aislamiento depende de un chequeo nuestro (`run_id`) y no del runtime. Modelo: Grok. Sirve solo con un tenant por cuenta.

---

## Comparación

| | A. Managed Agents | B. ADK + Cloud Run | C. Agent Engine | D. Loop propio | E. Cursor |
|---|---|---|---|---|---|
| Credencial fuera del modelo | Sí (vault) | Sí (`header_provider`) | A verificar | Sí | No |
| Token por run | Sí | Sí | A verificar | Sí | No |
| Sandbox para código | Incluido | Aparte | Incluido (preview) | Aparte | Incluido |
| Webhook firmado | Incluido | Lo hacemos | A verificar | No hace falta | Incluido |
| Tope de gasto | Incluido | Lo hacemos | Lo hacemos | Lo hacemos | Pool semanal |
| Modelos | Claude | Gemini o Claude | Gemini o Claude | Cualquiera | Grok |
| Trabajo nuestro | Bajo | Alto | Medio | Alto | Bajo |
| Nube | Anthropic | GCP | GCP | Railway | Cursor |
| Madurez | Beta | GA (Code Execution en preview) | GA, partes en preview | Nuestro | GA |

---

## Modelo por bot

Precios de lista por millón de tokens (entrada / salida). Fuente: precios de Anthropic al 06/10/2026 y página de precios de Vertex.

| Bot | Qué necesita | Claude | Gemini |
|-----|--------------|--------|--------|
| Jefe de cuenta | Planificar, consolidar y escribir el reporte. Pocas llamadas | Opus 5.5, $4 / $20, effort medio | Gemini 3.1 Pro, $2 / $12 |
| Analista de ventas | Escribir y correr Python sobre archivos, explicar cifras | Sonnet 5.5, $2 / $10 | Gemini 3.1 Pro |
| Analista de conversaciones | Leer cientos de charlas y clasificar motivos | Sonnet 5.5 coordina y Haiku 5.5 ($0.10 / $0.50) clasifica en lote | Gemini 3.7 Flash, $0.75 / $3.75 hasta el 31/12/2026 |

Estimación gruesa de un análisis de ventas de un año con Claude, a validar en la prueba:

- Jefe de cuenta: unos 200k tokens de entrada y 20k de salida, cerca de $1,2.
- Analista: unos 500k de entrada y 50k de salida, cerca de $1,5.
- Una hora de sesión: $0,08.

Total: unos **$3 por análisis**. El caché de prompts baja la entrada repetida.

---

## Recomendación

1. **Token por run en el MCP de agentes, ya.** Cierra el agujero en cualquier runtime y no depende de esta decisión. Va como cambio al 139.
2. **Prueba en Córdoba Frost: opción A (Claude Managed Agents).** Es la única que trae, sin construir, las tres cosas que nos faltan: credencial por sesión fuera del alcance del modelo, sandbox para el código y tope de gasto. El adaptador del 138 queda igual: `lanzar` crea la sesión con su vault, `seguir` manda un mensaje, `cancelar` interrumpe y el webhook trae el estado.
3. **Si la empresa prefiere quedarse en Google Cloud o usar Gemini: opción B,** sabiendo que es armar el loop, el sandbox y los topes. Conviene antes una prueba corta de dos días para confirmar si Agent Engine (C) toma MCP remoto, porque eso ahorraría parte de B.
4. **Grok deja de ser condición.** El adaptador ya separa el runtime; el modelo pasa a ser un campo del bot.

Si se elige A, cambian las decisiones 1 y 2 del 134: la prueba se paga por token (unos $3 por análisis, más el costo de las pruebas fallidas) en lugar de salir del plan de Cursor.

## A confirmar

- A: que la beta de Managed Agents esté habilitada en la organización de Anthropic de Suplai, y el uso de datos de los tenants en esa sesión según los términos vigentes.
- B y C: soporte de MCP remoto en Agent Engine, límites de Code Execution (preview) y precios de Claude en Vertex.
- Todas: el número real de tokens de un análisis, que sale de la primera corrida.

## Fuentes

- Guía bundled del SDK de Anthropic (Managed Agents: vaults, webhooks, session budgets, networking, disponibilidad por plataforma).
- [Agent Engine overview](https://docs.cloud.google.com/agent-builder/agent-engine/overview)
- [Code Execution en Agent Engine](https://discuss.google.dev/t/introducing-code-execution-the-code-sandbox-for-your-agents-on-vertex-ai-agent-engine/264336)
- [ADK: configuración avanzada de MCP (`header_provider`)](https://adk.dev/tools-custom/mcp-tools/advanced/)
- [Cloud Run: autenticar agentes](https://docs.cloud.google.com/run/docs/ai/authenticate-agents)
- [ADK en worker pool de Cloud Run](https://codelabs.developers.google.com/codelabs/cloud-run/host-adk-agent-worker-pool-single-turn)
- [Precios de Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/pricing)
- [Webhooks de Cursor Cloud Agents](https://cursor.com/docs/cloud-agent/api/webhooks)
