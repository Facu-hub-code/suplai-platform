# Copilot evals — manifest y casos golden por tenant

Suite de evaluación regresiva para **Suplai Copilot** (backend). Complementa `tests/test_copilot_sales_metrics.py` con casos end-to-end por tenant.

**Spec:** [docs/specs/045-suplai-copilot-evals-ci.md](../../backend-supabase/docs/specs/045-suplai-copilot-evals-ci.md)  
**Epic:** [docs/specs/014-suplai-copilot-supervisor-ritmo-ventas.md](../docs/specs/014-suplai-copilot-supervisor-ritmo-ventas.md)

---

## Estructura

```
scripts/copilot-evals/
  README.md                 # este archivo
  manifest.json             # tenants + lista de casos
  cases/
    demo/
      dow_global.json
      dow_by_vendedor.json
      followups_after_dow.json
      thought_steps_present.json
      top_products_regression.json
    gonzales/
      dow_global.json
      top_products_regression.json
    _template/
      case.template.json
```

---

## Ejecutar localmente

Desde `backend-supabase/`:

```bash
export COPILOT_ENABLED=true
export COPILOT_EVAL_FORCE_HEURISTIC=1
export COPILOT_EVAL_MANIFEST="../suplai-platform/scripts/copilot-evals/manifest.json"
python -m pytest tests/copilot_evals/ -m copilot_eval -v
```

Requisitos:

- `SUPABASE_DB_URL` apuntando al pooler (**6543**), no 5432.  
- Tenant con `copilot_enabled: true` y pedidos confirmados suficientes.

---

## Alta de un tenant

1. Crear carpeta `cases/{schema}/`.  
2. Copiar `_template/case.template.json` y completar `input` / `expect`.  
3. Añadir bloque en `manifest.json`:

```json
{
  "schema": "mi_tenant",
  "enabled": true,
  "critical": false,
  "min_confirmed_orders": 20,
  "cases": ["dow_global", "top_products_regression"]
}
```

4. Correr evals localmente.  
5. Marcar `critical: true` solo cuando el tenant es gate de CI estable (ej. `demo`).

---

## Casos incluidos (MVP epic 014)

| id | Qué valida |
|----|------------|
| `dow_global` | Tool `sales_by_day_of_week`, chart 7 barras, KPI líder |
| `dow_by_vendedor` | Desglose `by_vendedor`, tabla |
| `followups_after_dow` | ≥2 follow-ups con ids esperados |
| `thought_steps_present` | ≥3 thought steps en stream |
| `top_products_regression` | No regresión Fase 0 |
| `compare_periods_regression` | No regresión Fase 1 |

---

## Política CI

- Job `copilot-evals` en `backend-supabase/.github/workflows/ci.yml`.  
- Falla si cualquier caso con `"critical": true` en el caso o tenant falla.  
- Skip (warn) si `min_confirmed_orders` no se cumple.

---

## Añadir un caso nuevo

1. Crear JSON en `cases/{tenant}/{id}.json`.  
2. Referenciar `id` en `manifest.json` → `cases[]`.  
3. Preferir graders determinísticos (`tools`, `artifacts`, `follow_ups`) — no evaluar prosa LLM.  
4. PR en platform (manifest) + backend (graders si hace falta nuevo assert).
