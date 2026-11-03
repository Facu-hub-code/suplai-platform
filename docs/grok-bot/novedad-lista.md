# Novedad lista para el agente

**Issue:** DEV-209 · **Proyecto:** Grok Bot · Novedades listas para el agente (P-DEV-13)
**Tenants:** `dimer` (Odoo), `almaro` y `gonzales` (GEV, Arcor).

Es la definición que usan el vigía para detectar y el catálogo para completar. La consulta vive en la skill [`suplai-vigia-novedades`](../../.grok/skills/suplai-vigia-novedades/SKILL.md).

---

## Qué es una novedad

Un producto de `{schema}.productos` con `is_mock` falso y `created_at` posterior a la última corrida del vigía. En la primera corrida se toman los últimos 7 días.

- Entran por el sync del ERP: Odoo en dimer y GEV en almaro y gonzales. En gonzales también entran los **combos de GEV**: `nombre` empieza con `COMBO` y la descripción, con `Combo GEV [`.
- Las que tienen `en_catalogo` falso se informan aparte y no se trabajan: el agente no las ofrece.

## Cuándo está lista

| Campo | Regla | Dónde vive |
|---|---|---|
| En catálogo | `en_catalogo` verdadero y sin `motivo_baja` | `productos` |
| Stock | `stock > 0` | `productos` |
| Precio | `precio_unidad > 0` en al menos una lista con `activa` verdadero | `precios_productos` + `listas_precios` |
| Foto | `image_url` no vacía | `productos` |
| Descripción | 20 caracteres o más, distinta del nombre y sin el texto crudo del ERP (`Combo GEV [`) | `productos.descripcion` |
| Alias | Al menos uno | `productos_aliases` |
| Categoría | Al menos una | `product_categories` |
| Embedding al día | Un chunk `producto` del código cuyo `content` incluye la descripción actual | `documents` (`metadata->>'product_code'`, `metadata->>'chunk' = 'producto'`) |

Stock y precio los trae el ERP: si faltan, el bot **no** los inventa. Los reporta como bloqueo del ERP.

## Cómo se re-vectoriza

- `{schema}.productos` no tiene triggers: un `UPDATE` directo de la descripción o los alias **no** actualiza el embedding.
- El embedding lo arma el backend con `vectorizar_productos` → `upsert_documento_producto`. Se dispara por `POST /{schema}/productos/vectorize` con la lista de códigos en el body (`backend-supabase/routers/productos.py`), o solo al confirmar un borrador del MCP de Suplai.
- Los bots escriben con SQL (decidido en DEV-208), así que igual necesitan esa llamada al backend después de cada lote.

## Línea base (2026-11-03, últimos 30 días)

| Tenant | Nuevos | En catálogo | Stock | Precio | Foto | Descripción | Alias | Categoría | Embedding | **Listos** |
|---|---|---|---|---|---|---|---|---|---|---|
| almaro | 161 | 109 | 99 | 109 | 105 | 109 | 57 | 66 | 94 | **56** |
| gonzales | 453 | 197 | 170 | 197 | 0 | 197* | 0 | 0 | 0 | **0** |
| dimer | 18 | 9 | 7 | 9 | 0 | 6 | 9 | 0 | 9 | **0** |

\* Esta línea base contó las descripciones `Combo GEV [...]` como válidas. Con la regla de arriba, los 133 combos quedan sin descripción.

**Lo que dice:**
- **gonzales:** entraron 453 productos de GEV el 15, el 24 y el 29/10, entre ellos 133 combos. Ninguno de los 197 en catálogo tiene embedding, alias, categoría ni foto: **el agente no los puede encontrar.** Es el caso más urgente.
- **almaro:** la mitad está lista. Faltan sobre todo alias (52) y categoría (43), y 15 embeddings quedaron viejos después de cambiar la descripción.
- **dimer:** entra poco (18 en un mes). Le falta foto y categoría a todo, y 3 descripciones.

Las fotos de almaro y gonzales hoy vienen de `tokin.vtexassets.com` y `arcorencasa.com` (URLs externas). Las de dimer están en el Storage de Supabase.
