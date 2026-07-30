# SPEC-026 — Estrategias: ciclo inteligente con presupuesto (diseño)

**Estado:** borrador de diseño (aprobado en brainstorming)  
**Fecha:** 2026-07-30  
**Repos:** `platform` (spec), implementación en `backend/` + `backoffice/`  
**Rama sugerida platform:** `feat/estrategias-ciclo-inteligente`

## Objetivo

Evolucionar el módulo de **estrategias comerciales** para que, una vez aceptado un presupuesto, un **bucle semanal automático** evalúe la performance de los envíos de plantillas Meta, genere un reporte (métricas + narrativa LLM), re-segmente el público por **estado comercial**, cree pocas plantillas nuevas, despache recontactos y repita hasta agotar el saldo — sin aprobación humana semanal.

El sistema debe quedar **desacoplado por capas** (contrato de estrategia, ledger, planner, template ops, dispatcher, outcomes, reports) para poder sumar después inteligencia de re-segmentación, más granularidad de plantillas e hiper-personalización 1:1 sin reescribir el sender ni el presupuesto.

## Contexto actual

Hoy una estrategia es un pegamento:

- ` {schema}.estrategias` → `grupo_id` + `meta_plantilla_id` + `agenda_id` + `followup_sequence_id` + promos N:M  
- Wizard 5 pasos: audiencia, plantilla, schedule, follow-up, promos  
- Agenda `puntual` | `recurrente` vía `agenda_sender`  
- Stats desde `envios_plantillas` + `meta_template_stats_daily`  
- **No hay** presupuesto, ciclos, planner, footprint post-delete, ni reportes semanales LLM/PDF  

Evidencia: `sql/60_add_estrategias.sql`, `routers/estrategias.py`, `components/create-strategy-modal.tsx`, `components/strategies-view.tsx`.

## Criterios de aceptación (v1)

- [ ] Al aceptar presupuesto en modo `recurrente_ciclo`, la estrategia corre sola hasta `budget_remaining ≤ 0` (o `activo=false`).
- [ ] Ciclo 0 usa plantilla seed + audiencia seed; ciclos siguientes usan plan del Planner.
- [ ] PdV con ≥3 envíos de la estrategia sin respuesta queda en estado `paused_no_reply` y no recibe más dispatches de esa estrategia.
- [ ] Por ciclo se crean como máximo N plantillas Meta nuevas (default 3–5, por estado); no 1 plantilla por cliente.
- [ ] Plantillas Meta no usadas >14 días se borran en Meta; queda `footprint` en BD.
- [ ] Cada viernes (configurable) hay reporte con: enviados, monto gastado estimado, replies/interacciones, carritos abiertos, pedidos cerrados + narrativa LLM; descargable en PDF.
- [ ] Si una variant queda `REJECTED` o timeout `PENDING`, se pausa ese estado/cohort del ciclo; el resto continúa; el reporte lo refleja.
- [ ] Cambiar `planner_version` no requiere cambios en Dispatcher ni Ledger.
- [ ] Programación puntual sigue siendo un shot con tope de gasto, sin bucle de recontacto inteligente.

---

