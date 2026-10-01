# 090 — Proveedor de directorio: Outscraper, Google Places o scraper propio

**Estado:** Implementado en ramas `feat/directorio-outscraper`. Falta aplicar la migración 140 y cargar `OUTSCRAPER_API_KEY`  
**Fecha:** 2026-09-30 (implementación 2026-10-01)  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas sugeridas:** `feat/directorio-outscraper`  
**Serie:** Prospección outbound v2 (087 a 092). Se decide junto con [092](./092-directorio-compartido-suplai.md): el proveedor define qué datos podemos guardar.  
**Relaciona:** [071](./071-maps-icp-prospeccion-decisor.md) (búsqueda de zonas blancas), [083](./083-campana-outbound-mapas.md) (`PlaceDirectoryProvider`, precio por proveedor), [089](./089-validacion-whatsapp-previa.md).

---

## Objetivo

Encontrar **más comercios por zona**, **más baratos**, y con datos que podamos **guardar y reusar** entre distribuidoras. Hoy la búsqueda usa Google Places Text Search y cumple las tres cosas a medias.

### Métricas de éxito

- Por la misma zona y los mismos tipos, al menos el doble de comercios con teléfono que la búsqueda actual.
- Costo por comercio con teléfono al menos 50% menor que hoy.
- Los datos de la búsqueda se pueden guardar en el directorio compartido de 092 sin violar términos de uso.

---

## Diagnóstico de la búsqueda actual

Código: `calculate_white_zones` en `backend-supabase/services/geo_zones_service.py`.

- Hace **un request a `places:searchText` por cada tipo de comercio**, restringido al rectángulo (bbox) de la zona, **sin paginar**. Text Search devuelve hasta 20 resultados por página (hasta 60 con `nextPageToken`). O sea: **como máximo 20 comercios por tipo y por zona**, sin importar cuántos haya.
- La zona es un polígono, pero se busca en el rectángulo que lo contiene y después se filtra. En zonas alargadas, buena parte de los resultados cae afuera y se paga igual.
- El field mask pide `rating`, `userRatingCount`, `websiteUri`, `nationalPhoneNumber` y `photos`. Eso factura el SKU **Text Search Enterprise**: US$ 35 cada 1.000 requests (1.000 gratis por mes, bandas de descuento desde 100.000). `core.directory_provider` ya tiene US$ 0,035 por request.
- Hoy se guardan nombre, dirección y teléfono de Google en `clients` y en `campaign_prospect`.

Buena parte de «encontrar más prospectos» se arregla sin cambiar de proveedor: partir la zona en celdas y paginar. Pero eso multiplica los requests de Places, y el problema de términos (abajo) sigue.

---

## Comparación de opciones

Precios públicos a septiembre de 2026. Verificar al contratar.

| | Google Places (hoy) | Outscraper | Scraper propio |
|---|---|---|---|
| Unidad de cobro | Request (hasta 20 comercios) | Comercio devuelto | Infra, proxies y horas de desarrollo |
| Precio | US$ 35 cada 1.000 requests. 1.000 gratis por mes | 500 gratis por mes. US$ 3 cada 1.000 hasta 100.000. US$ 1 cada 1.000 después | Worker en Railway más proxies residenciales (pago por GB). Mantenimiento cuando Google cambia el HTML |
| Costo por 1.000 comercios | US$ 1,75 con páginas llenas de 20. Con celdas chicas y páginas a medio llenar, entre US$ 4 y US$ 9 | US$ 3 (US$ 1 con volumen) | Proxies alrededor de US$ 1 más infra fija y mantenimiento |
| Resultados por consulta | 20 por página, 60 con paginación | Hasta 500 por consulta | Lo que se scrollee (en la práctica unos 120 por búsqueda en el mapa) |
| Geografía | Rectángulo o círculo | Texto de ubicación o `coordinates` (`@lat,lng,zoom`). Sin polígono | Lo que se programe |
| Datos | Nombre, tipos, dirección, teléfono, web, rating | Lo mismo más horarios, `subtypes`, `business_status`, `verified` (ficha reclamada por el dueño), `owner_title`, `about`, cantidad de reseñas y fotos | Lo que se parsee |
| Enriquecimientos | No | `leads_n_contacts` (emails y redes desde la web, US$ 3 cada 1.000 dominios), `phones_enricher_service` (móvil o fijo), `whatsapp_checker`, `ai_chain_info` (cadena o independiente) | No |
| ¿Se puede guardar? | **No.** Solo `place_id` sin límite, y lat/lng por 30 días. Nombre, teléfono y dirección no se pueden cachear | Sí: somos dueños del archivo que compramos. El riesgo de scraping lo asume el proveedor | Sí, pero el riesgo de scraping es nuestro |
| Latencia | Segundos | Asíncrono, 1 a 3 minutos, con webhook | Minutos |
| Riesgo | Precio de Google y términos | Dependencia de un tercero que scrapea Google | Bloqueos, captchas, mantenimiento, términos de Google |

