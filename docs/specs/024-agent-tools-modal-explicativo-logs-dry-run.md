# Spec 024 — Modal explicativo de herramientas: ficha + logs + prueba (dry-run)

**Estado:** En progreso
**Fecha:** 2026-07-11
**Autor:** Facundo + agente
**Tipo:** Cross-repo (backoffice + backend + agente)
**Predecesor:** Spec 057 (backoffice) — Canvas blueprint de tools

**Implementación en curso (ramas):**
| Repo | Rama |
|------|------|
| agente | `feat/agent-tools-exec-persist-dryrun` |
| backend | `feat/agent-tools-editorial-logs-api` |
| backoffice | `feat/agent-tools-modal-explicativo` |

---

## Objetivo

Convertir el modal de configuración de una herramienta del agente (hoy `tool-config-modal.tsx`, editable pero puramente técnico) en una **herramienta de comprensión y prueba para implementadores no técnicos**. El modal debe responder tres preguntas sin soporte de ingeniería:

1. **¿Qué hace esta herramienta y cuándo la usa el agente?** (ficha explicativa)
2. **¿Qué pasó con ella?** (logs de ejecución del tenant)
3. **¿Puedo probarla sin romper nada?** (ejecución en simulación / dry-run)

Además debe explicar dos comportamientos que hoy son opacos para el usuario: la **respuesta custom/determinista** (por qué a veces el agente no redacta libremente sino que devuelve un texto canónico) y los **guards** (reglas que fuerzan a ejecutar una tool o secuencia).

Se alinea con el modelo de negocio: cualquier implementador con licencia Suplai debe poder entender y configurar el agente de forma autónoma.

## Contexto (estado actual)

- Metadata técnica ya disponible en `GET /{schema}/distribuidora/config/tools`: `tools_input_schemas`, `tools_meta` (`agent_groups`, `guards`, `deterministic_profiles`, `field_only`, `shared`), `assistant_channels`, `default_tool_descriptions`, config del tenant (`tools_descripciones`, `tools_habilitadas`, `tools_mensajes_post_success`).
- **Falta** una capa **editorial** (nombre humano, cómo funciona, cuándo usarla, outputs, efectos secundarios, prerrequisitos) → se resuelve con tablas globales en `core` (decisión previa).
- **Logs**: hoy las tool calls van a Loki (nombre + latencia, **sin args**) y solo se persisten con detalle en `core.agent_tool_runs` cuando `trace_enabled=true`. Para el modal se define **persistencia liviana siempre activa** en una tabla nueva.
- **Prueba**: no existe harness para ejecutar una tool aislada. Se define **dry-run read-only** (sin efectos secundarios).

## Decisiones de diseño técnico

| Tema | Decisión | Por qué (alternativa descartada) |
|---|---|---|
| Capa editorial de tools | Tablas globales en `core`, sembradas por SQL | Editable a futuro desde admin sin redeploy del agente. Descartado: dump JSON solo desde código (cada cambio de texto exige PR/deploy). |
| Fuente de logs del modal | Persistencia liviana siempre activa en `core.agent_tool_executions` (todos los tenants) | El modal necesita datos sin activar `trace_enabled`. Descartado: solo Loki (sin args/resumen usable, dependencia de retención) y solo `agent_tool_runs` (caro y opt-in). |
| Qué se guarda en el log | Resumen + status + latencia + `request_id` — **sin args ni PII** | Calidad en el canvas/modal sin basura ni riesgo de datos sensibles. El detalle con args sigue detrás de `trace_enabled`. |
| Escritura del log | Best-effort asíncrona tras la respuesta | Requisito duro: no sumar latencia al turno del agente. |
| Semántica de "probar" | Dry-run / simulación con rollback + stubs de side-effects externos | Tools de escritura tocan BD real; ejecución real es inaceptable en v1. Descartado: sandbox de cliente de prueba (más infra) y ejecución real. |
| Alcance de los logs mostrados | Todas las ejecuciones de la tool en el tenant (reales + dry-run marcado) | El implementador ve uso real, no solo ensayos del modal. |
| Casos de uso (workflows) | **Diferidos** a una versión posterior | Esta entrega se concentra en el modal explicativo + logs + dry-run. |
| Piloto editorial / dry-run | Flujo de pedidos (client + seller) | Acotar riesgo y seed; el resto se completa incrementalmente. |)

