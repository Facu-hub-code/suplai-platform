# 077 — Métricas: Pareto de clientes en riesgo y label de semana

**Estado:** Borrador  
**Fecha:** 2026-09-22  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas sugeridas:** `feat/metricas-pareto-semana`  
**Relaciona:** `GET /{schema}/metricas/comercial` (`data_access/comercial_metrics.py`, `CommercialClientesTable`, `CommercialSeriesChart`). No reemplaza Prioridad 1 (spec backend `074-prioridad-1-top-pdvs`): esa recorta el universo a los PDV de mayor facturación 90 días. Esta marca, dentro del resultado ya filtrado, quién concentra el dinero que se está yendo.

---

## Contexto

Detalle por cliente lista a todos los que compraron en el rango, ordenados por facturación. La columna Frecuencia compara contra `frecuencia_historica` y pinta el desvío (verde si acompaña, ámbar si cae). Con muchas filas, la caída de un cliente de ticket alto queda en la página 3, al lado de caídas chicas.

El gráfico de facturación, cuando la granularidad es semana, rotula `Semana 34`. El número ISO no dice qué días son.

La query de clientes ya agrega facturación, pedidos, ticket y frecuencia histórica de quien compró en la ventana. Rankear ese array es barato. Lo que sí puede costar es incorporar a los que **no compraron** en la ventana (la pérdida ya consumada): hoy no salen en `clientes[]`.

---

## Actualización 2026-09-26 — cupo de 200

“Solo importantes” marca hasta 200 clientes con más chance de comprar, no el 20% de la ventana. El día de visita de mañana prioriza y el ciclo de compra bloquea a quien ya compró. Quien no compró en el rango del gráfico igual puede entrar. El detalle vivo está en `docs/producto/supervisor-comercial.md`. El corte del 20% y la exclusión de quien tiene 0 pedidos en el rango, más abajo, quedan reemplazados por esta actualización.

## Objetivo

1. Entre los clientes con frecuencia por debajo de la histórica, marcar el 20% de mayor ticket y mostrar el monto que esa franja deja de facturar si sostiene la brecha.
2. Reemplazar `Semana N` por el rango de esa semana, de lunes a domingo.

### Métricas de éxito

