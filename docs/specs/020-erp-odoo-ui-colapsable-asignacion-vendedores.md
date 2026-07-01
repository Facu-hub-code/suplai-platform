# ERP Odoo — UI colapsable y asignación de vendedores al aprobar cliente

**Estado:** Borrador  
**Fecha:** 2026-07-01  
**Índice cross-repo:** este documento (platform)  
**Complementa:** [015-odoo-clientes-nuevos-deteccion-cola-alta.md](./015-odoo-clientes-nuevos-deteccion-cola-alta.md)  
**Incidente de referencia:** BenFresh — CELIS DELRAY BEACH aprobado en cola pero invisible para el agente vendedor (sin fila en `vendedores_clientes`)

---

## 1) Contexto

### 1.1 Qué funciona hoy (post spec 015)

- Cola **Clientes pendientes (Odoo)** detecta partners sin fila en `clients`.
- **Aprobar** crea/actualiza el cliente en `{schema}.clients` y resuelve la cola.
- La **sync manual** (Sync + detectar) sigue siendo el gate: no se insertan todos los partners Odoo automáticamente.

### 1.2 Gap operativo descubierto (jul-2026)

Tras aprobar **CELIS DELRAY BEACH** (y otros ERP recientes), el cliente **existe** en `clients` pero el agente responde *"No encontré ese cliente"*.

**Causa:** el agente vendedor solo busca clientes en la **cartera** (`vendedores_clientes`). El approve de cola **no** crea asignaciones. Hay que hacer un segundo paso manual (API/backoffice vendedores) que nadie ejecutó.

| Paso | Hoy | Resultado |
|---|---|---|
| Aprobar en cola ERP | ✅ Crea `clients` | Cliente en BD |
| Asignar vendedores | ❌ Manual, separado | Agente no encuentra al cliente |

### 1.3 Gap de UX en backoffice

La sección **Integraciones ERP** (`erp-integrations-section.tsx`) apila varios bloques con tablas paginadas:

1. Productos crudos (`erp_products_raw`)
2. Clientes pendientes Odoo (`ErpCustomerOnboardingQueueSection`)
3. Pedidos espejo (`ErpOrdersRawSection`)

En pantallas normales ocupan demasiado scroll; hace falta **colapsar/expandir** cada bloque.

---

## 2) Objetivo

1. **UI:** secciones ERP con tablas **colapsables** (expandir/contraer) para reducir ruido visual.
2. **Flujo approve:** al dar de alta un cliente desde la cola Odoo, preguntar en un **modal** si se desea **asignar a todos los vendedores activos**, evitando el segundo paso manual.
3. **Principio rector:** mantener la **sync manual** (cola + approve humano). **No** auto-asignar ni auto-insertar masivamente desde sync/detect.

---

## 3) Alcance

### 3.1 In scope

| Capa | Entrega |
|---|---|
| **Backoffice** | Acordeón/colapsables en Integraciones ERP; modal de confirmación al aprobar cliente pendiente |
| **Backend** | Extender `POST /{schema}/erp/customer-onboarding/queue/{id}/approve` con flag de asignación masiva a vendedores activos |
| **Agente** | Sin cambios (sigue leyendo `vendedores_clientes`) |

### 3.2 Out of scope

- Alta automática de **todos** los partners Odoo (sin pasar por cola).
- Asignación automática en **Sync + detectar** (solo en **approve** explícito).
- Asignación selectiva por vendedor en el modal V1 (solo toggle todos / ninguno).
- Sync bidireccional Suplai → Odoo.
- Alias comerciales (`clientes_aliases`) — flujo aparte post-alta.

---

## 4) UI — Secciones colapsables

### 4.1 Ubicación

`backoffice` → Configuración agente → **Integraciones ERP** (`components/erp-integrations-section.tsx` y subcomponentes).

### 4.2 Bloques colapsables (V1)

Cada bloque con **tabla paginada** pasa a patrón **Collapsible** (shadcn `Collapsible` o equivalente):

| Bloque | Componente actual | Default expandido |
|---|---|---|
| Productos crudos | Card + tabla en `erp-integrations-section` | **Contraído** |
| Clientes pendientes (Odoo) | `ErpCustomerOnboardingQueueSection` | **Expandido** si `pending_review > 0`, si no contraído |
| Pedidos espejo ERP | `ErpOrdersRawSection` | **Contraído** |

### 4.3 Comportamiento

- **Header clickeable** con chevron (`ChevronDown` / `ChevronRight`) + título + badge contador (ej. pendientes Odoo, total productos).
- Al **contraer**: ocultar `CardContent` (tabla, filtros, paginación); mantener visible el header y acciones críticas del header si ya existen (ej. botón Sync + detectar en clientes pendientes).
- **Persistencia opcional V1.1:** `localStorage` key `erp-section-{schema}-{sectionId}-open` — no obligatorio en V1.
- Accesibilidad: `aria-expanded`, foco en header, tecla Enter/Espacio togglear.

### 4.4 Wireframe (referencia)

```
┌─ Integraciones ERP ─────────────────────────────────────┐
│ [config conector — sin cambio]                          │
├─ ▼ Productos crudos (198) ──────────────────────────────┤
│   [tabla oculta si contraído]                           │
├─ ▼ Clientes pendientes (Odoo) [44] ── Sync + detectar ──┤
│   [tabla visible]                                       │
├─ ▶ Pedidos espejo ERP (142) ──────────────────────────┤
└─────────────────────────────────────────────────────────┘
```

---

## 5) UI — Modal al aprobar cliente

### 5.1 Trigger

En `ErpCustomerOnboardingQueueSection`, botón **Aprobar** (✓) ya no llama al API directo: abre **Dialog**.

### 5.2 Contenido del modal

