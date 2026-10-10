# 100 — Sección del prompt: si la búsqueda no coincide

**Estado:** Borrador  
**Fecha:** 2026-10-10  
**Repos:** `agente-conversacional-multi_tenant` (turno de laboratorio con prompt en memoria), `backend-supabase` (tools, receta, arreglo del diagnóstico)  
**Ramas sugeridas:** `feat/seccion-prompt-lab` en el agente, `feat/seccion-prompt` en el backend  
**Relaciona:** [099](./099-claude-mcp-estrategias-aliases.md) (el prompt quedaba en el backoffice), `services/system_prompt_builder.py`, `probar_agente`, `diagnosticar_busqueda`.

---

## Objetivo

Claude puede agregar o reemplazar un solo párrafo del prompt del tenant, el de «si la búsqueda no coincide», para que el agente diga que no trabaja un producto en lugar de listar los cinco más cercanos. Ve el prompt completo que el agente arma en runtime, recibe un aviso corto de qué implica ese párrafo, ensaya el turno sin WhatsApp y recién después confirma.

El resto del `system_prompt` y el prompt base compartido no se escriben.

### Métricas de éxito

- En Demo, un ensayo de «quiero una coca» con la vista previa todavía no guardada responde que no lo trabajan, y no presenta otros SKU como si fueran gaseosa.
- Confirmar no cambia ninguna otra sección del `system_prompt` de Demo.
- Si el prompt cambió entre la vista previa y la confirmación, no se escribe.
- `diagnosticar_busqueda` con un producto esperado deja de devolver error 500 por la columna `alias`.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Qué se edita | Solo el cuerpo bajo el título fijo `## Si la búsqueda no coincide` dentro de `public.distribuidoras.system_prompt` | El agente inventa porque `search_products` devuelve vecinos reales y el prompt actual («no inventes productos») no le dice que los descarte. Una sección alcanza. El 099 dejó el prompt en el backoffice para no reescribirlo entero. | Reescribir todo el `system_prompt`. Una columna nueva. Editar cualquier título existente. |
| Si el título no está | La vista previa lo agrega al final del prompt del tenant | Demo no tiene esa sección. Pegarla al final no reordena lo que ya funciona. | Insertarla en el medio, junto a «Unidades y catálogo». Más fácil pisar otra sección. |
| Prompt base | No se escribe. `agent_base_prompt_client` y `agent_base_prompt_seller` quedan quietos | Ahí viven pedidos, totales y tools. Un párrafo de catálogo no tiene que tocarlos. | Dejar que Claude edite el base «con cuidado». |
| Prompt completo | `ver_seccion_prompt` y la vista previa arman el system prompt del turno de cliente con `build_system_prompt` (base, unidades, entrega si está activa, perfil del tenant ya con la sección nueva) | Claude tiene que ver lo que el modelo lee, no solo el párrafo, para no repetir ni contradecir. | Mostrar solo la sección. Incluir descripciones de tools, pedido abierto y ficha del cliente: cambian por turno y meten ruido. |
| Aviso | Texto fijo, corto, en la lectura, en la vista previa y en la receta | La persona tiene que saber que suma un párrafo a cada mensaje. Sin tono de alarma. | Un checklist largo de la auditoría de prompts. Un bloqueo si el texto «parece peligroso». |
| Choque | Si una línea del párrafo nuevo, de 20 caracteres o más, en minúsculas y sin acentos, ya está en el prompt base o en otra sección del tenant, la vista previa lo dice y deja confirmar | Repetir una regla baja la atención del modelo. Bloquear asusta y corta un texto que igual puede servir. | Rechazar el preview. Ignorar el solapamiento. |
| Tope y forma | Texto obligatorio, hasta 800 caracteres, sin líneas que empiecen con `#` | Un título adentro partiría el parser y podría comerse la sección siguiente. 800 alcanza para una idea. | Sin tope. Aceptar markdown con subtítulos. |
| Integridad | Después de armar, cada otra sección `## ` queda byte a byte igual. Confirmar guarda solo si el sha256 del `system_prompt` actual coincide con el de la vista previa | Un parser flojo o un edit en el backoffice en el medio no pueden pisar el resto. | Confirmar igual y «resolver conflictos». |
| Modo v2 | Si `metadata.use_new_system_prompt` no es true, la tool no escribe | En legacy el runtime no usa `system_prompt`. Escribir ahí no cambia al agente. | Escribir igual. |
| Ensayo | `probar_agente` acepta `preview_id`. El backend manda el `system_prompt` ya armado al laboratorio. El agente hace `replace` del tenant en memoria y no lo persiste. El preview no se consume | Ensayar antes de guardar tiene que usar la regla nueva. Hoy el laboratorio lee el prompt grabado. Claude no manda un prompt suelto: solo uno que ya pasó la vista previa. | Confirmar y después ensayar. El párrafo malo queda en WhatsApp. `extra_system` pegado al final: si la sección ya existe, el modelo lee las dos. |
| Permiso | `laboratorio:usar` en ver, previsualizar, confirmar y en el ensayo | Es el permiso con el que ya ensayan al agente. Confirmar igual escribe el prompt de WhatsApp: la receta lo dice. | Un scope nuevo. Obliga a reconectar Claude antes de probar esta entrega. |
| Diagnóstico | `productos_aliases` se lee con `alias_raw` y, si viene vacío, `alias_norm` | La tool pide la columna `alias` y el 500 es `UndefinedColumnError`. No es la clave de OpenAI. | Dejar el 500 para otro PR. El ensayo de búsqueda sigue ciego. |
| Preview | Tipo `seccion_prompt` en `mcp_accion_previews`, mismo vencimiento que el resto | Confirmar dos veces no vuelve a escribir. | Un update directo. |

