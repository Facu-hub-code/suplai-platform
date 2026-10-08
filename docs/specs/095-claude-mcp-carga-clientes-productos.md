# 095 — Claude MCP: carga de clientes y productos

**Estado:** Borrador  
**Fecha:** 2026-10-08  
**Repos:** `backend-supabase` (tools, scope, preview), `suplai-sales-claude-plugin` (skills), `suplai-platform` (este spec)  
**Ramas sugeridas:** `feat/claude-mcp-carga` en backend y en el plugin  
**Serie:** [objetivos de capacidades](../claude-mcp/objetivos-capacidades.md), caso 1. El manual es el [094](./094-claude-mcp-manual.md).  
**Relaciona:** bulk de `routers/clientes.py` y `routers/productos.py`, `services/whatsapp_send.py::normalize_phone`, `services/tenant_format.py::resolve_tienda_show_products_without_stock`, spec 088 (`clients.lifecycle`), spec 089 (validar WhatsApp, fuera de esta entrega).

---

## Objetivo

El usuario sube un Excel a Claude. Claude acomoda las columnas y llama al conector. El conector devuelve, fila por fila, qué se puede cargar y qué no. Recién cuando el usuario dice que sí, se insertan los contactos y los productos nuevos para que el agente de WhatsApp los use.

La carga es operativa: no marca `is_mock` y no es el onboarding de demo (spec 036).

### Métricas de éxito

