# 112 — El atajo de precios no recotiza el listado anterior si el mensaje nombra otra cosa

**Estado:** Borrador. Sin rama ni implementación. El archivo queda en el working tree de `main` de `suplai-platform` porque el pedido fue revisarlo y specquearlo sin abrir rama.  
**Fecha:** 2026-10-13  
**Repos:** `agente-conversacional-multi_tenant` (riel PRE `catalog_price_quote` y `resolve_catalog_price_targets`).  
**Rama sugerida al implementar:** `feat/atajo-precio-listado` en el agente, desde `origin/master`.  
**Relaciona:** spec 127 del agente (`docs/specs/127-combo-catalog-listing-snapshot-and-price-pre-rail.md`), spec 048 del agente (snapshot de `search_products`), [108](./108-agente-busqueda-por-categoria.md).  
**Tenant de los casos:** `almaro`.

---

## Objetivo

Si el cliente nombra otro producto o otra categoría, el turno tiene que buscar de nuevo con `search_products`. El riel que responde `Te paso los precios:` solo cotiza el último listado cuando el mensaje pide el precio de lo que ya se mostró.

Hoy ese riel, con un snapshot de cinco SKU o menos, trata cualquier texto que contenga `precio` o `cuánto` como “cotizá todo el snapshot”. No mira si el mensaje nombra otra cosa. El turno no llega al modelo ni a `search_products`.

### Criterios de aceptación

- Con el snapshot de Pringles de la sesión de laboratorio, el texto guardado del caso 1 (`Golosinas` más la consigna que dice `código y precio`) no devuelve códigos Pringles. El riel no corta el turno.
- `La Galletita Diversion cuánto está?` contra el snapshot de Chocolinas del 7/10 no devuelve `14322`, `13939`, `14324`, `13940` ni `14323`.
- `me pasarias precio de los 3 combos` contra el listado de tres combos de helado sigue devolviendo `COM-HEL-INICIAL`, `COM-HEL-MEDIO` y `COM-HEL-PREMIUM` (test ya existente del spec 127).
- `cuánto está?` o `precio`, sin otro nombre de producto, contra un snapshot de hasta cinco ítems, sigue cotizando ese snapshot.
- `cuánto está la chocolina?` contra un snapshot mixto de Chocolinas y Coquitas cotiza solo las filas cuyo nombre cubre `chocolina`.
- Un snapshot de un solo SKU no se cotiza si el mensaje nombra un producto que no está en ese nombre (`cuánto está la diversion` después de haber mostrado solo Opera).
- La respuesta del riel, cuando sí cotiza, no agrega `No pude cotizar en catálogo:` para SKU que `get_product_by_code` rechaza. Si ninguno cotiza, el riel no corta el turno.

---

## Qué pasó

Los dos casos son el mismo riel. El formato (viñeta, precio con punto de miles, código entre backticks) sale de `_run_catalog_price_quote_guard` en `app/agent/seller/rails/catalog.py`. El nodo PRE `catalog_price_quote` corre antes del modelo. Si arma una respuesta, el turno termina ahí.

La puerta es `looks_like_specific_product_question`: alcanza con `precio`, `cuánto está`, `tenés`, u otra pregunta de catálogo. Después `resolve_catalog_price_targets` hace esto, en este orden:

1. Si el texto dice `los N` o `N combos`, devuelve los primeros N del snapshot.
2. Si el snapshot tiene un solo ítem, devuelve ese código.
3. Si dice `todos` / `todas` / `cada uno`, devuelve el snapshot (tope 20).
4. Si hay un ordinal (`el 2`, `opción 1`), devuelve esa posición.
5. Si el texto tiene `precio` o `cuánto` y el snapshot tiene 5 ítems o menos, devuelve **todos** los códigos.

El paso 5 es el que dispara los dos casos. No compara el nombre pedido con los nombres del snapshot.

El snapshot que lee es el último `catalog_search_snapshot` o `conversation_listing_snapshot` de la conversación (`load_latest_listing_snapshot`). En estos hilos es el último `search_products`, no la prosa que vio el cliente. Sin snapshot, el riel no hace nada: por eso la misma consigna de laboratorio en una sesión vacía busca bien.

