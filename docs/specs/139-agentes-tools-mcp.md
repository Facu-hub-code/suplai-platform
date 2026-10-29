# 139 — Equipo de agentes: tools nuevas en los dos MCP

**Estado:** Borrador.
**Fecha:** 2026-10-27
**Repos:** `backend-supabase` (`mcp_server/agentes_tools.py`, `mcp_server/agentes_main.py`, `services/agentes_*`, `services/oauth/constants.py`).
**Rama sugerida:** `feat/agentes-tools-mcp`.
**Relaciona:** [132](./132-mcp-para-agentes-y-humanos.md) (convención de nombres, borrador y `confirmar`, roles), [136](./136-agentes-modelo-de-datos.md), [137](./137-agentes-eventos-webhooks-scheduler.md), [141](./141-agentes-reportes.md).

---

## Objetivo

Sumar al MCP humano las tools para encargar y seguir un trabajo, y al MCP de agentes las tools para trabajar sobre archivos, dejar traza, preguntar y publicar. Los permisos los decide el servidor con el token del bot y su certificado.

### Criterios de aceptación

- Las dos fachadas llaman a los mismos servicios `services/agentes_*`. Ninguna tool tiene SQL ni lógica de dominio propia (principio 2).
- Un token de bot ve solo las tools de su rol y de su certificado. Una tarea en L1 no aparece en `list_tools`.
- Una escritura de un bot por encima de su nivel no se ejecuta ni falla: devuelve `estado: propuesta` con el id del borrador, y la Propuesta aparece en la Bandeja.
- Toda tool del MCP de agentes deja un evento de traza automático si el bot no lo dejó (principio 5); `registrar_traza` sirve para la línea en lenguaje humano.
- `exportar_lote` de un año de pedidos de Córdoba Frost se resuelve en una llamada y devuelve un link firmado.
- `editar_gobierno` ya no cambia autonomía ni límites: devuelve el link al formulario. Pausar y reanudar siguen.
- `encargar_analisis` repetido con la misma `clave_idempotencia` devuelve el mismo trabajo.

---

## Dos fachadas

| Fachada | Endpoint | Auth | Quién |
|---------|----------|------|-------|
| MCP humano | `/mcp` (el de hoy) | OAuth por distribuidora, JWT RS256 (`SuplaiTokenVerifier`) | El humano desde Claude. También los tokens OAuth por rol del 132 |
| MCP de agentes | `/agentes/mcp`, mismo proceso Railway | **Token por run**: JWT firmado por el backend al lanzar cada run | Los bots en el runtime ([138](./138-agentes-adaptador-runtime.md)) |

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Credencial del bot | Token por run, corto y revocable | Si se filtra, vale para un trabajo, un bot y unas horas. El tenant, el bot y el run salen del token y no de lo que diga el modelo | Token fijo por bot: con Cursor, cualquier agente de la cuenta podía usar el de otro bot |
| Mismo proceso | Un segundo `MCPServer` montado en `/agentes/mcp` en `mcp_server/main.py` | Un deploy, un pool, mismos servicios | Otro servicio Railway |
| Qué tools ve | Las que el token trae en `scopes`: intersección de los scopes del rol (`ROLES_AGENTE`), las `fuentes` del certificado y las tareas con nivel ≥ L2 | El certificado manda; el rol pone el techo | Solo el rol |

### Token por run

| Claim | Valor |
|-------|-------|
| `iss`, `aud` | El backend; `aud` es la URL de `/agentes/mcp` |
| `sub` | `bot:{bot_id}` |
| `distribuidora_id`, `schema` | Del bot |
| `bot_id`, `rol`, `certificado_id` | Certificado vigente al lanzar |
| `trabajo_id`, `run_id` | Del run |
| `scopes` | Calculados al lanzar, como dice la fila «Qué tools ve» |
| `exp` | 3 horas, o el `tiempo_max_min` del run más 30 min, lo que sea menor |
| `jti` | Igual al `run_id` |