Otras opciones vistas y descartadas por ahora: Apify (actor de Google Maps, precio parecido a Outscraper y más armado a mano), SerpApi (cobra por búsqueda, caro para este volumen) y OpenStreetMap u Overture Maps (gratis, pero con muy pocos teléfonos de comercios en Argentina).

### ¿Cuándo convendría un scraper propio?

Supuestos: el scraper propio cuesta unos US$ 50 por mes de infra, US$ 1 cada 1.000 comercios en proxies, y dos días por mes de mantenimiento (unos US$ 400). Contra Outscraper a US$ 3 cada 1.000, el punto de equilibrio está cerca de **225.000 comercios por mes**. Por encima de 100.000 Outscraper baja a US$ 1 cada 1.000, y ahí el scraper propio no se paga nunca.

Con 40 tenants y una campaña de 1.000 a 3.000 comercios por mes cada uno, estamos entre 40.000 y 120.000 por mes. Además, el directorio compartido de 092 hace que la segunda búsqueda de la misma zona no se pague. **No conviene construir un scraper.**

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Proveedor por defecto | **Outscraper** (`outscraper_maps`) | Más resultados por consulta, más barato por comercio con teléfono, más datos, y se puede guardar en 092 | Seguir con Places y paginar; construir scraper propio |
| Google Places | Queda registrado como segundo proveedor, apagado por defecto | La interfaz de 083 ya existe. Sirve si Outscraper falla o para completar una ficha puntual por `place_id` | Borrarlo |
| Scraper propio | No se construye. Se revisa si el volumen pasa de 200.000 comercios por mes o si Outscraper sube el precio más del doble | El punto de equilibrio está muy por encima del volumen real | Construirlo ahora «para no depender» |
| Barrido de la zona | La zona se parte en celdas (grilla o H3) del tamaño de un zoom 15 a 16. Una consulta de Outscraper por celda y por tipo, con `coordinates` en el centro de la celda | Outscraper no recibe polígonos. Una consulta de ciudad entera trae comercios de afuera y se corta en 500 | Una consulta por zona con el nombre del barrio |
| Filtro por polígono | Después de traer los resultados, `ST_Within` contra el polígono de la zona, en PostGIS | Lo de afuera no se muestra. Igual se guarda en 092 porque se pagó | Mostrar todo lo que devuelve el proveedor |
| Consultas | Texto en español del tipo (`kiosco`, `librería`, `carnicería`) sacado de la tabla de tipos de 071, con `language=es-419` y `region=AR` | Outscraper busca como el sitio de Google Maps, por texto | Enviar los `includedType` de Places |
| Costo estimado | Tope = celdas × tipos × `limit` por consulta. Se muestra como «hasta US$ X». Al terminar se guarda el costo real (comercios devueltos × precio) | Outscraper cobra por comercio devuelto; antes de buscar solo se puede dar un tope | Mostrar un número exacto antes de buscar |
| Enriquecimientos | En v1 solo `phones_enricher_service` si 089 no lo cubre. `leads_n_contacts` y el resto quedan para 091 | Cada enriquecimiento cobra aparte. Hay que medir cuál paga | Prender todos |
| Asíncrono | `async=true` con `webhook` hacia el backend. Si el webhook no llega, polling a `/requests/{id}` | Las consultas tardan minutos; no se puede tener el request del wizard abierto | `async=false` |
| Precio | En `core.directory_provider`: `price_unit = place`, `price_usd = 0,003` | 083 asumía precio por request. Outscraper cobra por comercio | Precio fijo en código |

