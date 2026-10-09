# Guion para el revisor (Demo Claude)

1. En Claude, conectá **Suplai Sales** (`https://mcp.suplaisales.com/mcp`).
2. Entrá con las credenciales del archivo local `reviewer-credentials.local.md` (no está en git).
3. En el consentimiento, la distribuidora tiene que ser **Demo Claude**. No tiene que aparecer otra.
4. Corré estas preguntas:

| # | Pregunta | Qué tendría que pasar |
|---|---|---|
| 1 | ¿Cuáles fueron los últimos 10 pedidos? | Lista de 10 pedidos recientes, con fecha, cliente `Almacén Demo N`, estado y total en pesos. |
| 2 | ¿Qué pidió Almacén Demo 1 el mes pasado? | Pedidos de ese cliente en el mes calendario anterior, o el mensaje de “no encontré un cliente” si el nombre no calza. |
| 3 | ¿Cuántos pedidos se cancelaron esta semana? | Conteo y monto de `cancelado` desde el lunes, o cero si no hay. |
| 4 | Dame el detalle de un pedido de esta semana | Un pedido con ítems (producto, cantidad, subtotal). |
| 5 | ¿Qué clientes más pidieron este mes? | Ranking por monto, `agrupar_por=cliente`, con `hay_mas` si aplica. |

Si pide otra distribuidora o ve clientes con nombres reales de Campi, **parar** y avisar: el aislamiento falló.
