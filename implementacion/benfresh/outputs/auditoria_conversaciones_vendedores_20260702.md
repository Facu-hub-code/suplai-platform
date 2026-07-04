# Auditoría de conversaciones — BenFresh Food (`benfresh`)

**Ventana:** 2026-04-23 → 2026-07-02 (UTC) · foco en pruebas de vendedor 25-jun / 30-jun / 01-jul
**Segmento:** vendedores en prueba — `17864035046` y `17866384969`
**Fuentes:** `benfresh.n8n_chat_histories` (texto), `core.seller_context`/`conversation_events` (mapeo), **Loki** (`service_name="Agent"`, `tenant_name="benfresh"`) para `tool_name` + parámetros
**Tenant id:** `fce614e5-ff61-40d7-ab3a-95567c6dd2c5`

## Resumen ejecutivo

- `17864035046` = **Christian (vendedor id 4)** es la única fuente real: 155 mensajes, 5 pedidos confirmados. `17866384969` (vendedor id 8) tiene **1 solo mensaje** (apenas se registró; sin pruebas útiles).
- **Problema de datos confirmado:** ambos teléfonos existen a la vez como cliente y como vendedor (`17864035046` → cliente 11 *BENFRESH MARKET LLC* y vendedor 4 *Christian*; hay incluso `117864035046` → cliente 50). Ellos operaron con **tools de vendedor** (`set_seller_selected_client`, `load_seller_order_text`, `create_order`, `edit_order`, `confirm_order_for_client`).
- **Hallazgo más grave (🔴 edición de pedido):** "quedate solo con los ítems X e Y" y "sacar ítem N" **duplican o borran de más** porque `edit_order` opera por **SKU**, no por índice de línea, y el pedido permite **líneas duplicadas del mismo SKU**. Un pedido de Sergio se **confirmó con líneas duplicadas** (total inflado de ~$895 a **$1.959,66**).
- Selección de cliente: **first-pass OK con nombres distintivos**, pero **loops** con nombres genéricos compartidos por muchos PDV (la saga "Celis" nunca resolvió; "Smoothie plus Miramar" mostró 8 candidatos idénticos "Smoothie Store").
- Stock: **se verifica y se respeta correctamente** ✓. El ruido viene de que casi todo el catálogo de prueba figura sin stock (dato de inventario no cargado) y del **parser de cantidad/pack**, que es frágil.

## Métricas de señal (hilo Christian, abril→julio)

| Señal | Cantidad |
|-------|----------|
| Desambiguaciones de cliente ("Hay varios clientes que coinciden") | 9 |
| Cliente no encontrado | 2 |
| Clientes seleccionados | 10 |
| Líneas fuera por falta de stock | 6 |
| Cargas parciales | 7 |
| Ambigüedad de producto | 8 |
| "No encontré productos en el texto" | 2 |
| Ediciones con remove (`Quité SKU`) | 12 |
| Ediciones con add/replace | 14 |
| Pedidos confirmados | 5 |

> Nota de traza: `core.agent_turns`/`agent_tool_runs` **no** cubren estos teléfonos (solo números AR de junio). El detalle de tools/params salió de **Loki**.

---

## 1) Formato general de los mensajes (para calibrar descripciones de tools)

El vendedor es **muy consistente**. Plantilla observada:

- **Línea 1 = cliente**, muchas veces con calificador de ubicación/sucursal: `Celis west palm beach`, `Smoothie plus Miramar`, `Powerfuel Miramar`, `Dixie ribs`.
- **Líneas siguientes = ítems**, dos variantes:
  - `CANT producto [pack]` → `3 mango 6x5`, `7 sweetcorn 30lb`, `23 cut green beans`, `4 blueberries 6x5`.
  - `producto-CANT` → `Diced Potatoes-1`, `White Rice-2`, `Corn-25`, `Sofrito-2`.
- **Notación de pack recurrente:** `6x5`, `7x3`, `4+1`, `8/15`, `22lb`, `30lb`, `2204 libras` (audio). El pack suele ir **después** del nombre.
- **Cliente + pedido en un mismo mensaje** (one-shot) es lo habitual.
- **Idioma mixto:** productos en inglés, comandos en español. Frecuente **audio transcrito** con ruido (`Carrot Dicet`, `Carro Dyset`, `2204 libras`).
- **Ediciones (lenguaje natural, por posición):** `Solo item 1`, `Item 2`, `Sacar item 2, 3`, `Dejar solo items 3`, `Sacar item 1 y 2`, `Cambiar el blueberry 6x5 por blueberry 22lb 5 cajas`, `Del item 1 es una caja`, `Agregar green peas 18`.
- **Cierre:** `Ok hace la orden`, `Confirmado`, `Ok confirmado`, `Ok hacer pedido`.

**Implicancia:** el vendedor razona **por número de línea** ("item 2", "solo items 4 y 5"), pero las tools razonan **por SKU**. Ese desajuste es el origen del hallazgo #4.

---

## 2) Selección de cliente — ¿lo encuentran a la primera?

**Depende del nombre.** First-pass correcto con nombres distintivos:

