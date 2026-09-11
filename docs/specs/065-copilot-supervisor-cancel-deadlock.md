# 065 — Cancelar escritura: freno consciente y punto muerto

**Estado:** Borrador  
**Fecha:** 2026-09-10  
**Repos:** `backend-supabase`, `product-management-app`, `suplai-platform`  
**Ramas:** `feat/copilot-supervisor-langgraph`  
**Extiende:** [062-copilot-supervisor-langgraph.md](./062-copilot-supervisor-langgraph.md)  
**Índice:** [001-suplai-copilot.md](./001-suplai-copilot.md)

---

## Objetivo

Cuando el operador **cancela** una escritura del Supervisor (Reintentar/Cancelar de `object_choice`, spec 067, o el Cancelar de un `action_preview` de assign_bulk), eso es un **freno consciente** al proceso, no un error. El grafo no puede romperse. El Supervisor usa esa señal: o bien llama a un especialista para **corregir** el problema, o **advierte y termina**.

Caso canónico visto en demo (carrito abandonado): el preview del grupo queda en **~0 clientes**. Cancelar esa escritura hoy tira un 400 de OpenAI y el chat muere. Lo correcto: si no hay audiencia, **no tiene sentido** etiquetar / crear grupo / plantilla / agenda. El Supervisor lo dice y cierra.

---

## Bug actual (evidencia)

Al Cancelar el interrupt, `confirm_node` mete un `AIMessage` («Cancelé la acción…») **sin** `ToolMessage` para los `tool_calls` pendientes. El nodo `supervisor` vuelve a llamar al LLM y OpenAI responde:

```text
An assistant message with 'tool_calls' must be followed by tool messages
responding to each 'tool_call_id'
```

Log local: `POST /api/copilot/chat` 500. El hint de continuación (`_continuation_hint` / `_NUDGE_USER`) encima empuja a llamar al siguiente `preguntar_a_*`, así que aunque no crashearía seguiría Sofía/Martín después de un grupo vacío.

Además, el **Cancelar del `action_preview`** (grupo/agenda) solo hace `setDone(true)` en el cliente: el Supervisor **no se entera**.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Cerrar tool_calls al cancelar | Un `ToolMessage` por `tool_call_id` pendiente: «Usuario canceló la escritura» | El historial OpenAI/LangGraph exige respuesta a cada tool_call. Es el crash de hoy | Meter solo un `AIMessage` (es lo que rompe). Borrar el AIMessage con tools del state (pierde el plan y el checkpoint) |
| Semántica de Cancelar | Freno: `write_cancelled=true` + no nudge de «llamá al siguiente especialista» | El operador marca un alto. Encadenar Sofía/Martín después de 0 clientes es el punto muerto | Tratar Cancelar como «saltar este paso y seguir» (peor: agenda vacía) |
| Inferir vs preguntar | **Primero inferir** de la bitácora/artefactos; preguntar «¿por qué cancelaste?» **solo si no es obvio** | El ejemplo del usuario: 0 clientes en preview ya explica el freno. Preguntar siempre suma un turno inútil | Preguntar siempre (fricción). Nunca preguntar (cancelar a mitad de un grupo *con* clientes quedaría ambiguo) |
| Punto muerto obvio | Preview/listado con **0 destinatarios** (clientes, grupo vacío, carrito vacío) → texto de cierre y `END` | No tiene sentido agenda/plantilla para contactar a nadie | Seguir el chip de carrito a rajatabla |
| Cancelar ambiguo | Una pregunta en texto (no otro interrupt) y esperar el próximo mensaje del usuario | El HITL de escritura ya usó el interrupt; el «por qué» es conversación normal | Segundo `interrupt()` (mezcla delegar escritura con diagnóstico) |
| Preview Cancelar | Notificar al Supervisor (mismo resume `confirmed=false` si hay interrupt abierto, o un turno user corto si el grafo ya siguió) | Hoy el preview se cierra en silencio y la cadena sigue | Dejar el Cancelar local (el Supervisor no puede frenar) |
| Detección preventiva | Antes de un `es_escritura` siguiente, el Supervisor mira el último artefacto: si 0 audiencia, no pide Sofía/Martín | Evita llegar al Cancelar | Solo reaccionar al Cancelar (el operador ya vio el absurdo) |

---

## Comportamiento esperado

```text
Usuario cancela escritura
        │
        ├─ Cerrar tool_calls (ToolMessage) → no 400
        │
        ├─ ¿Bitácora muestra 0 destinatarios / grupo vacío / sin carrito?
        │     sí → advertir en español, no llamar más especialistas, END
        │
        └─ no (cancelación ambigua)
              → preguntar por qué canceló
              → siguiente mensaje:
                    • «estaba mal la etiqueta / faltan clientes» → preguntar_a_lucia para corregir
                    • «dejá, no sigas» → END
                    • otra corrección (plantilla, agenda) → el especialista que corresponda
```