## 1. Decisiones de diseño técnico (con el por qué)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Arquitectura | Pipeline por artefactos de ciclo (Strategy → Cycle → Cohorts → Variants → Dispatches → Outcomes → Report) | Permite enchufar inteligencia solo en el Planner | Extender monolíticamente `estrategias` (acopla todo) o event-bus puro (complejidad prematura) |
| Granularidad v1 | Plantillas / cohorts por **estado comercial** | Escala con límites Meta y evita explosión de HSM | 1 plantilla × PdV (futuro vía mismo schema) |
| Aprobación humana | Solo al **aceptar presupuesto**; bucle automático hasta $0 | El presupuesto es el kill switch operativo | Gate semanal de plantillas (fricción) |
| Contabilidad de costo | Estimado `cost_per_send_usd × envíos` al reserve/commit | Predecible y operable sin billing Meta en tiempo real | Solo factura real Meta; híbrido reconcile (v1.1+) |
| Meta PENDING/REJECTED | Pausar ese estado del ciclo; seguir con otros; alertar en reporte | No frena toda la estrategia ni gasta en fallback genérico silencioso | Esperar indefinido; fallback automático a seed |
| Cohorts vs `grupos` | Cohorts dinámicos por ciclo; **no** mutar el grupo seed | El grupo se reutiliza en otras features; re-segmentar ≠ editar CRM | Reescribir membresía del grupo cada viernes |
| LLM reporte vs Planner | Componentes separados | Narrar ≠ decidir; evita que el reporte “tome” presupuesto | Un solo LLM que decide y reporta |
| Cleanup Meta | Job diario + footprint en variant | Cumple límite de plantillas sin perder auditoría | Dejar plantillas eternas en WABA |
| Envío | Reutilizar camino `agenda_sender` / envío plantilla vía `estrategia_dispatches` | No duplicar integración Meta | Sender nuevo paralelo |
| Follow-up / promos | Sin cambio de modelo en v1 (siguen opcionales en wizard) | Fuera del critical path del ciclo | Rediseñar follow-up global (ver SPEC-047 backoffice) |

---

## 2. Alcance explícito

### Incluido (v1)

- Ampliar contrato de `estrategias` (budget, mode, planner_version, cost_per_send).
- Ledger de presupuesto (reserve / commit / release).
- Tablas de ciclo, cohorts, template variants (+ footprint), dispatches, member_state, cycle reports, cycle plans.
- Planner `rules_v1` (estados: seed, engaged_no_buy, cart_open, paused_no_reply, converted, reattempt).
- Template Ops (create/poll Meta) + cleanup >14d.
- Cycle close: metrics factuales + narrativa LLM + PDF descargable.
- Wizard: paso/bloque de presupuesto; bifurcación puntual vs recurrente_ciclo.
- UI detalle: listado de reportes semanales + download PDF.
- Jobs desacoplados (ver §5).

### Fuera de alcance (v1)

- Aprobación humana semanal de plantillas/tandas.
- Cobro real / reconcile con factura Meta.
- Hiper-personalización 1:1 en producción (`per_client_v1`).
- Mutación automática del `grupo` seed.
- Shadow mode LLM planner (candidata v1.1).
- Resolver SPEC-047 (follow-up per-estrategia) — independiente, puede paralelizarse después.
- Rediseño visual del PDF (layout mínimo aceptable).

---

## 3. Arquitectura (bounded contexts)

```text
Strategy (contrato)     política + budget + seed grupo/plantilla
        │
Budget Ledger           reserve / commit estimado; kill switch
        │
Cycle Runner            orquestador idempotente por (estrategia, week_start)
        │
   ┌────┴────┐
   │ Planner │  plug-in: rules_v1 → (futuro llm_segment / per_client)
   └────┬────┘
        │ escribe plan
Cohorts + Template specs
        │
Template Ops            Meta create/poll; footprint; cleanup remoto
        │
Dispatcher              dispatches + agenda_sender path
        │
Outcomes / member_state hechos (envíos, replies, carritos, pedidos)
        │
Report Store            metrics jsonb + narrative LLM + PDF
```

**Regla de oro:** el Planner solo produce cohorts + template_specs. Ledger no segmenta. Dispatcher no planea. Report LLM no decide el próximo ciclo.

---

## 4. Modelo de datos

### 4.1 Ampliar `{schema}.estrategias`

| Columna | Tipo | Notas |
|---------|------|--------|
| `mode` | text | `puntual` \| `recurrente_ciclo` (default compat: mapear desde agenda) |
| `budget_total_usd` | numeric | Presupuesto aceptado |
| `budget_remaining_usd` | numeric | Proyección; fuente de verdad = ledger |
| `cost_per_send_usd` | numeric | Estimado unitario |
| `planner_version` | text | default `rules_v1` |
| `budget_accepted_at` | timestamptz | null hasta aceptar |

Se mantienen: `grupo_id` (seed), `meta_plantilla_id` (seed), `agenda_id` (ciclo 0 / puntual), follow-up, promos.

