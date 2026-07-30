# Estrategias ciclo inteligente — Fase 2 (Cycle 0 + Dispatcher) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Al aceptar presupuesto en `recurrente_ciclo`, abrir **ciclo 0** con cohort `seed_initial`, variant apuntando a la plantilla seed, **reserve** por destinatario según `cost_per_send_usd`, y un job `dispatch_reserved` que envía via `send_template_message` (mismo camino que agenda).

**Architecture:** Nuevos servicios desacoplados — `estrategias_cycle_service` (abrir ciclo + materializar seed) y `estrategias_dispatch_service` (enviar reserved). El ledger Fase 1 no cambia de contrato. Sin Planner `rules_v1` ni Template Ops Meta create (eso es Fase 3): ciclo 0 usa plantilla seed ya APPROVED.

**Tech Stack:** FastAPI, asyncpg, pytest asyncio, `services/whatsapp_send.send_template_message`, reuso de `_GROUP_CLIENTS_SQL` / lógica de params de `agenda_sender`.

**Spec:** `platform/docs/specs/026-estrategias-ciclo-inteligente-presupuesto.md` §3.3 / §5 ciclo 0  
**Depende de:** Fase 1 en `feat/estrategias-ciclo-schema` (ledger + accept_budget + migration 86)

**Repo / rama:** `backend-supabase` → continuar `feat/estrategias-ciclo-schema` (Fase 1 aún uncommitted)

## Global Constraints

- Nunca en `main`.
- Commits solo si el usuario lo pide.
- Pooler `6543` / `statement_cache_size=0` / pools locales min1 max2.
- TDD por task.
- YAGNI: no LLM report, no Meta create/poll de variants nuevas, no member_state machine completa (solo upsert `eligible` al seed), no UI.
- Un solo cycle “abierto” (`status` not in completed|skipped_no_budget|failed_plan) por estrategia.
- `can_open_cycle` debe ser True antes de open; si False → `skipped_no_budget` o no crear.
- Dispatch statuses Fase 2: `pending` | `reserved` | `sent` | `failed` | `deferred` (deferred = sin saldo al armar cola).
- Al enviar OK: `ledger.commit` + status `sent`; al fallar envío: `ledger.release` + status `failed`.

## File map

| File | Responsibility |
|------|----------------|
| `services/estrategias_cycle_service.py` | `open_cycle_0`, idempotency by week_start, seed cohort/variant/dispatches |
| `services/estrategias_dispatch_service.py` | `process_reserved_dispatches(schema, limit=…)`, send + commit/release |
| `services/estrategias_service.py` | Tras `accept_budget` si `mode=recurrente_ciclo` → `open_cycle_0` |
| `routers/estrategias.py` (opcional) | `POST /{id}/cycles/open-0` para reintento manual / tests |
| `tests/test_estrategias_cycle_service.py` | TDD open cycle 0 |
| `tests/test_estrategias_dispatch_service.py` | TDD send reserved |
| Optional cron entry | Wire `run_estrategias_dispatch_job` like agenda (solo si ya hay patrón de jobs en main) |

---

### Task 1: `open_cycle_0` service (TDD)

**Files:**
- Create: `services/estrategias_cycle_service.py`
- Test: `tests/test_estrategias_cycle_service.py`
- Consumes: `can_open_cycle`, `reserve` from ledger; `_GROUP_CLIENTS_SQL` pattern from `estrategias_service` (import shared SQL or duplicate minimal SELECT of client ids for grupo)

**Interfaces:**

```python
async def open_cycle_0(schema: str, tenant_id: str, estrategia_id: int) -> dict:
    """
    Returns {cycle_id, status, dispatched_reserved: int, deferred: int, ...}
    Idempotent: if cycle for (estrategia_id, week_start) exists, return it without duplicating.
    """
```

`week_start` = Monday of current week in `America/Argentina/Buenos_Aires` (same TZ family as agenda).

**Steps inside one TX where possible:**

1. Load estrategia: must have `budget_accepted_at`, `mode='recurrente_ciclo'`, `activo`, `grupo_id`, `meta_plantilla_id`, `cost_per_send_usd`, `agenda_id` optional.
2. If not `await can_open_cycle(...)`: insert cycle `skipped_no_budget` OR return without inserts if already skipped — prefer create cycle row with that status once.
3. Insert `estrategia_cycles` status `planned` (or `dispatching` when reserves done).
4. Insert cohort `reason_code='seed_initial'`, `priority=0`, `exclude=false` + members = client ids from grupo (reuse group membership SQL).
5. Insert `estrategia_template_variants`: `meta_plantilla_id` = seed, `meta_status='approved'`, `personalization_level='state'`, `template_spec={"source":"seed"}`.
6. Upsert `estrategia_member_state` `(estrategia_id, client_id)` state=`eligible` for members.
7. For each client in priority order (stable sort by client_id):
   - Try `reserve(cost_per_send)` with `cycle_id` + later `dispatch_id`
   - On success: insert dispatch `status='reserved'`, `reserved_cost_usd=cost`, `template_variant_id`, `cohort_id`, `agenda_id` from estrategia
   - On 409 INSUFFICIENT_BUDGET: insert remaining as `deferred` **without** reserve, stop further reserves (or continue marking deferred) — stop reserving further.
