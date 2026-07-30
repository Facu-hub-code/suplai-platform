# Estrategias ciclo inteligente — Fase 4 (Cycle reports: metrics + LLM + PDF)

> **For agentic workers:** executing-plans / SDD. Scope **solo reporte por ciclo de estrategia** — no reporte general de plataforma.

**Goal:** Al cerrar un ciclo, materializar metrics factuales, narrativa LLM (inyectable/mockeable) y PDF descargable; APIs para listar/ver/descargar sin mezclar con agenda Slack reports.

**Architecture:**
1. `compute_cycle_metrics(schema, cycle_id)` → jsonb (envíos, gastado_estimado, replies, carts, orders)
2. `generate_cycle_narrative(metrics, context)` → text (OpenAI opcional; fallback template si no hay key)
3. `build_estrategia_cycle_report_pdf_bytes(...)` → fpdf2 (patrón `copilot_report_pdf`)
4. Persist `estrategia_cycle_reports`; PDF regenerable on download (no storage obligatorio)
5. Hook en `close_cycle` **antes** de plan_next; fallo LLM no bloquea close/plan

**Repo:** `backend-supabase` `feat/estrategias-ciclo-schema`  
**Docs:** `suplai-platform` plan + SPEC-026 estado

## Tasks

### T1 Metrics (TDD)
- `services/estrategias_cycle_reports.py` — `compute_cycle_metrics`
- Counts from dispatches (sent/failed/deferred), ledger commit sum, replies (best-effort: member_state engaged / envios with reply stub), carts/orders in week window for cohort clients
- Test with monkeypatch query_schema

### T2 Narrative + PDF (TDD)
- `generate_cycle_narrative` injectable `llm_fn`
- `build_estrategia_cycle_report_pdf_bytes` using fpdf
- Fallback narrative without API key

### T3 Persist + wire close_cycle
- `upsert_cycle_report` after status update, before plan_next
- Errors logged, close continues

### T4 HTTP API
- `GET /{schema}/estrategias/{id}/cycles` — list cycles + report summary
- `GET /{schema}/estrategias/{id}/cycles/{cycle_id}/report`
- `GET /{schema}/estrategias/{id}/cycles/{cycle_id}/report.pdf` — application/pdf

### T5 Docs + commit
- SPEC-026 estado Fase 4; plan file; commit backend + platform

## Out of scope
- Reporte semanal general on-demand
- Backoffice UI (Fase 5)
- Slack delivery
