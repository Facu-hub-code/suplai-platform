# Odoo — fecha de entrega y etiqueta Suplai en la sales order

**Estado:** Borrador  
**Fecha:** 2026-10-12  
**Repo de implementación:** `backend/` (`backend-supabase`)  
**Complementa:** [012 en backend](../../../backend-supabase/docs/specs/012-inyeccion-pedidos-erp.md) (`push_order`), `services/delivery_schedule_service.py`, `services/tienda_pedidos_service.py`  
**Tenant que lo pidió:** `benfresh` (Odoo 19, `https://benfresh-llc1.odoo.com`)

---

## 1) Contexto y problema

Al confirmar un pedido, el backend inyecta un `sale.order` en Odoo (`OdooConnector.push_order`). El día de entrega que calcula Suplai y una etiqueta para distinguir esos pedidos no quedan visibles de forma confiable para la distribuidora.

### 1.1 Cómo se inyecta hoy

`inject_order_to_erp` lee `pedidos` + ítems y llama `push_order`. El `sale.order` se crea con:

| Campo Odoo | Origen en Suplai |
|------------|------------------|
| `partner_id` | `clients.partner_erp_id` / `partner_odoo_id` |
| `order_line` | SKU → `product.product` |
| `origin` | `SUPPLAI-{pedido_id}` |
| `client_order_ref` | `order_reference` o, si no hay, el mismo `SUPPLAI-{pedido_id}` |
| `note` | `pedidos.notas` |
| `commitment_date` | Solo si `notas` matchea `FECHA DE ENTREGA:` (`_parse_commitment_date_from_notes`) |

No se envía `tag_ids`.

`commitment_date` es el campo **Delivery Date** de Odoo 19 (en español, **Fecha de entrega**). Es un `datetime`. `expected_date` (**Fecha prevista**) es otro campo, calculado a partir de la fecha del pedido y el lead time de las líneas. No es el día de entrega de Suplai.

### 1.2 Por qué benfresh no ve el día

Benfresh tiene `fixed_delivery_schedule.client_picks_delivery_day = true` (timezone `America/New_York`). En ese modo la tienda **confirma sin anotar fecha**: el cliente elige el día después. La inyección al ERP sale en el mismo momento de la confirmación, así que el `sale.order` nace sin `commitment_date`.

El día elegido se guarda después en `set_tienda_delivery_day`: escribe `FECHA DE ENTREGA: YYYY-MM-DD` en `pedidos.notas` y llama `write_commitment_date`. Ese write reintenta **4 veces con 0.4 s** (~1,6 s) buscando `origin = SUPPLAI-{id}`. En pedidos reales de benfresh la inyección tardó **7–35 s**. Si el cliente elige el día mientras el `sale.order` todavía no existe, el write se rinde y no hay un segundo intento. La cola de fallback tampoco lo corrige: con `estado = enviado_erp` el pedido no se vuelve a inyectar, y el `push_order` idempotente retorna sin actualizar la orden que ya existe.

Evidencia leída en Odoo el 2026-10-12 (usuario API con tz `America/New_York`):

| Sales order | Pedido Suplai | `commitment_date` | Nota en Suplai al mirar |
|-------------|-----------------|-------------------|-------------------------|
| `2026/05316` | 2373 | `2026-10-12 12:00:00` | ISO `FECHA DE ENTREGA: 2026-10-12` (el write llegó) |
| `2026/05086` | 2159 | `2026-09-26 12:00:00` | ISO |
| `2026/05281` | 2278 | `2026-10-09 19:00:00` | Texto verbal; el parser lo levantó en el create |
| `2026/05147` | 2215 | vacío | `notas` null |
| `2026/05083` | 1522 | vacío | `notas` null |
| `2026/04855` | 1520 | vacío | `notas` null |
| `2026/04807` | 1519 | vacío | `notas` null |

En los cuatro últimos el cliente no dejó día (o el write no alcanzó a correr). `expected_date` en esos pedidos no es un día de ruta: no sirve para mirar la entrega.

Dos huecos más del parser, para el resto de los tenants:

- `FECHA DE ENTREGA: Llega hoy` no tiene día numérico → `commitment_date` queda vacío. Hay pedidos de benfresh en `error_sync` con esa nota (no llegaron a Odoo por otro error de partner, pero el parser igual no resolvería el día).
- `FECHA DE ENTREGA: Llega el Viernes 9 de Octubre` sí parsea (día + mes, hora default 12:00). El año se infiere.

