# Plan de prueba manual — promociones Almaro

Fuente: `implementacion/almaro/inputs/Promociones_Almaro_simple.xlsx` (copia del 23 oct 2026).
Tenant: `almaro`. Lista: Interior (10) o Tradicional (20). No confirmar un pedido de un cliente real.

## Dónde

| Canal | URL |
|---|---|
| Tienda | http://localhost:3002/almaro |
| Backend | http://localhost:8000 |
| Agente | http://localhost:8002 (no manda WhatsApp) |

Anotá cada fila: código, canal, OK o diferencia, qué viste.

## Cómo leer el Excel

- Hoja **Simples**: un solo producto.
- Hoja **Combinados**: más de un renglón. Si dice `REGALO`, el segundo ítem es el obsequio.
- El 2x1 de papas está en Combinados como «1 paga + 1 regalo del mismo SKU». En Suplai es una sola tarjeta `2x1`, cantidad 2, precio de una. No son dos líneas.

## Ronda 1 — tienen que estar en Promociones

Estas filas están en la base, lista Interior, después del sync.

| Código | Qué probar | Resultado esperado |
|---|---|---|
| 112527, 112528, 112529, 112530 | Papas 2x1. La cheddar es 112529 / SKU 15315 | Etiqueta `2x1`. Agregar deja 2 y el precio es el de una. El + de la tarjeta pasa a 4. El − de la tarjeta, desde 2, saca la línea |
| 113183, 113184, 113185, 113186 | Ramen bolsa, 2 unidades, 20% | Etiqueta `20% llevando 2`. El botón agrega 2. En esa tarjeta no hay +1 |
| 113187, 113188, 113189 | Ramen cup, 1 unidad, 20% | Etiqueta `20%`. El paso es 1, porque el pack es 1 |
| 112344 | Mate rojo tereré, 15% | Etiqueta `15%`. Agregar 1 al 15% |

Budines `113092`, `113093` y `113094` (15% desde 1) están en Suplai y no están en el Excel. Anotá si aparecen.

## Ronda 2 — no tienen que aparecer en Promociones

El sync las dejó afuera. Si ves alguna, es un fallo.

| Códigos | Por qué no |
|---|---|
| 112271 y 113190 | Turrón `3*$1000` y `3*$900`. El pack no baja de la lista con el tope del 90% |
| 113181 | Turrón 50 + Rocklets de regalo. El pack del título no pasa el tope, así que el combo entero queda afuera |
| 112408 a 112431 | Jugos `3x$1000`. El unitario del pack queda por encima del 90% de descuento |
| AG11834, AG11828, AG14356, AG10885, AG1782, AG15125, AG13289, 191259 | Precio de bolsa o display que el sync no publica como pack |
| 113011, 113014 | 50% en un solo renglón. Hoy no están entre las 15 de Interior |
| 121962 | Pan dulce 24%. No está en la base |
| 191258, 111271, 111265, 121963, 121964 | Bob, cajas de Navidad y Halloween. No son un regalo al 99% |
| HOGAR1, HOGAR2, IMPULSO2, 112487, 112488 | Combos con regalo del Excel. Hoy no hay filas `combo` en la lista Interior |

## Ronda 3 — catálogo, fuera de Promociones

- Una papa del 2x1, con el + del catálogo, entra de a 1 y a precio de lista. Puede decir «Hay promo».
- El turrón `4013` no está en Promociones. En el catálogo el paso es 10, no 1.

## Ronda 4 — agente

El proceso local no envía WhatsApp. Un turno de prueba no tiene que confirmar el pedido.

- «Dame un 2x1 de papas cheddar»: entra un pack de 2, sin preguntar sabores.
- Después de que liste las papas, «dame dos promociones de la primera»: entran dos packs (4 unidades).
- Pedir 1 ramen de pollo (`14996`): lo carga a lista y pregunta si quiere la promo de 2. «No» deja esa unidad a lista y no vuelve a preguntar ese SKU.