### Decisiones de implementación (2026-10-01)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Un pedido por celda | Cada celda es un `POST /google-maps-search` con todos los tipos como `query` y `coordinates = "lat,lng"` del centro | Outscraper acepta una sola coordenada por pedido. Así una zona de 12 celdas son 12 pedidos | Un pedido por celda y por tipo (más pedidos, mismo costo) |
| Celdas | Grilla de 1 km sobre el rectángulo. Solo se piden las celdas cuyo cuadrado toca el polígono (`ST_Intersects` en PostGIS) | Sin dependencias nuevas (no H3 ni Shapely). Las celdas de afuera no se pagan | H3 |
| `limit` por consulta | 100 (`organizationsPerQueryLimit`) | Un kiosco de barrio no tiene más de 100 iguales por km². Mantiene el tope de costo bajo | 400 o 500 |
| Interfaz | `DirectoryProvider` (`submit`, `fetch`) en `services/directory_outscraper.py`, con `OutscraperProvider` y `FakeOutscraper` | El `PlaceDirectoryProvider` de 083 nunca llegó al código: Places se llama directo desde `calculate_white_zones` | Refactorizar Places detrás de la interfaz en este PR |
| Resultados guardados en el job | Al terminar cada pedido, los comercios se copian a `core.directory_search_job.collected` | Outscraper guarda los resultados solo 2 horas. Además, los campos extra quedan para 092 | Volver a pedirlos a Outscraper |
| Quién avanza el job | El polling del wizard (cada 4 s, `GET .../search/{job_id}`) y el webhook. El cierre es un `UPDATE … WHERE status = 'running'` | Sin worker nuevo. El que llega primero cierra y cobra una sola vez | Worker en el scheduler |
| Webhook | `POST /directory/outscraper/webhook/{OUTSCRAPER_WEBHOOK_SECRET}`. Se manda solo si están el secreto y `PUBLIC_BACKEND_URL` | RNF-3. Sin secreto, alcanza con el polling | Firma HMAC (Outscraper no firma) |
| Proveedor default | `core.directory_provider.is_default` (único). Override por tenant en `metadata.places_providers.default`, si el proveedor está `enabled` | Rollback de plataforma con un `UPDATE`, sin deploy | Default en código |
| Sin key | Outscraper es default para todos ya. Sin `OUTSCRAPER_API_KEY`, la búsqueda devuelve 409 `DIRECTORY_PROVIDER_UNAVAILABLE` con mensaje accionable | Decisión del usuario. Igual que RF-6: no se cae a Places | Dejar Places como default hasta tener key |
| Cantidad de resultados | Outscraper sin el tope de 40 de Places: hasta 2.000 prospectos por búsqueda | 2.000 es el máximo que valida 089. El copiloto de mapas y Places siguen con 40 | Mantener 40 |
| Cobro | `places_cost` se suma al terminar: comercios devueltos × precio. Antes de buscar solo hay tope | Outscraper cobra por comercio devuelto, no por pedido | Cobrar el tope por adelantado |
| Teléfono | Normalizado a E.164 con +54 en el parser (`normalize_phone_ar`) | CB-4. 089 valida E.164 | Normalizar en 089 |
| Enriquecimientos | Ninguno en v1 | 089 ya valida WhatsApp; `phones_enricher` no hace falta | Prender `phones_enricher_service` |
| Mapa de zonas blancas | Sigue con Places, sincrónico, sin cambios | Es otra pantalla y otro flujo; no hace falta tocarla en v1 | Pasarla a Outscraper |

---

## Alcance explícito

### Incluido (v1)

- Implementación `outscraper_maps` de `PlaceDirectoryProvider`.
- Barrido por celdas de la zona, dedupe por `place_id` y filtro por polígono.
- Soporte de precio por comercio en `core.directory_provider`, además de por request.
- Webhook de fin de tarea y polling de respaldo.
- Campos extra guardados: horarios, `subtypes`, `verified`, `business_status`, web, rating y reseñas.
- Excluir `business_status` distinto de `OPERATIONAL`.
- Prueba comparativa (ver plan de prueba humana) antes de apagar Places como default.

### Fuera de alcance

