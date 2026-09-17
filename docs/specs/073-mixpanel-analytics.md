# 073 — Mixpanel: uso de usuarios en Backoffice, Tienda y Field

**Estado:** En implementación  
**Fecha:** 2026-09-17  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`, `wholesale-catalog-app`, `field-app`  
**Ramas sugeridas:** `feat/mixpanel-analytics`  
**Migraciones necesarias:** no

---

## Contexto

Hoy no hay un identificador estable de usuario ni un eje multi-tenant en analytics de producto. Vercel Analytics en tienda cuenta páginas, no funnels de negocio. Sin `tenant_schema` / `app` / `entidad`, cualquier evento futuro se mezcla entre distribuidoras (el mismo problema que con GA).

Duele a producto y CS: no se puede medir abandono de carrito, % de tareas Field completadas, ni adopción de Copilot/promos por tenant.

---

## Objetivo

Instrumentar Mixpanel con identidad namespaced, super properties multi-tenant y una taxonomía corta (15 eventos de producto + 1 de ERP) para armar funnels reales desde el día uno.

### Métricas de éxito

- En Mixpanel se puede filtrar un evento por `app`, `tenant_schema` y `entidad` sin tocar el código del evento.
- Un mismo número interno (p. ej. `id=42`) en backoffice, tienda y field **no** aparece como la misma persona.
- Un invitado de tienda que después hace login une el funnel pre-login al PdV (`identify`).
- `pedido_confirmado` / `pedido_confirmado_field` existen aunque el browser no ejecute JS.
- Sin token, las apps y el backend no fallan.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Proyectos Mixpanel | Uno solo, property `app` | Funnels cross-app (Field → pedido → backoffice). Un token, un lugar para mirar. | Un proyecto por app: no hay funnel cruzado; 3x dashboards. |
| SDK cliente | `mixpanel-browser` + wrapper `lib/analytics.ts` copiado en los 3 frontends | Mismo spirit sin paquete interno todavía. Cada repo versiona independiente. | Paquete npm compartido: overhead de publish para v1. Segment/RudderStack: overkill. |
| Eventos de negocio | Backend canónico (`mixpanel` Python) | Confirmación de pedido / tareas / ERP no pueden depender de JS del cliente. | Doble track cliente+server: cuenta dos veces. Solo cliente: pierde el evento si el tab se cierra. Proxy total vía backend: retrasa instrumentar UI. |
| `distinct_id` | `{app}:{schema}:{id}` | Evita colisiones entre entidades y tenants en un solo proyecto. | ID crudo: `user_id=42` y `cliente_id=42` se fusionan. Solo `{app}:{id}`: choca entre tenants. |
| Invitado tienda | Distinct anónimo de Mixpanel → `identify` al login | Une modo invitado + carrito al PdV. | Un id `...:guest` por tenant: todos los invitados son una persona. No trackear invitados: pierde abandono pre-login. |
| PII en People | No teléfono ni email en v1 | El token de proyecto es público en el bundle; teléfono es dato personal. | `people.set({ $email, $phone })`: riesgo innecesario para el primer funnel. |
| Token | `NEXT_PUBLIC_MIXPANEL_TOKEN` (front) y `MIXPANEL_TOKEN` (backend), mismo valor | El project token de Mixpanel es el que usa el JS SDK; el backend usa el mismo. | Token distinto por app: contradice proyecto único. |
| Fallos Mixpanel | No-op / log, nunca rompe el request de negocio | Analytics es best-effort. | `await` Mixpanel en el path de confirmar pedido: añade latencia y puntos de falla. |
| HQ admin backoffice | Fuera de v1 | El inventario de funnels es supervisor de tenant (A2/A4), no consola plataforma. | Identificar `_admin`: se puede sumar después. |

---

## Alcance explícito

### Incluido (v1)

- Init + super properties + `identify` en backoffice, tienda y field.
- Wrapper cliente `lib/analytics.ts` (copiado) y cliente Python `services/mixpanel_client.py`.
- Taxonomía de la sección siguiente.
- Env vars documentadas en `env.example` de cada repo. Railway: mismo token en los 4 servicios.
- Tests unitarios del wrapper (no-op sin token, formato de `distinct_id`, no throw).
- Tests backend: Mixpanel mockeado; confirmar pedido sigue OK si Mixpanel falla.

### Fuera de alcance

- Autocapture, session replay, heatmaps.
- Agente WhatsApp, landing, sales-engine, sniffer.
- Dashboards / insights / funnels ya armados en la UI de Mixpanel (se arman a mano post-deploy).
- People con PII; group analytics por distribuidora.
- Paquete npm compartido.
- HQ admin (`admin-auth-context`).
- Migración de BD.

---

## Identidad

Formato: `{app}:{schema}:{id}`

| App | `app` | `entidad` | `id` | Momento de `identify` |
|-----|-------|-----------|------|------------------------|
| Backoffice | `backoffice` | `A` | `profile.id` (UUID supervisor) | Auth resuelta (`AuthProvider`) |
| Tienda | `tienda` | `B` | `cliente.id` (int interno, **nunca** el teléfono) | Login por teléfono OK |
| Field | `field` | `C` | `vendedor.id` | Login por teléfono OK |

Invitado tienda: no llamar `identify`. Mixpanel usa el distinct anónimo del dispositivo. Al login, `identify('tienda:{schema}:{cliente.id}')` une el historial anónimo al PdV.

Logout (backoffice / field / tienda): `mixpanel.reset()` para no heredar identidad en dispositivo compartido.

### Super properties (todas las apps, al `init`)

```ts
{
  tenant_schema: schema,           // ej. "kiki_market"
  distribuidora_nombre: nombre,    // ej. "Kiki Market"
  entidad: "A" | "B" | "C",
  app: "backoffice" | "tienda" | "field"
}
```

Backend: no hay `register()`. Cada `track` envía `distinct_id` + las mismas properties en el payload.

People (v1, al `identify`): `$name` no; solo `app`, `tenant_schema`, `entidad`.

---

## Taxonomía de eventos

Propiedades listadas = extra al super set.

### Tienda (`app=tienda`)

| Evento | Fuente | Archivo | Props extra |
|--------|--------|---------|-------------|
| `login_telefono` | Cliente | `components/login-form.tsx` (rama no-guest) | — |
| `modo_invitado_iniciado` | Cliente | `components/login-form.tsx` (rama guest) | — |
| `producto_agregado_carrito` | Cliente | `components/catalog-client.tsx` `addToCart` | `sku`, `cantidad` |
| `pedido_repetido` | Cliente | `onRepeatPedido` (historial) | `pedido_origen_id` |
| `pedido_confirmado` | Backend | `routers/tienda.py` `confirmar_pedido_tienda` | `pedido_id`, `total`, `items_count` |

### Field (`app=field`)

| Evento | Fuente | Archivo | Props extra |
|--------|--------|---------|-------------|
| `ruta_abierta` | Cliente | `app/[schema]/home/page.tsx` (carga OK) | `pdv_count` |
| `pdv_visitado` | Cliente | `app/[schema]/pdv/[id]/page.tsx` | `cliente_id` |
| `torneo_visto` | Cliente | `app/[schema]/torneo/page.tsx` | `torneo_id` (si hay activo) |
| `pedido_confirmado_field` | Backend | `services/vendedor_pedidos_service.py` `confirmar_pedido` | `pedido_id`, `cliente_id`, `total` |
| `tarea_completada` | Backend | mismo confirm, un evento por ítem de `tareas_completadas` | `tarea_id`, `tipo`, `pedido_id` |

### Backoffice (`app=backoffice`)

Cliente, **después** de HTTP 2xx (el supervisor ya tiene JS).

| Evento | Archivo |
|--------|---------|
| `sign_up_completed` | `contexts/auth-context.tsx` signup OK (`sign_up_method`, `platform`) |
| `promo_creada` | `components/promotions-modal.tsx` POST `/api/promociones` |
| `estrategia_creada` | `components/estrategias/strategy-form-context.tsx` create OK |
| `vendedor_alta` | `components/vendedores/use-vendedores-management.tsx` POST `/api/vendedores` |
| `objetivo_creado` | `components/field/FieldObjetivosAdmin.tsx` create OK |
| `copilot_pregunta_enviada` | `components/copilot/CopilotChatView.tsx` `sendMessage` del usuario |

### Backend extra

| Evento | Archivo | Props extra |
|--------|---------|-------------|
| `erp_pedido_enviado` | `routers/erp.py` `push_order_to_erp` | `pedido_id`, `conector`, `ok` (bool) |

El cliente **no** dispara `pedido_confirmado` ni `pedido_confirmado_field`.

---

## Contrato del wrapper cliente

Cada frontend copia el mismo spirit (nombres y firma iguales):

```ts
export type Entidad = "A" | "B" | "C"
export type AppName = "backoffice" | "tienda" | "field"

