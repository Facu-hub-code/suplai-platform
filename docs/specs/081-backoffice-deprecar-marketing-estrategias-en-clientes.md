# 081 — Backoffice: deprecar Marketing y mover Estrategias a Herramientas de Clientes

**Estado:** Implementado en `product-management-app` rama `feat/sidebar-sin-marketing-estrategias-en-clientes` (sin PR todavía)  
**Fecha:** 2026-09-26  
**Repos:** `suplai-platform` (este doc), `product-management-app`  
**Rama sugerida:** `feat/sidebar-sin-marketing-estrategias-en-clientes` (`product-management-app`)  
**Relaciona:** [032 — Marketing Meta Ads](./032-marketing-meta-ads.md) (módulo que se depreca en la UI), [079](./079-vendedores-herramientas-y-reporte.md) (mismo patrón de tarjetas en Herramientas), [073 — Mixpanel](./073-mixpanel-analytics.md) (evento `estrategia_creada`). Sidebar en [`app/page.tsx`](../../../product-management-app/app/page.tsx) (`mainNavItems`). Herramientas de Clientes en [`client-tools-modal.tsx`](../../../product-management-app/components/client-tools-modal.tsx) sobre `ManagementToolsPickerModal` ([`management-tool-modal.tsx`](../../../product-management-app/components/management-tool-modal.tsx)), consumido por [`contacts-table.tsx`](../../../product-management-app/components/contacts-table.tsx). Estrategias hoy en [`strategies-view.tsx`](../../../product-management-app/components/strategies-view.tsx) y [`components/estrategias/`](../../../product-management-app/components/estrategias/).

---

## Contexto

La sidebar del backoffice tiene 11 entradas. Dos no se sostienen como sección propia:

- **Marketing** (Meta Ads Click-to-WhatsApp, spec 032) está en Beta y no tiene uso: en todo el proyecto hay 1 campaña y 1 creatividad, ambas en `demo`. El resto de los 40+ tenants tiene las tablas vacías.
- **Estrategias** es una forma de mandarle mensajes a un grupo de clientes. Sus insumos (grupos, plantillas de Meta, agendas) ya viven en Herramientas de Clientes. El supervisor sale de Clientes para crear algo que se arma con piezas de Clientes.

Datos al 2026-09-26 (MCP Supabase, `cvlbietibaaehgeimxgw`):

| Tabla | Filas |
|-------|-------|
| `{schema}.marketing_campaigns` | 1 (`demo`) |
| `{schema}.marketing_creative_packages` | 1 (`demo`) |
| `core.conversation_ad_attribution` | 969 |
| `{schema}.estrategias` | 5 (`demo` 3, `gonzales` 1, `cordoba_frost` 1) |

La atribución `ctwa_clid` la escribe el agente para cualquier anuncio Click-to-WhatsApp que traiga un cliente, se haya creado o no desde el módulo Marketing. No depende de la pantalla y no se toca.

---

## Objetivo

1. Sacar Marketing del backoffice: sin entrada en la sidebar y sin código de UI. Backend, tablas y atribución quedan como están.
2. Sacar Estrategias de la sidebar y ofrecerla como una tarjeta en Herramientas de Clientes, con dos botones de entrada: **Modo simple** y **Modo inteligente**.
3. La tarjeta también abre la administración de las estrategias existentes (KPIs, lista, editar, pausar, borrar, calendario de envíos, ciclos, Calendario Comercial), sin perder nada de lo que hace hoy la sección.

### Métricas de éxito

