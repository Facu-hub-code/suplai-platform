# 133 — El agente como preventista: los de siempre + novedades

**Estado:** v2, implementado (etapas 1 a 5) en PRs abiertos; falta la prueba con charlas reales de almaro. Decisiones aprobadas con la propuesta del spec (25/10/2026).
**Fecha:** 2026-10-25 (v1: 2026-10-24)
**Repos:** `agente-conversacional-multi_tenant`, `backend-supabase`, `wholesale-catalog-app` (tienda), `suplai-platform` (este spec).
**Relaciona:** [132](./132-mcp-para-agentes-y-humanos.md) (los bots que cuidan la configuración), [131](./131-promociones-tres-modelos.md) (promos), 081 del agente (`agente-conversacional-multi_tenant/docs/specs/081-repeat-last-order-deterministic.md`, repetir pedido), [073](./073-mixpanel-analytics.md) (métricas), dry run de almaro `implementacion/almaro/outputs/dry-run-preventista-20261024.md`.

---

## Objetivo

Que el agente venda como un buen preventista: llega con el pedido de siempre armado y suma algo nuevo.

**Meta mínima de cada pedido:** lo de siempre + al menos una novedad o una promoción.

---

## Qué hace hoy el agente

| Qué | Cómo | Límite |
|---|---|---|
| Repetir | `repeat_order` clona el último pedido confirmado (hasta 60 días). | Es el último pedido, no lo de siempre: si el último fue chico o raro, repite eso. |
| Historial | `list_recent_orders`. | Lo lee el modelo; no hay cantidades habituales. |
| Promos | `list_promotions` (páginas de 5, como la tienda). | Solo si el cliente pregunta. No elige la que conviene a ese cliente. |
| Cross y up sell | `suggest_order_boost_for_client`, `tenant_*_sell_mappings`. | Solo para el vendedor (Field), no para el cliente. |
| Habituales | `clients.metadata.top_products` (spec 132: mediana, frecuencia, origen Suplai y ERP). | El agente del cliente no lo lee. Solo lo usa `seller_field`. |
| Novedades | La tienda las muestra por `created_at`. | El agente no las conoce. |

---

## Cómo vende

### 1. Lo de siempre

- El agente recibe en el prompt un bloque corto por cliente: hasta 8 habituales (`habitual=true`) con su cantidad habitual, la última compra y cada cuántos días los pide. Si un habitual ya pasó su frecuencia, va marcado «le toca».
- Al primer «hola» de un cliente con habituales, ofrece armar lo de siempre en una línea: «¿Te armo lo de siempre? (yerba x6, azúcar x4…)».
- `repeat_order` suma `base`: `habitual` (nuevo, default si hay habituales) o `ultimo` (lo de hoy). Con `habitual` arma cada producto en su cantidad habitual, saca los que no tienen stock y lo dice.
- Si no tiene habituales, sigue como hoy (último pedido o pedido libre).

### 2. Una sugerencia, elegida para ese cliente

Una tool nueva del agente, `sugerir_para_cliente`, devuelve hasta 3 candidatos con el motivo, en este orden:

1. **Promo de un habitual:** una promo vigente de su lista que lleva un producto que ya compra.
2. **Novedad afín:** una novedad (últimos ingresos, con foto, stock y precio en su lista) de una categoría que ya compra.
3. **Cross sell:** el mapeo del tenant para algo que tiene en el carrito.

El agente ofrece **una**, después de armar lo de siempre, con su motivo en una frase («entró el set matero, va con la yerba que llevás»).

### 3. No cansar

- Una sugerencia por pedido. Nunca antes de que esté armado lo de siempre o lo que pidió.
- Si dice que no, esa sugerencia no vuelve en 14 días (`clients.metadata.sugerencias`, JSON que ya existe: sin columnas nuevas).
- No sugiere si el cliente pidió algo puntual con apuro («solo 2 cocas y listo») ni si está en un reclamo.

### 4. Cierre

