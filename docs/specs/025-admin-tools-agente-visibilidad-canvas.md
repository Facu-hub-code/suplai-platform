# Spec 025 — Admin Tools: catálogo de herramientas + visibilidad de canvas por tenant

**Estado:** Draft  
**Fecha:** 2026-07-16  
**Actualizado:** 2026-07-16 — alcance ampliado: edición editorial (nombre / “qué hace”) + tooltip hover en canvas  
**Tipo:** Cross-repo (backoffice admin + backend; consumo en Configuración → Herramientas del tenant)  
**Precede / relaciona:**  
- [024 — Modal explicativo de tools](./024-agent-tools-modal-explicativo-logs-dry-run.md)  
- Backoffice [057 — Canvas blueprint de tools](../../product-management-app/doc/specs/057-agent-tools-blueprint-canvas-ui.md)  
**Ramas sugeridas:**

| Repo | Rama |
|------|------|
| `suplai-platform` | `docs/spec-025-admin-agent-tools-canvas-visibility` |
| `backend-supabase` | `feat/tools-canvas-visibility` |
| `product-management-app` | `feat/admin-agent-tools-section` |

---

## 1) Contexto y problema

Hoy la configuración de tools del agente vive en dos lugares incompletos:

1. **Admin → Distribuidoras → Tools** (`DistribuidoraTools`): lista plana on/off + descripción. Está escondida dentro del catálogo de tenants, sin filtros por perfil (vendedor / PdV / recepcionista) y sin lenguaje de producto.
2. **Backoffice tenant → Configuración → Herramientas**: canvas React Flow por perfil. Solo muestra tools **habilitadas** cuyo `agent_groups` (código) incluye el perfil. Conectar/desconectar = `tools_habilitadas` **global**, no “mostrar en este canvas”.

Problemas concretos para implementaciones:

- El canvas es una **caja negra operativa**: mezcla tools de negocio (crear pedido) con tools de plomería del agente, sin forma de ocultar las que no aportan al implementador o al cliente.
- No hay forma de decir “esta tool está **encendida** para el runtime, pero **no la muestro** en el canvas del vendedor”.
- El admin de implementaciones no tiene una sección propia bajo **Tools implementación** para administrar el catálogo de forma educativa (tarjetas, no snake_case infinito).
- El canvas hoy muestra el **nombre técnico formateado** (`Create Order` desde `create_order`), no un nombre de producto editable, y **no explica al hover** qué hace cada nodo.

### Estado actual (referencia)

| Capa | Ubicación |
|------|-----------|
| Admin tools (lista) | `product-management-app/components/admin/distribuidora-tools.tsx` |
| Canvas tenant | `components/tools-config-section.tsx`, `lib/build-agent-tools-canvas.ts`, `components/agent-tools/tool-node.tsx` |
| API tenant | `GET/PATCH /{schema}/distribuidora/config/tools` |
| API admin | `POST /admin/distribuidoras/tools/{get,patch,backfill}` |
| Enable runtime | `public.distribuidoras.tools_habilitadas` |
| Perfil técnico | `tools_meta.agent_groups` (dump desde agente; no editable por tenant) |
| Editorial | `core.agent_tools` (spec 024; seed piloto; **sin API de escritura UI**) |

**No existe** hoy: sección admin dedicada, `show_in_canvas_*`, edición UI de `display_name` / `short_description`, ni tooltip hover en nodos del canvas.

---

## 2) Objetivo

Agregar en **Admin → Tools implementación** una sección **Tools del agente** que permita:

1. **Administrar las tools** con UX de **buscador de tarjetas**, filtrable por perfil (**Vendedor**, **Punto de venta**, **Recepcionista**).
2. Al seleccionar una tarjeta, abrir un **modal ABM** con:
   - config **por tenant** (enable, visibilidad canvas, descripción LLM, post-éxito);
   - textos **editoriales del catálogo** (nombre visible en canvas, “qué hace” para hover) — ver §3.
