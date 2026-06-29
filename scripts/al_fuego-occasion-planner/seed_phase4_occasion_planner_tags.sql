-- Fase 4 Occasion Planner — tags complementarios Al Fuego
-- Extiende cobertura del template asado (spec 016 anexo A + cortes faltantes).
-- Idempotente: ON CONFLICT DO NOTHING en tags y product_tags.

BEGIN;

-- Tags semánticos del anexo A (spec 016) — lowercase para escenarios futuros
INSERT INTO al_fuego.tags (name, description)
VALUES
  ('parrilla', 'Carnes aptas para parrilla / asado (Occasion Planner)'),
  ('corte-principal', 'Corte principal del escenario asado'),
  ('achura', 'Achuras del escenario asado'),
  ('complemento-asado', 'Carbón, leña y accesorios de parrilla')
ON CONFLICT (name) DO NOTHING;

-- Vincular tags de ratio faltantes en cortes que ya tenían Carnes pero no matcheaban slot
INSERT INTO al_fuego.product_tags (product_code, tag_id)
SELECT v.product_code, t.id
FROM (
  VALUES
    ('AFTE0052', 'Asado'),
    ('AFTE0085', 'Asado'),
    ('AFTE0067', 'Vacio'),
    ('AFTE0068', 'Vacio')
) AS v(product_code, tag_name)
JOIN al_fuego.tags t ON t.name = v.tag_name
ON CONFLICT (product_code, tag_id) DO NOTHING;

-- Tags anexo A en productos clave (alias semánticos)
INSERT INTO al_fuego.product_tags (product_code, tag_id)
SELECT v.product_code, t.id
FROM (
  VALUES
    ('AFTE0010', 'parrilla'), ('AFTE0010', 'corte-principal'),
    ('AFTE0012', 'parrilla'), ('AFTE0012', 'corte-principal'),
    ('AFTE0002', 'parrilla'), ('AFTE0002', 'corte-principal'),
    ('AFTE0091', 'parrilla'), ('AFTE0091', 'corte-principal'),
    ('AFTE0052', 'parrilla'), ('AFTE0052', 'corte-principal'),
    ('AFTE0067', 'parrilla'), ('AFTE0067', 'corte-principal'),
    ('AFTE0068', 'parrilla'), ('AFTE0068', 'corte-principal'),
    ('AFCE0108', 'achura'),
    ('AFCE0111', 'achura'),
    ('AFTE0007', 'achura'),
    ('AFTE0020', 'achura'),
    ('AFVA0031', 'complemento-asado'),
    ('VACO0181', 'complemento-asado'),
    ('VACO0183', 'complemento-asado')
) AS v(product_code, tag_name)
JOIN al_fuego.tags t ON t.name = v.tag_name
ON CONFLICT (product_code, tag_id) DO NOTHING;

COMMIT;

-- Verificación rápida (ejecutar aparte si se desea)
-- SELECT slot_id, matching_products FROM (... preview query ...);
