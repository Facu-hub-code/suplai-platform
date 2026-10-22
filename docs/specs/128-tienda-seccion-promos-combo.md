# 128 — Tienda: la sección Promociones vende el combo

**Estado:** Borrador  
**Fecha:** 2026-10-22  
**Repos:** `wholesale-catalog-app`, y el mínimo de cantidad en `backend-supabase`  
**Rama sugerida:** `feat/tienda-promos-combo` desde `origin/main`, después de mergear el [127](./127-gev-promos-regalo-y-pack.md)  
**Relaciona:** [127](./127-gev-promos-regalo-y-pack.md), [129](./129-agente-carga-promo.md)  
**Tenant de prueba:** `almaro`, lista Interior o Tradicional, un cliente con sesión de tienda.

---

## Objetivo

La sección Promociones de la tienda hoy filtra el catálogo y muestra el producto suelto, con el precio ya descontado y un paso de +1. Un 2x1 se ve como una papa con «50% OFF» y «A partir de 2», y el botón suma una unidad.

La sección pasa a mostrar el objeto promo. Si `forma = cerrada`, un botón agrega el pack entero (`Agregar 2x1`, `Agregar 2 con 20%`, `Agregar 3x$1000`, `Agregar combo`). Si `forma = combinable`, la ficha abre un armador: opciones prearmadas y un paso por sabor. El alta se habilita cuando la suma cierra el objetivo.

El catálogo general sigue vendiendo el SKU a lista. Ahí el piso es `cantidad_minima_de_venta` del producto, y el backend lo rechaza si el request viene por debajo. Si ese SKU entra en una promo, la tarjeta dice «Hay promo» y lleva a la ficha. El precio lo calcula el [127](./127-gev-promos-regalo-y-pack.md).

### Criterios de aceptación

- En Promociones no hay una tarjeta de producto suelto. Hay una tarjeta por promo de la lista del cliente.
- Una cerrada se agrega con un botón. Un 2x1 manda cantidad 2. Un `20% llevando 2` manda 2. Un `precio_pack` manda `cantidad_pack`. Un combo con regalo manda una línea por componente.
- Una combinable muestra los `armados` del 127 y un stepper por sabor. `Agregar` manda el reparto solo cuando la suma es el objetivo. `Mitad y mitad` o `Partes iguales` llena los steppers de un toque. `Todo {sabor}` también.
- El + y el − de una tarjeta cerrada saltan de a un pack. En el carrito, `cart-line-card` salta `cantidad_minima_de_venta`, porque la misma línea puede sumar unidades sueltas del catálogo.
- `POST` de una línea con `cantidad_solicitada` menor a `cantidad_minima_de_venta` responde 400. El turrón, con mínimo 10, no acepta 1 aunque el request lo arme a mano.
- Con 3 unidades de un 2x1, el precio es dos al 50% y una a lista. La tarjeta de promos no ofrece armar esa cantidad: llega desde el catálogo.
- Un combo con un componente sin stock no se puede agregar. La tarjeta se ve y el botón no dispara el alta.

---

## Cómo está hoy

`catalog-client.tsx` con `activeSection === "promos"` pide `GET /{schema}/tienda/productos` y se queda con los `product_code` que tienen promo activa. Cada ítem es un `ProductCard`.

Esa tarjeta muestra el precio final de `calculatePromotionPrice` aunque la cantidad del carrito sea 0, el texto «A partir de N» si `min_qty_umv > 1`, y `handleIncrement` suma 1. `addToCart` manda `add_lines` con esa cantidad.

`tienda_pedidos_service.tienda_patch_pedido` controla que el producto esté en catálogo y tenga precio. No compara `cantidad_solicitada` con `cantidad_minima_de_venta`. El mínimo de compra del pedido se evalúa al confirmar. El precio promo, en `promociones_pricing_service`, sí exige `min_qty_umv` para aplicar el descuento. Por eso la tarjeta puede mostrar 50% y el pedido de una unidad cobrar lista, o al revés si el front ya mostró el precio promo.

