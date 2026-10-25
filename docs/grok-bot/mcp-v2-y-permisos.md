# MCP de Suplai v2 y permisos de los bots

Cómo funciona el MCP después de las etapas 1 a 5 del [spec 132](../specs/132-mcp-para-agentes-y-humanos.md), y qué puede ver y hacer cada bot de Grok. Es la referencia para organizar el plantel ([plantel-v1.md](plantel-v1.md)).

**Conexión:** `https://mcp.suplaisales.com/mcp` (HTTP). Al primer uso abre el login del backoffice de la distribuidora.

---

## Las tools, por verbo

| Verbo | Qué hace | Ejemplos |
|---|---|---|
| `buscar_*` | Lista con `campos`, `filtros`, `orden` y `cursor` (todo con valores fijos en la firma, sin SQL libre). Productos, clientes y pedidos aceptan `origen`: `suplai`, `erp` o `comparar`. | `buscar_productos`, `buscar_clientes`, `buscar_eventos` |
| `ver_*` | La ficha completa de uno. | `ver_producto`, `ver_cliente`, `ver_memoria` |
| `editar_*` | Arma un **borrador** con su riesgo. No guarda nada. Los parámetros van dentro de `datos`; la variante se elige con `cambio`, `tipo` o `parte`. | `editar_productos cambio=imagen`, `editar_clientes cambio=habituales` |
| `confirmar` | Aplica un borrador con su `borrador_id`. Con `clave_idempotencia`, un reintento no lo aplica dos veces. | |
| `guia_suplai` | Recetas paso a paso. Solo si no sabés qué tool usar. | |

Las tools viejas (`previsualizar_*`, `explorar_*`, `listar_*`, `traer_*_erp`) ya no se ven. Si un bot llama una por nombre, el error le dice cuál usar. Quedan 12 sin reemplazo: `consultar_pedidos` (agrupa por cliente o zona), las métricas, el mapa, la prueba del agente, el prompt y la búsqueda.

---

## Qué pasa al confirmar

```
editar_* → borrador (riesgo bajo, medio o alto)
confirmar → ¿tenant o agente en pausa? → rechaza
          → ¿pasa un límite? → pendiente de aprobación
          → ¿la acción es «aprobar»? → pendiente de aprobación (pide razonamiento)
          → si no → se aplica y queda auditado
```

**Riesgo:**
- **Alto:** bajas, correcciones masivas, pedidos y activar una agenda.
- **Bajo:** aliases, descripción, etiquetas, categorías, habituales y memoria.
- **Medio:** el resto.
- Más de 100 filas sube el riesgo un nivel, salvo en los habituales, que se recalculan solos.

**Autonomía por defecto** (se cambia con `editar_gobierno`):

| Se aplica solo (`auto`) | Va al lote del dueño (`aprobar`) |
|---|---|
| Productos: stock, precios, visibilidad, aliases, descripción e imagen | Alta y corrección de productos |
| Listas, categorías y tags | Promociones |
| Clientes (habituales, lista, alta) | Corrección de clientes |
| Etiquetas, vendedores, zonas, notificaciones | Pedidos |
| Grupos de envío | Agendas y secuencias |
| Probar una plantilla | Crear o borrar plantillas |
| Memoria: resultados y objetivos | Playbook (si lo propone un agente) |
| | Cualquier baja, desactivación o borrado |

**Límites** (lo que los pasa va a aprobación):

| Límite | Valor |
|---|---|
| Envíos por día | 300 |
| Cambio de precio | 10 % |
| Bajas de productos | 20 |
| Escrituras por hora (toda la distribuidora) | 60 |

**Lotes:**
1. Lo que pide aprobación queda `pendiente_aprobacion`.
2. El jefe de cuenta lo junta en el lote de la semana con `editar_lotes accion=armar`, con la estrategia y el presupuesto.
3. El dueño responde por email.
4. El bot de correo registra la respuesta con `editar_lotes accion=resolver`, y lo aprobado se aplica.

**Pausa:** `editar_gobierno accion=pausar` frena las escrituras al instante, de todos o de un agente (`agente="catalogo"`). Las lecturas siguen.

---

## Tokens por rol

En la pantalla de permisos del login aparece **«¿Quién se conecta?»**: una persona o un rol. Solo pueden conectar agentes los perfiles `owner`, `admin` y `super_admin`.

- El token de agente trae **solo el paquete de su rol**. El atajo que tiene una persona (con `pedidos:leer` ve todo) no le vale.
- Todo lo que hace queda **a nombre de su rol**, aunque diga ser otro. Por eso un bot no puede hacerse pasar por `humano` para saltear el gobierno.
- El rol sobrevive al refresh del token.

