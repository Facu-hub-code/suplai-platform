# 066 — Supervisor: intérprete de playbooks + receta carrito abierto

**Estado:** En implementación  
**Fecha:** 2026-09-10  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas:** `feat/copilot-supervisor-langgraph`  
**Extiende:** [062-copilot-supervisor-langgraph.md](./062-copilot-supervisor-langgraph.md), [065-copilot-supervisor-cancel-deadlock.md](./065-copilot-supervisor-cancel-deadlock.md)  
**Índice:** [001-suplai-copilot.md](./001-suplai-copilot.md)

---

## Objetivo

El chip de carrito abierto no puede depender de un ReAct generalista. El Supervisor clasifica el pedido: si matchea una **receta**, un **intérprete** avanza un plan con estado (`pending` / `done` / `skipped` / `failed`). El LLM no elige el siguiente oficio. v1: una sola receta (`carrito_abierto`). El resto sigue el ReAct de 062.

Caso canónico visto en demo (10 sep 2026): el operador canceló etiquetar y crear plantilla con motivos válidos; el ReAct volvió a pedir etiquetar seis veces. El playbook marca `skipped` y sigue; no reencola el mismo `step_id`.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Forma de las recetas | Datos (registro Python) + un grafo intérprete | Cada caso nuevo es una receta, no un `StateGraph` | Un subgrafo compilado por caso (N grafos, N edges) |
| Quién elige el siguiente paso | `route` mira `plan[]` + `facts` | El bucle de demo nació de `_NUDGE_USER` + prompt de 6 pasos | Seguir en ReAct con más hints |
| Classifier v1 | Chip canónico + keywords, sin LLM | El chip ya existe y es determinístico | Nodo LLM classifier (costo y drift) |
| Observación | Artefactos (`table`, `action_preview`, `opens_modal`), no el texto del empleado | Lucía decía «Grupo creado» y devolvía preview de tag | Confiar en `respuesta` |
| Consulta al empleado | Un pedido por paso; sin `_WRITE_INSTRUCTION` mega | El mega-prompt mezclaba etiquetar+grupo+plantilla+agenda | Seguir inyectando el bloque de 062 |
| HITL | Reusa `confirm_node` / interrupt de 062 | La UI no cambia | Nuevo modal de playbook |
| Cancelar | Señal sobre el `current_step_id` (`skip` / `abort` / `ask`) | 065 pregunta «por qué» pero no tiene plan | Resetear `write_cancelled` y volver al ReAct |
| Reintentos | Mismo `step_id`: máx. 2 intentos si `failed`; nunca si `done`/`skipped` | Corta el loop de etiquetar | `recursion_limit` por invoke (cada Sí es un invoke nuevo) |
| Fallback | Pedido que no matchea → ReAct 062 | Carlos/Nina/Omar y ad-hoc no merecen receta | Forzar playbook en todo |

---

## Alcance explícito

### Incluido (v1)

- Registro de recetas + intérprete: `classify` → `playbook_route` → `confirm`? → `tools` → `observe` → `route`.
- Receta `carrito_abierto`: listar → etiquetar (skippable) → grupo → listar plantillas (PENDING no usable) → crear plantilla (skippable) → agenda → resumen.
- Matching del chip de Supervisor y de «carrito + grupo + (plantilla\|agenda)».
- 0 `client_ids` → abort con el copy de 065; no llama a Sofía ni Martín.
- Cancelar etiquetar + «ya están etiquetados» → `skipped`, sigue a grupo (etiqueta default `Carrito`).
- Cancelar crear plantilla + «tenemos una» → `skipped`; si no hay APPROVED en `facts`, pregunta el nombre.
- `facts` en el state: `client_ids`, `audience_count`, `etiqueta`, `grupo_id`, `plantilla`.
- Tests unitarios del matching, observe, skip/abort, y un e2e del grafo con empleados mockeados.
- Specs puntero en backend y backoffice. UI reusa interrupt + bitácora.

### Fuera de alcance

- Recetas extra («no responden», «no compran»).
- Classifier LLM / embeddings.
- Reescribir packs 1:1.
- Nodo LangGraph por paso de receta.
- Más hints en `_SUPERVISOR_PROMPT` del ReAct.
- Undo de escrituras ya ejecutadas (`dry_run=false`).
- Cambio de UI (salvo que el copy de cierre ya exista por 065).

---

## Orden de implementación

Cross-repo. Merge **backend → backoffice**. Spec en platform en paralelo.

| # | Repo | Qué |
|---|------|-----|
| 1 | `backend-supabase` | Recetas, classify, engine, observe, nodos, wire en `graph.py`, tests |
| 2 | `suplai-platform` | Este spec + enlace en 001 y 062 |
| 3 | `product-management-app` | Puntero; sin cambio de UI en v1 |

Rama en los tres: `feat/copilot-supervisor-langgraph`. Merge humano en GitHub.

---

## Migración de base de datos

Sin migración de BD. `plan` y `facts` viven en el checkpoint del orquestador (`core.copilot_orchestrator_runs`).

---

## Plan de prueba en CI/CD

- `tests/test_copilot_supervisor_playbook.py`:
  - Chip / keywords → `carrito_abierto`; «hola» → sin receta.
  - 0 clientes → `aborted`, `invoke_employee` solo Lucía listar.
  - Cancelar etiquetar + «ya están etiquetados» → no reencola `etiquetar`; siguiente `crear_grupo`.
  - Sofía lista APPROVED `cart_open` → `crear_plantilla` queda `skipped`.
  - `carrito_abandonado` PENDING no cuenta como usable.
  - Mismo `step_id` `done`/`skipped` no se despacha otra vez.
- `tests/test_copilot_supervisor_graph.py` (062/065) sigue verde: pedidos que no matchean van al ReAct.
- Gap: sin Playwright e2e obligatorio.

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenant `demo`.

1. Copilot → Supervisor → chip de carrito abandonado.
2. Si hay clientes: interrupt de etiquetar. Cancelar y escribir «creo que ya están etiquetados» → **no** vuelve a pedir etiquetar; pide grupo o avanza.
3. Si Sofía lista una APPROVED usable: no pide crear plantilla.
4. Si 0 clientes en el listado: advierte y **no** pide plantilla ni agenda.
5. Un pedido tipo «¿qué vendimos este mes?» sigue el ReAct (Carlos), no el playbook.
6. Chat 1:1 con Lucía intacto.

---

## Criterios de aceptación

- El chip de carrito dispara el playbook, no el ciclo ReAct con nudge.
- El plan es visible en el state del checkpoint (`plan[]` + `facts`).
- Cancelar un paso skippable no reabre ese paso.
- 0 audiencia cierra el playbook.
- Pedidos fuera de receta no se rompen.

## Receta v1 (`carrito_abierto`)

```text
listar_carrito ── 0 ids ── abort
       │
       ▼
etiquetar ── skip («ya están») ──► crear_grupo
       │
       ▼
crear_grupo
       │
       ▼
listar_plantillas ── APPROVED usable ── skip crear_plantilla
       │
       ▼
crear_plantilla ── skip («tenemos una»)
       │
       ▼
crear_agenda → cerrar
```

## Referencias de código

- Intérprete: `backend-supabase/services/copilot/supervisor/playbook/`
- Grafo: `backend-supabase/services/copilot/supervisor/graph.py`
- Receta: `backend-supabase/services/copilot/supervisor/playbook/recipes.py`
- ReAct (fallback): `backend-supabase/services/copilot/supervisor/graph.py` (`supervisor_node`)
