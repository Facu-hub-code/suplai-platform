# 132 — MCP de Suplai Sales para agentes y humanos

**Estado:** Borrador para revisión.
**Fecha:** 2026-10-24
**Repos:** `backend-supabase` (`mcp_server/`, `services/mcp_*`, `services/oauth/`), `suplai-platform` (este spec).
**Relaciona:** [094](./094-claude-mcp-manual.md) (MCP manual), [038](./038-copilot-agentes-especialistas.md) (agentes especialistas en el Copilot), [116](./116-mcp-pedidos-crud.md) (pedidos), [117](./117-mcp-canal-erp-o-carga.md)–[123](./123-mcp-erp-gescom.md) (ERP), [126](./126-mcp-una-agenda.md) (una agenda).
**Supersede:** la superficie de 52 tools de `mcp_server/superficie.py`. Las specs 094–126 siguen valiendo para la lógica de servicios; cambian los nombres y la forma de las tools.

---

## Objetivo

Que el MCP de cada distribuidora lo use, sobre todo, un equipo de agentes que trabaja solo, y que una persona también lo pueda usar para preguntas sueltas.

Hoy el MCP está pensado para una persona que conversa con Claude: 52 tools con nombres distintos para lo mismo (`buscar`, `explorar`, `listar`, `consultar`, `traer`), escrituras con un nombre que no dice qué hacen (`previsualizar_*`) y una familia ERP aparte. Para un agente que llama cientos de veces por día, eso es ruido: elige mal la tool, pide de más y no sabe qué puede hacer sin preguntar.

Este spec define:

1. Quién usa el MCP y con qué permisos.
2. Una convención de nombres única y el catálogo nuevo (de 52 a 37 tools).
3. El contrato de lectura (campos y filtros en la firma, origen Suplai o ERP).
4. El contrato de escritura (borrador, riesgo, confirmar, aprobación del dueño).
5. El gobierno: autonomía, límites, auditoría y kill switch, aplicados en el servidor y no en el prompt.
6. La memoria del tenant y los eventos que despiertan a los agentes.

---

## Quién usa el MCP

```mermaid
flowchart TD
  D[Dueño de la distribuidora<br/>reportes y aprobaciones por WhatsApp] --> G[Capa de gobierno<br/>autonomía, límites, auditoría, kill switch]
  G --> J[Jefe de cuenta<br/>agenda diaria, semanal y por eventos]
  J --> A[Analista<br/>ventas y churn]
  J --> S[Supervisor<br/>QA del agente]
  J --> C[Catálogo<br/>precios, stock, ERP]
  J --> V[Activador<br/>campañas y promos]
  A --> M[MCP de Suplai Sales por distribuidora<br/>borrador, confirmar, OAuth por tenant]
  S --> M
  C --> M
  V --> M
  M --> T[Memoria del tenant<br/>playbook, objetivos, resultados]
  M --> X[Suplai Sales core<br/>agente, pedidos, catálogo, ERP]
```

| Actor | Qué hace con el MCP | Volumen |
|---|---|---|
| **Jefe de cuenta** (orquestador) | Lee eventos, memoria y resultados. Arma la agenda y reparte trabajo. Casi no escribe: delega. | Alto, en lectura |
| **Analista** | Ventas, churn, clientes en riesgo, rendimiento por zona y vendedor. Escribe resultados en la memoria. | Alto, solo lectura |
| **Supervisor** | Lee conversaciones, prueba el agente, diagnostica búsquedas, propone cambios al prompt y a los productos (alias, descripciones). | Medio, con escrituras de riesgo |
| **Catálogo** | Precios, stock, productos y promos. Compara con el ERP e importa. | Medio, con escrituras frecuentes |
| **Activador** | Plantillas, grupos, agendas, secuencias y promos. Mide envíos. | Medio, con escrituras que llegan a clientes |
| **Humano** (dueño, operador de Suplai) | Preguntas puntuales, aprobaciones y ajustes a mano. | Bajo |

El MCP es el único camino de los agentes hacia los datos y las acciones. Ningún agente toca la base ni la API del core por fuera del MCP: así el gobierno y la auditoría valen para todos.

---

## Principios de diseño

