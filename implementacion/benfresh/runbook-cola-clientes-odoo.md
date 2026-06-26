# Backfill cola clientes Odoo — BenFresh

Ejecutar **después** de desplegar backend con migración 61 y con ERP configurado.

## 1. Aplicar migración (si no está en prod)

```bash
cd backend-supabase
python scripts/migrations/apply_migration_61.py
```

## 2. Sync + detectar (API)

Con backend local en `:8000` y ERP conectado:

```bash
curl -X POST "http://localhost:8000/benfresh/erp/customer-onboarding/queue/sync" \
  -H "Content-Type: application/json"

curl -X POST "http://localhost:8000/benfresh/erp/customer-onboarding/queue/detect" \
  -H "Content-Type: application/json"
```

También desde backoffice: **Configuración → Integraciones ERP → Clientes pendientes → Sync + detectar**.

## 3. Verificar CELIS encolados

```bash
curl "http://localhost:8000/benfresh/erp/customer-onboarding/queue?status=pendiente&limit=50" \
  -H "Content-Type: application/json" | jq '.items[] | select(.partner_name | test("CELIS"; "i"))'
```

Deben aparecer los 4 partners (odoo 545–548).

## 4. Aprobar altas

Desde backoffice, botón ✓ en cada fila, o:

```bash
QUEUE_ID=... # id de CELIS PRODUCE
curl -X POST "http://localhost:8000/benfresh/erp/customer-onboarding/queue/${QUEUE_ID}/approve" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Luego cargar alias comerciales (`celis`, `celis produce`, etc.) en `clientes_aliases`.

## 5. Smoke agente

Probar búsquedas: `celis produce`, `celis west palm beach` con vendedor de prueba.
