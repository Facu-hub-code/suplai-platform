# 104 — Conector: agendas sin duplicar, plantillas usables y estrategias deprecadas

**Estado:** Implementado en código, sin merge  
**Fecha:** 2026-10-11  
**Repos:** `backend-supabase` (tools, sender, migración), `suplai-sales-claude-plugin` (una línea de la skill), `suplai-platform` (este spec)  
**Rama:** `feat/mcp-agendas-plantillas-qa` en backend y en platform. La skill del plugin quedó editada sobre `feat/mcp-consolidar-tools`.  
**Relaciona:** [097](./097-claude-mcp-grupos-agendas.md), [096](./096-claude-mcp-plantillas.md), [099](./099-claude-mcp-estrategias-aliases.md)

---

## Objetivo

El conector deja de crear una agenda nueva cada vez que se “edita” o se prende una existente, marca las plantillas que no se pueden llenar desde un cliente, y saca las estrategias del catálogo de tools. El panel sigue administrando las estrategias que ya existen.

### Métricas de éxito

- Repetir `previsualizar_agenda` con el mismo grupo, plantilla, tipo, días o fecha y hora devuelve `accion: "actualizar"` y `agenda_existente_id`. Confirmar no inserta otra fila.
- Prender una agenda inactiva no aumenta la cantidad de agendas del grupo.
- Hay preview para editar, borrar una agenda y borrar un grupo. El grupo no se borra si tiene agendas activas.
- Un nombre de grupo repetido devuelve el `grupo_id` si hay uno solo con los mismos filtros, y se niega si hay más de uno.
- `listar_plantillas` marca `usable_en_agenda` y `origen`. Una agenda no acepta plantillas de sistema ni variables que no sean de cliente.
- `guia_suplai` sin tema no lista `estrategias`. Con ese tema dice que se deprecó y manda a `grupos-y-agendas`.
- El login y el consentimiento muestran la versión del conector.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Agenda repetida | El preview busca una igual y confirmar hace update | El QA mostró que volver a previsualizar creaba la 104 al lado de la 103, y la receta vieja de “activar” seguía ese camino | Índice único en la base. `dia_semana` es un array con variantes con y sin tilde: el índice mentiría |
| Duplicadas que ya están activas | El sender, en una misma corrida, no manda dos veces la misma plantilla al mismo teléfono | Esas copias ya están en producción (grupos 5 y 10). Impedir el alta nueva no las apaga | Borrarlas en la migración. No sabemos cuál quería quedar el operador |
| Activar | `previsualizar_editar_agenda` | Cambiar `activo` no es un alta. Si alguien igual vuelve a previsualizar la misma agenda, el update cubre el caso | Seguir la receta vieja de crear otra con `activar=true` |
| Borrar grupo | Se niega si hay agendas activas y, si no, borra las inactivas junto con el grupo | Un grupo vacío de agendas se puede sacar. Uno que está enviando, no | Borrar en cascada las activas |
| Nombre de grupo | Si hay más de uno igual, hay que pasar `grupo_id` | El QA encontró 8 “No responden” y el preview decía `grupo_reusado` sin decir cuál | Elegir el id más nuevo en silencio |
| Variables de plantilla en el conector | Solo `nombre`, `razon_social`, `vendedor`, `dia_de_visita`, `dia_de_entrega`, `producto` | Teléfono, CUIT, email y código no aportan en el mensaje y exponen datos. El backoffice sigue con su whitelist | Achicar también el API del panel en el mismo cambio |
| Rechazo de preview | `AccionError` en una tool `previsualizar_*` vuelve como `{valido: false, errores: [...]}` | El modelo lo estaba tratando como caída del sistema y ofrecía reportar un error que no lo era | Dejar el `ToolError` y cambiar solo el texto |
| Plantilla de sistema | Nombre que empieza con `suplai_`, o variables que no son columnas de cliente | Esas plantillas alimentan avisos al vendedor y campañas. Borrarlas o agendarlas las deja sin parámetros | Una tabla nueva de “origen” |
| Editar plantilla en Meta | Fuera de esta entrega | Meta limita las ediciones y borrar bloquea el nombre. El preview sigue sin crear en Meta; sí puede leer las existentes para avisar si el texto se repite | Exponer `previsualizar_editar_plantilla` sin conocer el cupo de la cuenta |
| Estrategias | Se van del catálogo MCP. El confirmar de un preview viejo responde que está deprecado. El sender y el panel no cambian | El panel todavía las usa. Apagarlas cortaría envíos que no pasan por Claude | Migrar o desactivar las de producción en esta entrega |
| Versión | Constante `2026.10.11` en el HTML de login y consentimiento, y en las instrucciones del server | Hay que ver qué conector está conectado sin abrir el repo | Leer `git describe` en cada request |
| Días sin tilde | El scheduler compara el día plegado, y la migración 157 reescribe `miercoles` y `sabado` al valor con tilde | `miercoles` está en el enum legacy y no matcheaba `miércoles`, así que esa agenda no disparaba | Solo normalizar al escribir. Las filas viejas seguían mudas |