- La sidebar queda con 9 entradas (8 si `AGENT_METRICS_DASHBOARD_ENABLED` está apagado).
- Desde Clientes → Herramientas se crea una estrategia simple y una inteligente con un clic menos que hoy (no hay que elegir el modo dentro del asistente).
- Las 5 estrategias existentes se ven, se editan y se pausan desde el modal, igual que en la sección actual.
- `estrategia_creada` en Mixpanel lleva `modo` (`simple` / `smart`).

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Alcance de “deprecar Marketing” | Borrar la entrada de la sidebar, `components/marketing/**`, `MarketingView` y los proxies `app/api/marketing/**`. Backend (`routers/marketing.py`, `services/marketing_service.py`, `meta_marketing_client.py`), tablas y `core.conversation_ad_attribution` no se tocan | Sin uso real, la UI es código que hay que mantener en cada refactor del backoffice. El backend no molesta a nadie y guarda la opción de volver sin migración. | Solo ocultar la entrada: deja ~15 archivos muertos que siguen compilando y rompiendo en cada cambio de tipos. Retiro completo con backend y DROP: toca 3 repos y la atribución del agente por un módulo que no cuesta nada tener apagado en el servidor. |
| Proxies `app/api/marketing/**` | Se borran junto con la UI | Sin pantalla no tienen consumidor. Verificado: ningún archivo fuera de `components/marketing/**` llama a `/api/marketing`. | Dejarlos “por si acaso”: son rutas expuestas sin dueño. |
| Credenciales Meta Ads en Admin | La pestaña “Marketing” de [`distribuidora-credentials-modal.tsx`](../../../product-management-app/components/admin/distribuidora-credentials-modal.tsx) queda | Es del panel interno de Suplai, no del tenant. Los secrets `meta_ads.*` siguen siendo válidos para el backend; borrar la pestaña obliga a ir a SQL si el módulo vuelve. | Sacarla en esta entrega: no suma al objetivo (la sidebar del tenant) y quita la única forma de ver si un tenant tiene credenciales. |
| Categoría de plantilla `MARKETING` | No se toca | Es la categoría de Meta para plantillas de WhatsApp (`UTILITY` / `MARKETING` / `AUTHENTICATION`) en Copilot, plantillas y estrategias. No tiene relación con el módulo. | — |
| Dónde vive Estrategias | Una tarjeta **Estrategias** en `ClientToolsModal`, destacada | Crear una estrategia es elegir un grupo de clientes y una plantilla; las dos cosas ya están en esas Herramientas. | Dos tarjetas separadas (Simple / Inteligente) más una “Mis estrategias”: tres tarjetas para un mismo objeto llenan el picker de 6 a 9. |
| Dos botones dentro de la tarjeta | Nuevo campo opcional `actions?: { id: string; label: string; icon?: LucideIcon }[]` en `ManagementToolPickerItem`. Clic en el cuerpo de la tarjeta → `onSelectTool(tool.id)`; clic en un botón → `onSelectTool(action.id)` | El picker hoy es un `<button>` por tarjeta; un botón dentro de otro es HTML inválido y el clic se propaga mal. Con `actions`, la tarjeta pasa a `div role="button"` con `tabIndex=0` y Enter/Espacio, y los botones son hermanos. Las demás tarjetas no cambian. | Un menú desplegable dentro de la tarjeta: esconde las dos opciones que el pedido quiere visibles. |
| Ids de herramienta | `ClientToolId` suma `"estrategias"`, `"estrategia-simple"`, `"estrategia-smart"` | El handler de `contacts-table.tsx` ya despacha por id; los botones son dos ids más, sin callback nuevo. | Un solo id con payload: cambia la firma de `onSelectTool` para todos los pickers. |
| Qué abre el cuerpo de la tarjeta | `ManagementToolModal` size `full` con `StrategiesView` adentro (KPIs, lista, Calendario Comercial, guía de ayuda) | Es la sección de hoy, entera, en otro contenedor. El supervisor la cierra y vuelve a la tabla de clientes en el mismo lugar. | Reescribir la lista para el modal: mismo resultado con más riesgo. |
| Qué abren los botones | El asistente `CreateStrategyModal` directo, con el modo ya elegido. No pasa por el modal de la lista | “Botón de entrada” = empezar a crear. Abrir primero la lista y después el asistente son dos modales para una acción. | Abrir la lista con el asistente encima: al cerrar el asistente queda un modal que el usuario no pidió. |
| Modo preseleccionado | Prop nueva `initialMode?: StrategyModeType` en `CreateStrategyModalProps`, pasada a `StrategyFormProvider`. En el `useEffect` de apertura en modo creación (`strategy-form-context.tsx`, bloque `isOpening && !estrategiaId`) se llama `setModeType(initialMode)` | Hoy la creación no resetea el modo: abre con el último usado. `setModeType("smart")` ya limpia grupos dinámicos no válidos para Inteligente. | Duplicar el asistente en dos componentes: dos copias del mismo formulario. |
| Toggle de modo dentro del asistente | Queda visible en creación | Si el usuario entró por el botón equivocado cambia ahí sin cerrar y reabrir. En edición sigue fijo como hoy. | Ocultarlo: obliga a cancelar para corregir un clic. |
| Después de guardar desde un botón | Mismo flujo que hoy: `onAfterSave` abre `StrategySendCalendarModal` de la estrategia nueva | El calendario de envíos es la confirmación de que quedó programada; es lo que ve hoy quien crea desde la sección. | Abrir la lista: el usuario no ve cuándo sale el primer mensaje. |
| Dueño del estado | Componente nuevo `components/estrategias/client-strategies-tool.tsx` que monta el modal de la lista, el asistente y el calendario de envíos, y expone `openList()`, `openCreate(mode)` | `contacts-table.tsx` ya tiene ~750 líneas y seis modales. Un componente por herramienta es lo que hacen Grupos y Agenda. | Meter todos los `useState` en `contacts-table.tsx`. |
| Botón “Nueva Estrategia” dentro de la lista | Se reemplaza por dos botones: “Modo simple” y “Modo inteligente” | Misma entrada que la tarjeta; un solo lenguaje para crear. De paso corrige el estado vacío, donde hoy `onCreateSimple` y `onCreateSmart` llaman al mismo handler y el modo no cambia. | Dejar “Nueva Estrategia” + toggle interno: dos formas distintas de lo mismo. |
| `StrategiesView` fuera de la sidebar | Se sigue montando lazy: solo cuando se abre el modal (`isActive = open`) | Hoy carga KPIs y lista solo si la sección está activa. En Clientes no tiene que pedir `/api/estrategias` cada vez que se entra a la tabla. | Precargar al entrar a Clientes: tres requests extra por visita. |
| Mixpanel | `estrategia_creada` suma la propiedad `modo: "simple" | "smart"` | Es la única forma de medir si el Modo inteligente se usa, que es la razón de tener dos botones. Sin PII. | Evento nuevo `estrategia_entrada_clic`: duplica `estrategia_creada` para medir lo mismo. |

