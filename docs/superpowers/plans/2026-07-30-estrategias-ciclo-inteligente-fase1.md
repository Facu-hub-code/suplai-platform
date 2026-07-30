# Estrategias ciclo inteligente — Fase 1 (schema + ledger) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persistir el contrato de presupuesto/ciclo en BD y exponer un Budget Ledger con `allocate` / `reserve` / `commit` / `release` + `budget_guard`, sin Planner ni envíos todavía.

**Architecture:** Ampliar `{schema}.estrategias` y crear tablas de ciclo del SPEC-026. El ledger es la fuente de verdad del saldo; `budget_remaining_usd` en estrategias es proyección actualizada en cada movimiento. Jobs de cycle/planner quedan para Fase 2+.

**Tech Stack:** PostgreSQL (migraciones `backend/sql/`), FastAPI + asyncpg (`backend-supabase`), pytest asyncio, Pydantic models.

**Spec:** `platform/docs/specs/026-estrategias-ciclo-inteligente-presupuesto.md`

**Repos / ramas**

| Repo | Path | Rama |
|------|------|------|
| platform | `suplai-platform/` | `feat/estrategias-ciclo-inteligente` (spec + este plan) |
| backend | `backend-supabase/` | `feat/estrategias-ciclo-schema` (crear desde `origin/main`) |

## Global Constraints

- Nunca implementar en `main` / `master`.
- Pooler: puerto `6543`; `statement_cache_size=0`; pools locales `min_size=1`, `max_size=2`.
- Commits solo si el usuario lo pide explícitamente (omitir pasos Commit del plan hasta entonces; dejar el working tree listo).
- No aplicar migración a producción/staging sin pedido explícito; el SQL debe ser idempotente y revisable en PR.
- TDD: test que falle → implementación mínima → test verde.
- YAGNI Fase 1: no Template Ops, no Planner, no LLM report, no UI backoffice.

## File map (Fase 1)

| File | Responsibility |
|------|----------------|
| `backend/sql/86_estrategias_ciclo_inteligente.sql` | DDL: columnas estrategia + tablas ciclo/ledger/… |
| `backend/models/estrategias_ciclo.py` | Pydantic: ledger entries, accept-budget payload, cycle enums |
| `backend/services/estrategias_budget_ledger.py` | allocate / reserve / commit / release / remaining / guard |
| `backend/services/estrategias_service.py` | Extender list/get/create para campos budget/mode; endpoint accept budget |
| `backend/routers/estrategias.py` | `POST /{id}/accept-budget`, campos en responses |
| `backend/models/estrategias.py` | Ampliar Create/Update/Response |
| `backend/tests/test_estrategias_budget_ledger.py` | Unit ledger |
| `backend/tests/test_estrategias_service.py` | Ajustar mocks a columnas nuevas |
| `backend/core/tenancy.py` | Opcional: no exigir tablas ciclo en REQUIRED_TABLES aún (lazy) |

---

### Task 1: Migration SQL `86_estrategias_ciclo_inteligente.sql`

**Files:**
- Create: `backend-supabase/sql/86_estrategias_ciclo_inteligente.sql`
- Test: validación manual `psql` dry-read / review en PR (sin apply automático)

**Interfaces:**
- Produces: tablas y columnas del SPEC-026 §4 listos para el ledger service

- [ ] **Step 1: Crear el archivo de migración** (patrón DO $$ + loop schemas activos como `60_add_estrategias.sql`)

Contenido mínimo obligatorio:

1. `ALTER TABLE {schema}.estrategias` ADD COLUMN IF NOT EXISTS:
   - `mode TEXT NOT NULL DEFAULT 'puntual'`
   - CHECK `mode IN ('puntual', 'recurrente_ciclo')` (constraint nombrado, idempotente)
   - `budget_total_usd NUMERIC(12,4)`
   - `budget_remaining_usd NUMERIC(12,4)`
   - `cost_per_send_usd NUMERIC(12,4)`
   - `planner_version TEXT NOT NULL DEFAULT 'rules_v1'`
   - `budget_accepted_at TIMESTAMPTZ`