| Principio | Qué implica | Por qué |
|---|---|---|
| Agentes primero, humanos también | Respuestas estables en JSON con ids y totales, y un `resumen` corto en lenguaje natural para la persona. | El agente parsea; la persona lee. Una sola tool sirve a los dos. |
| Un verbo por tipo de acción | `buscar_*`, `ver_*`, `editar_*`, `confirmar`. | El modelo elige la tool por el verbo sin leer 52 descripciones. |
| Familias del modelo de negocio | Productos, clientes, pedidos, vendedores, zonas, WhatsApp, conversaciones, agente, notificaciones. | Son las entidades que entiende el dueño y que ya existen en el core. |
| El ERP es un origen, no una familia | Parámetro `origen` en las lecturas e `importar_erp` en las escrituras. | El agente no tiene que saber qué ERP tiene el tenant. |
| Nada se escribe sin `confirmar` | `editar_*` deja un borrador. | Es el patrón que ya funciona; se mantiene. |
| Las reglas viven en el servidor | Autonomía, límites y kill switch se validan en `confirmar`. | Un prompt se puede saltear; el servidor no. |
| Cada llamada dice quién y por qué | `agente` y `motivo` en las escrituras; quedan en la auditoría. | El dueño tiene que poder reconstruir qué hizo cada agente. |

---

## Convención de nombres

| Verbo | Uso | Reemplaza |
|---|---|---|
| `buscar_<familia>` | Varias filas con filtros (GET de una colección). | `buscar_*`, `explorar_*`, `listar_*`, `consultar_*`, `traer_*_erp`, `metricas_*` |
| `ver_<cosa>` | La ficha completa de una fila (GET de una). | `ver_*` |
| `editar_<familia>` | Alta, edición o baja con `accion`. Deja un borrador. | `previsualizar_*` |
| `confirmar` | Ejecuta un borrador. | Igual que hoy |

- `editar` y no `cargar`: la misma tool da de alta, edita y borra. `cargar` se lee como solo alta.
- Una familia se parte en una segunda tool `editar_*` solo cuando la entidad tiene otra clave o otro ciclo de vida (las promociones no son productos; las listas de precios tampoco).
- Toda respuesta de `editar_*` termina igual: «Borrador listo, no se guardó nada. Para aplicarlo, confirmar con `borrador_id`.»

---

## Catálogo de tools (37)

### Orientación y gobierno

| Tool | Qué hace |
|---|---|
| `guia_suplai` | Recetas por tema. Para el humano y para el arranque de un agente. |
| `confirmar` | Ejecuta un borrador si el gobierno lo permite; si no, pide aprobación al dueño. |
| `buscar_borradores` | Borradores del tenant y su estado: pendiente, aprobado, rechazado, vencido, aplicado. |
| `buscar_eventos` | Lo que pasó desde un cursor: pedido nuevo, sin stock, cliente en riesgo, envío fallido, reclamo en una charla, sync de ERP. |
| `ver_memoria` / `editar_memoria` | Playbook, objetivos y resultados del tenant. |
| `reportar_problema` | Reporte a soporte de Suplai. Reemplaza `previsualizar_reporte`, que se confundía con el reporte de ventas. |

### Productos

| Tool | Qué hace |
|---|---|
| `buscar_productos` | Ficha completa: stock, precio por lista, alias, categoría, tags, promos vigentes, estado en el ERP. Filtrable por casi todos los campos. |
| `ver_producto` | Un SKU con todo, incluido el historial de precio y stock. |
| `editar_productos` | `accion`: alta, editar (nombre, descripción, alias, stock, precio por lista, categoría, tag), ocultar, baja, `importar_erp`. Al confirmar un cambio de nombre, descripción o alias, re-vectoriza solo. |
| `buscar_listas` / `editar_listas` | `tipo`: listas de precios, categorías, tags. |
| `buscar_promociones` / `editar_promociones` | Promos y combos, con sus componentes y listas. |

### Clientes

