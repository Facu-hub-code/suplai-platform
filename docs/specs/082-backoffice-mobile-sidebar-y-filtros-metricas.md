# 082 — Backoffice mobile: menú lateral para celular y filtros de Métricas en un panel

**Estado:** Implementado en `product-management-app` rama `feat/sidebar-sin-marketing-estrategias-en-clientes` (junto con la 081, sin PR todavía)  
**Fecha:** 2026-09-26  
**Repos:** `suplai-platform` (este doc), `product-management-app`  
**Rama sugerida:** `feat/backoffice-mobile-sidebar-metricas` (`product-management-app`, desde `origin/main`)  
**Relaciona:** [081](./081-backoffice-deprecar-marketing-estrategias-en-clientes.md) (deja la sidebar con 9 entradas). Layout y sidebar en [`app/page.tsx`](../../../product-management-app/app/page.tsx). Métricas en [`CommercialDashboard.tsx`](../../../product-management-app/components/commercial-dashboard/CommercialDashboard.tsx) y [`CommercialFilterBar.tsx`](../../../product-management-app/components/commercial-dashboard/CommercialFilterBar.tsx), estado en [`commercial-dashboard-context.tsx`](../../../product-management-app/contexts/commercial-dashboard-context.tsx). Panel lateral en [`components/ui/sheet.tsx`](../../../product-management-app/components/ui/sheet.tsx).

---

## Contexto

El supervisor abre el backoffice desde el celular para mirar números entre visitas. Hoy eso no funciona:

- **Sidebar.** Es un `aside` fijo de 64px (`w-16`) que se expande con `onMouseEnter`. En pantalla táctil no hay hover: se ven íconos sin nombre y el menú no se abre. El contenido tiene `ml-16` fijo, así que en 375px se pierde el 17% del ancho.
- **Header.** Título de la sección y siete controles en fila (feedback, tickets, configuración, idioma, tema, cuenta). En 375px no entran y la fila se desborda.
- **Métricas.** La barra de filtros tiene rango de fechas, cuatro `MultiSelect` de 180px, Aplicar, Reset y dos checkboxes. En mobile se apila en una columna que ocupa casi toda la primera pantalla: los KPIs, que es lo que se vino a ver, quedan debajo del pliegue.

Esta spec arranca por el marco (menú y header) y por Métricas. Las otras secciones se adaptan en specs aparte.

---

## Objetivo

1. En celular, un menú que se abre con un botón (hamburguesa) desde la izquierda, con los nombres de las secciones, y un header que entra en una fila.
2. En Métricas, en celular, los filtros pasan a un panel que se abre con un botón “Filtros”. La pantalla arranca con los KPIs.
3. En desktop no cambia nada.

### Métricas de éxito