2. Crear tablas IF NOT EXISTS:
   - `estrategia_budget_ledger` (`id`, `estrategia_id` FK CASCADE, `cycle_id` nullable, `dispatch_id` nullable, `entry_type` CHECK allocate|reserve|commit|release, `amount_usd NUMERIC(12,4) NOT NULL`, `meta jsonb`, `created_at`)
   - `estrategia_cycles` + unique `(estrategia_id, week_start)` + status CHECK
   - `estrategia_cohorts` + `estrategia_cohort_members`
   - `estrategia_template_variants`
   - `estrategia_dispatches`
   - `estrategia_member_state` PK `(estrategia_id, client_id)`
   - `estrategia_cycle_reports`
   - `estrategia_cycle_plans`

3. Comentario de rollback al tope del archivo (DROP tablas + DROP columnas).

4. `cycle_id` / `dispatch_id` en ledger: FK opcionales creadas **después** de las tablas cycles/dispatches, o sin FK en v1 si el orden complica — preferir FK con `ON DELETE SET NULL`.

- [ ] **Step 2: Self-check del SQL**

Run: `rg -n "CREATE TABLE|ADD COLUMN|CHECK" backend-supabase/sql/86_estrategias_ciclo_inteligente.sql | head -80`  
Expected: aparecen las 8+ tablas y las columnas de budget.

- [ ] **Step 3: Commit** (solo si el usuario lo pide)

```bash
cd backend-supabase
git add sql/86_estrategias_ciclo_inteligente.sql
git commit -m "$(cat <<'EOF'
feat(estrategias): add ciclo inteligente schema migration

EOF
)"
```

---

### Task 2: Pydantic models del ciclo / budget

**Files:**
- Create: `backend-supabase/models/estrategias_ciclo.py`
- Modify: `backend-supabase/models/estrategias.py`
- Test: `backend-supabase/tests/test_estrategias_ciclo_models.py`

**Interfaces:**
- Produces:
  - `AcceptBudgetRequest(budget_total_usd: Decimal, cost_per_send_usd: Decimal, mode: Literal["puntual","recurrente_ciclo"])`
  - `LedgerEntryType = Literal["allocate","reserve","commit","release"]`
  - `EstrategiaResponse` ampliado con `mode`, `budget_total_usd`, `budget_remaining_usd`, `cost_per_send_usd`, `planner_version`, `budget_accepted_at`

- [ ] **Step 1: Write failing test**

```python
# tests/test_estrategias_ciclo_models.py
from decimal import Decimal
from models.estrategias_ciclo import AcceptBudgetRequest

def test_accept_budget_rejects_non_positive():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AcceptBudgetRequest(
            budget_total_usd=Decimal("0"),
            cost_per_send_usd=Decimal("0.05"),
            mode="recurrente_ciclo",
        )

def test_accept_budget_ok():
    m = AcceptBudgetRequest(
        budget_total_usd=Decimal("30"),
        cost_per_send_usd=Decimal("0.05"),
        mode="recurrente_ciclo",
    )
    assert m.budget_total_usd == Decimal("30")
```

- [ ] **Step 2: Run test — expect FAIL (module missing)**

```bash
cd backend-supabase && source venv/bin/activate
pytest tests/test_estrategias_ciclo_models.py -v
```

Expected: `ModuleNotFoundError` o import error.

- [ ] **Step 3: Implement models**

```python
# models/estrategias_ciclo.py
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, Field

LedgerEntryType = Literal["allocate", "reserve", "commit", "release"]
EstrategiaMode = Literal["puntual", "recurrente_ciclo"]

class AcceptBudgetRequest(BaseModel):
    budget_total_usd: Decimal = Field(..., gt=0, max_digits=12, decimal_places=4)
    cost_per_send_usd: Decimal = Field(..., gt=0, max_digits=12, decimal_places=4)
    mode: EstrategiaMode = "recurrente_ciclo"
```

Ampliar `EstrategiaResponse` / `EstrategiaUpdate` en `models/estrategias.py` con campos opcionales de budget/mode.

