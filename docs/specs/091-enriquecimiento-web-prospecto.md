# 091 — Tercera capa de contexto: enriquecimiento web del prospecto

**Estado:** Borrador  
**Fecha:** 2026-09-30  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `agente-conversacional-multi_tenant`, `product-management-app`  
**Ramas sugeridas:** `feat/enriquecimiento-prospecto`  
**Serie:** Prospección outbound v2 (087 a 092).  
**Relaciona:** [084](./084-agente-prospeccion-funnel.md) (`load_facts` y prompt del grafo `prospect`), [090](./090-proveedor-directorio-outscraper.md) (datos del directorio), [092](./092-directorio-compartido-suplai.md) (dónde se guarda lo público).

---

## Objetivo

Hoy el agente de prospección conoce dos capas del comercio: **la ficha del directorio** (nombre, tipos, zona) y **el ICP de la campaña**. Este spec agrega una tercera: lo que se sabe del comercio **buscándolo en internet** (su web, su Instagram, sus reseñas). Con eso:

- El primer turno del agente deja de ser genérico («vi que venden útiles escolares y fotocopias; ¿con quién hablo por el papel?»).
- El operador ve en la tarjeta del prospecto si encaja con el ICP antes de mandarle nada.
- Se puede descartar antes del envío a los que claramente no encajan (un «kiosco» que en realidad es una agencia de lotería), sin gastar el HSM ni exponer el número.

### Métricas de éxito

- % respuesta Suplai (083) de prospectos enriquecidos mayor que el de no enriquecidos, en la misma campaña (A/B por prospecto).
- Tiempo a decisor (084) menor en enriquecidos.
- Costo de enriquecimiento menor a US$ 0,02 por prospecto.

---

## Capas de contexto

| Capa | Fuente | Qué aporta | Hoy |
|------|--------|------------|-----|
| 1. Directorio | Outscraper o Places (090) | Nombre, tipos, dirección, teléfono, horarios, rating | Sí |
| 2. Campaña | ICP snapshot (083) | Qué le queremos vender a este tipo de lugar | Sí |
| 3. Web | Búsqueda y lectura de páginas (este spec) | Qué vende de verdad, tamaño, señales de compra, redes, nombre del responsable si es público | No |

La capa 3 **no reemplaza** al ICP: le da al agente material para elegir el tramo del ICP que corresponde (regla de 084) y para abrir la conversación con algo concreto.

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

**Costo por prospecto** con la receta de v1 (una búsqueda con Serper, lectura de hasta 2 páginas y una llamada a un modelo chico para extraer): unos US$ 0,001 de búsqueda, unos US$ 0,002 de lectura y unos US$ 0,003 del modelo. **Menos de US$ 0,01 por prospecto.** Con Tavily en vez de Serper y lectura, unos US$ 0,012.

**Cobertura esperada:** en comercios chicos de Argentina, pocos tienen web propia. Lo más común es un Instagram o un Facebook, y reseñas de Google. Hay que medir qué % de prospectos devuelve algo útil antes de decidir el proveedor (ver plan de prueba).