| Tool | Qué hace |
|---|---|
| `buscar_clientes` | Filtros: zona, etiqueta, vendedor, lista de precios, estado de compra, WhatsApp, código. Une `buscar_clientes` y `explorar_clientes`. |
| `ver_cliente` | Ficha, últimos pedidos, conversación, etiquetas, zona y vendedor. |
| `editar_clientes` | Alta, edición, carga masiva, asignar lista, zona o vendedor. |
| `buscar_etiquetas` / `editar_etiquetas` | Etiquetas; `editar_etiquetas` también las asigna a clientes. Las etiquetas son filtro de `buscar_clientes`. |

### Pedidos

| Tool | Qué hace |
|---|---|
| `buscar_pedidos` | Pedidos y líneas, con `origen` Suplai o ERP en la capa de servicios. |
| `editar_pedidos` | Alta y baja con reglas de seguridad (ver «Escritura de pedidos»). |

### Vendedores y zonas

| Tool | Qué hace |
|---|---|
| `buscar_vendedores` | Con el id y el nombre de la zona asignada. |
| `editar_vendedores` | Alta, edición, baja, asignar zona. |
| `buscar_zonas` | Id, nombre, cantidad de clientes, vendedores y ventas del período. Reemplaza `listar_geozonas` y `mapa_zonas`. |
| `editar_zonas` | Alta, ajustar polígono, asignar clientes y vendedores, desactivar. Es la única forma de crear zonas: reemplaza `previsualizar_zona`. |

### WhatsApp

| Tool | Qué hace |
|---|---|
| `buscar_plantillas` / `editar_plantillas` | Plantillas con su estado en Meta y sus métricas de uso. |
| `buscar_envios` | Envíos con métricas (entregados, leídos, respondidos, pedidos generados), por fecha y con el id de la conversación que siguió. |
| `editar_envios` | `tipo`: agenda, grupo o secuencia. Las agendas mandan la variable producto: fija para todos (`dynamic_params`) o por cliente (sus productos más comprados). |

### Conversaciones

| Tool | Qué hace |
|---|---|
| `buscar_conversaciones` | Filtros: fecha, cliente, zona, etiqueta, con o sin pedido, con reclamo. `incluir_metricas` trae el resumen y el tablero. |
| `ver_conversacion` | El hilo completo con las tools que corrió el agente. |

### Agente

| Tool | Qué hace |
|---|---|
| `probar_agente` | Un turno del agente sin WhatsApp, con las tools que corrió (el lab de `/lab/mcp`). |
| `diagnosticar_busqueda` | Con frases, explica el ranking. Sin frases, diagnostica las búsquedas reales que no encontraron nada. Une `busquedas_sin_match`. |
| `ver_prompt` / `editar_prompt` | El prompt completo por secciones; `editar_prompt` reemplaza, agrega o quita secciones (ver «Edición del prompt»). |

### Notificaciones

| Tool | Qué hace |
|---|---|
| `buscar_notificaciones` | `tipo`: canal, pedido o envío. Para la distribuidora: vendedores y administrativos. |
| `editar_notificaciones` | Quién recibe qué aviso y por qué canal. |

Los reportes y aprobaciones al dueño por WhatsApp salen por la capa de gobierno, no por estas tools.

---

## Contrato de lectura

Toda tool `buscar_*` acepta los mismos parámetros:

| Parámetro | Tipo | Qué hace |
|---|---|---|
| `campos` | lista cerrada | Columnas a devolver. Sin campos, devuelve un conjunto corto por defecto. |
| `filtros` | lista de `{campo, op, valor}` | `op` en `=`, `!=`, `<`, `<=`, `>`, `>=`, `contiene`, `en`, `entre`, `vacio`. |
| `orden` | `{campo, dir}` | Orden por un campo permitido. |
| `cursor` / `tamano` | texto / 1–200 | Paginación por cursor, estable entre llamadas. |
| `origen` | `suplai` · `erp` · `comparar` | Solo en productos, clientes y pedidos. `comparar` marca las diferencias. |

- Los campos y los operadores válidos son `enum` en el esquema JSON de la tool. El modelo los ve en la firma sin hacer una llamada previa: es el `SELECT *` de la idea, sin SQL.
- No hay SQL libre. La capa de servicios arma la consulta con los campos permitidos y el schema del tenant. Así no hay inyección ni lecturas de otro tenant.
- Respuesta: `{"filas": [...], "total": n, "cursor": "...", "resumen": "texto para la persona"}`.

