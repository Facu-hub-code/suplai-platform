# Clasificación comercial de productos (tipo A / B)

**Estado:** Aprobado (diseño)  
**Fecha:** 2026-06-20  
**Índice:** [003-suplai-field-app.md](./003-suplai-field-app.md)  
**Implementación backend:** `backend/docs/specs/049-producto-tipo-venta.md` (pendiente)  
**Implementación backoffice:** extensión de `product-table.tsx` + detalle producto

---

## 1) Contexto

Las distribuidoras B2B operan con una lógica comercial interna sobre sus SKUs que no se refleja hoy en la plataforma. Dos categorías estratégicas (definidas por cada distribuidora con su propio significado):

| Tipo | Significado orientativo (no impuesto por el sistema) |
|------|------------------------------------------------------|
| **A** | Alta rotación / levantar pedido — mueve volumen |
| **B** | Alta rentabilidad / vender — genera margen al vendedor |

Este dato alimenta el motor de tareas Suplai Field V2 (reactivación, mix rentable, cross-sell). **No reemplaza** `rotacion_index` del catálogo ni tags jerárquicos.

---

## 2) Decisiones cerradas

| # | Tema | Decisión |
|---|------|----------|
| 1 | Asignación | **100% manual** por la distribuidora (experiencia interna) |
| 2 | Respaldo con `rotacion_index` | Opcional/informativo; **no obligatorio** ni auto-asignado |
| 3 | Códigos | `'A'` \| `'B'` \| `NULL` (sin clasificar) |
| 4 | Significado semántico | Lo define cada tenant; el sistema solo transporta el código |
| 5 | UX tabla productos | Badge **solo lectura** sobre el avatar |
| 6 | UX edición | Select en detalle/edición de producto |
| 7 | Asignación masiva UI | **Fuera de V1**; carga inicial vía Excel mapeado manualmente por implementación |
| 8 | Colores badge | **A** = azul (volumen) · **B** = verde (renta) |

---

## 3) Modelo de datos

### 3.1 Columna nueva en `{schema}.productos`

```sql
ALTER TABLE {schema}.productos
  ADD COLUMN IF NOT EXISTS tipo_venta TEXT
  CHECK (tipo_venta IS NULL OR tipo_venta IN ('A', 'B'));
```

- Nullable por defecto (productos existentes sin clasificar).
- Índice parcial recomendado: `(tipo_venta) WHERE tipo_venta IS NOT NULL` para queries del motor de tareas.

### 3.2 API

| Método | Campo | Notas |
|--------|-------|-------|
| `GET /{schema}/productos` | `tipo_venta` | Incluir en listado y detalle |
| `PATCH /{schema}/productos/{id}` | `tipo_venta: 'A' \| 'B' \| null` | Validación enum |

---

## 4) UX backoffice

### 4.1 Tabla de productos

Componente base: `TableEntityAvatar` en `product-table.tsx`.

```
┌─────────────┐
│  [img]  (A) │  ← badge superpuesto esquina inferior-derecha del avatar
│             │     A: bg-blue-500/90 text-white text-[9px]
└─────────────┘     B: bg-emerald-500/90
```

- Sin badge si `tipo_venta` es null.
- Tooltip opcional: "Tipo A — volumen" / "Tipo B — renta" (texto genérico; no imponer definición).

### 4.2 Detalle / edición

| Campo | Control | Valores |
|-------|---------|---------|
| Tipo comercial | Select | Sin clasificar · A · B |

---

## 5) Reglas de negocio downstream

| Consumidor | Uso |
|------------|-----|
| Tarea `REACTIVAR_CLIENTE` | Solo SKUs **tipo A** del historial del cliente |
| Tarea `MEJORAR_MIX_RENTABLE` | Solo SKUs **tipo B** del historial |
| Tarea `CROSS_SELL_RENTABLE` (futuro) | SKUs **tipo B** no comprados (sales-engine) |
| Agente / catálogo | Sin cambio en V1 |

Productos sin `tipo_venta` **se excluyen** de combos sugeridos en tareas.

---

## 6) Alcance V1 vs roadmap

| V1 | Post-V1 |
|----|---------|
| Columna + API + badge + select en detalle | Tipos C, D |
| Carga manual / Excel en onboarding | UI asignación masiva por tag/marca |
| | Sugerencias automáticas (no auto-asignación) basadas en rotación |

---

## 7) Criterios de aceptación

- [ ] Supervisor puede asignar A/B en detalle de producto y persiste en BD.
- [ ] Tabla muestra badge azul (A) o verde (B) sobre avatar; null = sin badge.
- [ ] Motor de tareas ignora SKUs sin clasificación al armar combos.
- [ ] `rotacion_index` existente no se modifica ni se recalcula por este cambio.
