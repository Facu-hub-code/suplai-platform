# SPEC: Cianbox — pull de productos e imágenes

**Estado:** Borrador  
**Fecha:** 2026-08-26  
**Tenant piloto:** `cordoba_frost`  
**Repos:** `backend/` (conector + servicios), `backoffice/` (botón de imágenes), `platform/` (este spec + plan)

---

## 1) Contexto

Córdoba Frost ya **inyecta pedidos** a Cianbox (`push_orders_enabled=true`). El conector es push-only: `fetch_products()` devuelve `[]`, `erp_products_raw` está vacío y el `product_id_map` se mantiene a mano en `erp.credentials`.

Eso duele en dos lados:

1. Los combos nuevos (helados `COM-HEL-*`) pueden entrar al ERP con `id=0` + texto si no están en el mapa.
2. El catálogo WhatsApp/tienda no toma fotos de Cianbox; hoy las imágenes se cargan por Excel/Serper.

Cianbox sí expone catálogo: `GET /api/v2/productos` (paginado) con `codigo_interno`, `id`, `imagenes[]` y `detalle_imagenes[]`.

## 2) Objetivo

Traer el catálogo Cianbox a **staging** (`erp_products_raw`), **reconstruir el mapa SKU → id Cianbox** para el push, y **copiar la primera imagen** a Storage + `productos.image_url` cuando el SKU ya existe en Suplai.

No convertir a Cianbox en fuente automática del catálogo WhatsApp.

## 3) Decisiones de diseño técnico (con el por qué)

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| Pull a `erp_products_raw`, no insert masivo en `productos` | Córdoba Frost vende por WhatsApp **solo 6 combos**. Un promote masivo rompería el system prompt y el RAG. La regla de producto ERP ya dice: ningún job crea productos. | `promote-products-bulk` sobre todo Cianbox |
| SKU = `codigo_interno`; si vacío, `CBX-{id}` | El push busca `product_id_map[product_code]`. Los combos ya usan códigos tipo `COM-COR-*` / `COM-HEL-*`. Si Cianbox no tiene interno, no inventamos un `COM-*`. | Usar el `id` numérico como `product_code` (rompe match con catálogo actual) |
| Merge de `product_id_map` (no replace) | Conserva mapeos manuales (helados, `ENVIO-DOM`) si Cianbox usa otro código interno | Reescribir el JSON entero |
| Imágenes: 1ª URL de `imagenes[]` → bucket `products-{schema}` → `productos.image_url` | Mismo contrato que Fase 1 (`cargar_imagenes_excel.py`). Cianbox URLs pueden expirar o no ser públicas estables para WhatsApp/tienda. | Hotlink directo a `cianbox.org/.../uploads` |
| Sync de imágenes **manual** (endpoint propio), no en el job 6h | Un catálogo grande + download HTTP + Storage timeout-ea el job de sync de precios. El espejo de productos sí puede ir en el job 6h. | Descargar todas las fotos en cada `load_products_to_raw` |
| No pisar `image_url` si ya hay una URL no-placeholder, salvo `force=true` | Evita borrar fotos de combos ya curadas (PDFs de campaña helados). | Sobrescribir siempre |
| `pull_products: true` en el perfil Cianbox | El job 6h ya llama `load_products_to_raw` si la capability está on. El botón backoffice **Cargar productos** llama el mismo servicio. | Script one-off solo para CF |
| `en_catalogo` no se toca en este spec | Quien promueva SKUs a `productos` lo hace a mano o con promote-bulk consciente. WhatsApp sigue filtrando por `en_catalogo`. | Auto `en_catalogo=true` al promote |

## 4) Alcance explícito

### Incluido (v1)

- `CianboxConnector.fetch_products()` paginado (`GET /productos?page=&limit=`).
- Persistencia en `{schema}.erp_products_raw` (flujo existente `load_products_to_raw`).
- `extra` en `raw_payload`: `cianbox_id`, `codigo_interno`, `vigente`, `imagenes`, `categoria`, `marca`.
- Merge de `product_id_map` en `public.tenant_secrets` (`erp.credentials`) tras un load exitoso.
- Endpoint `POST /{schema}/erp/sync-product-images` (dry-run default o flag `force`).
- Botón en Integraciones ERP del backoffice.
- Tests del mapper, paginación, merge del mapa e imágenes (HTTP/Storage mockeados).
- Probe read-only contra Cianbox de Córdoba Frost **antes** de asumir que los combos tienen `codigo_interno` igual al SKU Suplai.

### Fuera de alcance (v1)

