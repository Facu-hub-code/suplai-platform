# Suplai Field — Índice cross-repo

**Estado:** Aprobado (derivado del diseño de producto)  
**Fecha:** 2026-06-18  

Documento maestro que enlaza las specs de implementación de **Suplai Field** (app mobile-first para vendedores humanos). Diseño de producto aprobado en [002-suplai-field-app-diseno.md](./002-suplai-field-app-diseno.md).

---

## Nombre en UI

**Suplai Field**

## Decisiones de producto (cerradas)

| Tema | Decisión |
|------|----------|
| Auth vendedor | `POST /login-vendedor` + deep link `?wp=` (patrón tienda) |
| Completitud tareas V1 | Automática al confirmar pedido que cumple criterio |
| Pedidos V1 | Carga completa en app + refresh/sync ERP |
| Supervisor | Configura desde backoffice (no desde app móvil) |
| Contrato de venta | Pedido en estado **`confirmado`** (alineado SPEC-042 Copilot) |
| Granularidad temporal | **Semana** para tendencias y frecuencia |
| Omnicanal | Misma BD; app y agente WA son vistas |

## Specs hijas

| Repo | Archivo | Contenido |
|------|---------|-----------|
| `field-app` | [001-project-overview.md](../../../field-app/docs/specs/001-project-overview.md) | Next.js mobile-first, auth, pantallas, proxies BFF |
| `backend-supabase` | [047-field-app-auth-y-bff.md](../../../backend-supabase/docs/specs/047-field-app-auth-y-bff.md) | `login-vendedor`, BFF `/vendedor-app/*`, ventas-semanales |
| `backend-supabase` | [048-field-tasks-gamificacion.md](../../../backend-supabase/docs/specs/048-field-tasks-gamificacion.md) | Migración `field_*`, motor tareas, torneos, endpoints supervisor |
| `product-management-app` | [044-field-app-supervisor.md](../../../product-management-app/doc/specs/044-field-app-supervisor.md) | UI supervisor: plantillas, torneos, dashboard |
| `agente-conversacional-multi_tenant` | [032-seller-field-omnicanal.md](../../../agente-conversacional-multi_tenant/docs/specs/032-seller-field-omnicanal.md) | Tools omnicanal + deep link |

> **Nota numeración:** Los números 043/044 en `backend-supabase` ya estaban ocupados (Odoo). Field usa **047** y **048**. Backoffice usa **044** (040–043 ocupados).

## Orden de implementación

```text
1. backend 048 — migración field_* + motor tareas (bloqueante)
2. backend 047 — login-vendedor + BFF vendedor-app
3. field-app 001 — scaffold + Home + auth
4. field-app — PDV, ficha, pedidos, torneo
5. backoffice 044 — sección supervisor
6. agent 032 — tools omnicanal
```

## Feature flag

`distribuidoras.metadata.field_app_enabled` (default `false`). Requiere `sales_assistant_enabled` o flag independiente según tenant.

**Activar tenant piloto:**

```sql
UPDATE public.distribuidoras
SET metadata = metadata || '{"field_app_enabled": true}'::jsonb
WHERE schema_name = 'tu_schema';
```

## URLs

| Entorno | URL |
|---------|-----|
| Producción (propuesta) | `https://field.suplaisales.com/{schema}?wp={telefono}` |
| Backend | `https://web-production-f544f.up.railway.app` |
| Sales-engine | Variable `SALES_ENGINE_URL` (solo server-side) |

## Relación con productos existentes

- **Complementa** asistente vendedor WhatsApp (`seller-assistant`, spec 030).
- **Reutiliza** territorio spec 040, pipeline pedidos tienda, `predict-combo` sales-engine.
- **No reemplaza** backoffice ni tienda B2B.
- Supervisor opera desde `product-management-app`; vendedor desde `field-app`.

## Referencias

- Diseño: [002-suplai-field-app-diseno.md](./002-suplai-field-app-diseno.md)
- Arquitectura: [ARCHITECTURE.md](../ARCHITECTURE.md)
- Territorio: [040-territorio](../../../backend-supabase/docs/specs/040-territorio-geo-zonas-vendedores-pdv.md)
- Módulo 04: [uses-cases.txt](../../../agente-conversacional-multi_tenant/docs/uses-cases.txt)
