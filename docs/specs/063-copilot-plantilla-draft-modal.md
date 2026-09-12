# 063 — Copilot: borrador de plantilla en el modal de Meta

**Estado:** En implementación  
**Fecha:** 2026-09-09  
**Repos:** `suplai-platform` (este doc), `backend-supabase`, `product-management-app`  
**Ramas:** `feat/copilot-supervisor-langgraph`  
**Extiende:** [038-copilot-agentes-especialistas.md](./038-copilot-agentes-especialistas.md), [062-copilot-supervisor-langgraph.md](./062-copilot-supervisor-langgraph.md)  
**Índice:** [001-suplai-copilot.md](./001-suplai-copilot.md)

---

## Objetivo

Cuando Sofía (o el Supervisor vía Sofía) decide crear una plantilla, no debe abrir el editor vacío. Tiene que **proponer una idea** (nombre, categoría, cuerpo, variables, botones) y el modal oficial de Meta se **pre-carga** con ese borrador. El humano revisa, ajusta y envía a crear.

---

## Decisiones de diseño técnico (con el *por qué*)

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Superficie | Reusar `CreateMetaTemplateModal` | El POST a Meta, handles de imagen, variables y validación ya existen | Modal Copilot paralelo (doble UI, drift de reglas Meta) |
| Dónde nace la idea | Args de `plantilla_create_draft` | Sofía ya elige cuándo crear; el tool deja de ser un interruptor vacío | Un segundo LLM en el backend al abrir el modal (latencia, sin contexto del chat) |
| Transporte | Campo opcional `draft` en el artefacto `opens_modal` | El chat ya persiste artefactos; el botón reabre el mismo borrador | Query string / localStorage (se pierde al recargar el hilo) |
| Alcance del borrador | Texto: nombre, categoría, encabezado, cuerpo, quick replies, ejemplos/mapeo de `{{n}}` | Cubre el caso carrito/seguimiento. Imagen y carrusel siguen siendo edición humana | Prefill de media (la tool no sube archivos) |

---

## Alcance explícito

### Incluido (v1)

- Tool `plantilla_create_draft` acepta `nombre`, `categoria`, `encabezado`, `cuerpo`, `botones`, `ejemplos`.
- Artefacto `opens_modal` incluye `draft` sanitizado cuando hay idea.
- Card del chat muestra nombre + preview del cuerpo.
- El modal oficial se pre-carga; el operador puede editar y enviar.
- Prompt de Sofía: no abrir el modal vacío si va a crear.

### Fuera de alcance

- Crear la plantilla en Meta sin pasar por el modal.
- Prefill de imagen / carrusel.
- Crear etiquetas nuevas (sigue el flujo 062).
- Un editor Copilot distinto del modal de plantillas.

---

## Orden de implementación

1. Spec (este archivo) + punteros backend/backoffice.
2. `backend-supabase` — args + sanitizado + tests.
3. `product-management-app` — zod, card, `initialDraft` en el modal.
4. Merge humano (misma rama que 062).

---

## Migración de base de datos

Sin migración de BD. El `draft` viaja en `artifacts` JSONB ya persistido.

---

## Plan de prueba en CI/CD

- `tests/test_copilot_plantillas_tools.py`: sin args el artefacto sigue igual (sin `draft`); con args incluye `draft` sanitizado (nombre snake_case, max 3 quick replies).
- Checks de catalog/dispatch de Sofía siguen verdes.

---

## Plan de prueba humana (antes del PR)

**Servicios:** backend `8000`, backoffice `3000`. Tenant `demo`.

1. Copilot → Sofía o Supervisor. Pedir crear una plantilla de seguimiento de carrito (si no hay una usable).
2. La card no dice solo “abrir editor”: muestra nombre propuesto y un extracto del cuerpo.
3. Abrir el modal: nombre, categoría, cuerpo y botones vienen precargados.
4. Cambiar una frase y enviar. La plantilla se crea con el flujo oficial.
5. Desde Plantillas Meta (fuera de Copilot) el modal sigue abriendo vacío.

---

## Criterios de aceptación

- Sofía no abre el editor vacío cuando propone crear una plantilla.
- El humano puede ajustar el borrador antes de mandarlo a Meta.
- Sin `draft`, el modal vacío actual sigue funcionando.
