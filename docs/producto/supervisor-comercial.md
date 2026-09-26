# Supervisor comercial — a quién le vende Suplai

Suplai Sales trabaja para el supervisor comercial de una distribuidora.

## Quién es quién

- **Dueño.** Define el negocio. El supervisor le responde.
- **Supervisor comercial.** Usuario ideal. Se pone la camiseta de la distribuidora y su sueldo depende de que funcione. Gestiona a los vendedores.
- **Vendedor.** Mal pago, rota de trabajo seguido y no le gusta el laburo. Tiene una ruta de unos 30 clientes y un promedio de 15 minutos por visita. Con 30 clientes son 7 horas y media vendiendo: no llega a atenderlos a todos.

## La jornada del supervisor

Dos reuniones. A las **6:00** programa el día. A las **18:00** cierra el día. En el medio necesita poder mandar un mensaje masivo del estilo: “mañana te visitan, pero igual podés hacer el pedido por acá”.

## A quién escribir

Dirección de producto. El filtro “Solo importantes” de Métricas sigue esta misma idea.

1. Primero los clientes de un vendedor, después el día de visita.
2. Sobre eso, Pareto: escribir a los puntos de venta que suelen comprar y a los que se les puede mejorar la frecuencia. Si compran una vez por mes, capaz le compran a un competidor. No perseguir a los que están 100% perdidos.
3. Referencia de volumen: unos **200 mensajes por día** a los 200 puntos de venta con más probabilidad estadística de comprarnos.
4. Regla de frecuencia: si compra cada 2 semanas y ya compró en este ciclo, no enviar.

## Qué hace el filtro “Solo importantes” de Métricas

Arma hasta **200** clientes con más chance de comprar. El día de visita de mañana sube en el ranking, pero no achica la lista: si ese día tiene pocos PDV, igual se completan los 200 con los mejores del resto.

1. Universo: clientes con al menos un pedido `confirmado` o `descargado`, hasta hoy. El origen `erp` cuenta igual que `suplai`, `tienda` o un origen vacío. No exige que el SKU esté en el catálogo. Los filtros de vendedor, zona, etiqueta y prioridad de la pantalla sí recortan ese universo.
2. Si ya compró dentro de su ciclo (la distancia media entre sus pedidos), no entra. Con una sola compra no hay ciclo: no entra si compró en los últimos 14 días.
3. El score es más alto cerca de un ciclo de atraso y cae si hace muchos ciclos que no compra. El ticket histórico pesa. El día de mañana multiplica por 1,5.
4. Si después del bloqueo hay menos de 200, se muestran los que hay.

La ventana de fechas del gráfico sigue siendo la facturación y los pedidos de la tabla. Quien no compró en esa ventana igual puede estar en los 200, con facturación 0 en el rango.