La hora que mandamos en el camino ISO es `YYYY-MM-DD 12:00:00`. Odoo la guarda como UTC. Con el usuario en `America/New_York` (UTC−4 en octubre) se ve **el mismo día a las 08:00**. Medianoche UTC se vería el día anterior; por eso la hora ancla es el mediodía.

### 1.3 Etiqueta

En Odoo 19, `sale.order.tag_ids` es many2many a `crm.tag` (label **Tags**). El usuario API de benfresh puede leer, crear y escribir `crm.tag`, y escribir `sale.order`. Hoy no existe un tag `Suplai` y los `sale.order` inyectados tienen `tag_ids` vacío. `origin = SUPPLAI-123` no aparece como filtro de etiquetas en la UI de ventas.

---

## 2) Objetivo

| Objetivo | Éxito |
|----------|--------|
| El día de entrega calculado o elegido queda en **Fecha de entrega** (`commitment_date`) | Un pedido de benfresh con día elegido muestra ese día en el `sale.order`, aunque el cliente lo elija después de confirmar |
| La distribuidora filtra ventas de Suplai | Todo `sale.order` inyectado lleva el tag **Suplai** |
| Un fallo de etiqueta no frena la venta | Si Odoo rechaza crear el tag, el pedido igual se inyecta y queda logueado |

---

## 3) Alcance

### Incluido (v1)

- `OdooConnector.push_order`: setear `commitment_date` con la nota **releída justo antes del create**, y agregar el tag `Suplai`.
- Camino idempotente (la orden ya existe por `origin` / `client_order_ref`): completar tag y `commitment_date` si faltan. Hoy ese camino retorna sin escribir.
- `set_tienda_delivery_day` / `_write_odoo_commitment_date`: reintentar el write el tiempo que tarda una inyección real (hasta ~60 s), no 1,6 s.
- Después de un create exitoso, releer `pedidos.notas` una vez más y, si apareció una fecha que el create no tenía, escribir `commitment_date`.
- Parser: reconocer `Llega hoy` / `Hoy` usando la fecha del pedido en el timezone del tenant (`fixed_delivery_schedule.timezone`, default `America/Argentina/Buenos_Aires`).
- Script manual de backfill (no corre en el deploy) para `sale.order` con `origin` `SUPPLAI-%`: poner el tag; si la nota de Suplai tiene fecha parseable y `commitment_date` está vacío, escribirla.
- Tests en `backend/tests/test_erp_integration.py`.

### Fuera de alcance

- Cambiar `expected_date`. Es calculado; pisarlo no se sostiene y no es el campo de entrega.
- Columna nueva `pedidos.fecha_entrega`. La nota `FECHA DE ENTREGA:` ya es el contrato; el fallo es el momento en que se lee y se escribe.
- Confirmar la cotización en Odoo (`action_confirm`) ni crear el `stock.picking`. Varios pedidos de benfresh siguen en `draft`; el día vive en el `sale.order` igual.
- Otros ERPs (GEV ya manda `FECHA_ENTREGA_PEDIDO` por su propio payload).
- Reescribir el texto verbal que ve el cliente en WhatsApp. El agente puede seguir guardando `Llega el …`; el parser ya lo entiende. `Llega hoy` se cubre en el conector.
- UI de backoffice.

---

## 4) Decisiones de diseño

| Decisión | Por qué | Alternativa descartada |
|----------|---------|------------------------|
| Escribir `sale.order.commitment_date` | Es **Delivery Date / Fecha de entrega** en Odoo 19. En benfresh, cuando la nota ISO llegó a tiempo, el valor está ahí (`2026/05316`) | Escribir `expected_date`: es computed y en los pedidos sin día no refleja la ruta |
| Hora ancla `12:00:00` UTC | El mismo día calendario se ve en `America/New_York` (08:00) y en Argentina (09:00). Medianoche UTC corre el día hacia atrás en esas zonas | Mandar `00:00:00` o la hora local sin marcar timezone |
| Releer `notas` antes del create, write largo en el picker, y un write de cierre post-create | La carrera medida: el picker escribe la fecha después del `SELECT` inicial, y el write actual se rinde a los 1,6 s mientras el create tarda hasta ~35 s | Columna `fecha_entrega` en todos los tenants: migración amplia para un dato que la nota ISO ya guarda |
| En la orden ya existente, completar tag y fecha | El return idempotente de hoy deja huérfano al pedido si el primer create salió sin día | Confiar solo en el picker: si el proceso muere a los 2 s, nadie vuelve a escribir |
| Tag `crm.tag` nombre **Suplai**, comando `(4, id)` | `tag_ids` es el filtro nativo de ventas. `(4, id)` agrega sin borrar otras etiquetas del distribuidor. Búsqueda `ilike` `suplai` para no duplicar si ya lo crearon a mano | Prefijo en `origin` (ya existe `SUPPLAI-` y no se filtra como etiqueta) o un campo Studio |
| Si crear el tag falla, el pedido se inyecta igual | La etiqueta es operativa; perder la venta por un permiso de tags es peor | Abortar `push_order` |
| Backfill manual, no en el arranque | Hay `sale.order` históricos sin tag. Un script acotado a `origin ilike SUPPLAI-%` los marca sin reescribir pedidos del ERP | Migración automática al deploy, que escribiría en el Odoo del tenant sin una corrida explícita |

