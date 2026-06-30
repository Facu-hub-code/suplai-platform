-- Fase 3: historial de pedidos demo — tenant dimer
-- Marca: notas = 'SEED DEMO FIELD DIMER'

DELETE FROM dimer.items_pedido ip
USING dimer.pedidos p
WHERE ip.pedido_id = p.id
  AND p.notas LIKE 'SEED DEMO FIELD DIMER%';

DELETE FROM dimer.pedidos
WHERE notas LIKE 'SEED DEMO FIELD DIMER%';

DO $$
DECLARE
  v_pedido_id integer;
  v_total numeric;
  v_sku text;
  v_fecha date;
  rec record;
BEGIN
  -- A) REACTIVAR: historial tipo A
  FOR rec IN
    SELECT * FROM (VALUES
      (29, CURRENT_DATE - 120, ARRAY['12572647','110111091']::text[]),
      (29, CURRENT_DATE - 105, ARRAY['12572647']::text[]),
      (29, CURRENT_DATE - 90,  ARRAY['110111091']::text[]),
      (28, CURRENT_DATE - 118, ARRAY['12572647','770695']::text[]),
      (28, CURRENT_DATE - 103, ARRAY['12572647']::text[]),
      (28, CURRENT_DATE - 88,  ARRAY['770695']::text[]),
      (32, CURRENT_DATE - 115, ARRAY['110111091']::text[]),
      (32, CURRENT_DATE - 100, ARRAY['110111091']::text[]),
      (2,  CURRENT_DATE - 125, ARRAY['110077','134054']::text[]),
      (2,  CURRENT_DATE - 110, ARRAY['110077']::text[]),
      (2,  CURRENT_DATE - 95,  ARRAY['134054']::text[]),
      (13, CURRENT_DATE - 122, ARRAY['12510386']::text[]),
      (13, CURRENT_DATE - 107, ARRAY['12510386']::text[]),
      (24, CURRENT_DATE - 119, ARRAY['12616158']::text[]),
      (24, CURRENT_DATE - 104, ARRAY['12616158']::text[])
    ) AS t(cliente_id, fecha, skus)
  LOOP
    v_total := 8000 + (rec.cliente_id * 100);
    INSERT INTO dimer.pedidos (cliente_id, fecha, items, total, estado, notas, is_mock)
    VALUES (
      rec.cliente_id,
      rec.fecha + TIME '10:00:00',
      '[]'::jsonb,
      v_total,
      'confirmado',
      'SEED DEMO FIELD DIMER',
      true
    )
    RETURNING id INTO v_pedido_id;

    FOREACH v_sku IN ARRAY rec.skus LOOP
      INSERT INTO dimer.items_pedido (pedido_id, product_code, cantidad_solicitada, precio_unitario, is_mock)
      VALUES (v_pedido_id, v_sku, 2, 4000, true);
    END LOOP;
  END LOOP;

  -- B) REPOSICION_HABITO: Frío y Sabor (cliente 4)
  FOREACH v_fecha IN ARRAY ARRAY[
    CURRENT_DATE - 28,
    CURRENT_DATE - 21,
    CURRENT_DATE - 14,
    CURRENT_DATE - 7
  ]::date[] LOOP
    INSERT INTO dimer.pedidos (cliente_id, fecha, items, total, estado, notas, is_mock)
    VALUES (4, v_fecha + TIME '11:00:00', '[]'::jsonb, 12000, 'confirmado', 'SEED DEMO FIELD DIMER', true)
    RETURNING id INTO v_pedido_id;

    INSERT INTO dimer.items_pedido (pedido_id, product_code, cantidad_solicitada, precio_unitario, is_mock)
    VALUES (v_pedido_id, '12572647', 3, 4000, true);
  END LOOP;

  -- C) MEJORAR_MIX: clientes activos — solo tipo A
  FOR rec IN
    SELECT * FROM (VALUES
      (51, CURRENT_DATE - 12, ARRAY['12572647']::text[]),
      (51, CURRENT_DATE - 5,  ARRAY['12572647','110111091']::text[]),
      (8,  CURRENT_DATE - 8,  ARRAY['11000601']::text[]),
      (5,  CURRENT_DATE - 6,  ARRAY['10000374','770695']::text[])
    ) AS t(cliente_id, fecha, skus)
  LOOP
    INSERT INTO dimer.pedidos (cliente_id, fecha, items, total, estado, notas, is_mock)
    VALUES (
      rec.cliente_id, rec.fecha + TIME '09:30:00', '[]'::jsonb, 9500,
      'confirmado', 'SEED DEMO FIELD DIMER', true
    )
    RETURNING id INTO v_pedido_id;

    FOREACH v_sku IN ARRAY rec.skus LOOP
      INSERT INTO dimer.items_pedido (pedido_id, product_code, cantidad_solicitada, precio_unitario, is_mock)
      VALUES (v_pedido_id, v_sku, 2, 3500, true);
    END LOOP;
  END LOOP;

  -- D) Progreso objetivos comerciales
  FOR rec IN
    SELECT * FROM (VALUES
      (51, CURRENT_DATE - 4, '12510391', 25),
      (8,  CURRENT_DATE - 3, '12510391', 20),
      (5,  CURRENT_DATE - 2, '12510391', 30),
      (29, CURRENT_DATE - 5, '12510391', 15),
      (28, CURRENT_DATE - 4, '12510391', 20),
      (51, CURRENT_DATE - 3, '158385', 10),
      (4,  CURRENT_DATE - 2, '158385', 12),
      (8,  CURRENT_DATE - 1, '158385', 8),
      (5,  CURRENT_DATE - 1, '158385', 15)
    ) AS t(cliente_id, fecha, sku, qty)
  LOOP
    INSERT INTO dimer.pedidos (cliente_id, fecha, items, total, estado, notas, is_mock)
    VALUES (
      rec.cliente_id, rec.fecha + TIME '14:00:00', '[]'::jsonb, rec.qty * 500,
      'confirmado', 'SEED DEMO FIELD DIMER', true
    )
    RETURNING id INTO v_pedido_id;

    INSERT INTO dimer.items_pedido (pedido_id, product_code, cantidad_solicitada, precio_unitario, is_mock)
    VALUES (v_pedido_id, rec.sku, rec.qty, 500, true);
  END LOOP;

  RAISE NOTICE 'Seed pedidos OK';