- Firma RS256 con la clave que ya usa el OAuth del MCP (`OAUTH_JWT_PRIVATE_KEY_PEM`), con un `kid` propio para poder rotarla aparte.
- `RunTokenVerifier` verifica firma, `aud` y `exp`, y además que el run exista y esté `lanzando` o `corriendo`. Un run `terminado`, `error`, `cancelado` o `vencido` es un token revocado. No hace falta lista de revocación: el estado del run lo es.
- Pausar el bot o cancelar el trabajo cierra sus runs, y con eso sus tokens.
- Devuelve un `AccessToken` con los mismos claims que hoy (`distribuidora_id`, `_scopes` con `agente:<rol>`) más `bot_id`, `trabajo_id` y `run_id`. Así `run_scoped` y `filtrar_visibles` siguen andando sin cambios.
- **Ninguna tool recibe `trabajo_id` ni `run_id` como parámetro.** Salen del token. Un parámetro con el nombre de otro tenant o de otro trabajo no cambia nada: la consulta corre con el schema del token.

Tests obligatorios:

1. Un token de la distribuidora A no lee nada de la B, por ninguna tool.
2. Un token de un run cerrado falla con `token_revocado`.
3. Un token vencido falla con `token_vencido`.
4. Ningún parámetro de ninguna tool cambia el tenant, el bot ni el trabajo.

### Roles nuevos

En `ROLES_AGENTE`:

- `analista_ventas`: `pedidos:leer`, `carga:leer`, `vendedores:leer`, `estrategias:leer`, memoria, soporte.
- `analista_conversaciones`: `conversaciones:leer`, `aliases:leer`, `carga:leer`, `pedidos:leer`, memoria, soporte.
- El rol `analista` del 132 queda como alias de `analista_ventas` hasta el corte del 132.

Scope nuevo `agentes:trabajar` para las tools de trabajo del MCP de agentes, y `agentes:encargar` para las del MCP humano. `agentes:encargar` entra en `CONECTOR_ACEPTA_TOOLS_NUEVAS`.

---

## Tools nuevas en el MCP humano

### `encargar_analisis`

| Parámetro | Tipo | Notas |
|-----------|------|-------|
| `pedido` | texto | Lo que pidió la persona, literal |
| `tipo` | `analisis_ventas` · `analisis_conversaciones` | Claude lo infiere; si duda, pregunta |
| `desde`, `hasta` | fecha | Opcionales; si faltan, el jefe de cuenta los fija y lo dice en el plan |
| `clave_idempotencia` | texto | Obligatoria |

Crea el Trabajo con el usuario del token como humano asignado, delega jefe de cuenta + el analista del tipo, y emite `trabajo.creado`. No pasa por borrador: encargar no toca datos ni clientes.

Respuesta: `{trabajo_id, estado, link, resumen}`. El `resumen` dice: «Listo. El equipo arrancó; te aviso por correo cuando el reporte esté. Podés seguirlo acá: <link>».

### `ver_trabajos`

`trabajo_id` opcional, `estado` opcional, `tamano`. Sin id: lista. Con id: estado, avance, paso actual de cada bot, pregunta abierta y link. Devuelve también la MCP App compacta (`ui://suplai/app.html`, vista `trabajo`) con esos datos.

### `responder_pregunta` y `aportar_contexto`

- `responder_pregunta(pregunta_id, respuesta, guardar_como_regla=false)`.
- `aportar_contexto(texto, trabajo_id=None, guardar_como_regla=false)`.

Crean el Contexto, cierran la pregunta si corresponde, registran el paso en el carril del humano y emiten `contexto.aportado`.

### `abrir_backoffice`

`pantalla` (`trabajos`, `reportes`, `bandeja`, `equipo`, `avisos`), `id` opcional. Devuelve el link con `?src=claude`. No lee datos. Es la respuesta cuando la persona quiere editar un certificado o decidir una Propuesta con detalle.

### Cambio en `editar_gobierno`

Las acciones `pausar` y `reanudar` siguen. `autonomia` y `limites` responden `codigo: se_edita_en_backoffice` con el link a `/agentes/equipo` (principio 9). Se anota en el 132.

---

## Tools nuevas en el MCP de agentes

Ninguna recibe `trabajo_id` ni `run_id`: el trabajo y el run son los del token.

### `leer_instrucciones`

