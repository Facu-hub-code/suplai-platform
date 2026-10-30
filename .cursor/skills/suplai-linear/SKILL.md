---
name: suplai-linear
description: Operar el Linear de Suplai (workspace suplai-sales) desde Claude con el conector MCP. Usar para anotar ideas, pendientes o decisiones, ver qué hay para hacer, mover issues, cerrar trabajo al mergear un PR, escribir el avance de un proyecto o armar el panorama. También cuando una conversación deja un pendiente que no debe perderse.
---

# Linear de Suplai

Faka usa Linear **solo desde Claude**. La UI es para mirar el panorama, no para cargar cosas. Si algo se puede hacer con el conector, lo hacés vos; a Faka le pedís solo lo que el conector no expone.

## Estructura (verificar con las tools de listado antes de asumir)

| Nivel | Qué hay |
|-------|---------|
| Workspace | `suplai-sales` |
| Equipo | `TECHNICAL TEAM`, clave `DEV`. Las issues son `DEV-123` |
| Initiative | "Customer Success escalonado" (la crea Faka en la UI). Agrupa los proyectos de abajo |
| Proyectos | `Nivel 1 · Comercial como primera línea` (P-DEV-2), `Nivel 2 · MVP equipo de agentes` (P-DEV-1), `Nivel 3 · Escalamiento a Faka` (P-DEV-3) |
| Milestones del Nivel 2 | `1. Ver`, `2. Cablear`, `3. Trabajar solos`, `4. Proactivo` (etapas del spec 134) |
| Documentos | "Visión: Customer Success escalonado" y "Panorama" (en el equipo) |

Más adelante se suman las implementaciones de clientes nuevos como proyectos de la misma initiative.

### En qué proyecto va cada cosa

- Lo que hacen los bots o el runtime de agentes (specs 134–142): Nivel 2.
- Lo que resuelve el comercial o partner sin Suplai: Nivel 1.
- Caídas, alertas, incidentes que frenan el servicio: Nivel 3.
- Si no encaja en ninguno, creala sin proyecto y decíselo a Faka: puede ser un proyecto nuevo.

### Labels (grupos)

| Grupo | Valores | Regla |
|-------|---------|-------|
| Tipo (uno solo) | `Feature`, `Bug`, `Improvement`, `Idea`, `Decisión`, `Docs` | Siempre uno |
| Repo (varios) | `backend`, `backoffice`, `agent`, `platform`, `infra` | Los que toca |
| Tenant (varios) | `almaro`, `cordoba_frost`, `gonzales` | Solo si es de una distribuidora. Si falta el tenant, crealo con `save_issue_label` y `parent: Tenant` |

### Estados

`Backlog` (ideas y lo que no va ahora) → `Todo` (lo próximo) → `In Progress` → `In Review` (PR abierto) → `Done`. También `Canceled` y `Duplicate`.

## Cómo escribir una issue

- Título en español, en imperativo o como resultado: "Abrir el equipo de agentes a los owners".
- Descripción corta: contexto en 1–3 líneas, referencias concretas (spec, archivo, rama, commit) y una línea **"Hecho cuando:"** con el criterio verificable.
- Links con `links` (spec en GitHub, PR, Miro), no pegados sueltos.
- `Decisión`: listar las opciones con la recomendada primero y enlazar donde está escrita (por ejemplo, la sección "Decisión abierta" del spec).
- Dependencias con `blockedBy`/`blocks`, no en el texto.
- Prioridad: 1 urgente solo si frena el servicio; 2 lo que destraba lo siguiente; 3 lo normal; 4 lo que puede esperar.
- Asignar a Faka (`me`) solo lo que está en `Todo` o es una decisión suya.
- Nada de datos sensibles: ni tokens, ni contraseñas, ni teléfonos de clientes.

## Flujos

