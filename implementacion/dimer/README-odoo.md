# Dimer — Integración Odoo 18

Instancia: `https://dimerltda.odoo.com` (Odoo 18 Enterprise SaaS).  
Tenant: `dimer` (`public.distribuidoras.id` = `02a0c4e0-8ac7-4bf1-aee9-19b44a14f66a`).  
Login API: usuario `admin` (no el mail). Sociedad operativa: **DIMER S.A.** (`company_id=1`, RUT `76807250-7`).

## Las 3 sociedades

La base **no** está aislada. En el mismo Odoo conviven:

| id | Sociedad | Qué hay |
|---|---|---|
| 1 | **DIMER S.A.** | 44 listas, ~123k pedidos, catálogo y clientes operativos |
| 2 | DIAZ Y MERINO LTDA | 1 lista `Predeterminado`, 6 pedidos |
| 3 | ASESORIAS E INVERSIONES DIMERI LIMITADA | 1 lista `Predeterminado`, 0 pedidos |

Clientes (`res.partner`) y casi todo el catálogo son **compartidos** (`company_id` vacío). El filtro real es por sociedad en listas y pedidos. Credenciales de `dimer` guardan `company_id=1` y `compute_formula_prices=true`. **Benfresh no tiene esos flags.**

## Estado (2026-09-30)

| Ítem | Estado |
|---|---|
| Conector | `odoo` → `dimerltda.odoo.com`, sync `6h`, push ON, `company_id=1`, fórmula ON |
| Productos | **547** en catálogo · stock > 0 en **460** |
| Precios | **6030** filas · 4788 nuevas por fórmula/categoría · Lista DIMER **235** SKUs |
| Clientes | **4970** · **4669** con `partner_odoo_id` |
| Cola onboarding | **4672 resueltos · 2691 pendientes** (solo se dieron de alta compradores de 30 días) |
| Pedidos espejo 30 días | **18850** raw · **18818** con cliente |
| Pedidos Suplai | **17046** · **86145** ítems |

## Qué se hizo (sin tocar benfresh)

1. **3A — Alta de compradores recientes.** Partners Odoo que aparecen en el espejo de pedidos (7 días, después 30). Teléfono real si existe; si no, placeholder `999…`. Duplicados de cola se vincularon al cliente sugerido. No se crearon los ~2.7k partners sin compra reciente.
2. **2B — 30 días de pedidos.** 18.841 sale.order de DIMER S.A. proyectados a `pedidos` cuando había cliente + SKU + estado usable.
3. **1B — Precios fórmula.** Solo si `compute_formula_prices=true` (dimer). Benfresh sigue el path default: solo ítems `fixed` + producto.

Benfresh sigue en `https://benfresh-llc1.odoo.com`. Su job 6h corrió el 2026-09-30 00:02 UTC.

## Limitaciones que quedan

1. **Reglas `base=pricelist`.** Si la lista apunta a otra lista, no se calcula en v1. Por eso Lista DIMER cubre 235 SKUs y no todo el catálogo.
2. **Cola residual.** ~2691 partners Odoo sin compra en 30 días siguen en Integraciones ERP.
3. **Huecos de proyección.** Cancelados, pendientes, SKU faltante o cantidad inválida no entran a `pedidos`.
4. **Teléfonos sintéticos.** La mayoría de altas nuevas usa `999` + partner_id. Hay ~10 partners de 30 días sin alta por teléfono ya usado.

## Cómo operar

Backoffice → Configuración → **Integraciones ERP**.

```bash
set -a && source ../backend-supabase/.env && set +a
python implementacion/dimer/scripts/integrar_odoo.py --apply --steps lists,clients,products,prices,stock
python implementacion/dimer/scripts/integrar_odoo.py --apply --steps recent_buyers,orders,recent_buyers,project --orders-days 30
```

Rama de producto (filtro sociedad + fórmula gated + no dump de 123k pedidos):  
`backend-supabase` · `feat/odoo-company-context`.
