# Backoffice — Vendedores V2: métricas, rankings y layout supervisor

**Estado:** Aprobado (diseño)  
**Fecha:** 2026-06-22  
**Supersede parcialmente:** [006-vendedores-unificados-backoffice.md](./006-vendedores-unificados-backoffice.md)  
**Implementación backoffice:** `product-management-app/doc/specs/046-vendedores-metricas-rankings.md` (pendiente)  
**BFF backend:** extensión de `backend/docs/specs/052-bff-vendedores-dashboard.md` (pendiente)

---

## 1) Objetivo

Rediseñar la sección **Vendedores** del backoffice para que el supervisor vea de un vistazo el **rendimiento individual** de cada vendedor: tareas, objetivos comerciales y pedidos históricos. La operación (WhatsApp, plantillas, torneos) pasa a un menú **Herramientas**; la pantalla principal se dedica a métricas.

---

## 2) Terminología

| Antes | Nuevo |
|-------|-------|
| Torneo | **Ranking de tareas** |
| — | **Ranking de objetivos** (nuevo) |
| Plantillas de tareas | **Administrador de tareas** (solo lectura + explicación) |

---

## 3) Layout

```text
┌──────────────────────────────────────────────────────────────────┐
│ [Herramientas ▼]   Búsqueda vendedor              [+ Nuevo vendedor] │
├───────────────────────────────────────────────┬──────────────────┤
│  Tabs: [Tareas] [Objetivos] [Pedidos]         │  Rail derecho      │
│                                               │  (~25% ancho max)  │
│  Métricas del vendedor seleccionado           │  Fichas verticales │
│  + filtros de fecha                           │  · seleccionar     │
│                                               │  · abrir modal     │
└───────────────────────────────────────────────┴──────────────────┘
```

### 3.1 Eliminar de la vista principal

- Barra / card de estado WhatsApp del equipo
- Cards superiores de torneo activo y plantillas
- Resúmenes de tareas/torneo dentro del modal ficha (pasan al área central)

### 3.2 Dropdown Herramientas

Patrón existente: `product-table.tsx` / `contacts-table.tsx` (`DropdownMenu` + tooltips).

| Ítem | Modal | Crear |
|------|-------|-------|
| Ranking de tareas (ex torneos) | Fichas | Sí |
| Administrador de tareas | Fichas explicativas | **No** |
| Administrador de objetivos | Fichas | Sí |

---

## 4) Rail derecho — selector de vendedores

- Ocupa **≤ 25%** del ancho de pantalla.
- Lista vertical de **fichas compactas** (avatar, nombre, badge activo).
- **Click en ficha** → carga métricas en el panel central (vendedor activo).
- **Acción secundaria** (ícono expandir) → modal ficha vendedor (CRUD, zonas, clientes, WA).

Búsqueda filtra el rail sin perder la selección activa si sigue visible.

---

## 5) Pestañas centrales (vendedor seleccionado)

Estilo **pestañas de navegador** (tabs con indicador activo).

| Tab | Default filtro | Contenido |
|-----|----------------|-----------|
| **Seguimiento de tareas** | Hoy | Tareas del vendedor por PDV, estado, progreso SKU, puntos |
| **Seguimiento de objetivos** | Período del objetivo activo | Objetivos globales + avance del vendedor (unidades) |
| **Pedidos históricos** | Última semana | Pedidos cargados por el vendedor, líneas expandibles |

Cada tab expone selector **Desde / Hasta**; al cambiar vendedor se mantiene el tab activo y se recargan datos.

---

## 6) Modales

### 6.1 Ficha vendedor

- **Avatar:** `object-cover`, foto completa visible (fix crop).
- **Quitar** bloques de resumen de tareas/torneo/puntos (ya están en tabs centrales).
- Mantener: editar, zonas, clientes, WhatsApp, activar/desactivar.

### 6.2 Administrador de tareas (plantillas)

- Presentación en **fichas**, no tabla.
- **Sin botón crear** — las tareas se generan automáticamente por el motor Field.
- Cada ficha explica qué significa el tipo (`REACTIVAR_CLIENTE`, `MEJORAR_MIX_RENTABLE`, `CROSS_SELL_COMBO`).

### 6.3 Ranking de tareas (ex torneos)

- Fichas con nombre, fechas, participantes, estado.
- **Crear** y **cerrar** torneo permitidos.
- Renombrar labels UI: "Torneo" → "Ranking de tareas".

### 6.4 Administrador de objetivos

- Ver spec [010](./010-objetivos-comerciales-field.md).
- Fichas; crear por SKU individual o grupo de SKUs; meta en **unidades**.

---

## 7) BFF — performance

Extender el BFF existente (`GET /{schema}/bff/vendedores`) o agregar:

```http
GET /{schema}/bff/vendedores/dashboard?vendedor_id=5&tab=tareas&desde=2026-06-22&hasta=2026-06-22
```

**Response por tab** (precargado en una llamada; el front elige la sección):

| Tab | Datos agregados |
|-----|-----------------|
| tareas | `field_tasks` + progreso SKU + PDV nombre |
| objetivos | objetivos activos + unidades acumuladas del vendedor |
| pedidos | pedidos del vendedor + conteo ítems |

Proxy backoffice: `GET /api/bff/vendedores/dashboard`.

**Objetivo perf:** carga inicial panel central < 2s con 20 vendedores en rail (lista ligera) + 1 vendedor seleccionado (dashboard completo).

---

## 8) Componentes (backoffice)

| Componente | Acción |
|------------|--------|
| `VendedoresUnifiedSection` | Refactor → layout rail + tabs |
| `VendedorFichaDetailModal` | Fix avatar; quitar resúmenes |
| `FieldTournamentsView` | Fichas + rename ranking tareas |
| `FieldTemplatesTable` | Fichas; quitar crear |
| **Nuevo** `VendedorMetricsTabs` | Tabs tareas / objetivos / pedidos |
| **Nuevo** `VendedorRailList` | Rail derecho vertical |
| **Nuevo** `FieldObjetivosAdmin` | Modal admin objetivos |
| **Nuevo** `VendedoresToolsMenu` | Dropdown Herramientas |

---

## 9) Criterios de aceptación

- [ ] No hay fila superior WA / torneo / plantillas en la vista principal.
- [ ] Dropdown Herramientas abre los 3 administradores en modal.
- [ ] Rail derecho ≤ 25% ancho; selección de vendedor actualiza tabs centrales.
- [ ] Tab tareas default hoy; tab pedidos default última semana; tab objetivos con filtro fecha.
- [ ] Modal ficha: avatar corregido; sin resúmenes duplicados.
- [ ] Modal tareas: fichas, sin crear, con explicación por tipo.
- [ ] Modal ranking tareas: fichas, crear permitido.
- [ ] Labels "torneo" reemplazados por "ranking de tareas" en UI visible.
- [ ] Dashboard BFF en una llamada por tab + vendedor.
