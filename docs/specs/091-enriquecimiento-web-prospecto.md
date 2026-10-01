# 091 — Tercera capa de contexto: enriquecimiento web del prospecto

**Estado:** Borrador  
**Fecha:** 2026-10-01  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `agente-conversacional-multi_tenant`, `product-management-app`  
**Ramas:** `feat/enriquecimiento-prospecto`  
**Serie:** Prospección outbound v2 (087 a 092).  
**Relaciona:** [083](./083-campana-outbound-mapas.md) (publish y variables del HSM), [084](./084-agente-prospeccion-funnel.md) (`load_facts` y prompt del grafo `prospect`), [088](./088-clientes-vs-prospectos.md) (tabla Prospectos), [090](./090-proveedor-directorio-outscraper.md), [092](./092-directorio-compartido-suplai.md).

---

## Objetivo

Hoy el agente de prospección conoce dos capas del comercio: **la ficha del directorio** (nombre, tipos, zona) y **el ICP de la campaña**. Este spec agrega una tercera: lo que se sabe del comercio **buscándolo en internet** (su web, su Instagram, sus reseñas). Con eso:

- El primer turno del agente deja de ser genérico.
- El operador ve en la tarjeta si encaja con el ICP **antes** de mandar el HSM.
- Se descarta (destildado sugerido) a los que claramente no encajan, sin gastar el HSM.
- El saludo del HSM usa un **nombre de persona** solo si hay evidencia pública; si no, una plantilla reserva sin saludo personal o, si no hay reserva, la marca en el slot. Nunca «Hola Casa de Herrería».
- En Prospectos se ve el **cuerpo interpolado** que Meta aceptó, para auditar las variables.

### Métricas de éxito

- % respuesta Suplai (083) de prospectos enriquecidos mayor que el de no enriquecidos, en la misma campaña (A/B por prospecto).
- Tiempo a decisor (084) menor en enriquecidos.
- Costo de enriquecimiento menor a US$ 0,02 por prospecto.
- 0 envíos con el nombre de Places en un slot de persona.

---

## Capas de contexto

| Capa | Fuente | Qué aporta | Hoy |
|------|--------|------------|-----|
| 1. Directorio | Outscraper o Places (090) | Nombre, tipos, dirección, teléfono, horarios, rating | Sí |
| 2. Campaña | ICP snapshot (083) | Qué le queremos vender a este tipo de lugar | Sí |
| 3. Web | Búsqueda y lectura de páginas (este spec) | Qué vende de verdad, tamaño, señales de compra, redes, nombre del responsable si es público | Este spec |

La capa 3 **no reemplaza** al ICP: le da al agente material para elegir el tramo del ICP (regla de 084) y, si hay persona pública, un saludo que no suene a directorio.

---

## Investigación: proveedores

Precios públicos a septiembre de 2026, aproximados. Verificar al contratar.

| Proveedor | Qué devuelve | Precio cada 1.000 búsquedas | Nota |
|-----------|--------------|------------------------------|------|
| Serper | Resultados de Google crudos (links y snippets) | US$ 0,30 a US$ 1 | El más barato. Hay que leer las páginas aparte |
| Brave Search | Resultados propios | US$ 5 | Índice propio, menos cobertura local |
| Tavily | Resultados más contenido limpio de la página | US$ 5 a US$ 8 (búsqueda avanzada, el doble) | Pensado para agentes. Comprado por Nebius en 2026 |
| Exa | Búsqueda semántica más contenido | US$ 7 más US$ 1 cada 1.000 páginas | Bueno para «encontrar la web de este comercio» |
| Perplexity Sonar | Respuesta armada con citas | US$ 5 a US$ 12 más tokens | Resume solo, pero es menos controlable |
| Outscraper `leads_n_contacts` | Emails, redes y teléfonos sacados de la web del comercio | US$ 3 cada 1.000 dominios | Solo si el comercio tiene web. Viene con la búsqueda de 090 |

