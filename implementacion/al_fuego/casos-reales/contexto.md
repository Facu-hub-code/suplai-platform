# Al Fuego — casos reales B2C (Occasion Planner)

Tenant carnicería boutique en Valle Escondido (Córdoba). Primer flujo B2C: cliente final pide armar un asado por WhatsApp.

## Perfil

- **Modo:** cliente final (`--suite real` sin `--seller`)
- **Tool clave:** `plan_occasion_bundle` (opt-in)
- **Escenario V1:** `asado`

## Expectativas

1. El agente **no** inventa kilos en prosa: debe invocar `plan_occasion_bundle`.
2. La propuesta incluye ≥3 líneas (carne + achuras/provoleta/carbón según config).
3. Debe mencionar disclaimer de peso variable si aplica.

## Prerrequisitos BD

- `reglas_negocio.occasion_planners.enabled = true`
- `tools_habilitadas.plan_occasion_bundle = true`
- Tags de catálogo cargados (fase 01.1 + `phase-04-occasion-planner-tags.csv`)
