# 098 — Claude MCP: estado del ERP y promoción al catálogo

**Estado:** Borrador  
**Fecha:** 2026-10-08  
**Repos:** `backend-supabase` (tools, scopes, preview), `suplai-sales-claude-plugin` (skills), `suplai-platform` (este spec)  
**Ramas sugeridas:** `feat/claude-mcp-erp` en backend y en el plugin  
**Serie:** [objetivos de capacidades](../claude-mcp/objetivos-capacidades.md), caso 3. El manual es el [094](./094-claude-mcp-manual.md).  
**Relaciona:** `routers/erp.py`, `erp/services/erp_product_promote_service.py` (`promote_erp_products_bulk`, `dry_run` y filtro `skus`), cola `customer-onboarding`, `price-lists-raw` (`onboarding-preview`, `link`, `sync-prices`).

---

## Objetivo

El gerente pregunta cómo está la sincronización con el ERP. Claude dice qué llegó y qué todavía no está en Suplai. Si la persona acepta el preview, incorpora productos nuevos, clientes de la cola y una lista de precios del espejo. No conecta el ERP ni empuja pedidos.

### Métricas de éxito

- Sin conector configurado, la lectura lo dice y no inventa una última sync.
- Confirmar productos inserta solo los SKU que el preview guardó. Un SKU que ya está en `productos` no se pisa.
- Un cliente de la cola sin teléfono normalizable a WhatsApp Argentina no se aprueba, y el preview muestra el motivo.
- Vincular una lista no corre el alineado de precios hasta el sí, y el preview dice cuántos precios van a cambiar.
- En `demo`, si no hay ERP, alcanza con ver ese vacío. No se promueve otro tenant.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Quién puede | El mismo token del conector, cualquier perfil del backoffice que no sea `waitlist` | Integraciones no tiene un rol más chico en el backoffice: entra quien ya opera el tenant. `waitlist` no obtiene token. | Exigir `owner`. Hoy esa pantalla no está cerrada así y el spec se apartaría del producto. |
| Scopes | `erp:leer` para el estado. `erp:escribir` para promover | Mirar la sync no tiene que autorizar un alta masiva. `required_scopes` del servidor sigue en `pedidos:leer`. Si falta el scope, la tool pide reconectar. | Un solo `erp:escribir` también para la lectura. El objetivo de este caso pide scope de lectura aparte. |
| Escritura | `previsualizar_erp` y `confirmar_erp` | El dry run de productos ya existe y no inserta. Confirmar aplica la lista guardada en el server, no un lote distinto que el modelo arme después. | Llamar `promote-products-bulk` sin `dry_run` en la primera tool. |
| Productos | El preview guarda todos los SKU pendientes, no solo la muestra de 5 del dry run. Confirmar llama `promote_erp_products_bulk` con `skus` | El dry run de hoy devuelve el total y cinco filas, y el apply sin filtro da de alta todo lo que haya llegado después. Acá el sí cubre lo que la persona vio. | Aplicar “todos los pendientes” en el momento del confirm. |
| Descripción al promover | Se reusa el alta actual: descripción corta a partir del nombre del ERP, y vectorización | Es lo que ya hace `promote_erp_products_bulk` para que el agente encuentre el SKU. El preview lo dice. No se inventa precio. | Un insert mudo, sin descripción. El agente no lo busca bien y el camino del backoffice queda duplicado. |
| Clientes | Solo ítems de la cola en estado pendiente o en revisión. El teléfono se normaliza como en el [095](./095-claude-mcp-carga-clientes-productos.md) | La cola existe para no chocar con un contacto. Un número que no queda en `549` + 10 dígitos no se aprueba. | Promover directo desde `customers-raw` saltando la cola. |
| Listas | Vincular el espejo a una lista de Suplai que ya existe, o crear una con el nombre del espejo si la persona lo pidió. El alineado de precios es el `sync-prices` de esa lista, en el mismo confirm, después del vínculo | El objetivo junta vínculo y precios. Separarlos deja la lista conectada con precios viejos y el agente vende mal. | `onboarding-apply` completo del wizard. Mezcla decisiones de más para un chat. |
| Sync nueva | No hay tool que dispare `/sync`, `/load-products` ni el bridge | Esas llamadas dependen de credenciales y del conector. Este caso trabaja con lo que ya está en el espejo. | Un botón de “sincronizá ahora” en la v1. |
| Muestra | Hasta cinco nombres (SKU o razón social) y el total. Sin teléfonos en la respuesta ni en la auditoría | Claude repetiría el número en el chat. El motivo de rechazo de un teléfono alcanza, sin el valor. | Devolver la fila cruda del ERP. |
| Auditoría | `preview_id`, tipo, conteos, id de lista. Sin SKU sueltos de más, sin teléfonos ni precios | Misma regla que el resto de la serie. | Guardar el payload del espejo. |
| Conexión | Servicios y pool de la API | `mcp_connector` no escribe el espejo ni `productos`. | Darle INSERT al rol del conector. |
| Preview | `public.mcp_accion_previews`, tipos `erp_productos`, `erp_clientes`, `erp_lista`. 30 minutos | La tabla ya nace en el [096](./096-claude-mcp-plantillas.md). No hace falta otra. | Reusar `mcp_carga_previews`, que es de filas de Excel. |

---

## Alcance

### Incluido

Cuatro tools. Las de escritura van con `readOnlyHint = false`. `previsualizar_erp` no escribe. `confirmar_erp` no es idempotente.

**`estado_erp`** (`erp:leer`)

