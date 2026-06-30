-- Fase 5: reposición por hábito — ruta jueves Juan Pérez (tenant dimer)
-- Requisito motor: pedidos_90d > 3, sales-engine days_remaining <= 2, PDV en ruta del día

-- El pedido abierto de hoy con SKU 12572647 movía last_purchase_date → no hay urgencia
DELETE FROM dimer.items_pedido ip
USING dimer.pedidos p
WHERE ip.pedido_id = p.id
  AND p.cliente_id = 4
  AND p.notas = 'SEED DEMO FIELD DIMER - pedido abierto reposición';

DELETE FROM dimer.pedidos
WHERE cliente_id = 4
  AND notas = 'SEED DEMO FIELD DIMER - pedido abierto reposición';

-- Hábito semanal SKU 12572647 — Comidas Congeladas (PDV jueves, cliente 28)
DELETE FROM dimer.items_pedido ip
USING dimer.pedidos p
WHERE ip.pedido_id = p.id
  AND p.cliente_id = 28
  AND p.notas = 'SEED DEMO FIELD DIMER - reposicion jueves';

DELETE FROM dimer.pedidos
WHERE cliente_id = 28
  AND notas = 'SEED DEMO FIELD DIMER - reposicion jueves';

DO $$
DECLARE
  v_pedido_id integer;
  v_fecha date;
BEGIN
  FOREACH v_fecha IN ARRAY ARRAY[
    CURRENT_DATE - 35,
    CURRENT_DATE - 28,
    CURRENT_DATE - 21,
    CURRENT_DATE - 14,
    CURRENT_DATE - 7
  ]::date[] LOOP
    INSERT INTO dimer.pedidos (cliente_id, fecha, items, total, estado, notas, is_mock)
    VALUES (28, v_fecha + TIME '11:30:00', '[]'::jsonb, 12000, 'confirmado',
            'SEED DEMO FIELD DIMER - reposicion jueves', true)
    RETURNING id INTO v_pedido_id;

    INSERT INTO dimer.items_pedido (pedido_id, product_code, cantidad_solicitada, precio_unitario, is_mock)
    VALUES (v_pedido_id, '12572647', 3, 4000, true);
  END LOOP;
END $$;

-- Segundo PDV jueves: Alimentos de Hielo (cliente 29)
DELETE FROM dimer.items_pedido ip
USING dimer.pedidos p
WHERE ip.pedido_id = p.id
  AND p.cliente_id = 29
  AND p.notas = 'SEED DEMO FIELD DIMER - reposicion jueves';

DELETE FROM dimer.pedidos
WHERE cliente_id = 29
  AND notas = 'SEED DEMO FIELD DIMER - reposicion jueves';

DO $$
DECLARE
  v_pedido_id integer;
  v_fecha date;
BEGIN
  FOREACH v_fecha IN ARRAY ARRAY[
    CURRENT_DATE - 28,
    CURRENT_DATE - 21,
    CURRENT_DATE - 14,
    CURRENT_DATE - 7
  ]::date[] LOOP
    INSERT INTO dimer.pedidos (cliente_id, fecha, items, total, estado, notas, is_mock)
    VALUES (29, v_fecha + TIME '12:00:00', '[]'::jsonb, 9000, 'confirmado',
            'SEED DEMO FIELD DIMER - reposicion jueves', true)
    RETURNING id INTO v_pedido_id;

    INSERT INTO dimer.items_pedido (pedido_id, product_code, cantidad_solicitada, precio_unitario, is_mock)
    VALUES (v_pedido_id, '110111091', 2, 4500, true);
  END LOOP;
END $$;

-- Quitar tareas REPOSICION seed manuales de hoy (regenerar vía motor + home)
DELETE FROM dimer.field_point_ledger
WHERE task_id IN (
  SELECT id FROM dimer.field_tasks
  WHERE vendedor_id = 1 AND tipo = 'REPOSICION_HABITO' AND fecha = CURRENT_DATE
);

DELETE FROM dimer.field_tasks
WHERE vendedor_id = 1 AND tipo = 'REPOSICION_HABITO' AND fecha = CURRENT_DATE;

-- Hábito limpio: solo pedidos semanales dedicados (intervalo ~7 días)
DELETE FROM dimer.items_pedido ip
USING dimer.pedidos p
WHERE ip.pedido_id = p.id
  AND p.cliente_id = 28
  AND ip.product_code = '12572647'
  AND p.notas <> 'SEED DEMO FIELD DIMER - reposicion jueves';

DELETE FROM dimer.items_pedido ip
USING dimer.pedidos p
WHERE ip.pedido_id = p.id
  AND p.cliente_id = 29
  AND ip.product_code = '110111091'
  AND p.notas <> 'SEED DEMO FIELD DIMER - reposicion jueves';
