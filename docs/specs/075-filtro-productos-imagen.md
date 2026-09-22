# 075 — Filtro de productos con y sin imagen

**Estado:** Borrador  
**Fecha:** 2026-09-22  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas sugeridas:** `feat/filtro-productos-imagen`

---

## Contexto

En Productos el operador ya combina dos segmentos independientes:

- Catálogo: Todos / En catálogo / Bajas (`en_catalogo`).
- Origen: Todos / En ERP / Solo Suplai (`en_erp_staging`).

No puede aislar SKUs sin foto. La salud de catálogo ya cuenta `image_url` vacío (`NULL` o solo espacios) como faltante en el listado de mantenimiento, pero ese criterio no está en la barra de filtros.

La barra de búsqueda usa `flex-1` con `min-w-[240px]` / `sm:min-w-[320px]`. Un tercer segmento necesita achicar ese mínimo para que los tres controles quepan en el mismo renglón en desktop.

---

## Objetivo

Agregar un tercer segmento **Todos / Con imagen / Sin imagen**, con la misma semántica que los otros dos: un valor activo, combinable en AND con catálogo, origen, búsqueda, categorías y tags.

### Métricas de éxito

- Con imagen devuelve solo filas con `image_url` no vacío.
- Sin imagen devuelve solo filas con `image_url` nulo o en blanco, incluidas las que el mantenimiento ya marca como faltantes.
- Todos no manda el parámetro y el total coincide con el listado actual.
- En un viewport de escritorio (~1280px) búsqueda y los tres segmentos quedan en la primera fila.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Dónde filtra | Query param en `GET /{schema}/productos` | El listado ya pagina en el servidor. Filtrar en el cliente solo vería la página actual. | Filtro en memoria sobre `products[]`. |
| Parámetro | `con_imagen`: omitido = todos, `true` = con foto, `false` = sin foto | Mismo patrón tri-estado que `en_catalogo` y `en_erp_staging`. | `image=with\|without\|all`: un literal nuevo al lado de dos booleanos. |
| Qué es “sin imagen” | `image_url IS NULL OR BTRIM(image_url) = ''` | Es la definición que ya usa el conteo `image_url_faltante` en el mismo router. Una URL que no carga igual cuenta como “con imagen”: el filtro mira el dato, no el HTTP de la foto. | Tratar solo `NULL` y dejar strings vacíos en “con imagen”. |
| Combinación | AND con el resto de filtros | Así funcionan catálogo y ERP hoy. | Un modo que reemplace a los otros segmentos. |
| UI | Tercer `Button` group, mismas clases (`h-8`, `text-xs`) | Misma affordance que la captura de Productos. | Dropdown “Más filtros”: esconde el caso de uso. |
| Ancho de búsqueda | Bajar el mínimo a ~180px / 220px en `sm` y dejar `flex-1` | El usuario pidió achicar la barra para hacer lugar. El input sigue creciendo si sobra espacio. | Segunda fila fija: desperdicia alto cuando hay lugar. |

---

## Alcance explícito

### Incluido (v1)

- Segmento Todos / Con imagen / Sin imagen en `products-table-header.tsx`.
- Estado `ImageFilter = "all" \| "with" \| "without"` en la tabla de productos, reset de página al cambiar, y query `con_imagen`.
- Proxy `app/api/productos/route.ts` reenvía el param.
- `WHERE` en `routers/productos.py`.
- Labels en español (y portugués si el archivo de i18n ya traduce los otros dos segmentos).
- El empty-state de “catálogo vacío” no debe dispararse solo porque Sin imagen da 0 resultados.

### Fuera de alcance

- Subir o generar fotos.
- Filtrar por foto rota (URL presente que no responde).
- Export, copilot y tienda: no consumen este segmento.
- Cambiar columnas de la grilla.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `backend-supabase` | `feat/filtro-productos-imagen` | Query param + test del `WHERE` |
| 2 | `product-management-app` | `feat/filtro-productos-imagen` | Segmento, proxy, labels, ancho de búsqueda |

El backoffice puede mergear después del backend. Si el proxy manda `con_imagen` antes, el backend actual lo ignora (query extra) y el filtro no aplica: no rompe el listado, pero no hay que dar por cerrado el PR de UI sin el de API.

---

## Migración de base de datos

Sin migración de BD. `productos.image_url` ya existe.

---

## Contrato

`GET /{schema}/productos`

| `con_imagen` | Efecto |
|--------------|--------|
| ausente | Sin filtro de foto |
| `true` | `image_url` con texto luego de `BTRIM` |
| `false` | `NULL` o `BTRIM` vacío |
| otro valor | 422 |

Se combina con `en_catalogo`, `en_erp_staging`, `search`, `categoria_id`, `tag_id`, `page` y `page_size`.

---

## Plan de prueba en CI/CD

- Test de API (pytest, junto a `tests/test_filtros_productos_clientes.py` o el del listado de productos): `con_imagen=true` no incluye URL en blanco; `con_imagen=false` sí; ausente no agrega el predicado; valor inválido → 422.
- Checks existentes del PR de backend y de backoffice en verde.
- No hay smoke de migración.
- El backoffice no tiene test de este header hoy. El mínimo del PR de UI es `tsc` limpio en los archivos tocados si el pipeline ya lo corre; si no, el checklist humano de abajo es el cierre.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenant con productos con y sin `image_url`.

1. Productos. Confirmar tres segmentos: Todos / Con imagen / Sin imagen, al lado de catálogo y ERP. La búsqueda se ve más corta y no empuja los segmentos a una segunda fila en desktop.
2. Sin imagen: solo filas sin foto. Anotar el total.
3. Con imagen: ninguna de esas filas. Total distinto.
4. Todos: vuelve el total anterior.
5. Sin imagen + En catálogo + Solo Suplai: la intersección es más chica o igual que cada filtro por separado.
6. Buscar por código dentro de Sin imagen: solo matchea SKUs sin foto.
7. Mobile estrecho: los segmentos pueden wrappear; siguen clickeables y el activo queda en verde.

---

## Criterios de aceptación

### AC-1 Sin imagen

- **Given** un SKU con `image_url` nulo o `""` y otro con URL.
- **When** el operador elige Sin imagen.
- **Then** solo aparece el primero y el `total` de paginación no cuenta el segundo.

### AC-2 Con imagen y combinación

- **Given** el SKU con URL está en catálogo y el de sin foto está de baja.
- **When** Con imagen + En catálogo.
- **Then** aparece el de URL. El de baja no.

### AC-3 Todos

- **Given** un listado ya filtrado por foto.
- **When** vuelve a Todos.
- **Then** la request no incluye `con_imagen` y el total coincide con el listado sin ese filtro.