### 4.2 Nuevas tablas (por schema tenant)

**`estrategia_budget_ledger`**

- `id`, `estrategia_id`, `cycle_id` nullable, `dispatch_id` nullable  
- `entry_type`: `allocate` \| `reserve` \| `commit` \| `release`  
- `amount_usd`, `created_at`, `meta jsonb`

**`estrategia_cycles`**

- `id`, `estrategia_id`, `week_start`, `week_end`  
- `status`: `planned` \| `templates_pending` \| `dispatching` \| `completed` \| `skipped_no_budget` \| `partial` \| `failed_plan`  
- timestamps; unique `(estrategia_id, week_start)`

**`estrategia_cohorts`**

- `id`, `cycle_id`, `reason_code`, `priority`, `exclude` bool  
- miembros: `estrategia_cohort_members (cohort_id, client_id)`  

**`estrategia_template_variants`**

- `id`, `cycle_id`, `template_spec jsonb`, `personalization_level`  
- `meta_plantilla_id` nullable, `meta_status`, `footprint jsonb`  
- `last_used_at`, `remote_deleted_at`

**`estrategia_dispatches`**

- `id`, `cycle_id`, `cohort_id`, `client_id`, `template_variant_id`  
- `status`, `reserved_cost_usd`, `agenda_id` nullable, link opcional a `envios_plantillas`

**`estrategia_member_state`**

- `(estrategia_id, client_id)` PK  
- `state`: `eligible` \| `engaged` \| `cart_open` \| `converted` \| `paused_no_reply`  
- `sends_without_reply`, `updated_at`

**`estrategia_cycle_reports`**

- `cycle_id` UNIQUE, `metrics jsonb`, `narrative text`, `pdf_storage_key` nullable, `model`, `prompt_version`, `created_at`

**`estrategia_cycle_plans`**

- `cycle_id`, `planner_version`, `input_hash`, `output jsonb`, `created_at`

### 4.3 Cleanup Meta ↔ footprint

1. Variant `approved`, `last_used_at < now()-14d`, sin dispatch pendiente.  
2. Asegurar `footprint` completo.  
3. DELETE en Meta; `meta_status=deleted_remote`.

---

## 5. Flujo temporal y jobs

### Semana tipo

| Momento | Acción |
|---------|--------|
| Dom–Jue | Dispatcher / follow-ups |
| Vie AM | Close: outcomes + metrics |
| Vie PM | Report LLM; Planner ciclo N+1 |
| Lun+ | Template Ops poll; reserve; dispatch APPROVED |

### Ciclo 0 (bootstrap)

Al aceptar presupuesto en `recurrente_ciclo`: cohort `seed_initial` = miembros del grupo; plantilla seed ya APPROVED; reserve + dispatch según agenda del wizard. Luego entra el bucle semanal.

### Jobs

| Job | Frecuencia | Rol |
|-----|------------|-----|
| `cycle_close_and_report` | Vie | metrics + LLM report |
| `cycle_plan_next` | post-report | Planner |
| `template_ops_poll` | */15–30 | Meta create/poll |
| `dispatch_reserved` | */15 | envíos reserved+approved |
| `template_cleanup` | diario | delete remoto + footprint |
| `budget_guard` | en reserve / open_cycle | no abrir si remaining ≤ 0 |

Fallo de LLM report **no** bloquea el plan del próximo ciclo (metrics sí obligatorias).

### Idempotencia

- Un solo cycle “abierto” por estrategia.  
- Jobs idempotentes por `(estrategia_id, week_start)`.  
- Al pausar estrategia o agotar budget: no nuevos open_cycle; dispatches ya reserved se pueden completar; no reserved no se envían.

---

## 6. Contrato del Planner

### Input (resumen)

`estrategia_id`, `cycle_id`, `planner_version`, seed audience, `member_states`, metrics previas, `budget_remaining`, `cost_per_send`, constraints (`max_templates_per_cycle`, `max_clients_per_cohort`, forbidden ids).

### Output (escrito a DB)

