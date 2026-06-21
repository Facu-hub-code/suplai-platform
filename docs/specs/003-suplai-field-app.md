# Suplai Field — Índice cross-repo

**Estado:** Aprobado (V1 implementado parcialmente; V2 en diseño)  
**Fecha:** 2026-06-20 (actualizado)  

Documento maestro que enlaza las specs de implementación de **Suplai Field** (app mobile-first para vendedores humanos). Diseño de producto base en [002-suplai-field-app-diseno.md](./002-suplai-field-app-diseno.md).

---

## Nombre en UI

**Suplai Field** — módulo dentro del ecosistema **Vendedor Aumentado** (`sales_assistant_enabled`).

---

## Decisiones de producto (cerradas)

| Tema | Decisión |
|------|----------|
| Auth vendedor | `POST /login-vendedor` + deep link `?wp=` (patrón tienda) |
| Completitud tareas V1 | Automática al confirmar pedido que cumple criterio |
| **Completitud tareas V2** | Parcial por SKU + bonus completitud en un pedido; segundo pedido del día no suma |
| Pedidos V1 | Carga completa en app + refresh/sync ERP |
| Supervisor | Configura desde backoffice sección **Vendedores unificada** |
| Contrato de venta | Pedido en estado **`confirmado`** (alineado SPEC-042 Copilot) |
| Granularidad temporal | **Semana** para tendencias; ventana combo configurable en días |
| Clasificación productos | Manual A/B por distribuidora ([004](./004-clasificacion-productos-comerciales.md)) |
| Feature flag | **`sales_assistant_enabled` único** — deprecar `field_app_enabled` |
| Omnicanal | Misma BD; app y agente WA son vistas |

---

## Specs V1 (implementación base)

| Repo | Archivo | Contenido |
|------|---------|-----------|
| `field-app` | [001-project-overview.md](../../../field-app/docs/specs/001-project-overview.md) | Next.js mobile-first, auth, pantallas, proxies BFF |
| `backend-supabase` | [047-field-app-auth-y-bff.md](../../../backend-supabase/docs/specs/047-field-app-auth-y-bff.md) | `login-vendedor`, BFF `/vendedor-app/*`, ventas-semanales |
| `backend-supabase` | [048-field-tasks-gamificacion.md](../../../backend-supabase/docs/specs/048-field-tasks-gamificacion.md) | Migración `field_*`, motor tareas V1, torneos |
| `product-management-app` | [044-field-app-supervisor.md](../../../product-management-app/doc/specs/044-field-app-supervisor.md) | UI supervisor V1 (superseded en navegación por 006) |
| `agente-conversacional-multi_tenant` | [032-seller-field-omnicanal.md](../../../agente-conversacional-multi_tenant/docs/specs/032-seller-field-omnicanal.md) | Tools omnicanal + deep link |

---

## Specs V2 (diseño aprobado — junio 2026)

| # | Archivo | Contenido |
|---|---------|-----------|
| 004 | [004-clasificacion-productos-comerciales.md](./004-clasificacion-productos-comerciales.md) | Tipo A/B manual, badge productos |
| 005 | [005-field-tareas-v2-diseno.md](./005-field-tareas-v2-diseno.md) | 3 tipos tarea, delta, puntos por SKU, mediana × 2 |
| 006 | [006-vendedores-unificados-backoffice.md](./006-vendedores-unificados-backoffice.md) | Fichas FIFA, modales torneo/plantillas, BFF vendedores |
| 007 | [007-field-app-v2-mejoras.md](./007-field-app-v2-mejoras.md) | Perfil/logout, ayuda "?", pedidos en ficha PDV, CRON |

### Specs de implementación pendientes (por repo)

| Repo | Archivo propuesto | Contenido |
|------|-------------------|-----------|
| `backend-supabase` | `049-producto-tipo-venta.md` | Migración `tipo_venta`, API productos |
| `backend-supabase` | `050-field-tasks-v2-motor.md` | Motor tareas V2, CRON, evaluación parcial |
| `backend-supabase` | `051-bff-vendedores.md` | `GET /bff/vendedores`, avatar_url |
| `product-management-app` | `045-vendedores-unificados.md` | UI grid fichas, modales, upload avatar |
| `field-app` | `002-field-app-v2-mejoras.md` | Perfil, ayuda, pedidos históricos PDV |

> **Nota numeración:** Field backend usa 047/048 (V1). V2 continúa en 049–051.

---

## Orden de implementación V2

```text
Fase 1 — Productos
  backend 049 → backoffice badge + select tipo_venta

Fase 2 — Motor tareas
  backend 050 → config tenant combo/delta/puntos

Fase 3 — Backoffice vendedores
  backend 051 → backoffice 045 (fichas + modales + avatar)

Fase 4 — Field app
  field-app 002 → pedidos históricos PDV, perfil, ayuda "?"

Fase 5 — Deprecaciones
  field_app_enabled → sales_assistant_enabled
  CROSS_SELL_COMBO V1 → desactivar plantillas legacy
```

---

## Feature flag

**V2:** solo `sales_assistant_enabled` en `public.distribuidoras`.

`metadata.field_app_enabled` — **deprecado**; dejar de leer en backend, backoffice y login Field.

**Activar módulo vendedor + Field:**

```sql
UPDATE public.distribuidoras
SET sales_assistant_enabled = true
WHERE schema_name = 'tu_schema';
```

---

## URLs

| Entorno | URL |
|---------|-----|
| Producción | `https://field.suplaisales.com/{schema}?wp={telefono}` |
| Backend | `https://web-production-f544f.up.railway.app` |
| Sales-engine | Standby para `CROSS_SELL_RENTABLE` (V2.1+) |

---

## Referencias

- Diseño V1: [002-suplai-field-app-diseno.md](./002-suplai-field-app-diseno.md)
- Territorio / caso 2 visitas: [040-territorio](../../../backend-supabase/docs/specs/040-territorio-geo-zonas-vendedores-pdv.md)
- Arquitectura: [ARCHITECTURE.md](../ARCHITECTURE.md)
