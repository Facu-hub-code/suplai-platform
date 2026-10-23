# 130 — Sync GEV: cabecera del combo y precio del renglón

**Estado:** Borrador
**Fecha:** 2026-10-23
**Repos:** `backend-supabase`. La tienda y el agente no cambian: ya cobran `percent` y `precio_pack`.
**Rama sugerida:** `feat/gev-promos-cabecera` desde la rama del [127](./127-gev-promos-regalo-y-pack.md) si ese PR todavía no está en `main`. Si ya está, desde `origin/main`.
**Relaciona:** [127](./127-gev-promos-regalo-y-pack.md), [128](./128-tienda-seccion-promos-combo.md), [129](./129-agente-carga-promo.md)
**Tenant de prueba:** `almaro`. La misma lectura corre en `gonzales` porque el conector es `gev`.
**Fuente comercial:** `implementacion/almaro/inputs/Promociones_Almaro_simple.xlsx`, grabaciones del 22 oct 2026. Cruce contra la API el 23 oct 2026.

---

## Objetivo

El sync arma cada combo con dos endpoints: `GET /articulos/getCombos/` y `GET /combos/getDetalleCombos/`. El porcentaje de varias ofertas está en un tercero, `GET /combos/getCabeceraCombos/`, que hoy no se llama. Cuando el nombre trae `3*$1000`, el [127](./127-gev-promos-regalo-y-pack.md) toma ese texto como precio y descarta el combo. En la pantalla de Almaro ese texto no es el precio.

Este spec suma la cabecera del combo y usa el primer dato de precio que la API sí manda. El `Nx$` del nombre queda como último recurso, solo cuando no hay porcentaje ni precio de renglón.

### Criterios de aceptación

- El conector pide los tres endpoints y une por código de combo. `CODIGO_ARTICULO` de artículos y `CODIGO_COMBO` de cabecera y detalle son el mismo código (`112271`, `HOGAR1`, `AG15125`).
- `112271` se publica como 15% sobre 25 unidades de `4013`. No se lee como 3 por $1000.
- Un jugo `112408`–`112431` con `PRECIO_UNITARIO` 3920,67 y renglón `1 DI` se publica a $4.744,01 el display (neto × 1,21). El nombre `3x$1000` no define la cantidad ni el importe. `112424` es la excepción: la cabecera dice 50% y ese porcentaje gana.
- `113011`, `113014`, `121962`, `121963` y `121964` entran con el porcentaje de la cabecera. Los dos de Halloween son un combo cerrado: cada componente al 20%.
- `113181` entra como combo cerrado: 50 de `4013` al 20% y Rocklets de regalo. El `3*$900` del nombre no lo veta.
- `111265` entra como combo cerrado. El pan dulce `12727` queda al 24% y el resto a lista. Con las listas del 23 oct 2026 el total da $17.828,36, el mismo final del Excel.
- Un precio fijo se publica solo si el unitario queda debajo de la lista y el descuento es menor a 90%. `AG14356` (91,57%) queda en el dry-run.
- Papas 2x1, ramen, mate y los regalos de `HOGAR1`, `HOGAR2`, `IMPULSO2`, `112487` y `112488` siguen como en el 127.
- `113190` no está en la API el 23 oct 2026. El sync no lo inventa.
- La caja Bob `191258` y las bolsas sin descuento (`AG11834`, `AG11828`, `AG10885`, `AG1782`) no se publican.

---

## Qué trae cada endpoint

Lectura del 23 oct 2026, tenant `almaro`.

| Endpoint | Filas | Qué usa el sync |
|---|---:|---|
| `GET /articulos/getCombos/` | 172 | Código, nombre, activo. `DESCUENTO_DIRECTO` y `DESCUENTO_MAXIMO` vinieron en 0 en `112271`. No son el descuento de la oferta |
| `GET /combos/getDetalleCombos/` | 247 renglones, 174 combos | SKU, cantidad, `UNIDAD_MEDIDA`, `DESCUENTO` del renglón, `PRECIO_UNITARIO` neto |
| `GET /combos/getCabeceraCombos/` | 173 | `DESCUENTO` del combo, vigencia, `PRECIO_COMBO` |