---

## 5) Comportamiento

### 5.1 Fecha de entrega

1. Normalizar `commitment_date` a `YYYY-MM-DD HH:MM:SS`.
   - `FECHA DE ENTREGA: 2026-10-12` → `2026-10-12 12:00:00`.
   - `FECHA DE ENTREGA: Llega el Viernes 9 de Octubre` → día 9, octubre, hora 12:00, año de la fecha del pedido (la heurística de año que ya existe se mantiene).
   - `FECHA DE ENTREGA: Llega hoy` o `Hoy` → fecha calendario del pedido en el timezone del tenant, hora 12:00.
2. `inject_order_to_erp` vuelve a leer `pedidos.notas` inmediatamente antes de `push_order` (el `SELECT` del inicio queda viejo si el cliente eligió el día mientras se resolvían partner y SKUs).
3. `push_order` manda `commitment_date` en el `create` cuando hay fecha.
4. Si la orden ya existía, `write` de `commitment_date` cuando el valor nuevo está presente y el actual está vacío o es distinto.
5. `_write_odoo_commitment_date` reintenta hasta **60 s** (intervalo ~2 s) mientras `write_commitment_date` devuelve false. La búsqueda de la orden usa el mismo dominio que la idempotencia: `origin = SUPPLAI-X` **o** `client_order_ref = SUPPLAI-X`.
6. Al volver del `create`, si la nota en BD ahora tiene fecha y el create no la mandó, un `write` de `commitment_date`.

`write_commitment_date` sigue pudiendo actualizar `note`. No borrar una nota de Odoo que el distribuidor haya editado: si el `sale.order` ya existe, actualizar `commitment_date` y **no** pisar `note` en el write de backfill / idempotencia. En el create inicial, `note` sigue siendo `pedidos.notas`, como hoy.

### 5.2 Etiqueta Suplai

1. `search_read` de `crm.tag` con `name ilike suplai`, `limit 1`.
2. Si no hay, `create` `{name: "Suplai", color: 9}`.
3. En el `create` del `sale.order`, `tag_ids: [(4, tag_id)]`.
4. Si la orden ya existe, `write` con el mismo `(4, tag_id)` (Odoo ignora el duplicado del vínculo).
5. Cache del `tag_id` en la instancia del conector para no buscarlo en cada línea.
6. Error de tag → log `ODOO_SUPLAI_TAG_FAILED` y seguir con el pedido.

### 5.3 Backfill

Script en `backend/scripts/`, corrida manual por schema:

```bash
cd backend
python scripts/odoo_backfill_suplai_tag_and_delivery.py --schema benfresh
python scripts/odoo_backfill_suplai_tag_and_delivery.py --schema benfresh --apply
```

Sin `--apply` solo imprime. Con `--apply`:

- Busca `sale.order` con `origin ilike SUPPLAI-%`.
- Agrega el tag si falta.
- Si `commitment_date` está vacío, lee `pedidos.notas` del id numérico de `SUPPLAI-{id}` y escribe la fecha cuando el parser la resuelve.

No toca pedidos cuyo `origin` no es de Suplai.

---

## 6) Criterios de aceptación

### AC-1 — Create con fecha ISO

- **Given** un pedido con `notas = "ENVÍO A DOMICILIO: Ruta programada | FECHA DE ENTREGA: 2026-10-12"`.
- **When** `push_order`.
- **Then** el `create` incluye `commitment_date = "2026-10-12 12:00:00"` y `tag_ids` con el id del tag Suplai.

### AC-2 — El día llega después de confirmar

- **Given** benfresh (`client_picks_delivery_day`) y un `sale.order` que se crea sin fecha.
- **When** el cliente elige `2026-10-13` mientras la inyección sigue en curso, o hasta 60 s después de que el `sale.order` aparece.
- **Then** `commitment_date` queda en `2026-10-13 12:00:00` y el tag Suplai está puesto.