Sin parámetros. Devuelve las instrucciones del rol armadas con el certificado vigente y el contexto del tenant ([140](./140-agentes-bots-mvp.md)), y el `mensaje_inicial` del run. El entrypoint del [138](./138-agentes-adaptador-runtime.md) la llama al arrancar; así las instrucciones no viven en la imagen.

### `exportar_lote`

| Parámetro | Tipo | Notas |
|-----------|------|-------|
| `entidad` | `pedidos` · `items_pedido` · `clientes` · `productos` · `conversaciones` · `mensajes` | Cada una pide la fuente en el certificado |
| `desde`, `hasta` | fecha | Obligatorio para pedidos, items y conversaciones. Máximo 400 días |
| `campos` | lista cerrada | Mismo `enum` que el `buscar_*` de la familia (contrato de lectura del 132) |
| `filtros` | lista | Igual que el 132 |
| `formato` | `csv` · `parquet` | Default `csv` |

Respuesta: `{archivo_path, url_firmada, vence_at, filas, columnas, bytes, resumen}`. El archivo queda en el bucket de Cloud Storage `suplai-agentes-datos`, en `{schema}/{trabajo_id}/{run_id}/`, y se borra a los 7 días. La URL firmada (V4, solo lectura de ese objeto) vence en 1 hora y la firma el backend con la cuenta `railway-lanzador` ([138](./138-agentes-adaptador-runtime.md)). El contenedor del bot no tiene ningún otro acceso al bucket.

Reglas:

- Hasta 2 millones de filas o 200 MB por archivo; si pasa, devuelve `codigo: lote_muy_grande` con la sugerencia de partir por mes.
- Las conversaciones salen sin teléfono: el cliente va por id y razón social. Ningún archivo lleva teléfono ni email.
- La consulta corre con `statement_timeout` de 60 s, en réplica si existe, para no frenar al agente de WhatsApp (principio 8).
- Registra traza `paso` automático: «Exporté 18.240 pedidos de nov-2025 a oct-2026».

### `registrar_traza`

`tipo` (`plan`, `paso`, `hallazgo`, `error`, `fin`), `estado`, `linea`, `datos_path` opcional, `datos` opcional (para `plan`, la lista de pasos), `cierra_id` opcional, `clave`. La `pregunta` no va acá: es `crear_pregunta`.

Emite `trabajo.paso`. Una `linea` de más de 280 caracteres se rechaza con `campo_invalido`.

### `crear_pregunta`

`texto`, `banda` (default la del tenant para preguntas), `bloquea` (bool). Si `bloquea`, el trabajo pasa a `esperando_humano`. Crea la traza `pregunta` y emite `pregunta.creada`.

### `leer_contexto`

`trabajo_id`, `desde_id` opcional. Devuelve el contexto del trabajo y las reglas aceptadas del tenant. El bot lo llama al despertar por `contexto.aportado`, no en bucle.

### `publicar_reporte`

`titulo`, `resumen`, `secciones` (lista de bloques: `texto`, `tabla`, `grafico`, `hallazgo`), `datos_paths`. El backend arma la página y el PDF ([141](./141-agentes-reportes.md)), guarda el Reporte, cierra el trabajo y emite `reporte.listo`. Solo el bot responsable del trabajo puede publicar.

### `delegar` (solo jefe de cuenta)

`bot_rol`, `instruccion`, `clave`. Suma el bot al trabajo como colaborador y emite `trabajo.delegado` con la instrucción, que el dispatcher convierte en un run del bot. Rechaza un rol que el tenant no tiene o un bot pausado. Es una tarea del certificado (`delegar`).

### `guardar_archivo`

`nombre`, `contenido` (texto hasta 10 MB: CSV, JSON o Markdown), `tipo`. Guarda en el bucket, en `{schema}/{trabajo_id}/{run_id}/`, y devuelve `archivo_path`. Es la única forma de que un archivo salga del contenedor. Sirve para que los cálculos intermedios queden enlazados desde la traza.

### Tools existentes que se reutilizan

