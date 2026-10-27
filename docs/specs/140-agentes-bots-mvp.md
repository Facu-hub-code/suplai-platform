# 140 — Equipo de agentes: bots del MVP

**Estado:** Borrador. Los nombres de los bots son provisorios.
**Fecha:** 2026-10-27
**Repos:** `backend-supabase` (`services/agentes_prompts.py`, `services/agentes_prompts/*.md`, `scripts/agentes_alta_tenant.py`).
**Rama sugerida:** `feat/agentes-bots-mvp`.
**Relaciona:** [134](./134-mvp-equipo-de-agentes.md), [136](./136-agentes-modelo-de-datos.md) (certificado y niveles), [138](./138-agentes-adaptador-runtime.md) (cómo se lanzan), [139](./139-agentes-tools-mcp.md) (tools).

---

## Objetivo

Definir los tres bots que cubren las pruebas 1 y 2: qué hacen, con qué prompt, qué tools ven y con qué certificado arrancan. Dejar descrito el cuarto (activador) para que el modelo ya lo contemple.

### Criterios de aceptación

- Los prompts viven en el backend, versionados en git, y se arman con el certificado vigente. No viven en la imagen del contenedor: el entrypoint las pide con `leer_instrucciones` ([139](./139-agentes-tools-mcp.md)).
- Cada prompt nombra solo las tools que el certificado le da. Si el certificado cambia, el prompt del próximo run cambia solo.
- Cada bot registra un `plan` o un `paso` antes de su primera lectura grande, y un `fin` antes de terminar.
- Ningún prompt le pide al bot que consulte cada tanto si hay novedades.
- El alta de un tenant crea los tres bots con su modelo y su certificado v1. No hay tokens fijos: cada run recibe el suyo al lanzarse.

---

## Cómo se arma el prompt

`services/agentes_prompts.py` concatena, en este orden:

1. **Base común** (`base.md`): quién es el equipo, el tenant, el humano asignado, las reglas de traza (una línea humana por paso, en presente, sin jerga) y la regla de oro: si no podés explicar algo, preguntá con `crear_pregunta`; no inventes.
2. **Rol** (`jefe_de_cuenta.md`, `analista_ventas.md`, `analista_conversaciones.md`).
3. **Certificado vigente**: qué hace, fuentes, nivel por tarea en lenguaje natural («Podés anotar resultados en la memoria sin preguntar. Para cambiar el playbook, proponé»), reglas.
4. **Contexto del tenant**: playbook y objetivos vigentes de `core.tenant_memoria`, y reglas aceptadas.
5. **Este run**: `trabajo_id`, `run_id`, el evento que lo despertó y sus datos.

El prompt va en español rioplatense, como el resto del producto.

---

## Jefe de cuenta

| Campo | Valor |
|-------|-------|
| Rol | `jefe_de_cuenta` |
| Pruebas | 1 y 2 |
| Despierta con | `trabajo.creado`, `contexto.aportado` sin pregunta, `run.terminado` de un analista (vía dispatcher), `agenda.diaria`, `agenda.semanal` |
| Fuentes | Trabajos, trazas, memoria del tenant, métricas resumidas |

**Qué hace**

1. Lee el pedido y el contexto. Fija período y alcance si faltan, y los dice en el plan.
2. Registra el `plan`: lista de pasos con el bot que hace cada uno.
3. Delega con `delegar(bot_rol, instruccion)` ([139](./139-agentes-tools-mcp.md)): suma el bot al trabajo y emite el evento que lo lanza.
4. Cuando todos los analistas terminaron, lee sus hallazgos y archivos, consolida y llama `publicar_reporte`.
5. Si el humano pregunta cómo va (contexto sin pregunta), responde en la traza con un `paso` de resumen.

**Tareas y certificado v1**

| Tarea | Nivel |
|-------|-------|
| `planificar` | L4 |
| `delegar` | L4 |
| `consolidar_reporte` | L4 |
| `publicar_reporte` | L4 |
| `preguntar_humano` | L5 |
| `anotar_resultados` | L5 |
| `proponer_regla_playbook` | L3 |

Reglas iniciales: «No toques a ningún cliente.» «Si dos analistas se contradicen, decilo en el reporte; no elijas uno sin explicar.»

**Tools:** `registrar_traza`, `delegar`, `crear_pregunta`, `leer_contexto`, `publicar_reporte`, `ver_memoria`, `editar_memoria`, `buscar_pedidos` (para validar totales del analista).

---

## Analista de ventas

