-- Daily demo sales (SPEC-035). Called by n8n at 01:00 ART, before
-- backend field_daily_tasks (02:30).
--
-- 1) generate_daily_demo_orders(): INSERT pedidos nuevos del día, sin IA.
--    Día de visita de la zona + umbral md5 (~65% de los 14 clientes).
--    Idempotente: no duplica si ya hay notas='n8n_demo_pedido_diario' hoy.
-- 2) shift_sales_demo_dates(): corre promos / objetivos / torneo / chats.
--    YA NO desplaza pedidos ni items: el generador aporta volumen fresco
--    y el histórico de ≥2 meses se conserva para métricas.
--    No desplaza field_tasks ni ia_tickets.

CREATE OR REPLACE FUNCTION demo.generate_daily_demo_orders()
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
  dia_art date;
  dia_hoy text;
  n_zona integer := 0;
  n_gen integer := 0;
BEGIN
  dia_art := (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date;
  dia_hoy := CASE EXTRACT(DOW FROM dia_art)::int
    WHEN 1 THEN 'lunes'
    WHEN 2 THEN 'martes'
    WHEN 3 THEN 'miercoles'
    WHEN 4 THEN 'jueves'
    WHEN 5 THEN 'viernes'
    WHEN 6 THEN 'sabado'
    ELSE 'domingo'
  END;

  IF dia_hoy = 'domingo' THEN
    RETURN jsonb_build_object(
      'ok', true,
      'dia', dia_hoy,
      'generated', 0,
      'reason', 'no_visit_day'
    );
  END IF;

  WITH eligible AS (
    SELECT
      c.id AS cliente_id,
      COALESCE(c.lista_precios_id, 1) AS lista_precios_id
    FROM demo.clients c
    JOIN demo.puntos_venta pdv ON pdv.id = c.pdv_id
    JOIN demo.geo_zones z ON z.id = pdv.geo_zone_id AND z.active = true
    WHERE EXISTS (
        SELECT 1
        FROM unnest(z.dias_visita) d
        WHERE replace(replace(d::text, 'é', 'e'), 'á', 'a') = dia_hoy
      )
      AND get_byte(
            decode(md5(c.id::text || '|' || dia_art::text), 'hex'),
            0
          ) < 166
      AND NOT EXISTS (
        SELECT 1
        FROM demo.pedidos p
        WHERE p.cliente_id = c.id
          AND p.deleted_at IS NULL
          AND p.fecha::date = dia_art
          AND p.notas = 'n8n_demo_pedido_diario'
      )
  ),
  counted AS (
    SELECT COUNT(*)::int AS n FROM eligible
  ),
  ins AS (
    INSERT INTO demo.pedidos
      (cliente_id, fecha, items, total, estado, notas, is_mock, origen, sync_metadata)
    SELECT
      e.cliente_id,
      dia_art::timestamp + make_interval(hours => 10 + get_byte(
            decode(md5(e.cliente_id::text || '|' || dia_art::text), 'hex'), 1
          ) % 8),
      '[]'::jsonb,
      0,
      'confirmado',
      'n8n_demo_pedido_diario',
      true,
      'suplai',
      jsonb_build_object(
        'source', 'n8n_demo_daily',
        'generated_on', dia_art::text,
        'dia_visita', dia_hoy
      )
    FROM eligible e
    RETURNING id, cliente_id
  ),
  lines AS (
    INSERT INTO demo.items_pedido
      (client_id, product_code, precio_unitario, fecha_pedido, nombre,
       cantidad_solicitada, pedido_id, is_mock, notas)
    SELECT
      i.cliente_id::text,
      s.product_code,
      s.precio_unidad,
      dia_art,
      s.nombre,
      2 + get_byte(
        decode(md5(i.cliente_id::text || s.product_code || dia_art::text), 'hex'),
        2
      ) % 5,
      i.id,
      true,
      'n8n_demo_pedido_diario'
    FROM ins i
    JOIN eligible e ON e.cliente_id = i.cliente_id
    JOIN LATERAL (
      SELECT
        pp.product_code,
        pr.nombre,
        pp.precio_unidad
      FROM demo.precios_productos pp
      JOIN demo.productos pr ON pr.product_code = pp.product_code
      WHERE pr.en_catalogo = true
        AND pp.lista_precios_id = e.lista_precios_id
        AND pp.precio_unidad > 0
      ORDER BY
        CASE WHEN EXISTS (
          SELECT 1
          FROM demo.items_pedido ip
          JOIN demo.pedidos p ON p.id = ip.pedido_id
          WHERE p.cliente_id = e.cliente_id
            AND p.deleted_at IS NULL
            AND ip.product_code = pp.product_code
        ) THEN 0 ELSE 1 END,
        md5(e.cliente_id::text || dia_art::text || pp.product_code)
      LIMIT 4
    ) s ON true
    RETURNING pedido_id
  )
  SELECT
    (SELECT n FROM counted),
    (SELECT COUNT(*)::int FROM ins)
  INTO n_zona, n_gen;

  UPDATE demo.pedidos p
  SET total = sub.s,
      items = sub.items,
      updated_at = now()
  FROM (
    SELECT
      ip.pedido_id,
      ROUND(SUM(ip.precio_unitario * ip.cantidad_solicitada)::numeric, 2) AS s,
      jsonb_agg(jsonb_build_object(
        'product_code', ip.product_code,
        'nombre', ip.nombre,
        'cantidad_solicitada', ip.cantidad_solicitada,
        'precio_unitario', ip.precio_unitario
      )) AS items
    FROM demo.items_pedido ip
    JOIN demo.pedidos p2 ON p2.id = ip.pedido_id
    WHERE p2.notas = 'n8n_demo_pedido_diario'
      AND p2.fecha::date = dia_art
      AND p2.deleted_at IS NULL
    GROUP BY ip.pedido_id
  ) sub
  WHERE p.id = sub.pedido_id
    AND (p.total IS NULL OR p.total = 0);

  RETURN jsonb_build_object(
    'ok', true,
    'dia', dia_hoy,
    'candidatos_hash', n_zona,
    'generated', COALESCE(n_gen, 0)
  );
END;
$$;


CREATE OR REPLACE FUNCTION demo.shift_sales_demo_dates()
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
  dia_art date;
  d_promo integer := 0;
  d_obj integer := 0;
  d_tor integer := 0;
  d_chat integer := 0;
  max_promo date;
  max_obj date;
  max_tor date;
  max_chat date;
BEGIN
  dia_art := (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date;
  -- Pedidos e items NO se desplazan: el generador diario crea volumen nuevo
  -- y las métricas de 2+ meses se quedan en el calendario real.
  -- Cada entidad se auto-cura con su propia ancla (si ya cubre hoy, delta=0).

  SELECT MAX(fecha_fin)::date INTO max_promo FROM demo.promociones_semanales;
  IF max_promo IS NOT NULL THEN
    d_promo := GREATEST(0, dia_art - max_promo);
    IF d_promo > 0 THEN
      UPDATE demo.promociones_semanales
      SET fecha_inicio = fecha_inicio + make_interval(days => d_promo),
          fecha_fin = fecha_fin + make_interval(days => d_promo);
    END IF;
  END IF;

  SELECT MAX(fecha_fin) INTO max_obj FROM demo.field_objetivos WHERE activo = true;
  IF max_obj IS NOT NULL THEN
    d_obj := GREATEST(0, dia_art - max_obj);
    IF d_obj > 0 THEN
      UPDATE demo.field_objetivos
      SET fecha_inicio = fecha_inicio + d_obj,
          fecha_fin = fecha_fin + d_obj
      WHERE activo = true;
    END IF;
  END IF;

  SELECT MAX(fecha_fin) INTO max_tor FROM demo.field_tournaments WHERE estado = 'ACTIVO';
  IF max_tor IS NOT NULL THEN
    d_tor := GREATEST(0, dia_art - max_tor);
    IF d_tor > 0 THEN
      UPDATE demo.field_tournaments
      SET fecha_inicio = fecha_inicio + d_tor,
          fecha_fin = fecha_fin + d_tor
      WHERE estado = 'ACTIVO';
    END IF;
  END IF;

  SELECT MAX(created_at)::date INTO max_chat
  FROM core.conversations
  WHERE schema_name = 'demo';
  IF max_chat IS NOT NULL THEN
    d_chat := GREATEST(0, dia_art - max_chat);
    IF d_chat > 0 THEN
      UPDATE core.conversation_events e
      SET created_at = e.created_at + make_interval(days => d_chat)
      FROM core.conversations c
      WHERE e.conversation_id = c.id
        AND c.schema_name = 'demo';

      UPDATE core.conversations
      SET created_at = created_at + make_interval(days => d_chat),
          updated_at = updated_at + make_interval(days => d_chat)
      WHERE schema_name = 'demo';

      UPDATE demo.conversations
      SET started_at = started_at + make_interval(days => d_chat),
          updated_at = updated_at + make_interval(days => d_chat);
    END IF;
  END IF;

  RETURN jsonb_build_object(
    'ok', true,
    'pedidos_shift', false,
    'delta_promos', d_promo,
    'delta_objetivos', d_obj,
    'delta_torneo', d_tor,
    'delta_chats', d_chat
  );
END;
$$;


-- Tras el cron Field 02:30 (y el ML, que puede devolver SKUs borrados del
-- catálogo), reescribe combo_skus de tareas pendientes a productos en_catalogo.
CREATE OR REPLACE FUNCTION demo.sanitize_field_task_skus()
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
  rec record;
  dia date;
  keep text[];
  fill text[];
  new_skus text[];
  names text[];
  cname text;
  max_n integer;
  n_upd integer := 0;
  n_ok integer := 0;
  desc_new text;
  replenishment jsonb;
BEGIN
  dia := (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date;

  FOR rec IN
    SELECT t.id, t.tipo, t.cliente_id, t.descripcion, t.criterio_json, c.nombre AS cliente_nombre
    FROM demo.field_tasks t
    LEFT JOIN demo.clients c ON c.id = t.cliente_id
    WHERE t.estado IN ('PENDIENTE', 'PARCIAL')
      AND t.fecha >= dia
  LOOP
    max_n := CASE rec.tipo
      WHEN 'CROSS_SELL_COMBO' THEN 2
      WHEN 'REPOSICION_HABITO' THEN 3
      ELSE 3
    END;

    SELECT COALESCE(array_agg(s ORDER BY ord), ARRAY[]::text[])
    INTO keep
    FROM jsonb_array_elements_text(COALESCE(rec.criterio_json->'combo_skus', '[]'::jsonb))
         WITH ORDINALITY x(s, ord)
    JOIN demo.productos p ON p.product_code = x.s AND p.en_catalogo = true;

    IF cardinality(keep) >= max_n THEN
      n_ok := n_ok + 1;
      CONTINUE;
    END IF;

    new_skus := keep;

    SELECT COALESCE(array_agg(product_code ORDER BY rn), ARRAY[]::text[])
    INTO fill
    FROM (
      SELECT ip.product_code,
             row_number() OVER (ORDER BY COUNT(*) DESC, ip.product_code) AS rn
      FROM demo.items_pedido ip
      JOIN demo.pedidos p ON p.id = ip.pedido_id
      JOIN demo.productos pr ON pr.product_code = ip.product_code AND pr.en_catalogo = true
      WHERE p.cliente_id = rec.cliente_id
        AND p.deleted_at IS NULL
        AND lower(trim(p.estado::text)) IN ('confirmado', 'descargado')
        AND NOT (ip.product_code = ANY (new_skus))
      GROUP BY ip.product_code
      LIMIT 8
    ) h;
    new_skus := new_skus || fill;

    IF cardinality(new_skus) < max_n THEN
      SELECT COALESCE(array_agg(fos.product_code), ARRAY[]::text[])
      INTO fill
      FROM demo.field_objetivo_skus fos
      JOIN demo.field_objetivos o ON o.id = fos.objetivo_id AND o.activo = true
      JOIN demo.productos pr ON pr.product_code = fos.product_code AND pr.en_catalogo = true
      WHERE NOT (fos.product_code = ANY (new_skus));
      new_skus := new_skus || fill;
    END IF;

    IF cardinality(new_skus) < max_n THEN
      SELECT COALESCE(array_agg(product_code ORDER BY rotacion_index DESC NULLS LAST, product_code), ARRAY[]::text[])
      INTO fill
      FROM (
        SELECT pr.product_code, pr.rotacion_index
        FROM demo.productos pr
        WHERE pr.en_catalogo = true
          AND NOT (pr.product_code = ANY (new_skus))
        ORDER BY pr.rotacion_index DESC NULLS LAST, pr.product_code
        LIMIT 8
      ) t;
      new_skus := new_skus || fill;
    END IF;

    IF cardinality(new_skus) = 0 THEN
      CONTINUE;
    END IF;

    new_skus := new_skus[1:max_n];

    SELECT COALESCE(array_agg(p.nombre ORDER BY u.ord), ARRAY[]::text[])
    INTO names
    FROM unnest(new_skus) WITH ORDINALITY u(code, ord)
    JOIN demo.productos p ON p.product_code = u.code;

    cname := COALESCE(rec.cliente_nombre, 'el cliente');
    desc_new := CASE rec.tipo
      WHEN 'CROSS_SELL_COMBO' THEN
        'Ofrecer combo ' || array_to_string(names, ' + ') || ' a ' || cname
      WHEN 'REPOSICION_HABITO' THEN
        'Es momento de reponer para ' || cname || ': ' || array_to_string(names, ', ') || '.'
      WHEN 'REACTIVAR_CLIENTE' THEN
        'Reactivar a ' || cname || ' — sugeridos: ' || array_to_string(names, ', ')
      ELSE rec.descripcion
    END;

    IF rec.tipo = 'REPOSICION_HABITO' THEN
      SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'product_code', p.product_code,
        'nombre', p.nombre,
        'days_remaining', 1,
        'estado_reposicion', 'a_reponer'
      ) ORDER BY u.ord), '[]'::jsonb)
      INTO replenishment
      FROM unnest(new_skus) WITH ORDINALITY u(code, ord)
      JOIN demo.productos p ON p.product_code = u.code;
    ELSE
      replenishment := COALESCE(rec.criterio_json->'replenishment_items', '[]'::jsonb);
    END IF;

    UPDATE demo.field_tasks
    SET descripcion = desc_new,
        criterio_json = rec.criterio_json
          || jsonb_build_object(
            'combo_skus', to_jsonb(new_skus),
            'replenishment_items', replenishment,
            'skus_sanitizados', true
          ),
        updated_at = now()
    WHERE id = rec.id;

    n_upd := n_upd + 1;
  END LOOP;

  RETURN jsonb_build_object('ok', true, 'updated', n_upd, 'already_ok', n_ok);
END;
$$;
