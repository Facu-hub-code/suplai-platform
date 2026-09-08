# 039 — Copilot: links de entidad en tablas

**Estado:** Borrador (decisión de producto cerrada 2026-09-08)  
**Fecha:** 2026-09-08  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas sugeridas:** `feat/copilot-table-entity-links` (o la feature Copilot activa si se entrega en el mismo PR)  
**Índice:** [001-suplai-copilot.md](./001-suplai-copilot.md)  
**No confundir** con [backoffice 039](../../product-management-app/doc/specs/039-suplai-copilot-ui-artefactos.md) (panel y canvas de artefactos). Este 039 es de **platform** y cubre deep-links en celdas.

---

## Objetivo

Que un operador, desde una tabla del Copilot, abra la ficha de **cliente, producto, agenda, pedido o grupo** sin copiar IDs ni cambiar de pantalla a ciegas. El click vive en el **ID y en el nombre** cuando la fila ya conoce el identificador. El backend anota qué celda apunta a qué entidad; la UI no adivina por el título de columna.

---

## Criterios de aceptación

- Celdas anotadas (ID y nombre) se ven como links/botones; el resto de la tabla no cambia.
- Click abre un **popup/sheet de preview** de esa entidad, sin salir del chat.
- Si el id de la fila es `null` / ausente / `"—"`, la celda es texto plano.
- Tablas viejas (sin `link` en columnas) siguen renderizando igual: **compatibilidad hacia atrás**.
- La UI **no** infiere entidad por `label === "ID"` ni por el nombre de la `key`.
- Fuera de las cinco entidades v1, ningún click (etiquetas, plantillas Meta, zonas, métricas, NL→SQL).

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Quién decide el link | El backend anota al armar el artefacto (`columns[].link`) | El mismo `id` es agenda, grupo, etiqueta o zona según la tool. Adivinar en el front es un bug seguro | Inferir por label `"ID"` o por heurística de keys |
| Qué es clickeable | **ID y nombre** de la entidad, si la fila trae el id (`idKey`) | Pedido explícito (opción B + nombres). El nombre es lo que el operador lee | Solo IDs; o toda la fila clickeable |
| Dónde vive el id | Campo de la **misma fila** (`idKey`), visible o no | `sales_top_clients` ya trae `cliente_id` sin mostrarlo; no hace falta una columna extra | `row._links` paralelo (duplica contrato); URL absoluta en la celda |
| Identificador de producto | `product_code` (string), no el PK numérico | El catálogo y `ProductDetailSheet` resuelven por código (`GET /productos/{code}`) | Inventar un `product_id` que las tools de ventas no exponen |
| Popup vs navegar | Preview **dentro de Copilot**; CTA secundario “Ver en …” si hay sección nativa | El chat no debe desmontarse. `PedidosTable` solo expande si estás en Pedidos | `setActiveSection` + `focusPedidoId` como único camino |
| Reuso de modales nativos | Reusar solo los que abren **por id** (`GrupoDetailModal`). Cliente/producto/agenda/pedido: preview Copilot (fetch + ficha liviana) | `ClientDetailSheet` y `ProductDetailSheet` piden el objeto entero y un árbol de callbacks del padre (tabla). Montarlos desde Copilot arrastra ProductTable / ContactsTable | Embeder esas tablas enteras; o `ClientProfileModal` atado al mapa comercial |
| Filas sin id hoy | **Incluir el id en la fila** en esta entrega (aunque no se muestre) | Lucía: `funnel_clients` muestra `client_name` sin `client_id` en varios stages. Sin id no hay nombre clickeable | Dejar esas tablas sin link “porque hoy no traen id” |
| NL→SQL y tablas genéricas | Fuera de v1 | Keys arbitrarias; anotar sería adivinar de nuevo | Heurística `*_id` / `cliente_id` en SQL libre |

---

## Contrato (artefacto `table`)

Hoy (`lib/copilot/types.ts` / `build_artifacts_from_tool_result`):

```ts
{ type: "table"; title?: string; columns: { key: string; label: string }[]; rows: Record<string, unknown>[] }
```

v1 agrega `link` **opcional** por columna:

```ts
type CopilotEntity = "client" | "product" | "agenda" | "order" | "group"

type TableColumn = {
  key: string
  label: string
  link?: { entity: CopilotEntity; idKey: string }
}
```

Reglas:

1. `idKey` apunta a un campo de la **misma fila**. Puede coincidir con `key` (columna ID) o ser otro (`cliente_nombre` → `cliente_id`).
2. El front pinta link solo si `column.link` existe **y** `row[idKey]` es un id usable (número > 0, o string no vacío para `product`).
3. Varias columnas de la misma fila pueden linkear entidades distintas (pedido + cliente en “Mayores pedidos”).
4. Campos de id que no son columna visible **siguen en `rows`** (el modelo y el debug los ven; la tabla no está obligada a mostrarlos).
5. Zod en backoffice: `link` opcional. Mensajes persistidos sin `link` no rompen.

Ejemplo — top clientes (el id ya está en la fila, no hace falta columna nueva):

```json
{
  "type": "table",
  "title": "Top clientes",
  "columns": [
    { "key": "cliente_nombre", "label": "Cliente", "link": { "entity": "client", "idKey": "cliente_id" } },
    { "key": "cliente_codigo", "label": "Código" },
    { "key": "monto_total", "label": "Monto" }
  ],
  "rows": [{ "cliente_id": 12, "cliente_nombre": "Kiosco Sur", "cliente_codigo": "104", "monto_total": 150000 }]
}
```

---

## Alcance explícito

### Incluido (v1)

Entidades: **client**, **product**, **agenda**, **order**, **group**.

| Tool | Columnas clickeables | `idKey` | Notas de implementación |
|------|----------------------|---------|-------------------------|
| `sales_top_clients` | `cliente_nombre` | `cliente_id` | Ya viene en el item; no se muestra como columna |
| `sales_largest_order` | `pedido_id`; `cliente_nombre` | `pedido_id`; `cliente_id` | Ambos ya están en el item |
| `sales_top_products` | `nombre`; `product_code` | `product_code` | El código **es** el id de producto |
| `get_productos` | `nombre`; `product_code` | `product_code` | Nina |
| `agenda_list` | `id`; `grupo_nombre`; `client_id` | `id` (agenda); `grupo_id`; `client_id` | `grupo_id` ya viene en el SELECT. **SHOULD** agregar `cliente_nombre` (JOIN) para no mostrar solo el número; el nombre linkea al cliente |
| `funnel_clients` | `client_name`; `client_id` si se muestra | `client_id` | Hoy varios stages **no traen** `client_id` — hay que agregarlo en SQL (`get_clientes_inactivos`, respondieron, carritos, confirmados). Stages carritos/confirmados **MAY** anotar `pedido_id` si se incluye en la fila |
| `grupo_create` (preview confirmado) | no aplica a la tabla de zonas | — | La tabla de **zonas** no es v1 |

UI:

- `DataTable` en `CopilotArtifacts`: celdas con `link` = `<button>` estilo link (underline / color accent), teclado Enter/Espacio.
- Host `CopilotEntityPreview` (Dialog/Sheet) según `entity` + id.
- Fetch por BFF existente (`/api/clientes/:id`, `/api/productos/:code`, `/api/pedidos/:id`, grupos, agenda).
- Errores: toast + mensaje en el preview (“No se encontró…”). No navegar a otra sección en silencio.
- CTA opcional: “Ver en Clientes / Catálogo / Pedidos / Agenda / Grupos” que sí cambia de sección **después** de haber abierto el preview.

### Fuera de alcance (v1)

- Etiquetas (`etiquetas_list.id`), plantillas Meta, zonas geográficas (`grupo_create` modo geo), filas KPI/métricas/funnel overview/ERP sync.
- `nl_sql_query` (keys arbitrarias).
- Adivinar entidad en el cliente.
- Montar `ProductTable` / `ContactsTable` / mapa comercial dentro del Copilot.
- Escritura desde el preview (editar cliente, confirmar pedido). El preview es **lectura**.
- Deep-link desde markdown del LLM (`[cliente 12](...)`) — solo celdas de tabla anotadas.
- Historial persistido: no backfill de artefactos viejos; los chats nuevos sí anotan.

---

## Preview por entidad (front)

| Entidad | Abrir con | Contenido mínimo | Reuso |
|---------|-----------|------------------|--------|
| `group` | `grupoId` | Nombre, días, miembros | **`GrupoDetailModal`** (ya abre por id) |
| `client` | id numérico | Nombre, código, WhatsApp, lista, activo AI | Fetch → ficha liviana. No montar `ClientDetailSheet` completo en v1 (deps de PDVs, zonas, vendedores) |
| `product` | `product_code` | Nombre, código, imagen, stock, en catálogo | Fetch `GET /api/productos/{code}` → ficha liviana. `ProductDetailSheet` queda para una iteración si se extrae un modo read-only |
| `order` | `pedido_id` | Cliente, fecha, total, estado, ítems | Dialog Copilot. CTA “Ver en Pedidos” puede setear `focusPedidoId` |
| `agenda` | `agenda.id` | Tipo, día/hora, grupo, cliente, plantilla, activa | Dialog Copilot. No abrir `AgendaManagerModal` entero (es el gestor, no una ficha) |