---

## Alcance explícito

### Incluido (v1)

- `app/page.tsx`: fuera `strategies` y `marketing` de `mainNavItems`, fuera los dos bloques `visitedSections.has(...)`, fuera los imports de `StrategiesView` y `MarketingView` y de los íconos `Target` / `Megaphone` si quedan sin uso. La condición del badge Beta queda solo para `copilot`.
- Borrar `components/marketing/**` y `app/api/marketing/**`.
- `ManagementToolPickerItem.actions` y su render en `ManagementToolsPickerModal` (tarjeta como `div role="button"` solo cuando hay `actions`).
- Tarjeta Estrategias en `ClientToolsModal`, destacada, con descripción “Envíos de WhatsApp programados a un grupo de clientes.” y botones “Modo simple” (ícono `Send`) y “Modo inteligente” (ícono `Sparkles`), mismos íconos que el estado vacío actual.
- `client-strategies-tool.tsx`: modal de la lista (`StrategiesView` en `ManagementToolModal` size `full`), asistente con `initialMode`, calendario de envíos post-guardado.
- `initialMode` en `CreateStrategyModalProps` y `StrategyFormProvider`.
- En `StrategiesView`: “Nueva Estrategia” → dos botones; `StrategiesEmptyState` con `onCreateSimple` / `onCreateSmart` conectados al modo que dicen.
- `track("estrategia_creada", { modo })` y fila actualizada en la spec 073.
- Spec 032: estado → “Deprecado en UI (spec 081)”, con una línea sobre lo que sigue vivo en backend.

### Fuera de alcance

- Backend de Marketing (router, servicio, cliente Meta) y sus tablas: siguen. Un DROP se decide aparte si en 90 días nadie lo pide.
- Atribución CTWA en el agente (`ctwa_attribution.py`, `core.conversation_ad_attribution`).
- Pestaña Marketing de credenciales en Admin.
- Cambios en el asistente de estrategias (pasos, validaciones, presupuesto) más allá de `initialMode`.
- Endpoints `/api/estrategias/**` y `/api/estrategia-skeleton-ideas/**`: no cambian.
- Redirigir sesiones que tenían abierta la sección `strategies` o `marketing`: la SPA no persiste la sección activa (no está en URL ni `localStorage`, y `go-to` solo maneja pedidos y listas de precio), así que al recargar arrancan en la sección por defecto.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `product-management-app` | `feat/sidebar-sin-marketing-estrategias-en-clientes` | Un PR con los dos cambios. Commits sugeridos: (a) `actions` en el picker, (b) `initialMode` + `client-strategies-tool` + tarjeta, (c) sacar Estrategias de la sidebar, (d) borrar Marketing |
| 2 | `suplai-platform` | la del PR de docs que corresponda | Este spec, estado de la 032 y fila de `estrategia_creada` en la 073 |

