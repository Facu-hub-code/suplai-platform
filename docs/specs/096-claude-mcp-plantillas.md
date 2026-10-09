# 096 — Claude MCP: plantillas de WhatsApp

**Estado:** Borrador  
**Fecha:** 2026-10-08  
**Repos:** `backend-supabase` (tools, scope, preview), `suplai-sales-claude-plugin` (skills), `suplai-platform` (este spec)  
**Ramas sugeridas:** `feat/claude-mcp-plantillas` en backend y en el plugin  
**Serie:** [objetivos de capacidades](../claude-mcp/objetivos-capacidades.md), caso 2. El manual es el [094](./094-claude-mcp-manual.md). La carga es el [095](./095-claude-mcp-carga-clientes-productos.md). El grupo y la agenda que disparan el envío son el [097](./097-claude-mcp-grupos-agendas.md).  
**Relaciona:** `routers/plantillas_meta.py`, `models/plantillas_meta.py`, `services/promociones_service.py`, spec 087 (salud del número y métricas).

---

## Objetivo

El gerente le pide a Claude una plantilla para contactar o para promocionar. Claude explica para qué sirve, qué texto no se puede cambiar después, de qué columna sale cada variable y si una promo va a contradecir al agente. Muestra el texto. Recién con un sí, la crea en Meta. También puede decir cómo está el número y cómo rindieron las plantillas que ya existen.

Crear en Meta deja la plantilla en revisión. No queda enviable hasta que el estado sea aprobado. El envío masivo no es este spec: lo programa la agenda del 097.

### Métricas de éxito

