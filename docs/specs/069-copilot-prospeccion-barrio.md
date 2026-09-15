# 069 — Copilot: receta prospección por barrio + Juan (mapas)

**Estado:** En implementación  
**Fecha:** 2026-09-14  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas:** `feat/copilot-prospeccion-barrio`  
**Extiende:** [038](./038-copilot-agentes-especialistas.md), [062](./062-copilot-supervisor-langgraph.md), [065](./065-copilot-supervisor-cancel-deadlock.md), [066](./066-copilot-supervisor-playbook.md), [067](./067-copilot-object-choice.md)  
**Índice:** [001-suplai-copilot.md](./001-suplai-copilot.md)

---

## Objetivo

Sumar un **caso de uso nuevo** al Supervisor como **receta** `prospeccion_barrio`, sin modificar `carrito_abierto` ni `no_responden`. El operador busca comercios en un barrio (Google Places, aún no clientes), ve **mapa + tabla** en el chat, elige cuáles dar de alta (teléfono + día de visita de la zona) y el playbook arma etiqueta, grupo, plantilla MARKETING e agenda puntual a +7 días para invitarlos a comprar.

El oficio de mapa/Places/alta es un **agente nuevo**: slug `mapas`, nombre default **Juan**. El Supervisor lo llama en la receta; también aparece en la lista para chat 1:1.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Forma de entrega | Receta nueva en el intérprete 066 | Un caso nuevo = una receta, no un grafo extra; las anteriores no se tocan | Engordar ReAct; un StateGraph por caso |
| Origen de leads | Google Places **que no son clientes** (zonas blancas) | El operador dijo «crear contactos»; no es re-segmentar el CRM | Clientes ya geolocalizados del barrio |
| Barrio | Híbrido: match `geo_zones` por nombre; si no, geocode + polígono | El chip funciona con «Palermo» aunque la zona se llame distinto | Solo zonas existentes; solo geocode libre |
| Rubros | Extraídos del **mismo prompt** (`textQuery` libre, N rubros) | La búsqueda es libre; no el combo fijo de 4 tipos del mapa comercial | Chips kiosco/súper/escuela; default del tenant |
| Selección | Artefacto `lead_choice` (mapa + tabla + checkboxes) en el chat | Un HITL; no 15 modales ni alta ciega | Modal 1:1 del mapa comercial; `object_choice` |
| Sin teléfono | Se ve en el mapa; **no** se puede tildar | El alta exige `phone_number` | Crear contactos sin WhatsApp |
| Confirmación | Un solo confirm del lote (ids tildados + `confirm_token`) | Select + alta en un paso; no un `object_choice` extra encima | Dry-run create aparte después de elegir |
| Campos del alta | Zona → vendedor + `dia_de_visita`; lista **pública** del tenant | Places no trae esos campos; evita ficha por fila | Columnas editables por lead |
| Fallback campos | Una pregunta para todo el lote si falta vendedor o lista pública | No bloquea el mapa; no asume defaults rotos | Abort; inventar lista_id=1 |
| Agente mapas | Pack `mapas` / Juan + `preguntar_a_juan` | Spec 038: oficio nuevo = agente nuevo, no engordar a Lucía | Tools de mapa en Lucía o en el Supervisor |
| Mapa | Artefacto en el hilo (reactivar `map` **solo** en este flujo) | El playbook no se corta al ir al mapa comercial | Embeber `CommercialMapDisplay`; deep-link obligatorio |
| Agenda | Puntual **+7 días**, plantilla **MARKETING** | Tiempo a aprobación Meta; el día de visita queda en el PdV para Field | Recurrente por día de zona; envío el próximo día de visita |
| Tope Places | 40 resultados (dedupe por `place_id`) | Costo API + tabla usable | Sin tope; paginación v1 |
| Persistencia place | `clients.metadata.google_place_id` | Evita reimportar; no hay columna hoy | Migración de columna |
| Isolation recetas | `RECIPES` aditivo; match de carrito / no responden **primero** | Un pedido de carrito no cae en prospección | Classifier LLM |

---

## Alcance explícito