- El scraper propio.
- Enriquecimiento web (091).
- Guardar en el directorio compartido (092). Este spec deja los datos listos para eso.
- Borrar lo que ya se guardó de Google Places. Se trata en 092.

---

## Requisitos funcionales

- `RF-1` `estimate(zone, types)` devuelve la cantidad de celdas, las consultas y el tope de costo, sin llamar al proveedor.
- `RF-2` `search(zone, types)` crea una tarea asíncrona y devuelve un `job_id`. El wizard muestra el progreso.
- `RF-3` Al terminar: dedupe por `place_id`, filtro por polígono, exclusión de clientes actuales, opt-out y comercios cerrados. Después pasa a la validación de 089.
- `RF-4` El costo real se guarda en `campaign_cost_daily.places_cost` con el precio del momento.
- `RF-5` El proveedor activo del tenant sale de config (`metadata.places_providers.default`), con `outscraper_maps` por defecto.
- `RF-6` Si Outscraper devuelve 402 (sin saldo) o falla la tarea, el wizard muestra el error y ofrece reintentar. No cae automáticamente a Places: cambiar de proveedor cambia el costo y lo decide una persona.

## Requisitos no funcionales

- `RNF-1` La API key de Outscraper vive en config de plataforma. Nunca en el front.
- `RNF-2` Las consultas de un barrido van en lotes: todos los tipos de una celda en un pedido (Outscraper acepta hasta 250 consultas, pero una sola coordenada por pedido).
- `RNF-3` El webhook de Outscraper se valida con un secreto en la URL.
- `RNF-4` Logs con `zone_id`, `provider_id`, celdas, consultas, devueltos, dentro del polígono y costo.

---

## Criterios de aceptación

### `AC-1` Más comercios que hoy

- **Given** una zona de prueba y tres tipos.
- **When** se busca con Outscraper y con la búsqueda actual de Places.
- **Then** Outscraper trae al menos el doble de comercios con teléfono dentro del polígono.

### `AC-2` Tope de costo

- **Given** una zona de 12 celdas, 3 tipos y `limit` 100.
- **When** se estima.
- **Then** se muestra «hasta US$ 10,80» (12 × 3 × 100 × 0,003) y no hay llamada al proveedor.

### `AC-3` Polígono

- **Given** resultados de una celda que cae en el borde.
- **When** termina la búsqueda.
- **Then** solo se listan los comercios dentro del polígono.

### `AC-4` Sin saldo

- **Given** Outscraper responde 402.
- **When** se busca.
- **Then** el wizard lo dice y no se busca con Places por detrás.

---

## Casos borde

- `CB-1` Zona muy grande (más de 200 celdas): se pide confirmar y se muestra el tope de costo en grande.
- `CB-2` Comercio con varias categorías: se guarda `subtypes` entero; el tipo principal es `category`.
- `CB-3` Mismo comercio en dos celdas: el dedupe por `place_id` lo deja una vez, y se cobra una vez si se usa `dropDuplicates`.
- `CB-4` Teléfono con formato local: se normaliza a E.164 con prefijo de Argentina antes de 089.

---

## Migración de base de datos

Archivo: `backend-supabase/sql/140_directory_outscraper.sql`. Solo toca `core`; no hay cambios por tenant.

- `core.directory_provider`: columnas `price_unit` text (`request` | `place`, default `request`), `enabled` boolean (default `true`) e `is_default` boolean (default `false`), con índice único parcial para que haya un solo default. Seed de `outscraper_maps`: US$ 0,003 por comercio, `price_unit = place`, `enabled = true`, `is_default = true`. `google_places` queda `enabled = true` y `is_default = false`.
- `core.directory_search_job`: `id`, `schema_name`, `zone_id`, `campaign_id`, `provider_id`, `provider_request_ids text[]`, `status` (`running` | `done` | `failed` | `timeout`), `cells`, `queries`, `query_limit`, `returned`, `inside_polygon`, `price_usd`, `cost_usd`, `collected jsonb`, `results jsonb`, `error`, `last_polled_at`, `webhook_at`, `created_at`, `finished_at`. Índices por `(schema_name, campaign_id, created_at)` y GIN en `provider_request_ids` para el webhook.
- `{schema}.campaign_prospect`: sin columnas nuevas. `provider_id = outscraper_maps` y `provider_place_id` es el `place_id` de Google que devuelve Outscraper, que sirve para dedupe con los datos viejos.