### Caso 1 — laboratorio, 12/10

| | |
|---|---|
| Conversación | `78317`, schema `almaro`, sesión `mcp-lab-5493585098671` |
| Turno malo | `request_id` `6ff6e6b1-09d6-47de-9d3e-623f0de480d9`, 12/10 13:27 ART |
| Texto guardado | `El cliente escribe: "Golosinas". El agente debería mostrar golosinas concretas con código y precio, sin preguntar entre HALLOWEEN GOLOSINAS y NAVIDAD GOLOSINAS.` |
| Snapshot vigente | `search_products` query `Pringles`, cinco SKU `7026333`, `7026334`, `7026323`, `7026329`, `7026324` (eventos `147655` y `147658`, 07:57 ART). Los turnos de “Golosinas” de las 08:19 no escribieron snapshot: el modelo preguntó entre categorías. |
| Respuesta | `Te paso los precios:` con esas cinco Pringles. |
| Tools del turno | Ninguna fila en `core.agent_tool_executions`. |

`Golosinas` solo no entra a la puerta (`looks_like_specific_product_question` es falso) y `resolve_catalog_price_targets` devuelve `[]`. La consigna completa sí entra, porque contiene la palabra `precio`, y el paso 5 devuelve las cinco Pringles.

La sesión limpia es la conversación `78359`, sesión `mcp-lab-80`, mismo texto de consigna a las 13:27 ART. No había snapshot previo. El riel devolvió vacío, corrió `search_products` con query `golosinas` y la respuesta lista Mogul y Mr Pops.

Esa misma sesión, dos minutos después, repite el fallo con la categoría que acaba de mostrar. El turno `79be53a4-4715-44ac-b868-2e3f6226edad` guarda `El cliente escribe: "Qué tenés de navidad?". … con código y precio.` y responde `Te paso los precios:` con el snapshot de Navidad del turno anterior. No hay `catalog_search_snapshot` en ese `request_id`.

### Caso 2 — Vigay Julia, 7/10

| | |
|---|---|
| Conversación | `74337`, schema `almaro`, sesión `5493794608089` |
| Turno malo | `request_id` `batch-1791384985977`, 7/10 11:56:26 ART |
| Texto | `La Galletita Diversion cuánto está?` |
| Snapshot vigente | `search_products` query `Chocolinas` a las 11:43:47 ART (`145782`): `14322` CHOCOLINAS 40X170G, `13939` CHOCOLINAS 40X150G, `14324` CHOCOLINAS 50X100G, `13940` CHOCOLINAS 25X262G, `14323` CHOCOLINAS 25X250G |
| Respuesta | Las tres Chocolinas con stock, más `No pude cotizar en catálogo: 13939, 13940`. Latencia del turno: menos de un segundo. |
| Tools del turno | Ninguna fila en `core.agent_tool_executions`. |

El mensaje anterior del asistente (`145783`) había mostrado tres Chocolinas y dos Coquitas (`14325`, `14326`). El riel no usa esa prosa: usa el último tool snapshot, que es solo la búsqueda de Chocolinas. `13939` y `13940` están `en_catalogo` y tienen precio, con `stock = 0`. `get_product_by_code` los rechaza por falta de stock y el riel los imprime como códigos que no pudo cotizar.

El turno siguiente, `La Surtido?` (`batch-1791384994541`), no tiene `cuánto` ni `precio`. El riel no corta. Hay `search_products` query `Surtido Bagley` y el primer resultado con stock de esa búsqueda es `SURTIDO DIVERSION 21x400G` (`14336`).

### Reproducción local

Contra el código actual del agente, sin LLM ni base:

| Texto | Snapshot | Puerta | Códigos que devuelve el resolver |
|---|---|---|---|
| `Golosinas` | 5 Pringles | no | `[]` |
| Consigna de laboratorio del caso 1 | 5 Pringles | sí | los 5 Pringles |
| `La Galletita Diversion cuánto está?` | 5 Chocolinas | sí | `14322`, `13939`, `14324`, `13940`, `14323` |
| `me pasarias precio de los 3 combos` | 3 combos | sí | los 3 `COM-HEL-*` |
| `cuánto está?` | 5 Chocolinas | sí | las 5 Chocolinas |
| `precio` | 5 Pringles | sí | las 5 Pringles |

Logs de Railway no agregan nada: el riel llama `get_product_by_code` en proceso, no como tool del grafo, y no escribe `agent_tool_executions`. La evidencia durable es `core.conversation_events` más la ausencia de tools en ese `request_id`.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Reemplazar el fallback “`precio`/`cuánto` y snapshot de hasta 5 → todos los códigos” | Queda solo si el mensaje no tiene ningún token de producto. `cuánto está?` y `precio` siguen cotizando el snapshot (hasta 5). Si hay tokens, no se devuelve el snapshot entero por el solo hecho de decir precio | Ese fallback es el paso que ignora el producto pedido. Con cinco Pringles o cinco Chocolinas, cualquier frase que diga precio recotiza esa búsqueda. Borrarlo del todo también apaga `cuánto está?`, que es el atajo que hay que conservar | Dejar el fallback igual y filtrar solo la consigna `El cliente escribe`. Arregla el laboratorio y deja vivo el caso de Vigay. |
| Un token de producto que no está en ningún nombre del snapshot anula el atajo | Sí. El resolver devuelve `[]` y el riel no corta el turno | `Golosinas`, `Diversion` y `Halloween` no están en Pringles ni en Chocolinas. Buscar de nuevo es el comportamiento esperado. | Resolver el nombre adentro del riel con otra búsqueda. El riel existe para no llamar al modelo cuando el precio ya está en el listado. Si el nombre es otro, tiene que correr `search_products`. |
| Sin token de producto, el atajo se queda | `cuánto está?`, `precio`, `precio de esos`, `los N`, `todos` siguen cotizando el snapshot | Es el caso del spec 127. El cliente pide el precio de lo que acaba de ver. | Cotizar solo si hay un código o un ordinal. `cuánto está?` volvería al modelo y el atajo dejaría de cumplir lo que se pidió. |
| Si los tokens de producto sí están en el snapshot, cotizar el subconjunto que los cubre | `cuánto está la chocolina?` no arrastra Coquitas del mismo snapshot | Pedir el precio de una de las cosas mostradas no es pedir el listado entero. | Si un token matchea, devolver los cinco. Sigue mezclando productos que el cliente no nombró. |
| El `if len(pool) == 1` deja de devolver ese SKU por ser el único | Se devuelve si el mensaje es pregunta de precio sin token ajeno, o si entran `los N`, `todos` o un ordinal. `cuánto está?` con una sola Opera la cotiza. `cuánto está la diversion` y `tenés coca?` no | Hoy ese `if` corre antes de mirar el nombre. Con un solo ítem, cualquier pregunta de producto cotiza ese SKU. | Dejar el atajo de un ítem como está. El mismo bug queda en listados de un producto. |
| `me pasarias` y el relleno de la pregunta no son tokens de producto | Reusar `_extract_significant_tokens` y sumar un conjunto local: `precio`, `cuanto`, `cuesta`, `sale`, `vale`, `cotiza`, `cotizan`, `esta`, `estan`, `pasame`, `pasarias`, `pasar`, `decime`, `mostrame`, `codigo`, `cod`, `esos`, `estas`, `estos`, `esas`, `producto`, `productos`, `opcion`, `opciones` | El test del spec 127 dice `me pasarias precio de los 3 combos`. Si `pasarias` veta, ese test se rompe. `producto`/`esos` son anáfora, no una marca nueva. | Un embedding o el modelo para decidir si el mensaje es anafórico. El riel es determinístico y corre antes del LLM. |
| Números | Si ya matcheó `los N` / `N combos`, el número es cantidad del listado, no un token. Si no, un número de dos dígitos o más que no aparece en ningún nombre veta. Si aparece, achica el subconjunto (`la de 100` dentro de Chocolinas 50X100G) | `los 3` tiene que seguir siendo “los tres primeros”. `100` en un nombre es presentación, no la cantidad del atajo. | Tratar todo dígito como posición del listado. `100` no es una posición. |
| Comparación | Minúsculas, sin acento, mismo stem de plural que `_stem_spanish`. Un token matchea si su stem está en el stem del nombre o al revés (`chocolina` ↔ `chocolinas`, `combo` ↔ `combo helado`) | Es el criterio que ya usa el snapshot para pedidos. Alcanza para estos casos y no abre otra búsqueda. | Igualdad exacta del nombre. `Diversion` contra `SURTIDO DIVERSION` quedaría como miss y, al revés, `chocolina` no reconocería el listado cuando sí hay que cotizarlo. |
| El texto que se clasifica es el mensaje entero del turno | No recortar `El cliente escribe: "…"`. La veta por token alcanza para la consigna de laboratorio (`Golosinas`, `Halloween`, `pan`, `dulce` no están en el snapshot de Pringles o no cubren toda la frase de Navidad) y para WhatsApp | El caso real no trae comillas de laboratorio. Un parser de consigna dejaría el bug de Vigay igual. | Enseñar al riel el formato del harness de `probar_agente`. El harness no es el contrato del agente de WhatsApp. |
| Sacar del texto los SKU que `get_product_by_code` rechaza | La línea `No pude cotizar en catálogo` no se envía. Si no queda ningún precio, el riel devuelve `None` | `13939` y `13940` están sin stock. El cliente recibió códigos internos. En un `cuánto está?` legítimo el snapshot de la última búsqueda igual puede traer SKU que el modelo no mostró y que no tienen stock. | Seguir anexando los códigos fallidos “para depurar”. El mensaje sale por WhatsApp. |
| El pool sigue siendo el último snapshot de tool o de prosa | No reconstruir el pool desde el último mensaje del asistente en esta entrega | El bug pedido es cotizar otro producto. Cambiar la fuente mezcla Coquitas con Chocolinas en el caso anafórico y reabre el spec 127. Queda anotado abajo. | Parsear la prosa del último AI y cotizar eso. Es más fiel a “lo que se mostró”, y es otro cambio de comportamiento. |