### AC-3 — Orden ya existente

- **Given** un `sale.order` con `origin = SUPPLAI-10`, sin tag y sin `commitment_date`, y la nota en Suplai ya tiene `FECHA DE ENTREGA: 2026-10-12`.
- **When** corre de nuevo `push_order` (o el backfill con `--apply`).
- **Then** se agregan tag y `commitment_date`. `client_order_ref` y las líneas no se recrean.

### AC-4 — `Llega hoy`

- **Given** la nota `FECHA DE ENTREGA: Llega hoy` y fecha de pedido `2026-10-12` en `America/New_York`.
- **When** se parsea para Odoo.
- **Then** `commitment_date = "2026-10-12 12:00:00"`.

### AC-5 — El tag no bloquea

- **Given** `crm.tag.create` lanza error de acceso.
- **When** `push_order`.
- **Then** el `sale.order` se crea, el resultado sigue siendo `enviado_erp`, y queda el log `ODOO_SUPLAI_TAG_FAILED`.

---

## 7) Orden de implementación

Un solo repo. No hace falta PR de agente ni de backoffice.

| Paso | Repo | Rama | Dependencia |
|------|------|------|-------------|
| 1 | `backend/` | `feat/odoo-entrega-etiqueta` desde `origin/main` | Ninguna. Sin migración |
| 2 | Corrida manual del backfill en `benfresh` | — | Después del merge, con alguien mirando Odoo |

Merge: solo backend. No hay consumidor que desplegar antes.

---

## 8) Migración de base de datos

Sin migración de BD.

El backfill escribe en Odoo, no en Postgres. Rollback del código: dejar de mandar tag y fecha en pushes nuevos. Los `sale.order` ya etiquetados conservan el tag; sacarlo es un write manual o una segunda corrida que no entra en este spec.

---

## 9) Plan de prueba en CI/CD

En el PR de `backend/`:

- Extender `tests/test_erp_integration.py`:
  - `push_order` con nota ISO afirma `commitment_date` y `tag_ids: [(4, <id>)]`.
  - Orden ya existente: el mock de `search_read` devuelve un id y el siguiente `write` lleva tag y `commitment_date`.
  - Parser: ISO, verbal, `Llega hoy` con `base_date`, nota vacía → `None`.
  - Tag create que explota: `push_order` igual devuelve `enviado_erp`.
- `pytest tests/test_erp_integration.py` verde.
- No hay smoke de migración.

El backfill no entra al CI (habla con Odoo real).

---

## 10) Plan de prueba humana (antes del PR)

No hace falta backoffice ni el mapa. Hace falta el backend de test o, para benfresh, una corrida contra Odoo con un pedido de prueba acordado.

1. Tests locales: `cd backend && source venv/bin/activate && pytest tests/test_erp_integration.py -q`.
2. En Odoo de benfresh, abrir un `sale.order` ya inyectado que **sí** tiene fecha, por ejemplo `2026/05316`:
   - **Fecha de entrega** (`commitment_date`) = 12 oct 2026, 08:00 hora Nueva York.
   - **Fecha prevista** (`expected_date`) es otra cosa; no usarla para validar.
   - Tags vacío (todavía no está el cambio).
3. Después del deploy, pedido de prueba en la tienda de benfresh: confirmar, elegir un día, esperar a que `pedidos.estado` pase a `enviado_erp`.
4. En ese `sale.order`: tag **Suplai**, Fecha de entrega = el día elegido a las 08:00 ET, `origin` `SUPPLAI-{id}`.
5. Backfill en seco y después `--apply`. Un pedido viejo `SUPPLAI-%` muestra el tag. Uno con nota ISO y `commitment_date` vacío (si queda alguno) pasa a tener fecha. Uno con `notas` null sigue sin fecha: no hay día que inventar.

---

## 11) Riesgos

| Riesgo | Mitigación |
|--------|------------|
| El usuario de Odoo mira Fecha prevista | El spec y la prueba humana nombran el campo. No hay forma estable de reemplazar `expected_date` |
| Otro tenant Odoo sin permiso de `crm.tag` | El pedido se inyecta igual; el log avisa |
| Dos procesos crean el tag `Suplai` a la vez | `search` antes de `create`; si el create choca por duplicado, volver a buscar |
| Backfill pisa una nota editada en Odoo | El write de backfill e idempotencia no manda `note` |
| `Llega hoy` inyectado al día siguiente | Se usa la fecha del pedido en el timezone del tenant, no `now()` del servidor |
