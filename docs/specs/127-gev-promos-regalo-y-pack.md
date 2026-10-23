# 127 — Promos GEV que faltan: regalo y pack cerrado

**Estado:** Borrador  
**Fecha:** 2026-10-22  
**Repos:** `backend-supabase`. El precio del agente se copia en el [129](./129-agente-carga-promo.md).  
**Rama sugerida:** `feat/gev-promos-regalo` desde `origin/main`  
**Relaciona:** [128](./128-tienda-seccion-promos-combo.md), [129](./129-agente-carga-promo.md), censo en el canvas de combos de Almaro del 20 oct 2026  
**Tenant de prueba:** `almaro`. La misma regla corre en `gonzales` porque el conector es `gev`.

---

## Objetivo

El sync de Xionico deja afuera los combos cuyo regalo es otro SKU, y aplana el resto a un porcentaje sobre un producto suelto. Este spec agrega el combo con componentes (lo que se paga y lo que se regala) y, cuando el título trae un precio cerrado, vende ese pack en lugar del porcentaje del renglón.

Cada promo queda marcada `forma = cerrada` o `forma = combinable`. La cerrada se agrega entera. La combinable es un pozo de sabores con un mínimo, y este spec calcula los armados prearmados (mitad y mitad, partes iguales, todo de un sabor) para que la tienda y el agente ofrezcan los mismos números.

La tienda consume eso en el [128](./128-tienda-seccion-promos-combo.md). El diálogo del agente, en el [129](./129-agente-carga-promo.md). El precio del agente sigue en su copia `app/agent/promotions/pricing.py`, con las mismas reglas que `promociones_pricing_service.py`.

### Criterios de aceptación

- Un combo con al menos un renglón `paga` y al menos un renglón `regalo` de otro SKU (descuento del renglón ≥ 90) se persiste como `promo_scope = combo`. El regalo no queda como un `single_sku` al 99,99%.
- El precio del regalo es 0 solo cuando el pedido cumple la cantidad de cada componente `paga` de ese combo. Si falta un activador, el regalo vuelve a precio de lista.
- Un 2x1 sigue siendo 50% y el descuento cubre pares completos. La unidad que sobra queda a lista.
- Un título `Nx$` o `N*$` se lee como pack: N unidades por ese importe total. Se publica si el unitario del pack es menor a la lista y el descuento contra esa lista es menor a 90%. Si no, queda en el dry-run y no se publica.
- Un descuento ≥ 90 sobre un único SKU, sin ser 2x1 ni bonificación del mismo SKU, sigue sin sincronizarse.
- Los porcentajes legítimos (budines, mate, ramen, papas 2x1) siguen entrando. `113190` y los `3x$1000` pasan por el lector de título y por el tope del 90%. Con las listas del 21 oct 2026, el jugo display a $5.581 con título `3x$1000` da un unitario de $333 (94% off) y no se publica. El turrón `3*$900` como 3 unidades sale a $300, por encima de la lista de $261, y tampoco se publica.
- `pull_promotions` sigue en true. El job de 6 horas usa esta regla.
- Una promo de varios SKUs que GEV manda con cantidad por renglón queda `forma = cerrada`. Un grupo mix armado en Suplai queda `forma = combinable`.
- Para una combinable, la función de armados devuelve las opciones prearmadas del objetivo. Mitad y mitad, partes iguales y todo de un sabor salen de la misma función en la tienda y en el agente.

---

## Cómo viene el combo hoy

Lectura del 20 oct 2026: `GET /articulos/getCombos/` (171 cabeceras) y `GET /combos/getDetalleCombos/` (252 renglones). Dos detalles no tienen cabecera (`MATECLUBGO` y uno vacío). El censo da 173 combos.

| Familia | Combos | Qué hace el sync actual |
|---|---:|---|
| 2x1 del mismo SKU | 4 | Entra como 50% desde 2 |
| Porcentaje de un SKU | 12 | Entra. Uno de esos doce es el turrón `113190`, hoy guardado como 20% desde 50 aunque el título dice `3*$900` |
| Regalo de otro SKU | 9 | Se descarta (`skipped_unsupported_combos`) |
| Precio `Nx$` solo en el título | 23 | Se descarta porque `DESCUENTO` es nulo. Este spec los lee y los publica solo si el pack queda debajo de la lista y el descuento es menor a 90% |
| Kits, bolsas y un % que el renglón no trae | 23 | Se descarta |
| DEPOT y AASS sin descuento | 102 | Se descarta |

