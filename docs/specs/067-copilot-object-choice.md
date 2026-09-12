# 067 — Copilot: reuso vs creación (object_choice)

**Estado:** En implementación  
**Fecha:** 2026-09-11  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas:** `feat/copilot-supervisor-langgraph`  
**Extiende:** [038](./038-copilot-agentes-especialistas.md), [062](./062-copilot-supervisor-langgraph.md), [065](./065-copilot-supervisor-cancel-deadlock.md), [066](./066-copilot-supervisor-playbook.md)  
**Índice:** [001-suplai-copilot.md](./001-suplai-copilot.md)

---

## Objetivo

Los especialistas **buscan y puntúan** objetos existentes antes de crear. El HITL deja de ser «delegar permiso» (el especialista es el único que puede escribir) y pasa a una card con **hasta dos propuestas dry-run**: crear uno nuevo o reusar uno útil. El humano acepta crear, acepta la selección, o reintenta con un mensaje. Aplica al Supervisor y a los chats 1:1. La bitácora queda solo inline (sin sheet) y, si el grafo se traba (p. ej. modal de Meta), hay un chip de continuar.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Dónde vive el scoring | Código en la tool (`reuse.py`), no el LLM | El modelo olvidaba listar y duplicaba filas | Solo prompt; embeddings fuzzy (fuera de v1) |
| Cuándo pausar el grafo | **Después** de que el especialista corre en dry-run | El usuario elige sobre propuestas concretas, no sobre un permiso abstracto | Interrupt `es_escritura` antes del empleado (copy «delegar») |
| Artefacto | `object_choice` (create + reuse opcional) | Una card, tres acciones | Dos `action_preview` apilados; seguir con `supervisor_confirmation` |
| `write_intent` | Ya no saltea `dry_run` | Ejecutar al delegar saltaba el preview del payload | Ejecutar al confirmar la delegación |
| `etiquetas_assign_bulk` | Sigue `action_preview` Confirmar/Cancelar | No crea un objeto; es aplicar N clientes | Meter assign en la card de etiqueta |
| Reuso nulo | Ocultar «Aceptar selección» | No hay candidato útil | Botón disabled que confunde |
| Bitácora | Solo `CopilotHandoffTranscript` en el hilo | Dos UIs (caja + sheet) competían | Sheet «Ver chat» como segunda bitácora |
| Modal Meta | Aviso al Supervisor + chip continuar | Hoy el grafo no se entera y se traba antes de Martín | Solo mensaje local de éxito |

---

## Alcance explícito

### Incluido (v1)

- Scoring caso a caso: etiqueta, grupo, plantilla, agenda (matriz abajo).
- Tool `grupos_list` en Lucía.
- Artefacto `object_choice` en 1:1 y Supervisor.
- Interrupt del Supervisor **después** del empleado, payload `object_choice` o espera de `action_preview` (assign).
- Resume `{ choice: create \| reuse \| retry, message? }`.
- Card: Aceptar creación / Aceptar selección / Reintentar (+ texto opcional).
- Dedupe del razonamiento del playbook (frases no repetidas).
- Bitácora inline única; chip `continuation_chip` post-modal.

### Fuera de alcance

- Embeddings / fuzzy semántico.
- Recetas nuevas.
- Undo de writes ya ejecutados.
- Prefill de imagen en plantillas.
- UI propia del hilo puente (el bridge en BD sigue para memoria).

---

## Matriz de scoring

**Etiqueta.** Útil si: nombre exacto case-insensitive; o normalizado (sin acentos) igual al propuesto; o el nombre contiene el token de campaña (`carrito`, `no responden`, `no compran`) y **no** es genérica (`Canal`, `VIP`, etc.). Crear: nombre canónico de campaña o el que pidió el usuario.

**Grupo.** Útil si: activo, `mode=etiqueta`, y comparte `etiqueta_id` (o el nombre de etiqueta) con la audiencia actual. No útil: `lista` / geo / otra etiqueta.

