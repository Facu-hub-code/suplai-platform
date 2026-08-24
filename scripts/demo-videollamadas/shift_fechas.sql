-- Self-healing date shift for tenant demo (SPEC-035).
-- Called by n8n daily at 01:00 ART, before backend field_daily_tasks (02:30).
-- Shifts historical rows so MAX(fecha)::date of pedidos older than today
-- catches up to CURRENT_DATE. Pedidos de hoy no se tocan (órdenes live).
-- No desplaza field_tasks: el cron 02:30 genera las del día.

CREATE OR REPLACE FUNCTION demo.shift_sales_demo_dates()
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
  delta integer;
  max_f date;
BEGIN
  SELECT MAX(fecha)::date INTO max_f
  FROM demo.pedidos
  WHERE deleted_at IS NULL
    AND fecha::date < CURRENT_DATE;

  IF max_f IS NULL THEN
    RETURN jsonb_build_object('ok', true, 'delta_days', 0, 'reason', 'no_historical_pedidos');
  END IF;

  delta := (CURRENT_DATE - max_f);
  IF delta <= 0 THEN
    RETURN jsonb_build_object(
      'ok', true,
      'delta_days', 0,
      'skipped', true,
      'max_fecha_hist', max_f
    );
  END IF;

  UPDATE demo.pedidos
  SET fecha = fecha + make_interval(days => delta)
  WHERE deleted_at IS NULL
    AND fecha::date < CURRENT_DATE;

  UPDATE demo.items_pedido
  SET fecha_pedido = fecha_pedido + make_interval(days => delta)
  WHERE fecha_pedido IS NOT NULL
    AND fecha_pedido::date < CURRENT_DATE;

  UPDATE demo.promociones_semanales
  SET fecha_inicio = fecha_inicio + make_interval(days => delta),
      fecha_fin = fecha_fin + make_interval(days => delta);

  UPDATE demo.field_objetivos
  SET fecha_inicio = fecha_inicio + delta,
      fecha_fin = fecha_fin + delta
  WHERE activo = true;

  UPDATE demo.field_tournaments
  SET fecha_inicio = fecha_inicio + delta,
      fecha_fin = fecha_fin + delta
  WHERE estado = 'ACTIVO';

  UPDATE core.conversation_events e
  SET created_at = e.created_at + make_interval(days => delta)
  FROM core.conversations c
  WHERE e.conversation_id = c.id
    AND c.schema_name = 'demo';

  UPDATE core.conversations
  SET created_at = created_at + make_interval(days => delta),
      updated_at = updated_at + make_interval(days => delta)
  WHERE schema_name = 'demo';

  UPDATE demo.conversations
  SET started_at = started_at + make_interval(days => delta),
      updated_at = updated_at + make_interval(days => delta);

  UPDATE demo.ia_tickets
  SET created_at = created_at + make_interval(days => delta),
      closed_at = CASE
        WHEN closed_at IS NULL THEN NULL
        ELSE closed_at + make_interval(days => delta)
      END
  WHERE is_mock IS DISTINCT FROM false;

  RETURN jsonb_build_object(
    'ok', true,
    'delta_days', delta,
    'max_fecha_antes', max_f,
    'max_fecha_despues', CURRENT_DATE
  );
END;
$$;
