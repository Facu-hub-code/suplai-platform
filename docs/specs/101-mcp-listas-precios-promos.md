# 101 — Conector: listas nuevas, precios por lista, page size y promos

**Estado:** Borrador  
**Fecha:** 2026-10-11  
**Repos:** `backend-supabase` (tools, services, tests, recetas)  
**Rama:** `feat/mcp-listas-promos`  
**Relaciona:** [095](./095-claude-mcp-carga-clientes-productos.md) (carga), preview + `confirmar` unificado.

---

## Objetivo

El conector deja de asumir que las listas y las promos ya existen. Claude puede crear una lista (vacía o clonada), ver a qué lista está cada cliente, ver todos los precios de un producto, pedir más de 12 filas por llamada, y editar o eliminar una promo de un solo SKU.

### Métricas de éxito

- En Demo, crear “Lista Mayorista” vacía y después cargar 10 precios con `previsualizar_precios` + `confirmar`.
- Clonar una lista existente y ver en el preview cuántos precios se van a copiar antes del sí.
- `explorar_clientes` muestra `lista_precios_id` y el nombre. Un cliente sin lista sale vacío, no inventa id 1.
- `explorar_productos` lista un precio por lista, no uno solo.
- `explorar_productos` con `tamano=100` trae 100 SKUs en una llamada. 280 SKUs caben en 3 páginas.
- Editar una promo existente cambia descripción o fechas. Eliminarla la saca del listado del backoffice.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Crear lista | Tool nueva `previsualizar_lista_precios` + `confirmar` tipo `lista_precios` | `previsualizar_precios` pide un id que todavía no existe. Mezclar alta y precios en la misma tool confunde el preview. | Extender `previsualizar_precios` con `crear: true`. |
| Lista vacía vs clon | Vacía por defecto. `clonar_desde_id` opcional copia `precios_productos` en el confirm | El caso común es “lista nueva y después cargo el Excel”. El clon cubre “mayorista = copia de minorista”. | Solo vacía. Solo clon. Multiplicador automático. |
| Flags | `activa` default true, `es_publica` default false | Igual que `ListaPreciosCreate` del backoffice. Una lista nueva no se publica sola a la tienda. | Forzar pública. |
| Clientes | `explorar_clientes` y `buscar_clientes` suman `lista_precios_id` + `lista_precios` | El PDV ya trae el id. Faltaba el nombre. Sin lista: ambos vacíos. | Filtrar por lista en v1. Inventar lista 1. |
| Precios del producto | Array `precios: [{lista_id, lista, precio}]`. Se deja de devolver un solo `precio` | El listado del backoffice ya manda todas las listas. El conector tiraba la primera. | Un parámetro `lista_precios_id` que sigue mostrando una. |
| CSV de fotos | Sin cambio: `product_code`, `nombre`, `image_url` | Corregir fotos no necesita precios. Mezclarlos ensucia el CSV. | Exportar todas las columnas. |
| Page size | `tamano` 1–100, default 50, en productos y clientes | 12 filas × 280 SKUs eran ~24 roundtrips. El listado del backend acepta hasta 200. 100 es tope seguro para el chat. | Default 12. Sin tope. |
| Editar promo | `previsualizar_promocion` con `promocion_id` opcional. Sin id crea. Con id pisa. Un SKU. | Misma forma que ya usan. No suma una tool. | Tool `previsualizar_editar_promocion`. |
| Eliminar promo | `previsualizar_eliminar_promocion` + `DELETE` del servicio del backoffice | El backoffice ya borra la fila. No hay columna `activa`. Mentir un soft-delete dejaría la promo en el listado. | Poner `fecha_fin=now()`. |
| Scope de promo | Solo `single_sku`. Un `sku_group` se rechaza al editar | v1 no abre combos. El backoffice tiene otro flujo. | Editar grupos. |
| Permiso | `carga:escribir` / `carga:leer` como el resto del catálogo | No obliga a reconectar Claude. | Scope nuevo. |
| Preview | Tipos `lista_precios` y `eliminar_promocion` en `mcp_accion_previews`, 30 min. El CHECK tiene que listarlos (sql/155) | Confirmar dos veces no vuelve a crear ni a borrar. Un tipo nuevo sin migración cae en CheckViolationError. | Write directo. Dejar el CHECK viejo. |

