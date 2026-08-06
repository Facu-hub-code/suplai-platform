# Spec: Preparación tienda Benfresh (PDV Christian, imágenes, link post-pedido, origen)

**Fecha:** 2026-08-06  
**Tenant:** `benfresh`  
**Estado:** diseño aprobado (pendiente plan de implementación)

## Objetivo

Dejar la tienda web de Benfresh usable para prueba real de Christian como PDV: cliente con WhatsApp + lista Default, imágenes en los productos más pedidos (hotlink desde benfreshfood.com), segundo mensaje con link de tienda tras crear/editar pedido (flag spec 026), y marcar/mostrar `origen=tienda` en pedidos nacidos del login-tienda.

## Contexto (estado actual)

| Ítem | Hallazgo |
|------|----------|
| Christian | Vendedor `#4` (`549178640350466`); sigue como seller en WhatsApp |
| Teléfono PDV | `17864035046` hoy en cliente **DIXIE RIBS** `#13` |
| BENFRESH MARKET | `#11` con phone fake `9990000099911`, lista Default USD `#24` |
| `get_catalog_link` | Ya habilitada (opt-out; no está en `false`) |
| Imágenes | `0/202` productos con `image_url` |
| Flag catalog store | `metadata.catalog_store` ausente |
| `pedidos.origen` | Columna existe (default `suplai`); login-tienda no la setea; grilla Pedidos no la muestra |

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Perfil de prueba | Christian prueba tienda como PDV y sigue siendo vendedor | No cortar operación seller; la tienda autentica por `clients.phone_number`, independiente del actor WhatsApp | Pasar a solo-cliente / desactivar vendedor |
| Cliente PDV | Reusar `#11 BENFRESH MARKET LLC` + phone `17864035046` + lista `#24` | Ya tiene lista Default USD; nombre de marca claro | Crear cliente nuevo; reusar Dixie (precios Dixie) |
| Teléfono Dixie | Quitar `17864035046` de `#13` (placeholder) | `login-tienda` hace match exacto; un solo dueño del número | Dejar conflicto de teléfono |
| Tool link | No tocar `get_catalog_link` | Ya está disponible por opt-out | Forzar key `true` en `tools_habilitadas` (redundante) |
| Link post-pedido | Solo activar `metadata.catalog_store.append_link_after_order_tools=true` | Feature spec 026 ya en agente; cero código nuevo | Reimplementar mensaje / cambiar copy v1 |
| Imágenes | Script top 100 + match por nombre + **hotlink** al sitio | Rápido para mejorar UX de tienda; el sitio ya sirve assets públicos | Subir a Supabase Storage (más estable, más trabajo) |
| Ranking | `items_pedido` por `SUM(cantidad_solicitada)` | Fuente confiable; `pedidos.items` JSON a menudo vacío/wrapper | Parsear JSON de `pedidos.items` |
| Origen tienda | Setear `origen='tienda'` al **crear** carrito en login-tienda | Usuario eligió ver origen desde el primer carrito abierto | Solo al confirmar |
| UI origen | Badge en `pedidos-table` (+ filtro opcional) | La sección Pedidos es donde operan; ERP raw ya tiene origen distinto | Solo ERP / solo API |

## Alcance

### Incluido (v1)

1. **Ops datos Benfresh:** phone en `#11`, liberar `#13`, flag `catalog_store` en `distribuidoras.metadata`.
2. **Script** `scripts/benfresh/scrape_benfresh_images.py`: scrape benfreshfood.com, match top 100, dry-run CSV + `--apply` hotlink a `productos.image_url`.
3. **Backend:** `INSERT` de pedido abierto en `ensure_open_pedido_for_client` con `origen='tienda'`; exponer `p.origen` en `GET .../pedidos/v2`.
4. **Backoffice:** badge de origen en sección Pedidos; filtro origen (todos / tienda / suplai).

### Fuera de alcance

- Subir imágenes a Storage.
- Normalizar teléfonos en `login-tienda` (sigue match exacto).
- Cambiar copy de las variantes del segundo mensaje (spec 026).
- Tocar cliente `#50 BENFRESH,LLC`.
- Cambiar resolución seller/client en WhatsApp para Christian.
- Backfill de `origen` en pedidos históricos abiertos creados por tienda.

## Orden de implementación