- `cohorts[]` con `reason_code`, `priority`, `client_ids`, `exclude`  
- `template_specs[]` con components, category, `personalization_level`, reason_codes asociados  
- `notes[]` para el reporte  

### Invariantes (orquestador)

1. Clientes enviables ⊆ seed (salvo allowlist futura).  
2. Ningún enviable en forbidden / exclude.  
3. `#template_specs ≤ max_templates_per_cycle`.  
4. Si `personalization_level=client` ⇒ un client por cohort.  
5. Prioridad respetada cuando el budget no cubre toda la cola.

### `rules_v1` (comportamiento)

| Condición | reason_code / efecto |
|-----------|----------------------|
| ≥3 envíos estrategia sin reply | `paused_no_reply` (exclude) |
| Reply / interacción sin pedido | `engaged_no_buy` + carrusel historial compra |
| Carrito abierto sin confirm | `cart_open` + carrusel items + CTA confirmar |
| Convertido (pedido en ventana) | `converted` (exclude) |
| Resto elegible | `reattempt` / reglas simples |
| Ciclo 0 | `seed_initial` + plantilla seed |

Plugins futuros: `llm_segment_v1`, `per_client_v1` — mismo shape; factory por `planner_version`.

---

## 7. UI

- Wizard: bloque presupuesto + `cost_per_send`; mode puntual vs recurrente_ciclo en programación.  
- Medio de pago: referencia al ya configurado en portafolio/tenant (no cobro in-wizard en v1).  
- Detalle estrategia: pestaña Ciclos/Reportes (lista, metrics, narrativa, PDF).  
- PDF: lazy on download o async al close; regenerable desde `metrics` + `narrative`.

---

## 8. Orden de implementación

Cross-repo: **migraciones backend → API/jobs → backoffice**.

| # | Entrega | Repo | Rama sugerida |
|---|---------|------|---------------|
| 1 | Migration tablas + columnas estrategia | `backend` | `feat/estrategias-ciclo-schema` |
| 2 | Ledger + budget_guard + modes | `backend` | misma o `feat/estrategias-budget-ledger` |
| 3 | Ciclo 0 bootstrap + dispatches | `backend` | `feat/estrategias-cycle0` |
| 4 | Planner `rules_v1` + template_ops + cleanup | `backend` | `feat/estrategias-planner-v1` |
| 5 | Close metrics + LLM report + PDF API | `backend` | `feat/estrategias-cycle-reports` |
| 6 | Wizard presupuesto + UI reportes | `backoffice` | `feat/estrategias-ciclo-ui` |
| 7 | (post-v1) shadow LLM planner | `backend` | TBD |

Este documento vive en `platform` (`feat/estrategias-ciclo-inteligente`).

---

## 9. Migración de base de datos

- **Sí hay migración** (backend `sql/NN_*.sql` por schemas activos, patrón `60_add_estrategias.sql`).  
- Alter `estrategias` + create tablas §4.2.  
- Backfill: estrategias existentes → `mode` según agenda ligada; `budget_*` null; sin ciclos hasta reconfiguración.  
- Índice unique `(estrategia_id, week_start)` en cycles.  
- Rollback: DROP tablas nuevas; DROP columnas nuevas (script inverso documentado en el SQL).  
- Riesgo: bajo si columnas nuevas nullable; no romper listados actuales.

---

## 10. Plan de prueba en CI/CD

- Unit: Planner `rules_v1` (paused_no_reply, cart_open, engaged_no_buy, invariants).  
- Unit: Ledger reserve/commit/release y corte por saldo.  
- Unit: orquestador status transitions + idempotencia `(estrategia_id, week_start)`.  
- Integration (mocked Meta): template_ops PENDING→APPROVED / REJECTED → partial.  
- Tests existentes de `estrategias` / `agenda_sender` siguen verdes.  
- Gap: cron real y LLM e2e no en CI — mock del client LLM; job functions invocables en test.

---

## 11. Plan de prueba humana (antes del PR de UI)

**Servicios**

- Backend: `uvicorn` en `8000`  
- Backoffice: puerto **`3000`** (`BACKEND_URL=http://localhost:8000`)  