`MATECLUBGO` está solo en la cabecera. `191261` está solo en el detalle. El resto de los códigos coincide.

`PRECIO_COMBO` en esta lectura vale `0` o `1`. No es un importe. `1` acompaña a los renglones que traen `PRECIO_UNITARIO`. El importe está en el renglón.

`FECHA_VIGENCIA_DESDE` y `FECHA_VIGENCIA_HASTA` vinieron vacías en las filas del Excel. El sync sigue guardando inicio hoy y fin a 30 días, como hoy hace `erp_promotion_sync_service.py`. La fecha de la pantalla (5 nov, 31 oct, 31 dic) no está en estos tres payloads.

---

## Cruce con el Excel

60 ofertas. 59 tienen fila en la API. Falta `113190` (`4013 3*$900`): el 23 oct 2026 no está en ninguno de los tres endpoints.

| Grupo | Códigos | Dato que cierra con el Excel | Qué hace este spec |
|---|---|---|---|
| Ya entra por el renglón | Mate `112344`, ramen `113183`–`113189`, papas `112527`–`112530` | El `DESCUENTO` del renglón, o el 99,99% del mismo SKU en el 2x1 | Sin cambio |
| Regalo de otro SKU | `112487`, `112488`, `HOGAR1`, `HOGAR2`, `IMPULSO2` | Renglones al 99,99% y el resto a lista. El % del Excel es el peso de lo regalado | Sigue la regla de regalo del 127 |
| Porcentaje en la cabecera, renglón vacío | `112271` 15% × 25, `113011` y `113014` 50%, `121962` 24% × 2, `112424` 50% | `DESCUENTO` de la cabecera. En `112424` el renglón además trae un neto que daría 15%: gana el 50% de la cabecera | Publicar ese porcentaje sobre la cantidad del renglón |
| Porcentaje de cabecera en varios SKU | Halloween `121963`, `121964` | Cabecera 20% y el Excel es 20% sobre la suma de listas | Combo cerrado, cada componente al 20% |
| Precio neto del renglón | Jugos `112408`–`112423` y `112425`–`112431`, `191259`, bolsas `AG15125` y `AG13289` | `PRECIO_UNITARIO` × 1,21 × cantidad. El jugo `13184`: 3920,67 × 1,21 = 4.744,01, igual al final del Excel, sobre 1 display de lista $5.581,19. El incluye dice «1 jugo», no 3 | `precio_pack` con la cantidad del renglón y ese importe con IVA. El `3x$1000` del nombre no se usa |
| Renglón con % más regalo, y un `Nx$` en el nombre | `113181` | 50 × `4013` al 20% + Rocklets a 0. El final del Excel ($10.431,46) es esa cuenta, no 3 × $900 | Publicar el renglón y el regalo. El título no veta |
| Un componente con % y el resto a lista | Navidad chica `111265` | Suma de listas $19.399,79. El 24% de `12727` son $1.571,43. Final $17.828,36, igual al Excel | Combo cerrado. El 24% queda en ese SKU. Los renglones sin descuento van a lista |
| Navidad mediana | `111271` | La suma de listas da $25.139,43, igual al Excel. El 24% del pan dulce no alcanza: el final de la pantalla es $23.141,41, $426,59 más barato | Se publica lo que dicen los renglones (pan dulce al 24%, resto a lista). No se inventa el $426 |
| Tope del 90% | `AG14356` | 16 × 41,3218 × 1,21 = $799,99, el final del Excel. Contra la unidad de lista es 91,57% | No se publica. El dry-run deja el porcentaje |
| Sin oferta en la API | Bob `191258` | Las cantidades por la lista de cada unidad suman $7.704,10, el final del Excel. No hay descuento | No se publica |
| Precio de pantalla que la API no trae | `AG11834`, `AG11828`, `AG10885`, `AG1782` | El Excel muestra $2.399,97 o $2.100 y dice «sin descuento». `PRECIO_UNITARIO` × cantidad × 1,21 da ~$800 o ~$700 | No se publica. Vender el neto de la API sería otro precio, y no es menor a la lista de la unidad |
| Ausente | `113190` | No está en la API | No se publica |

