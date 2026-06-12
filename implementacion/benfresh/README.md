# Benfresh — Integración Odoo 19

Instancia: `https://benfresh-llc1.odoo.com` (Odoo 19 Enterprise SaaS, db `benfresh-llc1`).

## Estado (2026-06-10)

| Ítem | Estado |
|---|---|
| Conector Odoo 19 (`execute_kw`) | Implementado en `backend/` rama `feat/odoo-connector-v19-benfresh`, validado E2E contra la instancia real |
| Endpoints export CSV | `GET /{schema}/erp/products-raw/export` y `GET /{schema}/erp/customers/export` (misma rama) |
| Botones descarga en backoffice | `backoffice/` rama `feat/erp-csv-export-odoo` |
| Productos crudos en staging | 198 SKUs en `benfresh.erp_products_raw` (cargados vía MCP con el conector nuevo; 2 `default_code` duplicados en Odoo colapsaron) |
| Listas de precios | 20 listas `ERP_*` en `benfresh.listas_precios` con 191 precios en `precios_productos` (60 SKUs) |
| CSV productos crudos | `erp_productos_crudos_benfresh.csv` (200 productos con código) |
| CSV clientes con match | `erp_clientes_benfresh.csv` (501 clientes: 292 existentes, 8 nuevos, 201 sin teléfono) |

El match de clientes se hace por **últimos 10 dígitos** del teléfono (los `clients` guardan prefijo país `1`/`549`, Odoo guarda el número local). No se insertó ningún cliente.

## Pendiente (post-deploy del backend)

Configurar el conector en el backend desplegado (necesita la rama mergeada/desplegada, porque el conector viejo falla contra Odoo 19 y las credenciales se cifran con la master key de Railway):

```bash
curl -X POST https://web-production-f544f.up.railway.app/benfresh/erp/connect \
  -H "Content-Type: application/json" \
  -d '{
    "connector": "odoo",
    "base_url": "https://benfresh-llc1.odoo.com",
    "credentials": {"db": "benfresh-llc1", "username": "IABENFRESH@gmail.com", "password": "***"},
    "sync_frequency": "6h"
  }'
```

Luego los botones del backoffice (cargar productos, sync, descargas CSV) operan solos.

## Notas de datos Odoo

- 236 productos totales; 34 sin `default_code` (se descartan), 2 códigos duplicados (`10003`, otro): corregir en Odoo.
- Los precios reales están en pricelists (`product.pricelist.item`, fixed); el `list_price` del producto suele ser 0.
- 4 SKUs con precio en Odoo no existen en `benfresh.productos` (no se les creó precio).
- Clientes: todos `is_company=true`, campo `mobile` no existe en Odoo 19.