3. Configurar, **por tenant**, la **visibilidad condicional en el canvas** (qué tools aparecen en el canvas de vendedor / PdV / recepcionista), **sin confundir** eso con enable/disable de runtime.
4. Reutilizar esa misma config de visibilidad en el canvas de **Configuración → Herramientas** del backoffice del tenant.
5. Que el canvas muestre **nombres humanos** editables y, al pasar el mouse sobre un nodo-tool, un **hint flotante** (“toast” / tooltip) con qué hace la tool.

### Métricas de éxito

- Un implementador encuentra y configura una tool en &lt; 30 s (buscar → filtrar perfil → abrir tarjeta → guardar).
- Se puede dejar `search_products` habilitada en runtime y oculta en el canvas del recepcionista (o viceversa) sin redeploy.
- Tenants existentes no cambian comportamiento hasta que se edite visibilidad (defaults = compatibles con hoy).
- Tras editar `display_name` / `short_description` en admin, el canvas del tenant refleja el nombre y el hover muestra el texto nuevo sin redeploy del agente.

---

## 3) Decisiones de diseño técnico

| Tema | Decisión | Por qué (alternativa descartada) |
|------|----------|----------------------------------|
| Ubicación UI | Nueva sección bajo el grupo sidebar **Tools implementación**, id `agent-tools` (“Tools del agente”) | Hoy vive enterrada en Distribuidoras; el grupo Tools ya agrupa Lab/Health/Cleanup. Descartado: solo mejorar el panel dentro de Distribuidoras (sigue sin discoverability). |
| Flujo de pantalla | 1) Selector de tenant → 2) Grid de tarjetas con búsqueda + chips de perfil → 3) Modal ABM | Pedido explícito; escala mejor que lista infinita de switches. Descartado: canvas React Flow en admin (duplica el canvas del tenant y es más pesado para ABM). |
| Enable vs visibilidad | **Dos conceptos**: `tools_habilitadas` (runtime) y `tools_canvas_visibility` (solo UI del canvas) | Mezclarlos hace que “ocultar del canvas” apague la tool en WhatsApp. Descartado: reusar `tools_habilitadas` por perfil (rompe runtime actual y el grafo del agente). |
| Persistencia visibilidad | Nueva columna JSONB en `public.distribuidoras`: `tools_canvas_visibility` | Misma familia que `tools_habilitadas` / `tools_descripciones`; merge parcial por tool. Descartado: tabla hija (overkill v1) y solo `metadata` (más opaco para API/admin). |
| Semántica del JSON | Por `tool_name`: `{ "seller": bool, "client": bool, "reception": bool }` | Alineado a perfiles del canvas (`AgentProfile`). Descartado: booleano único “visible” (no alcanza para seller vs PdV). |
| Defaults (key ausente) | Si no hay entrada: **mostrar en canvas** del perfil **solo si** la tool está enabled **y** `agent_groups` incluye ese perfil (comportamiento actual) | Zero-touch para tenants existentes. Descartado: default `false` (vaciaría todos los canvases al deploy). |
| Filtro de tarjetas por perfil | Filtra por `tools_meta.agent_groups` (pertenencia técnica), no por flags de canvas | El implementador busca “tools del vendedor” aunque aún no estén visibles en canvas. Descartado: filtrar solo por visibilidad canvas (escondería tools a configurar). |
| Origen de copy de tarjeta / canvas | Preferir `core.agent_tools` (`display_name`, `short_description`, `category`, `icon`); fallback a nombre formateado + `default_tool_descriptions` | Spec 024 ya define la capa educativa. Descartado: inventar otro catálogo en el admin. |
| Edición editorial (nombre + “qué hace”) | **Editable en v1** desde el modal admin → escribe en `core.agent_tools` (**global**, todos los tenants) | Un solo nombre de producto en el canvas evita N overrides por cliente. Hint UI: “Afecta el canvas de todos los tenants”. Descartado: override por tenant de `display_name` (complejidad y copy inconsistente). Descartado: seguir solo con seed SQL (spec 024 “edición UI futura” se adelanta aquí para los campos del canvas). |
| Campos editoriales en v1 | `display_name` (título del nodo) + `short_description` (texto del hover) + opcional `category` / `icon` | Suficiente para canvas educativo. `how_it_works` / `when_to_use` siguen editables si ya están en el modal como textarea expandible; no bloquean v1. Descartado: editar outputs/side_effects/prerequisites en este epic (sigue siendo ficha larga del modal 024). |
| Upsert editorial | Si la tool no tiene fila en `core.agent_tools`, el PATCH **crea** la fila con defaults mínimos (`category='general'`, `status='active'`) | Evita “no puedo ponerle nombre porque no hay seed”. Descartado: exigir seed SQL previo. |
| Hover en canvas (“toast”) | **Tooltip / popover flotante al hover** sobre el `ToolNode` (Radix `Tooltip` o equivalente del design system), **no** Sonner/toast de notificación | Sonner se usa para acciones (guardar/error) y spamearía en cada hover. El usuario pidió “toast” en sentido de hint breve junto al nodo. Contenido: `short_description` (fallback: primeros ~160 chars de descripción default / LLM). Delay ~300 ms; no bloquea click de configurar. |
| Panel legacy en Distribuidoras | Deeplink / botón “Abrir Tools del agente” que lleve a la nueva sección con `?section=agent-tools&schema=…`; lista legacy marcada como secundaria o removida en el mismo PR si el costo es bajo | Evitar dos UIs divergentes. Descartado: mantener ambas sin enlace (confusión). |
| Quién puede ver/editar | Misma matriz de permisos que `lab` / tools de implementación: área `implementaciones` o `tecnica` + sección nueva `agent_tools` con `view`/`edit` | Consistente con HR permissions. Editar editorial global exige `edit` en `agent_tools`. Descartado: solo founders (bloquea implementadores). |
| Impacto en runtime agente | **Ninguno**. Visibilidad canvas y textos editoriales no entran en `build_tools()` | El agente sigue usando solo `tools_habilitadas` + `agent_groups` + gates (`field_app_enabled`, opt-in) + `tools_descripciones` para el LLM. Descartado: filtrar tools del LLM por canvas visibility (rompería conversaciones). |