---

## Alcance

### Incluido

**Lectura y edición** (`laboratorio:usar`)

- `ver_seccion_prompt`. Devuelve `seccion` (texto actual o vacío), `presente`, `prompt_completo` y `aviso`.
- `previsualizar_seccion_prompt` con `texto`. No escribe `distribuidoras`. Devuelve `preview_id`, el antes, el después, `prompt_completo` ya con la sección, `aviso`, `choque` (o null) y `siguiente_paso`.
- `confirmar_seccion_prompt` con `preview_id`. Hace `UPDATE` de `system_prompt` nada más. Rechaza si el hash no coincide, si el preview no es de este usuario y esta distribuidora, o si venció.

**Ensayo**

- `probar_agente` suma `preview_id` opcional. Sin ese id, el comportamiento actual no cambia.
- `POST /implementation-lab/simulate-turn` acepta `system_prompt` opcional. Si viene, ese texto reemplaza `tenant.system_prompt` solo en ese turno. Tope 20_000 caracteres. No hay `UPDATE`.

**Receta** `mcp_server/guias/seccion-prompt.md`, tema `seccion-prompt`.

Texto del aviso, igual en la tool y en la receta:

> Este párrafo se suma a lo que el agente ya lee en cada mensaje. Conviene una sola idea, en pocas líneas. Si repetís algo que ya está en el prompt completo, el modelo presta menos atención. Esta sección no cambia precios, stock ni cómo se confirma un pedido.

La receta sugiere este texto, sin escribirlo sola:

> Si la búsqueda no devuelve el producto que pidieron, decí que no lo trabajamos. No presentes otros productos como si fueran ese pedido. Una alternativa solo si la piden.

Pasos de la receta: leer la sección y el prompt completo, mirar el aviso, previsualizar, ensayar con «quiero una coca», y confirmar solo si la respuesta dice que no lo trabajan.

**Diagnóstico**

- La consulta de aliases usa `alias_raw` y `alias_norm`. El informe sigue exponiendo una lista `aliases`.

**Auditoría y Mixpanel**

- `parametros` de `ver` y del preview: largo de la sección y si hubo choque. No el prompt completo.
- Confirmar audita el `preview_id` y los largos. El evento `mcp_tool_called` no lleva el párrafo.

El catálogo del admin lee `build_server()`, así que las tools aparecen solas. No hay cambio de backoffice ni de plugin más allá de una skill de una línea que apunte a `guia_suplai` con tema `seccion-prompt`, si el plugin ya tiene ese patrón.

### Fuera de alcance

