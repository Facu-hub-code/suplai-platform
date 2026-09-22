# 079 — Vendedores: herramientas con el mismo look de Clientes, y reporte del equipo

**Estado:** Borrador  
**Fecha:** 2026-09-22  
**Repos:** `suplai-platform` (este doc), `product-management-app`, `backend-supabase`  
**Ramas sugeridas:** `feat/vendedores-herramientas-reporte`  
**Relaciona:** barra de Clientes ([`clients-table-header.tsx`](../../../product-management-app/components/clients-table/clients-table-header.tsx), [`ClientToolsModal`](../../../product-management-app/components/client-tools-modal.tsx) sobre `ManagementToolsPickerModal`). Hoy Vendedores usa un dropdown en [`VendedoresToolsMenu.tsx`](../../../product-management-app/components/vendedores/VendedoresToolsMenu.tsx) dentro de [`VendedoresUnifiedSection.tsx`](../../../product-management-app/components/vendedores/VendedoresUnifiedSection.tsx). El pin de la tarjeta “Punto de partida” es el de [078](./078-field-ruta-sugerida.md). El dato de tareas del día ya viaja en `field_hoy` del BFF ([`lib/bff-vendedores/types.ts`](../../../product-management-app/lib/bff-vendedores/types.ts)).

---

## Contexto

El supervisor de El Gigante necesita ver si el equipo hizo las tareas y los objetivos sin abrir la ficha de cada vendedor. Esa lectura es un reporte, y el lugar donde ya viven ranking, tareas, objetivos y podcast es “Herramientas”.

Ese menú hoy es un dropdown angosto. En Clientes, la misma idea es una barra (búsqueda, filtros, botón Herramientas con llave, acción primaria verde) y un modal de tarjetas. Vendedores tiene que verse igual en esa barra y en ese modal. Densidad, columnas y etiquetas de la tabla de clientes no aplican: Vendedores no es esa tabla.

---

## Objetivo

1. La sección Vendedores usa la misma barra y el mismo modal de tarjetas que Clientes.
2. Una tarjeta abre el reporte del equipo: una fecha, todos los vendedores, tareas del día y avance de objetivos.

### Métricas de éxito