**Plantilla.** Útil (reuso automático) si: status `APPROVED` y el nombre matchea el regex del caso (`carrito\|cart_open\|abandon` / `no_responden\|otro_momento\|callback`). PENDING no cuenta para reuso automático. Si el operador nombra una plantilla (o acaba de crearla), el playbook sigue a la agenda con ese nombre aunque no esté APPROVED y avisa que el HSM puede fallar. Crear: `opens_modal` + draft (spec 063).

**Agenda.** Útil si: misma `grupo_id` + misma plantilla + `activo` y fecha futura o sin fecha vencida (no duplicar el HSM). Si no: dry-run de create.

---

## Flujo

```text
Especialista (dry-run) → object_choice
        │
        ├─ Aceptar creación → confirm_token o modal Meta
        ├─ Aceptar selección → bind id, no insert
        └─ Reintentar [mensaje] → misma tool, tope 2
```

Supervisor: `playbook_route`/`supervisor` → `tools` → `observe` → `confirm` (interrupt) → resume → siguiente paso. Nunca «Sí, delegar».

1:1: misma card; create pega `POST /copilot/actions/confirm`; reuse manda un mensaje de bind; retry reenvía la guía.

---

## Orden de implementación

Cross-repo. Merge **backend → backoffice**. Spec en platform en paralelo.

| # | Repo | Qué |
|---|------|-----|
| 1 | `suplai-platform` | Este spec + punteros en 001, 062, 065 |
| 2 | `backend-supabase` | Scoring, `grupos_list`, grafo post-empleado, SSE, tests |
| 3 | `product-management-app` | Card 3 botones, bitácora inline, chip continuar |

Rama en los tres: `feat/copilot-supervisor-langgraph`. Merge humano en GitHub.

---

## Migración de base de datos

Sin migración de BD. `object_choice` viaja en `artifacts` JSONB; el interrupt usa `core.copilot_orchestrator_runs.interrupt_payload` ya existente.

---

## Plan de prueba en CI/CD

- `tests/test_copilot_reuse.py`: etiqueta/grupo/plantilla/agenda útil vs no útil.
- `tests/test_copilot_supervisor_graph.py`: write ya no pausa **antes** del empleado; `dry_run` no se saltea; reasoning del playbook sin duplicar.
- `tests/test_copilot_supervisor_playbook.py`: resume `choice=create\|reuse\|retry`; no_responden no pide «delegar».
- Catalog: `grupos_list` en pack `audiencia`.
- Front: typecheck. Gap: sin Playwright e2e obligatorio.

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000` (`BACKEND_URL=http://localhost:8000`). Tenant `demo`.

1. Copilot → Supervisor → chip de quienes no responden.
2. Lucía lista; aparece card crear/reusar etiqueta (si existe «No responden», ambas opciones). No hay «Sí, delegar».
3. Sofía reusa APPROVED o abre el modal; al crear en Meta (aunque quede PENDING), chip Continuar → Martín propone agenda y avisa que el envío puede fallar si Meta no aprobó.
4. Razonamiento sin frases pegadas dos veces.
5. Chat 1:1 con Lucía: misma card de 3 botones. No hay sheet «Ver chat».

---

## Criterios de aceptación

- Las tools de creación listan y puntúan; no insertan a ciegas.
- HITL = elegir propuesta, no delegar un permiso.
- 1:1 y Supervisor usan la misma card.
- Cancelar/reintentar no deja tool_calls abiertos ni 400.
- Tras el modal de Meta el flujo puede continuar.
- Una sola bitácora visible, en el hilo.

## Referencias de código

- Scoring: `backend-supabase/services/copilot/reuse.py`
- Tools: `backend-supabase/services/copilot/tools.py`
- Grafo: `backend-supabase/services/copilot/supervisor/graph.py`
- UI: `product-management-app/components/copilot/CopilotObjectChoice.tsx`
