# 092 — Directorio compartido de comercios (Suplai, PostGIS)

**Estado:** Borrador  
**Fecha:** 2026-09-30  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas sugeridas:** `feat/directorio-compartido`  
**Serie:** Prospección outbound v2 (087 a 092). Depende de la elección de proveedor de [090](./090-proveedor-directorio-outscraper.md).  
**Relaciona:** [083](./083-campana-outbound-mapas.md), [089](./089-validacion-whatsapp-previa.md) (validación de WhatsApp cacheada), [091](./091-enriquecimiento-web-prospecto.md) (enriquecimiento público).

---

## Objetivo

Cada comercio que Suplai encuentra en un directorio se guarda **una vez**, en una tabla de plataforma con ubicación en PostGIS. Cuando otra distribuidora busca el mismo tipo de comercio en la misma zona, se le da lo que ya tenemos, sin volver a pagar la búsqueda, la validación de WhatsApp ni el enriquecimiento. Solo se sale al proveedor cuando falta cobertura o el dato está viejo.

Ejemplo: una papelera de Córdoba busca librerías en Nueva Córdoba. Tres semanas después otra papelera busca librerías en una zona que se superpone. La segunda recibe las librerías de la parte ya barrida al instante y gratis, y solo se busca la parte nueva.

### Métricas de éxito

- En zonas ya barridas, la segunda búsqueda no llama al proveedor y responde en segundos.
- El costo de directorio más validación por comercio contactable baja mes a mes a medida que crece el directorio.
- Ningún dato de conversación, opt-out o resultado comercial de un tenant es visible para otro.

---

## Qué se comparte y qué no

| Dato | ¿Compartido? | Por qué |
|------|--------------|---------|
| Comercio: nombre, dirección, ubicación, tipos, teléfono, web, horarios, `verified`, rating | Sí | Es información pública del comercio, comprada una vez |
| Resultado de validación de WhatsApp (089) | Sí | Depende del teléfono, no del tenant |
| Enriquecimiento web público (091): rubro real, productos, redes | Sí | Se sacó de fuentes públicas |
| Qué zonas y tipos ya se barrieron | Sí, sin decir quién | Es lo que evita pagar dos veces |
| A qué comercio le escribió cada distribuidora | **No** | Es información comercial del tenant |
| Opt-out, respuestas, etapa del chat, decisor, pedidos | **No** | Es la relación del tenant con ese comercio |
| Que el comercio ya es cliente de una distribuidora | **No** | Es la cartera del tenant |
| ICP de cada tenant | **No** | Es estrategia del tenant |

Las tablas compartidas no tienen `schema_name` en las filas de comercios. El vínculo tenant–comercio vive solo en el schema del tenant (`campaign_prospect.place_ref`).

---

## Restricción de proveedor (términos de uso)

**Google Places no se puede usar para llenar este directorio.** Sus términos solo permiten guardar `place_id` sin límite y lat/lng por 30 días; nombre, teléfono y dirección no se pueden cachear ni reusar para otro cliente. Por eso:

- El directorio se llena con proveedores que permiten guardar los datos: Outscraper en v1 (090).
- De los datos que ya vinieron de Google Places, al directorio solo entra el `place_id`. Los datos que ya están en los schemas de los tenants (prospectos dados de alta por 071 y 083) no se copian al directorio.
- Si en algún momento se vuelve a usar Places para una búsqueda, esos resultados van solo al tenant, marcados `provider_id = google_places`, y no al directorio.

