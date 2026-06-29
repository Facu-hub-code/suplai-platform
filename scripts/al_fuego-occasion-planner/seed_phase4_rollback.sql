-- Rollback fase 4 Occasion Planner — al_fuego
-- No elimina tags de fase 01.1; solo revierte cambios de esta fase.

BEGIN;

UPDATE public.distribuidoras
SET
  metadata = metadata - 'business_mode',
  tools_habilitadas = tools_habilitadas - 'plan_occasion_bundle',
  reglas_negocio = reglas_negocio - 'occasion_planners'
WHERE schema_name = 'al_fuego';

DELETE FROM al_fuego.product_tags pt
USING al_fuego.tags t
WHERE pt.tag_id = t.id
  AND t.name IN ('parrilla', 'corte-principal', 'achura', 'complemento-asado');

DELETE FROM al_fuego.product_tags pt
USING al_fuego.tags t
WHERE pt.tag_id = t.id
  AND pt.product_code IN ('AFTE0052', 'AFTE0085', 'AFTE0067', 'AFTE0068')
  AND t.name IN ('Asado', 'Vacio');

DELETE FROM al_fuego.tags
WHERE name IN ('parrilla', 'corte-principal', 'achura', 'complemento-asado');

COMMIT;