El renglón útil es `CODIGO_ARTICULO`, `CANTIDAD_ARTICULO`, `DESCUENTO`, `UNIDAD_MEDIDA` (`UN`, `DI`, `BU`) y `ACTIVO`. `PRECIO_UNITARIO` en los `3x$1000` repite el mismo importe en displays distintos. No es el precio de la promo. `UNIDAD_MINIMA_VENTA` de la cabecera casi siempre es 0. En ocho bolsas es 3, y esas bolsas no traen descuento.

El modelo actual (`promociones_semanales.promo_scope` en `single_sku` | `sku_group`, `discount_kind` en `percent` | `nominal` | `fixed_price`) no tiene un rol de regalo. El sync GEV escribe siempre `percent`.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Alcance de esta entrega | Combo con regalo estructurado, pares del 2x1, y pack leído del título | El regalo es el hueco del pedido 930. El título `Nx$` es el precio que GEV no manda en `DESCUENTO` | Dejar el `Nx$` afuera |
| Representación | `promo_scope = combo` más filas en `promocion_componentes` (`paga` o `regalo`) | El porcentaje suelto no puede decir «este SKU va a 0 si el otro está» | Seguir aplanando el regalo a un % del activador |
| Precio del regalo | 0 solo con los activadores cumplidos, recalculado en cada armado del pedido | El 99,99% suelto fue el incidente del pedido 930 | Publicar el SKU de regalo con 99% de descuento |
| 2x1 | Sigue en `single_sku` al 50%, y el precio promo cubre `floor(cantidad / 2) * 2` unidades | Comprar 3 no puede dejar las 3 a mitad de precio | `max_qty_umv = 2`, que corta la promo en el segundo pack |
| Título `N*$` o `Nx$` | Pack de N a $P en total. `PRECIO_UNITARIO` del renglón no se usa. El $ está en la misma escala que `precio_unidad` y no se vuelve a multiplicar por 1,21 | En Almaro ese campo repite el mismo importe en displays distintos. El usuario pidió vender el importe del título. `3x$1000` es 3 por $1000, no $1000 cada uno | Tratar el título como un porcentaje, o como precio unitario |
| Guardado del pack | `mecanica = precio_pack`, `cantidad_pack`, `precio_pack` | `fixed_price` de hoy, una vez superado el mínimo, aplica el unitario a todas las unidades. La cuarta unidad de un pack de 3 tiene que volver a lista | Reusar `fixed_price` sin marcar que el descuento es por pack |
| Tope al publicar | Unitario del pack menor a la lista y descuento menor a 90%. Si no, `skipped_precio_titulo` | El jugo `13184` lista a $5.581 el display. 3 por $1.000 es 94% off. El turrón 3 por $900 sale a $300 contra lista $261. Publicar eso repite la escala del pedido 930 | Publicar el título aunque el descuento supere el 90% o supere la lista |
| Etiqueta visible | La arma el sync (`2x1`, `20% llevando 2`, `3x$1000`) | El título de GEV a veces omite la cantidad (ramen `14996 20%` con cantidad 2) | Mostrar `DESCRIPCION_ARTICULO` tal cual cuando contradice los números |
| Unidad del renglón | `UN` / `DI` / `BU` se convierte a la UMV del catálogo antes de guardar la cantidad | Un `1 DI` con UMV unidad y display de 50 son 50 unidades | Copiar `CANTIDAD_ARTICULO` cruda |
| Listas | Siguen siendo como máximo dos, las de más clientes | No cambia el tope actual. En Almaro son Interior y Tradicional | Copiar el combo a las 17 listas activas |
| Forma | `cerrada` o `combinable` | La cerrada tiene cantidades fijas. La combinable deja elegir el reparto, como Topline 7: 2x1 llevando 20 entre sabores | Tratar todo `sku_group` como mix, incluso un combo de GEV que pide 10 de A y 10 de B |
| Armados prearmados | Una función pura en el backend. La tienda y el agente muestran su salida | «Mitad y mitad» tiene que ser el mismo 10 y 10 en los dos canales. Hoy `pack_items_for_promo` reparte el mínimo en partes iguales y lo carga sin preguntar | Que cada canal invente el reparto, o seguir cargando ese reparto automático |
| Canal | La tienda usa `promociones_pricing_service`. El agente actualiza su copia en `app/agent/promotions/pricing.py` con las mismas reglas | El agente no importa ese servicio. Si la copia queda vieja, un regalo cargado por WhatsApp se cobra a lista o con el % anterior | Unificar los dos módulos en un paquete compartido en esta entrega |
| Cajas sin regalo al 99% | Fuera de esta entrega | Navidad descuenta un componente al 24% y el resto va a lista. No hay precio del combo | Inventar un precio de caja |
| DEPOT, AASS y bolsas sin descuento | Fuera | No son una oferta con descuento. El mínimo 3 de la bolsa es dato de catálogo, no una promo | Tratarlos como combo vendible |