- Una plantilla cuyo cuerpo nombra un precio o un descuento no se crea si no hay una promoción vigente para una lista concreta, con el SKU en catálogo y con stock mayor a 0.
- El cuerpo que el usuario vio en el preview es el que se manda a Meta. Un segundo confirm del mismo preview no crea otra.
- Ninguna tool edita el cuerpo de una plantilla ya creada.
- Las variables salen solo de la whitelist de columnas de `clients` (más `producto`).
- En `demo`, el preview de salud muestra cupo del día y calidad del número sin inventar un límite.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Quién redacta | Claude, en el chat. Al MCP llega el texto ya armado | El modelo conversa el tono. La tool valida reglas y llama a Meta. | Un `rewrite-body` del backend: ya existe y reescribe solo. El usuario no ve el prompt y el 094 quiere que la skill enseñe el criterio. |
| Escritura | `previsualizar_plantilla` y `confirmar_plantilla` | Mismo motivo que el 095: el preview queda guardado en el server y confirmar manda ese texto, no uno distinto que el modelo arme en el segundo llamado. | Un solo `crear_plantilla` y confiar en que Claude espere el sí. |
| Scope | `plantillas:escribir` | El consentimiento tiene que decir que ahora se crean plantillas en WhatsApp. `required_scopes` del servidor sigue siendo `pedidos:leer`. Las tools de este spec miran el scope adentro y, si falta, piden reconectar. | Un scope `plantillas:leer` aparte. Listar y medir son el paso previo a crear; una línea más en el consentimiento no cambia quién puede operar. |
| Lecturas | `listar_plantillas`, `columnas_plantilla`, `salud_whatsapp`, `metricas_plantillas`, mismo scope | Explicar y medir está en el objetivo y no escribe. Van en la misma familia para no abrir el conector a quien solo tiene `pedidos:leer`. | Reusar el `GET` del backoffice desde Claude con la cookie de sesión. |
| Listar sin efecto de más | La tool lee Meta y `public.meta_plantillas`. No llama `ensure_decisor_encontrado_meta_template` | El `GET /plantillas-meta` del backoffice intenta asegurar una plantilla global de decisor. Un “mostrame las plantillas” no puede crear una. | Llamar ese endpoint tal cual. |
| No se edita el cuerpo | No hay tool de update. El `PUT` local solo guarda categoría, motivo de rechazo y columnas, y Meta no acepta cambiar el texto | El objetivo lo prohíbe. Para otro texto se crea otra plantilla, con otro nombre. | Exponer el PUT y dejar que Claude “corrija” una aprobada. |
| Baja | Fuera de esta entrega | `DELETE /by-name` borra en Meta. Es irreversible y no hace falta para crear. | Una tool de baja en el mismo preview de alta. |
| Categoría | `contactar` → `UTILITY`. `promocionar` → `MARKETING`. `AUTHENTICATION` no se ofrece | Meta rechaza o recategoriza si el texto no coincide. El preview dice la categoría que se va a enviar. El usuario puede pedir la otra antes de confirmar; el server no la infiere del texto. | Elegir siempre MARKETING. Meta observa el uso de UTILITY y un recordatorio de visita no es una promo. |
| Nombre | El server lo deja en minúsculas y `_`, y el preview muestra el nombre final. Confirmar usa ese nombre guardado | Meta exige ese formato. Renombrar en silencio después del sí cambiaría lo que el usuario aceptó. | Rechazar `Promo Verano` y obligar al usuario a escribir `promo_verano`. |
| Variables | `variable_columns` en orden de `{{1}}`, `{{2}}`, … Solo nombres de `ALLOWED_CLIENT_COLUMNS` | Es la whitelist de `GET /columns-clients`: `phone_number`, `nombre`, `razon_social`, `codigo`, `dia_de_visita`, `dia_de_entrega`, `email`, `cuit`, `vendedor`, `producto`. Otra columna sale vacía en el envío. | Aceptar cualquier campo de `clients`. |
| Bordes del cuerpo | No puede empezar ni terminar en variable. Se reusa `meta_body_starts_or_ends_with_variable` | Meta lo rechaza. El preview lo dice antes de gastar el alta. | Descubrirlo recién en el 502 de Meta. |
| Forma del mensaje | Un solo componente `BODY` de texto. Sin imagen, carrusel ni botones | El alta con media pasa por upload a Meta y Storage. No es el pedido de esta v1. | El payload completo de `PlantillaMetaCreateMeta`. |
| Promoción | Si `objetivo = promocionar`, hace falta `promocion_id` de una promo vigente (`fecha_fin` posterior a hoy), con `lista_precios_id` o `codigo_cliente`, SKU `en_catalogo` y stock mayor a 0 en esa lista | Si la promo está en otra lista, o el SKU no se puede vender, el agente no la ve y el WhatsApp dice un precio que el chat no sostiene. Crear la promo es otro caso. | Crear la `promociones_semanales` desde esta tool. |
| Contactar | No exige promo. El preview avisa si el cuerpo trae un número que parece precio | Un recordatorio de visita no tiene lista. El aviso deja la decisión en el usuario; el server no adivina con una regex qué es un precio. | Rechazar cualquier dígito en un UTILITY. |
| Estado | Confirmar llama al `POST` que ya crea en Meta y, si Meta responde bien, inserta `public.meta_plantillas`. La respuesta dice que quedó en revisión y que no se puede agendar activa hasta `APPROVED` | Es el comportamiento actual del POST. Tratarla como enviable el mismo día miente. | Guardar solo en nuestra tabla y sincronizar después. |
| Fallo de Meta | Si Meta rechaza el alta, el preview no se consume | El usuario corrige el nombre o el texto y confirma de nuevo sin rearmar el lote a ciegas. | Consumir igual y obligar a otro preview idéntico. |
| Idioma | `es`, el default del modelo | Es el idioma de las plantillas de los tenants. | Pedirlo en cada alta. |
| Auditoría | `preview_id`, nombre normalizado, categoría, objetivo, `promocion_id`, resultado. Sin el cuerpo ni teléfonos en `parametros` | El cuerpo puede nombrar un comercio. `mcp_auditoria` no lleva ese texto. | Guardar el JSON que se manda a Meta. |
| Conexión | Servicios y pool de la API, no el rol `mcp_connector` | Ese rol no crea en Meta ni escribe `meta_plantillas`. | Darle INSERT al rol del conector. |

---

## Alcance