---

## Contrato de escritura

### Borrador

`editar_*` valida, calcula el efecto y guarda un borrador. No cambia nada. La respuesta trae:

| Campo | Qué es |
|---|---|
| `borrador_id` | Lo que se pasa a `confirmar`. |
| `efecto` | Qué cambia: filas, antes y después, cantidad. |
| `riesgo` | `bajo`, `medio` o `alto`, según la acción y el tamaño (ver gobierno). |
| `avisos` | Lo que conviene saber antes de confirmar: duplicados, mezcla con datos del ERP, clientes sin lista. |
| `vence` | Los borradores vencen; uno vencido no se confirma. |

Toda escritura pide `agente` (quién) y `motivo` (por qué, en una frase). Para el humano los completa el servidor.

### Confirmar

`confirmar(borrador_id, clave_idempotencia)`:

1. Revisa el kill switch del tenant y del agente.
2. Revisa los límites (ver gobierno).
3. Si la autonomía de esa acción es `auto`, aplica. Si es `aprobar`, manda el pedido de aprobación al dueño por WhatsApp y devuelve `estado: pendiente_aprobacion`. Si es `prohibido`, rechaza.
4. Registra el resultado en la auditoría.

`clave_idempotencia` evita que un reintento del agente aplique dos veces.

### Escritura de pedidos

- Deduplica por número de comprobante y cliente: un pedido que ya existe no se carga de nuevo.
- Si el tenant tiene ERP conectado, el borrador avisa que mezclar pedidos cargados a mano con los del ERP es peligroso, y `confirmar` exige `forzar_mezcla_erp`.
- La baja es lógica (`deleted_at`) y solo para pedidos cargados por el MCP que no se enviaron al ERP. Riesgo `alto` siempre.

### Edición del prompt

- `editar_prompt` opera sobre secciones con nombre: `reemplazar`, `agregar`, `quitar`.
- El borrador muestra el diff completo.
- Se rechaza si falta una sección obligatoria o si se borra más del 30 % del texto.
- Riesgo `alto` siempre: lo aprueba el dueño o un operador de Suplai.
- Segunda etapa: un chequeo de contradicciones entre la sección nueva y las demás.

---

## Gobierno

Vive en el servidor del MCP y se configura por tenant en `metadata.gobierno` de `public.distribuidoras`.

### Roles y permisos

Cada agente tiene su token OAuth por tenant con un paquete de scopes. Los scopes son los de hoy (`services/oauth/constants.py`), agrupados por rol:

| Rol | Lee | Escribe |
|---|---|---|
| Jefe de cuenta | todo | memoria |
| Analista | pedidos, productos, clientes, conversaciones, vendedores, zonas, eventos | memoria (resultados) |
| Supervisor | conversaciones, productos, prompt | productos (alias, descripción), prompt, búsqueda |
| Catálogo | productos, promos, listas, ERP | productos, promos, listas |
| Activador | clientes, etiquetas, plantillas, envíos, promos | plantillas, envíos, etiquetas, promos |
| Humano | según sus scopes | según sus scopes |

Un agente no ve las tools que su token no alcanza (igual que hoy con `filtrar_visibles`).

### Autonomía por acción

| Acción | Default |
|---|---|
| Lecturas | `auto` |
| Memoria, alias, descripciones | `auto` |
| Stock, precios hasta el límite, etiquetas, grupos | `auto` |
| Envíos a clientes, plantillas nuevas, promos | `aprobar` |
| Precios por encima del límite, bajas de productos, prompt | `aprobar` |
| Baja de pedidos, mezcla con ERP | `aprobar` |

El dueño cambia los defaults desde el admin. Un humano con el scope alcanza para aprobar.

### Límites

Ejemplos de límites por tenant, validados en `confirmar`:

- `max_envios_dia`: clientes alcanzados por WhatsApp por día.
- `max_cambio_precio_pct`: cambio de precio por SKU sin aprobación.
- `max_bajas_productos`: bajas por borrador.
- `max_escrituras_hora`: por agente, para cortar un loop.

### Auditoría