---

## Alcance

### Incluido

- Clasificar cada combo de GEV en: porcentaje de un SKU, 2x1, bonificación del mismo SKU, grupo con todos los renglones descontados, combo con regalo, pack leído del título, unidad sin factor, inactivo, sin descuento, pack de título que no pasa el tope.
- Leer `Nx$` y `N*$` del título y guardarlo como pack, con el tope del 90% contra la lista.
- Persistir el combo con regalo y sus componentes.
- Precio: regalo a 0 con activadores cumplidos; 2x1 por pares; pack leído del título solo en múltiplos completos; el resto de los porcentajes como hoy. La misma cuenta en `promociones_pricing_service.py` y en `app/agent/promotions/pricing.py`.
- Si el título tiene precio, no publicar el porcentaje del renglón. `113190` deja de quedar como 20% desde 50.
- Tests de los casos borde de abajo.
- La etiqueta, la `forma` y los armados prearmados viajan en la promo para que el [128](./128-tienda-seccion-promos-combo.md) y el [129](./129-agente-carga-promo.md) no reparen el título ni inventen el reparto.

### Fuera de alcance

- Dar de alta el código del combo como producto del catálogo.
- Cajas de Navidad, Halloween, Bob y aderezos.
- Copiar `UNIDAD_MINIMA_VENTA` de la cabecera a `cantidad_minima_de_venta`.
- El diálogo del agente y los rieles del grafo. Eso es el 129.
- El armador visual de la tienda. Eso es el 128.
- Subir el tope de dos listas.

---

## Regla de clasificación

Sobre renglones activos.

1. Si el título matchea `(\d+)\s*[*xX]\s*\$\s*(\d+)`, esa es la oferta y el porcentaje del renglón no se publica, aunque el pack después no pase el tope. N se cuenta en la `UNIDAD_MEDIDA` del renglón que se paga y se convierte con la tabla de abajo. La palabra `DI` dentro del título no cambia la unidad si el renglón dice `UN`. Un `15%OFF` en el mismo título no pisa el importe. N del título pisa `CANTIDAD_ARTICULO` cuando los dos números no coinciden. El unitario es `P / N` ya convertido, en la misma escala que `precio_unidad`. Si ese unitario es mayor o igual a la lista de esa lista de precios, o el descuento es mayor o igual a 90%, no se publica (`skipped_precio_titulo`) y el dry-run deja N, P, la lista y el porcentaje. Si pasa el tope, se guarda `mecanica = precio_pack`, `cantidad_pack = N`, `precio_pack = P`. Si además hay un regalo de otro SKU, el pack es la parte `paga` y el regalo sigue la regla 5 solo cuando el pack pasó el tope. `113181` no lo pasa. El combo entero queda afuera: el Rocklets no se publica a 0.
2. Sin ningún `DESCUENTO > 0` y sin pack de título publicado: `skipped_zero_discount`.
3. El título dice 2x1 y hay un solo SKU: se guarda como hoy, 50% y mínimo 2, después de convertir la unidad. El precio, de ahora en más, cubre pares completos.
4. Un solo SKU, una parte a 0% y otra a ≥ 90%: bonificación del mismo SKU, como hoy (`llevá total, pagá la parte paga`).
5. Hay un renglón ≥ 90 de un SKU y otro renglón de otro SKU, o el mismo SKU aparece a la vez como línea paga y como línea al 99,99% junto con otro código: es combo con regalo. Cada línea a ≥ 90 es `regalo`. Cada línea por debajo de 90 es `paga`. Si el paso 1 publicó un pack, ese pack reemplaza el porcentaje del renglón `paga`. Mate Club y los combos de helados entran por acá. `113181` tiene la forma del regalo y además un `3*$900`: el pack no pasa el tope contra la lista, y el combo entero no se publica.
6. Todos los renglones con descuento entre 0 y 90, más de un SKU, y cada uno con su cantidad: `forma = cerrada`, `promo_scope = combo`. Cada renglón es un componente `paga` con esa cantidad. No es un pozo: 10 de A y 10 de B no se pueden reemplazar por 20 de A. El `sku_group` que ya existe, armado a mano como mix, sigue `forma = combinable`.
7. Un solo renglón con descuento entre 0 y 90: `single_sku`, `forma = cerrada`. La etiqueta es `20% llevando 2` cuando la cantidad convertida es mayor a 1, y `15%` cuando es 1.
8. Un solo SKU al ≥ 90 sin 2x1 en el título: se omite. Es el caso del pedido 930.