| Rol | Permisos | Escribe |
|---|---|---|
| **Jefe de cuenta** | Lectura de todo + memoria + soporte | Memoria (objetivos y resultados), habituales, lotes (armar y cerrar). Confirma los borradores de los especialistas con los permisos de quien los armó. |
| **Analista** | Pedidos, catálogo, conversaciones, vendedores, etiquetas y envíos (lectura) + memoria + soporte | Habituales de clientes y resultados en memoria. Nada del catálogo ni envíos. |
| **Supervisor** | Pedidos, conversaciones y catálogo (lectura) + aliases + laboratorio + memoria + soporte | Aliases y descripciones de productos, sección del prompt, resultados. Prueba el agente. |
| **Catálogo** | Pedidos (lectura) + carga + ERP + aliases + memoria + soporte | Productos (stock, precios, fotos, descripciones, visibilidad, alta), listas, categorías, tags, promociones, importar del ERP, resultados. |
| **Activador** | Pedidos, catálogo y conversaciones (lectura) + etiquetas + plantillas + agenda + memoria + soporte | Etiquetas, plantillas, grupos, agendas y secuencias, resultados. |
| **Bot de correo** | Pedidos (lectura) + gobierno + aprobaciones + memoria (lectura) + soporte | Resuelve lotes, registra lo que pide el dueño (`editar_lotes accion=pedido_del_dueno`), pausa y reanuda. |

**Tools que ve cada rol:**

| Rol | Tools | Las que solo él tiene (entre los agentes) |
|---|---|---|
| Jefe de cuenta | 34 | `buscar_notificaciones`, `ver_envios_notificacion` |
| Analista | 28 | Ninguna: lee y calcula habituales |
| Supervisor | 32 | `probar_agente`, `ver_seccion_prompt`, `previsualizar_seccion_prompt` |
| Catálogo | 29 | `editar_listas`, `editar_promociones` (y `editar_productos` completo; el supervisor solo aliases y descripción) |
| Activador | 33 | `editar_etiquetas`, `editar_plantillas`, `editar_envios` |
| Bot de correo | 15 | Resolver lotes y pausar |

Todos ven `editar_lotes` y `editar_gobierno`, pero adentro se controla quién puede:
- **Armar y cerrar lotes:** solo el jefe de cuenta o una persona.
- **Resolver lotes y registrar lo que pide el dueño:** solo el bot de correo.
- **Pausar:** el bot de correo o una persona con `gobierno:escribir`.
- **Cambiar límites y autonomía:** solo una persona con `gobierno:escribir`.

---

## Memoria y eventos

- **`ver_memoria`** al arrancar una tarea: el playbook y los objetivos vigentes, y los últimos resultados de los agentes.
- **`editar_memoria`** tiene tres partes:
  - **Resultados:** cualquier agente, al terminar una tarea.
  - **Objetivos:** una persona o el jefe de cuenta.
  - **Playbook:** una persona. Si lo propone un agente, va al lote del dueño.
  - Playbook y objetivos se reemplazan enteros y guardan las versiones anteriores.
- **`buscar_eventos`**: lo que pasó, en orden. Para ver solo lo nuevo, filtro `id >` el último que viste.
  - **Ya funcionan:** `pedido_nuevo`, `pedido_error_erp`, `borrador_aprobado`, `borrador_rechazado`, `lote_resuelto` y `pedido_del_dueno`.
  - **Todavía no se generan:** `sin_stock`, `cliente_en_riesgo`, `envio_fallido`, `reclamo_en_charla` y `sync_erp`.

---

## Campos útiles para el preventista (spec 133)

| Dónde | Campo | Para qué |
|---|---|---|
| `buscar_clientes` | `habituales`, `habituales_codigos`, `habituales_al` | Quién tiene lo de siempre calculado y desde cuándo. |
| `buscar_productos` | `creado` | Ordenar por `creado` desc para ver las novedades. |
| `buscar_productos` | `clientes_habituales` | Cuántos clientes tienen ese producto entre sus habituales. |
| `buscar_productos` | `tiene_imagen`, `promos_vigentes` | Priorizar fotos y promos. |
| `editar_clientes` | `cambio=habituales` | Calcula lo de siempre desde los pedidos de Suplai y del ERP (`origen`). |
| `editar_productos` | `cambio=imagen` | Baja la foto de una URL y la guarda en Suplai. |