**Costo por prospecto** con la receta de v1 (una búsqueda con Serper, lectura de hasta 2 páginas y una llamada a un modelo chico para extraer): unos US$ 0,001 de búsqueda, unos US$ 0,002 de lectura y unos US$ 0,003 del modelo. **Menos de US$ 0,01 por prospecto.**

**Cobertura esperada:** en comercios chicos de Argentina, pocos tienen web propia. Lo más común es un Instagram o un Facebook, y reseñas de Google. El nombre de persona público será la excepción; el wizard avisa si falta reserva, pero no bloquea la publicación.

**Instagram y Facebook:** no se scrapean directo. Solo snippet del buscador y bio pública indexada.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Interfaz | `WebEnrichmentProvider.enrich(place) -> Enrichment` intercambiable | El mercado de APIs de búsqueda cambia rápido | Llamar al proveedor desde el agente |
| Receta v1 | Serper «{nombre} {dirección o barrio}», hasta 2 páginas, modelo chico → esquema fijo | Más barato y controlable. Tavily si la lectura falla mucho | Perplexity (menos control); Exa (más caro) |
| Salida | Esquema fijo. Cada campo con fuente (URL) y confianza | El agente y la UI necesitan datos auditables, no un párrafo | Resumen en prosa |
| Momento | En lote, antes del envío, sobre los tildados | Sirve para destildar y para el primer turno. No se paga lo que nunca se contacta | Enriquecer al responder; enriquecer todo el directorio |
| Descarte | `icp_fit`: `fits` / `unclear` / `does_not_fit`. `does_not_fit` se destilda; el operador puede volver a tildar | La decisión es del operador | Excluir automáticamente |
| Dónde se guarda lo público | `{schema}.prospect_profiles.enrichment_summary` (092 aún no existe). `icp_fit` en `campaign_prospect` | Lo público se reusa en el tenant 180 días; el encaje depende del ICP de **esta** campaña | Esperar `core.places` (092); compartir entre tenants ahora |
| Vigencia | 180 días para el resumen público | Lo que vende un comercio cambia poco | Enriquecer cada campaña |
| Variable del HSM | Nombre de **persona** solo si pasa el clasificador. Si no: reserva sin slot de persona, o la marca en el slot. Nunca el `displayName` de Places ni `nombre_de_pila` del alta mapa | «Hola Casa de Herrería» quema el número. Meta no admite slot vacío | Texto generado («vi que venden X»); usar el nombre del local como persona |
| Slots | `nombre` / `nombre_de_pila` / `nombre_contacto` = persona. Marca e ICP como hoy. `comercio` / `negocio` / `razon_social` **no** se usan de saludo en v1 | Evita que un slot mal etiquetado mande el nombre del local | Copy «Hola {comercio}» (otro producto) |
| Plantilla reserva | Si A o B tienen slot de persona, el wizard **avisa** y sugiere `F` sin ese slot. No bloquea Publicar. Sin reserva, el slot se llena con la marca (`greeting_name_source = brand_icp`) | Publicar no puede trabarse por un HSM viejo que usa `{{nombre}}` como marca | Bloquear publicación; no enviar a los que no tienen persona |
| A/B de enriquecimiento | Mitad `on` / `off` por hash estable. El nombre en el HSM solo si `on`. La mitad `off` va por reserva si hay, si no por A/B con marca | No mezclar el experimento de capa 3 con el de copy | Enriquecer a todos y personalizar el HSM siempre |
| A/B de copy | Sigue siendo A/B. La reserva no es variante experimental: `variant` queda A o B; `template_name` es la que se mandó | El panel de 083 sigue comparando copy | Tercera variante de experimento |
| Envío en lote | El front manda **un** `POST publish` con todos los tildados. Graph sigue 1 POST por teléfono (Cloud API) | El loop 1 a 1 del browser era latencia y progreso falso | Marketing Messages batch de Meta (no aporta acá) |
| Plantilla visible | Al aceptar Meta se guardan `template_name`, `body_params`, `rendered_body`, `greeting_name_source` | El operador audita variables sin ir a Meta | Solo `template_sent_at` |
| Uso en el agente | `load_facts` suma «Lo que sabemos del comercio». Pie de conversación; no afirmar confianza baja; no citar la fuente; no decir «vi tu Instagram». El nombre público se puede usar en el primer turno aunque el HSM haya ido por reserva | Personaliza sin delatar la investigación | Pegar HTML crudo |
| Datos personales | Solo nombre y rol publicados por el comercio (web, bio). Sin teléfonos ni redes personales | Ley 25.326 | LinkedIn o redes personales |

