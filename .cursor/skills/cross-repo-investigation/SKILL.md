---
name: cross-repo-investigation
description: Investigar bugs o preguntas que cruzan agente, backend, back office, tienda, sales-engine, sniffer y Supabase. Usar en flujos end-to-end, datos inconsistentes, link tienda, ML de compra o análisis Kommo.
---

# Investigación cross-repo Suplai

## Cuándo usar

- Datos distintos entre back office, agente o tienda web.
- Link de catálogo / pedido en tienda falla.
- Recomendaciones de combo o frecuencia de compra incorrectas.
- Análisis de conversaciones reales de vendedores (Kommo).
- Bug en pedido, contacto o conversación del agente.
- Tareas que tocan migración + API + UI + tool.

## Checklist

### 1. Acotar contexto

- [ ] `schema_name` del tenant
- [ ] IDs: contacto, pedido, `cliente_id`, `session_id`, teléfono
- [ ] ¿Flujo agente Meta, tienda web o sniffer Kommo?

### 2. Base de datos

- [ ] **Supabase principal** (MCP): `list_tables` en `public`, `core`, `{tenant}`
- [ ] **Sniffer**: tablas `kommo_*` en su Postgres (puede ser BD aparte)
- [ ] `execute_sql` solo lectura salvo cambios explícitos

### 3. Repo según síntoma

| Síntoma | Repo |
|---------|------|
| UI admin/distribuidora | `backoffice/` |
| Catálogo / carrito web | `tienda/` |
| Tool agente / WhatsApp | `agent/` |
| Endpoint / migración | `backend/` |
| Combo / retrain ML | `sales-engine/` |
| Conversación vendedor Kommo | `sniffer/` |

### 4. Síntesis

Reportar: flujo trazado, evidencia BD, archivos clave, fix mínimo por repo.

## Mapa rápido de datos

| Dato | Schema / BD | Repo escritor |
|------|-------------|---------------|
| Distribuidora / metadata agente | `public` | backend, backoffice |
| Productos, pedidos, contactos | `{tenant}` | backend, agente (tools) |
| Conversaciones agente | `core` | agente |
| Link tienda | metadata + URL fija | agente → tienda |
| Modelo co-ocurrencia | `.pkl` + lectura pedidos | sales-engine |
| Mensajes vendedor Kommo | `kommo_*` | sniffer |

## Referencias

- `platform/docs/CROSS-REPO-QUERIES.md`
- `platform/docs/ARCHITECTURE.md`
- Supabase principal: **`cvlbietibaaehgeimxgw`** (Suplai-east)