- En 375 × 812 (iPhone 12/13/14) no hay scroll horizontal en el marco ni en la pestaña Resumen de Métricas.
- En Métricas, en 375 × 812, la primera fila de KPIs se ve sin scrollear.
- Desde cualquier sección se llega a otra en dos toques (menú → sección).
- En ≥ 768px el layout es idéntico al de hoy (misma sidebar con hover y pin, misma barra de filtros).

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Qué es “mobile” | Menos de 768px (`md` de Tailwind) | Es el corte que ya usan las grillas del backoffice (`md:grid-cols-2`) y separa celular de tablet. En tablet horizontal (≥ 768px) la sidebar de 64px entra bien. | 640px (`sm`): tablets chicas en vertical quedarían con la sidebar de hover, que tampoco sirve al tacto. |
| Cómo se detecta | Solo CSS: `md:hidden` / `hidden md:flex`. Sin hook `useIsMobile` | La SPA ya renderiza en cliente, pero un hook con `matchMedia` igual pinta un frame con el layout equivocado al montar y agrega un listener por componente. Con CSS no hay parpadeo y no hay estado que sincronizar. | `useIsMobile()` con `matchMedia`: más código, y parpadeo al rotar el teléfono. |
| Patrón del menú | Barra superior fija con botón hamburguesa + `Sheet` desde la izquierda (`side="left"`, ancho `w-72`) | Es la sidebar de siempre, abierta a pedido y con nombres. El supervisor reconoce el orden y los íconos. `Sheet` ya existe en el repo y maneja foco, Escape y overlay. | Barra de pestañas inferior: entran 4 o 5 entradas y el backoffice tiene 9; habría que decidir cuáles se esconden en “Más”. |
| Contenido del menú | Logo y nombre de la distribuidora arriba; las mismas `mainNavItems` (con el avatar de Copilot y el badge Beta); abajo Feedback, Configuración, idioma y tema. Cerrar sesión sigue en el menú de cuenta del header | Así el header del celular queda con lo mínimo. Configuración, idioma y tema se usan poco y no necesitan estar siempre a la vista. | Repetir todo el header dentro del menú: Tickets duplicado y la cuenta en dos lugares. |
| Todas las secciones en el menú | Sí, las 9. No se ocultan las que todavía no están adaptadas | Ocultar Productos o Pedidos en mobile corta flujos que hoy funcionan a medias (ver un pedido, buscar un producto). Adaptarlas es trabajo de specs siguientes. | Mostrar solo las “listas para mobile”: el supervisor no encuentra la sección y cree que no existe. |
| Cierre del menú | Se cierra al elegir una sección, al tocar el overlay, con Escape y con el botón X | Es el comportamiento esperado de un drawer. Si queda abierto después de navegar, tapa la sección que se eligió. | Mantenerlo abierto: un toque extra para ver el contenido. |
| Header en mobile | Una fila de 56px (`h-14`): hamburguesa, título de la sección (`text-lg`, truncado), Tickets con badge, menú de cuenta | Tickets es la única alerta que el supervisor tiene que ver sin abrir nada. La cuenta queda porque es donde se ve el tenant. | Dejar el header actual con `flex-wrap`: dos o tres filas que empujan el contenido. |
| Feedback en mobile | El botón de feedback pasa a un ítem del menú | Es útil, pero no cada vez que se mira una pantalla. Sacarlo del header libera el ancho del título. | Quitarlo en mobile: se pierde el canal de feedback justo donde hay más para reportar. |
| Margen del contenido | `ml-0` en mobile; `md:ml-16` / `md:ml-64` (según pin) desde 768px. Padding `px-3` en mobile | En mobile la sidebar no ocupa lugar. `px-3` suma 26px útiles contra `px-4 sm:px-6`. | Mantener `ml-16`: 64px perdidos en todas las pantallas. |
| Sidebar de desktop | Sin cambios de comportamiento (hover, pin, `localStorage`). Solo se agrega `hidden md:flex` | Esta spec no toca desktop. | — |
| Código compartido del menú | Extraer `SidebarNavList` (lista de `mainNavItems` con el ítem activo, avatar de Copilot y badge Beta) usada por el `aside` de desktop y por el `Sheet` | Hoy la lista vive inline en `page.tsx`. Duplicarla hace que la próxima sección nueva aparezca en un menú y no en el otro. | Copiar el `map` en el `Sheet`. |
| Filtros de Métricas en mobile | Botón “Filtros” (ícono `SlidersHorizontal`) con la cantidad de filtros activos, que abre un `Sheet` desde abajo | Es un pop-up, que es lo pedido. Desde abajo lo alcanza el pulgar, y muestra los campos con ancho completo. | `Dialog` centrado: con cinco campos y popovers de `MultiSelect` adentro queda apretado y el teclado lo tapa. `Popover`: no entra en 375px. |
| `Sheet` desde abajo | Agregar `side="bottom"` a `SheetContent`: `inset-x-0 bottom-0 max-h-[85vh] rounded-t-2xl border-t`, con `slide-in-from-bottom` / `slide-out-to-bottom` y `pb-[env(safe-area-inset-bottom)]` | Hoy solo hay `left` / `right`. Una variante más cuesta poco y sirve para las próximas pantallas mobile. El `safe-area` evita que la barra de gestos del iPhone tape el botón Aplicar. | Un componente `Drawer` nuevo (vaul): una dependencia más para lo mismo. |
| Contenido del panel | Los mismos campos y en el mismo orden que la barra de desktop, uno debajo del otro y con ancho completo; Aplicar y Restablecer fijos al pie del panel | Mismos filtros y mismas etiquetas: lo que el supervisor configura en la compu lo reconoce en el celular. Los botones fijos no se pierden al scrollear. | Un subconjunto de filtros en mobile: dos pantallas con resultados distintos para la misma persona. |
| Cuándo se aplican los filtros en el panel | Solo al tocar Aplicar. Se cierra el panel y se piden los datos | En desktop, el rango de fechas se aplica al elegirlo. Adentro de un panel, cada cambio dispararía una carga que no se ve porque el panel tapa la pantalla. Además, Aplicar valida el rango incompleto (`bothDatesRequired`) igual que hoy. | Aplicar cada cambio en vivo: cargas de más y ningún feedback visible. |
| Cerrar sin Aplicar | Descarta lo que se cambió: el panel vuelve a `appliedFilters` al abrirse | Si cerrar guardara los cambios a medias, la pantalla mostraría datos de un filtro y el panel otro. | Guardar el borrador al cerrar: estado ambiguo. |
| Resumen visible sin abrir el panel | Al lado del botón, el rango aplicado en texto corto (“27/08 – 26/09”). Si hay más filtros, el badge del botón suma la cantidad (vendedores, zonas, etiquetas de cliente, de producto, Prioridad 1 y Destacados cuentan 1 cada uno si están activos) | Sin esto el supervisor no sabe qué está mirando. El rango siempre está (default: últimos 30 días), por eso va en texto y no en el badge. | Chips por filtro: ocupan la misma altura que se quiere ganar. |
| Refactor de `CommercialFilterBar` | Separar los campos en `CommercialFilterFields` (`layout: "inline" | "stacked"`, recibe `value` y `onChange` del borrador). La barra de desktop y el panel mobile usan ese componente | Un solo lugar donde vive cada filtro. La barra de desktop sigue editando el estado del contexto como hoy; el panel edita un borrador local. | Dos componentes de filtros: se desalinean en el próximo filtro que se agregue. |
| Pestañas de Métricas en mobile | `TabsList` con scroll horizontal (`overflow-x-auto`, sin `w-[600px]` debajo de `md`). El botón de ayuda pasa a ser solo el ícono | Hoy son cuatro pestañas en 600px forzados; en 375px los textos se cortan. El scroll horizontal mantiene los nombres completos. | Un `Select` en lugar de pestañas: esconde que existen las otras tres. |
| Tablas de Métricas | Fuera de alcance, salvo que no rompan el ancho: el contenedor de cada tabla lleva `overflow-x-auto` | Rediseñar las tablas para mobile (tarjetas por fila) es otro trabajo. Esta spec asegura que no empujen el layout. | Ocultar columnas en mobile: decide por el usuario qué dato no necesita. |
| Analytics | Sin eventos nuevos en Mixpanel | Microsoft Clarity ya graba sesiones y distingue el dispositivo; alcanza para ver si el panel de filtros se usa. | Evento `filtros_mobile_abiertos`: no cambia ninguna decisión de producto. |

