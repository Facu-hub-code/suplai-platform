# 107 — Conector: ocultar de a lotes incompletos, origen ERP real, y explorar liviano

**Estado:** Borrador  
**Fecha:** 2026-10-12  
**Repos:** `backend-supabase` (tools de pantallas, listado de productos, tests)  
**Rama sugerida:** `feat/mcp-explorar-ocultar`  
**Relaciona:** [095](./095-claude-mcp-carga-clientes-productos.md), [101](./101-mcp-listas-precios-promos.md) (`precios[]` y `tamano` hasta 100), [075](./075-filtro-productos-imagen.md) (`en_erp_staging`), [108](./108-agente-busqueda-por-categoria.md) (pesos que usa `probar_agente`)  
**Tenant que lo pidió:** `almaro`

---

## Objetivo

Tres huecos del conector impiden trabajar el catálogo de Almaro desde Claude.

1. `previsualizar_ocultar_producto` tira el lote entero si un código no está en `productos`, y el mensaje nombra como máximo 10. Con tope de 100 códigos por llamada, un maestro de 3.058 códigos a ocultar —de los cuales 1 existía en Suplai— no se puede procesar.
2. `explorar_productos` con `origen=en_erp` devuelve el mismo total que sin filtro, y el campo `en_erp` de un SKU cambia según el filtro. `AG299991` sale `false` sin filtro y `true` filtrando por `en_erp`.
3. Cada fila trae todas las listas de precios (Almaro tiene 17). Una página de 100 productos supera los 500 mil caracteres. No hay filtro por unidad de venta ni un modo que solo cuente o liste códigos.

### Métricas de éxito

