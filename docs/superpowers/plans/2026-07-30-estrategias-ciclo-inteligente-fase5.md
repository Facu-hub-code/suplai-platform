# Estrategias ciclo inteligente — Fase 5 (UI backoffice)

> **For agentic workers:** ejecutar en `product-management-app` rama `feat/estrategias-ciclo-ui`. Backend APIs ya existen (Fases 1–4).

**Goal:** Wizard con presupuesto + mode; detalle con ciclos/reportes y download PDF.

## Design (SPEC-026 §7)

| Pieza | Comportamiento |
|-------|----------------|
| Schedule step | Tras tipo agenda: campos `budget_total_usd`, `cost_per_send_usd`. Mode = `puntual` si agenda puntual; `recurrente_ciclo` si recurrente. Nota: medio de pago = portafolio tenant (texto). |
| Create finish | `POST /estrategias` → `POST …/accept-budget` (si budget > 0). Fallo accept-budget: toast warning (estrategia creada sin ciclo). |
| Edit | Si `budget_accepted_at`: budget read-only. Si no: permitir accept-budget al guardar. |
| Cards | Badge mode + remaining budget si aplica. Botón “Ciclos / Reportes”. |
| Panel reportes | Lista cycles; metrics; narrativa; download `report.pdf`. |

## Tasks

### T1 Proxies Next
- `POST /api/estrategias/[id]/accept-budget`
- `GET /api/estrategias/[id]/cycles`
- `GET /api/estrategias/[id]/cycles/[cycleId]/report`
- `GET /api/estrategias/[id]/cycles/[cycleId]/report.pdf` (stream PDF)

### T2 Wizard
- State budget fields; validate > 0 on finish when enabling budget
- Wire accept-budget after create/update

### T3 StrategyCyclesPanel
- Dialog/Sheet from card; fetch cycles; show report detail; PDF download

### T4 i18n + list badges
- Keys ES/EN/PT en `language-context`
- Card badges for mode/budget

### T5 Docs
- SPEC-026 estado Fase 5; commit backoffice + platform

## Out of scope
- Cobro in-wizard / Stripe
- Reporte general plataforma
- Redesign visual del wizard
