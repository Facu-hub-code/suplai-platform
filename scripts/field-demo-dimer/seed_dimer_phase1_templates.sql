-- Fase 1: plantillas de tareas — tenant dimer (espejo el_gigante)

INSERT INTO dimer.field_task_templates (
  tipo, nombre, descripcion_template, puntos_default, criterio_json, activo
)
SELECT * FROM (VALUES
  (
    'REACTIVAR_CLIENTE',
    'Reactivar cliente en riesgo',
    'Reactivar a {cliente} — {dias} días sin pedir',
    100,
    '{
      "top_n": 3, "max_items": 3, "ventana_dias": 120, "delta_unidades": 1,
      "puntos_por_sku": 10, "bonus_completitud": 20, "dias_sin_compra_min": 45,
      "categorias_elegibles": ["CHURN_RISK", "LOST"]
    }'::jsonb,
    true
  ),
  (
    'MEJORAR_MIX_RENTABLE',
    'Mejorar mix rentable',
    'Recomprar {combo} en {cliente}',
    50,
    '{
      "top_n": 3, "max_items": 3, "ventana_dias": 120, "delta_unidades": 1,
      "puntos_por_sku": 10, "bonus_completitud": 20
    }'::jsonb,
    true
  ),
  (
    'REPOSICION_HABITO',
    'Reposición por hábito',
    '{cliente}: reposición urgente — {detalle_skus}',
    50,
    '{
      "source": "sales_engine_replenishment", "max_items": 5, "days_ahead_max": 2,
      "puntos_por_sku": 10, "min_qty_per_sku": 1, "bonus_completitud": 20,
      "min_habit_purchases": 3
    }'::jsonb,
    true
  ),
  (
    'CROSS_SELL_RENTABLE',
    'Venta cruzada rentable (standby)',
    'Combo sugerido para {cliente}',
    50,
    '{"source": "sales_engine", "standby": true}'::jsonb,
    false
  ),
  (
    'CROSS_SELL_COMBO',
    'Vender combo sugerido (legacy)',
    'Vender combo en {cliente}',
    50,
    '{"source": "sales_engine", "requiere_todos": true, "min_qty_per_sku": 1}'::jsonb,
    false
  )
) AS v(tipo, nombre, descripcion_template, puntos_default, criterio_json, activo)
WHERE NOT EXISTS (
  SELECT 1 FROM dimer.field_task_templates t WHERE t.tipo = v.tipo
);
