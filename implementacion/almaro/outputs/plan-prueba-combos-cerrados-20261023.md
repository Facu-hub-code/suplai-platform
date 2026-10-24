# Plan de prueba — combos cerrados (Almaro)

**Fecha:** 23 oct 2026
**Tenant:** `almaro`. Cliente de prueba: id 79, código 5000, lista Suplai 20 TRADICIONAL (GEV `06`).
**Reemplaza a:** `plan-prueba-promos-20261023.md`, que probaba la clasificación en %, pack, 2x1 y regalo.

## La decisión

Acordado con Xionico: un combo de GEV es una promoción en sí misma y viene cerrado, como un SKU. Se pide tal cual figura y se cobra el precio que da GEV. No se reparte en productos ni se recalcula con descuentos. Las combinables también vienen cerradas.

Hay cuatro cosas que definir y probar:

1. **Traer.** Qué combos se sincronizan, con qué componentes y a qué precio por lista.
2. **Presentar.** Cómo se ven en Promociones de la tienda.
3. **Cargar.** Cómo el agente y la tienda dejan el combo en el pedido.
4. **Inyectar.** Cómo viaja el pedido a GEV.

La prueba pasa cuando la tienda, el agente y GEV dan el mismo total para la misma compra.

## De dónde salen los números

Pedidos reales de almaro leídos de `GET /pedidos/getPedidos/`, del 15 al 22 oct 2026: 622 pedidos, **970 líneas de combo y 104 combos distintos**.

Así trae GEV un combo dentro de un pedido:

- En `detalle` hay **una línea** con `CODIGO_COMBO`, sin `CODIGO_ARTICULO`.
  - `CANTIDAD_PEDIDA` es la cantidad de combos.
  - `PRECIO_UNITARIO_LISTA` es el **total neto de la línea**, no el de un combo.
- En `detalle_combo`, con el mismo `ID_DETALLE_PEDIDO`, van los componentes con su cantidad **total** y sin precio.

**Precio de un combo** = `PRECIO_UNITARIO_LISTA ÷ CANTIDAD_PEDIDA × 1,21`.

- Coincide con el precio final del Excel de la distribuidora en todos los combos que están en los dos.
- Es estable para el mismo combo y la misma lista en 125 de 136 pares. Las diferencias son de centavos, salvo Halloween (ver abajo).

`PRECIO_UNITARIO_VENTA` no sirve como precio: según el pedido vale ×1,00, ×1,21 o ×1,337 del de lista.

Mapeo de listas: GEV `06` → Suplai 20 TRADICIONAL, `07` → 10 INTERIOR, `99` → 13 LISTA D, `02` → 7 AUTOSERV Y ORIENTALE.

## Hallazgos que condicionan el diseño

| # | Hallazgo | Impacto |
|---|---|---|
| H1 | **La API no publica el precio del combo antes del pedido.** Ninguno de los 174 combos tiene precio en las listas de GEV, no está en `getArticulos`, y `PRECIO_COMBO` de la cabecera vale 0 o 1. El precio solo aparece en la línea del pedido. | Para mostrar el combo en la tienda y en el agente hace falta un endpoint o campo de Xionico con el precio por combo y lista. Es la pregunta 1. |
| H2 | **Combos de canal.** Las 486 líneas de combos `DEPOT`, `DPEOT` o `AASS` se pidieron con lista `99` o `02`, nunca con `06`, `01` ni `07`. `113049` (`DPEOT 4013`, 25 %) tiene 19 pedidos, todos con lista `99`. | El combo pertenece a la lista con la que se vende. Mientras Xionico no lo confirme, rige el filtro por prefijo del PR backend-suplai#329. |
| H3 | **Al 2x1 le falta el regalo en el pedido.** 15 × `112528` (papas 80 g) trae como componente 15 × `15316`, sin un renglón de regalo ni una línea sin cargo. El combo vale $1.987,93, que es casi el precio de lista de **una** bolsa ($1.987,74). | Hay que saber si se entregan 1 o 2 bolsas por combo. Pregunta 2. |
| H4 | **El precio cambia en el tiempo.** Halloween `121963` en lista 06: $47.745,41 neto el 15/10, $47.585,36 el 19/10 y $54.059,22 el 21/10. El último coincide con el Excel del 22/10. | El precio se trae seguido, no una sola vez. Pregunta 3. |
| H5 | **Vigencia.** La cabecera no trae fechas. `113190` (turrón 50 al 20 %) se vendió el 22/10 y el 23/10 ya no está en la API. | La promo vale mientras el combo esté en `getCombos`. Hoy el sync le pone 30 días. |
| H6 | **El enfoque anterior dejaba afuera combos que se venden.** `AG14356` (bolsa mix caramelos, 16 u a $799,99) se vendió y hoy queda en el dry-run por "91 % de descuento". Los jugos `112408`–`112431` quedan afuera desde que GEV les sumó un renglón a $0,10. | Con combos cerrados entran tal cual, con el precio de GEV. |

