# Fase 6.1 Field App Setup — Guía del implementador

## ¿Qué hace esta fase?

Completa la base de datos de Suplai Field con datos suficientes para que:
1. El modelo ML conozca los patrones de compra de cada PdV.
2. El job diario de tareas genere tareas REPOSICION_HABITO y REACTIVAR_CLIENTE
   con sugerencias reales (no vacías).
3. El dashboard del vendedor muestre historial de puntaje de los últimos 30 días.

## Pre-condiciones obligatorias

| Condición | Cómo verificar |
|---|---|
| Fase 6 cargada (pedidos F6) | `SELECT COUNT(*) FROM {schema}.pedidos WHERE is_mock=true` > 0 |
| Red comercial Fase 4 OK | `SELECT COUNT(*) FROM {schema}.vendedores_clientes WHERE activo=true` > 0 |
| `marca_lider` en manifest | `cat implementacion/{schema}/manifest.yaml \| grep marca_lider` |
| Tables field_* presentes | `SELECT * FROM information_schema.tables WHERE table_schema='{schema}' AND table_name LIKE 'field_%'` |
| `SALES_ENGINE_URL` en .env | `grep SALES_ENGINE_URL .env` |

## Variables del .env necesarias

```
SUPABASE_DB_URL=postgresql://...  # Necesario para todos los scripts
SALES_ENGINE_URL=https://sales-engine-production-xxx.up.railway.app  # Paso C
SALES_ENGINE_API_KEY=...           # Paso C
BACKEND_URL=https://web-production-f544f.up.railway.app  # Paso H (opcional si usa prod)
```

## Orden de ejecución

```
A → cargar_pedidos_field  (depende de preparar_pedidos_field)
B → habilitar_field
C → retrain_ml             (sin bloqueo si está caído)
D → setup_templates
E → setup_objetivos
F → setup_torneo
G → seed_tareas_historicas
H → trigger_tareas
```

## Cómo ejecutar los scripts

Desde la raíz del workspace `suplai-platform/`:

```bash
cd c:\Users\totot\OneDrive\Escritorio\Suplai_Sales\suplai-platform

# Paso A — Preparar y cargar pedidos field
python scripts/fase-06-1-field/preparar_pedidos_field.py --esquema demo
python scripts/fase-06-1-field/cargar_pedidos_field.py --esquema demo

# Paso B — Habilitar Field App
python scripts/fase-06-1-field/habilitar_field.py --esquema demo

# Paso C — Re-entrenar ML (silencioso si está caído)
python scripts/fase-06-1-field/retrain_ml.py --esquema demo

# Paso D — Templates de tareas
python scripts/fase-06-1-field/setup_templates.py --esquema demo

# Paso E — Objetivos comerciales
python scripts/fase-06-1-field/setup_objetivos.py --esquema demo

# Paso F — Torneo mensual
python scripts/fase-06-1-field/setup_torneo.py --esquema demo

# Paso G — Tareas históricas (últimos 30 días laborables)
python scripts/fase-06-1-field/seed_tareas_historicas.py --esquema demo

# Paso H — Tareas de hoy + próximos 5 días (lunes-sábado)
python scripts/fase-06-1-field/trigger_tareas.py --esquema demo --dias 6
```

## Posibles errores y fixes

| Error | Causa probable | Fix |
|---|---|---|
| `SUPABASE_DB_URL no configurada` | .env no cargado | Ejecutar desde la raíz del workspace |
| `No hay vendedores activos` | Fase 4 no cargada | Ejecutar F4 primero |
| `field_task_templates no encontrada` | Migraciones SQL faltantes | Aplicar SQL 55-56 desde Supabase SQL Editor |
| `rows_used=0` tras retrain | Pedidos fuera del rango de entrenamiento | Verificar DEFAULT_TRAIN_SINCE_DAYS en sales-engine config |
| `FIELD_NOT_MIGRATED` en trigger | Tablas field_* no presentes | Aplicar migraciones SQL |
| ML service down (Paso C) | Sales-engine caído en Railway | Continuar, avisar al implementador; re-intentar luego |

## ¿Qué pasa si el ML está caído?

Los pasos A–B–D–E–F–G–H son independientes del ML y corren igual.
El paso C se salta silenciosamente con un aviso en consola.
Las tareas del Paso H de tipo `CROSS_SELL_COMBO` y `REPOSICION_HABITO` no se generarán
hasta que el modelo esté entrenado. El resto (`REACTIVAR_CLIENTE`) sí se genera.

Para re-entrenar después:
```bash
python scripts/fase-06-1-field/retrain_ml.py --esquema demo
python scripts/fase-06-1-field/trigger_tareas.py --esquema demo --dias 1
```

## Purga (Fase 10)

Los pedidos creados en esta fase tienen `is_mock=true` y
`sync_metadata->>'source'` IN `('fase-06-1-field-backbone', 'fase-06-1-field-recent')`.
El script de purga los elimina en cascada junto con sus `items_pedido`.

Las tareas en `field_tasks` con `is_mock=true` (a definir) o creadas vía seed
también son eliminables mediante:
```sql
DELETE FROM {schema}.field_tasks WHERE fecha < CURRENT_DATE - 90;
```

## Checklist de cierre de fase

- [ ] `preparar_pedidos_field.py` completado sin errores
- [ ] `cargar_pedidos_field.py`: pedidos en BD > 0
- [ ] `habilitar_field.py`: `field_app_enabled=true` verificado
- [ ] `retrain_ml.py`: `rows_used > 0` O aviso de servicio caído documentado
- [ ] `setup_templates.py`: 3 templates activos
- [ ] `setup_objetivos.py`: 2 objetivos activos
- [ ] `setup_torneo.py`: 1 torneo ACTIVO
- [ ] `seed_tareas_historicas.py`: tareas > 0 en BD
- [ ] `trigger_tareas.py`: tareas de hoy generadas OK
- [ ] Manifest fase 06.1 → `estado: cargado`