---

## Alcance explícito

### Incluido (v1)

- Barra superior de mobile (`md:hidden`) con hamburguesa, título de la sección, Tickets con badge y menú de cuenta.
- Menú en `Sheet` izquierdo con logo, `SidebarNavList`, feedback, Configuración, idioma y tema. Se cierra al navegar.
- `aside` de desktop con `hidden md:flex` y el header de desktop con `hidden md:flex`. El margen del contenido es `ml-0` en mobile.
- `SidebarNavList` extraído de `page.tsx`.
- `SheetContent` con `side="bottom"`.
- `CommercialFilterFields` (inline / stacked), `CommercialFilterBar` (desktop, `hidden md:block`) y `CommercialFiltersSheet` (mobile, `md:hidden`) con botón, badge, resumen del rango, borrador local, Aplicar y Restablecer.
- Pestañas de Métricas con scroll horizontal y botón de ayuda solo con ícono en mobile.
- Tablas de Métricas: ya scrollean de costado, porque `components/ui/table.tsx` envuelve cada tabla en `overflow-x-auto`. No requieren cambio.

### Fuera de alcance

- Adaptar a mobile las otras secciones (Clientes, Productos, Pedidos, Mapa, Conversaciones, Vendedores, Copilot, Configuración, Tickets).
- Tablas de Métricas en formato tarjeta.
- PWA, íconos de instalación o modo offline.
- Gestos (deslizar para abrir el menú).
- Cambios en desktop.
- Field app: ya es mobile-first y no se toca.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `product-management-app` | `feat/backoffice-mobile-sidebar-metricas` | Un PR. Commits sugeridos: (a) `side="bottom"` en `Sheet`; (b) `SidebarNavList` y menú mobile en `page.tsx`; (c) `CommercialFilterFields` + `CommercialFiltersSheet`; (d) pestañas y tablas de Métricas |
| 2 | `suplai-platform` | la del PR de docs que corresponda | Este spec |