---

## Alcance

### Incluido

- `previsualizar_lista_precios`: `nombre` obligatorio; `activa`, `es_publica`, `clonar_desde_id` opcionales. Preview dice cuántos precios copia.
- `confirmar` crea la fila en `{schema}.listas_precios` y, si hubo clon, inserta los precios.
- `explorar_clientes` y `buscar_clientes`: `lista_precios_id`, `lista_precios`.
- `explorar_productos`: `precios[]` con todas las listas.
- `tamano` en `explorar_productos` y `explorar_clientes`.
- `previsualizar_promocion` acepta `promocion_id` para editar.
- `previsualizar_eliminar_promocion(promocion_id)`.
- Recetas `precios` y `promociones`. Catálogo visible: 41 tools.

### Fuera de alcance

- Promos de varios SKUs / `sku_group`.
- Borrar o renombrar una lista.
- Multiplicar precios al clonar (×0.9).
- Cambiar `previsualizar_precios`: sigue pidiendo una lista que ya existe.
- Asignar clientes al crear la lista: sigue `previsualizar_lista_clientes`.

---

## Orden de implementación

1. Lectura: `fila_producto`, `fila_cliente`, `tamano`, `buscar_clientes`.
2. Escritura: crear lista, editar/eliminar promo, `confirmar_dispatch`.
3. Tools, superficie (41), descripciones, recetas.
4. Tests.

Un solo PR de `backend-supabase`. El spec vive en `suplai-platform`.

---

## Migración de base de datos

`sql/155_mcp_accion_previews_lista_promo.sql`: amplia `mcp_accion_previews_tipo_check` con `lista_precios` y `eliminar_promocion`. Sin eso el preview cae en `CheckViolationError` y Claude no puede crear listas ni borrar promos.

Se reutilizan `{schema}.listas_precios`, `{schema}.precios_productos` y `{schema}.promociones_semanales`. Sin columnas nuevas.

Rollback: restaurar el check de `sql/153` (sin esos dos tipos). Las listas o promos ya confirmadas no se revierten.

---

## Plan de prueba en CI/CD

- `tests/test_mcp_pantallas.py`: varios precios, `tamano` llega al listado, cliente con lista.
- `tests/test_mcp_qa_conector.py` / catalogo: preview de lista vacía y clonada; promo con `promocion_id`; eliminar; el SQL del check cubre `_HANDLERS` + `_ERP`.
- `tests/test_mcp_superficie.py`: catálogo visible = 41.
- `tests/test_mcp_olas.py`: tools nuevas registradas.
- Checks existentes verdes. Smoke: `SELECT pg_get_constraintdef` de `mcp_accion_previews_tipo_check` incluye `lista_precios` y `eliminar_promocion`.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000`. Tenant: `demo`. Claude conectado con permiso de carga.

1. `listar_catalogo` entidad `lista_precios`. Anotar un id.
2. `previsualizar_lista_precios` nombre “Lista MCP prueba”, sin clon. Confirmar. Ver el id nuevo en el listado.
3. `previsualizar_lista_precios` clonando desde la lista del paso 1. El preview dice cuántos precios. Confirmar. `explorar_productos` de un SKU muestra las dos listas.
4. `explorar_clientes` `tamano=50`: cada fila trae lista o vacío. `buscar_clientes` de un kiosco conocido muestra la misma lista.
5. `explorar_productos` `tamano=100`: una sola llamada, `paginas` baja.
6. `listar_catalogo` entidad `promocion`. Editar una de un SKU (cambiar descripción). Confirmar. Ver el cambio en el backoffice.
7. Crear una promo de prueba, `previsualizar_eliminar_promocion`, confirmar. Desaparece del listado.
8. Intentar editar un `sku_group` si hay uno: el preview se niega.