- Ranking, tareas, objetivos y podcast siguen abriéndose, ahora como tarjetas.
- El reporte de un día muestra a los vendedores activos con pendientes, parciales y completadas que suman las `field_tasks` de esa fecha.
- El porcentaje de un objetivo en la fila del vendedor coincide con el de su ficha para el mismo objetivo.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Look | Reusar `ManagementToolsPickerModal` (grilla, ícono, título, descripción). Botón Herramientas `variant="outline" size="sm"` con ícono de llave, acción primaria “Nuevo vendedor” en esmeralda, misma altura de Clientes (`h-8`) | Es el patrón que el supervisor ya conoce. Un dropdown nuevo volvería a ser otro lenguaje visual. | Copiar el CSS de Clientes en un modal distinto: se desalinea en el siguiente ajuste del picker. |
| Qué no se copia | Sin densidad, sin configurador de columnas, sin filtro de etiquetas | Esas piezas son de la grilla de clientes. Vendedores sigue con el riel y las pestañas de la ficha. | Convertir Vendedores en una tabla con las 13 columnas de Clientes: rompe la ficha FIFA, que es la vista uno a uno. |
| Barra | Búsqueda (la de hoy), filtro Activos / Inactivos / Todos, Herramientas, Nuevo vendedor a la derecha | Es la fila de la captura de Clientes, con los filtros que Vendedores ya tiene. | Dejar el dropdown al lado del modal: dos entradas a lo mismo. |
| Tarjetas v1 | Ranking de tareas, Administrador de tareas, Administrador de objetivos, Podcast diario, Reporte del equipo (destacada), Punto de partida | Las cuatro primeras ya existen y solo cambian de contenedor. El reporte es la lectura de equipo. El punto de partida abre el editor de la spec 078 para el vendedor seleccionado en el riel. | Meter el reporte en el dashboard comercial: ese panel es de facturación, no de ejecución del día. |
| Reporte | Modal ancho (`ManagementToolModal` size `xl`) con fecha (default hoy, TZ del tenant) y una tabla | Se abre y se cierra sin cambiar de sección. El supervisor vuelve al riel en el mismo lugar. | Página nueva en el menú lateral: es otra navegación para un cruce de dos números que ya viven en Vendedores. |
| Objetivos en la tabla | Hasta 4 objetivos vigentes: una columna de % por objetivo. Si hay más de 4, esas columnas se reemplazan por un renglón desplegable por vendedor con la lista | El Gigante tiene 2 objetivos; 4 columnas se leen. Más de 4 aplasta el nombre del vendedor. | Una sola columna “objetivos” con texto largo: no se compara al equipo de un vistazo. |
| API | `GET /{schema}/field/equipo/reporte?fecha=YYYY-MM-DD` | Un request. El BFF actual es por vendedor (`field_hoy` de hoy nada más) y no trae objetivos del equipo. | N llamadas al dashboard de cada vendedor desde el browser: lento y fácil de dejar a medias. |
| Cálculo | En el servicio, dos agregados SQL: tareas del día por `vendedor_id`, y unidades de objetivos vigentes por vendedor con la misma regla que `FieldObjetivoService` | El % tiene que coincidir con la ficha. Recalcular con otra ventana de fechas los haría distintos. | Promediar los `pct` que ya pinta la ficha llamando al servicio en loop: N+1 sobre el pool de 60 conexiones. |
| Quién entra | Vendedores con `activo = true`. Una fila con ceros si ese día no tiene tareas | El supervisor ve al que no tiene trabajo generado, no solo al que ya sumó puntos. | Ocultar filas en cero: parece que el vendedor no existe. |
| Punto de partida | La tarjeta abre el editor de la spec 078 del vendedor seleccionado. Si no hay selección, la tarjeta pide elegir uno en el riel y no abre un alta vacía | El pin es por vendedor. Sin selección no hay fila que actualizar. | Un mapa de todos los orígenes en esta entrega: no está en el pedido. |
| Podcast | La tarjeta sigue siendo la config de voz, persona, días y horario del briefing actual | Esa pantalla ya existe. La agenda de 1–3 audios de la spec 080 la va a reemplazar cuando esté prendida; hasta entonces la tarjeta no cambia de destino. | Borrar la tarjeta en esta entrega: deja la voz sin lugar hasta que exista la 080. |

---

## Alcance explícito

### Incluido (v1)

- Barra de Vendedores alineada a la de Clientes (búsqueda, estado, Herramientas, Nuevo vendedor).
- Modal de tarjetas con las seis herramientas de la tabla de decisiones. Cada tarjeta abre el mismo diálogo que el ítem abre hoy, salvo Reporte y Punto de partida.
- Reporte: fecha, totales del equipo (tareas completadas, parciales, pendientes, puntos logrados / posibles) y tabla por vendedor.
- Columnas por vendedor: nombre, tareas completadas, parciales, pendientes, % completitud (`completadas / (completadas + parciales + pendientes)`, 0 si el denominador es 0), puntos logrados, puntos posibles, y el % de cada objetivo vigente.
- Clic en la fila selecciona ese vendedor en el riel (el detalle uno a uno sigue en las pestañas actuales).
- Endpoint nuevo y proxy BFF `/api/field/equipo/reporte`.

### Fuera de alcance

- Rediseñar la ficha, el riel o las pestañas tareas / objetivos / pedidos.
- Export CSV del reporte.
- Comparar contra otra fecha en la misma pantalla (la fecha se cambia y se vuelve a pedir).
- Torneos dentro del reporte: siguen en la tarjeta Ranking.
- La agenda del supervisor virtual (spec 080).

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `backend-supabase` | `feat/vendedores-herramientas-reporte` | `GET /{schema}/field/equipo/reporte` y tests del agregado |
| 2 | `product-management-app` | `feat/vendedores-herramientas-reporte` | Barra, modal, proxy, pantalla del reporte. El editor del pin depende del PATCH de la spec 078: si esa columna todavía no está, la tarjeta Punto de partida se muestra deshabilitada con el texto “Falta el punto de partida en el vendedor” |

