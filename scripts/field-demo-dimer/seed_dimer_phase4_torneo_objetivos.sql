-- Fase 4: torneo, objetivos, tareas demo y ledger — tenant dimer

DELETE FROM dimer.field_point_ledger
WHERE task_id IN (
  SELECT id FROM dimer.field_tasks WHERE criterio_json->>'seed' = 'demo_dimer'
);

DELETE FROM dimer.field_tasks WHERE criterio_json->>'seed' = 'demo_dimer';

DELETE FROM dimer.field_objetivo_skus
WHERE objetivo_id IN (SELECT id FROM dimer.field_objetivos WHERE nombre LIKE 'SEED DEMO%');

DELETE FROM dimer.field_objetivos WHERE nombre LIKE 'SEED DEMO%';

DELETE FROM dimer.field_tournaments WHERE nombre = 'Torneo Invierno Dimer 2026';

INSERT INTO dimer.field_tournaments (
  nombre, fecha_inicio, fecha_fin, estado, premio_nota, vendedor_ids
) VALUES (
  'Torneo Invierno Dimer 2026',
  CURRENT_DATE - 5,
  CURRENT_DATE + 20,
  'ACTIVO',
  'Día de campo + asado para el equipo ganador',
  ARRAY[1, 2, 3]
);

INSERT INTO dimer.field_objetivos (
  nombre, descripcion, tipo, meta_unidades, fecha_inicio, fecha_fin, activo, grupo_ref
) VALUES
(
  'SEED DEMO - Helado verano ChamoniX',
  'Push de helado trisabor ChamoniX — semana demo',
  'sku', 500, CURRENT_DATE - 2, CURRENT_DATE + 4, true,
  '{"source": "manual", "product_codes": ["12510391"]}'::jsonb
),
(
  'SEED DEMO - Hamburguesas Sadia fin de mes',
  'Liquidar stock hamburguesas vacuno Sadia',
  'sku', 200, CURRENT_DATE - 2, CURRENT_DATE + 5, true,
  '{"source": "manual", "product_codes": ["158385"]}'::jsonb
),
(
  'SEED DEMO - Merluza (inactivo)',
  'Borrador objetivo merluza',
  'sku', 100, CURRENT_DATE - 30, CURRENT_DATE - 1, false,
  '{"source": "manual", "product_codes": ["294"]}'::jsonb
);

INSERT INTO dimer.field_objetivo_skus (objetivo_id, product_code)
SELECT o.id, '12510391' FROM dimer.field_objetivos o
WHERE o.nombre = 'SEED DEMO - Helado verano ChamoniX'
UNION ALL
SELECT o.id, '158385' FROM dimer.field_objetivos o
WHERE o.nombre = 'SEED DEMO - Hamburguesas Sadia fin de mes'
UNION ALL
SELECT o.id, '294' FROM dimer.field_objetivos o
WHERE o.nombre = 'SEED DEMO - Merluza (inactivo)';

DO $$
DECLARE
  v_torneo_id integer;
  v_tpl_reactivar integer;
  v_tpl_mix integer;
  v_tpl_repos integer;
  v_task_id bigint;
  rec record;