export type AnalyticsContext = {
  tenant_schema: string
  distribuidora_nombre: string
  entidad: Entidad
  app: AppName
}

export function initAnalytics(context: AnalyticsContext): void
export function identifyUser(distinctId: string): void
export function resetAnalytics(): void
export function track(event: string, props?: Record<string, unknown>): void
export function distinctId(app: AppName, schema: string, id: string | number): string
```

`distinctId` → `` `${app}:${schema}:${id}` ``.

Reglas:

- Solo browser (`typeof window !== "undefined"`).
- Sin `NEXT_PUBLIC_MIXPANEL_TOKEN` o string vacío: todas las funciones no-op.
- `init` es idempotente.
- Nunca throw hacia UI.

Backend Python (equivalente):

```python
def track(event: str, *, distinct_id: str, tenant_schema: str, distribuidora_nombre: str, entidad: str, app: str, **props) -> None: ...
```

Fire-and-forget (`asyncio.create_task` o thread); log warning si Mixpanel falla. Pool HTTP propio, no usa Postgres.

---

## Requisitos funcionales

- `RF-1`: Al resolver sesión, cada app llama `initAnalytics` (super properties) y, si hay usuario conocido, `identifyUser`.
- `RF-2`: `distinct_id` siempre namespaced `{app}:{schema}:{id}`.
- `RF-3`: Invitado de tienda no se identifica; login posterior sí y fusiona.
- `RF-4`: Eventos de la taxonomía v1 disparan en los puntos indicados, con las props extra.
- `RF-5`: Backend emite `pedido_confirmado`, `pedido_confirmado_field`, `tarea_completada` y `erp_pedido_enviado`.
- `RF-6`: Sin token, producto funciona igual.

## Requisitos no funcionales

- `RNF-1` Performance: Mixpanel no bloquea login ni confirmación de pedido.
- `RNF-2` Seguridad: no enviar teléfono, email ni tokens. `sku` / ids internos sí.
- `RNF-3` Multi-tenant: `tenant_schema` en **todos** los eventos (super property o payload server).
- `RNF-4` Observabilidad: log warning si el SDK/backend no puede enviar; no ticket IA.
- `RNF-5` Conexiones: el cliente Mixpanel Python no abre conexiones a Postgres (no cuenta en el límite 60).

---

## Criterios de aceptación (Given / When / Then)

### `AC-1` Identidad namespaced

- **Given** un supervisor `profile.id=17` en schema `kiki_market`
- **When** inicia sesión en backoffice
- **Then** Mixpanel recibe `identify("backoffice:kiki_market:17")` y super properties `app=backoffice`, `entidad=A`, `tenant_schema=kiki_market`

### `AC-2` Sin colisión cross-app

- **Given** `cliente.id=42` y `vendedor.id=42` en el mismo tenant
- **When** ambos generan eventos
- **Then** Mixpanel los trata como personas distintas (`tienda:…:42` vs `field:…:42`)

### `AC-3` Funnel invitado → login

- **Given** un usuario en modo invitado que agrega un SKU al carrito
- **When** después hace login por teléfono
- **Then** `producto_agregado_carrito` queda unido al `distinct_id` `tienda:{schema}:{cliente.id}`

### `AC-4` Pedido confirmado sin JS

- **Given** un POST exitoso a confirmar pedido tienda
- **When** el backend persiste el pedido
- **Then** se encola `pedido_confirmado` con `pedido_id` y `total`, aunque el cliente no haya llamado `track`

### `AC-5` No doble conteo

- **Given** confirmación de pedido desde tienda o Field
- **When** el flujo termina OK
- **Then** existe **un** evento de confirmación (el del backend), no uno extra del cliente

### `AC-6` Degradación

- **Given** token ausente o Mixpanel caído
- **When** el usuario confirma un pedido o navega
- **Then** la app responde 2xx / UI normal; no hay excepción no capturada

### `AC-7` Logout

- **Given** un usuario identificado
- **When** hace logout
- **Then** se llama `resetAnalytics()` antes de limpiar la sesión local

---

## Casos borde

- `CB-1`: Init dos veces (Strict Mode / remount) → un solo `mixpanel.init`.
- `CB-2`: Login guest y luego teléfono en el mismo tab → `identify` una vez con el `cliente.id`.
- `CB-3`: `confirmar_pedido` Field ya confirmado (`already_confirmed`) → no re-emitir `pedido_confirmado_field` ni `tarea_completada`.
- `CB-4`: `tareas_completadas` vacío → no emitir `tarea_completada`.
- `CB-5`: Copilot `sendMessage` de sistema / bot → no emitir `copilot_pregunta_enviada`.
- `CB-6`: Dispositivo compartido en Field: logout hace `reset`; el siguiente vendedor no hereda el distinct.

---

## Impacto técnico

| Repo | Archivos |
|------|----------|
| `product-management-app` | `lib/analytics.ts`, `contexts/auth-context.tsx`, `components/promotions-modal.tsx`, `components/estrategias/strategy-form-context.tsx`, `components/vendedores/use-vendedores-management.tsx`, `components/field/FieldObjetivosAdmin.tsx`, `components/copilot/CopilotChatView.tsx`, `env.example` |
| `wholesale-catalog-app` | `lib/analytics.ts`, `components/login-form.tsx`, `components/catalog-client.tsx`, `env.example` |
| `field-app` | `lib/analytics.ts`, `components/auth/FieldAuth.tsx`, `app/[schema]/home/page.tsx`, `app/[schema]/pdv/[id]/page.tsx`, `app/[schema]/torneo/page.tsx`, `env.example` |
| `backend-supabase` | `services/mixpanel_client.py`, `routers/tienda.py`, `services/vendedor_pedidos_service.py`, `routers/erp.py`, tests, `.env.example` |
| `suplai-platform` | este spec |

**Migraciones necesarias:** no.

**Feature flag / env:** sí — `NEXT_PUBLIC_MIXPANEL_TOKEN` / `MIXPANEL_TOKEN`. Ausente = off.

---

## Orden de implementación (cross-repo)

Merge **backend primero** (eventos de pedido visibles aunque el front todavía no identifique). Frontends en paralelo después.

| Orden | Repo | Rama | PR |
|-------|------|------|-----|
| 1 | `backend-supabase` | `feat/mixpanel-analytics` | Mixpanel server + 4 eventos de negocio |
| 2a | `wholesale-catalog-app` | `feat/mixpanel-analytics` | wrapper + login/carrito/repeat |
| 2b | `field-app` | `feat/mixpanel-analytics` | wrapper + ruta/pdv/torneo + identify |
| 2c | `product-management-app` | `feat/mixpanel-analytics` | wrapper + identify + 5 eventos UI |
| doc | `suplai-platform` | `feat/mixpanel-analytics` | este spec |

`field-app` no está en el workspace Cursor actual; hay que sumarlo (o trabajar en `source/field-app`) antes del PR 2b.

---

## Migración de base de datos

Sin migración de BD. No se escribe en Postgres. El cliente Mixpanel no usa el pooler.

---

## Plan de prueba en CI/CD

- **Backend:** tests con Mixpanel mockeado (`unittest.mock` sobre `mixpanel_client.track`). Cubrir: confirm tienda emite `pedido_confirmado`; confirm Field emite `pedido_confirmado_field` + N `tarea_completada`; `already_confirmed` no re-emite; `track` que lanza no falla el endpoint.
- **Frontends:** tests del wrapper (token vacío → no llama al SDK; `distinctId` formatea; `init` doble no explota). Donde ya hay tests de login/add-to-cart, assert de `track` mockeado.
- Checks existentes (`pytest`, `tsc` / lint de cada repo) verdes.
- Gap: no hay e2e que abra Mixpanel Live View. Aceptable: unit + prueba humana con token de dev.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000`, backoffice `3000`, field `3001`, tienda `3002`. Tenant de prueba (p. ej. `demo` o `kiki_market`). Token Mixpanel de **proyecto de desarrollo** (no prod) en `.env` local.