El `Nx$` del nombre no explica ninguna fila del Excel. En las que se pudo cerrar la cuenta, el precio salió de la cabecera o del renglón.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Tercer endpoint | `GET /combos/getCabeceraCombos/`, unido por `CODIGO_COMBO` | El 15% de `112271` y el 20% de Halloween están ahí. El renglón viene con `DESCUENTO` vacío | Seguir con artículos + detalle y leer el porcentaje del nombre |
| Orden de la oferta | 1) porcentaje de cabecera entre 0 y 90. 2) descuento del renglón o regalo al 99,99%. 3) `PRECIO_UNITARIO` neto × 1,21. 4) `Nx$` del nombre, solo si los tres anteriores no trajeron precio | `112424` tiene cabecera 50% y un neto que daría 15%. El Excel cobra 50%. El jugo cobra el neto, no el `3x$1000` | Dejar la regla del 127: el título pisa el renglón aunque después no pase el tope |
| `PRECIO_COMBO` | Se ignora como importe. Solo marca que el precio está en el renglón | En esta API vale 0 o 1 | Guardar `PRECIO_COMBO` como precio del pack |
| Cantidad del precio fijo | La de `CANTIDAD_ARTICULO`, convertida con la tabla de unidades del 127. No la N del título | El incluye del jugo es 1 display y el renglón es `1 DI`. 3 no aparece en el renglón | Usar el 3 de `3x$1000` |
| Escala del neto | `PRECIO_UNITARIO` × 1,21, misma escala que `precio_unidad` | 3920,67 × 1,21 = 4.744,01, el final del Excel. El conector ya multiplica este campo por 1,21 en `fetch_promotions` | Tratar el neto como precio final con IVA incluido |
| Tope del precio fijo | Unitario menor a la lista de esa lista de precios, y descuento menor a 90%. Si no, `skipped_precio_fijo` con código, SKU, neto, lista y porcentaje | `AG14356` es 91,57%. Publicarlo repite la escala del pedido 930 | Publicar todo neto que venga en el renglón |
| Comparación de unidades | El neto es el precio de una `UNIDAD_MEDIDA` del renglón, ya convertida a la UMV. Se compara contra `precio_unidad` | En `AG13289`, 7 UN a $349,27 contra lista $391,19 del display es el 10,72% del Excel. Comparar ese neto contra el precio del display entero inventa un 99% | Dividir siempre `precio_unidad` por `unidades_por_display` |
| Varios SKU con porcentaje de cabecera | `forma = cerrada`, `promo_scope = combo`, cada renglón `paga` a ese porcentaje | Halloween es 20% sobre la suma. Un 20% en cada componente da el mismo total | Una sola promo `single_sku` sobre un SKU «caja» que no existe en el catálogo |
| Caja con un solo renglón descontado | Combo cerrado. El renglón con porcentaje es `paga` a ese porcentaje. El renglón sin descuento es `paga` al 0%, o sea lista | `111265` cierra al centavo con el 24% del pan dulce | Dejar la caja afuera, como dice el 127, aunque el renglón ya trae el 24% |
| Hueco de `111271` | Se publica la cuenta de los renglones. No se ajusta para llegar a $23.141,41 | Esos $426,59 no están en cabecera, detalle ni artículo | Inventar un descuento extra para copiar la pantalla |
| `Nx$` en el nombre | Solo si la cabecera no tiene porcentaje, ningún renglón tiene descuento ni regalo, y no hay `PRECIO_UNITARIO` | Fuera de este Excel puede haber un combo que solo traiga el precio en el nombre. El 127 ya lo sabe leer y topear | Borrar el lector de título |
| Regalo | Igual que el 127. El título no anula un regalo cuando el renglón que se paga tiene su propio porcentaje | `113181` es 20% más Rocklets. El `3*$900` no es la oferta | Seguir descartando el combo entero si el pack del título no pasa el tope |
| Vigencia | Se deja el ventana de 30 días del sync | Los tres endpoints trajeron la vigencia vacía. La fecha del Excel no está en el payload | Llamar otro endpoint de agenda en esta entrega |
| Listas | Siguen siendo como máximo dos | No cambia el tope del 127. En Almaro, Interior y Tradicional | Copiar el combo a las 17 listas |
| Canal | Solo el sync y el clasificador del backend | Tienda y agente ya aplican `percent`, `precio_pack`, `dos_por_uno` y el regalo a 0 | Un PR de tienda o de agente para volver a leer el nombre |

