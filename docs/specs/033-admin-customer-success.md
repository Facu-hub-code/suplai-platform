# Admin — Customer Success (continuación S1)

**Estado:** Implemented (código en ramas `feat/admin-customer-success`; migración 99 aplicada en Suplai-east)  
**Fecha:** 2026-08-07  
**Repos:** `backend-supabase`, `product-management-app`  
**Continúa:** pipeline S1 (Implementaciones → hito `in_production`)  
**Inventario:** Entidad S — Operación interna; extensión de S1 / precursor de facturación  
**Precede a:** plan de implementación (`docs/superpowers/plans/` — tras aprobación de este spec)

---

## 1) Objetivo

Herramienta interna en `/admin` para:

1. Ver la **salud** de cada cliente ya en producción.
2. Registrar **eventos** (touchpoints, ajustes de producto, incidencias, notas) — dato clave para detectar patrones hacia PMF.
3. Dejar listo el campo **`estado_pago`** (manual) sin lógica de cobranza.

Hoy hay ~5 proyectos en `in_production` y **0 clientes pagando** (fase PMF). Priorizar velocidad de construcción sobre completitud.

---

## 2) Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Quién entra a CS | Solo proyectos con `current_milestone = 'in_production'` | Continuación natural de S1; sin alta manual | Alta manual / híbrido |
| Modelo de datos | Extender `implementation_projects` + tabla `customer_success_events` | Mínimo schema, cero sync, sale rápido | Tabla `customer_success_accounts` 1:1; campos en `distribuidoras` |
| Salud | Enum `healthy` / `at_risk` / `critical` / `unknown` (default) | Semáforo filtrable, fricción baja | Score 1–5; solo notas libres |
| Pago | Enum `no_billable` / `pending` / `paying` / `churned` (default `no_billable`) | Estructura lista para facturar sin cobranza | Flag boolean; grace/overdue/trial |
| Tipos de evento | `touchpoint` / `ajuste_producto` / `incidencia` / `nota` | Catálogo corto filtrable | Catálogo amplio; tags libres |
| RBAC | Nueva sección `customer_success` (`view`/`edit`) | Separable de Kanban a futuro | Reusar `implementaciones`; área nueva |
| Matriz base | Área `implementaciones` → view+edit; founders/sudo | Mismo staff que opera onboarding | Solo founders |
| UI | Lista/tabla + panel detalle (no Kanban) | Volumen chico; foco en historial | Kanban por salud |
| API | Router dedicado `/admin/customer-success/*` estilo POST | No hinchar `admin_projects.py` | Extender router de projects |
| Delete eventos | Hard delete en v1 | Herramienta interna; YAGNI soft-delete | Soft-delete |

---

## 3) Alcance explícito

### Incluido (v1)

- Migración: columnas CS en `implementation_projects` + tabla `customer_success_events`.
- CRUD mínimo: list, get, update-status, events create/update/delete.
- Sección `/admin` Customer Success: lista con badges, filtros (`estado_salud`, `event_type`, búsqueda), detalle con timeline + form de evento.
- RBAC: sección `customer_success` en backend + backoffice.
- Tests unitarios/servicio básicos en backend (list filter, status update, create event).

### Fuera de alcance (v1)

- Facturación, invoices, recordatorios automáticos, integración de pagos.
- Cambio automático de `estado_salud` por métricas.
- Leaderboard / charts / export / adjuntos en eventos.
- Alta manual de clientes a CS sin pasar por `in_production`.
- Soft-delete de eventos; notificaciones Slack/email.

---

## 4) Orden de implementación

| Orden | Repo | Rama sugerida | Dependencia |
|-------|------|---------------|-------------|
| 1 | `backend-supabase` | `feat/admin-customer-success` | Migración SQL → service → router → tests → registro en `main.py` |
| 2 | `product-management-app` | `feat/admin-customer-success` | Tras API usable (o en paralelo con mocks mínimos); tipos permisos → sidebar → section UI → proxies si aplica |
| 3 | `suplai-platform` | `feat/admin-customer-success` | Este spec (+ plan); actualizar inventario S1 cuando esté shipped |

**Merge humano:** backend (migración aplicada en Supabase) → backoffice → docs platform.

---

## 5) Migración de base de datos

**Archivo sugerido:** `backend-supabase/sql/99_customer_success.sql` (confirmar número libre al implementar).

### 5.1 Alter `public.implementation_projects`

```sql
ALTER TABLE public.implementation_projects
  ADD COLUMN IF NOT EXISTS estado_salud text NOT NULL DEFAULT 'unknown'
    CHECK (estado_salud IN ('healthy', 'at_risk', 'critical', 'unknown')),
  ADD COLUMN IF NOT EXISTS estado_pago text NOT NULL DEFAULT 'no_billable'
    CHECK (estado_pago IN ('no_billable', 'pending', 'paying', 'churned')),
  ADD COLUMN IF NOT EXISTS cs_updated_at timestamptz;

COMMENT ON COLUMN public.implementation_projects.estado_salud IS
  'Customer Success health for in_production clients';
COMMENT ON COLUMN public.implementation_projects.estado_pago IS
  'Manual payment status; no billing automation in v1';
```

Backfill: no hace falta — DEFAULT cubre filas existentes (incl. los ~5 en producción).

