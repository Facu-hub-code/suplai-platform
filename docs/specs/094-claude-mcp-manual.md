# 094 — Claude MCP: manual del conector

**Estado:** Borrador  
**Fecha:** 2026-10-08  
**Repos:** `suplai-sales-claude-plugin` (skill), `suplai-platform` (este spec)  
**Rama sugerida:** `feat/claude-mcp-manual` en el plugin  
**Serie:** [objetivos de capacidades](../claude-mcp/objetivos-capacidades.md), caso 0. El caso 1 es el [095](./095-claude-mcp-carga-clientes-productos.md).  
**Relaciona:** skill existente `skills/consultar-pedidos/SKILL.md` y la tool `consultar_pedidos`.

---

## Objetivo

Cuando el usuario le pregunta a Claude qué puede hacer con Suplai y cómo, la respuesta sale de las herramientas que el conector tiene en ese momento. Un ejemplo por herramienta, y una línea sobre lo que todavía no está. Claude no inventa pantallas del backoffice ni promete cargas, plantillas o ERP.

### Métricas de éxito

- Ante “¿qué podés hacer?” o “¿cómo veo los pedidos?”, Claude nombra `consultar_pedidos`, da un ejemplo de frase y muestra el resultado como ya indica la skill de pedidos.
- Ante “cargá este Excel” o “armá una plantilla”, Claude dice que eso todavía no está en el conector y no llama una tool que no existe.
- La skill se actualiza en el mismo cambio que agrega una tool. El [095](./095-claude-mcp-carga-clientes-productos.md) saca la carga de la lista de “todavía no”.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Dónde vive el manual | Skill `skills/manual-conector/SKILL.md` del plugin | Claude la carga cuando la pregunta matchea la description. No hace falta auth ni una tool nueva. El patrón ya está en `consultar-pedidos`. | Tool `explicar_capacidades`: hay que desplegar backend para cambiar un texto. Queda para cuando la lista de tools sea larga. |
| Fuente de verdad | La skill nombra tools que existen en `mcp_server/main.py` hoy | Si la skill adelanta tools del 095, Claude las va a invocar y van a fallar. | Un manual “de la serie completa” publicado antes del backend. |
| Qué no puede | Una sección corta y cerrada | El usuario pregunta por cargas y plantillas. Sin esa sección, Claude completa con conocimiento general del backoffice. | Omitirlo y confiar en que el modelo no invente. |
| Escrituras futuras | Una regla fija: preview, esperar el sí, después confirmar | El 095 y los casos siguientes la reutilizan. En este spec no hay tool de escritura. | Explicar el flujo recién cuando exista la primera escritura. |
| Tono | Español rioplatense, de gerente comercial, sin nombrar tenants reales | Misma voz que `consultar-pedidos` y que el copy de cara al usuario. | Un manual técnico de endpoints. |

---

## Alcance

### Incluido

- Skill nueva con frontmatter `name` y `description` que dispare en preguntas del estilo “qué podés hacer”, “cómo funciona Suplai”, “ayuda”.
- Sección de herramientas reales. En este spec la única es `consultar_pedidos`: para qué sirve, un ejemplo (“¿cuáles fueron los últimos 10 pedidos?”) y un puntero a la skill `consultar-pedidos` para fechas y formato de la tabla.
- Sección “todavía no”: carga de Excel, plantillas, grupos, agendas, ERP, estrategias, cambiar el prompt del agente, borrar datos.
- Regla de escritura para cuando exista: Claude arma el preview, se lo muestra al usuario y no llama la tool de confirmación hasta un sí explícito en el chat.
- La skill no repite el detalle de fechas de pedidos. Delega en `consultar-pedidos`.

### Fuera de alcance

- Tools nuevas, scopes, cambios en `mcp_server/main.py` y en la pantalla de consentimiento.
- Cambiar `plugin.json` / el texto de la ficha del marketplace. Sigue diciendo que se consultan pedidos. El 095 lo actualiza cuando la carga exista.
- Tool que lea el catálogo de tools en vivo.
- Traducción a otro idioma.

---

## Orden de implementación

Un solo repo. No bloquea al backend.

| Orden | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `suplai-sales-claude-plugin` | `feat/claude-mcp-manual` | Agregar `skills/manual-conector/SKILL.md` |

Merge del plugin cuando el texto nombra solo `consultar_pedidos`. El 095, después, edita esta skill en su propio PR del plugin y se mergea **después** de que las tools de carga estén en el MCP.

---

## Migración de base de datos

Sin migración de BD.

---

## Plan de prueba en CI/CD

El plugin no tiene suite de tests. El gap es ese: un markdown no corre en el CI del backend.

Mínimo para el PR:

- El diff de la skill no nombra tools que no estén en `mcp_server/main.py` (`consultar_pedidos` es la única).
- La description del frontmatter incluye las frases de ayuda, para que Claude la seleccione.
- No se commitean secretos ni un token de OAuth.

---

## Plan de prueba humana

Hace falta el plugin instalado en Claude, con la sesión de Suplai ya conectada. No hace falta backoffice ni un puerto local.

1. Preguntar: “¿Qué podés hacer con Suplai?”.
2. Ver que nombra consultar pedidos, da un ejemplo y dice que la carga, las plantillas y el ERP todavía no están.
3. Preguntar: “¿Cuáles fueron los últimos 10 pedidos?” y ver una tabla real del tenant, no un ejemplo inventado.
4. Preguntar: “Cargá estos clientes” (sin archivo, o con uno) y ver que no intenta una tool inexistente y responde que la carga no está.
5. Preguntar: “¿Cómo cambio el prompt del agente?” y ver la misma negativa, en una línea.

OK: los pasos 2, 4 y 5 no prometen una capacidad que el conector no tiene, y el paso 3 sigue andando como antes.

---

## Contenido que tiene que quedar en la skill

Encabezado:

```yaml
name: manual-conector
description: Explica qué puede hacer el conector de Suplai Sales y cómo pedirlo. Usar cuando pregunten qué se puede hacer, cómo funciona, o pidan ayuda.
```

Cuerpo, en este orden:

1. Responder con las tools de esta lista y nada más.
2. `consultar_pedidos`. Ejemplo de frase. Decir que el detalle de fechas y de la tabla está en la skill `consultar-pedidos`.
3. Todavía no: carga de clientes o productos desde un Excel, plantillas de WhatsApp, grupos, agendas, sincronización con el ERP, estrategias, editar el prompt, borrar datos.
4. Cuando una tool escriba datos: mostrar el preview y esperar un sí del usuario antes de confirmar. Este spec no agrega esa tool.
