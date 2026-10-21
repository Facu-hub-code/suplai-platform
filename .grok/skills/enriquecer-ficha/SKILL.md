---
name: enriquecer-ficha
description: >-
  Deprecada. No usar. El alta de catálogo ya no se completa con Grok Bot
  ni con Tokin.
---

# Enriquecer ficha

Deprecada el 2026-10-21. El job no abre altas para este bot. Si te piden seguir esta skill, decí que está deprecada y no llames a las tools.

Trabajás un solo producto por turno. No escribís SQL. No usás el MCP de Supabase para actualizar `productos`. No usás el MCP de Claude.

## Orden

1. `leer_faltantes` con el schema y el `product_code` del mensaje. Si `abierto` es false, parás y lo decís.
2. Seguí el campo `objetivo` al pie de la letra. En Almaro ese texto manda a buscar en Tokin por las referencias `ARC-10…`, quedarte con el `productReference` exacto y copiar nombre, descripción, marca, foto del ítem UNIDAD y el texto de las dos conversiones.
3. Si ninguna referencia coincide, `proponer_ficha` con `encontrado=false` y el resto vacío. No busques otro producto por el nombre ni en la web.
4. `listar_categorias_suplai`. Elegí un id de esa lista. Si hay hoja y padre, la hoja. Si ninguna cierra, `categoria_id` null.
5. `proponer_ficha` con la referencia, la URL, los textos copiados y el `categoria_id`. No calculés unidades por bulto. No mandes precio.

## Qué responder

La etapa que devolvió `proponer_ficha`, el `productReference` usado, y los huecos que quedaron. Si la fila ya estaba cerrada, decilo y no vuelvas a proponer.
