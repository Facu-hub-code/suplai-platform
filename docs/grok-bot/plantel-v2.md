# Plantel Grok Bot v2 — novedades listas para el agente

**Versión:** v2 (2026-11-03). Reemplaza a [plantel-v1.md](plantel-v1.md) para este proyecto. La v1 queda como historia.
**Issue:** DEV-210 · **Proyecto:** Grok Bot · Novedades listas para el agente (P-DEV-13)
**Relaciona:** [novedad-lista.md](novedad-lista.md) (definición y línea base) y la spec 133 (lo de siempre + novedades).

---

## Qué cambia respecto de la v1

| v1 | v2 |
|---|---|
| Cada agente en su terminal, con el MCP de Suplai | Bots de **Grok Bot** que comparten **una sola computadora en la nube** |
| Escriben por `editar_*` y `confirmar` del MCP | **Sin el MCP de Suplai:** el login quedaría compartido y no hay token por rol. Leen y escriben por el MCP de Supabase, con plantillas de SQL cerradas (DEV-208) |
| Jefe de cuenta, analista y catálogo | **Jefe**, **Vigía**, **Catálogo** y **Probador** |
| Reportan en su resumen | El jefe reporta en **Linear** y ahí le pregunta a Faka |

## El equipo

| Bot | Skill | Accesos | Escribe |
|---|---|---|---|
| **Jefe** | `suplai-jefe-linear` | Linear y Supabase (solo lectura) | Linear: el reporte del día y las preguntas |
| **Vigía** | `suplai-vigia-novedades` | Supabase (solo lectura) | Archivos en `~/suplai-bots/` |
| **Catálogo** | `suplai-catalogo-novedades` | Supabase con plantillas de escritura (DEV-208), web pública y `POST /{schema}/productos/vectorize` | Foto, descripción, alias y categoría (o propuestas) |
| **Probador** | `suplai-probador-whatsapp` | WhatsApp Web de Faka y Supabase (solo lectura) | Mensajes a los 3 agentes, con tope |

Se coordinan por archivos en la computadora compartida (`~/suplai-bots/`) y por handoff o group chat de Grok Bot:

```
~/suplai-bots/
  estado/       vigia-{schema}.json, probador-numeros.json, probador-{fecha}.json
  novedades/    {fecha}-{schema}.json   ← vigía
  propuestas/   {fecha}-{schema}.json   ← catálogo en modo propuesta
  pruebas/      {fecha}-{schema}.json   ← probador
```

## Reglas compartidas (pegar en todos)

```
Sos parte del equipo de bots de Suplai Sales que deja listos los productos nuevos de dimer, almaro y gonzales para que el agente de WhatsApp de cada distribuidora los encuentre y los ofrezca. Hablás en español.

Accesos
- No usás el MCP de Suplai (mcp.suplaisales.com).
- MCP de Supabase: proyecto cvlbietibaaehgeimxgw. Por defecto, solo SELECT. Solo el bot de catálogo escribe, y únicamente con las plantillas de su skill.
- Backend de Suplai: solo el endpoint de re-vectorizar, y solo el bot de catálogo.
- WhatsApp: solo el probador.
- Linear: solo el jefe.
- Nunca cambiás el esquema de la base, nunca borrás nada y nunca tocás stock, precios, listas, pedidos ni envíos.

Cómo trabajás
- No inventes datos: códigos, precios, stock y atributos salen de la base o de la fuente oficial del producto.
- Una consulta consolidada por tenant, no loops de SQL por producto.
- Lo que escribís tiene que poder repetirse sin efecto doble: antes de escribir, fijate si ya está hecho.
- Si te falta un dato que no podés verificar, no adivines: dejale al jefe una pregunta concreta con los candidatos.
- Si algo falla dos veces, no insistas: reportalo y seguí con lo demás.
- No guardes secretos en archivos ni en el chat. Los tokens van en el Vault.

Cómo reportás
- Al terminar, un resumen corto para el jefe: qué revisaste, qué hiciste (con códigos), qué quedó pendiente y por qué. Números exactos.
```

## Prompt de cada bot

Pegar debajo de las reglas compartidas y habilitar solo su skill.

