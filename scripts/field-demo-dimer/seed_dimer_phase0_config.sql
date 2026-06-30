-- Fase 0: config tenant dimer — demo seguimiento tareas/objetivos
-- Ejecutar en Supabase. Ver scripts/field-demo-dimer/README.md

UPDATE public.distribuidoras
SET sales_assistant_enabled = true,
    metadata = COALESCE(metadata, '{}'::jsonb) || '{
      "field_combo_ventana_dias": 120,
      "field_combo_delta_unidades": 1,
      "field_combo_max_items": 3,
      "field_combo_top_n": 3,
      "field_puntos_por_sku_default": 10,
      "field_bonus_completitud_default": 20,
      "field_default_dias_reactivar": 45
    }'::jsonb
WHERE schema_name = 'dimer';
