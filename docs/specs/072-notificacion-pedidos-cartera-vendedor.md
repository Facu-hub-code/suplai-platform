# 072 — Notificación de pedidos solo a la cartera del vendedor

**Estado:** En implementación  
**Fecha:** 2026-09-17  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`, `agente-conversacional-multi_tenant`  
**Ramas sugeridas:** `feat/order-notif-cartera`  
**Relaciona:** agent [047](../../../agente-conversacional-multi_tenant/docs/specs/047-notificacion-confirmacion-pedido-vendedores.md) (estrategias `all` / `round_robin` / `weighted` / `random`); backoffice [069](../../../product-management-app/doc/specs/069-order-notification-meta-template-ui.md); backend `OrderNotificationConfig` en `reglas_negocio.order_notification`

---

## Contexto

Hoy, cuando un cliente confirma un pedido por el agente, WhatsApp avisa a **todos los vendedores tildados** en Configuración → notificaciones de pedido (`strategy: "all"`). El vendedor se entera de ventas que no son de su cartera.

Eso duele en equipos con preventistas / zonas distintas: filtración comercial, ruido y “¿por qué me llega el pedido de otro?”.

### Evidencia (MCP Supabase, 2026-09-17, proyecto `cvlbietibaaehgeimxgw`)

- Cartera = `{tenant}.vendedores_clientes` (`vendedor_id`, `cliente_id`, `activo boolean default true`). PK `(vendedor_id, cliente_id)`: un cliente **puede** tener más de un vendedor.
- `clients` solo tiene `vendedor` (varchar, nombre denormalizado). **No** hay `clients.vendedor_id` ni `pedidos.vendedor_id` en `gonzales` (tenant de referencia). La asignación operativa es la tabla N:N.
- Tenants con `order_notification` habilitado al momento de esta spec: `al_fuego`, `benfresh`, `cordoba_frost`, `del_corro`, `dimer`, `gonzales`, `suplai`. **Todos** usan `strategy = all`. `cordoba_frost` tiene 3 suscriptores; `dimer` tiene 2.

El despacho WhatsApp a vendedores corre en el **agente** (`send_order_confirmation_notification` al `confirm_order`) y, desde esta entrega, también en el **backend** al confirmar por **tienda** o **Field** (`run_order_confirmed_full_effects` → `send_seller_order_notification`). El webhook `order_confirmed` del agente **no** reenvía este WhatsApp (evita doble ping).

---

## Objetivo

Que el operador pueda marcar, por vendedor suscrito, si recibe **todos** los pedidos o **solo los de su cartera**. Un supervisor puede seguir viendo todo; el preventista no se entera de las ventas del resto.

### Métricas de éxito

- Un tenant con 2 vendedores en cartera distinta: el pedido del cliente A notifica solo al dueño de A (si está tildado con alcance cartera).
- Configuración existente (`scope` ausente) **no cambia** de comportamiento.
- Pedido confirmado aunque nadie matchee cartera: no se revierte; queda log de skip.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Superficie de config | Campo `scope` **por suscriptor** (`all` \| `cartera`) | Permite mixto: dueño/supervisor ve todo y el vendedor solo lo suyo. Expande la asignación sin romper las 4 estrategias. | 5ª estrategia global `cartera`: no permite mixto. Filtro previo a round-robin sobre todos: un supervisor “siempre elegible” distorsiona el turno. |
| Default | `scope` omitido = `all` | Backward compatible. Hoy todos los tenants productivos están en `all`. | Migrar JSON a `cartera` por tenant: cambiaría comportamiento sin consentimiento. |
| Fuente de cartera | `{schema}.vendedores_clientes` con `activo = true` | Misma tabla que Field, agente vendedor y Fase 4 de implementación. Índice `(cliente_id, vendedor_id)` ya existe. | `clients.vendedor` (texto): frágil, un solo nombre, no es FK. `clients.vendedor_id`: no existe en el schema de referencia. |
| Varios vendedores en el mismo cliente | Notificar a **todos** los suscriptores `cartera` que lo tengan activo | La PK es N:N a propósito (cuentas compartidas / backup). | Elegir “el primero” o el de peso más alto: pierde a un co-dueño. |
| Intersección con suscriptores | Allowlist sigue mandando: cartera ∩ tildados ∩ activos con teléfono | Un vendedor dueño que **no** está tildado no recibe (igual que hoy). | Auto-incluir a cualquier dueño de cartera: saltaría el selector del backoffice. |
| Mixto con estrategias | 1) Destino `all` = aplicar `strategy` entre suscriptores `scope=all`. 2) Destino `cartera` = dueños del cliente. 3) Unión sin duplicar. | El round-robin/peso sigue sirviendo para **pool de supervisores**. Los de cartera no entran al sorteo: si el cliente es de Juan, Juan siempre se entera. | Aplicar round-robin sobre el set ya filtrado: un supervisor siempre elegible se lleva casi todos los turnos. |
| Cliente sin cartera | No enviar a nadie de `scope=cartera`. Si tampoco hay `scope=all` elegible → skip + log. **No** caer a “todos los tildados”. | El problema es privacidad; filtrar mal es peor que un pedido sin ping. | Fallback a `all`: reintroduce el leak. Ticket `ia_tickets` automático: ruido en backoffice, se deja para v1.1. |
| Persistencia vendedor↔pedido | No | Fuera de 047; esta spec no asigna el pedido, solo el WhatsApp. | Escribir `pedidos.vendedor_id`: la columna no está; es otro producto. |
| Tienda / Field | Backend porta el mismo algoritmo y envía desde `run_order_confirmed_full_effects` si `source` es `tienda` o `field` | El pedido de tienda no pasa por `confirm_order` del agente; el vendedor no se enteraba. El HTTP de confirmar no cambia (background, best-effort). | HTTP backend→agente: hop extra y el agente local no tiene outbound. Meter este send en el webhook del agente: duplicaría ping en `confirm_order`. |
| Tickets IA / errores de sistema | Fuera de alcance | El pedido del usuario es “ventas del resto”. Un ticket de asistencia o un error Meta no es una venta de cartera. | Reusar el mismo `scope` en `custom_ia_tickets_notification`: se puede copiar después si hace falta. |
| Migración SQL | No | Solo JSON en `reglas_negocio.order_notification.subscribers[]`. | Tabla de preferencias: duplica la UI que ya edita `reglas_negocio`. |

---

## Alcance explícito

### Incluido (v1)

- `subscribers[].scope`: `"all"` (default) o `"cartera"`.
- UI backoffice en la lista de vendedores receptores de **notificación de pedidos**: toggle por fila “Solo su cartera”.
- Copy de ayuda: qué pasa si el cliente no está asignado; que el selector de estrategia aplica a quienes reciben **todos** los pedidos.
- Validación backend (Pydantic) del literal; valor inválido → 422.
- Dispatcher del agente: resolución de destinatarios según la tabla de más abajo.
- Dispatcher del backend (misma config `order_notification`): al confirmar por **tienda** o **Field**. `source=agente` no dispara (el agente ya mandó).
- Logs: `order_notification_cartera_matched`, `order_notification_no_portfolio_match` (tenant, order_id, client_id, vendedor_ids; **sin** teléfonos).
- Tests unitarios de parseo de política y de selección de destinatarios (incluye mixto, N:N, skip).
- Tenants actuales: **sin backfill**. El operador tilda el alcance cuando lo necesite.

### Fuera de alcance

- `custom_ia_tickets_notification` y `system_errors_notification`.
- Crear `ia_tickets` cuando no hay match de cartera.
- Asignar vendedor al pedido en BD.
- Reasignar o auditar calidad de `vendedores_clientes` (si la cartera está mal, la notificación estará mal).
- Alcance por zona geográfica (`vendedor_geo_zones`) en vez de cartera explícita.
- Cambiar plantilla Meta, texto del mensaje o `human_order_finish`.

---

## Contrato de configuración

`public.distribuidoras.reglas_negocio.order_notification` (JSONB). Claves existentes sin cambio. Suscriptor:

```json
{
  "enabled": true,
  "strategy": "all",
  "subscribers": [
    { "vendedor_id": 1, "weight": 1, "scope": "all" },
    { "vendedor_id": 2, "weight": 1, "scope": "cartera" }
  ]
}
```

| Campo | Default si falta | Notas |
|-------|------------------|--------|
| `scope` | `"all"` | Literal. El parser del agente y Pydantic del backend tratan omitido / null como `all`. |
| `weight` | `1` | Solo aplica a suscriptores `scope=all` cuando `strategy` es `weighted`. |

Ejemplo mixto: el dueño (id 1) recibe **cada** pedido; el preventista (id 2) solo si el cliente está en su `vendedores_clientes` activo.

---

## Algoritmo de destinatarios

Partir del set actual: vendedores **activos**, con teléfono, cuyo `id` está en `subscribers` (igual que 047).

1. `pool_all` = suscriptores con `scope=all`.
2. `pool_cartera` = suscriptores con `scope=cartera` cuyo `vendedor_id` aparece en:

```sql
SELECT vendedor_id
FROM vendedores_clientes
WHERE cliente_id = :client_id
  AND activo = true;