### Incluido

Cinco tools. Las de escritura van con `readOnlyHint = false`. `previsualizar_plantilla` es idempotente en el sentido de que no crea nada en Meta. `confirmar_plantilla` no lo es.

**`listar_plantillas`**

- Estado en Meta (`APPROVED`, `PENDING`, `REJECTED`, u otro que devuelva la WABA), nombre, categoría, idioma, id local si existe, y `variable_columns`.
- Omite las `suplai_global_*` que el listado del backoffice ya oculta, salvo que una estrategia del tenant las use.
- No crea la plantilla de decisor.

**`columnas_plantilla`**

- La whitelist, con el `name` y el rótulo que ya devuelve `columns-clients`.

**`salud_whatsapp`**

- Calidad, estado, si puede enviar, cupo del día, enviados hoy y restantes. Sale de `phone-health` / `outbound_guard`.
- Sin el número en la auditoría. En la respuesta al chat puede ir el cupo; no hace falta repetir el teléfono del negocio.

**`metricas_plantillas`**

- Enviados, entregados, leídos y respuestas por plantilla, la ventana que ya usa `GET /metrics` (1 a 89 días, default 30).
- Sin cuerpos de mensaje.

**`previsualizar_plantilla`**

- Entrada: `objetivo` (`contactar` o `promocionar`), `nombre`, `cuerpo`, `variable_columns`, y `promocion_id` si el objetivo es promocionar.
- Guarda el payload final 30 minutos: nombre normalizado, categoría, componente BODY, columnas, y el resumen de la promo si aplica.
- Respuesta: `preview_id`, el texto tal cual se va a enviar, la categoría, cada variable con su columna, y un veredicto de la promo (lista, vigencia, catálogo, stock) o el motivo de rechazo.
- Si falta la promo, la lista, el catálogo o el stock, no hay `preview_id`.
- No llama a Meta.

**`confirmar_plantilla`**

- Recibe solo `preview_id`.
- Crea en Meta con el payload guardado. Si Meta acepta, persiste la fila local y consume el preview en esa misma escritura local.
- La respuesta incluye el id local, el nombre y que el estado queda en revisión.

La skill `skills/plantillas-whatsapp/SKILL.md` enseña contactar versus promocionar, la regla promo ↔ lista ↔ stock, que el cuerpo no se edita, y que hay que esperar el sí. `skills/manual-conector/SKILL.md` suma estas tools y saca “plantillas” de la lista de “todavía no”. Grupos y agendas siguen en esa lista hasta el 097.

### Fuera de alcance

- Editar el cuerpo, la categoría o las columnas de una plantilla ya creada.
- Dar de baja una plantilla en Meta.
- Imagen de encabezado, carrusel, botones y `upload-sample-media`.
- `rewrite-body` y el envío de prueba a un cliente.
- Crear o editar `promociones_semanales`. Si no existe la promo, la tool explica qué falta y se detiene.
- Armar el grupo, la agenda o disparar el sender. Eso es el 097.
- Subir el cupo, comprar medios o conectar el token de WhatsApp.

---

## Orden de implementación

1. `backend-supabase`, rama `feat/claude-mcp-plantillas` desde `origin/main`. Migración de previews, scope, tools, tests.
2. Aplicar la migración en Suplai-east antes de probar el confirm en un entorno compartido.
3. Merge del backend.
4. `suplai-sales-claude-plugin`, misma rama: skills `plantillas-whatsapp` y el ajuste de `manual-conector`. Se mergea después, porque las skills nombran tools que tienen que existir.
5. Quien ya tenía el conector conectado vuelve a autorizar para recibir `plantillas:escribir`.

El 097 espera este spec: una agenda activa necesita una plantilla aprobada, y el preview de promo de acá es el que esa agenda va a citar.

---

## Migración de base de datos

`sql/147_mcp_accion_previews.sql` (el número libre siguiente si 147 ya existe). Tabla en `public`: el preview es de la sesión OAuth, no un dato del tenant.