Cada llamada queda en `public.mcp_auditoria` con agente, motivo, borrador, riesgo y quién aprobó. El dueño recibe un resumen diario por WhatsApp: qué hizo cada agente, qué quedó pendiente de aprobar, qué se rechazó.

### Kill switch

- `gobierno.pausado` frena todas las escrituras del tenant.
- `gobierno.agentes_pausados` frena las de un agente.
- Las lecturas siguen andando, para poder diagnosticar.
- Lo puede activar el dueño por WhatsApp («pausar agentes») o desde el admin.

---

## Memoria del tenant y eventos

**Memoria** (`ver_memoria`, `editar_memoria`):

| Parte | Qué guarda | Quién la escribe |
|---|---|---|
| Playbook | Cómo trabaja esta distribuidora: horarios, tono, reglas comerciales, qué no hacer. | Humano; los agentes proponen y el dueño aprueba. |
| Objetivos | Metas del período: ventas, reactivación, cobertura por zona. | Humano y jefe de cuenta |
| Resultados | Qué se hizo y qué dio: campañas, cambios de precio, pruebas del agente. | Cada agente al terminar una tarea |

**Eventos** (`buscar_eventos`): cola por tenant con cursor, para que el jefe de cuenta no tenga que recorrer todo. Tipos iniciales: `pedido_nuevo`, `pedido_error_erp`, `sin_stock`, `cliente_en_riesgo`, `envio_fallido`, `reclamo_en_charla`, `sync_erp`, `borrador_aprobado`, `borrador_rechazado`.

---

## Respuestas para agentes y para humanos

- Siempre JSON con la misma forma por verbo, ids reales y totales.
- `resumen`: dos o tres líneas para la persona; el agente lo puede ignorar.
- Errores con `codigo` estable (`campo_invalido`, `sin_permiso`, `limite_excedido`, `pausado`, `borrador_vencido`), el campo que falló y qué hacer.
- Las tools con interfaz (`ui_apps.py`, mapas, paneles) se mantienen para el humano y no son necesarias para el agente.

---

## Migración de las 52 tools

| Hoy | Pasa a |
|---|---|
| `consultar_pedidos` | `buscar_pedidos` |
| `previsualizar_carga_pedidos` | `editar_pedidos` |
| `explorar_productos`, `previsualizar_stock`, `previsualizar_precios` | `buscar_productos`, `editar_productos` |
| `previsualizar_correccion`, `previsualizar_ocultar_producto`, `previsualizar_aliases` | `editar_productos` |
| `listar_catalogo` | `buscar_listas`, `buscar_promociones` |
| `previsualizar_lista_precios`, `previsualizar_categoria`, `previsualizar_tag_producto` | `editar_listas` |
| `previsualizar_promocion` | `editar_promociones` |
| `previsualizar_carga` | `editar_productos` y `editar_clientes` (hoy mezcla los dos) |
| `buscar_clientes`, `explorar_clientes` | `buscar_clientes` |
| `previsualizar_lista_clientes` | `editar_clientes` |
| `listar_etiquetas`, `previsualizar_etiqueta` | `buscar_etiquetas`, `editar_etiquetas` |
| `listar_conversaciones`, `metricas_conversaciones` | `buscar_conversaciones` |
| `ver_conversacion` | `ver_conversacion` |
| `listar_plantillas`, `metricas_whatsapp`, `previsualizar_plantilla` | `buscar_plantillas`, `editar_plantillas` |
| `listar_envios` | `buscar_envios` |
| `previsualizar_agenda`, `previsualizar_grupo`, `previsualizar_secuencia` | `editar_envios` |
| `listar_geozonas`, `mapa_zonas` | `buscar_zonas` |
| `previsualizar_zona` | `editar_zonas` |
| `listar_vendedores`, `previsualizar_vendedor` | `buscar_vendedores`, `editar_vendedores` |
| `ver_notificaciones`, `ver_notificaciones_pedido`, `ver_envios_notificacion`, `previsualizar_notificaciones` | `buscar_notificaciones`, `editar_notificaciones` |
| `busquedas_sin_match`, `diagnosticar_busqueda` | `diagnosticar_busqueda` |
| `ver_seccion_prompt`, `previsualizar_seccion_prompt` | `ver_prompt`, `editar_prompt` |
| `probar_agente` | `probar_agente` |
| `traer_clientes_erp`, `traer_productos_erp`, `traer_precios_erp`, `traer_promociones_erp` | `origen="erp"` en `buscar_*`; `importar_erp` en `editar_productos` |
| `previsualizar_reporte` | `reportar_problema` |
| `guia_suplai`, `confirmar` | Igual |