Hay que validar con asesoría legal que revender o compartir datos comprados a Outscraper entre clientes de Suplai no viole sus términos, y revisar la Ley 25.326 sobre bases de datos con teléfonos (aunque sean comerciales publicados).

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Schema | `core` (junto a `core.directory_provider`) | `public` está expuesto por la Data API de Supabase y obligaría a mantener RLS para que un tenant no lea todo. Los tenants no consultan esta tabla: la consulta el backend | Tabla en `public`; una copia por tenant |
| Ubicación | `geography(Point, 4326)` con índice GiST | Las zonas ya son `MULTIPOLYGON` 4326 en PostGIS (`{schema}.geo_zones.geometry`). `ST_Within` y distancias en metros sin reproyectar | lat/lng como `numeric` y filtro en Python |
| Identidad del comercio | Clave natural `(source, source_place_id)`; con Outscraper, `source = google_maps` y el `place_id` de Google. Único | El mismo comercio puede venir de dos proveedores que leen Google Maps; el `place_id` los une | Clave por teléfono (varios comercios comparten teléfono, y un comercio tiene varios) |
| Teléfono | Normalizado a E.164, en columna propia con índice | Es la clave para validar (089), para excluir clientes y opt-out del tenant | Solo en el jsonb crudo |
| Cobertura | Grilla fija de hexágonos en toda Argentina (`ST_HexagonGrid` en EPSG:3857, lado de unos 500 m) y una tabla de celdas × tipo × fecha de barrido | Dos zonas distintas de dos tenants caen en las mismas celdas, así que se puede saber qué ya está barrido. PostGIS 3.3 ya trae `ST_HexagonGrid`; no hace falta la extensión H3 | Guardar los polígonos de cada búsqueda y calcular intersecciones cada vez |
| Tipo de comercio en la cobertura | Clave canónica de la tabla de tipos de 071 (`book_store`, `butcher_shop`, …), no el texto de búsqueda | El texto cambia por tenant y por idioma; el tipo canónico es el mismo | Cobertura por consulta de texto |
| Vigencia | Una celda × tipo se considera barrida por 90 días. Un comercio sin ver en 180 días se marca `stale` | Los comercios abren y cierran. 90 días es un balance entre costo y frescura, a ajustar con datos | Barrer siempre; no vencer nunca |
| Flujo de búsqueda | 1) celdas de la zona; 2) las cubiertas y vigentes se leen del directorio; 3) solo las no cubiertas van al proveedor; 4) lo nuevo se escribe en el directorio; 5) se filtra por polígono y se copia al tenant | Paga solo lo que falta | Leer del directorio solo si la zona entera ya está cubierta |
| Costo del tenant | El tenant paga (en `campaign_cost_daily`) solo lo que se buscó para él. Lo reusado figura como «ahorro» con el costo evitado | El CAC de 083 tiene que reflejar lo gastado de verdad, y el ahorro es un argumento de venta | Prorratear el costo original entre tenants |
| Contacto entre tenants | **Enfriamiento de red de 30 días** (ver abajo). La clave es el teléfono, no el `place_ref` | Protege al comercio de recibir dos HSM parecidos la misma semana y, con eso, los números de todas las distribuidoras. Por teléfono cubre también prospectos que no vinieron del directorio | Sin regla; exclusividad por rubro |
| Escritura | Solo el backend, con un rol de servicio. Upsert por `(source, source_place_id)`; los campos se pisan si el dato es más nuevo | Evita que dos búsquedas simultáneas dupliquen comercios | Escritura desde el front o el agente |

### Enfriamiento de red (decidido 2026-09-30)

Si dos distribuidoras del mismo rubro reciben el mismo comercio, las dos le pueden mandar un HSM la misma semana. El comercio recibe dos mensajes parecidos de dos números distintos y es más probable que bloquee o reporte a alguno.

Regla: si **cualquier** tenant le mandó un primer mensaje outbound aceptado por Meta en los últimos 30 días, para los demás el comercio aparece como «Contactado hace poco por la red Suplai · disponible el {fecha}» y no se puede tildar hasta que pase la ventana. No se dice quién ni por qué rubro.

- La clave es el teléfono E.164. Se guarda en `core.network_first_contacts` solo `phone_e164` y `last_first_contact_at`, **sin** `schema_name` ni campaña.
- Se escribe cuando el envío del primer HSM de una campaña queda aceptado (083), venga el comercio del directorio o no.
- Un HSM de decisor (071, 084) no abre la ventana: no es un primer contacto en frío.
- Para el tenant que ya le escribió, manda su propia regla (su `campaign_prospect` y su opt-out), no la de red.
- Filtración aceptada: un tenant puede inferir que «alguien de la red» contactó a ese comercio hace poco. No sabe quién.
- 30 días es constante de v1, no un setting.

---

## Modelo de datos