### 5.2 Tabla `public.customer_success_events`

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | uuid PK | `gen_random_uuid()` |
| `project_id` | uuid FK → `implementation_projects` ON DELETE CASCADE | |
| `author_user_id` | uuid FK → `profiles` ON DELETE RESTRICT | |
| `event_type` | text | CHECK touchpoint / ajuste_producto / incidencia / nota |
| `title` | text NOT NULL | ≤ 200 chars (validar en API) |
| `body` | text | nullable |
| `occurred_at` | timestamptz NOT NULL | default `now()` |
| `created_at` / `updated_at` | timestamptz | |

Índices: `(project_id, occurred_at DESC)`, `(event_type)`.

### 5.3 Rollback / riesgo

- Rollback: `DROP TABLE customer_success_events`; `DROP COLUMN` las tres columnas CS.
- Riesgo bajo: solo columnas nuevas con default; no toca lógica del Kanban.
- Aplicar vía script de migración del backend o MCP `apply_migration` cuando el usuario lo pida (no en brainstorm).

---

## 6) API

**Router:** `routers/admin_customer_success.py`  
**Service:** `services/customer_success.py`  
**Prefijo:** `/admin/customer-success`  
**Auth:** mismo cookie/JWT admin + `assert_section_action(ctx, "customer_success", ...)`.

| Endpoint | Permiso | Comportamiento |
|----------|---------|----------------|
| `POST /list` | view | Solo `current_milestone = 'in_production'`. Filtros: `estado_salud`, `event_type` (existe ≥1 evento), `q` nombre/schema. Incluir último evento resumido. |
| `POST /get` | view | Detalle + eventos ordenados `occurred_at DESC`. 404 si no está en producción. |
| `POST /update-status` | edit | Patch `estado_salud` y/o `estado_pago`; set `cs_updated_at = now()`. |
| `POST /events/create` | edit | Crea evento; valida enums y title. |
| `POST /events/update` | edit | Edita campos del evento. |
| `POST /events/delete` | edit | Hard delete. |

**RBAC (`core/admin_permissions.py` + FE `permissions-types.ts`):**

- Agregar `"customer_success"` a `ADMIN_SECTIONS`.
- `_apply_base_matrix`: si `"implementaciones" in areas` → `view`+`edit` en `customer_success`.
- `_sudo_sections` / founders: incluir la sección.
- Actualizar tests de matriz de permisos.

---

## 7) Frontend

| Pieza | Ubicación |
|-------|-----------|
| Nav + tipos | `admin-sidebar.tsx`, `permissions-types.ts`, `app/admin/page.tsx` |
| Sección | `components/admin/customer-success-section.tsx` |
| Detalle | `components/admin/customer-success-detail.tsx` (o panel dentro de section) |
| Tipos | `lib/admin/customer-success-types.ts` |
| Proxy | Solo si el patrón del admin lo requiere (`app/api/admin/...`); hoy muchos llaman backend vía `adminFetch` directo |

**Lista:** tabla — Cliente | Salud | Pago | Último evento | Actualizado CS.  
**Detalle:** selects salud/pago (edit) + timeline + form “Agregar evento”.  
**Visual:** misma línea que Implementaciones (Select, badges, skeleton, toast). Sin Kanban.

---

## 8) Plan de prueba en CI/CD

| Check | Repo | Qué |
|-------|------|-----|
| Unit / service | backend | Filtro list solo `in_production`; update-status setea `cs_updated_at`; create event valida tipo; permisos sección nueva en matriz |
| Tests permisos | backend | `test_admin_permissions.py` incluye `customer_success` |
| Lint / typecheck | backoffice | `tsc` / ESLint en archivos nuevos |
| Gap | — | No E2E Playwright admin obligatorio en v1; smoke manual alcanza para merge |

Checks existentes del PR deben quedar verdes.

---

## 9) Plan de prueba humana (antes del PR)

**Servicios**

```bash
# Terminal 1 — backend
cd backend-supabase && source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — backoffice (puerto 3000 — Maps)
cd product-management-app
BACKEND_URL=http://localhost:8000 npm run dev
```

**Precondición:** migración `99` aplicada en el entorno que usa el backend local; usuario staff con área `implementaciones` (o sudo).

**Checklist**

1. Login `/admin` → aparece **Customer Success** en sidebar.
2. Staff sin área implementaciones (si hay) no ve la sección.
3. Lista muestra solo clientes en `in_production` (contrastar con Kanban).
4. Filtrar por `estado_salud` y por `event_type`.
5. Abrir detalle → cambiar salud y pago → refresca badge en lista.
6. Crear evento de cada tipo → aparece en timeline con autor/fecha.
7. Editar y borrar un evento.
8. Proyecto en hito anterior a producción: no aparece en list; get → 404.
9. Sin errores de consola / toast de error inesperado.

---

## 10) Criterios de aceptación

- [ ] Staff con permiso ve sección Customer Success y lista de clientes en producción.
- [ ] Puede actualizar `estado_salud` y `estado_pago` manualmente.
- [ ] Puede crear/listar/editar/borrar eventos con los 4 tipos.
- [ ] Filtros por salud y tipo de evento funcionan.
- [ ] Misma puerta RBAC que el resto del admin (sección dedicada).
- [ ] No hay lógica de facturación ni jobs de cobranza.

---

## 11) Referencias

- Inventario S1: `docs/producto/inventario-features-casos-negocio.md`
- Kanban: `components/admin/projects-section.tsx`, `routers/admin_projects.py`, `sql/47_implementation_projects.sql`
- Permisos: `core/admin_permissions.py`, `sql/50_admin_permissions.sql`, SPEC-011 / 046
- Spec checklist US: `docs/specs/011-admin-implementaciones-checklist-user-stories.md`
