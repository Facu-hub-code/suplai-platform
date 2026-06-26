# Suplai Copilot — Índice cross-repo

**Estado:** Aprobado (decisiones de producto)  
**Fecha:** 2026-06-03  

Documento maestro que enlaza las specs anidadas. Implementación repartida en `backend-supabase` (orquestación, tools, PDF, persistencia) y `product-management-app` (UI, artefactos, proxy).

---

## Nombre en UI

**Suplai Copilot**

## Decisiones de producto (cerradas)

| Tema | Decisión |
|------|----------|
| Runtime LLM | Servicio en **backend** (secretos, auditoría, tools). El back office solo hace proxy BFF (`app/api/copilot/*`). |
| Contrato de venta | Cuenta venta un pedido en estado **`confirmado`**. No exige pasar a `descargado`. |
| “Más vendido” / ranking | **Cantidad vendida** (`items_pedido.cantidad_solicitada`, UMV) y **precio al que salió** (`items_pedido.precio_unitario` aplicado en el pedido, con contexto de **lista de precios** del ítem / cliente). No usar solo conteo de filas como métrica principal del Copilot. |
| PDF | Descarga + envío opcional por **email (Brevo)**, a pedido del usuario en la conversación. |
| Secuencias multi-paso | **Fase 3**. **Fase 2:** agenda simple (CRUD existente) con confirmación. |
| WRITE (MVP) | Todos los roles del back office pueden ejecutar acciones; **auditoría obligatoria** (`user_id`, email, timestamp). Sin matriz de permisos en v1. |
| Límites LLM por tenant | **Sin límites** al inicio; más adelante cuotas por uso. |
| Sniffer / Kommo | **Fuera de alcance** de Suplai Copilot. |
| Persistencia chat | **90 días** por usuario; **no compartida** entre usuarios del mismo tenant (cada operador ve su historial). |

## Specs hijas

| Repo | Archivo | Contenido |
|------|---------|-----------|
| `backend-supabase` | [041-suplai-copilot-plataforma.md](../../backend-supabase/docs/specs/041-suplai-copilot-plataforma.md) | API, orquestador, tools, PDF/Brevo, DB, fases, seguridad |
| `backend-supabase` | [042-suplai-copilot-contrato-ventas.md](../../backend-supabase/docs/specs/042-suplai-copilot-contrato-ventas.md) | Definiciones SQL de métricas de venta para tools y PDF |
| `product-management-app` | [039-suplai-copilot-ui-artefactos.md](../../product-management-app/doc/specs/039-suplai-copilot-ui-artefactos.md) | Panel, bubble, canvas de artefactos, confirmación write |
| `suplai-platform` | [014-suplai-copilot-supervisor-ritmo-ventas.md](./014-suplai-copilot-supervisor-ritmo-ventas.md) | **Epic Fase 2.5:** día de semana por vendedor, thought stream, follow-ups, evals CI |
| `backend-supabase` | [043-suplai-copilot-sales-by-day-of-week.md](../../backend-supabase/docs/specs/043-suplai-copilot-sales-by-day-of-week.md) | Tool `sales_by_day_of_week` |
| `backend-supabase` | [044-suplai-copilot-thought-stream-followups.md](../../backend-supabase/docs/specs/044-suplai-copilot-thought-stream-followups.md) | SSE progreso + follow-ups sugeridos |
| `backend-supabase` | [045-suplai-copilot-evals-ci.md](../../backend-supabase/docs/specs/045-suplai-copilot-evals-ci.md) | Eval harness pytest por tenant |
| `product-management-app` | [050-suplai-copilot-thought-followups-ui.md](../../product-management-app/doc/specs/050-suplai-copilot-thought-followups-ui.md) | UI thought steps + chips dinámicos |

## Fases (resumen)

| Fase | Entregable usuario |
|------|-------------------|
| **0** | Chat + lectura + tablas/gráficos (artefactos) + definiciones explícitas |
| **1** | PDF descarga + email Brevo + mapa embebido + comparación de periodos |
| **2** | Acciones write (agenda) con preview + confirmación + audit log |
| **2.5** | Ritmo ventas supervisor: día de semana + vendedor, thought stream, follow-ups, evals CI |
| **3** | Secuencias de seguimiento multi-paso (diseño + ejecución) |

## Relación con productos existentes

- **No reemplaza** `AgentChatPreview` (prueba del agente WhatsApp en Conversaciones).
- **Complementa** Dashboard (`metricas`), Mapa comercial (`client-locations`), Sales Engine (ML).
- Reutiliza patrones de **SPEC-021** (PDF + Brevo) y **SPEC-029** (top productos — evolucionar semántica según 042).

## Feature flag

`distribuidoras.metadata.copilot_enabled` (o columna dedicada en iteración posterior). Deshabilitado por defecto hasta rollout por tenant.

## Implementación Fase 2 (2026-06-04)

- Backend: `agenda_create` (dry_run + `confirm_token`), `POST .../actions/confirm`, tablas `core.copilot_pending_actions` y `core.copilot_action_log`, migración `sql/35_copilot_actions.sql`.
- Front: artefacto `action_preview` con Confirmar / Cancelar, proxy `app/api/copilot/actions/confirm`.

## Implementación Fase 1 (2026-06-03)

- Backend: comparación de periodos, serie temporal, tool `clients_geojson`, PDF (`POST reports/pdf`, download, email Brevo), migración `sql/34_copilot_reports.sql`.
- Front: artefactos `map`, `chart`, `download`; botón «Generar informe PDF»; proxy `app/api/copilot/reports/*`.

## Implementación Fase 0 (2026-06-03)

- Backend: `routers/copilot.py`, `services/copilot/*`, `services/copilot_sales_metrics.py`, migración `backend-supabase/sql/33_copilot_tables.sql`.
- Front: `components/copilot/`, `app/api/copilot/*`, bubble en `app/page.tsx`.
- **Activar tenant:** `UPDATE public.distribuidoras SET metadata = metadata || '{"copilot_enabled": true}'::jsonb WHERE schema_name = 'tu_schema';`
- **Migración obligatoria** en Supabase antes de usar chat (tablas `core.copilot_*`).
- Sin `OPENAI_API_KEY` el backend usa planner heurístico (misma UX, tools reales).

## Referencias

- Arquitectura workspace: [ARCHITECTURE.md](../ARCHITECTURE.md)
- Investigación cruzada: [CROSS-REPO-QUERIES.md](../CROSS-REPO-QUERIES.md)