- Un lote de 100 códigos con 1 existente y 99 inexistentes genera preview del existente y devuelve los 99 en `inexistentes`, sin recorte.
- Un lote donde ninguno existe no genera preview y lista todos los códigos. No aborta con un error que esconda la lista.
- `AG299991` tiene `en_erp: true` con `origen=todos` y con `origen=en_erp`.
- En un tenant donde un SKU no está en `erp_products_raw`, ese SKU sale `en_erp: false` y no entra en `origen=en_erp`. `origen=solo_suplai` lo incluye.
- `unidad=bulto` en Almaro cuenta los 106 productos con `caja_semantica = 'bulto'` (92 con `umv_tipo=unidad` y 14 con `umv_tipo=display`).
- `detalle=conteo` devuelve el total y `filas` vacío. `detalle=liviano` devuelve códigos sin el array `precios`. `detalle=completo` sigue trayendo las listas.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Lote incompleto | El preview guarda solo los códigos que existen. Los demás van todos en `inexistentes`. Si no queda ninguno, `preview_id` es null y no se llama a `confirmar` | Hoy `previsualizar_ocultar_producto` hace `AccionError` con `", ".join(faltan[:10])` en cuanto falta uno (`services/mcp_pantallas.py`). Un maestro grande, casi todo ausente en Suplai, no avanza. El tope de 100 se mantiene: 3.058 códigos son 31 llamadas, y cada una puede mezclar existentes e inexistentes | Rechazar el lote si falta uno. Subir el tope a 3.058 en una sola llamada: el preview y el `UPDATE` se vuelven un solo statement enorme |
| Cero existentes | Respuesta normal, mismo shape, sin `AccionError` | El modelo tiene que seguir con el próximo lote. Un error corta el turno y además hoy esconde los códigos después del décimo | `AccionError` con la lista completa. Sigue siendo un fallo de tool |
| `en_erp` de la fila | Booleano calculado por SKU: existe en `{schema}.erp_products_raw` con `sku = product_code`. `fila_producto` lee ese valor | Hoy la fila recibe `en_erp=origen == "en_erp"`. El campo copia el filtro, no el producto. Por eso `AG299991` cambia de `false` a `true` | Dejar el sello del filtro y documentarlo. El conector no puede auditar el origen |
| Total de Almaro | El `WHERE` de `en_erp_staging` ya existe en `GET /{schema}/productos` y `explorar_productos` sí lo reenvía. El 2026-10-12, los 3.302 productos de Almaro están en `erp_products_raw` (3.310 filas de staging). El total con `origen=en_erp` sigue igual al total sin filtro, y `solo_suplai` da 0. El reporte de 3.244 es el mismo fenómeno con el catálogo de ese momento | El síntoma «no filtra» en Almaro es el solapamiento total más el booleano mentiroso. Arreglar el booleano no tiene que achicar ese total | Inventar otra definición de «en ERP» (por ejemplo `en_catalogo` o un flag nuevo) para forzar un subconjunto. El backoffice ya usa `erp_products_raw` (spec 075) |
| Unidad de venta | Parámetro `unidad`: `todos` (default), `unidad`, `display`, `bulto`. Se filtra en el `WHERE` del listado, antes de paginar | `umv_tipo` solo admite `unidad` y `display`. En Almaro el bulto está en `caja_semantica = 'bulto'` con `umv_tipo` de unidad o display (`corregir_umv_bulto_y_segmento.py`). Filtrar solo `umv_tipo` dejaría `bulto` en cero | Filtrar `umv_tipo = 'bulto'`. Un filtro en memoria después de traer la página: el `total` mentiría |
| Regla de unidad | Si `caja_semantica` es `unidad`, `display` o `bulto`, manda ese valor. Si está vacía, manda `umv_tipo`. En Almaro hoy: unidad 2.120, display 1.076, bulto 106 | Es la unidad con la que se vende el SKU. Los 14 con caja bulto y `umv_tipo=display` cuentan como bulto | Exigir que caja y `umv_tipo` coincidan y dejar esos 14 afuera de los tres filtros |
| Detalle | `detalle`: `completo` (default), `liviano`, `conteo`. Liviano omite `precios`. Conteo devuelve `total` y filtros, con `filas: []` y `csv` vacío, y no ejecuta el `SELECT` de filas ni el `JSON_AGG` de precios | El peso está en las 17 listas por producto. El default completo no cambia a quien ya pide la ficha. Conteo tiene que ser una query de `COUNT`, si no el alivio es solo de la respuesta MCP | Bajar `tamano`. Sacar precios también del modo completo: rompe el caso del spec 101 |
| Dónde vive el filtro | `umv` / unidad y el booleano `en_erp` salen de `get_productos`. El conector solo los expone | `explorar_productos` no tiene `SELECT` propio (el test lo exige) y el `total` tiene que coincidir con la página | Un `SELECT` paralelo en `mcp_pantallas.py` |

### Shape de `previsualizar_ocultar_producto`

```json
{
  "preview_id": "… o null",
  "visible": false,
  "aceptados": 1,
  "rechazados": 99,
  "inexistentes": ["… los 99, sin recorte …"],
  "productos": [{ "product_code": "…", "nombre": "…", "en_catalogo": true }]
}
```

`confirmar` sigue escribiendo solo los códigos del payload del preview. Esos son los aceptados.

### Shape de unidad

| `unidad` | Condición |
|---|---|
| `todos` | Sin predicado nuevo |
| `bulto` | `lower(btrim(caja_semantica)) = 'bulto'` |
| `unidad` | caja `unidad`, o caja vacía y `umv_tipo = 'unidad'` |
| `display` | caja `display`, o caja vacía y `umv_tipo = 'display'` |

---

## Pesos de búsqueda que ve `probar_agente` (spec 108)

`probar_agente` no calcula un ranking. Hace `POST /implementation-lab/simulate-turn` y el agente corre `search_products`. Con el spec 108 desplegado, ese ensayo usa los pesos nuevos: similarity 0,35, `name_token` 0,25, penalización por token faltante 0,20 y `categoria_token` 0,15. No hay una segunda fórmula dentro de la tool: si el agente está desplegado, el laboratorio ya los toma.

`diagnosticar_busqueda` sí copia la fórmula en `services/mcp_busqueda.py`. Esa copia se actualiza en el 108, en el mismo cambio que el agente. Este spec no vuelve a escribir 0,40 / 0,30 / 0,25.