- Con 10 clientes en caída, quedan marcados 2 (el techo del 20%).
- El monto mostrado es la suma de `(frecuencia_historica - frecuencia) * ticket` de esos marcados, no de toda la tabla.
- El endpoint de métricas no suma un job ni una segunda request. El ranking viaja en la misma respuesta.
- El eje del gráfico dice, por ejemplo, `Semana del 10 al 16 de agosto` en lugar de `Semana 34`.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Universo v1 | Filas que **ya** devuelve `clientes[]` (compraron en el rango) y además `frecuencia < frecuencia_historica` | Ahí están frecuencia y ticket, que es la matemática pedida, y el costo es ordenar un array ya agregado. | Correr Pareto sobre las alarmas (`baja_frecuencia`, etc.): esas filas no traen ticket. Unirlas duplicaría la query de alarmas. |
| “Pérdida” total (0 pedidos en el rango) | Fuera de v1 | Esos clientes no están en el agregado. Meterlos exige otra rama (historial fuera de la ventana, ticket de referencia propio) y es el único cambio que puede alargar el endpoint. Se mide aparte si hace falta. | Job en background: el monto quedaría viejo respecto de fechas, vendedor, zona y etiquetas que el operador acaba de cambiar. |
| Corte 20% | Sobre el subconjunto en caída, no sobre todos los clientes. `ceil(n * 0.2)`, mínimo 1 si hay al menos uno en caída | “Dentro de los que bajan, el 20% de ticket más alto.” Sobre el total, un cliente estable de ticket enorme taparía al que se está yendo. | Top 20% de facturación de toda la tabla (Pareto clásico de concentración): no habla de riesgo de pérdida. |
| Orden del corte | Ticket descendente. Empate: mayor brecha de frecuencia, después `cliente_id` | El segundo eje es el valor en riesgo. La frecuencia ya definió quién entra al subconjunto. | Ordenar solo por caída de frecuencia y tomar el 20%: destacaría al que pasó de 2 a 0 pedidos con ticket chico. |
| Monto en riesgo | `max(0, frecuencia_historica - frecuencia) * ticket_promedio`, sumado **solo** en la franja Pareto | `frecuencia` en esta tabla es el conteo de pedidos del rango. La brecha por el ticket actual es la plata del período que no se repitió. | Sumar `facturacion` de esos clientes: eso es lo que sí vendieron, no lo que está en riesgo. |
| Dónde se calcula | En el servicio de métricas, sobre las filas ya armadas, mismo request | Cientos o pocos miles de clientes: ordenar es despreciable al lado del SQL de ítems. Un segundo proceso no aporta frescura y sí estados a medias. | Materializar de noche: ignora el filtro de la pantalla. |
| Guardia de tiempo | Loguear la duración del armado de `clientes` (ya existente) más el rank. Si en un tenant grande el endpoint pasa de ~1,5s p95 **después** de este cambio, recién ahí se evalúa recortar. No se construye el job en esta entrega. | El pedido era revisar que no sea lento. El rank no es el costo; el SQL sí, y no se toca en v1. | Optimizar antes de medir. |
| UI | Filas Pareto con fondo y borde izquierdo distintos, más un badge de texto. Barra encima de la tabla: cantidad y monto. Toggle “Solo importantes” filtra a esa franja. Sin el toggle, la tabla sigue mostrando a todos, con los marcados visibles en cualquier orden. | Pintar solo con color se pierde y no reduce el volumen. El toggle es el filtro; el color es la marca cuando se ve el listado completo. | Reordenar siempre y esconder el resto: tapa al cliente que el operador estaba buscando. |
| Semana | Lunes a domingo de esa semana ISO (el bucket ya es el lunes). El tick dice `Semana del 10 al 16 de agosto`. Si cruza mes: `Semana del 27 de julio al 2 de agosto`. Los ticks rotan o bajan de tamaño para que no se pisen. | Es el texto pedido. `Semana 34` no dice qué días son. El ejemplo “10 al 17” incluye el lunes siguiente y la barra de al lado repetiría ese día; el domingo cierra la semana sin solapar. | Label corto `10–16 ago`: se lee peor y no es lo que se pidió cambiar. |
| Idioma del mes | `date-fns` con el locale de la UI (es / pt) | El backoffice ya traduce Métricas. | Meses hardcodeados en español. |

Ejemplo de corte: 10 clientes con frecuencia bajo la histórica. `ceil(2) = 2`. Se marcan los dos de mayor ticket. Si el 2º y el 3º empatan en ticket y en brecha, gana el `cliente_id` menor para que el corte sea estable.

---

## Alcance explícito

### Incluido (v1)

- En la respuesta de métricas comerciales, por cliente en caída que caiga en la franja: `en_franja_pareto: true`. El resto `false` o el campo ausente = false.
- Objeto resumen, por ejemplo junto a `resumen` o como `pareto`:
  - `clientes_en_caida`
  - `clientes_franja` (el 20%)
  - `monto_en_riesgo` (suma de la franja, redondeada a 2 decimales)
- Tabla Detalle por cliente: estilo distinto + badge, barra con el monto, toggle Solo importantes.
- El toggle no pide otro fetch: filtra el array ya cargado.
- Gráfico de serie: buckets `week` con rango de fechas. Día y mes no cambian.
- Eje X con tick más chico o rotado lo necesario para que el rango no se superponga.

### Fuera de alcance

- Clientes con cero pedidos en el rango (pérdida ya cerrada).
- Aplicar el mismo corte a las cuatro tablas de Alarmas.
- Cambiar Prioridad 1, los umbrales de alarma (≥30% pedidos, etc.) ni la fórmula de `frecuencia_historica`.
- Persistencia del monto (no hay tabla nueva ni snapshot).
- Mixpanel: no es un evento de negocio de esta entrega.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `backend-supabase` | `feat/metricas-pareto-semana` | Rank + campos en la respuesta + tests. El label de semana no depende del backend (el bucket ISO ya existe). |
| 2 | `product-management-app` | `feat/metricas-pareto-semana` | Marca, toggle, monto y label del gráfico |

El gráfico se puede mergear sin el backend. La tabla Pareto no: sin los campos nuevos el toggle no tiene a quién marcar. Se puede calcular en el cliente con la misma fórmula si se quiere un solo PR de UI, pero la spec fija el cálculo en el backend para que el monto no dependa de un redondeo distinto en el browser. El front solo pinta.