---

## Alcance

### Incluido

- Llamar `GET /combos/getCabeceraCombos/` desde `GEVConnector.fetch_promotions` y pasar `DESCUENTO` de la cabecera al clasificador.
- El orden de la tabla de decisiones, con tests por cada fila de casos borde.
- Precio fijo del renglón como `mecanica = precio_pack`, `cantidad_pack` = cantidad convertida, `precio_pack` = neto × 1,21 × esa cantidad.
- Combo cerrado cuando la cabecera trae un porcentaje y hay más de un SKU.
- Combo cerrado cuando un renglón trae porcentaje y los otros no (`111265`).
- Dry-run con `skipped_precio_fijo` (código, SKU, neto, lista, porcentaje).
- Actualizar `docs/external/gev_erp.md` con el tercer endpoint y el significado de `PRECIO_COMBO`.

### Fuera de alcance

- Crear el código del combo como producto del catálogo.
- Publicar `113190` mientras no vuelva en la API.
- Copiar la fecha del Excel. La vigencia de estos combos vino vacía.
- Un endpoint de agenda de descuentos para explicar los $426 de `111271` o el precio de pantalla de las bolsas sin tachado.
- Subir o bajar el tope del 90%. `AG14356` queda afuera por ese tope.
- Publicar Bob `191258`. Es un armado a lista, sin descuento.
- Cambiar la tienda, el agente, el tope de dos listas o `cantidad_minima_de_venta`.
- Migración de tablas. `forma`, `mecanica`, `cantidad_pack`, `precio_pack` y `promocion_componentes` ya salieron en el 127.

---

## Regla de clasificación

Sobre renglones activos. La cabecera se lee aunque el artículo no haya venido. Si no hay cabecera, el porcentaje de cabecera es 0.

1. Si `DESCUENTO` de la cabecera es mayor a 0 y menor a 90, esa es la oferta. El `Nx$` del nombre y el `PRECIO_UNITARIO` no se usan. Un solo SKU: `single_sku`, `forma = cerrada`, mínimo = cantidad convertida. Etiqueta `15%` si la cantidad es 1, y `15% llevando 25` si es mayor. Varios SKU: `promo_scope = combo`, `forma = cerrada`, cada renglón `paga` a ese porcentaje, con su cantidad convertida.
2. Si no hubo porcentaje de cabecera y hay un renglón con descuento, o un regalo al 99,99%, corre la clasificación del 127 a partir de su regla 3 (2x1, bonificación del mismo SKU, regalo de otro SKU, combo cerrado, `single_sku`). El `Nx$` del nombre no se evalúa en este paso. Un renglón sin descuento, junto a otro que sí tiene porcentaje y sin nadie al 99,99%, es `paga` al 0%. Así entra `111265`. Un solo SKU al 99,99% sin 2x1 en el nombre sigue afuera.
3. Si no hubo porcentaje ni regalo, y algún renglón trae `PRECIO_UNITARIO` mayor a 0: un solo SKU. `fetch_promotions` ya multiplicó el neto por 1,21 antes de llegar al clasificador. El clasificador usa ese unitario y no lo vuelve a multiplicar. La cantidad es la del renglón, convertida. Se guarda `precio_pack` con esa cantidad y con importe = unitario × cantidad. Se publica si el unitario es menor a la lista y el descuento es menor a 90%. Si no, `skipped_precio_fijo`. El nombre no se lee.
4. Si tampoco hay precio de renglón y el nombre matchea `(\d+)\s*[*xX×]\s*\$\s*(\d+)`, sigue la regla 1 del 127, con el mismo tope.
5. Si no hubo nada de lo anterior: `skipped_zero_discount`. Ahí caen Bob y las bolsas cuyo neto no es una oferta.

