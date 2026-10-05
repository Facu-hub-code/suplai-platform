# Carpetas de plantillas, Kanban y filtros — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El supervisor agrupa plantillas en carpetas con un porcentaje del día, entra al Kanban desde el navbar y llega a Conversaciones y al wizard ya filtrados.

**Architecture:** Tablas en `public` y un router nuevo en el backend. El porcentaje se calcula al leer, con los envíos de hoy. El backoffice consume ese API y el `implementation_kinds` del config. El agente no cambia.

**Tech Stack:** FastAPI, asyncpg, Next.js, React.

## Global Constraints

- Objetivo de carpeta: `abrir_conversacion` o `abrir_con_decisor`, uno solo.
- Porcentaje del día en curso, timezone del tenant. Cero envíos → null, la UI muestra "—".
- El mismo envío cuenta en cada carpeta que tenga la plantilla.
- Etiquetas no cambian el numerador.
- Wizard ordena por `suplai_reply_pct` de 30 días, no por el porcentaje de hoy.
- Si `implementation_kinds` incluye `prospectos`, gana prospectos. Solo `long_tail` → clientes y Kanban de ventas. Sin proyecto → default de hoy.
- Backoffice local en el puerto 3000. Backend en 8000.
- El humano mergea. Orden: backend, después backoffice.

---

### Task 1: Migración y servicio

**Files:**
- Create: `backend-supabase/sql/142_plantilla_carpetas.sql`
- Create: `backend-supabase/services/plantilla_carpetas_service.py`
- Create: `backend-supabase/routers/plantilla_carpetas.py`
- Modify: `backend-supabase/main.py`
- Modify: `backend-supabase/routers/distribuidoras_config.py`
- Test: `backend-supabase/tests/test_plantilla_carpetas.py`

- [ ] Tablas de carpetas, items, etiquetas e items de etiqueta.
- [ ] CRUD y porcentaje del día. Plantilla de otro tenant rechazada.
- [ ] `implementation_kinds` en el GET del config.
- [ ] Tests de porcentaje, defaults y rechazo de objetivo.

### Task 2: Backoffice

**Files:**
- Create: proxies `app/api/plantilla-carpetas/**` y `app/api/plantilla-etiquetas/**`
- Create: `lib/implementation-kind.ts`, `lib/prospeccion/rank-templates.ts`
- Create: `components/conversations/kanban-section.tsx`, `components/meta-templates/template-folders-panel.tsx`
- Modify: modal de plantillas, alta de plantilla, `app/page.tsx`, filtros, wizard

- [ ] Carpetas y etiquetas en el modal.
- [ ] Navbar Kanban. Conversaciones sin el tablero.
- [ ] Filtros cerrados y default según el tipo.
- [ ] Wizard con recomendada.