---

## Migración de base de datos

Sin migración de BD. Sin backfill. Rollback: dejar de leer los campos nuevos; el listado de clientes sigue igual.

---

## Contrato

Sobre cada item de `clientes[]` que aplique:

```json
{
  "cliente_id": 10,
  "frecuencia": 3,
  "frecuencia_historica": 7.75,
  "ticket_promedio": 219230,
  "en_franja_pareto": true,
  "monto_en_riesgo": 1041342.5
}
```

`monto_en_riesgo` del cliente es la brecha de ese cliente (también en los que no son franja, para poder auditar). El total de la barra es la suma de los `en_franja_pareto`.

```json
"pareto": {
  "clientes_en_caida": 10,
  "clientes_franja": 2,
  "monto_en_riesgo": 1800000.0
}
```

Si nadie está en caída: `clientes_en_caida = 0`, `clientes_franja = 0`, `monto_en_riesgo = 0`, toggle deshabilitado.

Label de semana (solo UI, el `bucket` sigue siendo `YYYY-MM-DD` del lunes):

| Bucket (lunes) | Tick |
|----------------|------|
| 2026-08-10 | `Semana del 10 al 16 de agosto` |
| 2026-07-27 | `Semana del 27 de julio al 2 de agosto` |

---

## Plan de prueba en CI/CD

- Pytest junto a `tests/test_comercial_metrics.py`:
  - 5 clientes en caída, tickets distintos → `clientes_franja == 1` (`ceil(5 * 0.2)`).
  - El marcado es el de mayor ticket, aunque otro haya caído más en frecuencia.
  - Cliente con frecuencia ≥ histórica no entra aunque su ticket sea el más alto.
  - Monto = brecha × ticket, y el total del objeto `pareto` suma solo la franja.
  - Cero clientes en caída → ceros, sin excepción.
- No hace falta test del string del eje (es presentación). Sí un test de unidad chico del formateo de rango si se extrae a función pura; si queda inline en el chart, lo cubre el checklist humano.
- Checks del PR en verde. Sin smoke de migración.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000`, backoffice `3000`. Tenant con varios clientes y un rango de fechas donde haya caídas de frecuencia (ámbar en la columna Frecuencia) y al menos un ticket claramente más alto.

1. Métricas → Detalle por cliente. Las filas en caída de ticket alto se ven distintas (fondo/borde + badge), también si se ordena por nombre.
2. La barra muestra un monto y un conteo. El conteo es aproximadamente el 20% de las filas ámbar, nunca todas.
3. Solo importantes: la tabla queda en esa franja. Volver a ver todos restaura el listado y la página.
4. Cambiar vendedor o fechas: el monto y las marcas cambian con el mismo fetch de siempre (no aparece un spinner extra ni un número que quede pegado al filtro anterior).
5. Rango que agrupa por semana (el default del gráfico): el eje dice `Semana del 10 al 16 de agosto` (lunes a domingo), no `Semana 34`.
6. Un rango corto que agrupa por día sigue en `dd/MM`. Un rango largo por mes sigue en mes y año.
7. En una ventana angosta el eje de semanas no se pisa; si rota los ticks, se siguen leyendo.

---

## Criterios de aceptación

### AC-1 Corte por ticket dentro de la caída

- **Given** tres clientes en caída con tickets 100, 500 y 50, y uno estable con ticket 900.
- **When** se carga Métricas.
- **Then** `ceil(3 * 0.2) = 1` marcado: el de ticket 500. El estable no está marcado. `monto_en_riesgo` de la barra es solo la brecha del de 500 por su ticket.

### AC-2 El listado completo sigue

- **Given** el mismo resultado.
- **When** el toggle Solo importantes está apagado.
- **Then** se ven los cuatro clientes. El de ticket 500 está pintado distinto.

### AC-3 Sin segunda carga

- **Given** el panel ya cargado.
- **When** se activa el toggle.
- **Then** no hay un request nuevo a `/metricas/comercial`.

### AC-4 Semana legible

- **Given** granularidad semana y un bucket que cae el lunes 10 de agosto.
- **When** se mira el gráfico.
- **Then** el tick cubre del 10 al 16 de agosto y no dice `Semana` más un número suelto.