### Incluido (v1)

- Pack `mapas` (Juan): `zonas_list`, `territorio_resolve`, `leads_search`, `leads_create_batch`.
- Juan **no** se lista en el picker ni tiene chip de Supervisor hasta que la receta esté estable. El Supervisor igual puede llamarlo (`preguntar_a_juan`) si el texto matchea la receta.
- Wrapper Supervisor `preguntar_a_juan` (mismo patrón Command + transcript).
- Receta `prospeccion_barrio`: territorio → Places → `lead_choice` (elige y da de alta) → Lucía etiqueta/grupo → Sofía MARKETING → Martín +7.
- `kind: hitl` en el intérprete (paso `lead_choice`). El confirm del picker **es** el write de `leads_create_batch`; no hay segundo `object_choice` ni un paso Juan extra. Sí hay `object_choice` en etiqueta, grupo, plantilla y agenda.
- Alta: `is_prospect=true`, teléfono, dirección, coords (`PUT client-locations`, mismo contrato que el modal de prospecto), `dia_de_visita` y vendedor de la zona, lista pública, `metadata.google_place_id`.
- Filtro ya-clientes: teléfono normalizado **o** `metadata.google_place_id`.
- Chip de Supervisor **oculto** en esta entrega (la receta todavía no está lista para operar). El match por texto (`invitar` + `barrio` \| `mapa` \| `lead` \| `prospect` \| rubro) sigue en código.
- Tests de classify / observe / abort / e2e mockeado; UI `lead_choice`.
- Specs puntero cortos en backend y backoffice al implementar.

### Fuera de alcance

- Cambiar `carrito_abierto` o `no_responden`.
- Embeber el mapa comercial ni selección en esa pantalla (sí un follow-up «ver en mapa» después, no camino crítico).
- Alta de contactos sin teléfono.
- Rubro por default del tenant o combo fijo de 4 tipos.
- Agenda recurrente por día de visita / Field tasks automáticas.
- Classifier LLM / embeddings de barrio.
- Undo de altas ya confirmadas.
- Campañas n8n / envío inmediato al confirmar.
- Editar vendedor o lista **por fila**.

---

## Orden de implementación

Cross-repo. Merge **backend → backoffice**. Spec en platform en paralelo.

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `suplai-platform` | `feat/copilot-prospeccion-barrio` | Este spec + enlace en 001 |
| 2 | `backend-supabase` | `feat/copilot-prospeccion-barrio` | Catalog Juan, tools, receta, `hitl`, wrapper, tests. **No** alterar recetas 066/067 |
| 3 | `product-management-app` | `feat/copilot-prospeccion-barrio` | Artefacto `lead_choice` (mapa + tabla + checkboxes), tipos SSE, lista de agentes vía API |

El humano mergea en GitHub. Orden de merge: backend (tools + playbook) → backoffice (UI).

---

## Migración de base de datos

Sin migración de BD. `plan` / `facts` viven en `core.copilot_orchestrator_runs`. `google_place_id` va en `clients.metadata` (JSONB ya usado por memoria de cliente, spec 028). `is_prospect` ya existe.

Rollback de producto: no registrar la receta ni el pack; el resto del Copilot no depende de Juan.

---

## Plan de prueba en CI/CD

- `tests/test_copilot_supervisor_playbook.py`:
  - Chip canónico → `prospeccion_barrio`.
  - «kioscos en Palermo» **sin** invitar → **sin** receta (Juan 1:1 / ReAct).
  - Chip de carrito / no responden → recetas **previas**, no esta.
  - 0 Places o 0 con teléfono → `aborted`; no llama a Lucía/Sofía/Martín de campaña.
  - Resume `lead_choice` con 0 ids → abort; con N ids → `client_ids` y sigue a etiqueta (sin segundo confirm de alta).
  - Cancelar picker → no reencola `buscar_leads`.
  - Etiqueta default `Prospectos {barrio}`.