```

   Una query por pedido (no N+1). `search_path` del tenant.

3. `from_strategy` = aplicar `strategy` (`all` / `random` / `round_robin` / `weighted`) **solo** sobre `pool_all`. Si `pool_all` está vacío, `from_strategy = []` (no se sortea sobre cartera).
4. Destinatarios = unión `from_strategy ∪ pool_cartera`, dedupe por `vendedor_id`.
5. Si el set queda vacío: no enviar, log `order_notification_no_portfolio_match`, el pedido ya confirmado sigue igual (RNF de 047).

`round_robin` / `weighted` cuentan eventos `order_notification_sent` como hoy; no se cambia el contador. Un envío mixto (supervisor + vendedor de cartera) registra **un evento por destinatario**, igual que `strategy=all` con varios destinos.

---

## Orden de implementación

Cross-repo. El humano mergea en GitHub. Orden: **backend (validación) → backoffice (UI) → agent (runtime)**.

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `suplai-platform` | `feat/order-notif-cartera` | Esta spec |
| 2 | `backend-supabase` | `feat/order-notif-cartera` | `SellerSubscriber.scope`; dispatcher tienda/Field; tests PATCH + recipientes |
| 3 | `product-management-app` | `feat/order-notif-cartera` | Toggle por vendedor; default `all`; copy |
| 4 | `agente-conversacional-multi_tenant` | `feat/order-notif-cartera` | Parser + dispatcher + tests |

Dependencia: si el backoffice manda `scope` **antes** de que el backend lo declare en el modelo, Pydantic (extra ignore) **no valida** el literal y un typo quedaría persistido. Por eso backend mergea primero.

Specs puntero cortos en backend / backoffice / agent al implementar, como en 071.

---

## Migración de base de datos

**Sin migración de BD.** No hay tablas ni columnas nuevas.

- Cambio de datos: JSON opcional `subscribers[].scope` en `public.distribuidoras.reglas_negocio`.
- Seed / backfill: no. Omitido = `all` = comportamiento actual.
- Rollback: quitar `scope` de la UI y del parser (default `all`); el JSON residual no hace daño. No hace falta UPDATE masivo.
- Riesgo: cartera vacía o desactualizada → pedidos sin WhatsApp a vendedores `cartera`. Mitigación: copy en UI + log; no silenciar el pedido.

---

## Requisitos funcionales

- `RF-1`: Cada suscriptor de `order_notification` acepta `scope`: `all` \| `cartera`. Ausente = `all`.
- `RF-2`: PATCH `/{schema}/distribuidora/config` rechaza `scope` distinto de esos dos literales (422).
- `RF-3`: Al confirmar pedido por el agente **o** por tienda/Field, los destinatarios se resuelven con el algoritmo de esta spec.
- `RF-4`: `scope=cartera` usa solo filas `vendedores_clientes.activo = true` del `client_id` del pedido.
- `RF-5`: Cliente con varios dueños: todos los suscriptores `cartera` coincidentes reciben el mensaje (además de `from_strategy`).
- `RF-6`: UI: por cada vendedor tildado, control “Solo su cartera”. Estrategia de asignación con texto: aplica a quienes **no** tienen ese alcance.
- `RF-7`: Con notificaciones habilitadas sigue haciendo falta ≥ 1 vendedor tildado. `scope=cartera` **no** exige 2 vendedores (a diferencia de round-robin).
- `RF-8`: El contenido del WhatsApp, plantilla Meta y fallback texto (047 / 065) no cambian.
- `RF-9`: Confirmación nueva de tienda o Field dispara el mismo dispatcher; `already_confirmed` no. El webhook `order_confirmed` del agente no lo vuelve a enviar.

---

## Requisitos no funcionales

- `RNF-1` Privacidad: un vendedor `cartera` **nunca** recibe un pedido cuyo cliente no está en su asignación activa, aunque `strategy=all`.
- `RNF-2` Compatibilidad: config actual sin `scope` = bit-idéntico en runtime a hoy.
- `RNF-3` Multi-tenant: query de cartera en el schema del tenant; eventos en `core.conversation_events` con `tenant_id`.
- `RNF-4` Observabilidad: logs estructurados con `client_id`, `order_id`, `matched_vendedor_ids`, `strategy_vendedor_ids`, `cartera_vendedor_ids`. Sin dump de teléfono.
- `RNF-5` Pooler: una sola query de cartera por despacho; no loop por vendedor.
- `RNF-6` Robustez: fallo de la query de cartera o del send no revierte el pedido (mismo `try/except` que 047).

---

## Criterios de aceptación (Given/When/Then)

### `AC-1` Default = comportamiento actual

- **Given** `order_notification.enabled`, `strategy=all`, dos suscriptores sin `scope` (o `scope=all`).
- **When** se confirma un pedido de cualquier cliente.
- **Then** ambos reciben el WhatsApp. Igual que 047 `AC-1`.

### `AC-2` Solo cartera, cliente de Juan

- **Given** Juan y María tildados, ambos `scope=cartera`. Cliente 10 solo en cartera activa de Juan.
- **When** el cliente 10 confirma.
- **Then** solo Juan recibe. María no. Evento `order_notification_sent` con `vendedor_id` de Juan.

### `AC-3` Solo cartera, cliente de nadie tildado

- **Given** los mismos Juan y María `scope=cartera`. Cliente 11 sin filas activas en `vendedores_clientes`, o solo asignado a un vendedor **no** tildado.
- **When** el cliente 11 confirma.
- **Then** nadie recibe WhatsApp de vendedor; el pedido queda confirmado; log `order_notification_no_portfolio_match`.

### `AC-4` Mixto supervisor + preventista

- **Given** Ana `scope=all`, Juan `scope=cartera`, `strategy=all`. Cliente 10 es de Juan.
- **When** se confirma el pedido del cliente 10.
- **Then** Ana y Juan reciben. Un pedido del cliente 99 (cartera de otro, o sin Juan) lo recibe **solo Ana**.

### `AC-5` Cartera compartida

- **Given** Juan y María `scope=cartera`; cliente 10 activo en ambos.
- **When** se confirma.
- **Then** ambos reciben.

### `AC-6` Round-robin no sortea preventistas

- **Given** Ana y Luis `scope=all` con `strategy=round_robin`; Juan `scope=cartera`. Último notificado del pool `all` fue Ana. Cliente 10 es de Juan.
- **When** se confirma.
- **Then** destinatarios = Luis (siguiente del round-robin entre Ana/Luis) **y** Juan. Juan no “gasta” el turno de Ana/Luis.

### `AC-7` UI guarda y relee

- **Given** backoffice en `localhost:3000`, notificación de pedidos habilitada.
- **When** el operador tilda “Solo su cartera” en un vendedor y guarda.
- **Then** el PATCH persiste `scope: "cartera"`; al recargar, el toggle sigue activo. Un `scope` basura en el PATCH responde 422.

### `AC-8` Vendedor inactivo o sin teléfono

- **Given** match de cartera pero el vendedor está inactivo o sin teléfono.
- **When** se despacha.
- **Then** se lo omite (047 `CB-1`). Si no queda nadie, skip + log.

### `AC-9` Confirmación por tienda

- **Given** `order_notification.enabled`, Facu tildado, Kiosko Facu en su cartera si `scope=cartera`.
- **When** el PDV confirma un pedido **nuevo** en la tienda.
- **Then** Facu recibe el WhatsApp 047. Un reintento `already_confirmed` no reenvía. Un `confirm_order` del agente no genera un segundo ping desde el backend.

---

## Casos borde y errores

- `CB-1` `activo = false` en `vendedores_clientes`: no cuenta como cartera (asignación dada de baja).
- `CB-2` Tabla `vendedores_clientes` ausente en un tenant hipotético: log de error, skip de `pool_cartera`, no crash; `pool_all` sigue.
- `CB-3` `strategy` weighted y todos los tildados son `cartera`: no hay pool para pesos; solo mandan los dueños del cliente. La UI no exige pesos.
- `CB-4` Mismo `vendedor_id` en `from_strategy` y `pool_cartera`: un solo WhatsApp.
- `CB-5` `scope` inválido en PATCH: 422. En runtime del agente (JSON viejo/corrupto): tratar como `all` y log warning (no tirar el pedido).
- `CB-6` Confirmación por tienda/Field: el backend despacha el mismo WhatsApp 047/072. El agente **no** vuelve a mandarlo vía webhook `order_confirmed`. `already_confirmed` no reenvía.

---

## Impacto técnico

| Capa | Archivos (orientativos) |
|------|-------------------------|
| Backend | `models/order_notification.py` (`SellerSubscriber.scope`); `services/order_notification_seller_dispatcher.py` enganchado a `run_order_confirmed_full_effects`; tests `test_distribuidoras_config.py`, `test_order_notification_seller_dispatcher.py` |
| Backoffice | `SellerSubscribersSection.tsx`, `OrderNotificationConfigSection.tsx` (normalize/save/toggle); **no** reusar el toggle en tickets/errores en v1 |
| Agente | `app/tenancy/business_rules.py` (`SellerSubscriber`); `app/services/order_notification_dispatcher.py`; `tests/test_order_notification_vendedores.py` |

- Migraciones SQL: **no**.
- Feature flag / env: **no**. El alcance se activa por tenant al tildar en UI.
- OpenAPI: el PATCH de config ya acepta `reglas_negocio` opaco; no hace falta endpoint nuevo.

---

## Plan de prueba en CI/CD

- **Backend:** `pytest tests/test_distribuidoras_config.py tests/test_order_notification_seller_dispatcher.py` — PATCH `scope`; recipientes cartera; pipeline `source=tienda` dispara dispatcher y `source=agente` no pega a Graph.
- **Agente:** `pytest tests/test_order_notification_vendedores.py` — AC-1 a AC-6 y CB-1/CB-4 con DB mock (fila de cartera). No pegarle a Meta.
- **Backoffice:** `npx tsc --noEmit` en el PR de UI. Gap: no hay Playwright de esta pantalla; el toggle se cubre con prueba humana.
- Checks existentes de 047 / 065 / provision Meta **siguen verdes**.
- Sin smoke de migración (no hay SQL).

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`), tienda `3002` si se prueba el carrito. WhatsApp real requiere backend **desplegado** (o local con credenciales Meta); no es un flag del backend de “apagar WhatsApp” aparte de las credenciales del tenant.

