-- Seed re-ejecutable: carritos abandonados para el Supervisor Copilot.
-- Tenant: demo
-- No crea etiqueta, grupo, plantilla ni agenda: eso lo hacen Lucía / Sofía / Martín.
--
-- Lucía lista estos clientes con funnel_clients stage=carritos (HSM + pedido
-- en ventana de 48h). El pedido queda estado=abierto con líneas, sin confirmar.

DO $$
DECLARE
  seed_ids int[] := ARRAY[37010, 36814, 36800, 36798, 36804, 36808, 36810, 8, 36818, 36803];
  cid int;
  pid int;
  envio_at timestamptz := now() - interval '25 minutes';
  cart_at timestamp := (now() - interval '12 minutes')::timestamp;
  seed_template text := 'hola_cliente_pedido';
BEGIN
  -- Quitar corridas anteriores de este seed.
  DELETE FROM demo.items_pedido ip
  USING demo.pedidos p
  WHERE ip.pedido_id = p.id
    AND coalesce(p.sync_metadata->>'source', '') = 'seed_supervisor_carrito_abandonado';

  DELETE FROM demo.pedidos p
  WHERE coalesce(p.sync_metadata->>'source', '') = 'seed_supervisor_carrito_abandonado';

  DELETE FROM demo.envios_plantillas ep
  USING demo.clients c
  WHERE c.id = ANY(seed_ids)
    AND ep.session_id = c.phone_number
    AND ep.template_name = seed_template
    AND ep.created_at > now() - interval '14 days';

  FOREACH cid IN ARRAY seed_ids LOOP
    SELECT p.id
      INTO pid
    FROM demo.pedidos p
    WHERE p.cliente_id = cid
      AND p.deleted_at IS NULL
      AND lower(trim(p.estado)) IN ('abierto', 'en_revision')
    ORDER BY p.id DESC
    LIMIT 1;

    IF pid IS NULL THEN
      INSERT INTO demo.pedidos (
        cliente_id, fecha, items, total, estado, notas, is_mock, origen, sync_metadata
      )
      VALUES (
        cid,
        cart_at,
        '[]'::jsonb,
        0,
        'abierto',
        'seed_supervisor_carrito_abandonado',
        true,
        'tienda',
        jsonb_build_object(
          'source', 'seed_supervisor_carrito_abandonado',
          'story', 'carrito_abandonado'
        )
      )
      RETURNING id INTO pid;
    ELSE
      DELETE FROM demo.items_pedido WHERE pedido_id = pid;

      UPDATE demo.pedidos
      SET fecha = cart_at,
          items = '[]'::jsonb,
          total = 0,
          estado = 'abierto',
          notas = 'seed_supervisor_carrito_abandonado',
          origen = 'tienda',
          is_mock = true,
          sync_metadata = coalesce(sync_metadata, '{}'::jsonb) || jsonb_build_object(
            'source', 'seed_supervisor_carrito_abandonado',
            'story', 'carrito_abandonado'
          ),
          updated_at = now(),
          deleted_at = NULL
      WHERE id = pid;
    END IF;

    INSERT INTO demo.items_pedido (
      client_id, product_code, precio_unitario, fecha_pedido, nombre,
      cantidad_solicitada, pedido_id, is_mock, notas
    )
    SELECT
      cid::text,
      s.product_code,
      s.precio_unidad,
      cart_at::date,
      s.nombre,
      2 + (get_byte(decode(md5(cid::text || s.product_code), 'hex'), 0) % 4),
      pid,
      true,
      'seed_supervisor_carrito_abandonado'
    FROM LATERAL (
      SELECT
        pp.product_code,
        pr.nombre,
        pp.precio_unidad
      FROM demo.precios_productos pp
      JOIN demo.productos pr ON pr.product_code = pp.product_code
      JOIN demo.clients c ON c.id = cid
      WHERE pr.en_catalogo = true
        AND pp.precio_unidad > 0
        AND pp.lista_precios_id = coalesce(c.lista_precios_id, 1)
      ORDER BY
        CASE WHEN pr.nombre ILIKE '%cofler%' THEN 0 ELSE 1 END,
        md5(cid::text || pp.product_code)
      LIMIT 3
    ) s;

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
      WHERE ip.pedido_id = pid
      GROUP BY ip.pedido_id
    ) sub
    WHERE p.id = sub.pedido_id;

    INSERT INTO demo.envios_plantillas (session_id, template_name, created_at)
    SELECT c.phone_number, seed_template, envio_at
    FROM demo.clients c
    WHERE c.id = cid
      AND c.phone_number IS NOT NULL
      AND btrim(c.phone_number) <> '';

    pid := NULL;
  END LOOP;
END $$;