- `tests/test_copilot_catalog.py`: slug `mapas`; `preguntar_a_juan` en Supervisor; tools de Juan no se despachan en `audiencia`.
- Tools: `leads_search` excluye ya-clientes; `leads_create_batch` dry-run lista N, zona, día, vendedor, lista pública; duplicado de teléfono se omite en el resumen.
- `tests/test_copilot_supervisor_graph.py` y casos 066/067 **siguen verdes**.
- Front: typecheck/lint; Zod de `lead_choice`; checkbox disabled sin teléfono.
- Gap: sin Playwright e2e obligatorio; Places/geocode mockeados (no pegarle a Google en CI).

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenant `demo` (zonas + `ciudad_base` + lista pública). API key Google Maps ya usada por el mapa comercial.

1. Copilot → Supervisor → chip de prospección (o «invitar kioscos en {barrio de una zona demo}»).
2. Si el barrio matchea zona: no pregunta zona. Si el nombre es ambiguo o falta rubro: **una** pregunta y sigue.
3. Aparece mapa + tabla en el **chat** (no navega al mapa comercial). Filas sin teléfono no tildan. «Seleccionar todos con teléfono» + confirmar 2.
4. Preview del lote: N contactos, día de visita, vendedor, lista pública. Confirmar → contactos `is_prospect` con GPS y `metadata.google_place_id`.
5. Lucía: etiqueta `Prospectos {barrio}` → grupo. Sofía: draft MARKETING (o reuso). Martín: agenda puntual +7; aviso si PENDING.
6. Chip de **carrito abandonado**: playbook viejo, sin Juan.
7. Juan 1:1: «Buscá kioscos en Palermo y mostrame el mapa» → mapa/tabla, **no** arma plantilla ni agenda.

---

## Criterios de aceptación

- Recetas 066/067 intactas (tests verdes; chips viejos no entran a esta receta).
- Juan en `GET /agents`; 1:1 no dispara la campaña completa.
- El chip de prospección corre el playbook, no el ReAct con nudge.
- El operador elige el lote en el chat; sin teléfono no se da de alta.
- Tras confirmar hay `client_ids` de verdad (no IDs de Places) antes de etiquetar.
- 0 audiencia / 0 tildados cierra el playbook sin Sofía/Martín.
- Agenda +7 MARKETING, mismo patrón de aviso HSM que no responden.

---

## Receta (`prospeccion_barrio`)

**Chip (Supervisor):**  
«Buscá comercios en un barrio, mostrá el mapa, dales de alta y armá una campaña para invitarlos a comprar».

**Match:** chip, o `invitar` + algo de `barrio` / `mapa` / `lead` / `prospect` / rubro (`kiosco`, etc.). Un pedido solo de búsqueda va a Juan 1:1.

```text
resolver_territorio (Juan)
  extrae barrio + rubros del mismo mensaje
  zona existente → zone_id, dia_visita, vendedor
  si no → geocode (bias ciudad_base / HQ) + polígono; día/vendedor de la zona que cubra
  0 rubros o N zonas ambiguas → ask (mismo step al responder)
  sin lista pública y sin vendedor → ask una vez
       │
       ▼
buscar_leads (Juan) ── 0 con teléfono ── abort
  Places textQuery por rubro, recorte al polígono, excluye ya-clientes
  artefacto lead_choice (map + tabla), tope 40
       │
       ▼
lead_choice (HITL + write) ── 0 tildados ── abort
  confirmar = selected_place_ids + confirm_token
  ejecuta leads_create_batch (sin segundo object_choice)
  facts.client_ids; duplicados de teléfono se omiten y van al resumen
       │
       ▼
etiqueta «Prospectos {barrio}» → asignar → grupo   (Lucía)
       │
       ▼
plantillas MARKETING invitá-a-comprar → draft si hace falta   (Sofía)
       │
       ▼
agenda puntual +7 días   (Martín) → cerrar
```

`lead_choice` es `kind: hitl`. El resto: `employee` / `summarize` como 066. `object_choice` no pinta el picker.

### Facts (checkpoint)

`barrio`, `rubros`, `zone_id`, `dia_visita`, `vendedor_id`, `lista_precios_id`, `prospects`, `selected_place_ids`, `client_ids`, `etiqueta`, `grupo_id`, `plantilla` / `meta_plantilla_id`.