8. Set cycle status `dispatching` if any reserved; `skipped_no_budget` if zero clients or zero reserved and remaining was 0.

**Idempotency:** UNIQUE `(estrategia_id, week_start)` — on conflict, SELECT existing and return (do not re-reserve).

- [ ] **Step 1: Write failing tests** (monkeypatch DB / ledger)
  - open_cycle_0 creates cycle + cohort seed + N reserved when budget covers N
  - budget covers only K of M → K reserved, M-K deferred
  - second call same week → same cycle_id, no double reserve
  - can_open_cycle False → skipped_no_budget

- [ ] **Step 2: RED** → implement → **GREEN**

- [ ] **Step 3: Do NOT commit**

---

### Task 2: Hook `accept_budget` → `open_cycle_0`

**Files:**
- Modify: `services/estrategias_service.py` `accept_budget`
- Modify: `tests/test_estrategias_service.py`

**Behavior:**

After successful accept TX + `get_estrategia`, if `mode == "recurrente_ciclo"`:
```python
try:
    await open_cycle_0(schema, tenant_id, estrategia_id)
except Exception:
    logger.exception(...)  # do not fail accept_budget response — budget already accepted
```

For `mode == "puntual"`: no open_cycle_0 in Fase 2 (puntual cycle can be Fase 2.1 / defer).

- [ ] **Step 1: Test** accept recurrente mocks `open_cycle_0` called once; puntual not called
- [ ] **Step 2: Implement hook**
- [ ] **Step 3: Suite accept + cycle tests green**
- [ ] **Step 4: Do NOT commit**

---

### Task 3: `process_reserved_dispatches` (TDD)

**Files:**
- Create: `services/estrategias_dispatch_service.py`
- Test: `tests/test_estrategias_dispatch_service.py`

**Interfaces:**

```python
async def process_reserved_dispatches(schema: str, *, limit: int = 50) -> dict:
    """Pick dispatches status=reserved, send template, commit or release. Returns counts."""

async def run_estrategias_dispatch_job() -> None:
    """Iterate active schemas (get_valid_schemas) and process_reserved_dispatches each."""
```

**Per dispatch:**

1. Load client phone (`clients.phone_number`), template name from `public.meta_plantillas` via variant.meta_plantilla_id, variable_columns / dynamic params — **reuse helpers from agenda_sender** if importable without circular imports; else minimal copy of param build for seed templates.
2. Call `send_template_message(...)` (mock in tests).
3. On success: `commit(reserved_cost)`, set dispatch `sent`, set `envio_plantilla_id` if available / link session; bump `member_state.sends_without_reply` (+1) optional Fase 2.
4. On failure: `release(reserved_cost)`, set `failed`, store error in updated_at/meta if column exists — use logger; no new migration unless needed (skip error column; log only).
5. Skip if estrategia `activo=false` — release and mark failed or leave reserved? Prefer **leave reserved** until reactivated OR release+deferred. Spec: reserved already taken — **send if reserved**. Keep sending reserved even if strategy paused mid-flight (plata ya reserved). If `activo=false` before reserve, no new reserves (cycle service).

**Tests:**

- mock send ok → commit called, status sent
- mock send fail → release called, status failed
- empty queue → zeros

- [ ] Implement TDD RED→GREEN
- [ ] Do NOT commit

---

### Task 4: Optional HTTP + job wire

**Files:**
- Modify: `routers/estrategias.py` — `POST /{id}/open-cycle-0` (admin/retry) calling `open_cycle_0`
- Find how `run_agenda_job` is scheduled (main.py / cron router) and add `run_estrategias_dispatch_job` alongside if trivial; else document manual invoke for Fase 2 and defer cron to ops.

- [ ] Grep `run_agenda_job` registration
- [ ] Wire if same pattern exists in <20 LOC; else note in report “cron deferred”
- [ ] Test router open-cycle-0 smoke
- [ ] Do NOT commit

---

### Task 5: Update docs handoff

**Files:**
- Modify: `platform/docs/superpowers/plans/2026-07-30-estrategias-ciclo-inteligente-fase1.md` OR new plan status section
- Modify: SPEC-026 estado implementación — Fase 2 done checklist

- [ ] Document dispatch statuses + that cycle 0 runs on accept
- [ ] List Fase 3 next (planner rules_v1)

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| Ciclo 0 seed_initial + plantilla seed | T1 |
| Reserve por envío / defer si no alcanza | T1 |
| Accept presupuesto arranca bucle | T2 |
| Dispatcher envía reserved | T3 |
| Idempotencia week_start | T1 |
| Planner / Meta create / PDF | Out of scope |

## Self-review notes

- No Placeholder TBD in steps.
- `puntual` mode cycle deferred intentionally.
- Param building for Meta templates is the riskiest integration — prefer importing from `agenda_sender` private helpers only if stable; otherwise minimal path: templates with 0–1 `nombre` variable like existing tests.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-07-30-estrategias-ciclo-inteligente-fase2.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — same as Fase 1  
2. **Inline Execution**

**Which approach?**