- `Dixie` / `Dixie ribs` → 1 intento (alias) ✓
- `Sergio` → 1 intento (aprox.) ✓
- `Tu cocinita` → 1 intento ✓
- `Powerfuel Miramar` → 1 intento (alias) ✓

Loops / reintentos con nombres genéricos:

- **Saga "Celis" (06-25):** `Celis produces` (2 cand.), `Celis` (no encontrado), `CELIS PRODUCE` (2), `Celis smoothie` (**8 candidatos todos "Smoothie Store"**), `WD 272` (no encontrado), `242` (**seleccionó MAX FOOD DISTRIBUTORS**, cliente equivocado por match de código), `Celis west palm beach` (2). **Nunca** llegó al cliente buscado.
- **`Smoothie plus Miramar` (06-30):** 3 intentos; dos veces devolvió la **misma lista de 8** "Smoothie Store" idénticos; resolvió recién con `#2`.
- **`Wynwood for dogs` (06-30):** 2 intentos (lista → `1`).

**Causa raíz (doble):**
1. **Datos** — muchos PDV con **display name genérico idéntico** ("Smoothie Store" ×8, "Market Store", "Supermarket"). Las listas de desambiguación quedan **inservibles**: solo cambia el código, no hay dirección/zona para elegir.
2. **Búsqueda/UX** — input numérico (`242`, `WD 272`) **matchea fragmentos de código** y puede **seleccionar el cliente equivocado** sin confirmación. La lista de candidatos no muestra un diferenciador humano (dirección, zona, vendedor).

Clasificación: `seller_client_selection` + `data_gap` (🔴/🟡).

---

## 3) Producto seleccionado y stock

- **Stock: correcto ✓.** El agente valida stock y **excluye** líneas sin stock, informándolo: `«mango 6x5» → Mango Sorbet SP — no entró (insufficient stock)`, `«Yuca» → … sin stock`, etc. (6 líneas). No se cargó nada sin stock.
- **Ruido de inventario (dato):** casi todo cae "sin stock" (Yuca, Corn, Pepper, Carrot, Mango Sorbet, Acai tropical) → parece **inventario no cargado** en el tenant de prueba, no un bug del agente.
- **Matching RAG:** bueno con nombre claro (`sweetcorn 30lb`, `papaya 7x3`, `blueberries 6x5` ✓). **8 casos de ambigüedad** con genéricos (`blueberries`, `cut green beans`, `Peas`): ofrece ~5 opciones pero **no auto-resuelve** ni recuerda la elección.
- **Parser de cantidad/pack frágil (🟡→🔴 en algunos casos):**
  - `Carrot diced 22lb 18 cajas` → *"No encontré productos"* (pero `Carrot diced 22lb` solo sí funciona).
  - `Carrot diced 22lb` generó **líneas fantasma** partiendo el propio pack del nombre del producto: `4× lb (1x22` y `18× 04 lb)` → matcheó *Raspberries*.
  - `Mango 6x5` (sin cantidad al frente) → *"sin cantidad válida"*, aunque `3 mango 6x5` sí entra.
  - Audio: `2204 libras`, `Carro Dyset` → no interpretados.

---

## 4) Edición del pedido en curso — 🔴 hallazgo crítico

**Interfaz real de `edit_order` (confirmada en código + Loki):**
- `add_items` → **agrega** (append, **no** hace merge por SKU).
- `replace_items` → "borra líneas previas del SKU y agrega una sola con la cantidad dada" (upsert por SKU).
- `remove_product_codes` → "**borra todas las líneas de esos SKUs**".
- **No existe** operación por **índice de línea** ni **"keep only"**.

El vendedor habla **por índice** ("item 2", "solo items 4 y 5"); el LLM debe traducir índice→SKU. Ahí se rompe:

**Caso duplicación confirmado (30-jun, SERGIO'S CATERING, pedido #125) — evidencia Loki:**
- Pedido tenía 5 líneas. Vendedor: **"Ok hacer pedido solo items 4 y 5"**.
- Loki `13:01:46`: `edit_order add_items_count=2 remove_codes_count=3` → quitó ítems 1-3 **y re-agregó** Sweetcorn (`89090009` ×10) + Green Beans (`89090130` ×23) que **ya estaban** → **duplicó** ambas líneas.
- Vendedor insiste "solo items 4 y items 5" → `13:03:11 add_items=2 remove_codes=4` → **más duplicados**.
- Se **confirmó pedido #125 con líneas duplicadas**, total **$1.959,66** (debía ser ~$895).
- **Raíz:** el LLM implementa *"quedate solo con X"* como *quitar-todo-lo-demás + volver-a-agregar-X*; como `add_items` no mergea por SKU, **duplica**.

**Caso borrado de más (01-jul, TU COCINITA, pedido #134):**
- Pedido: ítem1 Carrot `89090013`, ítem2 Raspberries `89090065`, **ítem3 Carrot `89090013` (duplicado)**.
- Vendedor: **"Sacar item 1 y 2"** → Loki `remove_codes_count=2` con `89090013` y `89090065` → como remove es por SKU, borró **ítem 1 Y 3** → **pedido vacío** inesperado.

**Caso "no se puede quitar una sola de dos líneas iguales" (01-jul, POWERFUEL, pedido #130):**
- Había dos líneas PITAYA (`89010012`). "Sacar item 2 y 4" → `remove_codes_count=1` (`89010012`) borró **ambas**. Coincidió con lo deseado, pero deja claro que **no hay forma de quitar solo una** de dos líneas del mismo SKU.

**Caso comando de edición no reconocido:**
- Con pedido vacío, **"Dejar solo items 3"** se parseó como **producto nuevo** (`3× Dejar solo items`, baja confianza) en vez de edición.

**Resumen de causas (todas se combinan):**
1. El modelo de pedido **permite líneas duplicadas** del mismo SKU (`add_items` hace append, no upsert).
2. `remove_product_codes` **no distingue líneas**: borra todo el SKU.
3. **No existe operación por índice** ni `keep_only`, que es como habla el vendedor.
4. El LLM traduce "keep only" a *remove-otros + add-esos*, re-agregando lo que ya estaba → duplica.

---

## Recomendaciones priorizadas

| # | Prioridad | Acción | Capa | Esfuerzo |
|---|-----------|--------|------|----------|
| 1 | 🔴 | En `edit_order`, hacer que `add_items` **mergee por SKU** (sumar cantidad a la línea existente en vez de crear duplicado). Elimina la duplicación de raíz. | tool | medio |
| 2 | 🔴 | Agregar operación **por índice de línea** y/o `keep_only_indices` a `edit_order` (el vendedor razona por "item N"). Mapear "solo items 4 y 5", "sacar item 2", "dejar solo item 3". | tool + prompt | medio |
| 3 | 🔴 | Regla de prompt: **"quedate solo con…" ⇒ SOLO remover el resto; NO re-agregar** los que ya están. Y usar `replace_items` (no `add_items`) al ajustar cantidad de un SKU existente. | prompt | bajo |
| 4 | 🔴 | En listas de desambiguación de cliente, mostrar **diferenciador** (dirección/zona/vendedor) y **no autoseleccionar por match de código** ante input numérico ambiguo (`242`, `WD 272`) — pedir confirmación. | tool + datos | medio |
| 5 | 🟡 | **Datos:** de-duplicar / renombrar clientes con display name genérico ("Smoothie Store" ×8, "Market Store", "Supermarket") con nombre real de fantasía + sucursal. | datos | medio |
| 6 | 🟡 | Robustecer parser de cantidad/pack: aceptar `producto CANT [pack]` sin cantidad al frente, evitar que el pack del **nombre del producto** genere líneas fantasma (`(1x22,04 lb)`), y tolerar `22lb 18 cajas`. | tool/parse | medio |
| 7 | 🟡 | **Datos:** cargar stock del tenant de prueba (hoy casi todo "sin stock"), para que las pruebas E2E reflejen el flujo real. | datos | bajo |
| 8 | 🟢 | Resolver el doble registro cliente/vendedor del mismo teléfono (`17864035046`, `117864035046`) para evitar ambigüedad de rol. | datos | bajo |

## Descripciones de tools sugeridas (borrador para el punto 1)

- **`edit_order`** — dejar explícito el modelo mental por línea y evitar re-add:
  > "Edita el pedido abierto. Para *quitar* ítems que el vendedor menciona por posición ('sacar item 2', 'solo items 4 y 5'), usá `remove`/`keep_only` **por índice de línea** — NO vuelvas a agregar en `add_items` los ítems que ya están en el pedido. `add_items` **suma** cantidades por SKU (no crea líneas duplicadas). Para cambiar la cantidad de un SKU existente usá `replace_items`, nunca `add_items`."
- **`add_items` (campo)** — de "misma semántica que create_order" → aclarar: *"Agrega ítems nuevos; si el SKU ya está en el pedido, se **suma** a la línea existente (no duplica)."*
- **`remove_product_codes` (campo)** — advertir el efecto por SKU: *"Borra TODAS las líneas de esos SKUs. Si hay líneas duplicadas del mismo SKU y solo querés quitar una, usá remove por índice de línea."*
- **`set_seller_selected_client`** — *"Ante input numérico corto o ambiguo (ej. '242', 'WD 272') NO selecciones por coincidencia parcial de código: devolvé candidatos con diferenciador (dirección/zona) y pedí confirmación."*

## Sesiones revisadas

| session_id | perfil | motivo |
|------------|--------|--------|
| `17864035046` | vendedor 4 (Christian) | fuente real: 155 msgs, 5 pedidos, ediciones con bugs |
| `17866384969` | vendedor 8 | 1 solo mensaje (sin datos útiles) |

## Limitaciones

- `core.agent_turns`/`agent_tool_runs` no traza estos teléfonos; el detalle de tools salió de **Loki** (ventanas puntuales del 30-jun y 01-jul), no de toda la historia.
- `17866384969` prácticamente no se usó; las conclusiones aplican a Christian.
- Análisis read-only: no se modificó BD ni código del agente.