**Tenant:** `demo` (o el de staging). Hace falta: 2 vendedores activos **con teléfono de prueba**, 2 clientes, carteras distintas en `vendedores_clientes` (`activo=true`).

1. Backoffice → configuración del agente → notificación de pedidos. Dejar estrategia **Enviar a todos**. Tildar vendedor A y B, **sin** “Solo su cartera”. Guardar. Confirmar un pedido (agente): **ambos** reciben (regresión).
2. Tildar “Solo su cartera” en A y B. Guardar. Recargar: los toggles siguen. Pedido del cliente de A: **solo A**. Pedido del cliente de B: **solo B**.
3. Dejar A sin el toggle (`all`) y B con “Solo su cartera”. Pedido del cliente de B: A y B. Pedido de un cliente que no es de B: **solo A**.
4. Cliente sin fila en `vendedores_clientes`, ambos en cartera: el pedido confirma; nadie de B (si A también está en cartera, nadie). Ver log `order_notification_no_portfolio_match`.
5. Tickets de asistencia IA y errores de sistema: la UI **no** muestra el toggle (v1).
6. Mapa / resto de reglas de negocio: sin regresiones al guardar.
7. Tienda: login con el teléfono de Kiosko Facu, confirmar un pedido **nuevo**. El vendedor tildado (cartera o `all`) recibe el WhatsApp. Reintentar confirmar: `already_confirmed` **sin** segundo ping.

---

## Observabilidad y rollback

- Logs del dispatcher: match vs skip, ids de vendedor, no teléfonos.
- Rollback de producto: revertir PRs en orden inverso (agent → backoffice → backend). JSON con `scope` residual se ignora si el parser vuelve al default `all`.
- Rollback operativo (sin revertir código): en UI, destildar “Solo su cartera” / volver todos a `all`. Efecto inmediato en el próximo `confirm_order`.

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Cartera desactualizada (cliente nuevo sin asignar) | Copy en UI; skip explícito; no fallback a todos. Completar Fase 4 / asignación en Vendedores. |
| Doble interpretación “all” (estrategia vs scope) | Copy: la estrategia reparte entre quienes reciben **todos** los pedidos; el toggle recorta por cartera. |
| Doble ping agente + backend | El dispatcher backend solo corre con `source=tienda\|field`. El webhook del agente sigue en email/ERP/ticket, no en este send. |
| Merge backoffice antes que backend | Orden de PRs; si se invierte, un `scope` inválido podría persistir. Backend primero. |

---

## Evidencia de cierre

- PRs: (completar al implementar)
- Tests: lista de archivos en CI/CD
- Un tenant de staging con AC-2/AC-4 ejecutados a mano