En Almaro el turrón `4013` tiene `umv_tipo = unidad`, display 50, bulto 200 y `cantidad_minima_de_venta = 10`. El paso de la tarjeta es 1. El botón de display suma 50 porque `unidades_por_display` está cargado. El bot, en otro canal, sube una cantidad chica hasta el mínimo del producto. La tienda no.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Unidad de la sección | Una tarjeta por promo, no por SKU | El 2x1 y el regalo son una condición, no un producto con badge | Seguir filtrando `ProductCard` |
| Alta cerrada | Un botón que manda el pack completo | «Agregar 2x1» tiene que coincidir con lo que entra al pedido | Un stepper que arranca en 1 y «avisa» el mínimo |
| Alta combinable | Armador con opciones prearmadas y steppers | Topline 7 se arma 5 y 5 y 5 y 5, o todo de un sabor, o a mano. El cliente no tiene que adivinar el reparto | Un solo botón que reparte el mínimo en partes iguales y lo carga |
| Paso de la cerrada | El pack. Cero elimina la línea | En esa ficha no se suma de a 1 | Paso 1 con el descuento recién al llegar al mínimo |
| Catálogo | Sigue el SKU suelto, a lista, con piso `cantidad_minima_de_venta` | Comprar una papa a lista tiene que seguir existiendo. El 2x1 es la promo, no la única forma de venta | Bloquear el SKU en todo el sitio mientras haya promo |
| Precio en el catálogo | La tarjeta de catálogo, búsqueda, favoritos y home no muestra el unitario de la promo. Puede decir «Hay promo» si la promo está vigente y enlazar a la sección | `calculatePromotionPrice` hoy ignora `min_qty_umv` y pinta el % aunque la cantidad sea 0. `isPromotionActive` solo corre en la pestaña Promos, así que el resto del catálogo puede mostrar una promo vencida | Seguir tachando el precio de lista en el `ProductCard` general |
| Precio en la tarjeta | Total del pack, y al lado el de lista tachado | El cliente ve lo que va a pagar por el botón, no el unitario ya descontado de una unidad | Mostrar el % sobre la unidad y «a partir de N» |
| Etiqueta | La que genera el [127](./127-gev-promos-regalo-y-pack.md) | El título de GEV a veces omite la cantidad (ramen `14996 20%` con cantidad 2) y a veces anuncia un precio que el tope no deja publicar | `DESCRIPCION_ARTICULO` cruda |
| Combo con regalo | Una llamada agrega todas las líneas | Si el cliente tiene que buscar el Rocklets, el regalo no se cumple | Descontar el activador y esperar que agregue el regalo |
| Stock | Si un componente no alcanza para un pack, no se agrega | Un combo partido cobra el regalo a lista o deja el pedido incompleto | Agregar lo que haya y avisar |
| Cantidad mínima de catálogo | El `GET /tienda/productos` expone `cantidad_minima_de_venta`. El + del catálogo y el de `cart-line-card` saltan ese mínimo. El backend igual responde 400 si llega menos | El tipo `Product` de la tienda hoy no tiene ese campo. Solo trae `unidad_minima_de_venta` y el precio. Sin el campo, la UI no puede ocultar el paso de 1 | Subir la cantidad en silencio, como hace el bot |
| Paso del carrito | `cart-line-card` salta el mínimo del producto, no el pack | La misma línea puede mezclar el pack y unidades sueltas del catálogo. Forzar múltiplos del pack borraría esa compra | Hacer que el − del carrito baje de a un pack aunque el cliente haya sumado sueltos |
| Carrito mezclado | Si el catálogo sumó unidades sueltas, el carrito de ese SKU puede quedar en un valor que no es múltiplo del pack. El precio lo resuelve el 127 | Esas unidades son compra a lista, no un pack roto de la sección Promos | Forzar el carrito entero a múltiplos y borrar la compra suelta |

---

## Alcance

### Incluido

- Sección Promociones renderizada desde `GET /{schema}/tienda/promociones`, no desde el filtro de productos.
- Tarjeta cerrada: etiqueta, componentes con cantidad, precio del pack, botón de alta, stepper de a un pack.
- Tarjeta combinable: los `armados` del GET, un stepper por sabor, contador `suma/objetivo`, y `Agregar` habilitado solo cuando la suma cierra.
- Carrito: `cart-line-card` sube y baja de a `cantidad_minima_de_venta`. No fuerza múltiplos del pack.
- El `GET /tienda/productos` incluye `cantidad_minima_de_venta`, y el + del catálogo lo usa como paso.
- Backend de tienda: `add_lines` y `line_updates` rechazan `cantidad_solicitada` menor a `cantidad_minima_de_venta`.
- Alta de combo: un body con varias líneas (activadores y regalos) en el mismo patch.
- Vacío de la sección cuando no hay promos para esa lista. El catálogo y «Nuevos ingresos» quedan como están.

