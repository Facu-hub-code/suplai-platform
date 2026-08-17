# Admin Customer Success — Implementation Plan

> **For agentic workers:** execute task-by-task. Spec: `docs/specs/033-admin-customer-success.md`

**Goal:** Sección `/admin` Customer Success para clientes en `in_production` (salud, pago manual, eventos).

**Architecture:** Extender `implementation_projects` + tabla `customer_success_events`; router `/admin/customer-success`; UI lista+detalle; RBAC sección `customer_success`.

**Tech Stack:** FastAPI + asyncpg, Next.js admin panel, Postgres public schema.

## Global Constraints

- Solo clientes con `current_milestone = 'in_production'`
- Sin facturación / invoices / recordatorios
- Hard delete de eventos en v1
- Pooling: no tocar conexiones DB fuera de patrones existentes del admin

### Task 1: Backend migration + permissions + service + router + tests

### Task 2: Backoffice types + sidebar + section UI

### Task 3: Apply migration (user/MCP) + smoke verify