END $$;

-- Pedido abierto demo: Frío y Sabor con SKU reposición
UPDATE dimer.pedidos SET notas = 'Pedido demo anterior'
WHERE cliente_id = 4
  AND notas LIKE 'Pedido abierto mock%'
  AND estado IN ('abierto', 'pendiente');

INSERT INTO dimer.pedidos (cliente_id, fecha, items, total, estado, notas, is_mock)
SELECT 4, CURRENT_DATE + TIME '08:00:00', '[]'::jsonb, 12000, 'pendiente',
       'SEED DEMO FIELD DIMER - pedido abierto reposición', true
WHERE NOT EXISTS (
  SELECT 1 FROM dimer.pedidos
  WHERE cliente_id = 4
    AND notas = 'SEED DEMO FIELD DIMER - pedido abierto reposición'
    AND estado IN ('abierto', 'pendiente')
);

INSERT INTO dimer.items_pedido (pedido_id, product_code, cantidad_solicitada, precio_unitario, is_mock)
SELECT p.id, '12572647', 3, 4000, true
FROM dimer.pedidos p
WHERE p.cliente_id = 4
  AND p.notas = 'SEED DEMO FIELD DIMER - pedido abierto reposición'
  AND NOT EXISTS (
    SELECT 1 FROM dimer.items_pedido ip WHERE ip.pedido_id = p.id
  );