- Un teléfono que no queda en formato WhatsApp Argentina no se inserta, y el preview muestra el valor original y el motivo.
- Un producto sin precio mayor a 0 no se inserta.
- Un cliente o un SKU que ya existe no se pisa.
- Confirmar dos veces el mismo preview no duplica filas.
- En `demo`, un archivo de pocas filas termina con clientes nuevos en cartera y SKUs con precio en la lista elegida, visibles para el catálogo, y vectorizados para la búsqueda del agente.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Quién lee el Excel | Claude, en el chat. Al MCP llegan lotes ya normalizados de hasta 100 filas | Un xlsx en la tool revienta el payload y mezcla parseo con reglas de negocio. | Subir el archivo al MCP. |
| Escritura | Dos tools: `previsualizar_carga` y `confirmar_carga` | El preview muestra el rechazo. Confirmar aplica solo las filas que ese preview aceptó, guardadas en el server. | Una sola tool que inserta, y confiar en que Claude espere el sí. El modelo puede llamar igual. |
| Scope | `carga:escribir`, aparte de `pedidos:leer` | El consentimiento tiene que decir que ahora también guarda datos. El required scope del servidor sigue siendo `pedidos:leer`, si no `consultar_pedidos` se cae para quien no reconectó. La tool de carga mira el scope adentro y, si falta, pide reconectar. | Sumar `carga:escribir` a `required_scopes` del server. |
| Conexión de las escrituras | Los servicios actuales (`query_schema`, pool de la API) | `mcp_connector` tiene SELECT de pedidos y clientes, e INSERT solo de `mcp_auditoria`. No se le da INSERT de tenant. | Insertar con el rol `mcp_connector`. |
| Alta, no actualización | `ON CONFLICT DO NOTHING`, igual que el bulk de hoy. El preview marca “ya existe” | Pisar teléfono, precio o lista desde un chat es el accidente caro. | Upsert que actualice precio y razón social. |
| Teléfono | Dígitos `549` + 10 dígitos. Lo normaliza el server, no Claude | El agente y Meta entregan a ese formato. Un `11 15 1234-5678` o un `+54 9` tienen que salir iguales. | Aceptar cualquier E.164: los tenants de esta entrega son de Argentina. |
| Lista de precios | El usuario elige una lista activa y pública que ya existe. Si el id no es válido, la fila se rechaza | El bulk de clientes, si el id no existe, cae en silencio a la primera lista del tenant. Acá eso mezclaría precios. | Crear la lista desde Claude. |
| Precio | `precio_unidad > 0` en esa lista, o la fila de producto se rechaza y no se inserta el SKU | Sin precio no está en la tienda ni se lo puede vender. Inventar un precio está prohibido en los objetivos. | Insertar con `en_catalogo = false` y completar el precio después. |
| Stock ausente | Se guarda 0 y el preview lo dice | La columna y el validador de bulk tratan el vacío como 0. La tienda igual muestra esos SKUs salvo que `metadata.tienda` tenga `show_products_without_stock` en falso (`resolve_tienda_show_products_without_stock`, default true). | Rechazar la fila: frenaría la carga de un Excel que no trae stock. |
| Stock explícito | Se respeta, incluido 0. Negativo se rechaza | 0 escrito por el usuario no es lo mismo que columna vacía, pero el efecto en base es el mismo. El preview distingue “vino vacío” de “vino 0”. | |
| Catálogo | `en_catalogo = true` solo en las filas con precio válido | Es la condición de visibilidad junto con la lista activa y pública. | Dejar el default del bulk, que con `en_catalogo` vacío guarda false. |
| Descripciones | Solo si el Excel las trae. No se llama `ai_backfill_productos` | Ese job inventa texto comercial. Los objetivos lo dejan fuera de la v1. | Reusar el backfill del bulk-upsert. |
| Vectorización | Sí, en background, para los SKU insertados | Sin eso el agente no los encuentra por nombre. Ya existe `vectorizar_productos`. | Esperar a un paso manual del backoffice. |
| Aliases | Los que vengan en la fila (Claude puede proponerlos desde el nombre) se insertan en el confirmar, en un solo `INSERT … ON CONFLICT`, misma forma que `POST /{product_code}/aliases` | Un HTTP por alias en un lote de 100 no cierra. El preview lista los alias para que el usuario los vea antes. | Omitir aliases en la v1. |
| Cartera | Toda fila de cliente entra como `lifecycle = client` (default de la columna). `origen_alta` queda `import`, que es lo que ya escribe el bulk | El trigger de spec 088 solo pasa a prospecto si la etiqueta es `prospect` / `prospecto`. Esta carga no manda esa etiqueta. | Un flag `es_prospecto` en la v1. |
| Teléfono de vendedor | Si el número ya es de un vendedor, esa fila se rechaza y el resto del lote sigue | `bulk_validate_vendedores_conflict` hoy puede frenar el batch entero. | Fallar las 100 filas por un teléfono. |
| Auditoría | Cuenta de filas, `preview_id`, `lista_precios_id`, resultado. Sin teléfonos, nombres ni precios en `parametros` | `mcp_auditoria` y Mixpanel no llevan PII. | Guardar el payload del Excel. |
| Tope | 100 filas por preview. Claude parte el archivo | Mismo orden de magnitud que el `limite` de `consultar_pedidos`. Un confirm por cada preview. | Un solo llamado con el Excel completo. |

---

## Alcance

### Incluido

Tools nuevas, las dos con scope `carga:escribir`, anotadas como escritura (`readOnlyHint = false`). `previsualizar_carga` es idempotente. `confirmar_carga` no lo es, y el segundo llamado al mismo `preview_id` responde que ya se usó.

**`previsualizar_carga`**

- `tipo`: `clientes` o `productos`.
- `filas`: hasta 100 objetos con las columnas de abajo.
- En productos, `lista_precios_id` obligatorio.
- Respuesta: `preview_id`, vence a los 30 minutos, conteos (`aceptadas`, `rechazadas`, `ya_existen`) y una lista por fila con `estado` (`aceptada`, `rechazada`, `ya_existe`), `motivo` y, en productos aceptados, tres datos separados: entra al catálogo, lista y precio, y stock (dato del archivo, o “sin dato, se guarda 0”, más si la tienda de ese tenant oculta sin stock).
- No escribe clientes, productos, precios ni aliases.

**`confirmar_carga`**

- Recibe solo `preview_id`.
- Inserta las filas aceptadas. Las `ya_existe` y las rechazadas no se tocan.
- Marca el preview como consumido en la misma transacción que el insert del lote.
- Dispara la vectorización de los SKU nuevos. No dispara el backfill de descripciones.