## Alcance

### Incluido (v1)

- **Capa editorial** en `core.agent_tools` (piloto: tools del flujo de pedidos; el resto se completa incrementalmente).
- **Persistencia liviana** de cada ejecución de tool en `core.agent_tool_executions` (real + dry-run), best-effort sin impactar la latencia del turno.
- **API backend**: enriquecer `config/tools` con la ficha editorial; endpoint de logs por tool; endpoint de dry-run.
- **Dry-run en el agente**: ejecución de una tool con `ToolContext.dry_run=True`, dentro de transacción con rollback garantizado y con side-effects externos stubbeados.
- **Modal rediseñado** (backoffice) según el mockup provisto, con secciones: ficha, estructura de datos (inputs/outputs), efectos y prerrequisitos, **comportamiento en el flujo (guards + respuesta determinista)**, mensaje de éxito editable, logs de ejecución y botón "Probar (simulación)".

### Fuera de alcance (v1)

- Casos de uso / workflows (secuencias de tools).
- Ejecución real (no simulada) desde el modal.
- Editar guards, `agent_groups` o canal determinista desde la UI (siguen definidos por código / config general).
- Editar la ficha editorial desde la UI (v1 se siembra por SQL; pantalla admin es futura).
- Streaming/live tail de logs (v1 es fetch on-demand + refresh manual).

---

## Modelo de datos

### 1. Catálogo editorial — `core.agent_tools` (global)

```sql
CREATE TABLE core.agent_tools (
  tool_name              text PRIMARY KEY,          -- debe existir en ALL_AGENT_TOOL_NAMES
  display_name           text NOT NULL,             -- "Crear pedido"
  category               text NOT NULL,             -- pedidos | catalogo | clientes | entrega | field | registro | soporte
  icon                   text,                       -- Material Symbol name, ej "shopping_cart"
  short_description      text NOT NULL,             -- 1 línea para no-técnicos
  how_it_works           text,                       -- "Cómo funciona" (bloque del modal)
  when_to_use            text,                       -- "Cuándo usarla" (bloque del modal)
  outputs                jsonb NOT NULL DEFAULT '[]',   -- [{ "name", "description", "user_facing": bool }]
  side_effects           jsonb NOT NULL DEFAULT '[]',   -- ["Modifica el pedido abierto", "Notifica al ERP"]
  prerequisites          jsonb NOT NULL DEFAULT '[]',   -- ["Cliente resuelto en la sesión", "Sesión de auth válida"]
  read_only              boolean NOT NULL DEFAULT true, -- false => badge "Write Access"
  deterministic_note     text,                       -- explicación editorial de la respuesta determinista
  status                 text NOT NULL DEFAULT 'active', -- active | hidden | deprecated
  sort_order             int NOT NULL DEFAULT 0,
  updated_at             timestamptz NOT NULL DEFAULT now()
);
```

> Los campos técnicos (`inputs`, `guards`, `agent_groups`, `deterministic_profiles`, `field_only`, `opt_in`) **no se duplican**: siguen viniendo del dump del código (`agent_tools_catalog_meta.json` / `agent_tools_input_schemas.json`) y la API los une por `tool_name`.

### 2. Logs de ejecución — `core.agent_tool_executions` (global, siempre activa)

```sql
CREATE TABLE core.agent_tool_executions (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id        uuid NOT NULL,
  schema_name      text NOT NULL,
  tool_name        text NOT NULL,
  request_id       text,                       -- correlación con Loki y conversation_events
  conversation_id  uuid,
  session_id       text,
  actor_type       text,                       -- client | seller | reception
  status           text NOT NULL,              -- success | error
  summary          text,                       -- resumen humano ("Pedido #4521 creado")
  error_summary    text,                       -- si status = error
  latency_ms       integer,
  is_dry_run       boolean NOT NULL DEFAULT false,
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_agent_tool_exec_tenant_tool_time
  ON core.agent_tool_executions (tenant_id, tool_name, created_at DESC);
```

**Retención:** job de limpieza (cron/pg) que conserva, p. ej., los últimos 90 días o las últimas N filas por `(tenant_id, tool_name)`. Evita crecimiento ilimitado. Definir umbral final en implementación.