Los nombres viejos quedan como alias ocultos hasta que pasen las evals con los nuevos; después se borran.

---

## Etapas

| Etapa | Qué | Listo cuando |
|---|---|---|
| 1. Lectura | Los `buscar_*` con `campos`, `filtros`, `orden`, `cursor` y `origen`. `ver_*`. | Toda consulta de hoy sale con las tools nuevas. |
| 2. Escritura | `editar_*`, borrador con riesgo, `confirmar` con idempotencia. Pedidos seguros. Re-vectorizado al editar productos. | Todo borrador de hoy anda con los nombres nuevos. |
| 3. Gobierno | Autonomía, límites, kill switch, aprobación por WhatsApp, auditoría con agente y motivo, `buscar_borradores`. | Un agente no puede pasar un límite ni escribir con el tenant pausado. |
| 4. Agentes | Tokens por rol, `buscar_eventos`, memoria del tenant. Evals por rol. | El jefe de cuenta corre una agenda diaria en un tenant de prueba. |
| 5. Limpieza | Borrar las 52, actualizar guías, scopes y evals. | Evals verdes solo con las 37. |

Arcor primero: las etapas 1 a 3 se prueban con almaro y gonzales.

---

## Base de datos

Este spec necesita guardar borradores con estado, eventos, memoria y la configuración de gobierno. Las columnas y tablas nuevas se piden con permiso antes de crearlas (regla del equipo). Propuesta a revisar:

| Qué | Dónde | Alternativa sin migración |
|---|---|---|
| Configuración de gobierno | `public.distribuidoras.metadata.gobierno` | Ya es JSON: no hace falta columna |
| Agente, motivo, riesgo y aprobación en la auditoría | Columnas en `public.mcp_auditoria` | Dentro de `parametros` (JSON), menos consultable |
| Borradores con estado | Tabla `core.mcp_borradores` | Los previews de hoy, sin estado de aprobación |
| Eventos | Tabla `core.mcp_eventos` | Leer de las tablas de origen en cada llamada, más lento |
| Memoria | Tabla `core.tenant_memoria` | `metadata.memoria` (JSON), con un límite de tamaño |

---

## Fuera de alcance

- Los agentes en sí (prompts, agenda del jefe de cuenta, cómo corren). Este spec es la superficie que usan.
- SQL libre o NL→SQL desde el MCP.
- Agentes creados por el tenant: los roles son producto de Suplai, como en 038.

---

## Decisiones abiertas

1. **Aprobación del dueño:** ¿un mensaje por borrador o un lote por día?
2. **Escritura del jefe de cuenta:** ¿solo delega o puede confirmar lo que un especialista le propone?
3. **Memoria:** ¿tabla propia o JSON en `metadata`, para arrancar?
4. **Alias de los nombres viejos:** ¿cuánto tiempo conviven?

---

## Plan de prueba

**CI** (`mcp_server/evals`):

- Una eval por rol con su token: el agente ve solo sus tools, elige la tool correcta por el verbo y no pasa los límites.
- Contrato: todo `buscar_*` acepta los mismos parámetros, todo `editar_*` devuelve borrador con riesgo, `confirmar` respeta idempotencia, kill switch y límites.
- Migración: cada caso de las evals actuales tiene su equivalente con las tools nuevas.

**Prueba humana:**

1. Un humano pregunta «¿qué vendió la zona norte este mes?» y lo resuelve en una llamada.
2. El Activador arma un envío a 500 clientes con un límite de 300: el borrador avisa y `confirmar` pide aprobación.
3. El dueño responde «pausar agentes» por WhatsApp: las escrituras se frenan y las lecturas siguen.
4. El Catálogo compara precios con `origen="comparar"` e importa los que difieren: queda auditado con agente y motivo.
