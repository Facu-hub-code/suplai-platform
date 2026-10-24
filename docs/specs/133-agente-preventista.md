# 133 — El agente como preventista: los de siempre + novedades

**Estado:** Borrador para retomar después de mergear el MCP (spec 132) y levantar el primer plantel de bots. Es la base del brainstorming de las skills de venta.
**Fecha:** 2026-10-24
**Repos:** `agente-conversacional-multi_tenant`, `wholesale-catalog-app`, `backend-supabase`, `suplai-platform` (este spec).
**Relaciona:** [132](./132-mcp-para-agentes-y-humanos.md) (los bots que cuidan la configuración), [131](./131-promociones-tres-modelos.md) (promos), dry run de almaro `implementacion/almaro/outputs/dry-run-preventista-20261024.md`.

---

## Objetivo

Que el agente no solo tome pedidos bien sino que venda como un buen preventista: llega con el pedido de siempre armado y suma algo nuevo.

**Meta mínima de cada pedido:** el pedido habitual del cliente + al menos una novedad o una promoción.

---

## Lógica del preventista

1. **Los de siempre.** El agente sabe qué compra cada cliente y en qué cantidad. Ofrece cargarlo de una vez («¿te armo lo de siempre?») y el cliente solo corrige.
2. **Novedades.** Productos que entraron hace poco, con foto. Se muestran después de armar lo de siempre, uno o dos, elegidos por afinidad con lo que el cliente ya compra.
3. **Promociones.** Las vigentes para la lista del cliente, empezando por las que llevan productos que ya compra (un combo de un producto habitual vende más que uno de algo nuevo).
4. **Cierre.** Si el pedido no llegó a la meta mínima, el agente ofrece una novedad o una promo antes de confirmar, una sola vez y sin insistir.

---

## Qué tiene que tener cada cliente

Todo cliente tiene, en la tienda y en el agente:

| Qué | De dónde sale | Regla |
|---|---|---|
| **Favoritos** | Los que marca en la tienda + los habituales de su historial | Si no marcó ninguno, se arman con el historial. Si no tiene historial en Suplai, con el del ERP. |
| **Cantidad habitual** | La mediana de lo que pidió de cada producto | No es fija: depende del cliente y del producto (ver dry run). |
| **Novedades** | Los últimos ingresos del catálogo con stock, foto y precio en su lista | Sin foto no se muestra como novedad. |
| **Promociones** | Las vigentes de su lista de precios | Toda lista con clientes tiene promos; si no, se avisa. |

En la tienda: la sección Favoritos arranca llena con los habituales, con un botón «Repetir lo de siempre» que carga cada producto en su cantidad habitual. Novedades y Promociones ya existen.

---

## Cantidad habitual

La idea inicial era «de a 1 o de a 3 según el cliente». El dry run de almaro muestra que no alcanza con eso: la cantidad que más se repite por cliente y producto es de 4 a 6 unidades (37 %), y 1 y 3 son el 17 % cada una.

Regla propuesta:

- `cantidad_habitual` = mediana de la cantidad pedida de ese producto por ese cliente, en la unidad de venta (unidad o display).
- Solo para productos que pidió 2 veces o más; los que pidió una vez son «ocasionales» y no entran en lo de siempre.
- Se recalcula con cada pedido confirmado y vive en `clients.metadata.top_products` (hoy guarda el total, no la mediana: hay que sumarla).

---

## Quién lo cuida: los bots

Los agentes del spec 132 se ocupan de que esto esté bien configurado:

| Bot | Qué revisa |
|---|---|
| Catálogo | Novedades sin foto (las pide), sin stock o sin precio en alguna lista con clientes. |
| Analista | Clientes sin favoritos o sin historial; recalcula los habituales; mide cuántos pedidos llegan a la meta mínima. |
| Activador | Listas con clientes y sin promos; promos de productos habituales que conviene empujar. |
| Supervisor | Que el agente ofrezca lo de siempre y una novedad o promo en las conversaciones reales. |
| Jefe de cuenta | Junta los hallazgos en el lote de la semana, con la estrategia. |

---

## Pendientes antes de implementar

1. Brainstorming de las skills de venta: cuándo ofrecer, cómo elegir la novedad, cómo no cansar al cliente.
2. Traer el historial de pedidos del ERP para los clientes que no compraron por Suplai (en almaro son 108 de 150).
3. Sumar la mediana y la frecuencia a `top_products`, y correr el cálculo para todos los clientes.
4. Botón «Repetir lo de siempre» en la tienda y en el agente.
5. Métrica: % de pedidos con lo de siempre + al menos una novedad o promo.