---

## Alcance

### Incluido

- Preview parcial de ocultar / mostrar, con `inexistentes` completo.
- `en_erp` por fila, con el mismo `EXISTS` que el listado del backoffice.
- `unidad` en `explorar_productos` y en `GET /{schema}/productos` (query param, para que el total pagine bien).
- `detalle` `completo` | `liviano` | `conteo`.
- Descripción de las dos tools: el lote incompleto no cancela el resto; `liviano` y `conteo` sirven para contar y para bajar códigos.
- `probar_agente` sigue llamando al agente. No se le copia una fórmula de ranking: los pesos son los del spec 108.

### Fuera de alcance

- Subir el tope de 100 códigos por llamada.
- Borrar productos. Sigue siendo `en_catalogo`.
- Pantalla de Productos del backoffice: no suma el segmento unidad ni el modo liviano. El query param queda disponible.
- Cambiar la definición de «en ERP» del backoffice.
- Ocultar los 3.058 códigos de Almaro. Este spec deja la tool usable; la corrida es operación del tenant.
- Reimplementar el score de `search_products` dentro de `probar_agente`. El ensayo usa el agente desplegado.

---

## Orden de implementación

Un solo PR de `backend-supabase`, rama `feat/mcp-explorar-ocultar` desde `origin/main`.

1. `get_productos`: booleano `en_erp` en cada fila, `WHERE` de unidad, camino de solo `COUNT` cuando el llamador pide conteo, y salto del `JSON_AGG` de precios cuando el detalle no es completo.
2. `explorar_productos` y `previsualizar_ocultar_producto`: parámetros, shape y descripciones (`pantallas_tools.py`, `descripciones.py` si la tool está ahí).
3. Tests.

El spec vive en `suplai-platform`. El plugin de Claude no agrega tools: cambian argumentos de tools que ya existen.

---

## Migración de base de datos

Sin migración de BD.

---

## Plan de prueba en CI/CD

En `backend-supabase`, junto a `tests/test_mcp_pantallas.py` y `tests/test_filtros_productos_clientes.py`:

- Lote con códigos existentes e inexistentes: el preview solo incluye los existentes y `inexistentes` trae todos, incluidos más de 10.
- Lote sin ningún código existente: `preview_id` null, lista completa, sin excepción.
- Lote vacío y lote de más de 100: siguen siendo `AccionError`.
- `fila_producto` con `en_erp` tomado de la fila. Un mock de `get_productos` que devuelve `en_erp: false` no se pisa a `true` porque `origen` sea `en_erp`.
- El `WHERE` de unidad cubre bulto por `caja_semantica` y unidad/display por caja vacía + `umv_tipo`.
- `detalle=conteo` no arma filas. `detalle=liviano` no incluye `precios`. `detalle=completo` sigue incluyendo `precios`.

Checks existentes del backend en verde. No hay migración que smokear.

---

## Plan de prueba humana

Tenant: `almaro`. Conector con permiso de carga. No hace falta el backoffice.

1. `explorar_productos` con `origen=todos`, `texto=AG299991`, `detalle=liviano`. Anotar `en_erp` y `total`.
2. La misma llamada con `origen=en_erp`. `en_erp` del SKU queda igual. El `total` de Almaro no tiene que bajar: todos los SKU están en el staging.
3. `unidad=bulto` y `detalle=conteo`. El `total` es 106 (foto del 2026-10-12; si el catálogo se movió, contrastar con `caja_semantica = 'bulto'`).
4. `unidad=unidad` y `detalle=liviano`, `tamano=100`. La respuesta trae códigos y no trae listas de precios. Cabe en el chat.
5. `previsualizar_ocultar_producto` con un código real de Almaro y varios códigos que no existen (más de 10). El preview nombra solo el real. `inexistentes` trae el resto entero. Confirmar y ver `en_catalogo=false` solo en el real. Volver a mostrarlo con `visible=true` si ese SKU tenía que seguir publicado.