---

## 4) Alcance

### Incluido (v1)

- Nueva sección **Admin → Tools implementación → Tools del agente**.
- Selector de distribuidora/tenant.
- **Buscador de tarjetas** con:
  - Texto libre (nombre humano, `tool_name`, categoría).
  - Chips/filtro: **Todos | Vendedor | Punto de venta | Recepcionista**.
  - Badges en tarjeta: enabled/disabled, perfiles canvas visibles, opt-in, field-only, sin ficha editorial.
- **Modal ABM por tool** con campos:
  - **Catálogo (global)** — editables:
    - **Nombre en canvas** → `core.agent_tools.display_name`
    - **Qué hace (hover)** → `core.agent_tools.short_description` (1–2 líneas, máx. ~200 chars recomendado)
    - Opcional: `category`, `icon`, `how_it_works` / `when_to_use` (textareas; no bloquean si van vacíos)
  - **Este tenant** — editables:
    - **Habilitada** (`tools_habilitadas`)
    - **Visible en canvas** — tres switches: Vendedor / PdV (`client`) / Recepcionista
    - Descripción para el LLM (`tools_descripciones`) opcional
    - Mensaje post-éxito (`tools_mensajes_post_success`) opcional
  - Acciones: Guardar (puede disparar 1–2 requests: editorial global + config tenant), Resetear descripción LLM al default, (opcional) link a dry-run/logs si spec 024 ya está mergeada.