`buscar_pedidos`, `consultar_pedidos`, `buscar_clientes`, `ver_cliente`, `buscar_productos`, `ver_producto`, `buscar_zonas`, `buscar_conversaciones`, `ver_conversacion`, `metricas_conversaciones`, `metricas_whatsapp`, `busquedas_sin_match`, `ver_memoria` y `editar_memoria`. Se montan también en `/agentes/mcp` con el mismo registro. `editar_gobierno` y `confirmar` quedan solo del lado humano en el MVP.

---

## Conversión automática en Propuesta

Hoy `confirmar` (132) deja el borrador en `pendiente_aprobacion` cuando la autonomía es `aprobar`. El MVP lo hace sin que el bot llame a `confirmar`:

1. Una tool `editar_*` del MCP de agentes arma el borrador como siempre.
2. El servidor mira el nivel de la tarea en el certificado vigente.
3. L4 y L5: confirma en el acto con `clave_idempotencia` derivada del borrador y devuelve el resultado. L4 además crea el Aviso.
4. L3: guarda `bot_id` y `trabajo_id`, pasa el borrador a `pendiente_aprobacion` y devuelve `{estado: "propuesta", borrador_id, link}`. Registra traza `paso` en `esperando` («Propuse agregar al playbook: …»).
5. L2 o L1: no arma borrador. Devuelve `codigo: fuera_de_certificado` con la sugerencia de dejar un `hallazgo`.

La decisión en la Bandeja aplica el borrador con el mismo camino que `confirmar` y emite `contexto.aportado` al bot que propuso, con la decisión y el motivo.

En el MVP la única escritura de los bots es `editar_memoria` (resultados L5, playbook L3).

### Decisión abierta: quién aplica una propuesta aprobada (29/10/2026)

En la prueba de almaro el curador propone con `proponer_cambios_productos` y la aprobación la aplica `POST /admin/agentes/propuestas/resolver` (`services/agentes_catalogo.resolver_propuesta`). Es código, sin modelo: toma el lock de la propuesta, verifica que no esté resuelta y aplica cada producto solo si sigue como estaba al proponerlo; los que cambiaron quedan como `salteados`. Faka planteó que lo aplique el agente, no un código. Queda sin decidir entre:

| Opción | Cómo | A favor | En contra |
|--------|------|---------|-----------|
| A. Híbrido (recomendada) | El backend aplica el diff aprobado tal cual. La decisión emite `contexto.aportado` (ya previsto arriba) y un run nuevo del bot verifica el resultado, vuelve a proponer los `salteados` y cierra el trabajo con su resumen | Lo aplicado es exactamente lo aprobado. El criterio queda en el bot. Aplicar no espera un contenedor | Un run extra por propuesta |
| B. Lo aplica el bot | Aprobar le da al bot un permiso de una sola vez atado a esa propuesta (productos y valores). Un run nuevo lo ejecuta | El agente hace todo el trabajo | El servidor igual tiene que validar que lo escrito coincide con lo aprobado (principio 1): termina siendo un merge más lento y más caro |

Se decide antes de construir la Bandeja del [135](./135-backoffice-agentico.md). Con cualquiera de las dos, la pantalla Equipo de agentes (rama `feat/agentes-panel` en backend y backoffice) sigue llamando a `resolver`.

---

## Errores

Se suman a los códigos del 132: `token_revocado`, `token_vencido`, `trabajo_cerrado`, `fuera_de_certificado`, `lote_muy_grande`, `bot_pausado`, `se_edita_en_backoffice`.

## Plan de prueba

- Evals por rol con token de bot: el analista de ventas no ve `buscar_conversaciones`; el de conversaciones no ve `exportar_lote(entidad=pedidos)` si su certificado no tiene la fuente.
- Bajar una tarea a L1 en el certificado la saca de `list_tools` en la llamada siguiente.
- `editar_memoria(parte=playbook)` de un bot en L3 devuelve `propuesta` y aparece en la Bandeja; aprobarla escribe en `core.tenant_memoria`.
- Los cuatro tests del token por run (sección «Token por run»).
- `exportar_lote` con un filtro que nombra otro tenant: el archivo sale vacío o con datos del tenant del token, nunca del otro.
- `encargar_analisis` dos veces con la misma clave: un trabajo.