### Clasificador de persona (`public_contact_name`)

Entra al HSM solo si **todo** esto vale:

1. `value` tiene 1 o 2 palabras, solo letras (incluye acentos), 2–20 caracteres cada una.
2. Ninguna palabra está en la lista de rubro/forma jurídica (`casa`, `almacén`, `kiosco`, `ferretería`, `srl`, `sa`, …).
3. El valor no es el nombre del comercio ni su primera palabra de directorio.
4. Hay `source` (URL).
5. Confianza `high`, o `medium` **y** rol dueño/encargado/titular/propietario.

Se manda el **nombre de pila** (primera palabra). Si no pasa: reserva (`fallback`) si hay; si no, A/B con marca (`brand_icp`).

### Esquema de salida

```json
{
  "what_they_sell": ["útiles escolares", "fotocopias", "regalería"],
  "size_hint": "small | medium | large | unknown",
  "channels": {"website": "...", "instagram": "...", "facebook": "..."},
  "public_contact_name": {"value": "Laura", "role": "dueña", "source": "https://...", "confidence": "high"},
  "buying_signals": ["arma listas escolares por encargo"],
  "not_a_fit_signals": [],
  "sources": ["https://...", "https://..."],
  "confidence": "high | medium | low"
}
```

Por tenant, además: `icp_fit`, `icp_fit_reason`, tramo del ICP que encaja, `enrichment_variant`.

---

## Alcance explícito

### Incluido (v1)

- Provider con la receta de v1 y el esquema fijo.
- Enriquecimiento en lote de los tildados, antes de publicar, con progreso en el wizard.
- `icp_fit` con destildado por defecto de `does_not_fit`.
- Cascada de saludo + plantilla reserva.
- Un solo `publish` con todos los tildados.
- Persistencia y UI del HSM interpolado en Prospectos (fuente del nombre + encaje ICP).
- Preview «así se va a ver» en el wizard después de enriquecer.
- Bloque en el prompt de `load_facts` del grafo `prospect`.
- Guardado en `prospect_profiles.enrichment_summary` + columnas de `campaign_prospect`.
- Costo en `campaign_cost_daily.enrichment_cost`.
- A/B de enriquecimiento (`on` / `off`).

### Fuera de alcance

- Scraping directo de Instagram, Facebook o Google Maps (reseñas completas).
- Enriquecer la cartera de clientes existentes.
- Usar el enriquecimiento en el agente vendedor (después del handoff).
- Texto generado en una variable HSM («vi que venden X»).
- Saludo con el nombre del comercio (`Hola Casa de Herrería` a propósito).
- `whatsapp_nombre` (089 no lo trae) ni `nombre_de_pila` del alta mapa.
- LinkedIn o redes personales.
- Directorio compartido entre tenants (092). El reuso v1 es **por tenant**.

---

## Requisitos funcionales

- `RF-1` Al confirmar la selección del wizard, `POST /{schema}/outbound-campaigns/{id}/enrich` arranca un job para los tildados sin enriquecimiento vigente (180 días en `prospect_profiles.enrichment_summary`).
- `RF-2` Cada resultado cumple el esquema. Si el modelo devuelve otra cosa, el comercio queda «sin datos» y no bloquea la publicación.
- `RF-3` `icp_fit` se calcula con el ICP snapshot. `does_not_fit` se destilda y muestra el motivo.
- `RF-4` Publicar no espera al enriquecimiento más de 5 minutos. Los que no terminaron salen sin capa 3 y por reserva (o A/B con marca si no hay reserva).
- `RF-5` `load_facts` del grafo `prospect` lee el enriquecimiento y lo pone en el prompt con la regla de uso.
- `RF-6` El costo se suma a `campaign_cost_daily.enrichment_cost`.
- `RF-7` Si A o B tienen slot de persona y no hay reserva (`F`) sin ese slot, el wizard muestra un warning. Publicar sigue habilitado.
- `RF-8` El HSM de persona solo se manda si el clasificador pasa **y** `enrichment_variant = on`.
- `RF-9` El front publica con **un** POST y el array completo de tildados.
- `RF-10` Al aceptar Meta se guardan plantilla, params y cuerpo interpolado. La tabla Prospectos los muestra.