La barra y las cuatro tarjetas existentes pueden mergearse con el backend del reporte en cualquier orden. El reporte en la UI espera el endpoint.

---

## Migración de base de datos

Sin migración de BD. Lee `field_tasks`, `field_objetivos` y `vendedores`. El pin es la migración de la spec 078, no de esta.

---

## Contrato

`GET /{schema}/field/equipo/reporte?fecha=2026-09-22`

```json
{
  "fecha": "2026-09-22",
  "totales": {
    "tareas_completadas": 0,
    "tareas_parciales": 0,
    "tareas_pendientes": 144,
    "pts_logrados": 0,
    "pts_posibles": 0
  },
  "objetivos": [
    { "objetivo_id": 6, "nombre": "Impulso MANAOS — Q3 2026", "meta_unidades": 500 }
  ],
  "vendedores": [
    {
      "vendedor_id": 1,
      "nombre": "Vendedor",
      "tareas_completadas": 0,
      "tareas_parciales": 0,
      "tareas_pendientes": 16,
      "pct_completitud": 0,
      "pts_logrados": 0,
      "pts_posibles": 400,
      "objetivos": [
        { "objetivo_id": 6, "unidades_logradas": 10, "meta_unidades": 500, "pct": 2.0 }
      ]
    }
  ]
}
```

`pct` con un decimal, misma fórmula que la ficha (`unidades / meta`). Objetivo vencido o todavía no vigente en `fecha` no entra. `fecha` inválida: 422.

---

## Plan de prueba en CI/CD

Pytest del servicio (schema de test o fakes del agregado, sin N+1):

- Dos vendedores, tareas en tres estados: los conteos y el % de completitud cierran.
- Vendedor activo sin tareas: fila con ceros, sí aparece.
- Vendedor inactivo: no aparece.
- Un objetivo vigente: el `pct` del vendedor usa meta y unidades de esa ventana, igual que `FieldObjetivoService`.
- Objetivo fuera de la fecha: no está en `objetivos[]`.
- `fecha` mal formada: 422.

Backoffice: `tsc` en verde. No hace falta test de layout del modal. Checks del PR en verde.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000`, backoffice `3000`. Tenant con vendedores y tareas del día (`el_gigante` sirve: 9 activos).

1. Vendedores: la barra tiene búsqueda, estado, Herramientas (llave) y Nuevo vendedor en verde, en la misma línea visual que Clientes.
2. Herramientas abre el modal de tarjetas (no un dropdown). Ranking, tareas, objetivos y podcast abren lo que abrían antes.
3. Reporte del equipo, fecha de hoy: están los activos. Completadas + parciales + pendientes de una fila coinciden con la pestaña Tareas de esa persona en el mismo día.
4. El % de un objetivo de la fila coincide con el de la ficha de ese vendedor.
5. Clic en la fila deja seleccionado a ese vendedor en el riel.
6. Cambiar la fecha a un día sin tareas: la tabla sigue mostrando a los activos, en cero.
7. Punto de partida: con un vendedor seleccionado abre el editor del pin (o el aviso de que la spec 078 todavía no está). Sin selección, no guarda nada.

---

## Criterios de aceptación

### AC-1 Mismo contenedor que Clientes

- **Given** la sección Vendedores.
- **When** se abre Herramientas.
- **Then** es el modal de tarjetas (`ManagementToolsPickerModal`), con las seis tarjetas, y el botón de la barra es el de llave.

### AC-2 El reporte cierra con las tareas del día

- **Given** tareas de esa fecha para dos vendedores activos.
- **When** se abre el reporte en esa fecha.
- **Then** cada conteo por estado es el de `field_tasks` y el total del encabezado es la suma de las filas.

### AC-3 El objetivo coincide con la ficha

- **Given** un objetivo vigente y unidades ya vendidas por un vendedor.
- **When** se mira el % en el reporte y en la ficha.
- **Then** es el mismo número.
