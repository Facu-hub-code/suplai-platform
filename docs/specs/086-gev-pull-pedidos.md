# SPEC: 086 — GEV pull de pedidos → métricas (Almaro + Gonzales)

**Estado:** Implementación  
**Fecha:** 2026-09-30  
**Tenants:** `almaro`, `gonzales`  
**Repos:** `backend-supabase` (conector + proyección + capability) · `suplai-platform` (este spec)

n8n **no** entra. El pull y las métricas van por el conector GEV del backend y `{schema}.pedidos`.

---

## 1) Objetivo

Traer historial de pedidos de GEV (`GET /pedidos/getPedidos/`) a `erp_orders_raw`, proyectarlos a `pedidos` `confirmado` / `origen=erp`, y que Métricas de Almaro y Gonzales los cuenten. Si el pedido no tiene cliente en `clients`, crear un stub `activo_ai=false` solo para no romper la proyección.

## 2) Decisiones de diseño técnico (con el por qué)

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| Implementar `fetch_orders` en `GEVConnector`, no n8n | El job 6h y `POST /{schema}/erp/sync-orders` ya orquestan pull + espejo. n8n solo tiene push/stock/precios legacy | Workflow n8n de pull |
| Ventanas de 1–3 días + paginación | `fecha_desde` es obligatorio; un rango largo hace timeout en el gateway Xionico | Un GET de 12 meses |
| Primer backfill = últimos 12 meses (`fecha_min`); job = 30 días | Métricas de frecuencia necesitan historia; el job no puede barrer un año cada 6 h | Solo 30 días para siempre |
| `ESTADO=000000000` + `AUTORIZADO=S` → `confirmado` | La proyección solo acepta estados de `CONFIRMED_ERP_STATES`; el código crudo GEV no está en esa lista | Persistir `000000000` y ampliar el set global |
| Precio de línea = `PRECIO_UNITARIO_LISTA × 1.21` | Así se guardan los precios GEV en Suplai | Neto sin IVA: ticket medio queda corto vs catálogo |
| Combo: SKUs de `detalle_combo`, no el código combo | El catálogo tiene el artículo; el combo no siempre existe como SKU | Dejar el padre combo y fallar `missing_product` |
| Auto-project GEV (como Odoo/Galileo) | Sin esto el espejo se llena y Métricas sigue vacía | Botón manual `/orders-raw/project` cada vez |
| Stub solo si no hay match por `codigo` / `partner_*` | 22 Almaro + 92 Gonzales ya matchean por `codigo`. No duplicar ni apagar los vivos | Alta masiva de 2464 / 909 del espejo |
| `activo_ai=false` + teléfono `gev-{id}` | El agente no les escribe. `phone_number` es obligatorio y GEV casi no trae WhatsApp | Teléfono numérico inventado |
| Sin match por nombre | Gonzales tiene ~87 nombres parecidos con otro `codigo`; un fuzzy crearía duplicados o pisaría el vivo | `pg_trgm` |
| Capability `create_stub_customers_on_project` solo en perfil `gev` | Odoo/Galileo ya tienen cola de alta; no queremos stubs silenciosos ahí | Stub genérico para todos los conectores |
| Push sigue OFF | Este spec es pull → métricas, no inyección | Encender `push_orders` |

## 3) Alcance explícito

### Incluido (v1)

- `GEVConnector.fetch_orders(since=, fecha_min=)` paginado y por chunks de fecha.
- Mapper a `ErpOrder` (cabecera, detalle, combo, estado, `ID_CUENTA` numérico).
- `pull_orders: true` + `create_stub_customers_on_project: true` en perfil `gev`.
- `gev` en `AUTO_PROJECT_CONNECTORS`.
- Alta stub `activo_ai=false` si el pedido no matchea cliente. Backfill de `partner_erp_id` en el match existente si está null.
- Tests unitarios de mapper, estados, ventanas, stub vs match.
- Spec platform.

### Fuera de alcance

- n8n / `test-api-gev`.
- Encender push a GEV.
- Alta masiva de toda la cartera del espejo.
- Cola de onboarding, teléfonos reales, mapa / `puntos_venta`.
- Parser Excel spec 085.
- UI nueva.