La conversión de `UN`, `DI` y `BU` es la del 127. Si falta el factor, `skipped_unidad` y no se guarda la cantidad cruda.

`DESCUENTO` de cabecera mayor o igual a 90 no se publica y no se sigue con el neto ni con el título. En esta lectura no apareció ese caso. El dry-run lo deja en `skipped_precio_fijo` con el porcentaje de cabecera, el mismo tope que el precio fijo.

---

## Casos borde

Listas de Almaro del 23 oct 2026, Interior y Tradicional iguales en estos SKU.

| Caso | Entrada | Resultado |
|---|---|---|
| Turrón `112271` | Cabecera 15. Nombre `4013 15%OFF 3*$1000`. Renglón `4013` × 25 UN, descuento vacío, precio vacío. Lista $260,78 | 15% desde 25. No es 3 por $1000 |
| Jugo `112408` | Cabecera 0. Nombre `13184 3x$1000`. Renglón `13184` × 1 DI, neto 3920,67. Lista display $5.581,19 | `precio_pack` de 1 a $4.744,01. Descuento 15% |
| Jugo `112424` | Cabecera 50. El renglón trae el mismo neto 3920,67. Lista $5.581,19 | 50% desde 1 display. Final $2.790,60. El neto no se usa |
| Choclo `113011` | Cabecera 50. Renglón `9849` × 1 UN, descuento vacío | 50% desde 1 |
| Pan dulce `121962` | Cabecera 24. Renglón `12727` × 2 UN | 24% desde 2 |
| Halloween `121963` | Cabecera 20. Diez renglones sin descuento de línea | Combo cerrado, cada SKU al 20% |
| Turrón + Rocklets `113181` | Cabecera 0. Nombre con `3*$900`. `4013` × 50 al 20% y `10763` al 99,99% | Combo cerrado. 50 al 20% y el Rocklets a 0 si está el activador |
| Navidad chica `111265` | Cabecera 0. `12727` al 24% y seis renglones sin descuento | Combo cerrado. Solo el pan dulce al 24%. El total da $17.828,36 |
| Navidad mediana `111271` | Igual forma, un renglón al 24% | Se publica esa cuenta. El final de pantalla es $426,59 más bajo y no se persigue |
| Bolsa `AG15125` | Neto 233,0574 × 2 UN. Lista unidad $851 | `precio_pack` de 2. Unitario con IVA $282. Descuento 66,86% |
| Bolsa `AG13289` | Neto 288,6565 × 7 UN. UMV display, lista $391,19 | `precio_pack` de 7. Descuento 10,72% |
| Bolsa `AG14356` | 16 × neto 41,3218 × 1,21 = $799,99. Descuento 91,57% | No se publica. `skipped_precio_fijo` |
| Bolsas sin tachado | `AG11834`, `AG11828`, `AG10885`, `AG1782`. El neto × cantidad × 1,21 no es el final del Excel y no baja de la lista de la unidad | No se publica |
| Bob `191258` | Cuatro renglones sin descuento, cabecera 0, sin neto | No se publica |
| `113190` | No viene en los tres endpoints | No se publica |
| Papas `112529` | 1 UN + 1 UN al 99,99%, cabecera 0 | Sigue 2x1 al 50%, como el 127 |
| Mate `112344` | Renglón al 15%, cabecera 0 | Sigue 15% desde 1 |
| Título solo, sin cabecera, sin renglón y sin neto | Un combo fuera de este Excel cuyo nombre es `3x$1000` y el unitario no pasa el tope | Sigue `skipped_precio_titulo`, como el 127 |
| Cabecera de `MATECLUBGO` sin artículo | Los renglones siguen activos | Se clasifica por los renglones. El nombre sale de `DESCRIPCION_COMBO` |
| Vigencia vacía | `FECHA_VIGENCIA_HASTA` null | Inicio hoy, fin a 30 días |