**Orden:** aplicar la 140 antes del deploy del backend. Sin la 140, el backend nuevo falla al crear campañas (lee `enabled` e `is_default`).

**Rollback:** `UPDATE core.directory_provider SET is_default = (provider_id = 'google_places')`. Las campañas nuevas vuelven a Places sin deploy. Las tablas nuevas se pueden dejar.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `backend-supabase` | `feat/directorio-outscraper` | Migración 140, provider, barrido, job, webhook, precio por comercio |
| 2 | `product-management-app` | `feat/directorio-outscraper` | Progreso asíncrono, tope de costo, confirmación de zona grande, reintentar |
| 3 | `suplai-platform` | `feat/directorio-outscraper` | Este spec |

Deploy: migración 140 → variables `OUTSCRAPER_API_KEY` y `OUTSCRAPER_WEBHOOK_SECRET` en Railway → backend → backoffice. 089 ya está en producción.

---

## Plan de prueba en CI/CD

- **Backend** (`tests/test_directory_outscraper.py`, con `FakeOutscraper` y el store del job en memoria):
  - grilla de una zona de 3 × 4 km da 12 celdas; parser de la respuesta guardada de Outscraper; normalización de teléfonos;
  - dedupe y exclusión de cerrados; tope de AC-2 (US$ 10,80) sin llamar al proveedor;
  - flujo completo: polígono, clientes actuales, opt-out, costo real cobrado una vez;
  - 402 y falta de key dan `DIRECTORY_PROVIDER_UNAVAILABLE` sin fallback; zona de más de 200 celdas pide confirmación; timeout; doble cierre no cobra dos veces;
  - secreto y URL del webhook; elección del proveedor (plataforma, override del tenant, proveedor apagado); campaña Outscraper no llama a Places.
- Suite completa: 1805 passed; la única falla es previa (`test_admin_lab_endpoints`).
- **Backoffice:** `tsc --noEmit` sin errores nuevos (91 previos).
- Gap: Outscraper real, el SQL de celdas (`ST_Intersects`) y el filtro por polígono no corren en CI. Se cubren en la prueba humana.

## Plan de prueba humana (antes del PR)

**Prueba comparativa (antes de escribir código).** Con la cuenta gratuita de Outscraper (500 comercios por mes):

1. Elegir dos zonas reales de un tenant (una densa y una de barrio) y dos tipos del ICP de una campaña que ya corrió.
2. Correr la búsqueda actual (Places) y anotar comercios dentro del polígono, con teléfono, y el costo.
3. Correr Outscraper desde su web con consultas por barrio y los mismos tipos. Anotar lo mismo.
4. Cruzar por `place_id`: cuántos trae uno y no el otro, y cuántos teléfonos coinciden.
5. Si Outscraper no trae al menos el doble con teléfono, o si el costo por comercio con teléfono no baja, parar y revisar la decisión.

**Después de implementar:** migración 140 aplicada, backend `8000` con `OUTSCRAPER_API_KEY` (cuenta gratuita alcanza para una zona chica), backoffice `3000` (`BACKEND_URL=http://localhost:8000`), tenant `demo` con una zona de barrio. En local no hay webhook (Outscraper no llega a localhost): avanza el polling.

1. Sin key: el wizard, al confirmar la búsqueda, dice que falta la API key de Outscraper y no busca con Places.
2. Con key: en el paso 2 se ve «hasta US$ X» con celdas y consultas. En la base, no hay pedidos a Outscraper todavía.
3. Confirmar búsqueda: se ve «Buscando comercios en N celdas… k de N listas» y al terminar la lista, con «Costo real» menor o igual al tope.
4. Abrir los comercios en el mapa: ninguno fuera del polígono, ninguno que ya sea cliente.
5. `core.directory_search_job` del job: `status = done`, `returned`, `inside_polygon`, `cost_usd`; y `campaign_cost_daily.places_cost` sumó ese costo una sola vez.
6. Zona grande (más de 200 celdas): el botón queda deshabilitado hasta tildar la confirmación.
7. Rollback: `UPDATE core.directory_provider SET is_default = (provider_id = 'google_places')` y una campaña nueva vuelve a buscar con Places.