**Columnas que Claude manda**

Clientes: `telefono` (crudo), `razon_social`, y opcionales `nombre`, `lista_precios_id`, `codigo`, `dia_de_visita`, `dia_de_entrega`, `email`, `cuit`, `direccion`.

Productos: `product_code`, `nombre`, `precio_unidad`, y opcionales `stock`, `descripcion`, `unidades_por_bulto`, `unidad_minima_de_venta`, `aliases` (lista de textos).

**Normalización de teléfono (server)**

1. Dejar solo dígitos.
2. Si empieza con `00`, sacar esos dos.
3. Si empieza con `0`, sacar el tronco y seguir.
4. Si empieza con `54` y el siguiente no es `9`, insertar `9`.
5. Si tiene 10 dígitos y no tiene país, anteponer `549`.
6. Si en el tramo local aparece `15` de celular (después de la característica), sacarlo una sola vez antes de cerrar el `549`.
7. Aceptar solo el resultado `549` seguido de 10 dígitos. Cualquier otro caso: fila rechazada, con el valor original en el motivo.

**Días.** Misma lista que el bulk: `lunes` … `domingo`, con `miércoles` y `sábado`. Un día ilegible rechaza la fila, no el lote.

**Listas.** Tool de lectura `listar_listas_precios` (mismo scope): `id`, `nombre`, `activa`, `es_publica`. El preview de productos solo acepta una lista con las dos en true. Si el Excel trae una sola columna de precio, Claude pregunta cuál de esas listas es y manda ese id. Si trae varias columnas, un preview por lista, no un mapeo mágico adentro de una fila.

**Skill del plugin** `skills/cargar-datos/SKILL.md`: cómo mapear columnas típicas (teléfono, razón social, código, precio, stock), partir en tandas de 100, mostrar el preview en una tabla corta y no llamar `confirmar_carga` sin un sí. Actualizar `skills/manual-conector/SKILL.md` para sacar la carga de “todavía no” y dejar plantillas, grupos, agendas, ERP y estrategias en esa lista. Actualizar la description de `plugin.json` para mencionar la carga además de los pedidos. Actualizar las instructions del MCP: ya no son “solo lectura”; las escrituras pasan por preview y confirmación.

**Consentimiento.** La pantalla deja de tener fijo “Ver los pedidos de tu distribuidora” y lista los scopes pedidos. `pedidos:leer` → “Ver los pedidos de tu distribuidora”. `carga:escribir` → “Cargar clientes y productos de tu distribuidora”.

### Fuera de alcance

- Actualizar un cliente o un precio que ya existe.
- Alta de prospectos (`lifecycle = prospect`).
- Crear listas de precios, imágenes, categorías, tags y descripciones generadas.
- Saber si el número tiene WhatsApp (spec 089).
- `is_mock`, demo de onboarding, borrar filas, ERP.
- Más de un país en el teléfono.

---

## Orden de implementación

| Orden | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `backend-supabase` | `feat/claude-mcp-carga` | Migración del preview, scope, tools, servicio de normalización, tests |
| 2 | `suplai-sales-claude-plugin` | `feat/claude-mcp-carga` | Skills `cargar-datos` y el ajuste de `manual-conector`, más `plugin.json` |

El plugin se mergea después del backend. Si entra antes, Claude llama tools que todavía no existen.

El 094 puede estar mergeado antes. Si no lo está, este PR del plugin crea `manual-conector` ya con la carga incluida y el resto en “todavía no”.

---

## Migración de base de datos

`sql/146_mcp_carga_preview.sql` (el número libre siguiente si 146 ya existe al implementar). Tabla en `public`, no en el schema del tenant: el preview es de la sesión OAuth, no un dato comercial.

```text
public.mcp_carga_previews
  id uuid PK
  usuario_id uuid
  distribuidora_id uuid
  schema_name text
  tipo text  -- clientes | productos
  lista_precios_id int null
  filas_aceptadas jsonb   -- solo lo que confirmar va a insertar
  resumen jsonb           -- conteos y motivos, sin repetir teléfonos de más en logs
  expires_at timestamptz
  consumed_at timestamptz null
  created_at timestamptz default now()
```

