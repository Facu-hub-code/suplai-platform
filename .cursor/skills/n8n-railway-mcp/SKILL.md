---
name: n8n-railway-mcp
description: Opera la instancia n8n en Railway (proyecto n8n infra), conecta Cursor vía MCP instance-level, expone/ejecuta workflows, y publica JSON desde repos locales. Usar cuando el usuario mencione n8n, workflows, webhooks de integración, MCP de n8n, GEV/post_pedido, o el deploy Primary en Railway.
---

# n8n en Railway + MCP (Suplai)

## Instancia de producción

| Recurso | Valor |
|---------|--------|
| Railway project | `n8n infra` (`2357ab9c-7c48-440a-8efc-391ab3805c0f`) |
| Servicio UI/API | `Primary` |
| URL pública | `https://primary-production-c1d08.up.railway.app` |
| Endpoint MCP HTTP | `https://primary-production-c1d08.up.railway.app/mcp-server/http` |
| Modo ejecución | Queue (`EXECUTIONS_MODE=queue`) + servicio `Worker` + `Redis` + `Postgres` |

Variables operativas relevantes en Railway (sin valores): `N8N_EDITOR_BASE_URL`, `WEBHOOK_URL`, `PORT`, credenciales `DB_*`, `QUEUE_BULL_REDIS_*`. Consultar con Railway MCP `list_variables` solo si hace falta depurar deploy — **no** copiar secretos al chat ni a commits.

## Conectar Cursor al MCP de n8n

Documentación oficial: [Accessing n8n MCP server](https://docs.n8n.io/advanced-ai/mcp/accessing-n8n-mcp-server/).

### Prerrequisitos en n8n (UI)

1. **Settings → Instance-level MCP** → activar **Enable MCP access** (owner/admin).
2. Por workflow a usar desde el agente: **Available in MCP** (menú `...` → Settings, o lista en la página MCP).
3. **Connection details** → pestaña **Access Token**: copiar el token personal **en el primer acceso** (luego queda redactado).

OAuth2 también es válido; en Cursor suele ser más simple el Access Token.

### Configuración en el workspace

1. Copiar [`.cursor/mcp.n8n.example.json`](../../mcp.n8n.example.json) y fusionar `n8n-mcp` en [`.cursor/mcp.json`](../../mcp.json).
2. Sustituir `YOUR_N8N_MCP_ACCESS_TOKEN` por el token de n8n (no confundir con `N8N_API_KEY` de la REST API).
3. Reiniciar MCP en Cursor (Settings → MCP → refresh) o reiniciar el IDE.

**No** commitear tokens. Si un token quedó en git, rotarlo en n8n (Connection details → Access Token → generar nuevo).

### Verificar conectividad

Antes de usar herramientas MCP en Cursor:

- Sin token → el endpoint responde **401**.
- Con token y header `Accept: application/json, text/event-stream` → `initialize` devuelve servidor `n8n MCP Server` (SSE).

Si falla: MCP deshabilitado en instancia, token revocado, o URL incorrecta (debe incluir `/mcp-server/http`).

## Cuándo usar MCP vs REST API

| Necesidad | Canal |
|-----------|--------|
| Buscar/ejecutar workflows expuestos a MCP, crear/editar workflows con SDK desde el agente | **MCP** (`CallMcpTool` / servidor `n8n-mcp`) |
| Publicar JSON desde repo (`test-api-gev`, scripts bash/Python) | **REST API** con `N8N_BASE_URL` + `N8N_API_KEY` |
| Integraciones GEV (sync stock/precios, post pedido) | Repo `test-api-gev` + skill personal `n8n-gev-workflows` |

El MCP **no** expone todos los workflows: solo los marcados **Available in MCP** (+ `search_workflows` con previews del resto según permisos del usuario del token).

`execute_workflow` por defecto usa versión **publicada** (`production`); para borrador usar `executionMode: "manual"`.

## Flujo recomendado del agente (MCP)

1. **Leer esquema del tool** en el descriptor MCP de Cursor antes de invocar (nombre y `inputSchema` cambian por versión de n8n).
2. **Descubrir**: `search_workflows` (filtro `query`, revisar `availableInMCP` y `description`).
3. **Detalle**: `get_workflow_details` antes de `execute_workflow`.
4. **Ejecutar**: `execute_workflow` con `inputs` acorde al trigger (webhook / form / chat).
5. **Crear/editar código**: `get_sdk_reference` → `search_nodes` → `get_node_types` → `validate_workflow` → `create_workflow_from_code` o `update_workflow`.

Lista ampliada de tools y consideraciones: [reference.md](reference.md).

## Repos locales con workflows

| Repo / ruta | Uso |
|-------------|-----|
| `test-api-gev/workflows/*.json` | GEV: `post_pedido`, `sync_stock`, `sync_precios` |
| `platform/workflows/del_corro_campana_semana23_personalizada.json` | Experimento del_corro: plantillas personalizadas desde Google Sheets |
| `platform/docs/n8n/del-corro-campana-semana23-personalizada.md` | Spec operativa del experimento |
| `test-api-gev/publish_gev_workflows.py` | Generador + publicación vía API |
| `demo-aysa/n8n-workflow-*.json` | Demo operario WhatsApp |

Para publicar/sync GEV, usar la skill `n8n-gev-workflows` (scripts `run_publish.sh` / `run_sync.sh`).

## Railway (operaciones)

- Listar servicios: Railway MCP `list_services` con `project_id` del proyecto `n8n infra`.
- Logs del Primary: `get_logs` en el servicio `Primary`.
- Redeploy: solo si el usuario lo pide; no tocar `N8N_ENCRYPTION_KEY` ni credenciales de DB sin plan de rollback.

## Guardrails

- **MUST**: confirmar que el workflow objetivo tiene **Available in MCP** antes de ejecutarlo vía MCP.
- **MUST**: no pegar `N8N_API_KEY`, MCP Access Token ni passwords de Railway en skills, commits o respuestas.
- **MUST**: ante cambios destructivos (`archive_workflow`, borrar nodos), pedir confirmación explícita.
- **SHOULD**: preferir `manual` al probar cambios no publicados; `production` para validar comportamiento live.
- **SHOULD**: para integraciones Suplai (agente, backend), documentar webhooks con URL base `WEBHOOK_URL` / dominio público de Primary.

## Troubleshooting

| Síntoma | Acción |
|---------|--------|
| 401 en MCP | Token ausente/incorrecto o MCP desactivado en instancia |
| Workflow no aparece en tools | Activar **Available in MCP** en ese workflow |
| `execute_workflow` distinto al editor | Está corriendo versión publicada; usar `executionMode: manual` |
| Publicación API falla | Revisar `N8N_API_KEY` y permisos del usuario API (distinto del token MCP) |
| Cola colgada | Revisar servicio `Worker` y Redis en Railway |

## Referencias

- [reference.md](reference.md) — tools MCP, REST vs MCP, enlaces
- [mcp.n8n.example.json](../../mcp.n8n.example.json) — plantilla Cursor MCP
- [n8n MCP tools reference](https://docs.n8n.io/advanced-ai/mcp/mcp-server-tools-reference/)
