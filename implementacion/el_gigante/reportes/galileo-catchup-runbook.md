# El Gigante — runbook catch-up Galileo + Field

Tenant: `el_gigante`. No commitear secretos.

1. `POST /el_gigante/erp/connect` con host `srv561.hstgr.io:3306` y `push_orders_enabled=true`.
2. `load-products` → `load-price-lists` → `load-prices` → `sync` → `customer-onboarding/queue/sync`.
3. `POST /el_gigante/erp/sync-orders?days=30` (incremental) o `force=true` local si hace falta el piso 2025-08-01.
4. `POST /el_gigante/erp/orders-raw/project` `{"dry_run": false}`.
5. `POST /el_gigante/erp/promote-products-bulk` (dry_run primero).
6. Retrain sales-engine `el_gigante`.
7. Aplicar `scripts/wipe_field_tasks.sql` y regenerar con `ensure_daily_tasks` / login Field.
8. Verificar ticket `[ERP_PEDIDOS_HUECO] |2026-08|` en Notificaciones (agosto vacío en Galileo).