**Tenant:** demo o sandbox con WABA de prueba / mocks si no hay Meta.

**Checklist**

1. Crear estrategia recurrente_ciclo con budget chico (ej. 5–10 USD) y cost_per_send conocido.  
2. Verificar ciclo 0: envíos seed, ledger allocate/reserve/commit, remaining baja.  
3. Simular 3 no-replies en un PdV → siguiente plan lo excluye.  
4. Simular reply sin pedido → cohort engaged + spec carrusel.  
5. Simular carrito abierto → cohort cart_open.  
6. Forzar variant REJECTED → ese estado pausado; otros envían; reporte lo menciona.  
7. Viernes/job manual close → metrics + narrativa + PDF download.  
8. Cleanup: variant unused >14d (o clock fake) → delete Meta + footprint presente.  
9. Agotar budget → no nuevos cycles; estrategia `skipped_no_budget` / inactiva recurrente.  
10. Estrategia puntual: un solo cycle, sin planner de recontacto.

---

## 12. Riesgos y open points

| Riesgo | Mitigación |
|--------|------------|
| Demora aprobación Meta | Poll + partial; no bloquear otros estados |
| Estimado ≠ costo real | Documentar; reconcile en v1.1 |
| Calidad copy `rules_v1` | Specs con templates controlados; LLM solo en reporte v1 |
| Volumen de members N:M | Índices; batches en dispatcher |
| “Medio de pago portafolio” | v1 = referencia config tenant; definir tabla/fuente en implementación con producto |

**Default asumido:** día de reporte = viernes; ajustable por tenant en implementación.

---

## 13. Relación con otros specs

- Backoffice `047-estrategias-followup-per-estrategia.md` — follow-up scoped; complementario.  
- Agenda / plantillas Meta existentes — se reutilizan, no se reemplazan.  
- Inventario features: “Estrategias comerciales” se actualizará cuando v1 shippee.

---

## Historial de decisiones de producto (brainstorming)

1. Granularidad v1 = por estado (A).  
2. Sin gate semanal humano; solo aceptación de presupuesto.  
3. Costo = estimado por envío (A).  
4. PENDING/REJECTED = pausar estado, continuar resto, reportar.  
5. Arquitectura desacoplada por artefactos de ciclo (enfoque 2).  

## Estado de implementación

- **Fase 1 (schema + ledger + accept-budget):** plan `docs/superpowers/plans/2026-07-30-estrategias-ciclo-inteligente-fase1.md` ejecutado en backend `feat/estrategias-ciclo-schema` (2026-07-30). Migration `86_…`, ledger, `POST …/accept-budget` atómico. Ver handoff Fase 2+ en ese plan.
- **Fase 2 (cycle 0 + dispatcher):** plan `docs/superpowers/plans/2026-07-30-estrategias-ciclo-inteligente-fase2.md` (2026-07-30). `open_cycle_0` al aceptar `recurrente_ciclo`; dispatches `reserved`/`deferred`; job `estrategias_dispatch` */15; `POST …/open-cycle-0`.
- **Fase 3 (planner + template ops):** plan `docs/superpowers/plans/2026-07-30-estrategias-ciclo-inteligente-fase3.md`. `rules_v1`, `close_cycle` → plan next, template ops promote draft→approved, cleanup >14d.
- **Fase 4 (cycle reports + PDF):** plan `docs/superpowers/plans/2026-07-30-estrategias-ciclo-inteligente-fase4.md` (2026-07-30). Metrics al close → `estrategia_cycle_reports`; narrativa LLM (fallback sin key); PDF lazy (`report.pdf`); `GET …/cycles`, `…/report`, `…/report.pdf`. Sin reporte general de plataforma.
- **Fase 5 (UI backoffice):** plan `docs/superpowers/plans/2026-07-30-estrategias-ciclo-inteligente-fase5.md` (2026-07-30). Wizard presupuesto + mode; proxies accept-budget/cycles/report/PDF; panel Ciclos/Reportes en cards. Rama `feat/estrategias-ciclo-ui`.
