---
name: enriquecer-ficha
description: >-
  Completa un alta de catálogo abierto con la ficha de Tokin y una categoría
  de Suplai. Usar cuando hay una fila abierta en core.catalogo_alta.
---

# Enriquecer ficha

Trabajás un solo producto por turno. No escribís SQL. No usás el MCP de Supabase para actualizar `productos`. No usás el MCP de Claude.

## Orden

1. `leer_faltantes` con el schema y el `product_code` del mensaje. Si `abierto` es false, parás y lo decís.
2. Seguí el campo `objetivo` al pie de la letra. En Almaro ese texto manda a buscar en Tokin por las referencias `ARC-10…`, quedarte con el `productReference` exacto y copiar nombre, descripción, marca, foto del ítem UNIDAD y el texto de las dos conversiones.
3. Si ninguna referencia coincide, `proponer_ficha` con `encontrado=false` y el resto vacío. No busques otro producto por el nombre ni en la web.
4. `listar_categorias_suplai`. Elegí un id de esa lista. Si hay hoja y padre, la hoja. Si ninguna cierra, `categoria_id` null.
5. `proponer_ficha` con la referencia, la URL, los textos copiados y el `categoria_id`. No calculés unidades por bulto. No mandes precio.

## Qué responder

La etapa que devolvió `proponer_ficha`, el `productReference` usado, y los huecos que quedaron. Si la fila ya estaba cerrada, decilo y no vuelvas a proponer.