- Persistencia `tools_canvas_visibility` + exposición en APIs admin y tenant.
- API admin de **upsert editorial** sobre `core.agent_tools` (ver §7).
- Canvas de **Configuración → Herramientas** (tenant):
  - Respeta `tools_canvas_visibility` al armar el grafo.
  - Nodo muestra `display_name` (fallback: nombre formateado).
  - **Hover** sobre el nodo → tooltip con `short_description` (fallback: descripción default truncada).
- Permiso de sección `agent_tools` en el sistema de permisos admin.
- Deeplink: `/admin?section=agent-tools&schema=<schema>&tool=<tool_name>`.

### Fuera de alcance (v1)

- Editar `agent_groups`, guards o canal determinista desde UI (siguen en código / config general).
- **Alta de tools nuevas en el registry** del agente (sigue siendo código + dump meta). Solo se edita/crea la **ficha editorial** de tools que ya existen en el registry.
- Override **por tenant** de `display_name` / `short_description` (el nombre del canvas es global).
- Edición completa de outputs / side_effects / prerequisites desde este modal (queda en el modal educativo spec 024 si ya existe).
- Enable **por perfil** en runtime (solo visibilidad de canvas por perfil).
- Canvas React Flow dentro del admin.
- Field-app / tienda: no muestran este catálogo.
- Usar Sonner u otro toast de notificación para el hover (usar Tooltip/Popover).

---

## 5) UX — sección y modal

### 5.1 Navegación

```
Admin sidebar
└── Tools implementación (grupo)
    ├── Laboratorio
    ├── Health
    ├── Cleanup
    └── Tools del agente   ← NUEVO
```

Header: título **Tools del agente** + subtítulo *Configurá qué puede usar el agente y qué se muestra en el canvas por perfil*.

### 5.2 Layout principal

```
┌─────────────────────────────────────────────────────────────┐
│ Tenant: [ selector distribuidora ▼ ]     [ Backfill ]       │
│ Buscar: [________________]                                  │
│ Perfil: ( Todos ) ( Vendedor ) ( PdV ) ( Recepcionista )    │
├─────────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐                      │
│ │ Crear    │ │ Buscar   │ │ Confirmar│  … tarjetas          │
│ │ pedido   │ │ productos│ │ pedido   │                      │
│ │ ON · 👁 V │ │ ON · 👁 P │ │ OFF      │                      │
│ └──────────┘ └──────────┘ └──────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

- Click en tarjeta → abre modal ABM.
- Vacío: mensaje “Elegí un tenant” / “Sin tools para este filtro”.

### 5.3 Modal ABM (una tool)

Secciones del modal (orden sugerido):

1. **Cabecera** — `tool_name` (mono, read-only) + badge de categoría.
2. **Cómo se ve en el canvas (catálogo Suplai — todos los tenants)** — bloque con borde/hint claro:
   - Input **Nombre en canvas** → `display_name` (requerido al guardar editorial; 2–60 chars).
   - Textarea corta **Qué hace (al pasar el mouse)** → `short_description` (requerido; 1–2 líneas).
   - Preview live: mini-nodo + “hover preview” del tooltip.
   - Opcional collapsible: `how_it_works`, `when_to_use`, `category`, `icon`.
3. **Runtime (este tenant)** — Switch **Habilitada para el agente** (+ hint opt-in si aplica).
4. **Canvas — visibilidad (este tenant)** — tres switches independientes:
   - Mostrar en canvas **Vendedor**
   - Mostrar en canvas **Punto de venta**
   - Mostrar en canvas **Recepcionista**
   - Hint: *No cambia si el agente puede usar la tool; solo qué se ve en el mapa de Configuración → Herramientas.*
   - Si el perfil no está en `agent_groups`, el switch puede mostrarse disabled con tooltip “Esta tool no pertenece a este perfil en el código del agente”.
5. **Textos avanzados (este tenant)** (collapsible) — descripción LLM + mensaje post-éxito.
6. **Footer** — Cancelar / Guardar.

Validación:

- No se puede marcar “mostrar en canvas X” si la tool no pertenece a `agent_groups` de X (**v1: no permitir**).
- `display_name` y `short_description` no vacíos al guardar el bloque editorial.
- Guardar editorial sin tenant seleccionado: permitido solo si se define modo “solo catálogo”; en el flujo v1 con tenant obligatorio, igual se puede guardar editorial + config tenant en un solo Guardar.

### 5.4 Canvas tenant — nombre + hover

En `tool-node.tsx` (y data pasada desde `build-agent-tools-canvas.ts`):

| Elemento | Fuente |
|----------|--------|
| Título del nodo | `editorial.display_name` \|\| `formatToolName(toolName)` |
| Subtítulo | `tool_name` (mono, como hoy) |
| Hover / “toast” | Tooltip con `editorial.short_description` \|\| truncar descripción default |

Comportamiento:

- Aparece al **hover** (y focus teclado) con delay corto; desaparece al salir.
- No abre el modal ni dispara Sonner.
- Click en el nodo sigue abriendo configuración (comportamiento actual).
- Accesible: el tooltip debe asociarse con `aria-describedby` o patrón Radix Tooltip.

---

## 6) Modelo de datos

### 6.1 Migración — columna tenant

```sql
ALTER TABLE public.distribuidoras
  ADD COLUMN IF NOT EXISTS tools_canvas_visibility jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.distribuidoras.tools_canvas_visibility IS
  'Por tool_name: { seller, client, reception } bool — visibilidad en canvas UI; no afecta runtime del agente.';
