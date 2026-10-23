# 129 — Agente: cargar un SKU o una promo

**Estado:** Borrador  
**Fecha:** 2026-10-22  
**Repos:** `agente-conversacional-multi_tenant`  
**Rama sugerida:** `feat/agente-carga-promo` desde `origin/master`, después del precio del [127](./127-gev-promos-regalo-y-pack.md)  
**Relaciona:** [127](./127-gev-promos-regalo-y-pack.md), [128](./128-tienda-seccion-promos-combo.md)  
**Tenant de prueba:** `almaro`, un cliente con lista Interior o Tradicional y un pedido abierto.

---

## Objetivo

El agente hoy agrega SKUs y, si una promo tiene miembros, el riel `promo` reparte el mínimo en partes iguales y lo carga. Este spec separa dos cargas.

Cargar un producto escribe el SKU a lista. Si ese SKU entra en una promo vigente, el agente avisa y pregunta si la quiere aprovechar. «No» deja el suelto. «Sí» en una cerrada carga el pack. «Sí» en una combinable abre el armado.

Cargar una promo no pasa por ese aviso. «Dame dos promociones de la primera» o «dame un combo del chocolate» resuelven la promo. La cerrada entra entera, N packs. La combinable abre el segundo paso con objetivo `N × mínimo`.

En ese segundo paso el agente ofrece los armados del 127 y acepta un reparto dictado. Topline 7, 2x1, mínimo 20, cuatro sabores: «partes iguales» es 5+5+5+5, «todo menta» es 20, y «5 de menta, 5 de frutilla, 5 de uno y 5 del último» también cierra.

### Criterios de aceptación

- `agregar_producto` escribe a lista. Si hay promo vigente para ese SKU y el cliente no la rechazó en este pedido, la respuesta le pide al modelo que pregunte si la quiere aprovechar.
- El turno siguiente, con esa pregunta pendiente, lo toma `promo_offer_confirm` antes del modelo. «Sí» en cerrada carga el pack. «Sí» en combinable deja `promo_mix_pending` y nombra las opciones. «No» borra la oferta y el SKU sigue a lista.
- `agregar_promocion` con una cerrada y un solo match carga N packs. Con una combinable no escribe líneas: abre el armado con objetivo `N × min_qty_umv`.
- `promo_mix_collect`, con armado pendiente, ofrece las mismas etiquetas que el 127. «Partes iguales», «mitad y mitad», «todo menta» o «la 2» cargan ese armado. Un dictado cuyas cantidades suman el objetivo también. Una suma distinta responde cuánto falta y no escribe. «Mejor no» cancela.
- «Dame dos promociones de la primera», si la primera es combinable, abre el armado en 40 cuando el mínimo es 20. No reparte 40 en partes iguales por su cuenta.
- El riel `promo` actual deja de llamar `pack_items_for_promo` para una combinable. Para una cerrada con un solo match sigue cargando el pack fijo.

---

## Cómo está hoy

El grafo del PDV es `load_facts` → `pre_nodes` → `llm` ↔ `tools` → `post_nodes`. Adentro de `pre_nodes`, el riel `promo` (`run_pre_promo`) corre si el texto parece un CTA de promo. Lista las vigentes, matchea una, y `pack_items_for_promo` parte `min_qty_umv` en partes iguales entre los miembros y llama `create_order`.

`order_boost_confirm` ya muestra el patrón de un pendiente que sobrevive al turno: se guarda un evento y el mensaje siguiente lo resuelve un riel PRE, sin pasar por el modelo.

El precio no vive en el backend. `app/agent/tools/orders/pricing.py` llama `app/agent/promotions/pricing.py`. El 127 actualiza esa copia. Este spec no la reescribe.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Dónde vive el pendiente | Evento de la conversación, leído por un riel PRE | Cada mensaje de WhatsApp vuelve a entrar al grafo. `order_boost` ya persiste así | Dejarlo solo en la memoria del turno |
| Rieles nuevos | `promo_mix_collect` y después `promo_offer_confirm`, antes del `promo` de lista | Si hay un armado abierto, «5 de menta» no puede disparar el CTA que carga otra promo | Un nodo nuevo fuera de `pre_nodes` |
| Cerrada | Se escribe en el mismo turno en que se confirma | «Un combo del chocolate» con un solo match no necesita otra pregunta | Preguntar «¿confirmás?» después de que ya dijo que la quería |
| Combinable | Segundo turno de armado, con opciones y dictado | El reparto es del cliente. 5+5+5+5 no es la única mezcla válida | Seguir usando `pack_items_for_promo`, que reparte y carga solo |
| Opciones | Las de `services/promocion_armados.py`, replicadas en el agente con los mismos casos | El agente no llama al HTTP del backend. «Mitad y mitad» tiene que ser el mismo 10 y 10 que la tienda | Que el modelo invente las cantidades de la opción |
| SKU con promo | Se carga a lista y se pregunta | El cliente pidió el producto. La promo es una oferta encima | Frenar la línea hasta que conteste |
| Lo ya cargado | Cuenta para el objetivo | 10 de menta ya pedidas dejan el armado en 10/20 | Pedir 20 nuevas e ignorar las 10 |
| Frases de lista | «La primera» usa el orden de la última lista de promos del turno | «Dame dos de la primera» nombra un índice, no un SKU | Volver a buscar por nombre y agarrar otra |

