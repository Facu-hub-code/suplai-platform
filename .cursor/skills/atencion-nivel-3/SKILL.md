---
name: atencion-nivel-3
description: Atender el backlog del nivel 3 (proyecto de Linear «P3 - Nivel 3 · Escalamiento a Faka») como sesión orquestadora. Usar cuando Faka pide "atendé P3", "qué hay en el nivel 3" o "arrancá con el backlog": triage por prioridad y Origen, preguntas en una sola tanda, sesiones hijas en paralelo, revisión y merge con permiso, escrituras en producción y cierre con aviso al cliente.
---

# Atención del nivel 3

P3 junta lo que llega a Faka: solicitudes de clientes, trabajo proactivo y fallas que detectan jobs o agentes. Faka lo atiende cuando tiene tiempo; lo urgente ya le llegó por mail. Esta sesión es la **padre**: elige, pregunta, lanza hijas, revisa, mergea con permiso y cierra.

Diagrama del proceso: [Miro · Proceso de atención del nivel 3](https://miro.com/app/board/uXjVESGkfUQ=/).
Para escribir en Linear (labels, estados, cómo redactar), seguí la skill `suplai-linear`.

## 1. Triage

1. `list_issues` con `project: "P3 - Nivel 3 · Escalamiento a Faka"` y estados `Backlog`, `Todo`, `In Progress`, `In Review`. Traé prioridad, labels y relaciones (`includeRelations`).
2. Agrupá por la etiqueta `Origen` (grupo de labels): `Solicitud`, `Proactiva`, `Detectada`.
3. A lo que no tenga `Origen`, ponéselo con `addLabels` (es reversible; no preguntes). Si no queda claro, elegí el más probable y anotalo en un comentario.
4. Ordená:
   1. Prioridad 1 (urgente): primero siempre.
   2. `Solicitud`: hay un cliente esperando.
   3. `Detectada`.
   4. `Proactiva`.
   Dentro de cada grupo, por prioridad y después por antigüedad.
5. Solo es elegible lo que no tiene `blockedBy` abierto (bloqueante que no está en `Done`/`Canceled`). Lo bloqueado se muestra, no se lanza.
6. Mostrale a Faka la tabla corta: ID, título, Origen, prioridad, bloqueos y si tiene migración.

## 2. Preguntar todo al inicio

- Leé entera cada issue elegida (descripción y comentarios) y juntá lo que depende de Faka: decisiones de diseño, permisos para producción, datos que faltan (tenant, cliente, archivo).
- Hacé **todas las preguntas en una sola tanda**, antes de lanzar nada. Recomendación primero en cada una.
- Lo que se decide con el contexto o con un default razonable, lo decidís vos y lo dejás anotado en la issue ("Decidido: … porque …"). No le preguntes a Faka lo que se puede verificar en el código, en Linear o en la base (solo lectura).
- Las respuestas van como comentario en la issue, así la hija las lee.

## 3. Lanzar sesiones hijas

- **Una sesión hija por issue**, cada una en su worktree. Sesión visible (`start_session`), **no subagente**: Faka tiene que poder abrirla y escribirle.
- **Máximo 7 sesiones en la máquina, contando la padre.** Antes de lanzar, contá las activas (`list_sessions`) y lanzá solo los lugares libres.
- **Solo una hija con migraciones a la vez.** Las demás no tocan esquema.
- Elegí issues que no toquen los mismos archivos. Si dos se pisan, va una y la otra espera.
- Brief de cada hija:
  - Issue (ID y link) y que la lea entera con el conector de Linear.
  - Repo y rama base (`origin/main`; `origin/master` en `agent/`).
  - Qué no tocar (archivos que edita otra hija, specs ajenos).
  - Dependencias y decisiones ya tomadas en la tanda de preguntas.
  - "Pasá la issue a `In Progress`. **Abrí el PR y avisá; no mergees ni escribas en producción.** Comentá el link en la issue y pasala a `In Review`. Si te falta algo, frená e informá."
  - Su "Hecho cuando".

## 4. Revisar el PR

Cuando una hija avisa:

1. `gh pr view <n> --json state,mergeable,statusCheckRollup,files`: CI verde y sin conflictos.
2. Leé el diff: que haga lo que dice la issue y nada más.
3. Pedile permiso a Faka para mergear, con:
   - Riesgos y decisiones que tomó la hija.
   - Pasos en producción (migraciones, backfills, jobs).
   - Variables de entorno nuevas o cambiadas.
4. Sin un sí explícito para ese PR, no mergeás.
5. Orden: **backend antes que los consumidores** (backoffice, tienda, field-app, agent).

## 5. Producción

Las escrituras en producción (backfills, barridos, encolado de jobs, updates de datos) **las hace solo la padre**, en tres pasos:

1. **Vista previa:** `SELECT` con conteo y casos raros. Mostrásela a Faka.
2. **Impacto:** horario (lejos de las agendas), si el worker está corriendo, qué agendas o envíos se disparan.
3. **Escritura en tandas**, verificando el conteo después de cada una.

Cambios de esquema: pedir permiso antes, siempre.

## 6. Cerrar

- Comentario en la issue que empiece con **`Para el cliente:`** y una línea en lenguaje del cliente (sin jerga técnica). Es lo que sale en el aviso de vuelta (DEV-221).
  - Ejemplo: `Para el cliente: Ya pueden cargar pedidos por unidad para los productos que nos pasaron.`
- Pasá la issue a `Done` cuando se cumple su "Hecho cuando" (PR mergeado y, si aplica, paso en producción hecho).
- **Aprendizaje:** si una respuesta de Faka sirve para la próxima, anotala como comentario `Aprendizaje: …` en la issue. Cuando exista DEV-219, va a `core.aprendizajes`.
- **Aviso al cliente:** mientras el aviso automático no exista, dejá el texto listo y preguntale a Faka por qué canal mandarlo (WhatsApp, mail, comercial). No lo mandes sin su sí.

## 7. Limpieza

Se puede borrar una sesión hija solo cuando:

- su PR está mergeado, verificado con `gh pr view <n> --json state` (`MERGED`), y
- su worktree no tiene cambios sin commitear (`git status --porcelain` vacío).

Si falta cualquiera de las dos, queda.