---

## Alcance

### Incluido

- Update en lugar de insert cuando la agenda es la misma.
- Tools `previsualizar_editar_agenda`, `previsualizar_eliminar_agenda`, `previsualizar_eliminar_grupo`.
- Dedup de envío por teléfono y plantilla dentro de una corrida del sender.
- Cupo de hoy solo si el envío es hoy.
- `grupo_id` en el preview y rechazo si el nombre es ambiguo.
- Columnas de variable acotadas, `usable_en_agenda`, `origen`, aviso de texto poco transaccional y de cuerpo parecido.
- Ejemplo renderizado con un cliente, sin teléfono, y conteo de variables vacías antes del fallback.
- Receta `estrategias` deprecada y fuera del índice.
- Versión en la pantalla de auth.
- Migración `sql/157` con los tipos de preview nuevos y el backfill de días.

### Fuera de alcance

- Apagar o migrar las estrategias que ya corren en el panel. Siguen saliendo por el sender.
- Borrar desde acá las agendas duplicadas que ya están en producción. El sender deja de mandarlas dos veces en la misma corrida; limpiarlas es una decisión del operador.
- Editar el cuerpo de una plantilla ya aprobada en Meta.
- Cambiar la whitelist de variables del backoffice.
- Un índice único de agendas en Postgres.

---

## Orden de implementación

1. `backend-supabase`, rama `feat/mcp-agendas-plantillas-qa`.
2. Aplicar `sql/157_mcp_agendas_editar_eliminar.sql` antes de probar un preview de editar o borrar. Sin esa migración el `INSERT` del preview falla el check.
3. Merge del backend.
4. El plugin solo cambia la skill para que apunte a `previsualizar_editar_agenda`. Puede ir en el PR de `feat/mcp-consolidar-tools` o en uno aparte.

Sin migración de columnas. El check de `mcp_accion_previews.tipo` suma `editar_agenda`, `eliminar_agenda` y `eliminar_grupo`, y sigue aceptando `estrategia` para no invalidar previews viejos.

Rollback del check: restaurar el de `sql/156`. El backfill de días no se revierte solo: `miercoles` y `sabado` pasan a `miércoles` y `sábado`. El scheduler igual los acepta plegados si el backfill no corrió.

---

## Migración de base de datos

`sql/157_mcp_agendas_editar_eliminar.sql`.

- Reescribe el check de `public.mcp_accion_previews.tipo`.
- En cada schema de `public.distribuidoras`, si existen `agenda.dia_semana` y `grupos.dias_visita`, reemplaza `miercoles` y `sabado` por el valor con tilde. Solo si esas etiquetas existen en `core.dia_de_visita_enum`.

Sin tablas nuevas.

---

## Plan de prueba en CI/CD

- `tests/test_mcp_plantillas_agendas.py`: cupo, firma, columnas, plantilla sin mapeo, confirmar sin `vence_en_minutos`.
- `tests/test_mcp_superficie.py`: 47 tools, sin `previsualizar_estrategia`.
- `tests/test_mcp_guia.py`: el índice no lista `estrategias`; el tema responde la deprecación.
- `tests/test_agenda_sender_envio_plantilla.py`: dedup y comparación de día plegada.
- `tests/test_mcp_qa_conector.py`: el check SQL cubre los tipos del confirmar, incluido `estrategia`.

---

## Plan de prueba humana (antes del PR)

Backend en `8000`. Conector reconectado. Tenant de prueba (el del QA, con el grupo 38 si sigue).

1. `previsualizar_agenda` dos veces con el mismo grupo, plantilla, fecha y hora. La segunda responde `accion: "actualizar"` y el mismo `agenda_existente_id`. `confirmar` no suma una agenda.
2. `previsualizar_editar_agenda` con `activo=true` sobre una inactiva. Después de confirmar, `listar_envios` muestra la misma cantidad.
3. `previsualizar_agenda` con nombre `No responden` sin `grupo_id`. Tiene que pedir el id.
4. `listar_plantillas`: `prueba_variables` y `suplai_*` salen con `usable_en_agenda: false`. `previsualizar_agenda` con una de esas se niega con `valido: false`, no como error de tool.
5. `previsualizar_eliminar_plantilla` con un nombre `suplai_*` se niega.
6. `guia_suplai` sin tema no muestra `estrategias`. Con tema `estrategias` redirige a `grupos-y-agendas`.
7. Abrir el login del conector y ver `Conector 2026.10.11` en la card.
8. Los datos de prueba del QA (grupo 38, agendas 103 y 104) se pueden borrar con las tools nuevas, o desde el panel si la migración todavía no está aplicada.