```text
public.mcp_accion_previews
  id uuid PK
  usuario_id uuid
  distribuidora_id uuid
  schema_name text
  tipo text  -- en esta entrega solo 'plantilla'; el 097 suma 'grupo_agenda'
  payload jsonb          -- lo que confirmar va a ejecutar
  resumen jsonb          -- categoría, objetivo, conteos, id de promo; sin el cuerpo
  expires_at timestamptz
  consumed_at timestamptz null
  created_at timestamptz default now()
```

Índice por `expires_at`. No hay job de limpieza: previsualizar y confirmar ignoran vencidos o consumidos.

RLS activo. `REVOKE ALL` a `anon` y `authenticated`. Sin GRANT para `mcp_connector`. La escribe el rol de la API.

El check de `tipo` nace con `plantilla`. El 097 lo amplía en su migración. No se reutiliza `mcp_carga_previews`: ese check es `clientes | productos` y el payload de una plantilla no es una lista de filas.

Sin cambio de columnas de tenant ni de `public.meta_plantillas`.

Rollback: `DROP TABLE public.mcp_accion_previews`. No borra plantillas ya creadas en Meta.

---

## Plan de prueba en CI/CD

En `backend-supabase`, pytest junto a `tests/test_mcp_carga.py` y `tests/test_mcp_tool_schema.py`:

- Scope ausente → la tool responde que hay que reconectar y no llama a Meta.
- Cuerpo que empieza o termina en `{{1}}` → sin `preview_id`.
- Columna fuera de la whitelist → sin `preview_id`.
- `promocionar` sin promo, con promo vencida, con SKU fuera de catálogo o con stock 0 → sin `preview_id` y el motivo nombra qué falta.
- `contactar` sin promo → hay preview, categoría `UTILITY`.
- El nombre `Promo Verano` queda `promo_verano` en el payload guardado.
- Confirmar un preview vencido, ajeno o ya consumido → cero llamadas a Meta.
- Si el cliente de Meta falla, `consumed_at` sigue null.
- Confirmar no arma un componente que no sea BODY.
- `listar_plantillas` no invoca `ensure_decisor_encontrado_meta_template`.
- La auditoría no incluye el cuerpo.
- Annotations y el scope en el schema de las tools.

El `POST` real a Graph API se mockea. El CI (`pytest`) tiene que seguir verde.

Gap: el plugin no tiene CI. El PR del plugin se revisa a mano contra las tools del backend ya mergeado.

---

## Plan de prueba humana

Tenant `demo`. No usar un tenant de un cliente. Claude reconectado, con el permiso de plantillas visible en el consentimiento. Backend en el puerto `8000` y MCP en el `8100` si la prueba es local; si es el conector de producción, alcanza con el deploy de los dos servicios.

El confirm de esta prueba crea una plantilla real en la WABA de `demo` y Meta la deja en revisión. Usar un nombre que se note de prueba, por ejemplo `demo_claude_visita`.

Pasos:

1. “¿Cómo está el WhatsApp?” muestra calidad y cupo del día, no un límite inventado.
2. “¿Qué plantillas tengo?” lista nombres y estados. No aparece una plantilla nueva de decisor que antes no estaba.
3. Pedir un texto para avisar la visita del día, con el nombre del comercio. Ver el preview: categoría utilidad, variable `razon_social` o `nombre`, y el nombre ya normalizado.
4. Decir que no. En Meta y en `public.meta_plantillas` no está ese nombre.
5. Pedir el mismo texto y decir que sí. La respuesta dice que quedó en revisión.
6. Pedir confirmar otra vez. No se crea una segunda.
7. Pedir una plantilla que nombre un descuento, sin una promo vigente del `demo` para esa lista. El preview se niega y dice qué falta (promo, lista, catálogo o stock).
8. “Cambiale el texto a la que acabamos de crear.” Claude explica que hay que hacer otra con otro nombre, y no llama una tool de edición.

OK: lo rechazado no existe en Meta, lo confirmado existe una sola vez y sigue en revisión, y el manual ya no dice que las plantillas están pendientes.