**Derivación de `summary`:** del `ToolResult` de la tool (`user_facing_message` truncado, o fallback por status). No persiste argumentos ni PII sensible en v1 (solo resumen). El detalle completo con args sigue siendo dominio de `core.agent_tool_runs` (trace_enabled).

### Seed editorial — piloto flujo de pedidos

Se siembran por SQL las fichas de: `search_products`, `search_products_by_category`, `get_product_by_code`, `get_catalog_link`, `create_order`, `edit_order`, `suggest_order_boost`, `list_promotions`, `get_open_order_status`, `confirm_order` (cliente) y `set_seller_selected_client`, `get_seller_client_details`, `load_seller_order_text`, `edit_order_for_client`, `suggest_order_boost_for_client`, `get_open_order_status_for_client`, `confirm_order_for_client` (vendedor).

Ejemplo (`create_order`):

```json
{
  "tool_name": "create_order",
  "display_name": "Crear pedido",
  "category": "pedidos",
  "icon": "shopping_cart",
  "short_description": "Arma o suma ítems al pedido abierto del cliente actual.",
  "how_it_works": "Procesa la lógica de SKU + cantidad, valida existencias en tiempo real y asigna precios según la lista del cliente. Reutiliza el pedido abierto si existe o crea uno nuevo.",
  "when_to_use": "Cuando el cliente expresa intención de compra clara ('dame', 'quiero', 'necesito' + producto/cantidad) o pregunta '¿cuánto sería de...?'.",
  "outputs": [
    { "name": "resumen_pedido", "description": "ID del pedido, total acumulado y lista de errores de stock si los hubiera.", "user_facing": true }
  ],
  "side_effects": ["Modifica el pedido abierto en la BD de ventas", "Crea un registro nuevo si no existe uno previo"],
  "prerequisites": ["Cliente resuelto en la sesión", "Sesión de auth válida"],
  "read_only": false,
  "deterministic_note": "Con canal determinista de cliente activo, el resumen del pedido se muestra con el texto canónico de la herramienta y no lo reescribe el modelo."
}
```

---

## Backend (`backend-supabase`)

### Endpoints

1. **`GET /{schema}/distribuidora/config/tools`** — extender la respuesta con la ficha editorial por tool:

```jsonc
{
  // ...campos actuales...
  "tools_editorial": {
    "create_order": {
      "display_name": "Crear pedido",
      "category": "pedidos",
      "icon": "shopping_cart",
      "short_description": "...",
      "how_it_works": "...",
      "when_to_use": "...",
      "outputs": [ ... ],
      "side_effects": [ ... ],
      "prerequisites": [ ... ],
      "read_only": false,
      "deterministic_note": "..."
    }
  }
}
```

2. **`GET /{schema}/distribuidora/tools/{tool_name}/executions?limit=20`** — logs recientes:

```json
{
  "tool_name": "create_order",
  "executions": [
    { "id": 991, "status": "success", "summary": "Pedido #4521 creado", "latency_ms": 1200, "is_dry_run": false, "created_at": "2026-07-11T14:05:00Z", "request_id": "..." },
    { "id": 990, "status": "error", "summary": "Falla de validación de stock", "error_summary": "SKU 0012 sin existencias", "latency_ms": 800, "is_dry_run": false, "created_at": "2026-07-11T13:55:00Z" }
  ]
}
```

3. **`POST /{schema}/distribuidora/tools/{tool_name}/dry-run`** — proxya al agente (ver abajo). Body: `{ "args": { ... }, "actor_type": "client" }`. Respuesta: resultado de la simulación (sin persistir writes).

### Persistencia liviana

El agente escribe directo en `core.agent_tool_executions` (tiene acceso a BD). El backend **solo lee** de esa tabla para los endpoints. Respetar reglas de pooling (puerto 6543, `statement_cache_size=0`, pool mínimo).

### Sincronización catálogo

Extender el `POST .../config/tools/backfill` (o el script de mirror) para **validar** que todo `core.agent_tools.tool_name` exista en `ALL_AGENT_TOOL_NAMES` y reportar fichas faltantes u huérfanas. No bloquea deploy.

---

## Agente (`agente-conversacional-multi_tenant`)