### Preguntas para Xionico

1. ¿Qué endpoint o campo da el precio de un combo para una lista de precios, antes de armar el pedido? Lo necesitamos para mostrar el mismo número que su pantalla.
2. En `112528` (papas 2x1), el pedido trae 1 bolsa por combo y ningún regalo. ¿Se entregan 1 o 2 bolsas? Si son 2, ¿dónde viene la segunda?
3. ¿Cada cuánto cambia el precio de un combo? ¿Hay un campo de última modificación del precio?
4. `DEPOT`/`DPEOT` aparece solo con lista `99` y `AASS` con lista `99` y `02`. ¿Hay un campo que diga a qué listas o canales aplica cada combo?
5. Para inyectar: ¿el pedido debe llevar la línea del combo en `listadoDetallePedido` con `CODIGO_COMBO` y `PRECIO_UNITARIO_LISTA` igual al total neto, y los componentes en `listadoDetallePedidoCombo`, igual que su app?

## Cómo se espera que funcione

| Etapa | Esperado |
|---|---|
| Traer | Una promo por combo de `getCombos` que no sea de canal. Sus componentes salen tal cual de `getDetalleCombos`, con la cantidad por combo. El precio por lista sale de la fuente que indique Xionico (pregunta 1). Sin clasificar en %, pack, 2x1 ni regalo. |
| Presentar | Una tarjeta por combo, con el nombre de GEV, los componentes como texto («25 TURRON OBLEA…», «1 ROCKLETS… de regalo» si corresponde) y el precio del combo. El tachado es la suma de lista de los componentes, solo si es mayor. El buscador y el orden de la sección siguen funcionando. Los chips por tipo se revisan, porque dejan de existir %, pack y 2x1. |
| Cargar | «Agregar» o «dame N del combo X» deja **una línea de combo** × N al precio del combo. No escribe una línea por SKU. El stock del combo es el mínimo entre componentes. |
| Inyectar | En `listadoDetallePedido` va una línea con `CODIGO_COMBO`, `CANTIDAD_PEDIDA` = N y `PRECIO_UNITARIO_LISTA` = N × neto. En `listadoDetallePedidoCombo` van los componentes con cantidad = N × cantidad por combo, con el mismo `ID_DETALLE_PEDIDO`. |

## Casos con datos reales

Para cada caso: cargar la cantidad N del pedido real, una vez desde la tienda y otra desde el agente (`simulate-turn`, sesión de laboratorio). Vaciar el pedido entre corridas. **No confirmar.**

El total esperado es el de la línea real de GEV con IVA. Tolerancia: ±$0,05 por línea.

| Caso | Combo | Qué es | Componentes por combo | Precio por combo (final) | Excel | Pedido real de referencia | N | Total esperado |
|---|---|---|---|---|---|---|---|---|
| C1 | `112271` | Turrón 15 % llevando 25 | 25 × `4013` | $5.541,47 | $5.541,46 | `084720261022084557`, 22/10 | 2 | **$11.082,96** |
| C2 | `112422` | Jugo manzana «3x$1000» | 1 × `14430` | $4.744,01 | $4.744,01 | `084720261020124318`, 20/10 | 2 | **$9.488,02** |
| C3 | `112429` | Jugo multifruta + tableta Bon o Bon | 1 × `14431`, 1 × `15127` | $4.744,07 | $4.744,01 | `039520261021111448`, 21/10 | 1 | **$4.744,07** |
| C4 | `112528` | Papas 80 g «2x1» | 1 × `15316` (ver H3) | $1.987,93 | $1.987,93 | `084720261020094720`, 20/10 | 15 | **$29.819,01** |
| C5 | `113181` | Turrón 50 + Rocklets | 50 × `4013`, 1 × `10763` | $10.431,47 | $10.431,46 | `084720261021122112`, 21/10 | 1 | **$10.431,47** |
| C6 | `121962` | Pan dulce 24 % | 2 × `12727` | $9.952,38 | $9.952,38 | `112820261020124031`, 20/10 | 12 | **$119.428,57** |
| C7 | `113183` | Ramen pollo 20 % | 2 × `14996` | $1.957,61 | $1.957,61 | `084720261022105630`, 22/10 | 5 | **$9.788,05** |
| C8 | `112424` | Jugo durazno 50 % | 1 × `14439` | $2.790,60 | $2.790,60 | `084720261020131615`, 20/10 | 1 | **$2.790,60** |
| C9 | `113014` | 50 % un renglón | 1 × `13241` | $972,66 | $972,66 | `089820261015081942`, 15/10 | 5 | **$4.863,30** |
| C10 | `AG14356` | Bolsa mix caramelos | 16 × `14356` | $799,99 | $799,99 | `084720261019084549`, 19/10 | 3 | **$2.399,97** |
| C11 | `121963` | Halloween Golo, 10 componentes | 1 de cada uno; 5 × `15590` | $65.411,66 (precio del 21/10) | $65.411,64 | `084720261021094945`, 21/10 | 1 | **$65.411,66**, o el precio vigente que dé GEV (H4) |