| Campo | Valor |
|-------|-------|
| Rol | `analista_ventas` |
| Prueba | 1 |
| Despierta con | Delegación del jefe de cuenta, `contexto.aportado` a su pregunta |
| Fuentes | Pedidos, ítems, clientes, productos, zonas, vendedores |

**Qué hace**

1. `exportar_lote` de pedidos e ítems del período, y de clientes y productos.
2. Calcula con código sobre los archivos (no página por página): ventas por mes, tendencia, clientes que crecen y caen (comparando trimestres o mismo mes del año anterior), productos y zonas que más suben y bajan, concentración (Pareto).
3. Sube cada resultado intermedio con `guardar_archivo` ([139](./139-agentes-tools-mcp.md)) y, por cada hallazgo, registra `registrar_traza(tipo=hallazgo)` con la cifra y el `datos_path` de ese archivo.
4. Si no puede explicar algo relevante (un cliente del top 20 que dejó de comprar, una zona que cae más de 30 %), abre `crear_pregunta` sin bloquear y sigue con el resto.
5. Termina con `fin` y un resumen para el jefe de cuenta.

**Tareas y certificado v1**

| Tarea | Nivel |
|-------|-------|
| `leer_datos` | L5 |
| `calcular` | L5 |
| `registrar_hallazgo` | L5 |
| `preguntar_humano` | L5 |
| `anotar_resultados` | L5 |

---

## Analista de conversaciones

| Campo | Valor |
|-------|-------|
| Rol | `analista_conversaciones` |
| Prueba | 2 |
| Despierta con | Delegación del jefe de cuenta (agenda semanal o lote de `conversacion.cerrada`) |
| Fuentes | Conversaciones, mensajes, búsquedas sin match, métricas de conversaciones y WhatsApp |

**Qué hace**

1. `exportar_lote` de conversaciones y mensajes del período; `busquedas_sin_match` y `metricas_conversaciones`.
2. Clasifica cada conversación cerrada sin pedido: rechazo (con motivo: precio, stock, ya compró, no era el momento, atención), producto pedido que no encontró, oportunidad perdida (preguntó y no se le ofreció).
3. Agrupa motivos y productos, con ejemplos (id de conversación, sin teléfono).
4. Las conclusiones de motivo van como `hallazgo` con `confianza`. Un motivo que se repite y no se explica con los datos (por ejemplo «muchos dicen que ya compraron» sin pedido en Suplai) abre una pregunta: puede que compren por otro canal.

**Tareas y certificado v1**

| Tarea | Nivel |
|-------|-------|
| `leer_datos` | L5 |
| `clasificar_conversaciones` | L5 |
| `concluir_motivos` | L3 |
| `preguntar_humano` | L5 |
| `anotar_resultados` | L5 |

`concluir_motivos` en L3 quiere decir que el motivo general del período entra al reporte marcado «a confirmar» y como Propuesta de resultado en la memoria. El humano lo acepta o lo corrige en la Bandeja.

---

## Activador (siguiente fase, no se da de alta en el MVP)

| Campo | Valor |
|-------|-------|
| Rol | `activador` (ya existe en `ROLES_AGENTE`) |
| Prueba | 3 |
| Fuentes | Hallazgos de los analistas, clientes, promociones |

| Tarea | Nivel inicial |
|-------|---------------|
| `crear_seguimiento` | L3 |
| `enviar_en_ventana` | L3 |
| `enviar_por_agenda` | L3 |
| `pasar_contexto_al_vendedor` | L3 |

Regla del servidor (decisión 7): `enviar_en_ventana` solo si el último mensaje del comercio tiene menos de 24 horas; `enviar_por_agenda` solo como agenda de Suplai (`editar_envios`). Cualquier otro envío se rechaza, no se convierte en Propuesta. El check vive en el servicio de envíos, no en el prompt, y entra con el spec de la prueba 3.

---

## Alta en un tenant

```bash
python scripts/agentes_alta_tenant.py --schema cordoba_frost --humano <usuario_id>
```

1. Activa `metadata.agentes.habilitado` y los defaults de agenda, bandas y límites.
2. Crea los tres bots con su modelo y su certificado v1 (motivo «Alta inicial del MVP»).

## Evals

En `mcp_server/evals`, una por bot con el fake runtime del 138:

- Jefe de cuenta: con un pedido «ventas del último año», el primer paso es un `plan` y delega en el analista de ventas.
- Analista de ventas: con un dataset sembrado donde un cliente grande cae a cero, registra el hallazgo y abre una pregunta.
- Analista de conversaciones: con 20 conversaciones etiquetadas a mano, acierta el motivo en al menos 15.
- Todos: ningún bot termina sin `fin`; ninguno llama a una tool fuera de su certificado.
