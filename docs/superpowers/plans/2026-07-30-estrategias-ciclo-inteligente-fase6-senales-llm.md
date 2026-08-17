# Estrategias ciclo — Fase 6: Señales inteligentes + LLM escribe HSM (Opción A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Con `intelligence_config.signals` activo, el ciclo N+1 resuelve contexto (estacionalidad, calendario, clima, nearby), el LLM genera el body de plantillas Meta por cohort, Template Ops las crea y **espera APPROVED** antes de despachar; cleanup diario borra HSM viejos en Meta dejando footprint.

**Architecture:** Signal Resolver (lectura) → enriquece input del LLM Template Writer → `template_spec` con `components` + `signals_context` → Template Ops create/poll (ya existe stub) → ciclo `templates_pending` hasta APPROVED → Dispatcher. Planner sigue decidiendo cohorts; LLM no decide presupuesto ni pausas.

**Tech stack:** backend-supabase (asyncpg, httpx, OpenAI), Meta Graph message_templates, Nager.Date, OpenWeatherMap, Google Places (server), backoffice Next.js, Supabase `cvlbietibaaehgeimxgw`.

**Repos / ramas**

| Repo | Rama (misma del epic — un PR por repo) |
|------|------|
| `backend/` | `feat/estrategias-ciclo-schema` |
| `backoffice/` | `feat/estrategias-ciclo-ui` |
| `platform/` | `feat/estrategias-ciclo-inteligente` |

**Orden merge:** backend (migración + resolvers + LLM + template_ops real) → backoffice (Calendario UI + quitar “Próximamente”).

---

## Wait hasta APPROVED (diseño)

```
Vie: Planner crea variants status=draft + template_spec (body LLM)
     Template Ops: POST Meta → status=pending, ciclo → templates_pending
Cada 6 h: poll Graph GET template by name
     → APPROVED: meta_status=approved; materializar dispatches reserved
     → REJECTED: meta_status=rejected; pausar cohort; reporte
Timeout (ej. 72h PENDING): tratar como rejected parcial; no bloquear otros cohorts
```


**Ya existe:** `ensure_variants_for_cycle`, ciclo `templates_pending`, cleanup >14d stub.  
**Falta:** create real Meta (no promote seed), poll real, wire LLM body, no despachar pending.

---

## Cleanup de plantillas viejas (diseño)

Job diario `template_cleanup` (ya esqueleto en `estrategias_template_ops.cleanup_unused_variants`):