### Una sesión por proyecto, sub-sesiones por issue
- Cada sesión de Claude atiende **un solo proyecto** de Linear y es su orquestadora. No toma issues de otros proyectos: si aparece algo de otro, lo anota (ver "Anotar al pasar") y lo deja para la sesión de ese proyecto.
- Para las issues puntuales, la sesión crea **sub-sesiones** (subagentes o sesiones hijas), una por issue, cada una en su rama y su worktree.
- **Máximo 3 sub-sesiones a la vez.** El límite lo pone lo que Faka puede revisar y entender, no la velocidad de los agentes. Se eligen para que no toquen los mismos archivos, y solo una puede tener migraciones a la vez.
- Las sub-sesiones no escriben en producción ni mergean. Abren su PR, comentan el link en la issue y la pasan a `In Review`.
- Cuando una sub-sesión termina, la sesión padre verifica el PR (CI, conflictos, que haga lo que dice). Después **le pide permiso a Faka para mergear** y le avisa qué tiene que revisar él: riesgos, decisiones del agente, pasos en producción, variables de entorno. Sin un sí explícito para esos PRs, no mergea.
- Las escrituras en producción (backfills, barridos, encolado de jobs) las corre la sesión padre: primero una vista previa con conteo y casos raros, después en tandas, y lejos del horario de las agendas.

### Anotar al pasar
Cuando la charla deja un pendiente, una idea o una duda: creá la issue sin preguntar (es reversible), con Tipo, Repo y proyecto. Contale a Faka el ID en una línea. Si es una idea suelta, `Idea` en `Backlog`.

### "¿Qué tengo?" / "¿Dónde estamos?"
`list_issues` con `assignee: me` y estados `Todo`/`In Progress`/`In Review`, agrupado por proyecto. Para un proyecto: `get_project` con milestones y contar issues por estado. Responder con lo que está en curso, lo bloqueado y la decisión que destraba más.

### Empezar una issue
Pasala a `In Progress`. La rama sigue `docs/git-workflow.md` y lleva el ID: `feat/dev-12-slug`. Con la integración de GitHub en Linear, la rama y el PR se vinculan solos.

### Cerrar trabajo
- PR abierto: `In Review` y link al PR.
- PR mergeado: `Done` (si la integración no lo hizo) y un comentario de una línea con lo que quedó.
- Algo que se descarta: `Canceled` con el motivo en un comentario.

### Revisión semanal del backlog
Listar `Backlog` y `Todo`. Proponer a Faka en una tabla: qué pasa a `Todo`, qué se cancela, qué se fusiona. Aplicar solo lo que apruebe.

### Avance de un proyecto
`save_status_update` (`type: project`) con `health` (`onTrack`, `atRisk`, `offTrack`) y tres partes: qué se hizo desde el último avance, qué sigue, qué bloquea. Enlazar issues por ID.

### Panorama
Actualizar el documento "Panorama" del equipo con `patch`: estado de cada proyecto (hecho, en curso, falta, % por conteo de issues), decisiones abiertas y links a los diagramas (Miro). Hacerlo al cerrar una etapa o cuando Faka pregunta dónde estamos.

### Decisión abierta en un spec
Si una decisión queda escrita en un spec, crear la issue `Decisión` con link a la sección. Cuando Faka decide, actualizar el spec y cerrar la issue.

## Lo que el conector no hace

- Crear o editar initiatives: pedirle a Faka que la cree en la UI; después vos colgás los proyectos con `save_project` (`addInitiatives`) y los documentos con `save_document` (`initiative`).
- Renombrar el equipo o cambiar su clave.
- Crear vistas guardadas (custom views): usar el documento "Panorama" o el avance del proyecto.

Pedir esos pasos juntos y explicados en una línea cada uno.

## Antes de escribir

- Leé primero (`list_*`, `get_*`) para no duplicar: buscá por título con `query`.
- Usá los nombres exactos de labels, estados y milestones que devuelve Linear.
- En lotes grandes, contale a Faka la agrupación antes de crear.