### Fuera de alcance

- Rediseñar la grilla del catálogo para que el paso sea el display de 50 en todo SKU con `umv_tipo = unidad`. El spec `014-comprar-por-display` deja el +/− en 1 UMV y el botón Display aparte. Este spec no lo cambia: el botón Display sigue sumando `unidades_por_display`. El único piso nuevo del catálogo es `cantidad_minima_de_venta`.
- Cambiar el agente. El diálogo, las tools y los rieles están en el [129](./129-agente-carga-promo.md).
- Backoffice de alta manual de promos.

---

## Tarjeta y cantidades

La promo de la lista del cliente es la fuente. Dos filas de la misma promo en dos listas no se ven juntas: el cliente tiene una lista.

| Promo | Tarjeta | El botón manda | El stepper |
|---|---|---|---|
| 2x1 | `2x1` y el nombre del producto. Total = una unidad a lista | 2 del SKU | 2, 4, 6… y eliminar |
| `20% llevando 2` | Esa etiqueta y el nombre | 2 del SKU al 20% | De a 2 |
| `15%` con mínimo 1 | `15%` y el nombre | 1, que es el pack | De a 1, porque el pack es 1 |
| Combo con regalo | Etiqueta, cada paga con su cantidad y cada regalo como «de regalo» | Una línea por componente | Otro pack suma otra vez esas cantidades |
| `precio_pack` (`3x$1000`) | La etiqueta del 127 y el total del pack | `cantidad_pack` del SKU | De a `cantidad_pack`. En 3, el − saca la línea. No queda en 1 ni en 2 |
| Combinable | Etiqueta, mínimo y un stepper por sabor | El reparto cuya suma es el objetivo | Cada sabor de a su mínimo de venta. El contador muestra `10/20` |

El precio de una cerrada es el total del pack que devuelve el `GET /tienda/promociones`. El de una combinable es la suma de los sabores elegidos, con el descuento del 127 sobre el pozo. No sale de `calculatePromotionPrice`.

En el catálogo, la búsqueda, los favoritos y el home, `ProductCard` deja de usar el precio promo. Puede marcar «Hay promo» si `isPromotionActive` es verdadero y llevar a la sección. El + del catálogo suma `cantidad_minima_de_venta` cuando ese valor es mayor a 1, y 1 cuando es 1 o el campo no vino. No suma el pack de la promo. El botón Display sigue como está.

`handleIncrement` de la tarjeta cerrada no existe como +1. El primer toque es el botón del pack. En la combinable, el primer toque puede ser una opción prearmada, que llena los steppers, o un sabor. `Agregar` recién escribe el pedido.

Si el carrito ya tiene 10 de menta y el objetivo es 20, el armador abre con esas 10 contadas. `Todo menta` propone sumar 10. `Partes iguales` de 5+5+5+5 no se muestra, porque obligaría a bajar la menta. `Completar parejo` reparte las 10 que faltan. Esas tres reglas salen de `armados` en el GET, recalculadas con lo ya pedido. Un control de packs (1, 2, 3) cambia el objetivo a 20, 40, 60 y vuelve a pedir los armados.

En el carrito, `cart-line-card` no usa el paso del pack: sube y baja de a `cantidad_minima_de_venta`. Una línea que nació en 2 por el 2x1 y después sumó 1 desde el catálogo queda en 3, y el precio lo parte el 127.

---

## Backend de la tienda

En `services/tienda_pedidos_service.py`, al agregar y al actualizar una línea:

- Leer `cantidad_minima_de_venta` del producto junto con el nombre.
- Si `cantidad_solicitada` es menor, responder 400 con el mínimo y el `product_code`. No subir la cantidad por atrás.
- El mismo control corre en `line_updates`. Bajar de 10 a 1 en el turrón también falla.
- Cantidad 0 no entra por este control: eliminar la línea sigue siendo el delete que ya existe.

El patch de un combo manda todas las líneas juntas. Si una falla por stock o por mínimo, no queda la otra escrita. La transacción que ya envuelve el patch alcanza si el rechazo ocurre antes del commit. Hay que verificarlo en el servicio y, si hoy hace commit por línea, envolver el alta del combo en una sola transacción.