- Umbral de `search_products` para no devolver vecinos. Si el párrafo no alcanza, es otro cambio.
- Editar otros títulos, el prompt base, `identidad`, `contexto`, `reglas_negocio` o las descripciones de tools.
- Pantalla nueva en el backoffice.
- MCP Apps.
- Borrar la sección. Una confirmación con texto vacío se rechaza. Para sacar la regla, el backoffice.

---

## Flujo

1. Claude llama `ver_seccion_prompt` y lee `prompt_completo` y `aviso` antes de redactar.
2. `previsualizar_seccion_prompt` valida, arma el prompt, compara el resto de las secciones y guarda la vista previa con el `system_prompt` nuevo y el sha256 del actual.
3. `probar_agente` con el `preview_id` y el objetivo. El laboratorio responde con `envio_whatsapp: false`.
4. Si la persona dice que sí, `confirmar_seccion_prompt`. Si el prompt del tenant cambió, hay que previsualizar de nuevo.

Errores de negocio, con el tema `seccion-prompt`: texto vacío, más de 800 caracteres, una línea que es un título, el armado movió otra sección, el tenant no está en v2, preview vencido o de otro tipo, hash distinto.

---

## Orden de implementación

| Orden | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `agente-conversacional-multi_tenant` | `feat/seccion-prompt-lab` | `system_prompt` opcional en `simulate-turn`, `replace` en memoria, test de que no persiste |
| 2 | `backend-supabase` | `feat/seccion-prompt` | Tools, receta, `flow_hint`, aliases del diagnóstico, `preview_id` en `probar_agente` |

Merge del agente antes que el del backend. Si el backend llega primero, `probar_agente` con `preview_id` responde que el laboratorio no acepta el prompt de ensayo, y confirmar igual puede guardar. No es el camino de esta entrega.

Sin cambios de plugin obligatorios para que Claude vea las tools: salen del servidor. La skill de una línea puede ir en el mismo PR del backend o en un PR corto del plugin después.

---

## Migración de base de datos

Sin migración de BD. Se reescribe el texto de `system_prompt` de la distribuidora que confirme. El rollback es volver a guardar el texto anterior, que queda en el resumen de la vista previa hasta que venza.

---

## Plan de prueba en CI/CD

**Agente**

- Test del laboratorio: con `system_prompt` en el body, el turno usa ese texto. Sin el campo, usa el de la base. El test no abre una conexión de escritura a `distribuidoras`.
- La suite existente de `tests/test_implementation_lab_api.py` sigue verde.

**Backend**

- Armar la sección: la agrega si falta, reemplaza el cuerpo si está, rechaza un `#` adentro, rechaza más de 800 caracteres, rechaza vacío, y rechaza si otra sección `## ` cambió.
- El choque se informa y no lanza `AccionError`.
- Confirmar con hash distinto no hace `UPDATE`.
- `ver_seccion_prompt` incluye un marcador del prompt base y el texto del tenant en `prompt_completo`.
- El SQL de aliases contiene `alias_raw` y no selecciona una columna `alias`.
- `pytest` de esos módulos, más los tests de MCP que ya cubren `run_scoped` y `probar_agente`.

No hay smoke de migración.

---

## Plan de prueba humana

Servicios: backend en `8000`, MCP en `8100`, o el conector de producción después del merge. Tenant Demo. Cuenta de Claude que ya tiene `laboratorio:usar`.

1. Pedile a Claude que muestre la sección y el aviso, sin guardar nada.
2. Previsualizá el párrafo sugerido. El prompt completo tiene que seguir diciendo que es Tato de Demo y que no inventa precios.
3. Ensayá «quiero una coca» con ese `preview_id`. La respuesta dice que no lo trabajan. No tiene que salir un SKU de atún, puré o fideos como si fuera gaseosa.
4. Confirmá. En `public.distribuidoras`, el `system_prompt` de Demo gana el título `## Si la búsqueda no coincide` y el resto de los títulos quedan igual.
5. `diagnosticar_busqueda` con consulta «atún» y producto esperado `13136` responde un informe, no un 500.
6. Un segundo confirmar del mismo `preview_id` no vuelve a escribir.

Qué observar para dar OK: el ensayo anterior a confirmar ya usa la regla, y WhatsApp real no cambia hasta el paso 4.
