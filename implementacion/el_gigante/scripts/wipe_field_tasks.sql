-- Wipe tareas Field de el_gigante para regenerar con pedidos al día.
-- Ledger no tiene ON DELETE CASCADE. Plantillas / objetivos / torneo se dejan.
-- Schema: el_gigante

BEGIN;

DELETE FROM el_gigante.field_point_ledger;
DELETE FROM el_gigante.field_task_events;
DELETE FROM el_gigante.field_tasks;

COMMIT;

SELECT
  (SELECT COUNT(*) FROM el_gigante.field_tasks) AS tasks,
  (SELECT COUNT(*) FROM el_gigante.field_task_events) AS events,
  (SELECT COUNT(*) FROM el_gigante.field_point_ledger) AS ledger,
  (SELECT COUNT(*) FROM el_gigante.field_task_templates) AS templates;