El recálculo de precio posterior al patch es el del 127. La tienda no manda el precio unitario de la promo. Lo resuelve el servidor, como hoy con `resolve_effective_price`.

---

## Casos borde

| Caso | Qué hace el cliente | Qué tiene que pasar |
|---|---|---|
| 2x1 de papas | Toca `Agregar 2x1` | El pedido queda con 2. El precio es una unidad, equivalente al 50% sobre las dos |
| 2x1, segundo toque | Toca + en la tarjeta | Pasa a 4, no a 3 |
| 2x1, menos | Está en 2 y toca − | Sale la línea. No queda en 1 |
| 2x1 desde el catálogo | Suma 1 en la grilla general | Entra 1 a precio de lista. La sección Promos no participó |
| 2x1, catálogo suma otra | Ya hay 2 de la promo y suma 1 en el catálogo | Quedan 3. El precio es el par al 50% y una a lista |
| Ramen 20% llevando 2 | Toca el botón | Entran 2 al 20%. No hay forma de mandar 1 desde esa tarjeta |
| Budín 15% mínimo 1 | Toca el botón | Entra 1 al 15%. El paso 1 es el pack |
| Combo de helados o Mate Club | Toca `Agregar combo` | Entran todas las líneas `paga` y cada `regalo` a 0 |
| Combo y después se quita un activador | Borra una línea `paga` | El recálculo pasa los regalos a lista |
| Combo sin stock de un regalo | Abre Promociones | La tarjeta no agrega. El mensaje dice qué componente falta |
| Turrón suelto, mínimo 10 | En el catálogo intenta cantidad 1, o un request manual manda 1 | La UI no ofrece 1. Si llega igual, el backend responde 400 |
| Turrón, cantidad 10 | Desde el catálogo | Entra a lista. El mínimo del producto es 10. El `3*$900` no se publica con las listas del 21 oct 2026, así que no hay tarjeta de ese pack |
| Pack `3x$1000` publicado | Una promo de prueba con `mecanica = precio_pack`, N = 3 | El botón dice `Agregar 3x$1000` y manda 3. El precio del pedido es el `precio_pack`. El + siguiente manda 6. En Almaro, el jugo real no aparece: el 127 lo deja en el dry-run |
| Promo de otra lista | El cliente es Tradicional | No ve la fila de Interior |
| Sin promos | Lista sin filas vigentes | El vacío actual de la sección, sin grilla de productos |
| `sku_group` combinable, nada en el carrito | Abre Topline 7, mínimo 20, cuatro sabores | Ve `Partes iguales` (5+5+5+5) y hasta cuatro `Todo {sabor}`. `Agregar` sigue apagado en 18 |
| `Mitad y mitad` | Dos sabores, objetivo 20 | Un toque deja 10 y 10. `Agregar` escribe esas dos líneas |
| Topline con 10 de menta ya cargadas | Abre el armador | El contador dice `10/20`. No ofrece el 5+5+5+5. Ofrece completar parejo y todo menta |
| Dos packs | Sube el control de packs a 2 | El objetivo pasa a 40 y las opciones se recalculan |
| Reparto a mano | Pone 5, 5, 5 y 5 | `Agregar` se habilita. 5, 5, 5 y 4 lo deja apagado |
| Dos packs y stock justo para uno | Stock alcanza para un pack y no para dos | El segundo + no se manda y lo dice la tarjeta |
| Invitado | Toca el botón sin sesión | Sigue el modal de registro, y al volver se agrega el pack, no 1 |

---

## Orden de implementación

| Orden | Repo | Rama | Depende de |
|---|---|---|---|
| 1 | `backend-supabase` | `feat/gev-promos-regalo` | El [127](./127-gev-promos-regalo-y-pack.md), que trae `etiqueta`, `componentes` y el precio |
| 2 | `backend-supabase` | `feat/tienda-minimo-de-venta` o el mismo PR del 128 si sale junto | Puede ir en paralelo con el 127. Es el 400 por `cantidad_minima_de_venta` y el campo en `GET /tienda/productos` |
| 3 | `wholesale-catalog-app` | `feat/tienda-promos-combo` | El contrato de `GET /tienda/promociones` ya con etiqueta y componentes |

