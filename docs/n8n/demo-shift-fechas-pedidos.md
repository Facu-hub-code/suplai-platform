# n8n — shift de fechas del tenant Demo

Workflow versionado: [`workflows/demo_shift_fechas_pedidos.json`](../../workflows/demo_shift_fechas_pedidos.json)

Instancia: `https://primary-production-c1d08.up.railway.app/workflow/zBDJRgEDeuJuKe62` (activo).

Función SQL: `demo.shift_sales_demo_dates()` (script [`scripts/demo-videollamadas/shift_fechas.sql`](../../scripts/demo-videollamadas/shift_fechas.sql)).

## Qué hace

Calcula `delta = CURRENT_DATE - MAX(demo.pedidos.fecha)::date`. Si `delta > 0`, desplaza pedidos, ítems, promos, objetivos, torneo, tareas Field, ledger, conversaciones y tickets mock. Si ya hay un pedido de hoy, no hace nada.

Corre **01:00 ART**, antes del cron backend `field_daily_tasks` (02:30).

## Publicar

1. Importar el JSON en `https://primary-production-c1d08.up.railway.app`.
2. Credential Postgres existente en n8n: `Postgres account` (`ZMxTKu6BCAdKqOaZ`).
3. El script `scripts/demo-videollamadas/publicar_n8n.py` publica el JSON.
4. Activar el workflow (el publicador deja `active=false` hasta pegar/verificar credential).

El nodo se llama “Supabase — shift fechas demo” porque la conexión es al pooler de Supabase (el nodo REST de Supabase no ejecuta SQL con CTE).