El orden dentro de `resolve_catalog_price_targets`:

1. Tokens de producto no cubiertos por ningún nombre → `[]`.
2. Tokens de producto, todos cubiertos, y el mensaje es una pregunta de precio (`precio` / `cuánto`) → solo los ítems que cubren esos tokens. Sobre ese subconjunto siguen `los N`, un solo ítem, `todos` y el ordinal.
3. Cero tokens de producto y pregunta de precio, con snapshot de hasta 5 → el snapshot entero. Es `cuánto está?` y `precio`.
4. Cero tokens y sin pregunta de precio → `[]`, salvo `los N`, `todos` o un ordinal, que siguen valiendo. Un snapshot de un solo ítem no se devuelve por ser el único: hace falta una pregunta de precio (paso 3) o una de esas tres reglas. Así `tenés coca?` después de una sola Opera no cotiza la Opera.

`Qué tenés de navidad?` tiene token (`navidad`) y no es pregunta de precio: cae en `[]` aunque el snapshot sea de Navidad. La consigna de laboratorio de ese turno, además, mete `pan`, `dulce` y `stock`, que no están en esos nombres, así que también veta por el paso 1. `navideños` no matchea el stem `navidad`; no hace falta un diccionario de familia. El turno sigue a `search_products`.

`_should_force_catalog_price_quote` puede seguir usando `looks_like_specific_product_question`. Si el resolver devuelve `[]`, el riel ya no corta. No hace falta partir esa función: también la usan otros flujos para no reemplazar una pregunta de producto por el link de tienda.

---

## Alcance

### Incluido