Merge: backend primero, tienda después. Sin el 127, la tienda puede mostrar las promos actuales (2x1 y porcentaje) armando el pack con `min_qty_umv` y una etiqueta local. Esa etiqueta local se borra cuando el 127 está en el entorno. Una promo `precio_pack` usa `cantidad_pack` y `precio_pack` del GET. No se muestra el título crudo de GEV.

---

## Migración de base de datos

Sin migración en este spec. El `CHECK` de `promo_scope` y `promocion_componentes` están en el 127.

El rechazo por cantidad mínima no agrega columnas. Lee `productos.cantidad_minima_de_venta` y lo incluye en `GET /{schema}/tienda/productos`.

---

## Plan de prueba en CI/CD

Backend: un test de `tienda_patch_pedido` (o del servicio que ya cubra el patch) donde `cantidad_minima_de_venta = 10` y `cantidad_solicitada = 1` devuelve 400, y cantidad 10 pasa el control de mínimo. Otro test: cantidad 10 con un 2x1 no aplica, porque el mínimo de promo y el mínimo de catálogo son distintas reglas. El 2x1 se cubre en los tests de precio del 127.

Tienda: si el proyecto no tiene test de componente de esta grilla, el hueco queda explícito. El mínimo del PR de tienda es el test de la función que, dada una promo, devuelve la cantidad del pack y la etiqueta del botón (`2x1` → 2 y «Agregar 2x1»; mínimo 1 → 1; `precio_pack` con N = 3 y etiqueta `3x$1000` → 3 y «Agregar 3x$1000»). Otro test: con `armados` de 5+5+5+5, elegir `Partes iguales` deja esa suma y habilita `Agregar`; con suma 18 lo deja apagado. No alcanza con un render estático.

Checks existentes de tienda y de `tienda_pedidos_service` tienen que seguir verdes.

---

## Plan de prueba humana

Backend en el puerto 8000. Tienda en el puerto 3002 (`BACKEND_URL=http://localhost:8000`), para no pisar el backoffice en el 3000.

Cliente de `almaro` cuya lista sea Interior o Tradicional.

1. Abrir Promociones. Cada tarjeta es un combo. No aparece la papa suelta con «A partir de 2» y un + de una unidad.
2. `Agregar 2x1` en papas. El pedido queda en 2. El precio equivale a pagar una.
3. El + de esa tarjeta pasa a 4. El − de la tarjeta, desde 2, saca la línea y no la deja en 1. En el carrito, el − de esas 2 papas puede dejar 1, porque el mínimo de venta de la papa es 1, y esa unidad queda a lista.
4. En el catálogo, sumar 1 de esas papas. Entra a precio de lista.
5. Ramen `20% llevando 2`: el botón agrega 2 y el precio es el 20%. No hay +1 en esa tarjeta.
6. Combo con regalo (helados o Mate Club, el que esté vigente): un botón, varias líneas, el regalo en 0. Bajar un activador y confirmar que el regalo vuelve a lista antes de confirmar el pedido.
7. Pedir el turrón suelto con cantidad 1 desde el catálogo. No se ofrece, y un request con cantidad 1 responde 400.
8. Cliente de otra lista: no ve la promo de Interior si su lista es otra.
9. Confirmar un pedido de un 2x1 y verificar que el total persistido coincide con el de la tarjeta.
10. En una combinable de prueba (Topline 7 o un `sku_group` de la lista), tocar `Partes iguales` y agregar. El pedido queda con el reparto de esa opción, no con un solo sabor. Tocar `Todo` de un sabor y ver que las 20 van a ese SKU.

---

## Preguntas que este borrador ya cierra

1. En Promociones no se vende el suelto. En el catálogo sí, a lista, respetando el mínimo del producto. Confirmado el 21 oct 2026.
2. El paso 1 desaparece en la promo cerrada cuando el pack es mayor a 1. Un 15% desde 1 sigue sumando de a uno, porque ese es el pack. Un `3x$1000` suma de a 3. En la combinable, cada sabor suma de a su mínimo de venta, y el alta espera a que la suma cierre.
3. El display de 50 no reemplaza al paso de todo el catálogo. El turrón deja de aceptar 1 porque su mínimo de catálogo es 10. Con las listas del 21 oct 2026 no hay tarjeta de promo para ese turrón: el pack `3*$900` no pasa el tope del 127.
4. El armador ofrece mezclas listas y también el reparto a mano. Confirmado el 22 oct 2026. Las cantidades de «mitad y mitad», «partes iguales» y «todo de un sabor» salen del 127.