- [ ] **Step 4: Run tests — PASS**

```bash
pytest tests/test_estrategias_ciclo_models.py -v
```

---

### Task 3: Budget Ledger service (TDD)

**Files:**
- Create: `backend-supabase/services/estrategias_budget_ledger.py`
- Test: `backend-supabase/tests/test_estrategias_budget_ledger.py`

**Interfaces:**
- Consumes: `query_schema` / `get_connection` de `core.db`
- Produces (async functions):

```python
async def allocate(schema: str, estrategia_id: int, amount_usd: Decimal, *, meta: dict | None = None) -> dict
async def reserve(schema: str, estrategia_id: int, amount_usd: Decimal, *, cycle_id: int | None = None, dispatch_id: int | None = None) -> dict
async def commit(schema: str, estrategia_id: int, amount_usd: Decimal, *, cycle_id: int | None = None, dispatch_id: int | None = None) -> dict
async def release(schema: str, estrategia_id: int, amount_usd: Decimal, *, cycle_id: int | None = None, dispatch_id: int | None = None) -> dict
async def get_remaining(schema: str, estrategia_id: int) -> Decimal
async def can_open_cycle(schema: str, estrategia_id: int) -> bool  # remaining > 0 and activo and budget_accepted_at set
```

Reglas:
- `allocate`: setea `budget_total_usd`, `budget_remaining_usd = amount`, insert entry allocate; falla si ya hay `budget_accepted_at`.
- `reserve`: si `remaining < amount` → HTTP 409 `INSUFFICIENT_BUDGET`; insert reserve; `remaining -= amount`.
- `commit`: insert commit (auditoría); **no** vuelve a restar si ya se reservó (el saldo ya bajó en reserve). Si se usa commit sin reserve previo en el mismo flujo, documentar: Fase 1 asume reserve-then-commit donde commit solo registra; **alternativa simple Fase 1:** solo `reserve` baja saldo, `commit` es no-op de saldo + log, `release` sube saldo.
- `release`: `remaining += amount` (tope: no superar `budget_total_usd`).
- Actualizar `estrategias.budget_remaining_usd` en la misma transacción que el insert del ledger.

- [ ] **Step 1: Write failing tests** (monkeypatch `query_schema` o fake conn)

Casos mínimos:
1. `allocate` OK → remaining == total  
2. `allocate` segunda vez → 409/400  
3. `reserve` OK → remaining baja  
4. `reserve` > remaining → 409 `INSUFFICIENT_BUDGET`  
5. `release` tras reserve → remaining recupera  
6. `can_open_cycle` False si remaining 0 o sin accept  

- [ ] **Step 2: Run — FAIL**

```bash
pytest tests/test_estrategias_budget_ledger.py -v
```

- [ ] **Step 3: Implement `estrategias_budget_ledger.py`**

Usar una transacción (`get_connection` + `async with conn.transaction()`) por operación. SQL con `{schema}` vía `query_schema` o formateo seguro ya usado en el repo.

- [ ] **Step 4: Run — PASS**

```bash
pytest tests/test_estrategias_budget_ledger.py -v
```

---

### Task 4: `accept_budget` en service + router

**Files:**
- Modify: `backend-supabase/services/estrategias_service.py`
- Modify: `backend-supabase/routers/estrategias.py`
- Modify: `backend-supabase/tests/test_estrategias_service.py`
- Modify: `backend-supabase/tests/test_estrategias_router.py` (si aplica)

**Interfaces:**
- Consumes: `allocate` del ledger
- Produces: `async def accept_budget(schema, tenant_id, estrategia_id, body: AcceptBudgetRequest) -> dict`
- HTTP: `POST /{schema}/estrategias/{id}/accept-budget`

Comportamiento:
1. Verificar estrategia existe y `activo`.
2. Setear `mode`, `cost_per_send_usd`, `planner_version` default.
3. Llamar `allocate(...)`.
4. Setear `budget_accepted_at = now()`.
5. Devolver estrategia actualizada (incluir campos budget en SELECT list/get).

