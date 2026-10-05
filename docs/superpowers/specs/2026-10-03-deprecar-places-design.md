# Deprecar Google Places: un solo input de mapa

**Estado:** aprobado en chat el 2026-10-03  
**Fecha:** 2026-10-03  
**Repos:** `backend-supabase`, `product-management-app`, `suplai-platform`  
**Rama:** `feat/deprecate-google-places` en los tres

## Objetivo

Dejar de buscar comercios con la API de Google Places. La única búsqueda de comercios en el mapa es la de la campaña outbound, y esa sale por Outscraper. El mapa comercial sigue mostrando clientes y zonas. El geocoding de direcciones sigue en Google.

## Criterios de aceptación

- En el mapa no hay botón ni modal de zonas blancas.
- En el mapa y en la ficha del cliente no hay “Enriquecer memoria” que llame a Nearby Search.
- El copiloto de mapas (pack `mapas`, Juan) no busca ni da de alta leads. Responde que esa función ya no está.
- Una campaña outbound busca comercios solo con Outscraper, aunque el tenant tenga `metadata.places_providers.default = google_places`.
- No queda ninguna llamada a `places.googleapis.com` ni a `maps.googleapis.com/maps/api/place/`.
- El mapa se sigue viendo y una dirección sigue geocodificándose.

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Único input de búsqueda | Panel de campaña outbound en el mapa comercial | Ya parte la zona en celdas y llama a Outscraper. Es el flujo que queremos conservar | Reescribir zonas blancas encima de Outscraper |
| Zonas blancas | Se apaga la pantalla y el endpoint | Era un segundo input, sincrónico, contra Places | Dejarlo y cambiarle el proveedor |
| Memoria “nearby” | No se piden comercios nuevos. Si `metadata.nearby` ya existe, las estrategias lo siguen leyendo | El usuario pidió deprecar el enriquecimiento, no borrar lo ya guardado | Seguir llamando a Nearby Search, o borrar el cache |
| Otros pasos de memoria | Quedan `preferred_contact`, `purchase_frequency` y `top_products` | No usan Places | Apagar todo el wizard de memoria |
| Copiloto de mapas | Las tools `zonas_list`, `territorio_resolve`, `leads_search` y `leads_create_batch` responden `deprecated`, igual que el PDF | El pack entero es el copiloto de mapas. `leads_search` es el que pega a Places | Apagar solo `leads_search` y dejar a Juan listando zonas |
| Alta interna de prospectos | `execute_leads_create_batch` sigue disponible para la campaña outbound | La campaña lo usa por código, no por el chat del copiloto | Mover esa función en este cambio |
| Proveedor `google_places` | Deja de estar habilitado. La búsqueda de campaña ignora ese override y usa Outscraper | Si no, un tenant con el override viejo volvería a Places | Borrar la fila y el historial |
| Mapa y geocoding | Siguen | Outscraper no dibuja el mapa ni convierte una dirección en coordenadas | Pasar el geocoding a Outscraper |
| Datos ya guardados | No se borran `place_id`, prospectos ni costos | El pedido fue dejar de usar la API, no purgar | Limpieza en este PR |

## Alcance explícito

Incluido:

- Sacar del backoffice el botón y el modal de zonas blancas, y los botones de enriquecer memoria de zona y de cliente que disparan Nearby Search.
- `POST /{schema}/geo-zones/{zone_id}/white-zones` responde 410.
- `POST /{schema}/clientes/enrich-memory`, el batch y el paso `nearby` de `enrich-memory/step-batch` no llaman a Google. El paso `nearby` responde que está apagado.
- `resolve_nearby_places` no llama a la red. Lee el cache si hay.
- Las cuatro tools del pack `mapas` responden deprecadas. El pack no se ofrece en el selector.
- `CampanaOutboundService.search` siempre arranca el job de Outscraper.
- `core.directory_provider`: `google_places` queda `enabled = false` e `is_default = false`. `outscraper_maps` queda como único default.

Fuera de alcance:

- Borrar el código muerto de `calculate_white_zones` más allá de dejar de invocarlo y de hacer fallar el endpoint. Se puede dejar el método sin llamarlo desde la campaña, o reducirlo a un error. No se reescribe.
- Mover `execute_leads_create_batch` fuera de `mapas_tools.py`.
- Purgar prospectos o `place_id` históricos.
- Cambiar el mapa (tiles, markers) ni el geocoding.
- Apagar `preferred_contact`, frecuencia de compra ni top de productos.

## Orden de implementación

| Orden | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `backend-supabase` | `feat/deprecate-google-places` | Apagar Places, forzar Outscraper, deprecar tools, migración de `directory_provider` |
| 2 | `product-management-app` | `feat/deprecate-google-places` | Sacar zonas blancas y botones de memoria nearby |
| 3 | `suplai-platform` | `feat/deprecate-google-places` | Este spec |

El backoffice se mergea después del backend. Si el front sale antes, los botones viejos reciben 410.

## Migración de base de datos

Archivo nuevo en `backend-supabase/sql/`, siguiente número libre después de 142.

- `UPDATE core.directory_provider SET enabled = false, is_default = false WHERE provider_id = 'google_places'`.
- `UPDATE core.directory_provider SET enabled = true, is_default = true WHERE provider_id = 'outscraper_maps'`.
- No se agregan columnas. No se tocan tablas de tenant.
- Rollback: volver a poner `google_places.enabled = true`. No alcanza para reactivar la búsqueda: el código ya no llama a Places. El rollback real es revertir el deploy.

## Plan de prueba en CI/CD

- Actualizar tests que esperan Places en la búsqueda de campaña: con provider `google_places` igual se llama al start de Outscraper.
- Test del endpoint de zonas blancas: 410.
- Test de `leads_search` (y las otras tres tools del pack): `error = deprecated`, sin HTTP a Google.
- Test de `resolve_nearby_places` / enrich nearby: no abre `places.googleapis.com` ni `place/nearbysearch`.
- `tests/test_directory_outscraper.py` sigue verde con el provider forzado.
- El backoffice no tiene runner de tests. El mínimo del PR es `tsc` sobre los archivos tocados, sabiendo que el proyecto ya tiene errores previos ajenos a este cambio.

## Plan de prueba humana

Servicios: backend en `8000`, backoffice en `3000`. Tenant `demo`.

1. Abrir el mapa. No aparece “Calcular zonas blancas” ni “Enriquecer memoria”.
2. Abrir una campaña outbound de una zona y buscar comercios. El job es de Outscraper. En los logs del backend no hay `places.googleapis.com`.
3. En Copilot, pedir “buscá kioscos en Palermo”. La respuesta dice que esa función ya no está, y no se crean prospectos.
4. El mapa sigue mostrando la zona y los clientes. Guardar una dirección de cliente sigue resolviendo lat/lng.
