# 071 — Prospección ICP en mapa comercial + primer HSM + tool decisor

**Estado:** Diseño (pendiente revisión humana)  
**Fecha:** 2026-09-15  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`, `agente-conversacional-multi_tenant`  
**Ramas sugeridas:** `feat/maps-icp-prospeccion`  
**Relaciona:** mapa comercial / zonas blancas; alta PDV; plantillas Meta; [069](./069-copilot-prospeccion-barrio.md) (Copilot/Juan, **no** se modifica); [029](./029-client-memory-wizard-agendas-1a1.md); agent spec 066 (swap primario/secundario); agent spec 034 (opt-in de tools)

---

## Objetivo

Permitir que el operador, desde el **mapa comercial** (zonas blancas), defina un ICP estructurado, busque prospectos de rubros afines en Google Places, tildé a quién contactar y mande (o agende) un **primer HSM** elegido del pool de plantillas Meta.

El contacto se guarda **antes** del HSM. Cuando responde, cae en el **agente comercial** (pedidos), no en el recepcionista.

Si el interlocutor no es el decisor, el agente comercial usa una tool para pedir el número, dejarlo como **contacto primario del mismo PDV** y enviar la plantilla predefinida **decisor encontrado** (`{nombre} me pasó tu número, te contacto de {distribuidora}`).

### Métricas de éxito

- Un operador completa búsqueda → alta → primer HSM sin salir del mapa.
- Un inbound al teléfono ya dado de alta **no** dispara el flujo de recepcionista.
- Una objeción “no soy yo” produce un segundo HSM al decisor y el PDV queda con el nuevo número como primario.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Superficie | Wizard de 4 pasos en el mapa comercial | Pedido explícito: mismo flujo de UI que zonas blancas | Receta Copilot 069; campaña de estrategias |
| ICP | Texto de cliente ideal + tamaño PdV; chips de Places sugeridos | El operador describe a quién busca; no escribe `textQuery` | Rubros fijos a mano; texto libre como query |
| Places | Enum Table A (`includedType`) + `textQuery` derivado (`_` → espacios) | Places se porta mal con queries inventadas; los tipos oficiales existen | LLM arma queries; concatenar “qué venden” a la query |
| Chips sugeridos | LLM elige 3–6 IDs **solo** del enum; fallback por keywords/sinónimos | “Hace magia” sobre chance de existir, sin inventar tipos | LLM inventa queries; chips fijos de 7 rubros |
| Qué venden / tamaño | Copy de plantilla + ranking suave (rating/reviews) | No son tipos de Places | Filtrar Places por tamaño (casi no existe) |
| Selección | Tildar solo prospectos **con teléfono** | El HSM exige WhatsApp | Envío masivo a todos; alta 1:1 como hoy |
| Confirmación | Alta lote + enviar ahora **o** agendar fecha/hora | Prospección en caliente y cola fuera de horario / plantilla PENDING | Solo ahora; solo agenda +7 como 069 |
| Skip recepcionista | Persistir cliente **antes** del HSM | El webhook ya rutea `actor_type=client` conocido al agente comercial | Routing nuevo; mandar al WhatsApp del vendedor |
| Quién atiende el inbound | Agente comercial de la distribuidora | Detecta objeciones en prosa; el canal vendedor es determinístico | Asistente del vendedor; aviso Field sin chat |
| Plantilla 1er contacto | Slot default + pool APPROVED; Sofía puede crear un draft PENDING y agendar +7 | Meta tarda en aprobar; no mandar texto libre | Solo slot; crear plantilla sin humano |
| Plantilla decisor | Solo slot tenant; la tool no elige del pool | Copy contractual; el modelo no inventa HSM | Override runtime; agendar el 2º HSM |
| Tool decisor | Siempre en agente comercial si hay PDV | “Las compras las hace mi mamá” también pasa en clientes ERP | Solo `is_prospect`; ventana 48 h post-HSM |
| Swap | Número nuevo = primario del mismo PDV; el actual = secundario | El decisor es quien hay que contactar; Maps/referrer se conserva | Dejar el de Maps primario; fusionar PDVs |
| Persistencia ICP | `metadata.prospeccion.icp_saved` (JSONB, tope 8, dedupe por texto) | Reutilizar la descripción sin tabla de campañas | Tabla de campañas; solo estado local del wizard |
| `google_place_id` | `clients.metadata.google_place_id` | Igual que 069; evita reimportar | Columna nueva |
| Mapping canales | Constante Table A (~420 tipos comerciales) + aliases v1 | v1 sin tabla ni admin de taxonomía; IDs oficiales de Google | Tabla `rubros_places`; 7 chips fijos |
| Copilot 069 | No se toca | Oficio distinto (barrio en chat vs ICP en mapa) | Unificar en Juan |

---

## Alcance explícito

### Incluido (v1)

- Reemplazar el modal de 4 rubros fijos por un wizard de 4 pasos en la zona seleccionada.
- Enum Table A de Places (tipos comerciales; sin geo/natural/housing/transporte-infra).
- Texto ICP → `POST /{schema}/prospeccion/improve-icp` reescribe con LLM y persiste; `GET/POST /{schema}/prospeccion/icp-saved` lista/guarda (tope 8). El wizard prellena el último y permite reutilizar.
- Texto ICP → `POST /{schema}/prospeccion/suggest-channels` sugiere chips del enum (LLM + fallback); el operador tilda, descarta o agrega del catálogo.
- Búsqueda con `includedType` + `textQuery` fijo (id con `_` → espacios). Alias v1 (`dietetica` → `health_food_store`, etc.). Compat `business_types`.
- Búsqueda en bbox de la zona, dedupe `place_id`, excluir ya-clientes (teléfono normalizado o `google_place_id`), tope 40, ranking suave.
- Tabla + pines; checkbox solo con teléfono.
- Paso 4: plantilla default del slot *primer contacto Maps*, cambio a otra APPROVED del pool, **enviar ahora** o **agendar**. Botón **Crear con Sofía**: chat con la especialista de plantillas (Copilot `plantillas`) en el mismo modal; el borrador abre `CreateMetaTemplateModal`. Si queda PENDING, el picker la elige y **Agendar** se prellena a +7 días. Enviar ahora sigue bloqueado hasta APPROVED.
- Alta en lote al confirmar: `is_prospect=true`, GPS, dirección, vendedor y `dia_de_visita` de la zona, lista pública, `metadata.google_place_id`.
- Config tenant `metadata.prospeccion.primer_contacto_meta_plantilla_id` y `decisor_encontrado_meta_plantilla_id` (UI en modal de plantillas Meta).
- Endpoint de outreach y endpoint `refer-decision-maker`.
- Tool agente `refer_decision_maker` (opt-in spec 034), reutilizable si hay otra objeción.
- HSM decisor inmediato con variables: nombre de quien refirió + nombre de la distribuidora.

### Fuera de alcance

- Receta Copilot 069 / agente Juan (sigue independiente). El chat de Sofía en el wizard **no** orquesta a Juan ni a Martín.
- Enviar el primer HSM desde el WhatsApp personal del vendedor o su asistente determinístico.
- Fusionar PDVs si el número del decisor ya pertenece a **otro** PDV.
- LLM que invente queries Places o el cuerpo del HSM.
- Tabla de campañas ICP, undo de altas, paginación Places, edición de vendedor/lista por fila.
- Agendar el HSM de decisor; elegir esa plantilla del pool en runtime.
- Polling hasta APPROVED para enviar ahora; crear plantilla en Meta sin pasar por el editor.
- Campo “qué venden” cruzado con catálogo de productos (texto libre en v1).

---

## Orden de implementación

Cross-repo. El humano mergea en GitHub. Orden: **backend → backoffice → agent**.

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `suplai-platform` | `feat/maps-icp-prospeccion` | Esta spec |
| 2 | `backend-supabase` | `feat/maps-icp-prospeccion` | Mapping, slots config, white-zones ICP, outreach, refer-decision-maker, tests |
| 3 | `product-management-app` | `feat/maps-icp-prospeccion` | Wizard mapa, picker plantillas, chat Sofía, slots en modal Meta |
| 4 | `agente-conversacional-multi_tenant` | `feat/maps-icp-prospeccion` | Tool `refer_decision_maker`, prompt, opt-in, tests |

Dependencias: el wizard no envía sin endpoints 2. La tool no swap/HSM sin `refer-decision-maker`. Specs puntero cortos en backend / backoffice / agent al implementar.

---

## Migración de base de datos

Sin migración de schema tenant ni de `public.meta_plantillas`.

- Keys nuevas en `public.distribuidoras.metadata.prospeccion` (JSONB ya existente), nullable: slots de plantillas + `icp_saved` (lista de `{id,text,tamano_pdv,updated_at}`, cap 8).
- `google_place_id` en `clients.metadata` (ya usado por 069).
- `is_prospect`, PDV, contactos secundarios: ya existen.

**Seed / backfill:** no. Cada tenant configura los dos slots en el modal de plantillas.

**Rollback:** no registrar los endpoints ni la tool; quitar keys de `metadata.prospeccion`. El mapa vuelve al modal viejo si se revierte el front.

**Riesgo:** plantillas MARKETING no APPROVED → **Enviar ahora** y la tool decisor se bloquean a propósito (no se manda texto libre). El 1er contacto PENDING sí se puede agendar a +7.

---

## Requisitos funcionales

- `RF-1` Wizard 4 pasos: ICP → búsqueda → selección → plantilla + ahora/agenda. Zona ya seleccionada.
- `RF-2` ICP: `que_venden` (texto), `tamano_pdv` (`chico` \| `barrio` \| `grande`), `canales[]` = IDs Table A. Sin canal no se busca. El LLM **no** escribe `textQuery`. `POST /{schema}/prospeccion/improve-icp` reescribe el texto (JSON `{"text":"..."}`) y lo guarda en `metadata.prospeccion.icp_saved`. Buscar también persiste el texto usado. El wizard lista los guardados y prellena el último.
- `RF-3` Cada chip → `includedType` = id + `textQuery` = id con `_` → espacios. Alias v1 (`dietetica`→`health_food_store`, `kiosco`→`convenience_store`, …). Compat: `business_types` crudos si son IDs oficiales. `GET /{schema}/prospeccion/place-types` lista el enum; `POST /{schema}/prospeccion/suggest-channels` sugiere 3–6 IDs filtrados al enum.
- `RF-4` Excluir conocidos; pines sin teléfono visibles y no tildeables.
- `RF-5` Outreach: alta de tildados **antes** de Graph/agenda. Tope 20 envíos ahora por confirm. Filas omitidas (teléfono duplicado, alta fallida) en el resumen; no abortan el resto salvo error de config global (sin slot, zona sin vendedor, sin lista pública).
- `RF-6` Enviar ahora usa `send_template_message`. Agendar crea agenda puntual en la fecha/hora elegida (timezone del tenant), misma plantilla.
- `RF-7` Inbound al teléfono dado de alta: agente comercial, no recepcionista (comportamiento actual del webhook; no hay router nuevo).
- `RF-8` Slots en config; el wizard default al primer slot y permite otra plantilla APPROVED del pool. PENDING solo con **Agendar**. La tool usa **solo** el slot decisor.
- `RF-8b` Paso 4: chat Sofía (`agent_slug=plantillas`) en el modal. Prefill con ICP. Artefacto `opens_modal` → editor Meta. Al crear: seleccionar la plantilla, modo agenda, fecha = hoy+7 (hora 10:00, editable).
- `RF-9` `refer_decision_maker(nombre, phone)`: validar PDV + plantilla APPROVED + teléfono; crear o reusar contacto en **ese** PDV; promover a primario; demotar el interlocutor a secundario; enviar HSM ya. Misma tool si hay otra objeción.
- `RF-10` Si el número nuevo ya es el primario de **ese** PDV: no duplicar; reenviar HSM (idempotente).
- `RF-11` Si el número nuevo pertenece a **otro** PDV: HTTP 409 / error de tool; no fusionar.
- `RF-12` HSM decisor: `{{1}}` = `nombre_de_pila` o `nombre` del referrer; `{{2}}` = `brand_name` o nombre de la distribuidora. Si la plantilla no tiene exactamente esos 2 params de body, error accionable y **sin** swap.
- `RF-13` Tool opt-in (`OPT_IN_TOOL_NAMES`). Sin `true` en `tools_habilitadas` no se expone.

### Canales Places (Table A)

Fuente: [Place Types — Table A](https://developers.google.com/maps/documentation/places/web-service/place-types). Enum en `backend/services/prospeccion_place_types.py`.

- El operador **no** escribe queries. Elige chips del enum (sugeridos por LLM o buscados a mano).
- Búsqueda: `includedType` = id; `textQuery` = id.replace(`_`, ` `). Tope 8 tipos / 40 Places.
- Aliases v1 (copy comercial → Table A): `dietetica`→`health_food_store`, `kiosco`→`convenience_store`, `restaurante`→`restaurant`, `supermercado`→`supermarket`, `farmacia`→`pharmacy`, `escuela`→`school`, `gimnasio`→`gym`.
- Los 4 tipos viejos del modal (`convenience_store`, `restaurant`, `supermarket`, `school`) siguen válidos porque **son** IDs Table A.

Ranking suave (no excluye): preferir `rating` / `userRatingCount` más altos cuando `tamano_pdv=grande`; no hay hard-filter por tamaño.

---

## Requisitos no funcionales

- `RNF-1` Places: tope 40 resultados dedupeados; no paginar en v1; no pegarle a Google en CI.
- `RNF-2` Pooler 6543, `statement_cache_size=0`; outreach sin loop de queries N+1 (alta en batch / pocas round-trips).
- `RNF-3` Multi-tenant: header `x-schema-name`; slots y plantillas por distribuidora.
- `RNF-4` Logs: `zone_id`, `canales`, `n_places`, `n_outreach`, `client_ids`, `template_id`, `send_now|agenda`, `pdv_id` en refer (sin dump de teléfonos).
- `RNF-5` Fallo Graph **después** de persistir el alta: el cliente queda; no rollback de PDV. El resumen marca `hsm_failed`. En la tool, fallo Graph post-swap: primarios **sí** quedan (el número sirve); la tool reporta que el HSM no salió. Fallo de **validación** pre-write: no swap.

---

## Criterios de aceptación (Given/When/Then)

### `AC-1` Wizard ICP → Places

- **Given** zona seleccionada, texto ICP y chips `gym` + `health_food_store` (alias `dietetica` resuelto).
- **When** el operador confirma el paso 1.
- **Then** el backend busca con `includedType` + `textQuery` fijo (sin queries inventadas), excluye ya-clientes y devuelve ≤ 40 prospectos con `google_place_id`, nombre, teléfono opcional.

### `AC-1b` Sugerir chips del enum

- **Given** texto “vendo suplementos; busco gimnasios de barrio y dietéticas”.
- **When** el operador pide sugerir canales.
- **Then** el backend devuelve 3–6 IDs Table A (p. ej. `gym`, `health_food_store`); IDs inventados se descartan; Places no se llama todavía.

### `AC-2` Sin teléfono no se tilda

- **Given** un pin sin teléfono.
- **When** el operador está en el paso 3.
- **Then** el checkbox está disabled; no entra al outreach.

### `AC-3` Alta antes del HSM

- **Given** 2 pines con teléfono, slot primer contacto APPROVED, enviar ahora.
- **When** confirma el paso 4.
- **Then** existen 2 clientes `is_prospect` con GPS y `metadata.google_place_id`; Graph se llama después; un inbound de esos números **no** entra al recepcionista.

### `AC-4` Override de plantilla

- **Given** slot default A y el pool con plantilla APPROVED B.
- **When** el operador elige B y confirma.
- **Then** el HSM/agenda usa B, no A.

### `AC-5` Agendar

- **Given** fecha/hora futura en timezone del tenant.
- **When** confirma “agendar”.
- **Then** no hay send inmediato; hay agenda puntual con esa plantilla; los contactos ya existen.

### `AC-6` Tool decisor

- **Given** conversación del agente comercial con el primario de un PDV (prospecto o ERP).
- **When** objeta y el agente llama `refer_decision_maker` con nombre + WhatsApp válido, slot decisor APPROVED de 2 params.
- **Then** el nuevo número es primario del mismo PDV; el anterior es secundario; el nuevo recibe el HSM *“{referrer} me pasó tu número, te contacto de {distribuidora}”*.

### `AC-7` Misma tool otra objeción

- **Given** el decisor también objeta y da un tercer número.
- **When** se llama de nuevo la tool.
- **Then** el tercero es primario; el segundo queda secundario; se envía otro HSM decisor.

### `AC-8` Número de otro PDV

- **Given** el teléfono nuevo ya es cliente de otro PDV del tenant.
- **When** se llama la tool.
- **Then** error 409 / `user_facing_message` para humano; **sin** swap ni HSM.

### `AC-9` Sin slot / no APPROVED

- **Given** falta `decisor_encontrado_meta_plantilla_id` o no está APPROVED.
- **When** el agente llama la tool.
- **Then** error accionable; primarios intactos. En el wizard, **Enviar ahora** exige APPROVED; una PENDING se puede **agendar**.

### `AC-10` Sofía crea draft y agenda +7

- **Given** paso 4 con contactos tildados.
- **When** el operador abre **Crear con Sofía**, pide el borrador y confirma en `CreateMetaTemplateModal`.
- **Then** la plantilla queda en el picker (PENDING), el modo es **Agendar**, la fecha es hoy+7 10:00 (editable) y Enviar ahora está disabled.

---

## Casos borde y errores

- `CB-1` Zona sin geometría / sin API key → 4xx/5xx claro; no se abre el paso 3 vacío como éxito.
- `CB-2` Zona sin vendedor o tenant sin lista pública → bloquear outreach; no inventar `lista_precios_id=1`.
- `CB-3` Teléfono de Places ya cliente → omitir en resumen; no fallar el lote.
- `CB-4` HSM `no_existente` (webhook) → contacto queda; no reintento automático.
- `CB-5` Plantilla primer contacto con N variables ≠ las que el backend puede llenar (`distribuidora`, opcional `que_venden`) → bloquear esa plantilla en el picker o fallar el envío de esa fila con mensaje; no mandar params de más/menos a Graph.
- `CB-6` OpenAI caído o timeout al mejorar ICP → no vaciar el textarea; devolver el texto original y persistirlo igual.
- `CB-6` Tool sin PDV (contacto huérfano) → error; no crear PDV implícito.
- `CB-7` Compat `business_types` viejos: el endpoint white-zones sigue aceptándolos.

---

## Impacto técnico

| Capa | Archivos (orientativos) |
|------|-------------------------|
| Backend | `prospeccion_place_types.py`, `prospeccion_channels.py`, `prospeccion_suggest.py`, `routers/geo_zones.py`, `services/geo_zones_service.py`, `data_access/geo_zones.py`, `routers/pdv.py`, `services/pdv_service.py`, `models/distribuidoras_config.py`, `routers/distribuidoras_config.py` |
| Backoffice | `WhiteZonesIcpStep.tsx`, `WhiteZonesContactStep.tsx`, `SofiaProspeccionChat.tsx`, `WhiteZonesModal.tsx`, `commercial-map-context.tsx`, `meta-templates-modal.tsx`, i18n `language-context.tsx`, proxies `app/api/prospeccion/*` y `app/api/geo-zones/*` |
| Agente | `app/agent/tools/registry.py`, tool nueva, `tool_activation_policy.py`, prompt comercial, tests evals |

- Migraciones SQL de tablas: **no**.
- Feature flag: no. Tool sí es **opt-in** por tenant. Slots vacíos = feature de envío apagada con mensaje.
- Env: `GOOGLE_MAPS_API_KEY` ya requerida por zonas blancas.

---

## Plan de prueba en CI/CD

- **Backend** (`pytest`): enum Table A (retail in, geo out); expand alias→`includedType` + `textQuery` fijo; descarta IDs/texto inventados; suggest fallback sin OpenAI; LLM mock filtra IDs inventados; `merge_saved_icps` dedupe/cap 8; parse JSON de improve-icp; ranking suave; white-zones con body ICP (Places mock); outreach; refer-decision-maker; tests de config `metadata.prospeccion`.
- **Backoffice:** `tsc --noEmit`; checkbox disabled sin teléfono; Enviar ahora disabled si PENDING; agenda +7 al crear con Sofía.
- **Agente:** tool en registry + opt-in; payload; no-write si backend 4xx; AC-6/7 con HTTP mock.
- Checks existentes (Copilot 069, geo_zones, pdv secondary, agenda) **siguen verdes**.
- Gap: sin Playwright e2e obligatorio; Graph y Places mockeados.

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenant `demo` con zona, vendedor, lista pública, `GOOGLE_MAPS_API_KEY`. Configurar las dos plantillas APPROVED (primer contacto y decisor de 2 params). Habilitar `refer_decision_maker` en `tools_habilitadas`.

1. Mapa → zona → zonas blancas → Cliente ideal “vendo suplementos; busco gimnasios de barrio y dietéticas” → **Mejorar con IA** (el texto se reescribe y queda en el combo de guardados) → **Sugerir canales** → tildar gym + dietética (u otros del enum) → buscar. Cerrar, reabrir: el último ICP está prellenado y se puede elegir otro guardado.
2. Tildar 2 con teléfono; dejar uno sin teléfono destildado. Elegir plantilla del pool (cambiar el default). **Enviar ahora**.
3. Verificar en clientes: 2 prospectos con GPS y `google_place_id`. Desde un WA de prueba, escribir a la línea de la distribuidora: entra el **agente comercial**, no el formulario de recepcionista.
4. Decir “las compras las hace {Nombre}” y pasar un número de prueba 2. La tool envía *“{NombreMaps} me pasó tu número, te contacto de {distribuidora}”*. El PDV queda con el 2 como primario y el de Maps como secundario.
5. Repetir el wizard con **agendar** a +1 h: no sale HSM ahora; la agenda existe.
6. Chip/receta Copilot de barrio (069): sin regresiones; no se abre este wizard.
7. Paso 4 → **Crear con Sofía** (no auto-envía; el textarea viene prellenado con el ICP) → mandar el mensaje → **Revisar y crear** → confirmar en el editor. El picker muestra la PENDING, **Agendar** queda en hoy+7 10:00, **Enviar ahora** disabled. Confirmar agenda. Copilot 069 / Juan no se abre.

---

## Observabilidad y rollback

- Logs estructurados en white-zones, outreach y refer-decision-maker.
- Rollback de producto: revertir PRs en orden inverso (agent → backoffice → backend); keys de metadata se pueden `null`.

---

## Riesgos

| Riesgo | Mitigación |
|--------|------------|
| Costo Places | Tope 40; un search por query del mapping; zona bbox no nearby infinito |
| Plantilla MARKETING PENDING | Enviar ahora y tool bloquean; el operador puede agendar el 1er contacto a +7 |
| Swap irreversible si Graph falla | Validar plantilla **antes** del write; post-Graph no rollback (el primario nuevo es el deseado) |
| Confusión con Copilot 069 | Spec 069 intacta; este flujo vive solo en el mapa |