```sql
-- Comercios
core.places (
  id               bigserial primary key,
  source           text not null,          -- google_maps
  source_place_id  text not null,          -- place_id de Google
  provider_id      text not null,          -- outscraper_maps (quién nos lo vendió)
  name             text not null,
  category         text,                   -- tipo principal del proveedor
  subtypes         text[],
  canonical_types  text[] not null,        -- tipos de la tabla de 071
  address          text,
  location         geography(Point, 4326) not null,
  phone_e164       text,
  website          text,
  verified         boolean,
  business_status  text,
  rating           numeric,
  reviews_count    integer,
  working_hours    jsonb,
  raw              jsonb,                  -- respuesta del proveedor, para reprocesar
  whatsapp_check   text,                   -- yes | no | unknown (089)
  whatsapp_business boolean,
  whatsapp_checked_at timestamptz,
  enrichment       jsonb,                  -- 091, solo datos públicos
  enriched_at      timestamptz,
  first_seen_at    timestamptz not null default now(),
  last_seen_at     timestamptz not null default now(),
  stale            boolean not null default false,
  unique (source, source_place_id)
);
-- índices: GiST(location), btree(phone_e164), GIN(canonical_types)

-- Cobertura de barridos
core.place_cells (
  cell_id  text primary key,               -- i,j de la grilla fija
  geom     geometry(Polygon, 4326) not null
);
core.place_coverage (
  cell_id        text references core.place_cells,
  canonical_type text not null,
  provider_id    text not null,
  searched_at    timestamptz not null,
  returned       integer not null,
  primary key (cell_id, canonical_type, provider_id)
);
```

En cada tenant:

- `{schema}.campaign_prospect.place_ref bigint` (id de `core.places`, sin FK cruzada entre schemas; se valida en el backend).
- `{schema}.campaign_cost_daily.reused_places integer` y `saved_cost numeric`.

---

## Flujo

```text
Wizard: zona + tipos (083)
  → celdas de la grilla que tocan el polígono
  → por celda × tipo: ¿cobertura vigente?
       sí → leer core.places (ST_Within zona, canonical_types && tipos, no stale)
       no → consulta al proveedor (090) → upsert en core.places → escribir cobertura
  → unir, filtrar por polígono
  → excluir clientes del tenant, opt-out del tenant
  → marcar no tildables los teléfonos en enfriamiento de red (core.network_first_contacts, 30 días)
  → validación de WhatsApp (089) solo para los que no tienen resultado vigente
  → lista del wizard
```

---

## Alcance explícito

### Incluido (v1)

- Tablas `core.places`, `core.place_cells`, `core.place_coverage` y columnas en tenants.
- Lectura del directorio antes de llamar al proveedor, por celdas.
- Escritura de todo resultado de proveedores que permiten guardarlo.
- Caché compartida de validación de WhatsApp (089) y lugar para el enriquecimiento (091).
- Costo reusado y ahorro visibles en el panel de la campaña.
- Job semanal que marca `stale`.
- Enfriamiento de red de 30 días por teléfono.

### Fuera de alcance

- Un buscador del directorio para que el tenant explore sin campaña.
- Vender o exportar el directorio fuera de Suplai.
- Copiar al directorio los datos que ya vinieron de Google Places (términos de uso).
- Exclusividad por rubro o ventanas configurables por tenant.

---

## Requisitos funcionales

- `RF-1` La búsqueda de 090 consulta primero la cobertura y el directorio.
- `RF-2` Solo las celdas × tipo sin cobertura vigente van al proveedor.
- `RF-3` Todo resultado de un proveedor con `shareable = true` se escribe en `core.places` y en la cobertura.
- `RF-4` Resultados de proveedores con `shareable = false` (Google Places) no se escriben en `core.places`.
- `RF-5` El tenant ve en el wizard cuántos comercios salieron del directorio y cuántos se buscaron nuevos, y el costo de cada parte.
- `RF-6` Ninguna respuesta de la API expone datos de otro tenant.
- `RF-7` Al quedar aceptado el primer HSM de una campaña, se hace upsert de `core.network_first_contacts` con el teléfono y la fecha. El HSM de decisor no escribe.
- `RF-8` En la lista del wizard y antes de cada envío de la cola, un teléfono con `last_first_contact_at` en los últimos 30 días, escrito por otro tenant, no se puede tildar ni enviar. Si ya estaba en la cola, se reprograma para el día en que vence la ventana.

## Requisitos no funcionales

- `RNF-1` La lectura del directorio para una zona es una sola query espacial, no una por celda.
- `RNF-2` El upsert de un lote es una sola sentencia (`INSERT … ON CONFLICT`), no uno por comercio.
- `RNF-3` Pooler 6543, `statement_cache_size=0`.
- `RNF-4` `core.places` no se expone por la Data API de Supabase.

---

## Criterios de aceptación

### `AC-1` Reuso

- **Given** el tenant A barrió librerías en una zona hace 10 días.
- **When** el tenant B busca librerías en una zona que la contiene en un 70%.
- **Then** solo se consulta al proveedor por el 30% de celdas que faltan, y B ve el ahorro.

### `AC-2` Aislamiento

