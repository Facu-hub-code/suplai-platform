---
name: suplai-implementation-phase-06-1
description: >
  Fase 6.1 Field App Setup — pedidos históricos densos para ML, re-entrenamiento,
  templates, objetivos, torneo y seed de tareas históricas. Usar después de Fase 6.
---

# Fase 6.1 — Suplai Field App Setup

> [!IMPORTANT]
> **MANDATORIO**: Leer `skill-guide.md` antes de ejecutar cualquier paso.
> Esta fase modifica `public.distribuidoras.metadata` y crea datos en tablas `field_*`.

## Input

- Fase 6 cargada (`pedidos` + `items_pedido` en BD).
- Catálogo con `rotacion_index` (Fase 1 OK).
- Red comercial cargada: `vendedores`, `vendedores_clientes`, `geo_zones` (Fase 4 OK).
- `marca_lider` en `manifest.yaml` del tenant.
- `SALES_ENGINE_URL` y `SALES_ENGINE_API_KEY` en `.env`.

## Output

| Archivo CSV | Descripción |
|---|---|
| `phase-06-1-pedidos-field.csv` | Pedidos históricos backbone (Jun 2025 – Feb 2026) |
| `phase-06-1-items-pedido-field.csv` | Ítems correspondientes |
| `phase-06-1-objetivos.csv` | 2 objetivos comerciales creados |
| `phase-06-1-torneo.csv` | Torneo mensual activo |

## Pasos (en orden)

### Paso A — Pedidos históricos enriquecidos

```bash
python scripts/fase-06-1-field/preparar_pedidos_field.py --esquema <schema>
# Revisar CSVs en implementacion/<schema>/outputs/
python scripts/fase-06-1-field/cargar_pedidos_field.py --esquema <schema>
```

Genera ~7 pedidos por cliente en Jun 2025 – Feb 2026 + 3 pedidos en Abr–May 2026.
Los mismos SKUs se repiten con intervalos regulares → ML detecta frecuencia.
20% de clientes quedan inactivos → REACTIVAR_CLIENTE dispara para ellos.

### Paso B — Habilitar Field App en el tenant

```bash
python scripts/fase-06-1-field/habilitar_field.py --esquema <schema>
```

Actualiza `public.distribuidoras.metadata → {"field_app_enabled": true}`.

### Paso C — Re-entrenar el modelo ML

```bash
python scripts/fase-06-1-field/retrain_ml.py --esquema <schema>
```

Llama `POST {SALES_ENGINE_URL}/v1/tenants/{schema}/models/retrain`.
Si el servicio está caído, continúa y avisa al implementador al final del paso.

### Paso D — Configurar templates de tareas

```bash
python scripts/fase-06-1-field/setup_templates.py --esquema <schema>
```

Activa: `REACTIVAR_CLIENTE`, `CROSS_SELL_COMBO`, `REPOSICION_HABITO`.
Desactiva: `MEJORAR_MIX_RENTABLE`, `CROSS_SELL_RENTABLE` (sin tipo_venta en productos).

### Paso E — Crear objetivos comerciales

```bash
python scripts/fase-06-1-field/setup_objetivos.py --esquema <schema>
```

Objetivo 1: SKU top por rotacion_index, meta 100 u, 30 días.
Objetivo 2: Grupo marca líder, meta 500 u, hoy-15 → hoy+45 días.

### Paso F — Crear torneo mensual

```bash
python scripts/fase-06-1-field/setup_torneo.py --esquema <schema>
```

Crea `field_tournaments` ACTIVO para el mes corriente con todos los vendedores mock.

### Paso G — Sembrar historial de tareas (últimos 30 días)

```bash
python scripts/fase-06-1-field/seed_tareas_historicas.py --esquema <schema>
```

Inserta `field_tasks` + `field_point_ledger` + `field_task_events` para los últimos
30 días laborables. Distribución: 60% COMPLETADA, 25% PARCIAL, 15% PENDIENTE.

### Paso H — Generar tareas de hoy (vía asyncpg + ML API directa)

```bash
python scripts/fase-06-1-field/trigger_tareas.py --esquema <schema> --dias 6
```

Genera tareas para hoy + próximos 5 días directamente en la BD (sin depender de que el
backend tenga el endpoint `trigger-daily-tasks` desplegado). Por cada vendedor cuya zona
tiene `dia_visita` igual al día objetivo:
- `REACTIVAR_CLIENTE` → clientes con último pedido > 60 días
- `CROSS_SELL_COMBO` → si ML /predict-combo devuelve sugerencias
- `REPOSICION_HABITO` → si ML /predict-replenishment devuelve ítems vencidos en ≤3 días

## Verificación post-carga

```sql
-- Tareas generadas hoy
SELECT vendedor_id, tipo, estado, COUNT(*)
FROM {schema}.field_tasks
WHERE fecha = CURRENT_DATE
GROUP BY vendedor_id, tipo, estado;

-- Progreso de objetivos
SELECT o.nombre, SUM(ip.cantidad_solicitada) AS unidades_logradas, o.meta_unidades
FROM {schema}.field_objetivos o
JOIN {schema}.field_objetivo_skus s ON s.objetivo_id = o.id
JOIN {schema}.items_pedido ip ON ip.product_code = s.product_code
JOIN {schema}.pedidos p ON p.id = ip.pedido_id AND p.estado IN ('confirmado','descargado')
WHERE o.activo = true
GROUP BY o.id, o.nombre, o.meta_unidades;

-- Puntos por vendedor (torneo activo)
SELECT v.nombre, SUM(pl.puntos) AS pts_totales
FROM {schema}.field_point_ledger pl
JOIN {schema}.vendedores v ON v.id = pl.vendedor_id
GROUP BY v.nombre
ORDER BY pts_totales DESC;
```

## Cierre

Manifest fase `06.1` → `cargado`. Proceder a Fase 7 (conversaciones).