**Instagram y Facebook:** no se scrapean directo (términos de Meta y bloqueos). Solo se usa lo que aparece en el snippet del buscador y en la bio pública indexada.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Interfaz | `WebEnrichmentProvider.enrich(place) -> Enrichment` con implementación intercambiable | El mercado de APIs de búsqueda cambia rápido (precios, compras) | Llamar a un proveedor desde el agente |
| Receta v1 | Buscador barato (Serper) con la consulta «{nombre} {dirección o barrio}», lectura de la web propia si existe y de hasta 2 resultados, y extracción con un modelo chico a un esquema fijo | Es la opción más barata y controlable. Tavily queda como alternativa si la lectura de páginas da muchos errores | Perplexity (respuesta armada, menos control); Exa (más caro para este caso) |
| Salida | Esquema fijo, no texto libre (ver abajo). Cada campo con su fuente (URL) y confianza | El agente y la UI necesitan datos, no un párrafo. La fuente permite auditar | Resumen en prosa |
| Momento | **En lote, antes del envío**, para los comercios que el operador tildó en el wizard | Sirve para descartar antes de gastar el HSM, y el primer turno ya lo tiene. Bajo demanda sumaría latencia al primer mensaje | Enriquecer cuando responde; enriquecer todo lo que devuelve el directorio (se paga lo que nunca se contacta) |
| Descarte | El enriquecimiento da `icp_fit`: `fits`, `unclear` o `does_not_fit`, con motivo. `does_not_fit` se destilda por defecto y el operador lo puede volver a tildar | La decisión la toma el operador; el modelo propone | Excluir automáticamente |
| Qué se comparte | Datos del comercio (qué vende, redes, tamaño, horarios) van a `core.places.enrichment` (092). `icp_fit` es del tenant, porque depende de su ICP | Lo público se paga una vez; el encaje con el ICP es estrategia del tenant | Todo compartido; todo por tenant |
| Vigencia | 180 días para lo compartido | Lo que vende un comercio cambia poco | Enriquecer cada campaña |
| Uso en el agente | `load_facts` del grafo `prospect` suma un bloque «Lo que sabemos del comercio» con los campos y la regla: usar como pie de conversación, no afirmar lo que tiene confianza baja, no citar la fuente | Personaliza sin inventar. Decir «vi tu Instagram» puede incomodar | Pegar el texto crudo de las páginas en el prompt |
| Variable del HSM | No en v1 | Las plantillas se aprueban con variables fijas (083); meter texto generado en una variable arriesga rechazos y calidad | Poner «vi que venden X» en la plantilla |
| Datos personales | Solo nombre y rol del responsable si están publicados por el comercio (web, bio). No se buscan teléfonos ni redes personales | Ley 25.326 y sentido común: es un comercio, no una persona | Buscar al dueño en LinkedIn o redes personales |

### Esquema de salida

```json
{
  "what_they_sell": ["útiles escolares", "fotocopias", "regalería"],
  "size_hint": "small | medium | large | unknown",
  "channels": {"website": "...", "instagram": "...", "facebook": "..."},
  "public_contact_name": {"value": "Laura", "role": "dueña", "source": "https://..."},
  "buying_signals": ["arma listas escolares por encargo"],
  "not_a_fit_signals": [],
  "sources": ["https://...", "https://..."],
  "confidence": "high | medium | low"
}
```

Por tenant, además: `icp_fit` (`fits` | `unclear` | `does_not_fit`), `icp_fit_reason`, y el tramo del ICP que encaja.

---

## Alcance explícito

### Incluido (v1)

- Provider con la receta de v1 y el esquema fijo.
- Enriquecimiento en lote de los comercios tildados, antes de publicar, con progreso en el wizard.
- `icp_fit` con destildado por defecto de `does_not_fit`.
- Tarjeta del prospecto (wizard, kanban de 084 y tabla de prospectos de 088) con lo encontrado y sus fuentes.
- Bloque en el prompt de `load_facts` del grafo `prospect` (`app/agent/prospect/prompt.py`).
- Guardado compartido en `core.places.enrichment` (si 092 está) o en `campaign_prospect` (si no).
- Costo en `campaign_cost_daily.enrichment_cost`.
- A/B: la mitad de los prospectos de la campaña se enriquecen para medir el impacto. Se apaga cuando haya resultado.

### Fuera de alcance

- Scraping directo de Instagram, Facebook o Google Maps (reseñas completas).
- Enriquecer la cartera de clientes existentes.
- Usar el enriquecimiento en el agente vendedor (después del handoff). El paquete de handoff de 084 puede llevarlo en una segunda etapa.
- Variables del HSM generadas.

---

## Requisitos funcionales

- `RF-1` Al confirmar la selección del wizard, `POST /{schema}/campanas-outbound/{id}/enrich` arranca un job para los tildados sin enriquecimiento vigente.
- `RF-2` Cada resultado cumple el esquema. Si el modelo devuelve otra cosa, el comercio queda «sin datos» y no bloquea la publicación.
- `RF-3` `icp_fit` se calcula con el ICP snapshot de la campaña. `does_not_fit` se destilda y muestra el motivo.
- `RF-4` Publicar no espera al enriquecimiento más de 5 minutos. Los que no terminaron salen sin la capa 3.
- `RF-5` `load_facts` del grafo `prospect` lee el enriquecimiento del prospecto y lo pone en el prompt con la regla de uso.
- `RF-6` El costo se suma a `campaign_cost_daily.enrichment_cost`.

