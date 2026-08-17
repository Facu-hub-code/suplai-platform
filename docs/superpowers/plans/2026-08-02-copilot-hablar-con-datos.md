# Copilot hablar-con-datos Implementation Plan

> **For agentic workers:** Execute task-by-task. Spec: `docs/specs/027-copilot-hablar-con-datos.md`.

**Goal:** Copilot full-page bajo Estrategias, siempre on, híbrido tools + NL→SQL, UI texto+tabla.

**Architecture:** Reusar `POST /{schema}/copilot/chat`. Backend: tools canónicas + `nl_sql_query`. Front: nav sibling de Estrategias + `CopilotChatView`; sacar panel lateral.

**Tech Stack:** FastAPI/asyncpg, OpenAI tools, Next.js backoffice.

## Global Constraints

- Sin `copilot_enabled` ni env kill-switch.
- Pooler 6543, `statement_cache_size=0`, pools mínimos.
- Schema tenant siempre por auth/path.
- Respuesta UI: solo text + table.

---

## Task 1: Backend NL-SQL + gates off

**Files:**
- Create: `backend-supabase/services/copilot/nl_sql.py`
- Create: `backend-supabase/tests/test_copilot_nl_sql.py`
- Modify: `services/copilot/tools.py`, `orchestrator.py`, `routers/copilot.py`, `persistence.py` (si aplica)

- [ ] Tests validate_sql
- [ ] Implement nl_sql module
- [ ] Wire tool + remove geo/agenda from specs
- [ ] Remove tenant/global disable gates from chat path

## Task 2: Backoffice full-page chat

**Files:**
- Create: `components/copilot/CopilotChatView.tsx`
- Modify: `app/page.tsx`, `contexts/distribuidora-config-context.tsx`, simplify `CopilotArtifacts` / panel usage
- Remove usage of `CopilotShell` from page

- [ ] Nav item under Estrategias
- [ ] Full-page ChatGPT-like view
- [ ] Render only text + table
- [ ] Always show (no copilotEnabled)

## Task 3: Smoke

- [ ] Backend unit tests pass
- [ ] Front typechecks / lint on touched files