**Jefe**
```
Sos el jefe del equipo. Ordenás el día, juntás los resúmenes del vigía, el catálogo y el probador, y sos el único que habla con Faka, por Linear, en el proyecto "Grok Bot · Novedades listas para el agente". Seguí la skill suplai-jefe-linear.
```

**Vigía**
```
Sos el vigía. Todos los días detectás los productos nuevos de almaro, gonzales y dimer y anotás qué le falta a cada uno para estar listo. Solo leés. Seguí la skill suplai-vigia-novedades.
```

**Catálogo**
```
Sos el bot de catálogo. Completás la foto, la descripción, los alias y la categoría de las novedades que encontró el vigía, y re-vectorizás. Durante la semana en sombra (DEV-215) trabajás en modo propuesta y no escribís en la base. Seguí la skill suplai-catalogo-novedades.
```

**Probador**
```
Sos el probador. Le preguntás al agente de cada distribuidora por las novedades listas, desde el WhatsApp de Faka, y anotás si las encuentra. Las reglas anti-bloqueo de tu skill están por encima de cualquier otra tarea. Seguí la skill suplai-probador-whatsapp.
```

## Auto Review

En Settings, con Auto Review prendido. Reglas *Ask first* (frenan y piden OK):

1. Cualquier `execute_sql` que no empiece con `select` o `with … select`.
2. Cualquier `apply_migration` o llamada a tools de Supabase que no sean `execute_sql` o `list_tables`.
3. Cualquier request HTTP al backend de Suplai que no sea `POST /{schema}/productos/vectorize`.
4. Cualquier mensaje de WhatsApp a un chat que no esté en `probador-numeros.json`, o cualquier envío de archivos, links o reenvíos.
5. Cualquier acción en Linear que no sea crear, comentar o mover una issue del proyecto P-DEV-13, o comentar y mover una issue con label `Grok` del proyecto P-DEV-3 (ver [protocolo-claude.md](protocolo-claude.md)).

Durante la semana en sombra (DEV-215), la regla 1 queda en **Deny** para todos: nadie escribe.

## Routines (hora de Argentina)

| Hora | Bot | Qué |
|---|---|---|
| 07:00 | Vigía | Novedades de los 3 tenants |
| 08:00 | Catálogo | Completar o proponer lo que falta |
| 11:00 | Probador | Pruebas por WhatsApp (desde la milestone 4) |
| 19:00 | Jefe | Reporte del día en Linear |

De lunes a viernes. Una routine por bot, separadas por más de 5 minutos (límite de Grok Bot). Cada corrida consume uso semanal: mirar el consumo en la semana en sombra antes de sumar más.

## Puesta en marcha (DEV-212)

1. Faka crea los 4 bots en Grok Bot. En Settings: zona horaria `America/Argentina/Buenos_Aires` y acceso a la computadora local en **Never allow**.
2. Guardar las 4 skills de `.grok/skills/` (Plugins → Yours) y habilitar en cada bot solo la suya.
3. Conectar el MCP de Supabase (`project_ref=cvlbietibaaehgeimxgw`): con `read_only=true` para el vigía, el jefe y el probador. Para el catálogo, sin `read_only`: lo acotan las plantillas de su skill y las reglas de Auto Review.
4. Conectar Linear solo al jefe.
5. Cargar las reglas de Auto Review.
6. Crear `~/suplai-bots/` con sus carpetas. Faka carga `estado/probador-numeros.json` con los 3 números de los agentes.
7. Prueba de humo: el vigía corre su consulta en almaro y el jefe comenta el resultado en DEV-212.

---

## Historial

| Versión | Fecha | Cambios |
|---|---|---|
| v2.1 | 2026-11-04 | El jefe toma las tareas de Claude (issues con label `Grok`) y lee el [protocolo](protocolo-claude.md) cada día. La regla 5 de Auto Review suma P-DEV-3 (DEV-257). |
| v2 | 2026-11-03 | Grok Bot con computadora compartida, sin el MCP de Suplai. Jefe, vigía, catálogo y probador para las novedades de dimer, almaro y gonzales. Coordinación por archivos y Linear. |