---

## Pack Juan (`mapas`)

| Tool | Lectura / write | Contrato |
|------|-----------------|----------|
| `zonas_list` | read | Zonas: nombre, `dia_visita`, vendedor, bbox |
| `territorio_resolve` | read | Match nombre zona **o** geocode barrio → polígono + zona que cubre. Ask si ambiguo / falta rubro |
| `leads_search` | read | `textQuery` por rubro, `locationRestriction` del polígono, filtro ya-clientes, artefacto `lead_choice` |
| `leads_create_batch` | write | Alta del lote. En el playbook la dispara el confirm de `lead_choice` (el artefacto ya trae el dry-run en `summary`). En 1:1, el mismo artefacto |

No tiene etiquetas, grupos, plantillas ni agendas. Reusa la lógica de `calculate_white_zones` (Places `searchText`) pero con query libre y recorte por polígono geocodificado, no solo `zone_id`.

Chips 1:1: «¿Qué zonas hay?», «Buscá kioscos en Palermo y mostrame el mapa».

Alta (mismo espíritu que `AddProspectAsClientModal`): `POST` cliente + `PUT` `client-locations` (lat/lng, address, `google_maps_url` con `query_place_id`). `dia_de_visita` del enum de la zona. Vendedor = `vendedor_principal` de la zona (nombre o id según el alta actual). Lista = primera `es_publica` del tenant.

---

## Artefacto `lead_choice`

Payload (SSE `artifact` + interrupt):

- `type: "lead_choice"`
- `geojson` FeatureCollection: polígono de territorio + puntos (propiedades: `has_phone`, `place_id`)
- `center` / `zoom`
- `rows`: `place_id`, `name`, `address`, `phone`, `rubro`, `has_phone`
- `summary`: N con teléfono, zona, día de visita, vendedor, lista pública
- `confirmToken`, `expiresAt`

UI:

- Mapa encima o al lado; pin distinto si no hay teléfono.
- Tabla con checkbox **solo** si `has_phone`.
- «Seleccionar todos con teléfono». Confirmar disabled si 0 tildados.
- Confirmar → `POST .../actions/confirm` (o resume Supervisor) con `selected_place_ids`.
- Cancelar → skip/abort 065/066; **no** reencola `buscar_leads`.

El mapa genérico `clients_geojson` de Carlos **sigue** deprecado. Solo este flujo emite mapa.

---

## Errores y bordes

| Caso | Comportamiento |
|------|----------------|
| Prompt sin rubro / varias zonas | `ask` en `resolver_territorio`; no llama Places |
| Geocode vacío / sin `GOOGLE_MAPS_API_KEY` | abort; copy claro; no inventa pines |
| 0 Places o todos sin teléfono / ya clientes | abort (065); no etiqueta ni agenda |
| Confirm con 0 ids | UI no deja; si llega → abort |
| Teléfono duplicado (lote o CRM) | omite fila; resumen de omitidos |
| Zona sin vendedor / sin lista pública | una pregunta para el lote; después sigue |
| Cancelar picker | skip/abort; no reencola búsqueda |
| Plantilla MARKETING PENDING | agenda +7 igual; aviso HSM |
| Geocode | bias `ciudad_base` / HQ del tenant |

---

## Referencias de código (al implementar)

- Recetas: `backend-supabase/services/copilot/supervisor/playbook/recipes.py` (solo **agregar**)
- Intérprete: `.../playbook/schema.py`, `nodes.py`, `observe.py`
- Catalog: `backend-supabase/services/copilot/catalog.py`
- Wrappers: `.../supervisor/employee_tools.py`, `employee_graphs.py` (`SLUG_BY_PERSONA`)
- Places hoy: `backend-supabase/services/geo_zones_service.py` (`calculate_white_zones`)
- Alta prospecto UI (contrato a replicar en batch): `product-management-app/components/commercial-map/modals/AddProspectAsClientModal.tsx`
- Artefactos: `product-management-app/lib/copilot/types.ts`, `components/copilot/CopilotArtifacts.tsx`
