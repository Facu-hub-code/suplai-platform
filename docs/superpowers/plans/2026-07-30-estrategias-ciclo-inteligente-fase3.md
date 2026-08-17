# Estrategias ciclo inteligente — Fase 3 (Planner rules_v1 + Template Ops) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or executing-plans.

**Goal:** Tras cerrar un ciclo (o on-demand), el Planner `rules_v1` escribe cohorts del próximo ciclo según `member_state` / outcomes simples; Template Ops crea/poll plantillas Meta nuevas; cleanup borra en Meta variants unused >14d dejando footprint.

**Architecture:** `estrategias_planner_rules_v1` produce `PlannerOutput` → persistido en `estrategia_cycle_plans` + cohorts/variants del **nuevo** cycle. `estrategias_template_ops` create/poll Meta. `estrategias_template_cleanup` job diario. Sin LLM report (Fase 4).

**Tech Stack:** backend FastAPI, Meta Graph via existing `routers/plantillas_meta` / `meta_api_service`, pytest.

**Repo / rama:** `backend-supabase` `feat/estrategias-ciclo-schema`  
**Docs:** `platform` `feat/estrategias-ciclo-inteligente`

## Global Constraints

- No commits salvo pedido (este turno el usuario ya pidió commits de fases previas; Fase 3 commits al cerrar si pide).
- TDD; YAGNI: no PDF/LLM report; no UI.
- Max templates per cycle default **4**.
- PENDING/REJECTED → cohorts de esa variant quedan sin reserve (partial); no bloquea otros.
- `paused_no_reply` si `sends_without_reply >= 3`.

## Tasks

### Task 1: Planner `rules_v1` (TDD)
- Create `services/estrategias_planner_rules_v1.py`
- `plan_next_cycle(schema, tenant_id, estrategia_id, previous_cycle_id | None) -> dict`
- Rules: paused_no_reply (exclude), engaged_no_buy, cart_open (stubs queries), reattempt, seed only on cycle0 (already done)
- Persist plan JSON + create next `estrategia_cycles` week+7 + cohorts/members/variants specs (`meta_status=draft`)
- Tests with monkeypatch member_state + fake SQL

### Task 2: Wire close → plan
- `close_cycle(schema, cycle_id)` sets status `completed`, then calls planner for next week if `can_open_cycle`
- Optional `POST /{id}/cycles/{cycle_id}/close`
- Hook: after dispatch job, if no reserved left for cycle → auto-close (simple check)

### Task 3: Template Ops create/poll
- `ensure_variants_for_cycle(schema, cycle_id)` — for draft variants, create in Meta (reuse plantillas_meta create path), set pending; poll approved/rejected
- Job `run_estrategias_template_ops_job` */15
- On approved: allow reserve+dispatch (extend dispatcher to only send approved variants — already seed approved)

### Task 4: Cleanup >14d
- `cleanup_unused_variants(schema)` — approved, last_used_at < now()-14d, no reserved/pending dispatch → delete Meta + footprint + deleted_remote
- Daily cron

### Task 5: Docs
- Update SPEC-026 estado + plan fase3 file

## Out of scope
- LLM narrative / PDF
- Real purchase history carousel SQL perfection (stub SKU list ok)
- Backoffice UI