Copy de cierre (orientativa, no literal de UI):

> El preview quedó en 0 clientes, así que no tiene sentido armar plantilla ni agenda de seguimiento. Frené acá. Si más adelante hay carritos abiertos, lo retomamos.

---

## Alcance explícito

### Incluido (v1)

- Fix del 400: `ToolMessage` al cancelar el interrupt.
- Flag de freno: sin nudge de continuación en ese turno.
- Inferencia de punto muerto (0 clientes / grupo vacío) → advertir y terminar.
- Pregunta «¿por qué cancelaste?» solo si el motivo no está en la bitácora.
- El Cancelar del `action_preview` avisa al Supervisor (no es solo UI local).
- Si el último resultado de Lucía es 0 audiencia, **no** encadenar Sofía ni Martín.
- Tests de grafo: cancelar cierra tool_calls; 0 clientes → END; cancelar ambiguo no crashea.
- Copy en español (y las keys i18n pt/en del Copilot).

### Fuera de alcance

- Undo de una escritura **ya ejecutada** (`dry_run=false` post-confirm).
- Modal extra «¿por qué?» con opciones fijas; v1 es texto en el hilo.
- Reintentar automático sin el operador (el Supervisor no inventa audiencia).
- Undo de una escritura **ya ejecutada** (`dry_run=false` post-confirm). El HITL de crear/reusar es spec 067.
- Evals CI nuevos (quedan tests unitarios del grafo).

---

## Orden de implementación

Cross-repo. Merge **backend → backoffice**. Spec en platform en paralelo.

| # | Repo | Qué |
|---|------|-----|
| 1 | `backend-supabase` | `confirm_node` emite ToolMessage; `write_cancelled`; skip nudge; inferencia 0 audiencia; tests |
| 2 | `product-management-app` | Cancelar de `action_preview` notifica al chat del Supervisor; copy de cancelado vs usado |
| 3 | `suplai-platform` | Este spec + enlace en 001 y 062 |

Rama en los tres: `feat/copilot-supervisor-langgraph`. Merge humano en GitHub.

---

## Migración de base de datos

Sin migración de BD. El checkpoint del grafo ya persiste mensajes; solo cambia cómo se completan al cancelar.

---

## Plan de prueba en CI/CD

- `tests/test_copilot_supervisor_graph.py`:
  - Cancelar interrupt → hay `ToolMessage` por cada `tool_call_id`; el siguiente `supervisor_node` **no** pega un 400 (historial válido).
  - Tras cancelar con transcript/preview de 0 clientes → el modelo (mock) **no** llama al siguiente `preguntar_a_*`; el turno termina con texto de cierre.
  - Nudge `_continuation_hint` / `_NUDGE_USER` no se aplican si `write_cancelled`.
- Checks existentes del grafo 062 (interrupt, carrito mockeado, resumeToken) siguen verdes.
- Gap: sin Playwright e2e obligatorio; la prueba humana cubre el 500 real.

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000`. Tenant `demo`.

1. Copilot → Supervisor → prompt de carrito abandonado.
2. Confirmar etiquetar / grupo hasta un preview con **0 clientes** (o simularlo).
3. Click **Cancelar** en el interrupt de la escritura siguiente (o en el preview).
4. **No** hay error genérico ni `POST /api/copilot/chat` 500. El chat sigue vivo.
5. El Supervisor **advierte** que no hay a quién contactar y **no** pide crear plantilla ni agenda.
6. Caso ambiguo (grupo con clientes, el operador cancela igual): pregunta por qué; si el usuario dice «no sigas», termina; si pide corregir etiqueta, vuelve a Lucía.
7. Un chat 1:1 con Lucía/Martín no se ve afectado.

---

## Criterios de aceptación

- Cancelar una escritura del Supervisor nunca deja `tool_calls` abiertos ni 400 de OpenAI.
- Cancelar es un freno: no se encadena el siguiente oficio por inercia.
- 0 destinatarios en la bitácora → cierre explícito, sin agenda ni plantilla.
- Si el motivo no es obvio, el Supervisor pregunta por qué canceló y usa la respuesta para corregir o terminar.
- El Cancelar del preview de grupo/agenda llega al Supervisor.

## Referencias de código

- Grafo: `backend-supabase/services/copilot/supervisor/graph.py` (`confirm_node`, `_NUDGE_USER`, `_continuation_hint`)
- Stream: `backend-supabase/services/copilot/supervisor/stream.py` (`Command(resume={"confirmed": ...})`)
- UI interrupt: `product-management-app/components/copilot/CopilotObjectChoice.tsx` (reemplaza «Sí, delegar»)
- UI preview: `product-management-app/components/copilot/CopilotArtifactActionPreview.tsx`