## Requisitos no funcionales

- `RNF-1` Concurrencia acotada (10 a la vez) para no saturar al proveedor ni al modelo.
- `RNF-2` Timeout de 10 s por página leída.
- `RNF-3` API keys en config de plataforma.
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
- **Then** queda «sin datos», se puede publicar, y el agente trabaja como hoy.

### `AC-4` Reuso

- **Given** un comercio enriquecido para otro tenant hace 30 días.
- **When** entra en una campaña nueva.
- **Then** no se vuelve a buscar; solo se recalcula `icp_fit` con el ICP nuevo (una llamada al modelo, sin búsqueda).

---

## Casos borde

- `CB-1` La búsqueda devuelve otro comercio con el mismo nombre en otra ciudad: la extracción exige que la dirección o el barrio coincidan; si no, confianza baja.
- `CB-2` Página caída o con captcha: se ignora esa fuente.
- `CB-3` Cadena (sucursal de una franquicia): `size_hint = large` y señal «parte de una cadena». Suele comprar centralizado; el agente pregunta por compras centrales.
- `CB-4` El modelo intenta sacar un teléfono personal de una página: el esquema no tiene ese campo; se descarta.

---

## Migración de base de datos

- `core.places.enrichment jsonb`, `enriched_at timestamptz` (ya previstos en 092).
- `{schema}.campaign_prospect`: `enrichment jsonb` (si no hay 092), `icp_fit text`, `icp_fit_reason text`, `enriched_at timestamptz`, `enrichment_variant text` (`on` | `off`, para el A/B).
- `{schema}.campaign_cost_daily.enrichment_cost numeric not null default 0`.
- `core.web_enrichment_provider`: `id`, `price_per_search_usd`, `price_per_page_usd`, `enabled`.

**Rollback:** apagar el provider; el wizard no enriquece y el prompt no tiene la capa 3.

---

## Orden de implementación

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `suplai-platform` | `feat/prospeccion-outbound-v2` | Este spec |
| 2 | `backend-supabase` | `feat/enriquecimiento-prospecto` | Provider, job, esquema, `icp_fit`, costo |
| 3 | `agente-conversacional-multi_tenant` | `feat/enriquecimiento-prospecto` | Bloque en `load_facts` y prompt de `prospect` |
| 4 | `product-management-app` | `feat/enriquecimiento-prospecto` | Progreso, tarjeta, destildado sugerido |

Mejor después de 090 y 092, para que lo compartido se guarde una vez.

---

## Plan de prueba en CI/CD

- **Backend:** provider fake con tres casos (encaja, no encaja, sin datos). Validación del esquema. `icp_fit` destilda. Reuso sin búsqueda. Costo sumado.
- **Agente:** el prompt de `prospect` con enriquecimiento incluye el bloque y la regla; sin enriquecimiento, es igual al actual (snapshot del prompt).
- **Backoffice:** `tsc --noEmit`.
- Gap: el juicio del modelo sobre `icp_fit` no se prueba en CI. Se mide en la prueba humana.

## Plan de prueba humana (antes del PR)

**Prueba de cobertura (antes de escribir código):**

1. Tomar 50 prospectos reales de una campaña de 083 (mezcla de rubros).
2. Para cada uno, correr a mano la receta (búsqueda en Serper o Tavily, leer la web si hay, extraer con un modelo chico usando el esquema).
3. Anotar: % con algún dato útil, % con `what_they_sell` correcto (revisado a ojo), % de `does_not_fit` correctos, costo total.
4. Si menos del 40% trae algo útil, reducir el alcance a «solo comercios con web o con Instagram en el snippet».

**Después de implementar:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`), agente local. Tenant `demo`.

1. Wizard: tildar 10 comercios, ver el progreso de enriquecimiento y los `does_not_fit` destildados con motivo.
2. Abrir la tarjeta de uno: ver lo encontrado y las fuentes.
3. Publicar a un teléfono de prueba y responder. El primer turno del agente usa lo que se encontró sin decir «vi tu web».
4. Revisar en el panel el costo de enriquecimiento.
