# 040 — Copilot: export CSV / PDF de tablas

**Estado:** Borrador (decisión de producto cerrada 2026-09-08)  
**Fecha:** 2026-09-08  
**Repos:** `suplai-platform` (este doc), `product-management-app`  
**Ramas sugeridas:** `feat/copilot-agentes-especialistas` (misma feature Copilot activa)  
**Índice:** [001-suplai-copilot.md](./001-suplai-copilot.md)  
**No confundir** con el PDF de **informe Copilot** (`POST /{schema}/copilot/reports/pdf` + Brevo). Este 040 exporta **la tabla ya renderizada** en el chat.

---

## Objetivo

Que un operador baje una tabla del Copilot como **CSV** (Excel) o **PDF** sin copiar celdas a mano. Los botones viven en el encabezado de **cada** artefacto `table`.

---

## Criterios de aceptación

- Cada tabla muestra botones **CSV** y **PDF** a la derecha del título.
- CSV abre una descarga `.csv` UTF-8 con BOM (Excel en macOS/Windows abre tildes bien).
- PDF abre una descarga `.pdf` con título, fecha, columnas visibles y filas de esa tabla.
- Se exportan las **columnas visibles** (`columns[].label` + `rows[key]`). Los ids ocultos (`cliente_id`, etc.) **no** salen.
- Celdas `null` / ausentes se exportan como `—` (en PDF, como `-`).
- Números se formatean igual que en pantalla (enteros sin decimales; no enteros con locale del tenant).
- Tablas persistidas viejas (sin cambios de contrato) también se pueden exportar: el payload ya trae `columns` + `rows`.
- El pipeline de informes Copilot / Brevo **no** cambia.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Dónde corre el export | **100% cliente**, desde el artefacto ya pintado | La tabla ya está recortada (top 15/20/30). No hay round-trip ni auth extra | Endpoint backend nuevo; reusar `reports/pdf` |
| CSV | Blob `text/csv` + BOM UTF-8, RFC 4180 | Patrón ya usado en Pedidos/ERP; Excel necesita BOM | `xlsx` (deps de más para un CSV plano) |
| PDF | `jspdf` ya en el backoffice (mismo patrón que catálogo) | Cero deps nuevas; descarga de archivo, no diálogo de imprimir | `window.print()`; `jspdf-autotable`; pipeline Brevo |
| Qué columnas | Solo las **visibles** (`artifact.columns`) | El operador ve eso; ids ocultos no aportan en Excel | Dump de todas las keys de la fila |
| Nombre de archivo | `{slug-titulo}_{YYYY-MM-DD}.csv\|pdf` | Trazable al pegarlo en un mail | Nombre fijo `tabla.csv` |
| Orientación PDF | Landscape si hay más de 5 columnas | Tablas anchas de Copilot (top clientes, funnel) no entran en A4 vertical | Siempre portrait; o HTML print |
| Links de entidad | El export es **texto plano** (el valor de la celda) | CSV/PDF no son el chat; el click sigue en la UI | Meter URLs del backoffice en cada celda |

---

## Alcance explícito

### Incluido (v1)

- Botones CSV y PDF en el header de cada `DataTable` de Copilot.
- Helpers puros en `lib/copilot/table-export.ts`.
- PDF: título, “Suplai Copilot · fecha”, header de columnas, filas, pie de página.

### Fuera de alcance (v1)

- Export de gráficos, mapas, KPI rows, informes Brevo.
- Elegir columnas / “exportar todo el resultado de la tool” sin el recorte del artefacto.
- Excel `.xlsx`, Google Sheets, o mandar el archivo por mail desde el chat.
- Incluir ids ocultos o hipervínculos a fichas.

---

## Orden de implementación

1. Spec (este doc) + enlace en [001](./001-suplai-copilot.md).
2. Front `product-management-app` en `feat/copilot-agentes-especialistas` (helpers + header).
3. Sin backend, sin migración. Merge con el PR Copilot activo o el que lo contenga.

---

## Migración de base de datos

Sin migración de BD. El contrato del artefacto `table` no cambia.

---

## Plan de prueba en CI/CD

- No hay suite unitaria en el backoffice (gap previo).
- Checks del PR de `product-management-app` (lint/build) deben quedar verdes en lo **nuevo**.
- `tsc --noEmit` tiene errores preexistentes (`Response.json`); no mezclarlos con este cambio.
- Mínimo aceptable para el PR: revisar el helper de CSV a mano (BOM + quoting) y smoke humano abajo.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000` + backoffice `3000`. Tenant de prueba: `del_corro` (Campi).

1. Abrir Copilot → Carlos (reportes).
2. Pedir una tabla, p. ej. “top clientes del mes” o “¿qué agendas hay activas?”.
3. En el encabezado de la tabla, **CSV**: se descarga `{titulo}_{fecha}.csv`. Abrir en Excel/Numbers: tildes, comas en números, `—` en vacíos. No aparecen columnas de id ocultas.
4. **PDF**: se descarga `.pdf`. Título de la tabla, fecha, mismas columnas/filas. Si hay muchas columnas, sale apaisado.
5. Tabla persistida (chat viejo con tabla): los botones también funcionan.
6. CSV/PDF de informes Copilot (otro flujo, si existe en el chat) **no** se altera.
