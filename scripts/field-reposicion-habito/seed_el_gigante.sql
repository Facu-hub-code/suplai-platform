-- Seed localhost: tarea REPOSICION_HABITO — tenant el_gigante
-- Ejecutar en Supabase SQL Editor. Ver docs/specs/010-field-tarea-reposicion-habito.md §11

UPDATE public.distribuidoras
SET sales_assistant_enabled = true
WHERE schema_name = 'el_gigante';

ALTER TABLE el_gigante.field_task_templates
  DROP CONSTRAINT IF EXISTS field_task_templates_tipo_check;

ALTER TABLE el_gigante.field_task_templates
  ADD CONSTRAINT field_task_templates_tipo_check
  CHECK (tipo IN (
    'REACTIVAR_CLIENTE',
    'MEJORAR_MIX_RENTABLE',
    'CROSS_SELL_RENTABLE',
    'CROSS_SELL_COMBO',
    'REPOSICION_HABITO'
  ));

INSERT INTO el_gigante.field_task_templates (
  tipo, nombre, descripcion_template, puntos_default, criterio_json, activo
)
SELECT
  'REPOSICION_HABITO',
  'Reposición por hábito',
  '{cliente}: reposición urgente — {detalle_skus}',
  50,
  '{
    "source": "sales_engine_replenishment",
    "days_ahead_max": 2,
    "max_items": 5,
    "min_habit_purchases": 3,
    "puntos_por_sku": 10,
    "bonus_completitud": 20,
    "min_qty_per_sku": 1
  }'::jsonb,
  true
WHERE NOT EXISTS (
  SELECT 1 FROM el_gigante.field_task_templates WHERE tipo = 'REPOSICION_HABITO'
);

UPDATE el_gigante.productos SET tipo_venta = 'A' WHERE product_code = '295';
UPDATE el_gigante.productos SET tipo_venta = 'B' WHERE product_code = '318';
UPDATE el_gigante.productos SET tipo_venta = NULL WHERE product_code = '6';

DO $$
DECLARE
  v_cliente_id integer;
  v_pedido_id bigint;
  v_fechas date[] := ARRAY[
    CURRENT_DATE - 21,
    CURRENT_DATE - 14,
    CURRENT_DATE - 7
  ];
  v_fecha date;
  v_total numeric := 9720.00;
BEGIN
  SELECT id INTO v_cliente_id
  FROM el_gigante.clients
  WHERE phone_number = '5493587905250'
  LIMIT 1;

  IF v_cliente_id IS NULL THEN
    RAISE EXCEPTION 'Cliente Dulce Sorpresa no encontrado (5493587905250)';
  END IF;

  DELETE FROM el_gigante.items_pedido ip
  USING el_gigante.pedidos p
  WHERE ip.pedido_id = p.id
    AND p.cliente_id = v_cliente_id
    AND p.notas = 'SEED REPOSICION_HABITO test';

  DELETE FROM el_gigante.pedidos
  WHERE cliente_id = v_cliente_id
    AND notas = 'SEED REPOSICION_HABITO test';

  FOREACH v_fecha IN ARRAY v_fechas LOOP
    INSERT INTO el_gigante.pedidos (
      cliente_id, fecha, items, total, estado, notas
    ) VALUES (
      v_cliente_id,
      v_fecha + TIME '10:00:00',
      '[]'::jsonb,
      v_total,
      'confirmado',
      'SEED REPOSICION_HABITO test'
    )
    RETURNING id INTO v_pedido_id;

    INSERT INTO el_gigante.items_pedido (
      pedido_id, product_code, cantidad_solicitada, precio_unitario
    ) VALUES (
      v_pedido_id, '295', 2, v_total / 2
    );
  END LOOP;

  RAISE NOTICE 'Seed OK: cliente_id=%, 3 pedidos semanales SKU 295', v_cliente_id;

  -- Elegibilidad REPOSICION: pedidos_90d debe ser > 3
  INSERT INTO el_gigante.pedidos (cliente_id, fecha, items, total, estado, notas)
  VALUES (
    v_cliente_id,
    (CURRENT_DATE - 28) + TIME '10:00:00',
    '[]'::jsonb,
    5000,
    'confirmado',
    'SEED REPOSICION_HABITO test'
  );
  INSERT INTO el_gigante.items_pedido (pedido_id, product_code, cantidad_solicitada, precio_unitario)
  SELECT id, '295', 1, 5000
  FROM el_gigante.pedidos
  WHERE cliente_id = v_cliente_id AND notas = 'SEED REPOSICION_HABITO test'
  ORDER BY id DESC LIMIT 1;
END $$;