El 2x1 de un solo SKU y el `precio_pack` son `forma = cerrada`. El regalo también.

`MATECLUBGO` no tiene cabecera. Si los renglones están activos, se clasifica igual y el nombre visible sale de la etiqueta generada (`Combo MATECLUBGO`).

### Conversión de unidad

| `UNIDAD_MEDIDA` | UMV del catálogo `unidad` | UMV `display` |
|---|---|---|
| `UN` | la cantidad del renglón | la cantidad, si el display es la unidad de venta |
| `DI` | cantidad × `unidades_por_display` | la cantidad |
| `BU` | cantidad × `unidades_por_bulto` | cantidad × `displays_por_bulto` |

Si el factor falta o es menor a 1, el combo no se sincroniza (`skipped_unidad`). No se guarda la cantidad cruda.

### Precio en el pedido

La función de la tienda vive en `services/promociones_pricing_service.py`. `tienda_pedidos_service` la llama. No se duplica la cuenta en el router. El agente no importa ese módulo: `app/agent/tools/orders/pricing.py` llama `app/agent/promotions/pricing.py`. Esta entrega copia ahí las reglas nuevas (pares, regalo a 0 con activadores, `precio_pack` por múltiplos). No se extrae un paquete común.

- Componente `regalo`: precio unitario 0 si cada componente `paga` del mismo `promocion_id` está en el pedido con cantidad mayor o igual a la suya. Si el activador baja, el regalo pasa a precio de lista en el recálculo.
- Un SKU de regalo agregado solo, sin activador, queda a lista. No se rechaza el SKU.
- 2x1: unidades a precio promo = `floor(cantidad / 2) * 2`, al 50%. El resto a lista.
- Porcentaje con mínimo (ramen, budín): igual que hoy. Debajo del mínimo, lista. Desde el mínimo, el % en las unidades del renglón.
- `precio_pack`: entran packs completos. Con cantidad `q` y pack `N` a `$P`, las unidades a ese precio son `floor(q / N) * N` y el unitario es `P / N`. El resto queda a lista. Comprar 3 paga 1000. Comprar 6 paga 2000. Comprar 4 paga 1000 más una unidad a lista.
- El porcentaje de un componente `paga` no crea, además, una promo `single_sku` de ese SKU. `113190` y `113181` no quedan publicados con las listas del 21 oct 2026, porque el pack leído del título no pasa el tope.
- Dos combos no se apilan sobre el mismo regalo. Gana el combo cuyos activadores estén cumplidos. Si los dos están cumplidos, gana el de mayor ahorro y el otro no descuenta ese SKU.
- Combinable con mecánica 2x1: el pozo es la suma de los sabores. Con la suma en un múltiplo del mínimo, las unidades a 50% son `floor(suma / 2) * 2`, repartidas en el orden de las líneas. El resto de esa suma queda a lista. Topline 7 con mínimo 20 y reparto 5+5+5+5 deja las 20 al 50%.