(c) va después de (b) en el mismo PR: en ningún commit intermedio Estrategias queda sin entrada. (d) es independiente y se puede revertir solo.

---

## Migración de base de datos

Sin migración de BD. Las tablas `marketing_*` quedan con sus datos; `estrategias` no cambia.

---

## Plan de prueba en CI/CD

El backoffice no tiene tests unitarios; el CI corre `pnpm run check:screens` y `pnpm run build`.

- `check:screens` en verde: detecta imports de componentes borrados (`MarketingView`, `components/marketing/*`) que hayan quedado en algún JSX.
- `pnpm run build` en verde: tipa `ClientToolId` extendido, `actions` opcional y `initialMode`.
- En el PR, `rg -n "components/marketing|/api/marketing|MarketingView" --glob '!node_modules'` sin resultados (pegar la salida en la descripción).
- Gap: no hay test de interacción del picker. Mínimo aceptable para el PR es la prueba humana de abajo, en particular teclado en la tarjeta con botones.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000` y backoffice `3000` (`BACKEND_URL=http://localhost:8000 npm run dev`). Tenant `demo` (3 estrategias, Meta con token). Para el estado vacío, un tenant sin estrategias y con Meta configurado.

1. Sidebar: no están Estrategias ni Marketing. Copilot sigue con el badge Beta.
2. Clientes → Herramientas: está la tarjeta Estrategias, destacada, con los botones Modo simple y Modo inteligente. Las otras seis tarjetas se ven y abren igual que antes.
3. Clic en el cuerpo de la tarjeta: abre el modal ancho con KPIs, las 3 estrategias de `demo`, Calendario Comercial y guía de ayuda. Editar, pausar/activar, calendario de envíos y ciclos funcionan como en la sección vieja. Cerrar vuelve a la tabla de clientes.
4. Botón Modo simple: abre el asistente con Modo simple elegido. Crear una estrategia puntual → se abre el calendario de envíos de la nueva.
5. Botón Modo inteligente: abre el asistente con Modo inteligente elegido, aunque la última estrategia creada haya sido simple. Un grupo dinámico no aparece como válido.
6. Dentro del asistente abierto por un botón, el toggle permite cambiar de modo.
7. En el modal de la lista, los dos botones de creación abren el modo que dicen. En el tenant vacío, las dos tarjetas del estado vacío también.
8. Teclado: Tab llega a la tarjeta Estrategias y a cada botón por separado; Enter en la tarjeta abre la lista, Enter en un botón abre el asistente.
9. Mixpanel Live View: `estrategia_creada` con `modo=simple` y con `modo=smart` para las dos creaciones de los pasos 4 y 5.
10. Admin → credenciales de un tenant: la pestaña Marketing sigue.

---

## Criterios de aceptación

### AC-1 Marketing fuera del backoffice

- **Given** cualquier tenant.
- **When** se abre el backoffice.
- **Then** no hay entrada Marketing, no existe `components/marketing/` ni `app/api/marketing/`, y el backend sigue respondiendo `/{schema}/marketing/*` (no se tocó).

### AC-2 Estrategias sin sección propia

- **Given** la sidebar.
- **Then** no hay entrada Estrategias y la sección solo se alcanza desde Clientes → Herramientas.

### AC-3 Dos entradas con el modo elegido

- **Given** Clientes → Herramientas.
- **When** se hace clic en Modo simple o en Modo inteligente.
- **Then** el asistente abre en ese modo, sin importar el último modo usado.

### AC-4 Nada se pierde de la sección vieja

- **Given** un tenant con estrategias.
- **When** se hace clic en el cuerpo de la tarjeta Estrategias.
- **Then** KPIs, lista, editar, pausar, borrar, calendario de envíos, ciclos y Calendario Comercial están y hacen lo mismo que antes.

### AC-5 El modo llega a Mixpanel

- **Given** una estrategia creada desde cualquiera de las entradas.
- **Then** `estrategia_creada` tiene `modo` igual al modo con que se guardó.