Si el fetch 404: preview con estado vacío, no crash.

---

## Orden de implementación

Cross-repo. Merge **backend primero** (artefactos nuevos); el front ignora `link` desconocido hasta el PR de UI, y el backend viejo sigue enviando columnas sin `link`.

| Paso | Repo | Qué |
|------|------|-----|
| 1 | `backend-supabase` | Extender `build_artifacts_from_tool_result`: `link` en columnas de la tabla de tools v1. Incluir ids faltantes en filas (`funnel_clients`, `cliente_nombre` en `agenda_list`) |
| 2 | `backend-supabase` | Tests de snapshot/contrato: cada tool v1 emite `link` + `idKey` correcto; funnel items tienen `client_id` |
| 3 | `product-management-app` | Zod `link` opcional; `DataTable` pinta botones |
| 4 | `product-management-app` | `CopilotEntityPreview` + adapters de fetch; reusar `GrupoDetailModal` |
| 5 | ambos | QA humana (abajo) → PR backend → PR front |

Ramas: `feat/copilot-table-entity-links` en cada repo, desde `origin/main` (o continuar `feat/copilot-agentes-especialistas` si se acuerda un solo tren de merge).

---

## Migración de base de datos

Sin migración de BD. El contrato vive en el JSON del artefacto (SSE y mensajes persistidos). Artefactos antiguos sin `link` son válidos.

---

## Plan de prueba en CI/CD

**Backend (obligatorio en el PR):**

- Tests unitarios sobre `build_artifacts_from_tool_result` (o helper de anotación):
  - `sales_top_clients`: columna `cliente_nombre` → `entity=client`, `idKey=cliente_id`.
  - `sales_largest_order`: `pedido_id` → `order`; `cliente_nombre` → `client`.
  - `sales_top_products` / `get_productos`: `nombre` y `product_code` → `product` / `product_code`.
  - `agenda_list`: `id` → `agenda`; `grupo_nombre` → `group` / `grupo_id`; cliente → `client` / `client_id`.
  - `funnel_clients`: filas con `client_id`; nombre anotado.
  - `etiquetas_list` / `metrics_agent_summary` / `nl_sql_query`: **sin** `link`.
- Checks existentes de Copilot (agentes, tools) verdes.

**Front:**

- Si hay tests de artefactos: columna con `link` + id renderiza `button`; sin id no.
- `npx tsc --noEmit` en el PR de backoffice (no introducir `any` en el contrato).
- Gap aceptable: no hay E2E de click en Copilot; la prueba humana cubre el popup.

---

## Plan de prueba humana (antes del PR)

Servicios (tabla de puertos del workspace):

1. Backend: `cd backend-supabase && source venv/bin/activate && uvicorn main:app --reload --host 0.0.0.0 --port 8000`
2. Backoffice: `cd product-management-app && BACKEND_URL=http://localhost:8000 npm run dev` → **`http://localhost:3000`** (Maps).

Tenant: uno con Copilot on (p. ej. `del_corro` / Campi) y datos reales de clientes, productos, agendas y pedidos.

| # | Pasos | OK si |
|---|--------|--------|
| 1 | Carlos: “Top clientes del mes”. Click en un **nombre**. | Sheet/dialog de cliente con ese nombre; cerrar vuelve al chat. |
| 2 | Carlos: “Mayores pedidos”. Click en **ID** y en **nombre de cliente**. | Pedido vs cliente: dos previews distintos. |
| 3 | Carlos / Nina: tabla de productos. Click en **nombre** y en **código**. | Misma ficha de producto. |
| 4 | Martín: “Agendas del tenant”. Click en **ID** (agenda), **Grupo**, celda de **cliente**. | Tres entidades distintas. Agenda 1:1 sin grupo: grupo no es link. Agenda de grupo sin `client_id`: cliente no es link. |
| 5 | Lucía: “Clientes que no responden” (o funnel). Click en **nombre**. | Abre cliente. Si una fila no resolvió id, el nombre no es link. |
| 6 | Sofía: listado de plantillas. Omar: sync ERP. | Celdas **no** clickeables. |
| 7 | Ancho de tabla | Los links no rompen el `w-max` de las tablas anchas. |
| 8 | Teclado | Tab + Enter en un link abre el preview. |
| 9 | 404 | Id inventado (si se puede forzar) muestra error claro, no pantalla en blanco. |

---

## Relación con 038

Complementa [038-copilot-agentes-especialistas.md](./038-copilot-agentes-especialistas.md): los especialistas ya devuelven tablas; esta entrega las hace accionables. No cambia packs, prompts ni slugs.
