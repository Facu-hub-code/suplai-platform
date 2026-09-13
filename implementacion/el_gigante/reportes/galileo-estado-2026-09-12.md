# Galileo — estado El Gigante (2026-09-12 / catch-up 2026-09-13)

Schema: `el_gigante`. Clave MySQL espejo **solo** en `public.tenant_secrets` (`erp.credentials`). No commitear secretos.

## Diagnóstico (12-sep)

- Job ERP 6h cortado el **4-sep**. Canónico origen `erp` cortado el **28-jul**.
- Galileo vivo: pedidos `updated_at` hasta **11-sep** (~150/día hábil). Productos/precios 8-sep.
- Mapeo `SUPLAI_*` OK vs `backend-supabase/docs/external/galileo_el_gigante_erp.md`.
- Staging: `erp_customers_raw.erp_partner_id` NULL; join que funciona: `clients.codigo`.
- Agosto-2026 = **0** pedidos en Galileo (no rellenar). Septiembre live ~863 `origen=preventa`.
- Push `SUPPLAI-36759` pendiente desde 20-ago; no bloquea Field.

## Catch-up (13-sep)

| Paso | Resultado |
|---|---|
| `POST /el_gigante/erp/connect` | 200, `push_orders_enabled=true` |
| Pull catálogo / precios / clientes | 250 productos, 5 listas, 2225 precios, 2485 clientes |
| `sync-orders?days=30` | 862 raw septiembre |
| Promoción SKUs | 99 + 93 altas |
| Proyección `dry_run=false` | `MAX(fecha)` origen erp **2026-09-11**; **793** pedidos sep; 69 raw sep sin proyectar |
| Retrain sales-engine | `rows_used=123051` |
| Wipe Field + regen | ledger/events/tasks a 0; 76 `REPOSICION_HABITO` fecha **2026-09-14** (hoy domingo no hay ruta); 68/76 con pedido sep |
| Ticket hueco | `ia_tickets` #51 `[ERP_PEDIDOS_HUECO] \|2026-08\|` open |

SKUs aún ausentes en catálogo (probable inactivos en Galileo): `10198`, `10199`, `10200`.