1. Variants `approved`, `remote_deleted_at IS NULL`, `last_used_at < now()-14d`
2. Sin dispatches `reserved`/`pending`
3. `DELETE` Meta by name + soft local `deleted_remote` + conservar `footprint` (copy + signals usados)
4. No borrar plantilla **seed** de la estrategia (`estrategias.meta_plantilla_id`)

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/sql/89_estrategias_calendar_events.sql` | Tablas calendario public + tenant |
| `backend/services/estrategias_signals.py` | Resolver 4 señales + cache |
| `backend/services/estrategias_llm_template.py` | LLM → body/components HSM |
| `backend/services/estrategias_template_ops.py` | Create/poll Meta real; no seed-promote en Opción A |
| `backend/services/estrategias_planner_rules_v1.py` | Llamar signals + LLM al materializar specs |
| `backend/routers/calendar_events.py` | CRUD + import Nager |
| `backoffice/components/strategy-calendar-modal.tsx` | UI Calendario |
| `backoffice/.../estrategias` page | Botón Calendario |
| `docs/specs/026-...md` | Decisiones Opción A (ya actualizado) |

Env vars (Railway, globales): `OPENAI_API_KEY`, `OPENWEATHER_API_KEY`, `GOOGLE_PLACES_API_KEY` (server). Nager sin key.

---

### Task 1: Migración calendario

**Files:**
- Create: `backend/sql/89_estrategias_calendar_events.sql`
- Apply via MCP Supabase

- [ ] **Step 1: SQL**

```sql
-- public.suplai_calendar_events (country_code, name, event_date, source nager|manual, ...)
-- {schema}.distribuidora_calendar_events (name, event_date, kind holiday|commercial|custom, ...)
-- public.distribuidoras.calendar_country_code TEXT DEFAULT 'AR'
```

- [ ] **Step 2: apply_migration** + verificar `demo`

---

### Task 2: Signal resolver + tests

**Files:**
- Create: `backend/services/estrategias_signals.py`
- Create: `backend/tests/test_estrategias_signals.py`

- [ ] **Step 1: TDD** — estacionalidad YoY vs fallback 7d; calendario ventana ±7d; clima/nearby con httpx mock
- [ ] **Step 2: Implementar** respetando `intelligence_config.signals` (skip si false)
- [ ] **Step 3: pytest** verde

---

### Task 3: LLM template writer

**Files:**
- Create: `backend/services/estrategias_llm_template.py`
- Create: `backend/tests/test_estrategias_llm_template.py`

- [ ] **Step 1: TDD** — con signals mock, output `components` BODY válido Meta + nombre único `estr_{id}_c{cycle}_{reason}_{hash6}`
- [ ] **Step 2: Prompt** con constraints categoría MARKETING/UTILITY, sin vars inventadas de más, idioma ES-AR
- [ ] **Step 3: Fallback** si no hay OPENAI: template_spec sin create Meta (status skipped / keep seed) + log

---

### Task 4: Template Ops real create + poll

**Files:**
- Modify: `backend/services/estrategias_template_ops.py`
- Modify: `backend/routers/plantillas_meta.py` (helper interno create/poll/delete si falta)
- Modify: tests template ops

- [ ] **Step 1:** Replace `_default_create_template` seed-promote with Graph create using `template_spec.components`
- [ ] **Step 2:** Poll pending → approved/rejected via list-by-name
- [ ] **Step 3:** On all non-excluded cohorts approved (or rejected/timeout handled), allow dispatch job
- [ ] **Step 4:** Cleanup never deletes `estrategias.meta_plantilla_id` seed

---

### Task 5: Planner wire signals + LLM

**Files:**
- Modify: `backend/services/estrategias_planner_rules_v1.py`

- [ ] **Step 1:** Load `intelligence_config` from estrategia
- [ ] **Step 2:** Per non-exclude cohort, `resolve_signals` (sample o agregado del cohort) → LLM → `template_spec`
- [ ] **Step 3:** Cap `MAX_TEMPLATES_PER_CYCLE`; tests existentes siguen verdes

---

### Task 6: API + UI Calendario

**Files:**
- Create: `backend/routers/calendar_events.py`
- Create: `backoffice/app/api/calendar-events/...`
- Create: `backoffice/components/strategy-calendar-modal.tsx`
- Modify: listado estrategias (botón Calendario)
- Modify: `strategy-intelligence-step.tsx` (sacar “Próximamente” o marcar “activo”)

- [ ] **Step 1:** CRUD tenant + import Nager por `calendar_country_code`
- [ ] **Step 2:** Modal calendario + selector país default AR
- [ ] **Step 3:** i18n ES/EN/PT

---

### Task 7: Env + docs + prueba humana

- [ ] Documentar env vars Railway
- [ ] Actualizar acceptance criteria SPEC-026
- [ ] Smoke local: estrategia recurrente con signals → draft→pending→(mock approved)→dispatch; cleanup dry-run

---

## Plan de prueba CI/CD

- `pytest` signals + llm_template + template_ops (httpx/OpenAI mocked)
- No hits reales a Meta/OpenWeather/Places en CI

## Plan de prueba humana

1. Backend `:8000` + backoffice `:3000`, tenant `demo`
2. Calendario → import feriados AR → crear evento custom
3. Nueva estrategia recurrente, paso Inteligencia: activar 4 signals
4. Simular close ciclo / forzar `plan_next_cycle` en staging
5. Ver variants `pending` → tras mock/poll `approved`
6. Confirmar cleanup no borra seed; sí marca footprint en variants viejas

## Fuera de alcance Fase 6

- 1 plantilla por PdV (`personalization_level=client`)
- Billing real Meta
- UI de monitoreo PENDING en detalle (nice-to-have; reporte ya menciona variants pausadas)
