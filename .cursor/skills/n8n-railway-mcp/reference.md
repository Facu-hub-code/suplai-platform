# Referencia — n8n Railway + MCP

## Arquitectura Railway (`n8n infra`)

```
Primary (editor + API + MCP)  ──queue──►  Worker
        │                                    │
        ├── Postgres (metadatos n8n)       │
        └── Redis (Bull queue) ◄─────────────┘
```

- **Primary**: `https://primary-production-c1d08.up.railway.app`
- Webhooks externos usan el mismo host (`WEBHOOK_URL` apunta al dominio público).

## MCP instance-level vs MCP Server Trigger

| Aspecto | Instance-level MCP | Nodo MCP Server Trigger |
|---------|-------------------|-------------------------|
| Alcance | Toda la instancia (workflows habilitados) | Un solo workflow |
| Auth | OAuth2 o Access Token centralizado | Config por workflow |
| Uso en Suplai | Cursor / agentes de código | Exponer un micro-servidor MCP ad hoc |

## Consideraciones (docs n8n)

- Hay que habilitar MCP en la instancia **y** en cada workflow (`Available in MCP`).
- `search_workflows` puede listar previews de workflows del usuario; el resto de tools solo sobre workflows MCP-enabled (salvo búsqueda).
- Todos los clientes MCP conectados ven los mismos workflows habilitados (no hay ACL por cliente).
- `execute_workflow` default = versión **publicada**; `manual` = borrador actual.

## Tools MCP observados (instancia Suplai)

Verificar siempre con `tools/list` tras actualizar n8n. Conjunto típico:

**Workflows**

- `search_workflows` — buscar por nombre/descripción
- `get_workflow_details` — esquema e inputs antes de ejecutar
- `execute_workflow` — disparar (webhook / form / chat)
- `validate_workflow` — validar código SDK
- `create_workflow_from_code` — crear desde TypeScript SDK
- `update_workflow` — actualizar por ID
- `archive_workflow` — archivar

**Construcción (SDK)**

- `get_sdk_reference` — patrones del Workflow SDK
- `search_nodes` — descubrir nodos por servicio
- `get_suggested_nodes` — sugerencias por técnica
- `get_node_types` — tipos exactos de parámetros (obligatorio antes de codear)

Puede haber tools adicionales de **data tables** según versión; consultar [MCP server tools reference](https://docs.n8n.io/advanced-ai/mcp/mcp-server-tools-reference/).

## REST API (publicación desde repo)

Base: `https://primary-production-c1d08.up.railway.app/`

| Variable local | Uso |
|--------------|-----|
| `N8N_BASE_URL` | Raíz de la instancia (trailing slash opcional) |
| `N8N_API_KEY` | JWT de API pública (`aud: public-api`) — **distinto** del MCP Access Token |

Ejemplo en repos: `test-api-gev/.env` (no versionar), scripts `publish_examples/publish-n8n.sh`.

Header típico:

```
X-N8N-API-KEY: <N8N_API_KEY>
```

## Cursor `mcp.json` (HTTP + SSE)

n8n exige cliente que acepte `application/json` y `text/event-stream`. Cursor lo gestiona al usar `type: http` en la config oficial.

Ejemplo mínimo (token fuera del repo):

```json
"n8n-mcp": {
  "type": "http",
  "url": "https://primary-production-c1d08.up.railway.app/mcp-server/http",
  "headers": {
    "Authorization": "Bearer <MCP_ACCESS_TOKEN>"
  }
}
```

Alternativa OAuth: URL base sin header; autorizar en el flujo del cliente (ver docs n8n → Claude Desktop / Claude Code).

## Integración con el stack Suplai

| Sistema | Relación con n8n |
|---------|------------------|
| Agente (`agent/`) | Histórico en `{tenant}.n8n_chat_histories`; webhook v2 reemplazó parte del rol n8n en media/typing |
| Backend | Specs referencian plantillas/envíos vía n8n; no es el runtime del agente LangGraph |
| Sniffer | `FORWARD_URL` opcional hacia otro webhook (puede ser n8n) |
| Sales-engine | Cron/retrain puede dispararse desde n8n (job semanal en README) |

## Enlaces

- [Instance-level MCP setup](https://docs.n8n.io/advanced-ai/mcp/accessing-n8n-mcp-server/)
- [MCP tools reference](https://docs.n8n.io/advanced-ai/mcp/mcp-server-tools-reference/)
- [Railway MCP](https://docs.railway.com/ai/mcp-server) — logs y variables del proyecto `n8n infra`