```

Ejemplo:

```json
{
  "create_order": { "seller": true, "client": true, "reception": false },
  "get_seller_route": { "seller": true, "client": false, "reception": false },
  "resolve_client_identity": { "seller": false, "client": false, "reception": false }
}
```

### 6.2 Resolución de visibilidad (backend + front)

```
visible_in_canvas(tool, profile, tenant) =
  if tools_canvas_visibility[tool][profile] is boolean:
    return that value
  else:
    return tool_enabled(tool, tenant) AND profile in agent_groups(tool)
```

El canvas del tenant **debe** usar esta función (no solo `enabled && agent_groups`).

### 6.3 Editorial — `core.agent_tools` (ya existe, spec 024)

Sin migración de schema nueva para editorial. Se agrega **escritura** vía API:

| Campo | Uso en canvas |
|-------|----------------|
| `display_name` | Título del nodo |
| `short_description` | Texto del tooltip hover |
| `category`, `icon` | Tarjetas admin / badges (opcional) |
| `how_it_works`, `when_to_use` | Modal largo / preview (opcional en este ABM) |

Upsert: `INSERT … ON CONFLICT (tool_name) DO UPDATE` de los campos enviados. `updated_at = now()`.

### 6.4 Sin cambios en

- Semántica de `tools_habilitadas`, `tools_descripciones`, `tools_mensajes_post_success`
- `core.agent_tool_executions`
- Registry del agente / `build_tools()`

### 6.5 Seed / backfill

- `tools_canvas_visibility` default `{}` → resolución legacy.
- Opcional: materializar defaults de canvas; opcional: seed faltante de `core.agent_tools` con `display_name` = nombre formateado y `short_description` = default description truncada (mejora UX, no bloquea).

### 6.6 Rollback

- Visibilidad: dejar de leer/escribir la columna; riesgo bajo.
- Editorial: revertir filas editadas o redeploy de seed; la API de escritura se desactiva en código.

---

## 7) API

### 7.1 Admin

Extender payloads existentes y agregar escritura editorial:

| Endpoint | Cambio |
|----------|--------|
| `POST /admin/distribuidoras/tools/get` | Incluir `tools_canvas_visibility`, `tools_meta`, `tools_editorial` (mapa `tool_name` → ficha), `tools_mensajes_post_success` |
| `POST /admin/distribuidoras/tools/patch` | Aceptar merge parcial `tools_canvas_visibility` (misma semántica merge que `tools_habilitadas`) |
| `POST /admin/distribuidoras/tools/backfill` | No obliga a rellenar visibilidad; documentar si se agrega modo `materialize_canvas_defaults` |
| `POST /admin/agent-tools/editorial/upsert` (**nuevo**) | Body: `{ "tool_name", "display_name", "short_description", "category?", "icon?", "how_it_works?", "when_to_use?" }`. Valida que `tool_name` exista en registry / `tools_meta`. Upsert en `core.agent_tools`. Requiere `edit` en `agent_tools`. |

Alternativa aceptable: incluir bloque `tools_editorial_patch` dentro del `tools/patch` admin — pero **separar** el endpoint deja claro el scope global vs tenant y evita mezclar transacciones.

### 7.2 Tenant (backoffice Configuración)

| Endpoint | Cambio |
|----------|--------|
| `GET /{schema}/distribuidora/config/tools` | Incluir `tools_canvas_visibility` |
| `PATCH /{schema}/distribuidora/config/tools` | Permitir patch de `tools_canvas_visibility` (operador del tenant) **o** dejar escritura solo admin en v1 |

**Decisión v1:** lectura en ambos; **escritura** en admin (sección nueva) **y** en el modal del canvas tenant (para no forzar ir al admin). Si se quiere restringir al admin, marcar el PATCH tenant como fuera de alcance y solo GET.

**Recomendación:** escritura en ambos con mismo merge (implementadores usan admin; operadores del cliente ajustan desde Configuración).

### 7.3 Shape PATCH

```json
{
  "schema_name": "demo",
  "tools_habilitadas": { "create_order": true },
  "tools_canvas_visibility": {
    "create_order": { "seller": true, "client": true, "reception": false }
  },
  "tools_descripciones": {},
  "tools_mensajes_post_success": {}
}
```

Merge: por `tool_name`, merge superficial de claves de perfil; `null` en un perfil puede significar “borrar override y volver al default” (documentar en OpenAPI).

---

## 8) Cambios de UI por repo

### 8.1 `product-management-app` (admin)

| Archivo / área | Cambio |
|----------------|--------|
| `lib/admin/permissions-types.ts` | Agregar sección `agent_tools` / nav `agent-tools` |
| `components/admin/admin-sidebar.tsx` | Item en `toolsNavItems` |
| `app/admin/page.tsx` | Montar nueva section component |
| `components/admin/agent-tools-section.tsx` (nuevo) | Selector tenant + grid + filtros |
| `components/admin/agent-tool-card.tsx` (nuevo) | Tarjeta |
| `components/admin/agent-tool-abm-modal.tsx` (nuevo) | Modal ABM |
| `components/admin/distribuidora-tools.tsx` | Deeplink a la nueva sección o thin wrapper |

### 8.2 `product-management-app` (tenant Configuración)

| Archivo | Cambio |
|---------|--------|
| `lib/build-agent-tools-canvas.ts` | Filtrar con `tools_canvas_visibility`; pasar `displayName` + `shortDescription` al nodo |
| `components/agent-tools/tool-node.tsx` | Título = `displayName`; Tooltip hover con `shortDescription` |
| `components/tools-config-section.tsx` | Cargar/guardar visibilidad; en lista, chips de canvas; usar editorial en labels |
| `components/tool-config-modal.tsx` | Switches de visibilidad canvas (misma semántica). Nombre editorial: read-only con link “Editar en Admin → Tools del agente” **o** mismos campos si el usuario es staff (opcional; v1 mínimo = solo admin edita editorial) |

### 8.3 `backend-supabase`

| Archivo | Cambio |
|---------|--------|
| Migración SQL | `tools_canvas_visibility` en `public.distribuidoras` |
| `routers/distribuidoras_tools_config.py` | GET/PATCH (+ devolver `tools_editorial` ya unido si aplica) |
| `routers/admin.py` (tools get/patch) | Idem + endpoint upsert editorial |
| Servicio editorial | Upsert `core.agent_tools` con validación de registry |
| Tests | Merge/resolución canvas; upsert editorial; rechazo de `tool_name` desconocido |

### 8.4 `agente-conversacional-multi_tenant`

Sin cambios de runtime en v1. (Opcional docs: aclarar que canvas visibility es solo UI.)

---

## 9) Orden de implementación

1. **Backend** — migración `tools_canvas_visibility` + GET/PATCH admin/tenant + **upsert editorial** + tests.  
   Rama: `feat/tools-canvas-visibility`
2. **Backoffice admin** — sección, tarjetas, modal ABM (tenant + editorial), permisos, deeplink.  
   Rama: `feat/admin-agent-tools-section`
3. **Backoffice tenant** — canvas: filtro visibilidad + `display_name` + **tooltip hover**.  
   Misma rama backoffice o PR follow-up corto.
4. **Docs platform** — este spec; actualizar inventario de features si aplica.

Merge order: **backend → backoffice**. El agente no bloquea.

---

## 10) Migración de base de datos

| Ítem | Detalle |
|------|---------|
| Cambio tenant | `ALTER TABLE public.distribuidoras ADD COLUMN tools_canvas_visibility jsonb NOT NULL DEFAULT '{}'` |
| Cambio editorial | **Sin migración** — tabla `core.agent_tools` ya existe (spec 024 / migración 78). Solo API de escritura. |
| Seed | No requerido para visibilidad. Editorial: upsert on-demand o backfill opcional de fichas faltantes. |
| Backfill | Opcional |
| Orden | Migración columna tenant antes de deploy API que la escribe; upsert editorial puede ir en el mismo deploy backend |
| Rollback | Columna: dejar de usar / drop opcional. Editorial: desactivar endpoint. |
| Riesgo | Bajo |

---

## 11) Plan de prueba en CI/CD

| Check | Repo | Notas |
|-------|------|-------|
| Unit: merge `tools_canvas_visibility` | backend | Override parcial, `null` reset, default legacy |
| Unit: `visible_in_canvas` | backend o backoffice `lib/` | Matriz enabled × agent_groups × overrides |
| Unit: upsert editorial | backend | Crea fila si falta; actualiza `display_name` / `short_description`; rechaza tool desconocida |
| Typecheck / lint | backoffice | Nueva sección + permisos + Tooltip en `tool-node` |
| Tests existentes tools config | backend | No regresiones en patch de `tools_habilitadas` |
| Gap | — | No hay E2E Playwright admin hoy; mínimo aceptable = unit + prueba humana |

---

## 12) Plan de prueba humana (antes del PR)

**Servicios**

| Servicio | Puerto |
|----------|--------|
| Backend | `8000` |
| Backoffice | `3000` |

```bash
# Terminal 1
cd backend && source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2
cd backoffice && BACKEND_URL=http://localhost:8000 npm run dev
```

**Tenant de prueba:** `demo` (u otro con tools backfilleadas).

**Checklist**

1. Login admin con permiso de implementaciones/técnica.
2. Sidebar → **Tools implementación** → **Tools del agente**.
3. Elegir tenant → ver grid de tarjetas con nombres humanos cuando hay editorial.
4. Filtrar **Vendedor** / **PdV** / **Recepcionista** → el set cambia según `agent_groups`.
5. Buscar por texto (`pedido`, `create_order`) → filtra.
6. Abrir una tool compartida (ej. catálogo/pedido):
   - Cambiar **Nombre en canvas** a algo humano (ej. “Buscar productos”).
   - Completar **Qué hace (hover)** con una línea clara.
   - Dejar **Habilitada = ON**.
   - Canvas Vendedor = ON, PdV = OFF (si pertenece a ambos) → Guardar.
7. En backoffice del tenant → Configuración → Herramientas:
   - Perfil Vendedor: la tool **aparece** con el **nuevo nombre**.
   - Hover sobre el nodo → aparece el tip con el texto “qué hace” (sin toast Sonner).
   - Perfil PdV: la tool **no aparece** en canvas aunque siga enabled.
8. Abrir canvas de **otro** tenant → el **mismo nombre** editorial se ve (global).
9. Enviar mensaje WhatsApp / lab que dispare esa tool en PdV → **sigue funcionando** (runtime no afectado).
10. Quitar override de visibilidad → canvas vuelve al default (enabled ∩ agent_groups); el nombre editorial permanece.
11. Usuario sin permiso `agent_tools` → no ve la sección / no puede upsert editorial.

---

## 13) Criterios de aceptación

- [ ] Existe sección **Tools del agente** bajo Tools implementación.
- [ ] UI = selector tenant + buscador de tarjetas + filtros Vendedor / PdV / Recepcionista.
- [ ] Click en tarjeta abre modal ABM con: nombre canvas + “qué hace”, enable, 3 switches de visibilidad, textos LLM/post-éxito opcionales.
- [ ] Guardar `display_name` / `short_description` persiste en `core.agent_tools` (upsert si no existía fila).
- [ ] El modal advierte que esos textos son **globales** (todos los tenants).
- [ ] `tools_canvas_visibility` persiste por tenant y sobrevive reload.
- [ ] Canvas del tenant: título = `display_name`; hover = tooltip con `short_description`.
- [ ] Canvas del tenant respeta overrides de visibilidad; ausencia de key = comportamiento previo.
- [ ] Deshabilitar visibilidad de canvas **no** deshabilita la tool en el agente.
- [ ] No se puede marcar visible en un perfil fuera de `agent_groups`.
- [ ] Permisos admin: sin `view` no se ve la sección; sin `edit` no se guarda ni se hace upsert editorial.
- [ ] Deeplink con `schema` + `tool` abre el modal correspondiente.

---

## 14) Riesgos y notas

- **Fichas editoriales incompletas:** muchas tools sin fila en `core.agent_tools`; el upsert del modal las crea al guardar nombre/“qué hace”. Hasta entonces, tarjetas y canvas degradan a nombre formateado + descripción default.
- **Edición global:** un implementador que cambia el nombre en el tenant A afecta el canvas de todos. El hint del modal es obligatorio.
- **Recepcionista:** tools de registration pueden no estar en `ALL_AGENT_TOOL_NAMES` / `tools_habilitadas`; el grid debe incluirlas vía `tools_meta` con `agent_groups: ["reception"]` aunque el toggle enable sea limitado o read-only en v1 (documentar en UI si no son patchables). Editorial sí se puede upsert si están en `tools_meta`.
- **Doble UI:** cerrar o redirigir el panel legacy en Distribuidoras en el mismo epic para no bifurcar config.
- **Hover vs drag del canvas:** el Tooltip no debe pelear con pan/zoom de React Flow (`nodrag` ya está en el nodo); probar que el tip no se queda “pegado” al mover el viewport.

---

## 15) Preguntas abiertas (resolver en implementación si no hay respuesta)

1. ¿El operador del **tenant** (no staff Suplai) puede editar visibilidad de canvas desde Configuración → Herramientas, o solo staff admin?  
   **Default del spec:** ambos pueden.
2. ¿Queremos un cuarto chip **“Solo ocultas / solo visibles”** en el grid?  
   **Default v1:** no; se itera después.
3. ¿El operador del tenant puede editar `display_name` / `short_description` desde su modal de Configuración, o solo staff en Admin?  
   **Default del spec:** solo Admin (editorial global); en el modal tenant se muestra read-only + hint.
4. ¿Límite duro de caracteres en `short_description` (ej. 200) enforced en API?  
   **Default del spec:** soft limit 200 en UI; API acepta hasta 500 y trunca en tooltip si hace falta.