| Orden | Repo | Rama sugerida | Dependencia |
|-------|------|---------------|-------------|
| 1 | `suplai-platform` | `feat/benfresh-tienda-prep` | Spec + script imágenes (dry-run) |
| 2 | Ops BD (MCP / SQL) | — (tras review) | Cliente `#11`/`#13` + flag metadata |
| 3 | `backend-supabase` | `feat/benfresh-tienda-origen` | Merge antes que backoffice si el filtro usa query param |
| 4 | `product-management-app` | `feat/benfresh-tienda-origen-ui` | Consume `origen` de pedidos v2 |
| 5 | Apply imágenes | `--apply` del script | Tras dry-run revisado |

Orden de merge habitual: **backend → backoffice**; ops + script pueden ir en paralelo.

## Migración de base de datos

**Sin migración de BD.**

- Columna `pedidos.origen` ya existe (migración histórica `45_add_erp_orders_raw_mirror.sql`).
- Cambios de datos: UPDATE de `clients` (#11, #13) y merge JSON en `distribuidoras.metadata` para `benfresh`.
- `productos.image_url`: UPDATEs puntuales vía script (no DDL).

**Rollback / riesgo**

- Cliente: revertir phones de `#11`/`#13`.
- Flag: quitar `catalog_store` o setear `false`.
- Imágenes: `image_url = NULL` en filas tocadas (guardar CSV del apply).
- Origen: carritos nuevos quedan `tienda`; no afecta históricos `suplai`.

## Plan de prueba en CI/CD

| Repo | Qué validar |
|------|-------------|
| backend | Test unitario/service: `ensure_open_pedido_for_client` inserta con `origen='tienda'` (mock DB o assert SQL params). Checks existentes verdes. |
| backoffice | Lint/typecheck; si hay test de tabla de pedidos, cubrir render de badge `tienda`. |
| platform | Script: dry-run sin red flaky en CI (opcional); al menos el script debe parsear args y fallar claro sin `DATABASE_URL`. |
| Gap | No hay E2E tienda+backoffice en pipeline; el OK de merge de UI/API se apoya en checklist humana abajo. |

## Plan de prueba humana (antes del PR / apply prod)

**Servicios**

- Backend: `8000`
- Backoffice: `3000` (`BACKEND_URL=http://localhost:8000`)
- Tienda: puerto distinto de 3000 (ej. `3002`)

**Tenant / datos**

- Schema `benfresh`
- Cliente `#11` con `wp=17864035046`, lista Default USD
- Christian sigue pudiendo usar WhatsApp como vendedor

**Checklist**

1. [ ] Abrir `https://tienda.suplaisales.com/benfresh?wp=17864035046` (o local) → login OK como BENFRESH MARKET LLC, precios Default.
2. [ ] Dixie ya no autentica con ese `wp`.
3. [ ] Tras login, pedido abierto nuevo tiene `origen='tienda'` en BD.
4. [ ] En backoffice → Pedidos: badge **Tienda** visible; filtro origen funciona.
5. [ ] Pedido creado por agente sigue badge **Suplai** / `origen=suplai`.
6. [ ] Con flag activo: PDV (sesión cliente, no seller) tras `create_order`/`edit_order` recibe segundo mensaje con URL de tienda.
7. [ ] Script dry-run: CSV con matches; revisar calidad; `--apply` deja imágenes en top productos; tienda muestra fotos.

## Criterios de aceptación

- **AC-1:** `#11` tiene `phone_number=17864035046` y lista `#24`; `#13` no tiene ese phone.
- **AC-2:** `metadata.catalog_store.append_link_after_order_tools === true` en Benfresh.
- **AC-3:** `get_catalog_link` sigue disponible (sin regresión).
- **AC-4:** Dry-run del script produce CSV; `--apply` solo actualiza filas sin `image_url` (o según flag documentado) con URLs absolutas a benfreshfood.com.
- **AC-5:** Nuevo carrito vía login-tienda persiste `origen='tienda'`.
- **AC-6:** Pedidos v2 + UI muestran origen; filtro opcional usable.

## Archivos clave (referencia)

- `backend/services/tienda_login.py` — INSERT pedido abierto
- `backend/routers/pedidos.py` — SELECT v2
- `backoffice/components/pedidos-table.tsx` — badge/filtro
- `agent/app/agent/tools/catalog_store_promotion.py` — ya implementado
- `scripts/benfresh/scrape_benfresh_images.py` — a crear
- Sitio: `https://www.benfreshfood.com` (`assets/images/product/*`)