---

## Orden de implementación

Depende del 127: el clasificador, `precio_pack` y `promocion_componentes` tienen que estar en la rama.

| Orden | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `backend-supabase` | `feat/gev-promos-cabecera` | Conector, clasificador, tests, doc del ERP |

No hay PR de tienda ni de agente. El precio que este sync escribe ya lo calculan `promociones_pricing_service.py` y la copia del agente.

Dentro del backend:

1. `fetch_promotions` pide la cabecera y la adjunta al combo (`descuento_cabecera`). El detalle sigue exponiendo `PRECIO_UNITARIO` ya multiplicado por 1,21.
2. `classify_gev_combo` aplica el orden de arriba. El título deja de ser el primer paso.
3. El dry-run suma `skipped_precio_fijo` y su detalle. El script `scripts/test_xionico_promociones_sync.py` lo imprime.
4. Nota de operación: el job de 6 horas tiene que correr este código. Si Railway sigue con el sync anterior, el próximo ciclo borra las filas de prefijo `PROMO ERP (GEV):` que este clasificador insertó.

---

## Migración de base de datos

Sin migración de BD.

---

## Plan de prueba en CI/CD

Extender `tests/test_erp_promociones_sync.py` con una fila por caso borde de este spec. El conector se mockea: no hay red. Cada test arma el combo con los tres pedazos (artículo, cabecera, detalle) y espera el `promo_scope`, la mecánica, la cantidad y el importe.

Tienen que quedar verdes, además, los tests del 127 que no cambian de regla: papas 2x1, ramen, regalo de otro SKU, y el descarte del 99,99% suelto. El test del 127 que espera que `3*$1000` del título pise un renglón con porcentaje se reemplaza: si el renglón o la cabecera traen porcentaje, el título no gana.

No hay smoke de migración. No hay SQL nuevo.

---

## Plan de prueba humana

Backend en el puerto 8000, con `SCHEDULER_ENABLED=false`. Tenant `almaro`. No confirmar un pedido de un cliente real.

1. `PYTHONPATH=. ./venv/bin/python scripts/test_xionico_promociones_sync.py --schema almaro --dry-run`
2. En el dry-run, `112271` mapea al 15% con mínimo 25. No aparece como pack de 3 a $1000.
3. Un jugo, por ejemplo `112408`, mapea con `precio_pack` de 1 display a $4.744,01. `112424` mapea al 50%.
4. `113181` mapea con componente `4013` al 20% y Rocklets `regalo`. `111265` mapea con `12727` al 24% y el resto a lista.
5. `AG14356`, Bob `191258`, las cuatro bolsas sin tachado y `113190` no están entre las mapeadas. `AG14356` figura en `skipped_precio_fijo`.
6. Papas `112527`–`112530`, ramen `113183`–`113189` y mate `112344` siguen mapeadas.
7. Después del `--apply`, `GET /almaro/tienda/promociones?lista_precios_id=10` muestra el turrón al 15% llevando 25 y un jugo a $4.744,01. La sección de promociones de la tienda, en `http://localhost:3002/almaro`, agrega el turrón de a 25 y el jugo de a 1 display.

El `--apply` reescribe las promos de prefijo `PROMO ERP (GEV):` en las listas Interior y Tradicional. Conviene correrlo cuando el job de producción ya tenga este código, o volver a aplicarlo después del deploy.