Antes de `confirm_order`, si el pedido no llegó a la meta mínima y todavía no se ofreció nada, ofrece una sola vez. Si ya se ofreció, confirma sin insistir.

---

## La tienda

- La sección Favoritos arranca llena con los habituales (los que marcó el cliente primero).
- Botón «Repetir lo de siempre»: carga cada habitual en su cantidad habitual. Lee los habituales de un endpoint del backend (`/{schema}/tienda/habituales`).

---

## Quién lo mantiene

Los bots del spec 132, con el prompt del plantel (`docs/grok-bot/`):

| Bot | Qué hace |
|---|---|
| Analista | Recalcula los habituales todos los días (`editar_clientes cambio=habituales`). Mide la meta mínima. |
| Catálogo | Novedades con foto y descripción. Sin foto no se sugieren. |
| Activador | Toda lista con clientes tiene promos; si no, lo avisa. |
| Supervisor | Lee charlas reales: ¿ofreció lo de siempre? ¿una sola sugerencia? ¿insistió? |

---

## Si se acaba el crédito de un proveedor

Pedido de Facundo (24/10/2026): el agente no puede quedarse mudo porque se terminó el saldo de OpenAI o de Anthropic.

- `llm_factory.build_chat_model` arma, además del modelo del tenant, uno de respaldo del otro proveedor: `gpt-4o` ↔ `claude-sonnet-5-5`, `gpt-4o-mini` ↔ `claude-haiku-5-5`.
- Solo cambia por errores de saldo o cuota: OpenAI `insufficient_quota` (429) y Anthropic «credit balance is too low» (400). Un error común o un timeout se reintenta como hoy.
- Al cambiar, el proveedor caído queda fuera 15 minutos para todos los tenants y se loguea `LLM_PROVEEDOR_SIN_SALDO` como error (lo ve Suplai en Grafana; no va a los tickets de la distribuidora, porque el saldo es de Suplai).
- Si falta la clave del otro proveedor, no hay respaldo y queda como hoy.
- Con Claude se pide la tool por prompt (sin `tool_choice` forzado), como ya hace `supports_forced_tool_choice`.

---

## Métricas (Mixpanel, spec 073)

- `pedido_confirmado`, `pedido_confirmado_field` y el nuevo `pedido_confirmado_agente` suman `uso_lo_de_siempre`, `tiene_novedad`, `tiene_promo`, `meta_minima`, `sugerencia_ofrecida`, `sugerencia_aceptada` y `tipo_sugerencia`. Salen del backend y se calculan al confirmar, sin columnas nuevas (ver spec 073).
- En la tienda, `lo_de_siempre_cargado` cuando el cliente usa el botón.
- Métrica: % de pedidos con lo de siempre + al menos una novedad o promo, por tenant y por semana.

---

## Etapas

| Etapa | Qué | Listo cuando |
|---|---|---|
| 1 | Fallback de proveedores. | Con la clave de OpenAI sin saldo, el agente contesta con Claude y avisa. |
| 2 | Bloque «lo de siempre» en el prompt y `repeat_order base=habitual`. | El cliente 79 de almaro pide «lo de siempre» y recibe sus habituales en su cantidad. |
| 3 | `sugerir_para_cliente`, una sugerencia y no cansar. | En 20 charlas de prueba ofrece una sola vez y nunca antes de armar el pedido. |
| 4 | Tienda: Favoritos con habituales y «Repetir lo de siempre». | El botón carga lo mismo que el agente. |
| 5 | Métricas en Mixpanel. | La meta mínima se ve por tenant en Live View. |

---

## Decisiones para aprobar

1. **¿Extender `repeat_order` con `base` o una tool aparte?** Propuesta: extender, para no sumar tools al agente.
2. **¿Cuántos días sin repetir una sugerencia rechazada?** Propuesta: 14.
3. **¿El fallback cambia para todos los tenants o solo para el que falló?** Propuesta: para todos, porque el saldo es de la cuenta y no del tenant.
4. **¿Arranca en almaro solo, con un flag por tenant?** Propuesta: sí, `metadata.preventista_activo`, y después gonzales.