1. Abrir Mixpanel → Live View filtrado por `tenant_schema` del tenant de prueba.
2. **Tienda:** modo invitado → agregar producto → login teléfono → confirmar pedido. Ver `modo_invitado_iniciado`, `producto_agregado_carrito`, `login_telefono`, y `pedido_confirmado` (este último con `app=tienda` desde servidor). El distinct del carrito debe unirse al PdV.
3. **Field:** login vendedor → home (ruta) → abrir un PdV → torneo. Confirmar un pedido de prueba. Ver `ruta_abierta`, `pdv_visitado`, `torneo_visto`, `pedido_confirmado_field`.
4. **Backoffice:** login supervisor → crear promo / estrategia / vendedor / objetivo (en ambiente de prueba) → mandar una pregunta a Copilot. Ver los 5 eventos con `entidad=A`.
5. Filtro `app=tienda` no debe listar eventos de Field.
6. Quitar el token, repetir un login: la app sigue funcionando.

OK si Live View muestra los eventos con super properties correctas y sin teléfono en el payload.

---

## Riesgos y rollback

| Riesgo | Mitigación |
|--------|------------|
| Token de prod en un PR / screenshot | Proyecto Mixpanel de dev vs prod; rotar token si se filtra. El project token es semi-público por diseño (va en el bundle). |
| Eventos duplicados en un refactor futuro | Contrato: confirmación solo backend. Comentario en el wrapper y en este spec. |
| Mixpanel lento | Timeout corto + fire-and-forget en backend; SDK browser asíncrono. |
| Identidad mal namespaced | Helper único `distinctId`; tests. |

**Rollback:** quitar las env vars (todo queda no-op) o revertir los PRs. No hay datos en nuestra BD que revertir.

---

## Evidencia de cierre

- PRs (completar al mergear).
- Tests CI verdes.
- Captura o nota de Live View en staging con un evento de cada `app`.
