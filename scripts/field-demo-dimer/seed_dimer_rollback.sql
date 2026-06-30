-- Rollback seed demo field — tenant dimer

DELETE FROM dimer.field_point_ledger
WHERE task_id IN (SELECT id FROM dimer.field_tasks WHERE criterio_json->>'seed' = 'demo_dimer');

DELETE FROM dimer.field_tasks WHERE criterio_json->>'seed' = 'demo_dimer';

DELETE FROM dimer.field_objetivo_skus
WHERE objetivo_id IN (SELECT id FROM dimer.field_objetivos WHERE nombre LIKE 'SEED DEMO%');

DELETE FROM dimer.field_objetivos WHERE nombre LIKE 'SEED DEMO%';

DELETE FROM dimer.field_tournaments WHERE nombre = 'Torneo Invierno Dimer 2026';

DELETE FROM dimer.field_task_templates
WHERE tipo IN (
  'REACTIVAR_CLIENTE', 'MEJORAR_MIX_RENTABLE', 'REPOSICION_HABITO',
  'CROSS_SELL_RENTABLE', 'CROSS_SELL_COMBO'
);

DELETE FROM dimer.items_pedido ip
USING dimer.pedidos p
WHERE ip.pedido_id = p.id AND p.notas LIKE 'SEED DEMO FIELD DIMER%';

DELETE FROM dimer.pedidos WHERE notas LIKE 'SEED DEMO FIELD DIMER%';

UPDATE dimer.productos SET tipo_venta = NULL
WHERE product_code IN (
  '12572647', '110111091', '770695', '110077', '158385', '10000374', '11000601',
  '12510391', '12616158', '12616196', '12562288', '12510386', '294', '134054'
);

UPDATE dimer.clients SET client_rfm_class = NULL
WHERE id IN (2, 4, 5, 8, 13, 24, 28, 29, 32, 51);