- **Given** que A le escribió a un comercio y ese comercio pidió la baja.
- **When** B lo recibe del directorio.
- **Then** B no ve la baja de A ni que fue A quien le escribió. Si A le escribió hace menos de 30 días, B lo ve como «Contactado hace poco por la red Suplai» y no lo puede tildar.

### `AC-5` Enfriamiento de red

- **Given** que A le mandó el primer HSM a un comercio hace 10 días.
- **When** B lo tiene en su cola para hoy.
- **Then** no sale; queda reprogramado para dentro de 20 días. A los 30 días B lo puede contactar.

### `AC-3` Google Places no entra

- **Given** una búsqueda con `provider_id = google_places`.
- **When** termina.
- **Then** `core.places` no tiene filas nuevas.

### `AC-4` Validación compartida

- **Given** un teléfono validado para A hace 5 días.
- **When** B lo recibe.
- **Then** B no paga validación por ese teléfono.

---

## Casos borde

- `CB-1` El mismo comercio cambió de teléfono: el upsert pisa el teléfono y borra la validación de WhatsApp anterior.
- `CB-2` Comercio cerrado (`business_status` distinto de `OPERATIONAL`): se guarda, pero no se ofrece.
- `CB-3` Celda barrida con 0 resultados: igual cuenta como cubierta (no se vuelve a pagar para confirmar que no hay nada).
- `CB-4` Dos búsquedas simultáneas de la misma celda: un lock por `(cell_id, canonical_type)` durante la consulta al proveedor.

---

## Migración de base de datos

- Nuevas en `core`: `places`, `place_cells`, `place_coverage` y `network_first_contacts` (`phone_e164` PK, `last_first_contact_at timestamptz not null`, sin columna de tenant). `place_cells` se llena bajo demanda (la celda se crea la primera vez que se usa), no con un seed de todo el país.
- `core.directory_provider.shareable boolean not null default false`. `outscraper_maps = true`, `google_places = false`.
- En tenants: `campaign_prospect.place_ref`, `campaign_cost_daily.reused_places` y `saved_cost`.

**Backfill:** `network_first_contacts` se llena con los primeros HSM aceptados de los últimos 30 días de `campaign_prospect` de todos los tenants (solo teléfono y fecha máxima). Nada desde Google Places al directorio. Si antes de este spec ya se hicieron búsquedas con Outscraper (090), se pueden importar desde `core.directory_search_job` si se guardó la respuesta.

**Orden:** migración → backend (lectura y escritura del directorio dentro de la búsqueda de 090) → backoffice (ahorro en el wizard y el panel).

**Rollback:** apagar la lectura del directorio por flag; la búsqueda vuelve a ir siempre al proveedor. Las tablas quedan.

**Riesgo:** crecimiento de la tabla. Con 100.000 comercios nuevos por mes y unos 3 KB por fila con `raw`, son unos 300 MB por mes. Si pesa, `raw` se mueve a Storage.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `suplai-platform` | `feat/prospeccion-outbound-v2` | Este spec |
| 2 | `backend-supabase` | `feat/directorio-compartido` | Migración, grilla, cobertura, lectura y escritura. Se mergea después de 090 |
| 3 | `product-management-app` | `feat/directorio-compartido` | Directorio vs búsqueda nueva y ahorro en el wizard y el panel |

---

## Plan de prueba en CI/CD

- **Backend:** grilla determinística (la misma zona da las mismas celdas). Cobertura parcial solo consulta las celdas que faltan (provider fake). Upsert idempotente. `shareable = false` no escribe. Aislamiento: la respuesta para B no trae campos de tenant. `ST_Within` con polígono de fixture. Smoke de la migración con PostGIS.
- **Backoffice:** `tsc --noEmit`.

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenants `demo` y `demo_jorge` con zonas que se superponen.

1. En `demo`, buscar librerías en una zona. Anotar costo y cantidad.
2. En `demo_jorge`, buscar librerías en una zona que se superpone. El wizard dice cuántas salieron del directorio y cuánto se ahorró. El costo es solo de la parte nueva.
3. En `demo`, dar de baja un comercio. En `demo_jorge`, ese comercio aparece sin marca de baja.
4. En SQL, confirmar que `core.places` no tiene filas con `provider_id = google_places`.
5. Desde `demo`, publicar un HSM a un teléfono de prueba. En `demo_jorge`, buscar una zona que lo incluya: aparece «Contactado hace poco por la red Suplai» con la fecha de disponibilidad y no se puede tildar.