## Requisitos no funcionales

- `RNF-1` Concurrencia acotada (10 a la vez) para no saturar al proveedor ni al modelo.
- `RNF-2` Timeout de 10 s por página leída.
- `RNF-3` API keys en config de plataforma (`SERPER_API_KEY`, modelo chico).
- `RNF-4` Logs con `campaign_id`, cantidad, % con datos y costo. Sin contenido de páginas.

---

## Criterios de aceptación

### `AC-1` Descarte sugerido

- **Given** un comercio tipo `store` cuya web muestra que es una agencia de lotería, en una campaña de papel para librerías.
- **When** se enriquece.
- **Then** queda `does_not_fit` con el motivo, destildado, y el operador lo puede volver a tildar.

### `AC-2` Primer turno personalizado

- **Given** un prospecto enriquecido con «fotocopias y útiles» y confianza alta.
- **When** responde al HSM.
- **Then** el agente menciona algo de eso en el primer turno, sin decir de dónde lo sacó y sin inventar productos que no están.

### `AC-3` Sin datos no bloquea

- **Given** un comercio sin nada en internet.
- **When** se enriquece.
- **Then** queda «sin datos», se puede publicar, y el agente trabaja como hoy. El HSM va por reserva si hay; si no, A/B con la marca en el slot de persona.

### `AC-4` Reuso en el mismo tenant

- **Given** un comercio enriquecido para **este** tenant hace 30 días.
- **When** entra en una campaña nueva.
- **Then** no se vuelve a buscar; solo se recalcula `icp_fit` con el ICP nuevo (una llamada al modelo, sin búsqueda).

### `AC-5` No «Hola Casa de Herrería»

- **Given** Places `displayName = "Casa de Herrería"` y sin persona pública, o `public_contact_name.value = "Casa"`.
- **When** se resuelve el HSM.
- **Then** no se usa ese valor en un slot de persona. Si hay reserva, se manda esa (`greeting_name_source = fallback`). Si no, A/B con la marca (`greeting_name_source = brand_icp`).

### `AC-6` Persona pública

- **Given** enriquecimiento con `public_contact_name = {value: "Laura", role: "dueña", source: "https://…", confidence: "high"}`, variant `on`, y plantilla A con slot `nombre`.
- **When** se publica.
- **Then** `{{nombre}}` = `Laura`, `greeting_name_source = person`, y Prospectos muestra el cuerpo interpolado.

### `AC-7` Publish en lote

- **Given** 8 comercios tildados.
- **When** el operador publica.
- **Then** el browser hace un solo `POST …/publish` con los 8. Graph recibe 8 POSTs desde el backend (o menos si hay cola).

### `AC-8` Plantilla visible

- **Given** un envío aceptado.
- **When** se abre Prospectos.
- **Then** «Primer mensaje» muestra el cuerpo interpolado truncado, la fecha y la fuente (`persona`, `reserva` o `marca`). El detalle muestra el texto completo.

---

## Casos borde

- `CB-1` La búsqueda devuelve otro comercio con el mismo nombre en otra ciudad: la extracción exige que la dirección o el barrio coincidan; si no, confianza baja.
- `CB-2` Página caída o con captcha: se ignora esa fuente.
- `CB-3` Cadena (sucursal de una franquicia): `size_hint = large` y señal «parte de una cadena». Suele comprar centralizado; el agente pregunta por compras centrales.
- `CB-4` El modelo intenta sacar un teléfono personal: el esquema no tiene ese campo; se descarta.
- `CB-5` A y B tienen slot de persona y no hay reserva: warning en el wizard; Publicar sigue habilitado y el slot se llena con la marca.
- `CB-6` Sin keys de Serper/modelo: el job termina «sin datos» y no bloquea.
- `CB-7` Filas viejas sin `rendered_body`: Prospectos muestra solo la fecha.

