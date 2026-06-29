# Occasion Planner B2C — seed tenant `al_fuego` (spec 016 fase 4)

Configura tags complementarios, `reglas_negocio.occasion_planners`, `metadata.business_mode` y habilita `plan_occasion_bundle`.

## Prerrequisitos

- Tenant `al_fuego` cargado (fases 01–07 del manifest).
- Tags de catálogo base desde fase 01.1 (`Carnes`, `Asado`, `Vacio`, etc.) — ya presentes.
- Backend con endpoints Occasion Planner desplegado (`feat/occasion-planners-config` → prod).
- Agente con tool `plan_occasion_bundle` desplegado (`feat/occasion-planner-tool` → prod).

## Orden de ejecución

En Supabase SQL Editor o vía MCP `execute_sql`:

```text
seed_phase4_occasion_planner_tags.sql
seed_phase4_occasion_planner_config.sql
```

## Verificación

```bash
chmod +x scripts/al_fuego-occasion-planner/smoke_al_fuego_occasion_planner.sh

# Producción (requiere backend desplegado)
./scripts/al_fuego-occasion-planner/smoke_al_fuego_occasion_planner.sh

# Local
BACKEND_URL=http://127.0.0.1:8000 ./scripts/al_fuego-occasion-planner/smoke_al_fuego_occasion_planner.sh
```

Esperado: `ready_for_runtime: true` y cobertura > 0 en los 4 slots (`carne_principal`, `achuras`, `provoletas`, `carbon`).

## E2E conversacional (fase 5 / manifest 09)

Tras deploy del agente:

```bash
python scripts/fase-09-e2e/healthcheck_schema.py --schema al_fuego
python scripts/fase-09-e2e/test_agent_e2e.py --schema al_fuego --suite real --sequential
```

Casos en `implementacion/al_fuego/casos-reales/`.

## Rollback

```sql
-- scripts/al_fuego-occasion-planner/seed_phase4_rollback.sql
```

## Referencias

- Spec índice: `docs/specs/016-occasion-planner-b2c.md`
- Mapping tags: `implementacion/al_fuego/outputs/phase-04-occasion-planner-tags.csv`