(b) y (c) son independientes. Si el PR de la spec 081 todavía no está mergeado, esta rama sale de `origin/main` igual: las dos tocan `page.tsx` en zonas distintas (081 saca dos ítems de `mainNavItems`; 082 mueve la lista a `SidebarNavList`). El segundo en mergearse resuelve un conflicto chico en `mainNavItems`.

---

## Migración de base de datos

Sin migración de BD.

---

## Plan de prueba en CI/CD

El backoffice no tiene tests unitarios; el CI corre `pnpm run check:screens` y `pnpm run build`.

- `check:screens` y `build` en verde.
- `tsc` sin errores nuevos en los archivos tocados (el repo tiene errores previos en otros archivos; en el PR se filtran por path).
- Gap: no hay test visual ni de viewport. Mínimo aceptable para el PR: capturas en 375 × 812 y en 1440 × 900 de Métricas → Resumen, con el menú abierto y con el panel de filtros abierto, pegadas en la descripción del PR.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000` y backoffice `3000` (`BACKEND_URL=http://localhost:8000 npm run dev`). Tenant con datos de métricas (`benfresh`: 122 clientes en el último mes).

Chrome DevTools, modo dispositivo, iPhone 12 Pro (390 × 844) y un ancho de 360px (Android chico). Un celular real en la misma red también sirve (`http://<ip-local>:3000`). En ese caso el Mapa no carga, porque la API key de Google Maps solo acepta `localhost:3000`, pero Métricas no lo usa.

1. Menos de 768px: no hay sidebar de 64px y el contenido usa todo el ancho. En la barra superior están la hamburguesa, el título, Tickets con su badge y la cuenta, en una fila, sin scroll horizontal.
2. Hamburguesa: el menú entra desde la izquierda con los nombres de las 9 secciones, la sección activa marcada y Copilot con Beta. Abajo están Feedback, Configuración, idioma y tema.
3. Elegir Métricas en el menú: el menú se cierra y se ve Métricas. Probar también el cierre con el overlay y con Escape (teclado físico).
4. Métricas → Resumen: arriba están el botón Filtros y el rango “dd/mm – dd/mm”; la primera fila de KPIs se ve sin scrollear.
5. Filtros: el panel sube desde abajo con los mismos campos que en desktop, con ancho completo. Elegir un vendedor y una zona: los `MultiSelect` abren encima del panel y se pueden scrollear. Todavía no se recarga nada.
6. Aplicar: el panel se cierra, los datos se recargan con esos filtros y el badge muestra 2.
7. Abrir de nuevo, cambiar algo y cerrar con la X sin aplicar: al reabrir, el panel muestra los filtros aplicados, no el cambio descartado.
8. Rango incompleto: dejar solo “desde” y tocar Aplicar. Se ve el error de fechas y el panel no se cierra.
9. Restablecer: igual que en desktop, vuelve a los últimos 30 días sin filtros y cierra el panel. “Solo destacados” no se toca (tampoco lo toca el Reset de desktop).
10. Pestañas de Métricas: se deslizan de costado con los nombres completos. Vendedores, PdVs y Alarmas: las tablas scrollean de costado dentro de su caja y no empujan la página.
11. En iPhone con barra de gestos (o el simulador de Safari), el botón Aplicar no queda tapado.
12. Pasar a 1440 × 900: la sidebar de hover y el pin, el header de siempre y la barra de filtros inline funcionan igual que en `main`.

---

## Criterios de aceptación

### AC-1 Menú usable al tacto

- **Given** un ancho menor a 768px.
- **When** se toca la hamburguesa y después una sección.
- **Then** el menú muestra los nombres de las 9 secciones, navega a la elegida y se cierra.

### AC-2 Sin ancho perdido

- **Given** 375px de ancho en cualquier sección.
- **Then** el contenido arranca en el borde izquierdo (sin el margen de 64px) y el header ocupa una sola fila.

### AC-3 Filtros en un panel

- **Given** Métricas en menos de 768px.
- **When** se abre Filtros, se cambian valores y se toca Aplicar.
- **Then** los datos se recargan con esos filtros, el panel se cierra y el badge cuenta los filtros activos.

### AC-4 Cerrar no aplica

- **Given** el panel de filtros con cambios sin aplicar.
- **When** se cierra con X, overlay o Escape.
- **Then** no se recargan los datos y al reabrir se ven los filtros aplicados.

### AC-5 Desktop igual

- **Given** 768px o más.
- **Then** la sidebar, el header y la barra de filtros son los de hoy.