**Título:** `Dar de alta cliente`  
**Subtítulo:** nombre del partner Odoo + `odoo #ID`.

**Pregunta principal (checkbox o switch, default ON):**

> **¿Asignar a todos los vendedores activos?**

Texto de ayuda (debajo):

> Si lo activás, el cliente quedará en la cartera de todos los vendedores y el agente podrá encontrarlo. Si no, tendrás que asignarlo manualmente desde Vendedores.

**Botones:**

| Botón | Acción |
|---|---|
| **Cancelar** | Cierra modal, no approve |
| **Confirmar alta** | `POST .../approve` con body según §6 |

Campos avanzados V1: **ninguno** (teléfono/lista precios siguen como hoy — inferidos del staging ERP).

### 5.3 Feedback post-approve

Toast de éxito ampliado:

> `CELIS DELRAY BEACH` dado de alta → client_id **323**. Asignado a **8** vendedores.

Si el toggle estaba OFF:

> … Alta OK. **Sin asignación** — recordá asignar vendedores manualmente.

---

## 6) API — Backend

### 6.1 Extender approve

**Ruta existente:** `POST /{schema}/erp/customer-onboarding/queue/{queue_id}/approve`

**Body** (`ERPCustomerOnboardingApproveRequest`):

| Campo | Tipo | Default | Descripción |
|---|---|---|---|
| `phone_number` | string \| null | null | Sin cambio |
| `lista_precios_id` | int \| null | null | Sin cambio |
| `activo_ai` | bool \| null | null | Sin cambio |
| **`assign_to_all_sellers`** | **bool** | **false** | Si `true`, asignar cliente a todos los vendedores activos |

### 6.2 Lógica de asignación (servicio)

Tras crear/actualizar `clients` y marcar cola `resuelto`:

```text
SI assign_to_all_sellers = true:
  vendedores ← SELECT id FROM {schema}.vendedores WHERE COALESCE(activo, true)
  PARA CADA vendedor_id:
    UPSERT vendedores_clientes (vendedor_id, cliente_id, activo=true)
    UPDATE clients SET vendedor = vendedor.nombre WHERE id = client_id
    (reutilizar lógica de POST /{schema}/vendedores/{id}/clientes:asignar)
```

**Respuesta ampliada:**

```json
{
  "client_id": 323,
  "orders_backfilled": 12,
  "sellers_assigned": 8,
  "assign_to_all_sellers": true
}
```

Si `assign_to_all_sellers=false` → `sellers_assigned: 0`.

### 6.3 Reglas de negocio

| Regla | Detalle |
|---|---|
| Solo vendedores **activos** | `COALESCE(activo, true) = true` |
| Idempotente | Re-approve o approve con cliente existente no duplica filas (`ON CONFLICT` / `NOT EXISTS`) |
| Sync manual intacta | `POST .../queue/sync` y `.../detect` **no** asignan vendedores |
| Link manual | `POST .../queue/{id}/link` — fuera V1; opcional mismo flag en V1.1 |

### 6.4 Tests backend

- Approve con `assign_to_all_sellers=true` → N filas en `vendedores_clientes` (N = vendedores activos mock).
- Approve con `false` → 0 asignaciones.
- Agente path: cliente aprobado + asignado → aparece en query de cartera del vendedor (test integración opcional).

---

## 7) Repos y specs hijas

| Repo | Archivo propuesto | Contenido |
|---|---|---|
| `product-management-app` | `doc/specs/051-erp-ui-colapsable-approve-modal.md` | Detalle UI Collapsible + Dialog |
| `backend-supabase` | `docs/specs/058-erp-approve-assign-all-sellers.md` | Servicio, modelo, tests |
| `suplai-platform` | este documento | Índice cross-repo |

---

## 8) Criterios de aceptación (BenFresh)

1. Sección **Pedidos espejo** y **Productos crudos** contraídas por default; usuario puede expandir.
2. **Clientes pendientes** expandida si hay badge > 0.
3. Aprobar **CELIS DELRAY BEACH** con toggle ON → agente Facundo/Christian encuentra por *"celis delray beach"* sin paso manual extra.
4. Aprobar con toggle OFF → cliente en `clients` pero agente **no** lo ve hasta asignación manual.
5. **Sync + detectar** sigue solo encolando; no crea asignaciones masivas.

---

## 9) Plan de implementación

| Fase | Entrega |
|---|---|
| **A — Backend** | Flag `assign_to_all_sellers` + tests |
| **B — Backoffice** | Modal approve + respuesta en toast |
| **C — Backoffice** | Collapsible en 3 bloques ERP |
| **D — BenFresh prod** | Re-asignar retroactivo clientes ERP ya aprobados (script one-shot o approve link) + smoke agente CELIS |

---

## 10) Riesgos

| Riesgo | Mitigación |
|---|---|
| Demasiados clientes en cartera de cada vendedor | Solo en approve manual; toggle default ON pero editable |
| Vendedor ve clientes que no le corresponden territorialmente | V2: asignación por zona/geo; V1 aceptado para BenFresh (8 vendedores) |
| Toggle ON olvidado en tenants grandes | Texto de ayuda claro; default ON solo BenFresh o global según decisión en implementación |

---

## 11) Referencias

- [015-odoo-clientes-nuevos-deteccion-cola-alta.md](./015-odoo-clientes-nuevos-deteccion-cola-alta.md)
- [implementacion/benfresh/runbook-cola-clientes-odoo.md](../../implementacion/benfresh/runbook-cola-clientes-odoo.md)
- Agente: `resolve_client_for_seller` filtra por `vendedores_clientes`
- Backoffice: `components/erp-integrations-section.tsx`, `erp-customer-onboarding-queue-section.tsx`
