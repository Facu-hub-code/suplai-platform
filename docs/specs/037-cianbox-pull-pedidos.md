# SPEC: Cianbox — pull de pedidos

**Estado:** Borrador  
**Fecha:** 2026-08-27  
**Tenant piloto:** `cordoba_frost`  
**Repos:** `backend/` (conector + capability), `backoffice/` (UI existente de espejo de pedidos), `platform/` (este spec)

Reemplaza el enfoque de `036-cianbox-pull-productos-imagenes` (retirado). Productos e imágenes de Córdoba Frost se cargan por **Excel**, no por API.

---

## 1) Contexto

Córdoba Frost ya **inyecta** pedidos a Cianbox (`push_orders=true`, `POST /pedidos/alta`). El conector no lee el CRM: `fetch_orders()` devuelve `[]` y `erp_orders_raw` está vacío.

Cianbox documenta `GET /api/v2/pedidos` (paginado) con cabecera, cliente y `detalles[]`. El backoffice ya tiene «Sincronizar pedidos» (`POST /{schema}/erp/sync-orders`) para conectores con `pull_orders`.

## 2) Objetivo

Espejar pedidos de Cianbox en `{schema}.erp_orders_raw` para operar el historial del CRM en Integraciones ERP, sin duplicar en `{schema}.pedidos` los que ya inyectó Suplai.

## 3) Decisiones de diseño técnico (con el por qué)

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| Solo pull de pedidos; productos/imágenes por Excel | El GET `/productos` con el user actual devolvió `total_pages=0`. El dueño va a mandar catálogo en Excel. | Seguir con pull de productos/imágenes (spec 036) |
| Reusar `sync_orders_to_raw` + botón backoffice existente | Galileo/Odoo ya persisten en `erp_orders_raw`. No hay UI nueva. | Endpoint Cianbox-only |
| SKU de línea = `CBX-{id_producto}` si no hay código | El GET de pedidos trae `id_producto` + `detalle`, no `codigo_interno`. El Excel cubrirá el maestro. | Bloquear el pull hasta tener productos |
| `origen=suplai` si `referencia_externa` es el id Suplai | El push manda `referencia_externa=pedido_id`. Evita tratar esos pedidos como captura nueva al proyectar. | Reimportar todo como `externo` |
| Filtrar `since` en cliente (Cianbox no tiene `fecha_min`) | La API solo pagina por `page`/`limit`/`order`. | Pedir un endpoint nuevo a Cianbox |
| `pull_orders: true`; resto de pulls en `false` | El job 6h ya llama `sync_orders_to_raw` si la capability está on. | Encender `pull_customers` / `pull_products` |
| No proyectar automático Cianbox → `pedidos` | El auto-project del job es Galileo. Meter historial CRM en la tabla operativa duplicaría lo ya confirmado por WhatsApp. | `auto_project` para Cianbox en v1 |
| Saltar `anulado=true` | No ensuciar el espejo con cancelados. | Traer anulados como estado |

## 4) Alcance explícito

### Incluido (v1)

- `CianboxConnector.fetch_orders(since=)` paginado (`GET /pedidos`).
- Mapper a DTO `ErpOrder` + líneas `detalles[]`.
- Capability `pull_orders: true` en perfil Cianbox.
- Tests de mapper, paginación, filtro `since` y retry 401.
- Documentar contrato GET pedidos en `docs/external/cianbox_erp.md`.

### Fuera de alcance (v1)

- Pull de productos, precios, listas, clientes (Excel / otro spec).
- Sync de imágenes / Storage.
- Alta de SKUs en `{schema}.productos`.
- Proyección automática a `{schema}.pedidos`.
- Cambiar el push de pedidos.

## 5) Orden de implementación

1. **platform** rama `feat/cf-cianbox-pull-pedidos`: retirar spec 036; publicar este spec.
2. **backend** rama `feat/cianbox-pull-pedidos`: mapper + `fetch_orders` + SQL capability + tests.
3. Backoffice: sin PR. El paso Pedidos ERP ya llama `sync-orders`.
4. Merge: solo backend (+ spec platform).
5. Operación CF: aplicar SQL → Integraciones → Sincronizar pedidos → revisar espejo.

## 6) Migración de base de datos

- **Sí, liviana:** `UPDATE core.erp_connector_profiles SET capabilities = capabilities || '{"pull_orders": true}' WHERE connector = 'cianbox';`
- Sin tablas/columnas nuevas. `erp_orders_raw` ya existe.
- Rollback: `pull_orders` a `false`. El espejo no se borra.
- Seed: el primer `POST .../sync-orders` en `cordoba_frost` llena el espejo.

## 7) Contrato Cianbox (campos usados)

Fuente: [get_pedidos_lista.md](https://github.com/cianbox/api-docs/blob/master/get_pedidos_lista.md).

```
GET https://cianbox.org/{cuenta}/api/v2/pedidos
  ?access_token=…&page=1&limit=50
  &order=modified-date-desc
```

Campos: `id`, `fecha`, `numero`, `id_cliente`, `cliente`, `total`, `observaciones`, `estado`, `detalles`, `anulado`, `vigente`, `referencia_externa` (si el API la expone).

Línea: `id_producto`, `detalle`, `cantidad`, `neto_uni`.

## 8) Criterios de aceptación

- `POST /cordoba_frost/erp/sync-orders` persiste filas en `erp_orders_raw` cuando Cianbox lista pedidos.
- Un pedido inyectado desde Suplai queda con `origen=suplai` y `suplai_pedido_id` si `referencia_externa` matchea.
- Un pedido nacido en Cianbox queda `origen=externo`.
- Push de pedidos no cambia.
- Tests del conector Cianbox en verde en CI.

## 9) Plan de prueba en CI/CD

- `pytest tests/erp/connectors/test_cianbox_connector.py` (push existente + pull pedidos).
- Checks del PR backend en verde.
- Sin test de SQL; documentar aplicar `108_cianbox_pull_orders.sql` en prod.

## 10) Plan de prueba humana (antes del PR)

- Backend local `8000`. Backoffice **puerto 3000**.
- Tenant `cordoba_frost`.
- Integraciones ERP → Pedidos → Sincronizar (30 días).
- Observar: `synced > 0` **o**, si Cianbox lista 0 (mismo síntoma que productos), anotar `total_pages` del GET y no afirmar que el CRM está vacío sin mirar la UI de Cianbox.
- Confirmar que un pedido WhatsApp reciente sigue `enviado_erp` y no se duplicó en `pedidos`.