## 4) Orden de implementación

| Repo | Rama | PR | Orden |
|---|---|---|---|
| `suplai-platform` | `feat/gev-pull-pedidos` | spec 086 | Puede mergear en paralelo |
| `backend-supabase` | `feat/gev-pull-pedidos` | conector + SQL + proyección + tests | **Merge primero** para que el job 6h lo use |

Backoffice: sin PR. Métricas ya lee `confirmado` / `descargado` con `origen=erp`.

## 5) Migración de base de datos

Sí, liviana — solo JSON de capabilities. Sin tablas ni columnas nuevas.

```sql
UPDATE core.erp_connector_profiles
SET capabilities = COALESCE(capabilities, '{}'::jsonb) || '{
  "pull_orders": true,
  "create_stub_customers_on_project": true
}'::jsonb
WHERE connector = 'gev';
```

El perfil es compartido: Almaro y Gonzales entran juntos. Push no se toca.

Rollback: `pull_orders` y `create_stub_customers_on_project` a `false`. El espejo y los stubs no se borran.

Sin seed de pedidos. El primer `sync-orders` (o el job) llena el espejo.

## 6) Plan de prueba en CI/CD

- `pytest tests/erp/connectors/test_gev_connector.py` — mapper, ventanas, estado, combo, `ID_CUENTA` con ceros.
- `pytest tests/test_erp_order_auto_projection.py` — `gev` auto-proyecta; Cianbox no.
- `pytest tests/test_erp_order_projection_service.py` — stub vs match existente; no apaga `activo_ai`.
- Checks del PR backend en verde.
- El SQL se aplica en prod / migrate job; no hay test de SQL.

## 7) Plan de prueba humana (antes / post deploy)

Servicios: backend `8000` (pooler `6543`, `statement_cache_size=0`). Backoffice **puerto 3000** si se miran Métricas.

1. Aplicar `sql/135_gev_pull_orders.sql` (o deploy que lo corra).
2. `POST /almaro/erp/sync-orders` y `POST /gonzales/erp/sync-orders` (o esperar el job 6h).
3. Observar: `erp_orders_raw > 0` en ambos; `orders_last_sync_at` poblado en Almaro.
4. Pedidos nuevos `confirmado` / `origen=erp`. Stubs con `activo_ai=false` y `phone_number` `gev-*`.
5. Los 22 piloto Almaro y los ~92 Gonzales con `codigo` = cuenta GEV **no** se duplican ni se apagan.
6. Métricas de ambos tenants: facturación / frecuencia / ticket incluyen esos confirmados.

Notas operativas: un 404 con `cabecera: []` es ventana vacía. Gonzales a veces responde 530 (Cloudflare) en ventanas recientes; reintentar o usar un rango histórico. El primer `sync-orders` con raw vacío hace backfill de 12 meses en chunks de 3 días (varios minutos).

## 8) Contrato GEV (campos usados)

```
GET {base_url}/pedidos/getPedidos/
  ?fecha_desde=YYYYMMDDHHMM&fecha_hasta=YYYYMMDDHHMM&page=1&limit=1000
```

Almaro acepta `YYYYMMDD`. Gonzales exige `YYYYMMDDHHMM`. El conector manda siempre 12 dígitos (`0000` / `2359`). Un 404 con `cabecera: []` es ventana vacía, no error.

Cabecera: `ID_PEDIDO`, `ID_CUENTA`, `RAZON_SOCIAL`, `MON_TOT_PED_C_DTO_IMP`, `FECHA_INICIO_PEDIDO`, `NOTAS_VENDEDOR`, `ESTADO`, `AUTORIZADO`, `ANULADO`, `ID_VENDEDOR`.

Detalle: `CODIGO_ARTICULO`, `DESCRIPCION_ARTICULO`, `CANTIDAD_PEDIDA`, `PRECIO_UNITARIO_LISTA`, `CODIGO_COMBO`.

Combo: `CODIGO_ARTICULO` real + `CODIGO_COMBO` + `CANTIDAD_PEDIDA`.

Doc: `backend-supabase/docs/external/gev_erp.md` §2.2.
