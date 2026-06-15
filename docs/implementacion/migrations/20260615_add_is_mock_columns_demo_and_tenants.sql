-- Migración: columna is_mock para onboarding agéntico (Fase 10 purga mock)
-- Plantilla: schema demo (+ backfill en tenants existentes registrados en public.distribuidoras)
-- Default false: datos productivos existentes no se marcan como mock.
-- Los CSV de implementación insertan is_mock = true en datos simulados.

DO $$
DECLARE
  r record;
  t text;
  tenant_tables constant text[] := ARRAY[
    'productos',
    'listas_precios',
    'precios_productos',
    'promociones_semanales',
    'vendedores',
    'geo_zones',
    'vendedor_geo_zones',
    'puntos_venta',
    'clients',
    'pedidos',
    'items_pedido',
    'n8n_chat_histories',
    'ia_tickets'
  ];
BEGIN
  FOR r IN
    SELECT DISTINCT d.schema_name
    FROM public.distribuidoras d
    WHERE EXISTS (
      SELECT 1
      FROM information_schema.schemata s
      WHERE s.schema_name = d.schema_name
    )
    ORDER BY d.schema_name
  LOOP
    FOREACH t IN ARRAY tenant_tables
    LOOP
      IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = r.schema_name
          AND table_name = t
          AND table_type = 'BASE TABLE'
      ) THEN
        EXECUTE format(
          'ALTER TABLE %I.%I ADD COLUMN IF NOT EXISTS is_mock boolean NOT NULL DEFAULT false',
          r.schema_name,
          t
        );
        EXECUTE format(
          'COMMENT ON COLUMN %I.%I.is_mock IS %L',
          r.schema_name,
          t,
          'True = dato de onboarding/simulación; purgable con DELETE WHERE is_mock = true.'
        );
      END IF;
    END LOOP;
  END LOOP;
END $$;

ALTER TABLE public.tenant_cross_sell_mappings
  ADD COLUMN IF NOT EXISTS is_mock boolean NOT NULL DEFAULT false;

ALTER TABLE public.tenant_up_sell_mappings
  ADD COLUMN IF NOT EXISTS is_mock boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.tenant_cross_sell_mappings.is_mock IS
  'True = relación cross-sell de onboarding; purgable por tenant_id + is_mock.';

COMMENT ON COLUMN public.tenant_up_sell_mappings.is_mock IS
  'True = relación up-sell de onboarding; purgable por tenant_id + is_mock.';
