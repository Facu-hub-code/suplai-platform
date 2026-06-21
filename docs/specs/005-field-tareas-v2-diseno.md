# Suplai Field — Motor de tareas V2 (diseño)

**Estado:** Aprobado (diseño)  
**Fecha:** 2026-06-20  
**Supersede parcialmente:** [002 §8](./002-suplai-field-app-diseno.md#8-motor-de-tareas-y-gamificación), [048](../../../backend-supabase/docs/specs/048-field-tasks-gamificacion.md)  
**Depende de:** [004-clasificacion-productos-comerciales.md](./004-clasificacion-productos-comerciales.md)  
**Implementación backend:** `backend/docs/specs/050-field-tasks-v2-motor.md` (pendiente)

---

## 1) Resumen

El motor V2 redefine **3 tipos de tarea** orientados a la clasificación comercial A/B, reemplaza umbrales fijos de reactivación por **frecuencia personalizada del cliente**, introduce **combos con delta configurable** y un modelo de **puntos por SKU + bonus de completitud**.

---

## 2) Configuración tenant (backoffice)

Parámetros globales en metadata de distribuidora o tabla de config Field (recomendado: `field_config` JSON en metadata):

| Clave | Default | Descripción |
|-------|---------|-------------|
| `field_combo_ventana_dias` | 120 | Ventana para contar apariciones de SKU en pedidos |
| `field_combo_delta_unidades` | 1 | Diferencia máxima en unidades vs el último SKU del top N para incluir empates |
| `field_combo_max_items` | 7 | Tope de SKUs por combo (reactivación default 3, mix rentable default 3) |
| `field_combo_top_n` | 3 | Cantidad base del ranking antes de aplicar delta |
| `field_puntos_por_sku_default` | 10 | Puntos por cada SKU cumplido en la tarea |
| `field_bonus_completitud_default` | 20 | Bonus extra al cumplir **todos** los SKUs del combo en **un solo pedido** |

Cada plantilla puede override estos defaults en `criterio_json`.

### 2.1 Algoritmo delta (ejemplo acordado)

Ventana = 120 días. Ranking por **apariciones** (presencia en `items_pedido`, no unidades ni monto):

| SKU | Apariciones |
|-----|-------------|
| SKU1 | 20 |
| SKU2 | 15 |
| SKU3 | 14 |
| SKU4 | 13 |
| SKU5 | 7 |

Con `top_n=3`, `delta_unidades=1`, `max_items=7`:

1. Tomar top 3: SKU1, SKU2, SKU3.
2. Incluir SKUs adicionales cuya aparición ≥ `apariciones[top_n] - delta` → SKU4 (13 ≥ 14−1).
3. SKU5 queda fuera (7 < 13).
4. Resultado combo: [SKU1, SKU2, SKU3, SKU4] (4 items, ≤ max 7).

**Nota:** `rotacion_index` del catálogo **no participa** en este cálculo.

---

## 3) Tipos de tarea

### 3.1 `REACTIVAR_CLIENTE` — Reactivación

**Disparador:** cliente inactivo según frecuencia personalizada.

```text
intervalos = diferencias en días entre pedidos confirmados/descargados (ordenados)
mediana_intervalo = mediana(intervalos)
inactivo si dias_sin_pedir >= 2 × mediana_intervalo
```

| Caso | Comportamiento |
|------|----------------|
| ≥ 2 pedidos históricos | Calcular mediana; generar tarea si cumple umbral |
| < 2 pedidos (poco historial) | **Generar tarea igual** con badge `frecuencia_estimada: baja_confianza` en BFF |
| Sin pedidos | No generar (o tratar como caso aparte en implementación) |

**Combo sugerido:** solo productos **tipo A** que el cliente **ya compró** en la ventana configurada, rankeados por apariciones, con algoritmo delta. Default `max_items=3`.

**Criterio de éxito:** pedido **creado ese día** (`fecha = hoy`) en estado evaluable (`confirmado` / según pipeline ERP) con match de SKUs sugeridos.

**Puntos:** por SKU matched + bonus si todos en un solo pedido.

---

### 3.2 `MEJORAR_MIX_RENTABLE` — Mix rentable

**Disparador:** cliente activo (no inactivo por regla de reactivación) con historial de compras tipo B.

**Combo sugerido:** top N productos **tipo B** del historial del PDV, rankeados por apariciones en unidades en ventana configurable, con delta y max_items.

**Criterio de éxito:** mismo que reactivación — match de SKUs sugeridos en pedido del día.

**Sales-engine:** **no se usa** en esta etapa.

---

### 3.3 `CROSS_SELL_RENTABLE` — Venta cruzada (standby)

**Estado:** plantilla reservada; **sin criterio de éxito definido** en V2.0.

**Dirección futura:** tareas creadas desde **sales-engine** cuando el módulo esté hidratado con datos ERP. Mock/stub hasta integración.

**Acción V2.0:** seed de plantilla inactiva + documentación; no generar instancias.

---

## 4) Modelo de puntos y cumplimiento

### 4.1 Principio

Cada tarea = venta de N SKUs a un PDV. Cada SKU tiene valor parcial; completar todos en **un solo pedido del día** otorga bonus.

```text
Ejemplo: 7 SKUs × 10 pts = 70 base + 20 bonus = 90 pts máximo
```

Configurable por plantilla:

```json
{
  "puntos_por_sku": 10,
  "bonus_completitud": 20,
  "combo_skus": ["SKU1", "SKU2", ...],
  "ventana_dias": 120,
  "delta_unidades": 1,
  "max_items": 7
}
```

### 4.2 Regla crítica: un pedido por evaluación diaria

> **Un segundo pedido del mismo día NO puede completar el resto de SKUs ni sumar bonus.**

Motivo: las tareas reflejan la venta en una visita/pedido; el sync ERP suele consolidar al cierre del día.

Implementación sugerida:

- Al evaluar el **primer pedido del día** que matchea parcialmente: registrar SKUs cumplidos en `criterio_json.progreso`.
- Marcar `evaluacion_cerrada: true` en la tarea tras esa evaluación.
- Pedidos posteriores del mismo día: ignorados para esa tarea.
- Estado final: `PARCIAL` (algunos SKUs) o `COMPLETADA` (todos + bonus).

### 4.3 Estados

| Estado | Descripción |
|--------|-------------|
| `PENDIENTE` | Sin pedido evaluado |
| `PARCIAL` | Primer pedido del día matcheó algunos SKUs; evaluación cerrada |
| `COMPLETADA` | Todos los SKUs + bonus en un solo pedido |
| `EXPIRADA` | Fin del día sin pedido evaluable |
| `CANCELADA` | Supervisor canceló |

### 4.4 Ledger

- Un registro en `field_point_ledger` al cerrar evaluación (parcial o completa).
- Puntos = `(skus_cumplidos × puntos_por_sku) + (bonus si completitud total)`.

### 4.5 UI vendedor

- Progreso en badge de tarea (ej. "3/7 SKUs") — **prioridad baja**; el vendedor ve el resultado tras sync ERP (a la noche).
- Field app: mostrar SKUs sugeridos y puntos posibles en ficha PDV.

---

## 5) Badge de confianza en frecuencia (BFF)

Exponer en respuestas de home/perfil/tareas:

```json
{
  "cliente_id": 123,
  "frecuencia_compra": {
    "mediana_dias": 7,
    "pedidos_analizados": 1,
    "confianza": "baja",
    "badge": "Historial limitado"
  }
}
```

| `confianza` | Condición |
|-------------|-----------|
| `alta` | ≥ 4 pedidos en historial |
| `media` | 2–3 pedidos |
| `baja` | 1 pedido o mediana no calculable |

---

## 6) Generación de tareas

Ver [007-field-app-v2-mejoras.md](./007-field-app-v2-mejoras.md) §6 — estrategia híbrida recomendada.

Resumen:

1. **CRON nocturno** (06:00 TZ tenant): pre-genera tareas para vendedores activos con ruta del día siguiente... *corrección:* genera para **hoy** al inicio del día comercial.
2. **Lazy on access**: `ensure_daily_tasks` idempotente en `GET /vendedor-app/home` para PDVs nuevos o plantillas recién activadas.
3. **No re-evaluar combos** intra-día salvo refresh explícito supervisor (futuro).

---

## 7) Plantillas y reglas visibles (backoffice)

Cada plantilla muestra bloque **"Reglas de negocio"** auto-generado (solo lectura) a partir de `criterio_json`:

> Se activa cuando el cliente lleva el doble de su frecuencia habitual sin pedir.  
> Combo: productos tipo A que ya compró, top 3 con delta de 1 unidad, máx. 3 ítems.  
> Puntos: 10 por SKU + 20 bonus por completar todos en un pedido.

Parámetros editables; texto legible derivado.

---

## 8) Migración desde V1

| V1 | V2 |
|----|-----|
| `CROSS_SELL_COMBO` + sales-engine | Deprecar generación; migrar plantilla a `MEJORAR_MIX_RENTABLE` o desactivar |
| Umbral 45 días fijo | Reemplazar por mediana × 2 |
| Completitud binaria | PARCIAL + puntos por SKU |
| `field_app_enabled` | Deprecar → solo `sales_assistant_enabled` |

---

## 9) Criterios de aceptación

- [ ] Reactivación usa mediana × 2; badge baja confianza si < 2 pedidos.
- [ ] Combos tipo A/B respetan ventana, delta, max_items configurables.
- [ ] Evaluación cierra en primer pedido del día; segundo no suma.
- [ ] Puntos por SKU + bonus configurables por plantilla.
- [ ] `CROSS_SELL_RENTABLE` existe como plantilla standby inactiva.
- [ ] BFF expone `frecuencia_compra.confianza` en perfil/tareas.