### 1. Persistencia liviana siempre activa

Nuevo wrapper (o extensión de `implementation_trace.wrap_tools_for_implementation_trace`) que, **para todos los tenants**, tras cada tool call encola una fila en `core.agent_tool_executions` con: `tenant_id`, `schema_name`, `tool_name`, `request_id`, `conversation_id`, `session_id`, `actor_type`, `status`, `summary` (derivado del `ToolResult`), `error_summary`, `latency_ms`, `is_dry_run=false`.

**Performance (requisito duro):** la escritura **no debe agregar latencia al turno**. Se hace best-effort de forma asíncrona (task en background / cola acotada, flush tras enviar la respuesta al usuario). Si falla, se loguea y se descarta — nunca rompe el turno. Reutiliza el pool existente; no abre conexiones por evento.

### 2. Ejecución en simulación (dry-run)

Nuevo endpoint autenticado (bearer `OBSERVABILITY_BEARER_TOKEN` o equivalente):

`POST /tools/dry-run` → `{ tenant_id, schema_name, tool_name, args, actor_type, session_id? }`

Comportamiento:

1. Construye `ToolContext` con nuevo flag **`dry_run=True`**.
2. Ejecuta la tool dentro de una **transacción/`SAVEPOINT` que siempre se hace `ROLLBACK`**, de modo que ninguna escritura persista.
3. Los side-effects **externos** (notificación ERP, envío WhatsApp, HTTP a terceros, generación de links con efecto) deben cortocircuitarse cuando `ctx.dry_run` es `True` y devolver un valor simulado documentado.
4. Devuelve el `ToolResult` (incluye `user_facing_message` y payload), `status`, `latency_ms`, y un flag `persisted=false`.
5. Registra la ejecución en `core.agent_tool_executions` con `is_dry_run=true` para que aparezca en los logs del modal.

**Cobertura v1:** el dry-run se garantiza para las tools del piloto (flujo de pedidos). Cada tool declara si honra `dry_run`; las que aún no lo honran se muestran en el modal con el botón "Probar" deshabilitado y un tooltip explicativo.

### 3. Scaffolding editorial

Script tipo `dump_*` opcional que genere el **esqueleto** de `core.agent_tools` (una fila por tool del registry con campos vacíos) para facilitar el seed SQL y detectar tools sin ficha.

---

## Frontend / Modal (`product-management-app`)

Rediseño de `tool-config-modal.tsx` siguiendo el mockup (estética Material: tokens de color provistos, Inter + JetBrains Mono para `code`, Material Symbols). Secciones, de arriba a abajo:

| # | Sección | Fuente de datos | Editable |
|---|---------|-----------------|----------|
| Header | Ícono + `display_name` + badge categoría + badge Write/Read Access + `ID: tool_name` | editorial + `read_only` | No |
| 1 | **Descripción del Agente** (con contador de tokens + "Restaurar default" + aviso de descripción custom) | `tools_descripciones` / `default_tool_descriptions` | Sí |
| 2 | **Cómo funciona** / **Cuándo usarla** (grid 2 col) | `how_it_works`, `when_to_use` | No |
| 3 | **Estructura de datos**: Inputs (nombre, tipo, requerido/opcional) + Outputs | `tools_input_schemas` + editorial `outputs` | No |
| 4 | **Efectos secundarios** / **Prerrequisitos** (grid 2 col) | editorial `side_effects`, `prerequisites` | No |
| 5 | **Comportamiento en el flujo** (NUEVA): Guards + Respuesta determinista | `tools_meta.guards`, `deterministic_profiles`, `assistant_channels`, `deterministic_note` | No |
| 6 | **Mensaje de éxito** (respuesta custom que se anexa al ejecutarse) | `tools_mensajes_post_success` | Sí |
| 7 | **Logs de ejecución** + botón **Probar (simulación)** | `.../executions` + `.../dry-run` | Acción |
| Footer | Cancelar / Guardar cambios | — | — |

### Sección 5 — Comportamiento en el flujo (nueva, requerida por el usuario)

Bloque unificado, read-only, que explica en lenguaje simple:

- **Guards** — por cada guard de `tools_meta[tool].guards`, mostrar `label` + `description`, con un texto introductorio: *"Un guard es una regla que obliga al agente a ejecutar esta herramienta (o una secuencia) en ciertos casos, aunque el modelo no lo decida solo."* Si no hay guards, ocultar el subbloque o mostrar "Sin guards".
- **Respuesta determinista** — si `deterministic_profiles` no está vacío, explicar: *"Cuando el canal determinista está activo para [perfil(es)], la respuesta al usuario no la redacta el modelo: se muestra el texto canónico de la herramienta. Esto garantiza consistencia y evita alucinaciones."* Indicar además, con `assistant_channels`, si el tenant lo tiene **activo o inactivo** hoy (badge), con deeplink a Configuraciones Generales. Complementar con `deterministic_note` editorial si existe.

### Sección 7 — Logs + Probar

- Lista de ejecuciones (badge Éxito/Error, `summary`, "hace X", latencia). Dry-runs con badge adicional "Simulación". Orden: recientes primero. Botón "Ver más" / refresh.
- Botón **"Probar (simulación)"**: abre un formulario inline generado desde `tools_input_schemas` (respetando tipos/enums/requeridos). Al enviar, llama al proxy de dry-run, muestra el `user_facing_message` + payload resultante y un aviso claro *"Simulación — no se guardó ningún cambio"*, y refresca la lista de logs. Deshabilitado (con tooltip) para tools que no honran `dry_run` en v1.

### Proxies Next.js (backoffice)

- `GET /api/tools-config` — ya existe; heredará `tools_editorial`.
- `GET /api/tools-config/executions?tool=...` → backend `.../tools/{tool}/executions`.
- `POST /api/tools-config/dry-run` → backend `.../tools/{tool}/dry-run`.

---

## Plan cross-repo (orden de merge)

| Orden | Repo | Rama | Contenido | PR |
|------|------|------|-----------|----|
| 1 | `agente-conversacional-multi_tenant` | `feat/agent-tools-exec-persist-dryrun` | Persistencia liviana + `ToolContext.dry_run` + endpoint `/tools/dry-run` + scaffolding editorial | — |
| 2 | `backend-supabase` | `feat/agent-tools-editorial-logs-api` | Migración `core.agent_tools` + `core.agent_tool_executions` + seed piloto + endpoints (config enriquecido, executions, dry-run proxy) | — |
| 3 | `product-management-app` | `feat/agent-tools-modal-explicativo` | Rediseño del modal + proxies | — |

Migraciones y seed viven en `backend-supabase`. El agente escribe en las tablas; backend lee.

---

## Migración de base de datos

**Sí hay migración** (en `backend-supabase`):

1. Crear `core.agent_tools` (catálogo editorial global).
2. Crear `core.agent_tool_executions` + índice `(tenant_id, tool_name, created_at DESC)`.
3. Seed SQL del piloto (tools del flujo de pedidos).
4. Job/nota de retención para `agent_tool_executions` (umbral a fijar en implementación, p. ej. 90 días).

**Orden:** migración + seed en el PR del backend **antes** de que el agente empiece a escribir y antes de que el backoffice consuma `tools_editorial`.  
**Rollback:** drop de tablas nuevas (sin datos de negocio críticos en v1; el seed es reprocesable). No altera tablas de pedidos/clientes.

---

## Plan de prueba en CI/CD

| Repo | Qué debe quedar verde en el PR |
|------|--------------------------------|
| **Agente** | Tests unitarios del wrapper de persistencia (mock de pool: encola y no bloquea el turno). Test del dry-run: tool de escritura (`create_order` o stub) con `dry_run=True` → resultado OK y **assert de que no quedó fila/pedido**. Test de stub de side-effect externo. |
| **Backend** | Test de migración (aplica limpio). Test del GET `config/tools` incluye `tools_editorial` cuando hay seed. Test del GET executions (filtro por tool + orden). Test del proxy dry-run (mock al agente). Backfill reporta fichas huérfanas/faltantes. |
| **Backoffice** | Build/lint del modal. Test de render de secciones (ficha, guards/determinista, lista de logs) con fixtures. Proxy routes con mock del backend. |

**Gap aceptable v1:** e2e browser completo del dry-run puede quedar como manual si el CI no tiene agente+BD; en ese caso el PR **MUST** documentar el checklist humano abajo y dejar evidencia (capturas o nota en el PR).