- Pull de precios / listas / clientes / pedidos históricos (otro spec; capabilities siguen en `false` salvo `pull_products`).
- Alta masiva a `productos` (`promote-products-bulk` existe; **no usarlo en CF** sin filtro).
- Vectorizar ni reescribir descripciones de productos ya existentes.
- Cambiar el flujo de push de pedidos.

## 5) Orden de implementación

1. **Probe** Cianbox (script read-only) → confirmar paginación, `codigo_interno` de los 6 combos, presencia de `imagenes`.
2. **backend** rama `feat/cianbox-pull-productos-imagenes`: mapper + `fetch_products` + merge mapa + sync imágenes + tests + SQL capability.
3. **backoffice** rama `feat/cianbox-sync-product-images`: botón + proxy API.
4. Merge: backend primero, backoffice después.
5. Operación CF: Cargar productos → revisar mapa → Sincronizar imágenes → verificar 2–3 SKUs en Cianbox y en backoffice.

## 6) Migración de base de datos

- **Sí, liviana:** `UPDATE core.erp_connector_profiles SET capabilities = capabilities \|\| '{"pull_products": true}' WHERE connector = 'cianbox';`
- Sin columnas nuevas. `erp_products_raw.raw_payload` ya es JSONB; `productos.image_url` ya existe.
- Rollback: volver `pull_products` a `false`. El espejo y las fotos copiadas no se borran (no son destructivos).
- Seed/backfill: el primer `POST .../load-products` en `cordoba_frost` llena el espejo.

## 7) Contrato Cianbox (campos usados)

Fuente: [get_productos_lista.md](https://github.com/cianbox/api-docs/blob/master/get_productos_lista.md).

```
GET https://cianbox.org/{cuenta}/api/v2/productos
  ?access_token=...
  &page={n}
  &limit=50
  &fields=id,producto,codigo_interno,codigo_barras,stock_total,vigente,descripcion,imagenes,categoria,marca
```

Respuesta: `status=ok`, `page`, `total_pages`, `body[]`.

Mapeo a `Product`:

| Cianbox | Product / extra |
|---|---|
| `codigo_interno` o `CBX-{id}` | `sku` |
| `producto` | `nombre` |
| `stock_total` | `cantidad` |
| `id` | `extra.cianbox_id` |
| `imagenes[0]` | `extra.image_src` |
| `vigente` | `extra.vigente` |

Productos con `vigente=false` se persisten igual (el espejo es fiel); el sync de imágenes los salta salvo `include_inactive=true`.

## 8) Plan de prueba en CI/CD

- `pytest -q tests/erp/connectors/test_cianbox_connector.py` (fetch paginado, SKU fallback, 401+refresh).
- `pytest -q tests/erp/services/test_cianbox_product_id_map.py` (merge no pisa claves ajenas).
- `pytest -q tests/erp/services/test_erp_product_image_sync.py` (dry-run, skip si image_url llena, upload mock).
- Checks backend existentes verdes. Sin migración de schema tenant.

## 9) Plan de prueba humana (antes del PR / en CF)

Servicios: backend `8000`, backoffice `3000`, tenant `cordoba_frost`.

1. Probe: contar páginas y buscar `COM-COR-01826`, `COM-HEL-INICIAL` (o el código interno real).
2. Backoffice → Integraciones ERP → **Cargar productos**. Esperar `loaded > 0` y filas en la tabla cruda.
3. Confirmar en logs (sin imprimir secretos) que `product_id_map` creció; un pedido de prueba de un combo mapeado sigue inyectando con id numérico (no `id=0`).
4. **Sincronizar imágenes** (sin force): SKUs sin foto reciben URL `.../storage/v1/object/public/products-cordoba_frost/{sku}.jpg`.
5. Abrir un producto combo en catálogo backoffice: se ve la foto. Combos que ya tenían imagen de campaña **no** cambian.
6. WhatsApp: `en_catalogo` de los 6 combos no cambia; el agente no lista el catálogo completo de Cianbox.

## 10) Criterios de aceptación

- **Given** Cianbox con N productos vigentes **When** operador pulsa Cargar productos **Then** `erp_products_raw` tiene N filas (sku único) y `loaded=N`.
- **Given** un SKU `COM-HEL-INICIAL` con `codigo_interno` igual **When** termina el load **Then** `product_id_map["COM-HEL-INICIAL"]` es el `id` entero de Cianbox.
- **Given** producto Suplai sin `image_url` y Cianbox con `imagenes[0]` **When** sync imágenes **Then** `image_url` apunta al bucket público del tenant.
- **Given** producto con `image_url` ya seteada **When** sync sin `force` **Then** no se pisa.
- **Given** job 6h **When** `pull_products=true` **Then** refresca espejo; **no** crea filas en `productos`.
