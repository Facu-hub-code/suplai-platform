# 071 — Prospección ICP en mapa comercial + primer HSM + tool decisor

**Estado:** En implementación  
**Fecha:** 2026-09-18  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`, `agente-conversacional-multi_tenant`  
**Ramas sugeridas:** `feat/prospeccion-sofia-plantilla-picker` (wizard plantilla / hold cron); epic previa `feat/maps-icp-prospeccion`  
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
| ICP | Texto de cliente ideal; chips de Places sugeridos | El operador describe a quién busca; no escribe `textQuery` | Rubros fijos a mano; texto libre como query |
| Places | Enum Table A (`includedType`) + `textQuery` derivado (`_` → espacios) | Places se porta mal con queries inventadas; los tipos oficiales existen | LLM arma queries; concatenar “qué venden” a la query |
| Chips sugeridos | LLM elige 3–6 IDs **solo** del enum; fallback por keywords/sinónimos | “Hace magia” sobre chance de existir, sin inventar tipos | LLM inventa queries; chips fijos de 7 rubros |
| Tamaño PdV | Fuera de la UI v1; APIs reciben `tamano_pdv=barrio` fijo | Una sola variable extra no cambia Places y sí fricción en el wizard | Selector chico/barrio/grande; filtrar Places por tamaño |
| Selección | Tildar solo prospectos **con teléfono** | El HSM exige WhatsApp | Envío masivo a todos; alta 1:1 como hoy |
| Confirmación | Alta lote + agendar fecha/hora (PENDING: hoy; el cron espera APPROVED) | Prospección en caliente y cola fuera de horario / plantilla PENDING | Solo ahora; agenda +7 ciega como 069 |
| Plantilla 1er contacto | Slot default + pool APPROVED/PENDING; Sofía ofrece existentes (`MetaTemplatesModal` Usar) o draft; HITL **Revisar propuesta**; PENDING se agenda hoy y el cron hold hasta APPROVED | Meta tarda 1–2 días; el operador no espera a ciegas una semana | Solo slot; crear plantilla sin humano; +7 fijo |
| Zona sin vendedor | Diálogo para elegir vendedor; `vendedor_id` en el retry asigna zona + clientes | El error 409 no es accionable; el operador ya está en el wizard | Mandar a editar la zona a mano; toast y cortar |
| Alta de zona + vendedor | En crear/editar zona: elegir vendedor existente o alta inline (`POST /vendedores` + `vendedor_ids`) | Evita zonas huérfanas antes del wizard de prospección | Solo asignar después, en outreach |
| Skip recepcionista | Persistir cliente **antes** del HSM | El webhook ya rutea `actor_type=client` conocido al agente comercial | Routing nuevo; mandar al WhatsApp del vendedor |
| Quién atiende el inbound | Agente comercial de la distribuidora | Detecta objeciones en prosa; el canal vendedor es determinístico | Asistente del vendedor; aviso Field sin chat |
| Plantilla decisor | Plantilla de sistema `suplai_decisor_encontrado_v1` (auto-provision al tener WABA); el slot apunta a esa fila | Copy contractual; el modelo no inventa HSM; igual que pedido vendedor / error de sistema | Cada tenant crea la plantilla a mano; override runtime; agendar el 2º HSM |
| Variables HSM decisor | Backend llena `{{1}}` = `nombre_de_pila`/`nombre` del referrer y `{{2}}` = `brand_name`/`nombre` | El LLM no elige params; Graph exige count exacto | Que el modelo arme el texto libre |
| Cuerpo / conversación | MARKETING, solo BODY, cierra con pregunta; **sin** botones URL/CTA | Meta rechaza variable al inicio/fin; la respuesta del decisor abre ventana 24 h y entra al agente comercial | UTILITY (Meta lo rechaza: no es un evento transaccional); CTA que saca del chat |
| Tool decisor | Siempre en agente comercial si hay PDV | “Las compras las hace mi mamá” también pasa en clientes ERP | Solo `is_prospect`; ventana 48 h post-HSM |
| Swap | Número nuevo = primario del mismo PDV; el actual = secundario | El decisor es quien hay que contactar; Maps/referrer se conserva | Dejar el de Maps primario; fusionar PDVs |
| Persistencia ICP | `metadata.prospeccion.icp_saved` (JSONB, tope 8, dedupe por texto) | Reutilizar la descripción sin tabla de campañas | Tabla de campañas; solo estado local del wizard |
| `google_place_id` | `clients.metadata.google_place_id` | Igual que 069; evita reimportar | Columna nueva |
| Mapping canales | Constante Table A (~420 tipos comerciales) + aliases v1 | v1 sin tabla ni admin de taxonomía; IDs oficiales de Google | Tabla `rubros_places`; 7 chips fijos |
| Copilot 069 | No se toca | Oficio distinto (barrio en chat vs ICP en mapa) | Unificar en Juan |

---

## Alcance explícito

### Incluido (v1)

- Al crear (o editar) una zona, asignar un vendedor existente o crear uno (nombre + teléfono) en el mismo formulario.
- Reemplazar el modal de 4 rubros fijos por un wizard de 4 pasos en la zona seleccionada.
- Enum Table A de Places (tipos comerciales; sin geo/natural/housing/transporte-infra).
- Texto ICP → `POST /{schema}/prospeccion/improve-icp` reescribe con LLM y persiste; `GET/POST /{schema}/prospeccion/icp-saved` lista/guarda (tope 8). El wizard prellena el último y permite reutilizar.
- Texto ICP → `POST /{schema}/prospeccion/suggest-channels` sugiere chips del enum (LLM + fallback); el operador tilda, descarta o agrega del catálogo.
- Búsqueda con `includedType` + `textQuery` fijo (id con `_` → espacios). Alias v1 (`dietetica` → `health_food_store`, etc.). Compat `business_types`.
- Búsqueda en bbox de la zona, dedupe `place_id`, excluir ya-clientes (teléfono normalizado o `google_place_id`), tope 40, ranking suave.
- Tabla + pines; checkbox solo con teléfono.
- Paso 4: plantilla default del slot *primer contacto Maps*, cambio a otra APPROVED/PENDING del pool, **agendar**. Botón **Crear con Sofía**: aviso de 1–2 días, **Ver plantillas existentes** (modal Meta en modo Usar) y **Proponer una nueva**. El HITL dice **Revisar propuesta** y abre `CreateMetaTemplateModal`. Si queda PENDING, el picker la elige, la fecha es **hoy** y el cron envía apenas Meta la deje APPROVED. Enviar ahora sigue bloqueado hasta APPROVED.
- Alta en lote al confirmar: `is_prospect=true`, GPS, dirección, vendedor y `dia_de_visita` de la zona, lista pública, `metadata.google_place_id`.
- Config tenant `metadata.prospeccion.primer_contacto_meta_plantilla_id` y `decisor_encontrado_meta_plantilla_id` (UI en modal de plantillas Meta).
- Endpoint de outreach y endpoint `refer-decision-maker`.
- Tool agente `refer_decision_maker` (opt-in spec 034), reutilizable si hay otra objeción.
- HSM decisor inmediato con variables: nombre de quien refirió + nombre de la distribuidora.
- Plantilla de sistema `suplai_decisor_encontrado_v1` auto-provisionada (Meta + `public.meta_plantillas` + slot) cuando el tenant tiene WABA. Backfill a tenants activos; tenants nuevos al conectar WhatsApp o al abrir Plantillas de Meta.

### Fuera de alcance

- Selector de tamaño de PdV (`chico` / `barrio` / `grande`) en el wizard. v1 manda `tamano_pdv=barrio` fijo a improve/suggest/search.
- Receta Copilot 069 / agente Juan (sigue independiente). El chat de Sofía en el wizard **no** orquesta a Juan ni a Martín.
- Enviar el primer HSM desde el WhatsApp personal del vendedor o su asistente determinístico.
- Fusionar PDVs si el número del decisor ya pertenece a **otro** PDV.
- LLM que invente queries Places o el cuerpo del HSM.
- Tabla de campañas ICP, undo de altas, paginación Places, edición de vendedor/lista por fila.
- Agendar el HSM de decisor; elegir esa plantilla del pool en runtime.
- Polling en el wizard para **enviar ahora** apenas Meta apruebe. El copy del decisor **sí** lo crea el backend (plantilla de sistema), sin el editor. El primer contacto Maps sigue yendo por Sofía / pool. El cron de agenda **sí** hold hasta APPROVED.
- Campo “qué venden” cruzado con catálogo de productos (texto libre en v1).

---

## Orden de implementación

Cross-repo. El humano mergea en GitHub. Orden: **backend → backoffice → agent**.

| # | Repo | Rama | Qué |
|---|------|------|-----|
| 1 | `suplai-platform` | `feat/prospeccion-sofia-plantilla-picker` | Esta spec (hold cron + picker Sofía) |
| 2 | `backend-supabase` | `feat/prospeccion-sofia-plantilla-picker` | Cron agenda: puntual `fecha <= hoy` + skip hasta APPROVED |
| 3 | `product-management-app` | `feat/prospeccion-sofia-plantilla-picker` | Modal Usar, CTAs Sofía, Revisar propuesta, fecha hoy si PENDING |

Orden de merge: **backend (cron hold) → backoffice**. Agent no cambia en este follow-up.

---

## Migración de base de datos

Sin migración de schema tenant ni de `public.meta_plantillas`.

- Keys nuevas en `public.distribuidoras.metadata.prospeccion` (JSONB ya existente), nullable: slots de plantillas + `icp_saved` (lista de `{id,text,tamano_pdv,updated_at}`, cap 8).
- `google_place_id` en `clients.metadata` (ya usado por 069).
- `is_prospect`, PDV, contactos secundarios: ya existen.

**Seed / backfill:** plantilla de sistema `suplai_decisor_encontrado_v1` (MARKETING, `es_AR`, 2 params). Script `backend/scripts/provision_decisor_encontrado_meta.py` para tenants `activa=true`. En runtime, `ensure_decisor_encontrado_meta_template` al listar plantillas Meta y al guardar `whatsapp.waba` / token. El slot `metadata.prospeccion.decisor_encontrado_meta_plantilla_id` se apunta a esa fila (se puede overridear en el modal). Primer contacto Maps **no** es plantilla de sistema: sigue siendo slot elegido por el operador.

**Rollback:** no registrar los endpoints ni la tool; quitar keys de `metadata.prospeccion`. El mapa vuelve al modal viejo si se revierte el front. La plantilla Meta queda en el WABA (se puede borrar a mano).

**Riesgo:** plantillas MARKETING no APPROVED → **Enviar ahora** y la tool decisor se bloquean a propósito (no se manda texto libre). El 1er contacto PENDING sí se puede **agendar hoy**; el cron no envía hasta APPROVED (`fecha_programada <= hoy`, skip si status ≠ APPROVED).

---

## Requisitos funcionales

- `RF-1` Wizard 4 pasos: ICP → búsqueda → selección → plantilla + ahora/agenda. Zona ya seleccionada.
- `RF-2` ICP: `que_venden` (texto) + `canales[]` = IDs Table A. Sin canal no se busca. El LLM **no** escribe `textQuery`. `POST /{schema}/prospeccion/improve-icp` reescribe el texto (JSON `{"text":"..."}`) y lo guarda en `metadata.prospeccion.icp_saved`. Buscar también persiste el texto usado. El wizard lista los guardados y prellena el último. `tamano_pdv` sigue en el payload (default `barrio`) por compat de API; **no** se muestra ni se edita en v1.
- `RF-3` Cada chip → `includedType` = id + `textQuery` = id con `_` → espacios. Alias v1 (`dietetica`→`health_food_store`, `kiosco`→`convenience_store`, …). Compat: `business_types` crudos si son IDs oficiales. `GET /{schema}/prospeccion/place-types` lista el enum; `POST /{schema}/prospeccion/suggest-channels` sugiere 3–6 IDs filtrados al enum.
- `RF-4` Excluir conocidos; pines sin teléfono visibles y no tildeables.
- `RF-5` Outreach: alta de tildados **antes** de Graph/agenda. Tope 20 envíos ahora por confirm. Filas omitidas (teléfono duplicado, alta fallida) en el resumen; no abortan el resto salvo error de config global (sin slot, sin lista pública). Zona sin vendedor: el wizard abre un diálogo para elegir vendedor (`vendedor_id` en el retry); el backend lo deja como principal, asigna los clientes de la zona y sigue el alta. El diálogo también linkea a **Notificaciones**. Tras el alta OK: se limpian los pines de Places, se recargan las ubicaciones y los nuevos PDV aparecen como clientes en el mapa.
- `RF-5b` Crear/editar zona: selector **Vendedor de la zona** (`Sin asignar` / existente / **Crear vendedor nuevo**). El alta inline pide nombre + teléfono, hace `POST /vendedores` y manda `vendedor_principal_id` + `vendedor_ids` en el POST/PATCH de la zona.
- `RF-6` Enviar ahora usa `send_template_message`. Agendar crea agenda puntual en la fecha/hora elegida (timezone del tenant), misma plantilla.
- `RF-7` Inbound al teléfono dado de alta: agente comercial, no recepcionista (comportamiento actual del webhook; no hay router nuevo).
- `RF-8` Slots en config; el wizard default al primer slot y permite otra plantilla APPROVED del pool. PENDING solo con **Agendar**. La tool usa **solo** el slot decisor.
- `RF-8b` Paso 4: chat Sofía (`agent_slug=plantillas`) en el modal. Prefill con ICP. CTA **Ver plantillas existentes** abre `MetaTemplatesModal` en `selectionMode` (botón Usar → UUID local). Aviso visible: crear nueva tarda 1–2 días. HITL de plantilla: **Revisar propuesta** (no “Aceptar creación”) → editor Meta. Al crear o reusar: seleccionar la plantilla; si PENDING, fecha = hoy (hora 10:00, editable). El cron envía apenas esté APPROVED.
- `RF-8c` `agenda_sender`: puntuales con `fecha_programada <= hoy` y `enviado_at` nulo. Antes de Graph, status live de Meta (cache por `template_name` en la corrida). Si no es APPROVED: skip, no marcar `enviado_at`, log `AGENDA_HOLD_PENDING_TEMPLATE`. El UUID que se pasa a la agenda es `public.meta_plantillas.id` (`db_record_id`).
- `RF-9` `refer_decision_maker(nombre, phone)`: validar PDV + plantilla APPROVED + teléfono; crear o reusar contacto en **ese** PDV; promover a primario; demotar el interlocutor a secundario; enviar HSM ya. Misma tool si hay otra objeción.
- `RF-10` Si el número nuevo ya es el primario de **ese** PDV: no duplicar; reenviar HSM (idempotente).
- `RF-11` Si el número nuevo pertenece a **otro** PDV: HTTP 409 / error de tool; no fusionar.
- `RF-12` HSM decisor: cuerpo de sistema *«Hola, {{1}} me pasó tu número. Te contacto de {{2}}. ¿Tenés un momento para hablar?»* (no empieza ni termina en variable; invita a responder). `{{1}}` = `nombre_de_pila` o `nombre` del referrer; `{{2}}` = `brand_name` o nombre de la distribuidora. Las llena `PdvService.refer_decision_maker` vía `decisor_hsm_body_params`. Si la plantilla del slot no tiene exactamente 2 params de body, error accionable y **sin** swap.
- `RF-12b` Provision: `ensure_decisor_encontrado_meta_template(schema)` crea `suplai_decisor_encontrado_v1` en el WABA si falta, upserta `public.meta_plantillas` (`variable_columns = ["referrer_nombre","distribuidora"]`) y setea el slot. Idempotente. No corre en el clone de schema (todavía no hay WABA).
- `RF-13` Tool opt-in (`OPT_IN_TOOL_NAMES`). Sin `true` en `tools_habilitadas` no se expone.

### Canales Places (Table A)

Fuente: [Place Types — Table A](https://developers.google.com/maps/documentation/places/web-service/place-types). Enum en `backend/services/prospeccion_place_types.py`.

- El operador **no** escribe queries. Elige chips del enum (sugeridos por LLM o buscados a mano).
- Búsqueda: `includedType` = id; `textQuery` = id.replace(`_`, ` `). Tope 8 tipos / 40 Places.
- Aliases v1 (copy comercial → Table A): `dietetica`→`health_food_store`, `kiosco`→`convenience_store`, `restaurante`→`restaurant`, `supermercado`→`supermarket`, `farmacia`→`pharmacy`, `escuela`→`school`, `gimnasio`→`gym`.
- Los 4 tipos viejos del modal (`convenience_store`, `restaurant`, `supermarket`, `school`) siguen válidos porque **son** IDs Table A.

Ranking suave (no excluye): en v1 el front manda siempre `tamano_pdv=barrio` (orden default rating → reviews). El backend aún acepta `grande`/`chico` por si se reactiva el selector. No hay hard-filter por tamaño.

---

## Requisitos no funcionales

- `RNF-1` Places: tope 40 resultados dedupeados; no paginar en v1; no pegarle a Google en CI.
- `RNF-2` Pooler 6543, `statement_cache_size=0`; outreach sin loop de altas: `PdvService.create_prospects_batch` inserta PDV + cliente + GPS y recompute de zona en una transacción.
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

### `AC-10` Sofía reusa o crea draft y agenda al aprobar

- **Given** paso 4 con contactos tildados.
- **When** el operador abre **Crear con Sofía**, usa **Ver plantillas existentes** y pulsa **Usar** en una APPROVED, o pide un borrador, pulsa **Revisar propuesta** y confirma en `CreateMetaTemplateModal`.
- **Then** la plantilla queda en el picker (UUID local). Si está PENDING, la fecha es hoy 10:00 (editable), el aviso dice 1–2 días y Enviar ahora está disabled. Al confirmar agenda, el cron no envía hasta APPROVED.

---

## Casos borde y errores

- `CB-1` Zona sin geometría / sin API key → 4xx/5xx claro; no se abre el paso 3 vacío como éxito.
- `CB-2` Zona sin vendedor → no toast de error: diálogo para elegir vendedor (asigna zona + clientes de sus PDV) y reintenta el outreach. Tenant sin lista pública → bloquear; no inventar `lista_precios_id=1`.
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

- **Backend** (`pytest`): enum Table A (retail in, geo out); expand alias→`includedType` + `textQuery` fijo; descarta IDs/texto inventados; suggest fallback sin OpenAI; LLM mock filtra IDs inventados; `merge_saved_icps` dedupe/cap 8; parse JSON de improve-icp; ranking suave; white-zones con body ICP (Places mock); outreach (incl. `ZONE_MISSING_VENDEDOR`, bind de `vendedor_id` y alta bulk de prospectos); refer-decision-maker; tests de config `metadata.prospeccion`; `agenda_sender` hold PENDING y envío APPROVED; provision `suplai_decisor_encontrado_v1` (cuerpo, params, skip sin WABA, reuse local).
- **Backoffice:** `tsc --noEmit`; checkbox disabled sin teléfono; PENDING agenda hoy; Usar en modal picker pega UUID.
- **Agente:** tool en registry + opt-in; payload; no-write si backend 4xx; AC-6/7 con HTTP mock.
- Checks existentes (Copilot 069, geo_zones, pdv secondary, agenda) **siguen verdes**.
- Gap: sin Playwright e2e obligatorio; Graph y Places mockeados.

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenant `demo` con zona, vendedor, lista pública, `GOOGLE_MAPS_API_KEY`. Slot primer contacto APPROVED. Decisor: plantilla de sistema `suplai_decisor_encontrado_v1` (APPROVED). Habilitar `refer_decision_maker` en `tools_habilitadas`.

1. Mapa → zona → zonas blancas → Cliente ideal “vendo suplementos; busco gimnasios de barrio y dietéticas” → **Mejorar con IA** (el texto se reescribe y queda en el combo de guardados) → **Sugerir canales** → tildar gym + dietética (u otros del enum) → buscar. Cerrar, reabrir: el último ICP está prellenado y se puede elegir otro guardado.
2. Tildar 2 con teléfono; dejar uno sin teléfono destildado. Elegir plantilla del pool (cambiar el default). **Enviar ahora**.
3. Verificar en clientes: 2 prospectos con GPS y `google_place_id`. Desde un WA de prueba, escribir a la línea de la distribuidora: entra el **agente comercial**, no el formulario de recepcionista.
4. Decir “las compras las hace {Nombre}” y pasar un número de prueba 2. La tool envía *“Hola, {NombreMaps} me pasó tu número. Te contacto de {distribuidora}. ¿Tenés un momento para hablar?”*. El PDV queda con el 2 como primario y el de Maps como secundario.
5. Repetir el wizard con **agendar** a +1 h: no sale HSM ahora; la agenda existe.
6. Chip/receta Copilot de barrio (069): sin regresiones; no se abre este wizard.
7. Paso 4 → **Crear con Sofía** → aviso 1–2 días → **Ver plantillas existentes** → **Usar** una APPROVED → preview y Crear Agenda. Repetir con **Proponer una nueva** → **Revisar propuesta** (no “Aceptar creación”) → editor. El picker muestra la PENDING, fecha **hoy** 10:00. Confirmar agenda. Copilot 069 / Juan no se abre. Copilot 1:1 Sofía: mismo botón Revisar propuesta; Lucía/Martín siguen Aceptar creación.
8. Zona **sin** vendedor principal → Crear Agenda. No sale toast de error: aparece el diálogo, se elige un vendedor, **Asignar y crear agenda** crea la agenda y deja al vendedor en la zona + clientes. El link **Ir a Notificaciones** cierra el wizard y abre esa sección. Tras un alta OK (con o sin diálogo): los pines blancos de Places desaparecen y los contactos aparecen como clientes en la zona.
9. Mapa → **Crear zona**: el formulario muestra **Vendedor de la zona**. Elegir uno existente y guardar: la zona queda con `vendedor_principal_id`. Repetir con **Crear vendedor nuevo** (nombre + teléfono): se crea el vendedor y queda asignado. **Sin asignar** sigue permitido.

---

## Observabilidad y rollback

- Logs estructurados en white-zones, outreach y refer-decision-maker.
- Rollback de producto: revertir PRs en orden inverso (agent → backoffice → backend); keys de metadata se pueden `null`.

---

## Riesgos

| Riesgo | Mitigación |
|--------|------------|
| Costo Places | Tope 40; un search por query del mapping; zona bbox no nearby infinito |
| Plantilla MARKETING PENDING | Enviar ahora y tool bloquean; el operador agenda hoy y el cron hold hasta APPROVED |
| Swap irreversible si Graph falla | Validar plantilla **antes** del write; post-Graph no rollback (el primario nuevo es el deseado) |
| Confusión con Copilot 069 | Spec 069 intacta; este flujo vive solo en el mapa |