En cada caso hay que revisar:

- **Tienda:** la tarjeta muestra el precio por combo. «Agregar» y el stepper dejan N combos, y el carrito y el banner de mínimo suman el total esperado.
- **Agente:** con «Quiero N del combo <nombre>», o «dame N promos de <producto>», carga N combos y el total del resumen es el esperado. El cliente no lee instrucciones internas.
- **Base:** queda una línea de combo con N y el precio por combo. Los componentes quedan asociados a esa línea.
- **Inyección:** en dry-run del push, el payload tiene la línea con `CODIGO_COMBO`, `CANTIDAD_PEDIDA` = N y `PRECIO_UNITARIO_LISTA` ≈ el valor del pedido real. `listadoDetallePedidoCombo` tiene los mismos componentes y cantidades que el pedido real.

### Casos que no tienen que aparecer (cliente de lista 20)

| Caso | Combo | Por qué |
|---|---|---|
| N1 | `113049` `DPEOT 4013` (25 %) | De canal: solo se vende con lista `99` (H2). En la tienda, «turrón» no la trae, y el agente no la ofrece. |
| N2 | `MATECLUBGO` | No está en `getCombos`. Componente pago a $1. |
| N3 | `113190` turrón 50 al 20 % | Se vendió el 22/10 y hoy no está en la API (H5). |
| N4 | Cualquier `AASS …` | De canal (H2). |

### Cuando se puede comparar con la pantalla de GEV

Si Almaro carga en su app la misma compra de C1, C4 y C11 para un cliente de lista 06, los tres totales (GEV, tienda y agente) tienen que coincidir. Es la prueba final de paridad.

## Estado de hoy, como punto de partida

- **C1** ya da $5.541,50 por combo en la tienda y en el agente, pero como 25 líneas de SKU con 15 %, no como una línea de combo.
- **C2** (jugo manzana) no se publica: el sync lo deja afuera desde que GEV le agregó el renglón a $0,10.
- **C4** (papas) se publica como «2x1» de 2 bolsas. La tienda y el agente cargan 2 unidades, y GEV pide 1 (H3).
- **C8** (jugo durazno 50 %) se publica y da $2.790,60, pero como línea de SKU con descuento.
- **C10** no se publica: queda en el dry-run por «91 %».
- Las pruebas del agente corren contra `fix/agente-promo-plural` (local, sin push). Las del backend, contra `feat/gev-promos-sin-canal` (#329).

## Resultados del 24 oct 2026

Se corrió con el modelo de combos como SKU, de 09:32 a 09:53 UTC. Después se revirtió con el sync de `main` y los productos combo salieron del catálogo.

- **Tienda (C1–C11):** cada combo entra como una línea y el total coincide con el pedido real (±$0,06). Excepción: C2 y C3, +$1,22 y +$0,55 por el regalo a $0,10 que GEV sumó el 23/10.
- **Agente:** C1, C4, C5, C6, C7 y C11 cargan el combo al precio del pedido real. C2 y C8 preguntan Arcor o BC. C10 no carga por stock 0.
- **Payload a GEV:** coincide con el pedido real (`113181` $8.621,05 neto). Se armó sin enviarlo.

Detalle, decisiones y pendientes en [`docs/specs/131-promociones-tres-modelos.md`](../../../docs/specs/131-promociones-tres-modelos.md).