---

## Migración de base de datos

- `core.web_enrichment_provider`: `provider_id`, `price_per_search_usd`, `price_per_page_usd`, `enabled`, `source_url`, `effective_on`.
- `core.web_enrichment_job`: job del wizard (status, items jsonb, done/total, cost).
- `{schema}.campaign_prospect`: `template_name text`, `body_params jsonb`, `rendered_body text`, `greeting_name_source text` (`person` | `fallback` | `brand_icp`), `icp_fit text`, `icp_fit_reason text`, `enriched_at timestamptz`, `enrichment_variant text` (`on` | `off`).
- `{schema}.campaign_template.variant` admite `F` (reserva).
- `{schema}.campaign_cost_daily.enrichment_cost numeric not null default 0`.
- `{schema}.prospect_profiles.enrichment_summary` ya existe (088). Se le escribe el esquema público + `enriched_at` dentro del jsonb.
- Sin `ALTER` de `clients`. No se recrean `v_cartera` / `v_prospectos`.

**Seed:** Serper a US$ 0,001 por búsqueda y US$ 0,001 por página (aprox. precio público).

**Rollback:** `enabled = false` en el provider; el wizard no enriquece; publish usa solo marca/ICP o reserva; el prompt no tiene capa 3.

**Riesgo:** tenants nuevos copian columnas con `LIKE … INCLUDING ALL` del template. La migración recorre schemas activos.

---

## Orden de implementación

| # | Repo | Rama | Qué | Merge |
|---|------|------|-----|-------|
| 1 | `suplai-platform` | `feat/enriquecimiento-prospecto` | Este spec + notas en 083/088 | Primero |
| 2 | `product-management-app` | `feat/enriquecimiento-prospecto` | Publish en lote (se puede mergear solo) | Luego o junto con 4 |
| 3 | `backend-supabase` | `feat/enriquecimiento-prospecto` | Migración, persistir preview, BFF, provider, job, params por prospecto | Antes del resto de UI/agente |
| 4 | `product-management-app` | misma rama | Wizard enrich + reserva + tabla Prospectos | Después de 3 |
| 5 | `agente-conversacional-multi_tenant` | `feat/enriquecimiento-prospecto` | Bloque en `load_facts` / prompt | Después de 3 |

---

## Plan de prueba en CI/CD

- **Backend:** clasificador de persona (Laura sí; Casa de Herrería / Ferretería SRL / primera palabra de Places no). `outreach_body_params` por prospecto. Destildado `does_not_fit`. Reuso sin búsqueda. Costo sumado. Render del cuerpo. Provider fake (encaja, no encaja, sin datos).
- **Agente:** prompt con enriquecimiento incluye el bloque y la regla; sin enriquecimiento, igual al actual.
- **Backoffice:** `tsc --noEmit`.
- Gap: el juicio del modelo sobre `icp_fit` no se prueba en CI. Se mide en la prueba humana.

## Plan de prueba humana (antes del PR)

Backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`), agente local. Tenant `demo`.

1. Wizard: tildar 10 comercios, ver el progreso de enriquecimiento y los `does_not_fit` destildados con motivo.
2. Si A tiene slot de persona y no hay reserva, aparece un warning y Publicar sigue habilitado.
3. Preview «así se va a ver» en una fila con persona y en una sin.
4. Publicar: **una** request `publish` en Network. Progreso «Enviando N…».
5. Prospectos: cuerpo interpolado, fuente del nombre, encaje ICP.
6. Responder un HSM de prueba. El primer turno usa lo encontrado sin decir «vi tu web».
7. Revisar en el panel el costo de enriquecimiento.