### Armados prearmados

Solo para `forma = combinable`. Vive en `services/promocion_armados.py`. No escribe el pedido. Devuelve opciones. El 128 y el 129 las muestran y, si el cliente elige una, mandan esas cantidades.

Entrada: miembros en orden estable, `objetivo` (packs × `min_qty_umv`), lo que ya está en el pedido por SKU, `cantidad_minima_de_venta` y stock.

Una opción es válida si la suma da el objetivo, cada cantidad es 0 o llega al mínimo de venta de ese SKU, ninguna baja lo que ya está cargado, y el stock alcanza para el delta. Se descartan las repetidas.

| Orden | Cuándo | Etiqueta | Ejemplo, objetivo 20 y cuatro sabores |
|---|---|---|---|
| 1 | El reparto en partes iguales cierra | `Mitad y mitad` si hay dos sabores y el resto es 0. Si no, `Partes iguales` | 5, 5, 5 y 5 |
| 2 | Un sabor se lleva el objetivo y el resto queda en 0 | `Todo {nombre}` | 20 de menta |
| 3 | Ya hay unidades cargadas y falta para el objetivo | `Completar parejo` | Van 10 de menta: suma 5 y 5 en dos sabores que todavía están en 0 |

La tienda muestra `Mitad y mitad` o `Partes iguales`, `Completar parejo` si existe, y hasta cuatro `Todo {nombre}`. El resto de los «todo» no se esconde del dato: el agente los puede nombrar y la tienda los arma con los steppers. Si un preset no pasa el mínimo de venta o el stock, no viaja.

---

## Casos borde

| Caso | Entrada | Resultado |
|---|---|---|
| Papas 2x1, cantidad 2 | `112529`, 1 UN + 1 UN al 99,99% | 50% sobre las 2. Etiqueta `2x1` |
| Papas 2x1, cantidad 3 | El mismo, el cliente carga 3 | 2 al 50% y 1 a lista |
| Papas 2x1, cantidad 1 | Carga suelta | Lista. La promo no aplica |
| Ramen `14996 20%` con cantidad 2 | Renglón 2 UN al 20% | 20% desde 2. Etiqueta `20% llevando 2` |
| Budín 15% cantidad 1 | Renglón 1 UN al 15% | 15% desde 1 |
| Turrón `4013 3*$900` | `113190`. Lista $260,78 la unidad. Pack leído: 3 por $900, unitario $300 | No se publica. $300 no es menor a la lista |
| Turrón + Rocklets | `113181`, título `3*$900` y Rocklets al 99,99% | No se publica. El pack paga no pasa el tope, y el regalo no sale solo |
| Jugo `3x$1000` | `13184`, UMV display, lista $5.581, renglón 1 DI. Pack: 3 displays por $1.000 | No se publica. Unitario $333 contra $5.581 es 94% off |
| Pack que sí pasa el tope | N y $P tales que `P/N` es menor a la lista y el descuento es menor a 90% | `precio_pack`. Etiqueta `3x$1000` |
| Pack publicado, cantidad 4 con N = 3 | El mismo, el cliente carga 4 | Un pack al importe del título y 1 a lista |
| Título `15%OFF 3*$1000` | Hay un importe y un porcentaje en el nombre | Manda el importe. Después corre el tope |
| Regalo con activador cumplido | Helados hogar, o Mate Club, con todas las líneas `paga` | Cada `regalo` a 0 |
| Regalo sin el activador | Solo el SKU de regalo en el pedido | Precio de lista |
| Se baja un activador | El combo estaba completo y se quita una línea `paga` | El recálculo devuelve los regalos a lista |
| Mate Club | Seis renglones, cinco al 99,99%, uno a lista, sin cabecera | Un combo. Los cinco regalos a 0 si está el activador `503516` |
| Helados hogar | Varios `paga` y dos regalos al 99,99% | Un combo. Falta un activador y ningún regalo va a 0 |
| Navidad | Un componente al 24%, el resto sin descuento, nadie al 99% | No entra. No es regalo |
| `3x$1000` con `DESCUENTO` nulo | El importe sale del título. `PRECIO_UNITARIO` se ignora | Pasa o no según el tope contra la lista. El jugo de arriba no pasa |
| `14439 50%` con descuento nulo | El % está solo en el título | No entra |
| Línea `1 DI` y el catálogo no tiene `unidades_por_display` | Factor ausente | No entra |
| SKU de regalo fuera del catálogo | El código no está en `productos` | El combo no entra |
| Renglón `ACTIVO = 0` | Se ignora | Si no queda un paga y un regalo, no entra |
| Mismo SKU a lista y al 99,99%, más otro SKU | `H.DEPOT 13020` | Combo: la línea al 99,99% es regalo, las otras son paga |
| Descuento 99,99% y un solo SKU, título sin 2x1 | Caso pedido 930 | No entra |
| Bonificación 60 + 6 del mismo SKU | Ya cubierto en Gonzales | Sigue entrando, sin componentes de regalo de otro código |
| Combo duplicado | Misma firma de componentes, cantidades y descuentos | Una sola promo, como el filtro de duplicados actual |
| GEV con 10 de A y 10 de B, ambos con % | Dos renglones entre 0 y 90 | `forma = cerrada`. 20 de A no cumple |
| Topline 7, mínimo 20, cuatro sabores | Combinable, objetivo 20, nada cargado | `Partes iguales` es 5+5+5+5. `Todo menta` es 20. No hay `Completar parejo` |
| Topline 7 con 10 de menta ya en el pedido | Objetivo 20 | `Todo menta` suma 10. `Partes iguales` 5+5+5+5 no viaja, porque bajaría la menta. `Completar parejo` reparte las 10 que faltan |
| Dos packs de Topline | Objetivo 40 | Las mismas etiquetas, con el doble de unidades |
| Sabor con mínimo de venta 10 y objetivo 20 en tres sabores | Partes iguales daría 7, 7 y 6 | Esa opción no viaja. `Todo` de un sabor sí, si 20 alcanza el mínimo |