---

## Alcance

### Incluido

- Tool `agregar_producto` con aviso de promo aplicable.
- Tool `agregar_promocion` para cerrada (N packs) y para abrir el armado combinable.
- Rieles `promo_offer_confirm` y `promo_mix_collect` en `SELLER_PRE_RAIL_NODES`, en ese orden, inmediatamente antes de `promo`.
- Lectura de los `armados` con la misma tabla de ejemplos del 127.
- El riel `promo` de lista deja de auto-cargar una combinable.
- Frases: «dame dos promociones de la primera», «dame un combo del chocolate», «partes iguales», «mitad y mitad», «todo menta», «mejor no», y un dictado de cantidades.

### Fuera de alcance

- Migrar el precio del agente. Lo hace el 127.
- El armador de la tienda. Lo hace el 128.
- Cambiar `load_facts`, el POST de `order_mutation`, ni el texto de entrega.
- Backoffice para marcar una promo como combinable. El 127 ya deja `forma` en la fila.

---

## Turnos

| Lo que dice | Estado previo | Qué pasa |
|---|---|---|
| «Sumame 10 de menta» | Nada pendiente | `agregar_producto` escribe 10 a lista. Si entra en Topline 7, pregunta si la quiere armar |
| «No» | Oferta pendiente | `promo_offer_confirm` cierra la oferta. Siguen las 10 a lista |
| «Sí» | Oferta de una cerrada | Carga el pack y termina |
| «Sí» | Oferta de Topline, mínimo 20, van 10 | Abre el armado. Dice que van 10 de 20 y nombra `Completar parejo`, `Todo menta` y el dictado |
| «Partes iguales» | Armado en 0 de 20, cuatro sabores | Carga 5+5+5+5 |
| «5, 5, 5 y 5» | Armado pendiente, sabores recién nombrados | Carga ese dictado si suma 20 |
| «5 y 5» | Faltan 10 | Responde que faltan 10 y no escribe |
| «Mejor no» | Armado pendiente | Borra el pendiente. Lo ya cargado a lista queda |
| «Dame un combo del chocolate» | Un solo match cerrado | Carga un pack |
| «Dame un combo del chocolate» | Varios matches | El modelo pregunta cuál. No escribe |
| «Dame dos promociones de la primera» | La última lista tiene una combinable de mínimo 20 en el puesto 1 | Abre el armado con objetivo 40 |
| «Dame dos promociones de la primera» | La primera es un 2x1 cerrado | Carga dos packs, cuatro unidades si el pack es 2 |
| «Qué promos hay» | Nada pendiente | El riel `promo` lista. No abre un armado solo |

El 2x1 del pozo lo aplica el precio del 127 después de escribir las líneas. Con 20 unidades justas, las 20 quedan al 50%.

---

## Nodos

El grafo no cambia de forma: `START` → `load_facts` → `pre_nodes` → `llm` ↔ `tools` → `post_nodes` → `END`.

Dentro de `pre_nodes`, el tramo nuevo queda así:

`order_boost_confirm` → `promo_mix_collect` → `promo_offer_confirm` → `promo` → resto de rieles.

