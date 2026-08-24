# n8n — pedidos diarios + shift de fechas (tenant Demo)

Workflow versionado: [`workflows/demo_shift_fechas_pedidos.json`](../../workflows/demo_shift_fechas_pedidos.json)

Instancia: `https://primary-production-c1d08.up.railway.app/workflow/zBDJRgEDeuJuKe62` (activo).

SQL: [`scripts/demo-videollamadas/shift_fechas.sql`](../../scripts/demo-videollamadas/shift_fechas.sql)

- `demo.generate_daily_demo_orders()`
- `demo.shift_sales_demo_dates()`

## Qué hace cada noche (01:00 ART)

1. **Genera pedidos nuevos del día** (sin IA, idempotente).
2. **Corre fechas** de promos, objetivos Field, torneo activo y conversaciones, cada uno con su propia ancla. Si ya cubren hoy, no hace nada.
3. **No toca** `pedidos` / `items_pedido` históricos (así las métricas de 2+ meses no se deslizan).
4. **No toca** `ia_tickets` (notificaciones estáticas).
5. A las **03:00 ART** (después del cron Field 02:30) corre `demo.sanitize_field_task_skus()`: si el ML devolvió códigos que ya no están en el catálogo de 250, los reemplaza por SKUs en catálogo (historial del cliente → objetivos → rotación) y reescribe la descripción con nombres.

## Lógica determinística de pedidos

No hay LLM. El calendario comercial manda:

| Día ART | Zona(s) que piden | Cartera |
|---------|-------------------|---------|
| lunes | Palermo | 14 |
| martes | Belgrano | 14 |
| miércoles | Colegiales | 14 |
| jueves | Villa Crespo | 14 |
| viernes | Caballito | 14 |
| sábado | Palermo + Caballito | 28 |
| domingo | nadie (día sin visita) | 0 |

De esos clientes, entra ~65% según el primer byte de `md5(cliente_id \| fecha ART)` (umbral 166/255). Mismo día + mismo cliente = misma decisión, siempre.

Ítems: hasta 4 SKUs del catálogo 250, con precio de la lista del cliente. Prioriza productos que ese cliente ya compró; el desempate es `md5`. Cantidad `2–6` también sale del hash. Hora entre las 10 y las 17.

Marca: `notas = n8n_demo_pedido_diario`, `is_mock=true`, `estado=confirmado`. Si ya hay un pedido con esa nota hoy para ese cliente, no duplica.

Volumen esperado: ~9 pedidos/día hábil, ~18 el sábado, 0 el domingo.

## Por qué ya no se shiftean pedidos

Si se corrían las fechas del histórico **y** se insertaban pedidos nuevos, el día de hoy se duplicaba y la serie de métricas se aplastaba hacia el presente. Ahora el histórico se queda en junio/julio/agosto y el mes corriente crece con pedidos reales del generador.

## Publicar

1. Aplicar el SQL (`shift_fechas.sql`) en schema `demo` (pooler 6543).
2. Publicar el JSON: `scripts/demo-videollamadas/publicar_n8n.py` (actualiza el workflow `zBDJRgEDeuJuKe62`).
3. Credential Postgres: `Postgres account` (`ZMxTKu6BCAdKqOaZ`), pooler 6543.
4. Activar el workflow si quedó inactivo.

Probar: **Ejecutar manualmente** en n8n, o `SELECT demo.generate_daily_demo_orders();` dos veces (la segunda tiene que devolver `generated: 0`).
