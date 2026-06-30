# Seed demo — Seguimiento tareas y objetivos (tenant `dimer`)

Datos mock para presentación de Suplai Field + backoffice supervisor, basado en `el_gigante`.

## Prerrequisitos

- Tenant `dimer` con `sales_assistant_enabled = true`
- Tablas `field_*` migradas
- MCP Supabase con escritura habilitada (o SQL Editor)

## Orden de ejecución

```bash
# En Supabase SQL Editor o vía MCP execute_sql, en orden:
seed_dimer_phase0_config.sql
seed_dimer_phase1_templates.sql
seed_dimer_phase2_productos_ab.sql
seed_dimer_phase3_pedidos.sql
seed_dimer_phase4_torneo_objetivos.sql
seed_dimer_phase5_reposicion_jueves.sql   # hábito semanal + ruta jueves
```

Post-seed (producción):

```bash
chmod +x scripts/field-demo-dimer/smoke_dimer_production.sh
# Requiere SALES_ENGINE_API_KEY (mismo valor que Railway backend/sales-engine)
./scripts/field-demo-dimer/smoke_dimer_production.sh
```

O manualmente:

```bash
curl -X POST "https://sales-engine-production-f6bd.up.railway.app/v1/tenants/dimer/models/retrain" \
  -H "Content-Type: application/json" -H "X-API-Key: $SALES_ENGINE_API_KEY" \
  -d '{"since_days": 365}'

curl "https://web-production-f544f.up.railway.app/dimer/vendedor-app/home" \
  -H "x-schema-name: dimer" -H "x-vendedor-telefono: 5493516123456"
```

Post-seed (local):

```bash
chmod +x scripts/field-demo-dimer/smoke_dimer.sh
BACKEND_URL=http://127.0.0.1:8000 SALES_ENGINE_URL=http://127.0.0.1:8001 \
  ./scripts/field-demo-dimer/smoke_dimer.sh
```

## Rollback

```sql
-- scripts/field-demo-dimer/seed_dimer_rollback.sql
```

## Demo URLs

| Rol | URL |
|-----|-----|
| Backoffice | `https://<backoffice-prod>/dimer` → Vendedores |
| **Field App (prod)** | **`https://field.suplaisales.com/dimer?wp=5493516123456`** |
| Field App (local) | `http://localhost:3001/dimer?wp=5493516123456` |

**Mejor día:** jueves (ruta Juan — ZONA OESTE).

## Vendedores demo

| Nombre | Teléfono | Ruta |
|--------|----------|------|
| Juan Pérez | 5493516123456 | lunes + jueves |
| María González | 5493516987654 | martes + viernes |
| Carlos Rodríguez | 5493516123457 | miércoles + sábado |

## Escenarios incluidos

- **REACTIVAR_CLIENTE:** 6 clientes inactivos 90+ días con historial tipo A
- **REPOSICION_HABITO:** Frío y Sabor — ciclo semanal SKU `12572647`
- **MEJORAR_MIX_RENTABLE:** 3 clientes activos sin compras tipo B
- **Torneo activo:** Torneo Invierno Dimer 2026 + ranking ledger
- **Objetivos:** ChamoniX (500 u) + Hamburguesas Sadia (200 u)
- **Pedido abierto:** Frío y Sabor pendiente con SKU reposición

## Marca de seed

Todos los registros demo usan `notas = 'SEED DEMO FIELD DIMER'` (pedidos) o `criterio_json.seed = 'demo_dimer'` (tareas).