BEGIN
  SELECT id INTO v_torneo_id FROM dimer.field_tournaments WHERE nombre = 'Torneo Invierno Dimer 2026';
  SELECT id INTO v_tpl_reactivar FROM dimer.field_task_templates WHERE tipo = 'REACTIVAR_CLIENTE';
  SELECT id INTO v_tpl_mix FROM dimer.field_task_templates WHERE tipo = 'MEJORAR_MIX_RENTABLE';
  SELECT id INTO v_tpl_repos FROM dimer.field_task_templates WHERE tipo = 'REPOSICION_HABITO';

  -- Tareas completadas históricas (ledger torneo)
  FOR rec IN
    SELECT * FROM (VALUES
      (1, 29, 29, 'REACTIVAR_CLIENTE', CURRENT_DATE - 4, 70),
      (1, 28, 28, 'REACTIVAR_CLIENTE', CURRENT_DATE - 3, 80),
      (1, 32, 32, 'REACTIVAR_CLIENTE', CURRENT_DATE - 2, 70),
      (2, 13, NULL, 'REACTIVAR_CLIENTE', CURRENT_DATE - 4, 80),
      (2, 5,  NULL, 'MEJORAR_MIX_RENTABLE', CURRENT_DATE - 3, 90),
      (2, 13, NULL, 'REACTIVAR_CLIENTE', CURRENT_DATE - 2, 110),
      (3, 24, NULL, 'REACTIVAR_CLIENTE', CURRENT_DATE - 4, 50),
      (3, 51, NULL, 'MEJORAR_MIX_RENTABLE', CURRENT_DATE - 3, 60),
      (3, 24, NULL, 'REACTIVAR_CLIENTE', CURRENT_DATE - 2, 40)
    ) AS t(vendedor_id, cliente_id, pdv_id, tipo, fecha, puntos)
  LOOP
    INSERT INTO dimer.field_tasks (
      template_id, vendedor_id, pdv_id, cliente_id, tipo, descripcion, puntos,
      estado, criterio_json, fecha, completada_at
    ) VALUES (
      CASE rec.tipo
        WHEN 'REACTIVAR_CLIENTE' THEN v_tpl_reactivar
        WHEN 'MEJORAR_MIX_RENTABLE' THEN v_tpl_mix
        ELSE v_tpl_repos
      END,
      rec.vendedor_id, rec.pdv_id, rec.cliente_id, rec.tipo,
      'SEED DEMO FIELD DIMER - histórico ' || rec.tipo,
      rec.puntos, 'COMPLETADA',
      '{"seed": "demo_dimer"}'::jsonb,
      rec.fecha, rec.fecha + TIME '18:00:00'
    )
    ON CONFLICT (vendedor_id, cliente_id, tipo, fecha) DO UPDATE
      SET descripcion = EXCLUDED.descripcion,
          criterio_json = EXCLUDED.criterio_json
    RETURNING id INTO v_task_id;

    INSERT INTO dimer.field_point_ledger (vendedor_id, task_id, puntos, fecha, torneo_id)
    VALUES (rec.vendedor_id, v_task_id, rec.puntos, rec.fecha, v_torneo_id)
    ON CONFLICT DO NOTHING;
  END LOOP;

  -- Tareas de hoy
  INSERT INTO dimer.field_tasks (
    template_id, vendedor_id, pdv_id, cliente_id, tipo, descripcion, puntos,
    estado, criterio_json, fecha
  ) VALUES
  (v_tpl_reactivar, 1, 28, 28, 'REACTIVAR_CLIENTE',
   'Reactivar Comidas Congeladas — 101 días sin pedir [Historial limitado]',
   40, 'PENDIENTE', '{"seed": "demo_dimer", "combo_skus": ["12572647", "770695"]}'::jsonb, CURRENT_DATE),
  (v_tpl_reactivar, 1, 32, 32, 'REACTIVAR_CLIENTE',
   'Reactivar Sabor Frío — 90 días sin pedir [Historial limitado]',
   30, 'PENDIENTE', '{"seed": "demo_dimer", "combo_skus": ["110111091"]}'::jsonb, CURRENT_DATE),
  (v_tpl_repos, 1, 4, 4, 'REPOSICION_HABITO',
   'Frío y Sabor: reposición urgente — BOTE CAFE HELADO 4.8 CL (A) — cada 7 d',
   30, 'PENDIENTE', '{"seed": "demo_dimer", "combo_skus": ["12572647"]}'::jsonb, CURRENT_DATE),
  (v_tpl_reactivar, 2, NULL, 13, 'REACTIVAR_CLIENTE',
   'Reactivar Alimentos Árticos — 114 días sin pedir [Historial limitado]',
   40, 'PENDIENTE', '{"seed": "demo_dimer"}'::jsonb, CURRENT_DATE),
  (v_tpl_mix, 2, NULL, 5, 'MEJORAR_MIX_RENTABLE',
   'Recomprar 12562288 + 12616158 en La Helada',
   30, 'PENDIENTE', '{"seed": "demo_dimer", "combo_skus": ["12562288", "12616158"]}'::jsonb, CURRENT_DATE),
  (v_tpl_reactivar, 3, NULL, 24, 'REACTIVAR_CLIENTE',
   'Reactivar Frío y Fresco — 112 días sin pedir [Historial limitado]',
   40, 'PENDIENTE', '{"seed": "demo_dimer"}'::jsonb, CURRENT_DATE),
  (v_tpl_mix, 3, NULL, 51, 'MEJORAR_MIX_RENTABLE',
   'Recomprar 12510391 en Alimentos de Nieve',
   30, 'PENDIENTE', '{"seed": "demo_dimer", "combo_skus": ["12510391"]}'::jsonb, CURRENT_DATE)
  ON CONFLICT (vendedor_id, cliente_id, tipo, fecha) DO UPDATE
    SET descripcion = EXCLUDED.descripcion,
        puntos = EXCLUDED.puntos,
        criterio_json = EXCLUDED.criterio_json;
END $$;