Índice por `expires_at` para limpiar vencidos. No hace falta un job en la v1: confirmar y previsualizar ignoran filas vencidas o consumidas.

Rollback: `DROP TABLE public.mcp_carga_previews`. No toca `clients` ni `productos`.

Sin cambio de columnas de tenant. `clients.lifecycle` y las vistas `v_cartera` / `v_prospectos` no se alteran.

El rol `mcp_connector` no recibe GRANT sobre esta tabla ni sobre tablas de tenant. La escribe el mismo rol de la API que ya inserta clientes. RLS queda activo y se revoca el acceso de `anon` y `authenticated`: el preview guarda teléfonos y no debe quedar expuesto por la API pública.

---

## Plan de prueba en CI/CD

En `backend-supabase`, pytest del mismo estilo que `tests/test_mcp_tool_schema.py`:

- El teléfono `11 15 1234-5678`, `+54 9 11 1234-5678` y `5491112345678` (con una característica válida de 10 dígitos locales en el caso de prueba) caen en el mismo `549` + 10 dígitos. Un valor corto o con letras se rechaza.
- Preview de productos: precio 0 o ausente → rechazada y no está en `filas_aceptadas`. Lista inexistente o no pública → error de la tool, sin `preview_id`.
- Preview de clientes: sin razón social, o teléfono de un vendedor → esa fila rechazada, las otras siguen.
- SKU o teléfono ya presente → `ya_existe`, y confirmar no llama al insert de esa fila.
- Confirmar con `preview_id` vencido, ajeno a otro usuario, o ya consumido → error, cero inserts.
- El camino de confirmar no llama `ai_backfill_productos`. Sí encola `vectorizar_productos` con los códigos insertados.
- La auditoría del confirmar no incluye el teléfono ni el precio en `parametros`.
- Schema de las tools: annotations, scope y el tope de 100.

El CI actual del backend (`pytest`) tiene que seguir verde. No hay migración que correr en un tenant de prueba más allá de aplicar el SQL en el entorno de test si la suite levanta schema.

Gap: el plugin sigue sin CI. El PR del plugin se revisa a mano contra la lista de tools del backend ya mergeado.

---

## Plan de prueba humana

Tenant `demo`. No usar un tenant de un cliente. Claude conectado de nuevo, para aceptar el permiso de carga. Backend del entorno donde esté el MCP de prueba.

Armar un xlsx de 5 filas de productos y 5 de clientes:

- Un teléfono argentino bien escrito de otra forma (`11 15 …`).
- Un teléfono imposible.
- Un teléfono que ya esté en `demo.clients`.
- Un producto con precio y sin columna de stock.
- Un producto con precio 0.
- Un código que ya exista.

Pasos:

1. “¿Qué podés hacer?” incluye la carga y sigue sin prometer plantillas ni ERP.
2. Subir el Excel de clientes. Pedir la lista de precios si hace falta y elegir una activa y pública.
3. Ver el preview: el teléfono imposible rechazado, el existente marcado como ya está, el válido aceptado en formato `549…`.
4. Decir que no. Confirmar en base que no hay un cliente nuevo con ese teléfono.
5. Decir que sí. Ver el cliente nuevo, `lifecycle = client`, `origen_alta = import`, y la lista elegida (no otra).
6. Repetir con productos. El de precio 0 no aparece. El nuevo está `en_catalogo`, con precio en esa lista, stock 0 si el archivo no lo traía, y el preview lo decía.
7. Pedir de nuevo confirmar el mismo lote y ver que no duplica.
8. En la tienda del `demo` (o una consulta de catálogo), el SKU nuevo se lista. La búsqueda del agente puede tardar hasta que termine la vectorización: alcanza con ver en base que el job quedó encolado, no hace falta esperar el embedding en esta prueba.

OK: nada de lo rechazado se persistió, nada de lo existente cambió de precio o de teléfono, y el segundo confirm no inserta de nuevo.