Checks existentes de cada repo (lint, typecheck, tests suite) **MUST** seguir verdes; no mergear con checks rojos.

---

## Plan de prueba humana (antes del PR)

### Prerrequisitos locales

| Servicio | Puerto | Notas |
|----------|--------|-------|
| Backend | `8000` | `uvicorn` con migración aplicada + seed |
| Backoffice | `3000` | `BACKEND_URL=http://localhost:8000` |
| Agente | según env local | dry-run + persistencia liviana desplegados |

Tenant de prueba con tools de pedidos habilitadas (ej. `demo` o el que use el implementador).

### Checklist — ficha y modal

1. Abrir Configuración del agente → pestaña Herramientas → canvas.
2. Click en `create_order` (o "Crear pedido").
3. Verificar: display name, categoría, badge Write Access, ID técnico.
4. Verificar bloques: descripción (tokens + restaurar), cómo funciona / cuándo usarla, inputs/outputs, efectos / prerrequisitos.
5. Verificar sección **Comportamiento en el flujo**: si la tool tiene guards, se listan; si tiene perfiles deterministas, se explica y se ve si el canal del tenant está activo (deeplink a Config. Generales).
6. Editar mensaje de éxito → Guardar → recargar → persiste. Restaurar descripción default funciona.

### Checklist — logs

7. Generar al menos una ejecución real (mensaje WhatsApp/lab que dispare la tool) o esperar datos existentes.
8. Abrir el modal → sección Logs: aparece resumen, estado, latencia, orden reciente primero.
9. Confirmar que **no** se muestran argumentos crudos ni texto del usuario.

### Checklist — dry-run (crítico)

10. En `create_order`, click **Probar (simulación)** → completar args mínimos válidos → ejecutar.
11. Ver resultado + aviso "Simulación — no se guardó ningún cambio".
12. En BD del tenant: **ningún** pedido nuevo / ítem nuevo atribuible a esa prueba.
13. En logs del modal: aparece entrada con badge **Simulación**.
14. Tool sin dry-run habilitado: botón deshabilitado + tooltip.

### Checklist — performance (smoke)

15. Un turno normal del agente no se siente más lento; si falla la escritura del log, el turno igual responde (revisar log del agente: warning, no error fatal).

---

## Criterios de aceptación

- [ ] `core.agent_tools` y `core.agent_tool_executions` creadas por migración en `backend-supabase`.
- [ ] Seed editorial de las tools del flujo de pedidos aplicado.
- [ ] Cada tool call real persiste una fila en `core.agent_tool_executions` sin agregar latencia perceptible al turno.
- [ ] `GET config/tools` devuelve `tools_editorial`.
- [ ] El modal muestra ficha completa (descripción, cómo funciona, cuándo usarla, inputs, outputs, efectos, prerrequisitos).
- [ ] El modal muestra la sección "Comportamiento en el flujo" con guards y explicación de respuesta determinista, indicando si está activa en el tenant.
- [ ] El modal lista los logs de ejecución de la tool (recientes primero, con estado y latencia).
- [ ] El botón "Probar (simulación)" ejecuta un dry-run sin efectos secundarios, muestra el resultado y lo agrega a los logs marcado como simulación.
- [ ] Ninguna escritura del dry-run persiste (verificado con una tool de escritura como `create_order`).
- [ ] El backfill valida coherencia entre `core.agent_tools` y `ALL_AGENT_TOOL_NAMES`.

## Riesgos y notas

- **Latencia del agente:** la persistencia liviana debe ser estrictamente best-effort/asíncrona. Cualquier bloqueo síncrono es un no-go.
- **Seguridad del dry-run:** el rollback de transacción cubre writes a la BD del tenant, pero los side-effects externos (ERP, WhatsApp, links) deben stubbearse explícitamente por tool. Auditar tool por tool antes de habilitar su botón "Probar".
- **PII / storage:** `agent_tool_executions` guarda solo resumen, no args ni texto de usuario. El detalle con args sigue detrás de `trace_enabled`.
- **Retención:** definir umbral de limpieza para no inflar `core`.
- **Consistencia editorial:** al agregar/renombrar tools en el código, hay que actualizar el seed; el backfill lo detecta pero no lo corrige solo.
