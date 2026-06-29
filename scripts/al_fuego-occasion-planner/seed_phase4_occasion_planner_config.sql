-- Fase 4 Occasion Planner — config tenant al_fuego
-- Plantilla asado (backend build_asado_template) + business_mode hybrid + tool opt-in.

BEGIN;

UPDATE public.distribuidoras
SET
  metadata = COALESCE(metadata, '{}'::jsonb) || '{"business_mode": "hybrid"}'::jsonb,
  tools_habilitadas = COALESCE(tools_habilitadas, '{}'::jsonb) || '{"plan_occasion_bundle": true}'::jsonb,
  reglas_negocio = COALESCE(reglas_negocio, '{}'::jsonb) || $occasion$
{
  "occasion_planners": {
    "enabled": true,
    "default_scenario_id": "asado",
    "scenarios": {
      "asado": {
        "label": "Asado para N personas",
        "active": true,
        "parameters_schema": {
          "adults": {"type": "integer", "default": 4, "min": 1, "max": 30},
          "children": {"type": "integer", "default": 0, "min": 0, "max": 20},
          "wants_achuras": {"type": "boolean", "default": true}
        },
        "demand_rules": [
          {"slot": "carne_principal", "grams_per_adult": 500, "grams_per_child": 250},
          {"slot": "achuras", "ratio_of_slot": {"base": "carne_principal", "ratio": 0.25}},
          {"slot": "provoletas", "ratio_of_slot": {"base": "carne_principal", "ratio": 0.12}},
          {"slot": "carbon", "ratio_of_slot": {"base": "carne_principal", "ratio": 0.75}}
        ],
        "slots": [
          {
            "id": "carne_principal",
            "label": "Cortes principales",
            "selection": {
              "strategy": "distribute_by_tag_ratio",
              "tags_all": ["Carnes"],
              "tags_any": ["Asado"],
              "ratios": [
                {"tag": "Asado", "weight": 0.40},
                {"tag": "Vacio", "weight": 0.30},
                {"tag": "Entraña", "weight": 0.15},
                {"tag": "Picaña", "weight": 0.15}
              ],
              "max_skus": 4
            }
          },
          {
            "id": "achuras",
            "label": "Achuras",
            "selection": {
              "strategy": "pick_by_tags",
              "tags_any": ["Chorizo", "Morcilla", "Molleja", "Chinchulín"],
              "max_skus": 4
            }
          },
          {
            "id": "provoletas",
            "label": "Provoletas",
            "selection": {
              "strategy": "pick_by_tags",
              "tags_any": ["Provoleta", "Provolone"],
              "max_skus": 2
            }
          },
          {
            "id": "carbon",
            "label": "Carbón o leña",
            "selection": {
              "strategy": "pick_by_tags",
              "tags_any": ["Carbón", "Leña"],
              "max_skus": 2
            }
          }
        ],
        "pipeline": [
          "calculate_demand",
          "select_products_by_tags",
          "distribute_by_ratio",
          "filter_stock",
          "estimate_prices",
          "apply_disclaimers"
        ],
        "disclaimers": {
          "variable_weight": true,
          "template": "Precios aproximados; el peso real de los cortes puede variar y se confirma al armar el pedido."
        }
      }
    }
  }
}
$occasion$::jsonb
WHERE schema_name = 'al_fuego';

COMMIT;

-- Verificación
-- SELECT metadata->>'business_mode', tools_habilitadas->>'plan_occasion_bundle',
--        reglas_negocio->'occasion_planners'->>'enabled'
-- FROM public.distribuidoras WHERE schema_name = 'al_fuego';
