# Benfresh — Integración Odoo 19

Instancia: `https://benfresh-llc1.odoo.com` (Odoo 19 Enterprise SaaS, db `benfresh-llc1`).  
Tenant: `benfresh` (`public.distribuidoras.id` = `fce614e5-ff61-40d7-ab3a-95567c6dd2c5`).

## Estado (2026-09-24)

El conector está **vivo en producción**: job cada 6 h, push de pedidos ON, espejos actualizados hoy.

| Ítem | Estado |
|---|---|
| Conector | `odoo` → `https://benfresh-llc1.odoo.com`, sync `6h`, `push_orders_enabled=true` |
| Último pull productos/precios | 2026-09-24 00:02 UTC (`last_sync_at`) |
| Último pull pedidos/clientes | 2026-09-24 06:02 UTC |
| Productos espejo ↔ catálogo | **209 / 209** (0 solo-ERP) |
| Listas ERP vinculadas | **26 / 26** activas (quedan 2 listas mock inactivas: `List 1`, `Default`) |
| Clientes con `partner_odoo_id` | **517 / 532** |
| Cola onboarding | **220 resueltos, 0 pendientes** |
| Pedidos espejo | 1940 raw · **1824 proyectados** a `pedidos` |
| Push Suplai → Odoo | 92 pedidos origen `suplai`; 87 en estado `enviado_erp` |

Cierre operativo de hoy (script `scripts/cerrar_huecos_erp_odoo.py --apply`, informe `outputs/erp-odoo-huecos-2026-09-24.json`):

- 7 SKUs promovidos + vectorizados (packs 12×2 lb Benfresh + Capri/Italian blend + kale).
- Listas **La Real** (`erp_list_id=25` → lista 47) y **Luncheros** (`28` → 48) + 44 precios.
- 7 clientes nuevos dados de alta (5 con teléfono placeholder `999…`).
- 12 ítems de cola que ya existían en `clients` marcados `resuelto`.
- **605 pedidos ERP** proyectados a `pedidos` / `items_pedido`.

Clientes nuevos (alta 2026-09-24): Vybes Nutrition, POKE HOUSE US, TRANSFORM 180 FITNESS, CHOC-O-PAIN, Chicken pollo LLC, Anchor Bloom Cafe, LAS CHICAS BAKERY.

## Pendiente (no bloquea operación)

1. **Auto-proyección de pedidos Odoo** — PR backend [#248](https://github.com/Facu-hub-code/backend-suplai/pull/248). Hasta el merge/deploy, el job 6 h solo refresca el espejo; los canónicos se atrasan (hoy ya proyectamos el backlog).
2. **95 pedidos `sale` no proyectables** por suciedad de Odoo (no inventar SKUs):
   - 58 sin SKU en líneas
   - 68 con cantidad ≤ 0
   - 18 con SKUs que no son catálogo: `Delivery_007`, `89010007` (cargo de envío)
3. **20 draft + 1 cancel** en el espejo: se omiten a propósito.
4. Teléfonos sintéticos `999…` en los 5 clientes sin phone en Odoo — completar cuando operaciones tenga el número real.
5. Listas mock inactivas `List 1` / `Default` sin `erp_list_id` — no tocar.

## Cómo operar

Backoffice → Configuración → **Integraciones ERP**:

- Sync productos / precios / stock (job 6 h o botón).
- Sync + detectar clientes (cola; hoy vacía).
- Proyección de pedidos: `POST /benfresh/erp/orders-raw/project` o

```bash
set -a && source ../backend-supabase/.env && set +a
python scripts/benfresh/project_erp_orders.py --apply
```

Cerrar huecos de nuevo (si reaparecen SKUs/listas/cola):

```bash
python implementacion/benfresh/scripts/cerrar_huecos_erp_odoo.py --apply
```

## Notas de datos Odoo

- Productos sin `default_code` se descartan en el pull.
- Precios reales viven en pricelists (`product.pricelist.item`, fixed); `list_price` del producto suele ser 0.
- Partners B2B a menudo sin `phone`/`mobile` (Odoo 19 no expone `mobile`). Match por `partner_odoo_id` / últimos 10 dígitos.
- La promoción ERP → Suplai (productos, clientes, listas) es **humana** (wizard / cola / este script). El job solo refresca espejo y actualiza precios/stock ya vinculados.