| Nodo | Corre cuando | Efecto |
|---|---|---|
| `promo_mix_collect` | Hay `promo_mix_pending` | Si el texto elige una opción o dicta cantidades que cierran, escribe las líneas, borra el pendiente y `pre_hit` termina el turno. Si falta, responde el faltante y también termina el turno. «Mejor no» borra el pendiente y termina |
| `promo_offer_confirm` | El turno anterior preguntó si quería aprovechar | «Sí» cerrada escribe el pack. «Sí» combinable crea el pendiente de armado y lista opciones. «No» marca el rechazo para ese SKU en este pedido |
| `promo` | Texto de lista o de nombre, y no hay pendiente | Una cerrada con un solo match se carga. Una combinable abre el pendiente y no llama `pack_items_for_promo` |
| `tools` / `agregar_producto` | El modelo está cargando un SKU | Escribe a lista y, si corresponde, deja la oferta para el turno siguiente |
| `tools` / `agregar_promocion` | «Dos de la primera», «un combo del chocolate» | Cerrada: N packs. Combinable: pendiente con objetivo `N × mínimo`. Varios matches: el modelo pregunta cuál |

Si `promo_mix_collect` no entiende el texto y tampoco es una cancelación, responde una vez con las opciones y las cantidades que faltan. No suelta el turno al modelo mientras el pendiente siga abierto, para que un «hola» no arme un pedido al pasar.

---

## Orden de implementación

| Orden | Repo | Rama | Depende de |
|---|---|---|---|
| 1 | `backend-supabase` | `feat/gev-promos-regalo` | El [127](./127-gev-promos-regalo-y-pack.md): `forma`, precio y armados |
| 2 | `agente-conversacional-multi_tenant` | `feat/gev-promos-precio` | La copia de precio del 127 |
| 3 | `agente-conversacional-multi_tenant` | `feat/agente-carga-promo` | `forma` ya persistida y la copia de precio mergeada |

Puede ser un solo PR del agente si el precio y los rieles salen juntos. La rama sale de `origin/master`.

---

## Migración de base de datos

Sin migración en este spec. `forma`, componentes y armados están en el 127. El pendiente de oferta y de armado se guarda como evento de conversación, igual que `order_boost`.

---

## Plan de prueba en CI/CD

Tests del agente, sin LLM, sobre los rieles y sobre la función de armados replicada:

- Topline, objetivo 20, cuatro sabores, nada cargado: «partes iguales» produce 5+5+5+5.
- Las mismas 10 de menta ya en el pedido: «partes iguales» de 5 no está entre las opciones. «Todo menta» suma 10. «Completar parejo» reparte 10.
- Objetivo 40: «mitad y mitad» de dos sabores es 20 y 20.
- `promo_mix_collect` con suma 18 no llama `create_order`.
- `promo_offer_confirm` con «no» no llama `create_order`.
- Una cerrada 2x1 y la frase «dame dos de la primera» llama la carga con cantidad 4.
- Una combinable no pasa por `pack_items_for_promo`.

La topología en `tests/test_pdv_graph_topology.py` (o el test de seller que ya lista `SELLER_PRE_RAIL_NODES`) incluye `promo_mix_collect` y `promo_offer_confirm` antes de `promo`.

Checks de grafo y de promociones del agente tienen que seguir verdes.

---

## Plan de prueba humana

Agente apuntando al backend local en el puerto 8000, tenant `almaro`, un WhatsApp de prueba o el canal que ya use el entorno local del agente.

1. Pedir 10 de un sabor que entre en una combinable. El agente carga 10 a lista y pregunta si quiere armar la promo.
2. Responder que no. El pedido sigue con esas 10 a lista. Un mensaje nuevo de otro producto no reabre la pregunta de ese SKU.
3. Repetir el pedido, responder que sí. El agente muestra opciones y dice que van 10 de 20. No carga el resto solo.
4. Decir «todo menta». El pedido queda en 20 de menta y el precio es el 50% del pozo.
5. En otro pedido, decir «partes iguales» con cuatro sabores y el armado en cero. Entran 5 de cada uno.
6. Decir «5, 5 y 5». El agente responde que faltan 5 y no agrega esas 15.
7. «Dame un combo del chocolate» contra una cerrada única. Entra un pack, sin segunda pregunta de sabores.
8. «Dame dos promociones de la primera» contra un 2x1. Entran dos packs.
9. «Dame dos promociones de la primera» contra Topline. El objetivo que anuncia es 40, y no aparecen 40 unidades repartidas hasta que elija una opción.

---

## Preguntas que este borrador ya cierra

1. El SKU se carga a lista y la promo se ofrece encima. Confirmado el 22 oct 2026.
2. La cerrada termina al decir que sí. La combinable tiene un segundo paso.
3. El segundo paso ofrece armados prearmados y acepta un dictado. Las cantidades salen del 127.
4. Mientras el armado está pendiente, ese riel se queda con el turno.