- `resolve_catalog_price_targets` en `app/agent/catalog_snapshot.py`.
- El texto final de `_run_catalog_price_quote_guard`: no listar códigos rechazados; si no hay ninguna línea de precio, no cortar el turno.
- Tests en `tests/test_conversation_listing_snapshot.py` con los textos de los dos casos, la anáfora, el subconjunto y el snapshot de un ítem.
- El test `test_resolve_catalog_price_targets_los_tres_combos` sigue verde.

### Fuera de alcance

- Cambiar el harness `El cliente escribe` / `probar_agente`. En sesión vacía ya busca bien. El defecto es el riel.
- Reemplazar el pool por la prosa del último mensaje del asistente. En Vigay esa prosa tenía tres Chocolinas y dos Coquitas; el snapshot tenía cinco Chocolinas. Un `cuánto están?` va a seguir cotizando el snapshot de la última tool, incluidos SKU sin stock que simplemente no se imprimen.
- `search_products`, el peso de categoría del 108, ni el prompt de Almaro.
- Coach, recepcionista, vendedor. El riel ya sale solo con `actor_profile == "client"`.
- Migración, backoffice, tienda.

---

## Orden de implementación

Un solo repo.

| Paso | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `agente-conversacional-multi_tenant` | `feat/atajo-precio-listado` desde `origin/master` | Tests nuevos en rojo, después el resolver y el sufijo del riel. Merge humano a `master`. |

No hay consumidor en backend ni en front. No hay orden cross-repo.

---

## Migración de base de datos

Sin migración de BD. No se tocan snapshots ya guardados ni `core.conversation_events`.

---

## Plan de prueba en CI/CD

En el PR del agente:

- `pytest tests/test_conversation_listing_snapshot.py`
- El test existente de `precio de los 3 combos` queda verde.
- Casos nuevos, todos sobre `resolve_catalog_price_targets` salvo el último:
  - consigna de laboratorio del caso 1 + snapshot Pringles → `[]`
  - `La Galletita Diversion cuánto está?` + snapshot Chocolinas → `[]`
  - `cuánto está?` + ese snapshot → los cinco códigos (el filtro de stock es del riel, no del resolver)
  - `cuánto está la chocolina?` + snapshot Chocolinas y Coquitas → solo códigos cuyo nombre tiene chocolina
  - snapshot de un ítem Opera + `cuánto está la diversion` → `[]`
  - snapshot de un ítem Opera + `cuánto está?` → ese código
  - `Qué tenés de navidad?` + la cola de la consigna (`con código y precio`, pan dulce, turrones) contra el snapshot de Navidad de `mcp-lab-80` → `[]`
- No hay migración que smoke-testear.
- El check de pytest del agente tiene que quedar verde. No hay otro pipeline que cubra este riel.

---

## Plan de prueba humana (antes del PR)

No hace falta backoffice. El comportamiento nuevo es determinístico y los tests de arriba son la prueba.

Si se quiere ver el turno completo en Almaro, con el agente local apuntando al pooler `6543` (`statement_cache_size=0`):

1. Sesión de laboratorio ya usada, o una nueva, schema `almaro`.
2. Primer mensaje: `Y pringles?`. Tiene que listar Pringles y dejar snapshot.
3. Segundo mensaje, el texto real, no la consigna: `Golosinas`. Tiene que buscar y mostrar golosinas (Mogul, Mr Pops u otras con stock). No puede abrir con `Te paso los precios:` ni repetir Pringles.
4. En otra sesión, después de un listado de Chocolinas, escribir `La Galletita Diversion cuánto está?`. Tiene que buscar Diversión / Surtido, no reimprimir Chocolinas ni `13939` / `13940`.
5. Después de un listado de tres productos, escribir `cuánto está?`. Ahí sí cabe `Te paso los precios:` con esos productos, sin códigos que `get_product_by_code` rechace.
6. `me pasarias precio de los 3 combos` después de listar tres combos sigue cotizando esos tres.

Qué mirar: en el turno 3 y en el 4 no hay respuesta instantánea armada por el riel; hay `search_products` en `core.agent_tool_executions` o un `catalog_search_snapshot` nuevo. En el turno 5 la respuesta puede ser el riel y no tiene por qué haber `search_products`.
