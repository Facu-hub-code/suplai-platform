-- Fase 2: clasificación comercial A/B — SKUs del demo

UPDATE dimer.productos SET tipo_venta = 'A'
WHERE product_code IN (
  '12572647', '110111091', '770695', '110077', '158385', '10000374', '11000601'
);

UPDATE dimer.productos SET tipo_venta = 'B'
WHERE product_code IN (
  '12510391', '12616158', '12616196', '12562288', '12510386', '294', '134054'
);

-- RFM cosmético para filtros backoffice
UPDATE dimer.clients SET client_rfm_class = 'CHURN_RISK'
WHERE id IN (2, 13, 24, 28, 29, 32);

UPDATE dimer.clients SET client_rfm_class = 'ACTIVE'
WHERE id IN (4, 5, 8, 51);