- [ ] **Step 1: Extender SELECTs** `_LIST_ESTRATEGIAS_SQL` / `_GET_ESTRATEGIA_SQL` con columnas nuevas (COALESCE mode `'puntual'`).

- [ ] **Step 2: Test service `accept_budget`** con monkeypatch.

- [ ] **Step 3: Implement service + ruta**.

- [ ] **Step 4: Ajustar tests existentes** que arman dicts de estrategia — agregar keys nuevas con defaults para que no rompan.

- [ ] **Step 5: Run suite estrategias**

```bash
pytest tests/test_estrategias_service.py tests/test_estrategias_router.py tests/test_estrategias_budget_ledger.py tests/test_estrategias_ciclo_models.py -v
```

Expected: all PASS.

---

### Task 5: Documentar handoff Fase 2 en el plan/spec (sin código)

**Files:**
- Modify: `suplai-platform/docs/specs/026-estrategias-ciclo-inteligente-presupuesto.md` (sección historial: “Fase 1 plan ready”)
- O nota al final de este plan (abajo)

- [ ] **Step 1: Anotar** que Fase 2 = cycle 0 bootstrap + dispatches; Fase 3 = planner rules_v1 + template_ops; Fase 4 = reports/PDF; Fase 5 = UI wizard.

---

## Fase 1 — estado de entrega (2026-07-30)

Implementado en `backend-supabase` rama `feat/estrategias-ciclo-schema` (working tree; sin commit hasta pedido humano):

| Entrega | Path |
|---------|------|
| Migration | `sql/86_estrategias_ciclo_inteligente.sql` |
| Models | `models/estrategias_ciclo.py` + campos en `models/estrategias.py` |
| Ledger | `services/estrategias_budget_ledger.py` |
| Accept API | `accept_budget` (TX atómica) + `POST /{schema}/estrategias/{id}/accept-budget` |
| Tests | `test_estrategias_ciclo_models.py`, `test_estrategias_budget_ledger.py` (+ ajustes service/router) — **39 passed** |

Pendiente operativo Fase 1: aplicar migración en entorno de prueba (solo con OK humano) y commit/PR.

## Fase 2 — estado de entrega (2026-07-30)

Implementado en la misma rama `feat/estrategias-ciclo-schema`:

| Entrega | Path |
|---------|------|
| Cycle 0 | `services/estrategias_cycle_service.py` (`open_cycle_0`) |
| Hook accept | `accept_budget` → `open_cycle_0` si `recurrente_ciclo` (lazy import) |
| Dispatcher | `services/estrategias_dispatch_service.py` + cron `estrategias_dispatch` */15 |
| HTTP retry | `POST /{schema}/estrategias/{id}/open-cycle-0` |
| Tests | `test_estrategias_cycle_service.py`, `test_estrategias_dispatch_service.py` (+ hooks/router) |

Dispatch statuses: `reserved` → `sent` \| `failed`; sin saldo al armar → `deferred`.

## Fase 3+ (siguiente)

1. **Planner `rules_v1` + Template Ops + cleanup** — member_state transitions, variants Meta, footprint >14d.
2. **cycle_close metrics + LLM report + PDF**.
3. **Backoffice** wizard presupuesto + pestaña ciclos/reportes.

## Spec coverage (self-review Fase 1)

| Spec item | Task |
|-----------|------|
| Columnas budget/mode en estrategias | T1 |
| Tablas ciclo/ledger/… | T1 |
| Ledger estimado allocate/reserve/… | T3 |
| budget_guard / can_open_cycle | T3 |
| Accept presupuesto API | T4 |
| Planner / Meta / PDF / UI | Explicitamente fuera (Fase 2+) |

## Placeholder scan

Sin TBD en steps de código. Apply remoto de migración queda fuera a propósito (PR review).

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-30-estrategias-ciclo-inteligente-fase1.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — un subagente por task, review entre tasks  
2. **Inline Execution** — ejecutar en esta sesión con checkpoints  

**Which approach?**