- Si no hay conector: `conectado: false` y una frase. Sin fechas inventadas.
- Si hay: salud de `dependency-health`, momento de la última sync que el backend ya guarda, productos en el espejo que no están en `productos`, listas del espejo sin lista de Suplai, e ítems de la cola de clientes pendientes o en revisión.
- Conteos. Sin teléfonos y sin el detalle de precios.

**`previsualizar_erp`** (`erp:escribir`)

- `tipo`: `productos`, `clientes` o `lista`.
- Productos: no pide ids. Arma el universo pendiente y guarda los SKU. Respuesta: total, hasta cinco nombres, y la frase de que al confirmar se escribe una descripción corta desde el nombre del ERP y se vectoriza.
- Clientes: guarda los `queue_id` cuyo teléfono normaliza. El resto va en el reporte con motivo y no entra al payload. Si no queda ninguno, no hay `preview_id`.
- Lista: `raw_id` obligatorio. `lista_precios_id` para vincular una existente, o `crear: true` para crear con el nombre del espejo. Las dos cosas juntas se rechazan. La respuesta incluye cuántos precios va a alinear el confirm.
- No llama a Meta ni inserta productos, clientes ni precios.

**`confirmar_erp`** (`erp:escribir`)

- Recibe solo `preview_id`.
- Productos: `promote_erp_products_bulk` con la lista de SKU guardada.
- Clientes: el approve de la cola solo para esos `queue_id`.
- Lista: primero el vínculo (`link`, con `create_new` si el preview lo decía) y después `sync-prices` de la lista de Suplai resultante. Si el vínculo entra y el alineado falla, el preview no se consume y la respuesta dice que la lista quedó vinculada y los precios no.
- Consume el preview cuando el paso que el tipo prometía terminó.

La skill `skills/erp/SKILL.md` enseña a leer primero y a no prometer una sync nueva. `manual-conector` suma estas tools y saca el ERP de “todavía no” en la parte de lectura y de alta. Sigue sin poder conectar credenciales ni empujar pedidos.

### Fuera de alcance

- `POST /connect`, token de ingesta, paquete del bridge y heartbeat.
- `POST /sync`, `/load-products`, `/load-customers`, `/load-prices` y `/sync-orders`.
- Empujar un pedido a ERP (`push-order`).
- Desvincular una lista, descartar un cliente de la cola y el wizard largo de onboarding de listas.
- Editar precio, stock o teléfono a mano. Lo que no vino en el espejo no se completa.

---

## Orden de implementación

1. El [096](./096-claude-mcp-plantillas.md) mergeado, con `public.mcp_accion_previews` creada.
2. `backend-supabase`, rama `feat/claude-mcp-erp` desde `origin/main`. Amplía el check de `tipo`, suma los dos scopes y las tools.
3. Aplicar esa migración antes de probar el confirm.
4. Merge del backend.
5. Plugin, misma rama: `skills/erp/SKILL.md` y el renglón del manual. Después del backend.

Quien ya tenía el conector tiene que reconectar para recibir `erp:leer` y `erp:escribir`.

---

## Migración de base de datos

`sql/149_mcp_accion_previews_erp.sql`.

Amplía el check de `public.mcp_accion_previews.tipo` para aceptar `erp_productos`, `erp_clientes` y `erp_lista`, además de los tipos ya cargados. Misma tabla, mismo RLS, sin GRANT nuevo.

Sin columnas nuevas en el espejo ni en `productos` o `clients`.

Rollback: volver el check a los tipos anteriores después de borrar las filas `erp_*`. No deshace un alta ya confirmada.

---

## Plan de prueba en CI/CD

Pytest en `backend-supabase`:

- Scope de lectura ausente en `estado_erp`, y scope de escritura ausente en el preview → piden reconectar y no llaman al servicio de promote.
- Preview de productos guarda la lista completa de SKU y la respuesta muestra solo cinco nombres.
- Confirmar productos llama al promote con esos SKU y `dry_run` en falso. Un segundo confirm no llama.
- Cliente sin teléfono normalizable → no está en el payload. Si todos fallan, no hay `preview_id`.
- Lista con `lista_precios_id` y `crear` a la vez → error, sin preview.
- Si `sync-prices` falla después del link, `consumed_at` sigue null.
- La auditoría no incluye un teléfono ni un precio.
- Annotations y los dos scopes en el schema de las tools.

El promote, la cola y Meta de precios se mockean. El CI (`pytest`) sigue verde.

Gap: el plugin no tiene CI. Se revisa a mano contra las tools del backend.

---

## Plan de prueba humana

Tenant `demo`. No usar un tenant de un cliente. Claude reconectado, con los dos permisos de ERP en el consentimiento. Backend `8000` y MCP `8100` en local, o los dos servicios ya deployados.

Si `demo` no tiene ERP configurado:

1. “¿Cómo está el ERP?” responde que no está conectado y no inventa una fecha.
2. Pedir “subí los productos del ERP”. No hay preview de alta.

Eso alcanza para el OK de un `demo` sin conector.

Si el entorno de prueba tiene espejo con datos de laboratorio:

3. La lectura muestra conteos de productos, listas y cola.
4. Preview de productos, decir que no, y verificar que no apareció un `product_code` nuevo.
5. Decir que sí sobre otro preview. Entran solo esos SKU, con descripción y vectorización encolada, sin cambiar el precio de uno que ya existía.
6. Un ítem de cola con teléfono imposible queda afuera y no se aprueba.
7. Vincular una lista de laboratorio y ver en el preview cuántos precios cambian antes del sí.

OK: lo rechazado no se persistió y el manual ya no dice que el ERP está entero afuera.