---

## Orden de implementación

| Orden | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `backend-supabase` | `feat/gev-promos-regalo` desde `origin/main` | Migración, sync, precio de tienda y el `GET` |
| 2 | `agente-conversacional-multi_tenant` | `feat/gev-promos-precio` desde `origin/master` | La copia de precio. Mergea después del backend, cuando las columnas ya existen. El diálogo es el 129 |

En el backend:

1. Migración del `CHECK` de `promo_scope`, columnas del pack, `forma` y tabla de componentes, por tenant.
2. Clasificación y persistencia en `erp_promotion_sync_service.py`.
3. Precio en `promociones_pricing_service.py` y armados en `services/promocion_armados.py`.
4. El `GET /{schema}/tienda/promociones` devuelve `etiqueta`, `forma`, `mecanica`, `cantidad_pack`, `precio_pack`, `promo_scope`, `armados` y, en los combos, `componentes` (`rol`, `product_code`, `nombre`, `cantidad`, `descuento_percent`). `armados` va vacío en una cerrada. El [128](./128-tienda-seccion-promos-combo.md) y el [129](./129-agente-carga-promo.md) mergean después.

En el agente, este PR solo toca `app/agent/promotions/pricing.py` y sus tests. Las tools y los rieles quedan en el 129.

---

## Migración de base de datos

Por cada schema de tenant que ya tiene `promociones_semanales`:

- Ampliar `promociones_semanales_promo_scope_chk` a `single_sku`, `sku_group`, `combo`. El patrón es el de `sql/62_promociones_grupo_mix_and_match.sql`: dropear el check, no usar `CASCADE`.
- Agregar en `promociones_semanales`: `forma` (`cerrada` | `combinable`, default `cerrada`), `mecanica` (nulo, o `percent` | `precio_pack` | `dos_por_uno` | `combo`), `cantidad_pack` (nulo o mayor a 0) y `precio_pack` (nulo o mayor a 0). `precio_pack` exige `cantidad_pack`. Las filas viejas quedan `cerrada`, salvo el `sku_group` ya existente, que pasa a `combinable`.
- Crear `{schema}.promocion_componentes` con `promocion_id` FK a `promociones_semanales` `ON DELETE CASCADE`, `product_code`, `rol` (`paga` | `regalo`), `cantidad > 0`, `descuento_percent` nulo o entre 0 y 90, `orden`.
- Índice único `(promocion_id, product_code, rol, orden)` para permitir el mismo SKU como paga y como regalo (`H.DEPOT`).

La migración no recalcula descuentos. El único backfill es `forma`: `sku_group` pasa a `combinable` y el resto queda `cerrada`. El próximo sync de 6 horas reconcilia las filas GEV: saca el 20% del turrón `113190` porque el título manda, y no lo vuelve a insertar mientras el pack no pase el tope. Inserta los combos con regalo que sí clasifican. Las promos armadas a mano, sin el prefijo `PROMO ERP (GEV):`, no se tocan.

Rollback: volver el check a los dos scopes deja de poder borrar filas `combo` hasta que se borren esas promos. El rollback operativo es correr el sync anterior y borrar las filas `combo` de ese prefijo antes de restaurar el check.

---

## Plan de prueba en CI/CD

Extender `tests/test_erp_promociones_sync.py`, `tests/test_promociones_pricing_service.py` y un test nuevo de `promocion_armados` con la tabla de casos borde. Cada fila es un test de clasificación, de precio o de un armado. En el agente, la misma tabla de precio cubre `app/agent/promotions/pricing.py` (junto a `tests/test_promociones_grupo.py`). Un caso de par: cantidad 3 en un 2x1 deja una unidad a lista en los dos repos. Un caso de regalo: sin el activador, el SKU de regalo queda a lista en los dos repos. Un caso de armado: Topline con objetivo 20 y cuatro sabores devuelve partes iguales 5+5+5+5 y un «todo» por sabor.

Checks que tienen que seguir verdes: la suite de promociones y la de sync GEV que ya cubre 2x1, bonificación del mismo SKU y el descarte del 99,99% suelto.

No hay smoke de migración en CI contra Supabase. El SQL se revisa en el PR y se aplica en el entorno de staging antes del merge a `main`.

---

## Plan de prueba humana

Backend en el puerto 8000. Tenant `almaro`.

1. Dry-run del script `backend/scripts/test_xionico_promociones_sync.py --schema almaro --dry-run`.
2. En el dry-run, `113190`, `113181` y un `3x$1000` de jugo (por ejemplo `13184`) figuran en `skipped_precio_titulo` con N, el importe, la lista y el porcentaje. No están entre las promos mapeadas. Mate Club o un combo de helados vigente aparece con componentes `paga` y `regalo`.
3. Confirmar que las cuatro papas siguen en 50% desde 2, y que un pedido de prueba con cantidad 3 deja una unidad a lista.
4. Confirmar que Mate Club o, si la API lo sacó, el combo de helados que siga vigente arma componentes paga y regalo.
5. Confirmar que una promo manual de otro tenant GEV (`gonzales`) que no lleva el prefijo ERP sigue en la base después del sync.
6. `GET /almaro/tienda/promociones` con la lista Interior o Tradicional devuelve `etiqueta`, `forma` y, en los combos, `componentes`. En una combinable, `armados` trae las opciones de un pack.

---

## Preguntas que este borrador ya cierra

Quedan escritas como decisión para poder implementar. Si una se responde al revés, se cambia esta sección y la tabla de decisiones antes de codear.

1. El título `Nx$` o `N*$` se lee y se vende como pack de N por ese importe total. Confirmado el 21 oct 2026. El tope sigue: si el unitario no es menor a la lista, o el descuento es de 90% o más, no se publica. Con las listas de ese día, el turrón `3*$900` y el jugo `3x$1000` quedan en el dry-run y no en la tienda.
2. El regalo de otro SKU entra en esta entrega. Las cajas sin renglón al 99% no. Un `Nx$` que además trae regalo solo entra si el pack pasa el tope.
3. Comprar el SKU suelto sigue permitido a precio de lista, con el mínimo del producto. Confirmado el 21 oct 2026. El regalo a 0 exige el pack. La sección de promociones de la tienda, en el 128, no ofrece el suelto.
4. La carga es cerrada o combinable, por tienda o por agente. Confirmado el 22 oct 2026. La cerrada se agrega entera. La combinable tiene un segundo paso de reparto, con opciones prearmadas y la posibilidad de dictar las cantidades.
