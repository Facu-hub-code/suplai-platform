# 108 — Agente: una sola búsqueda, con peso de categoría y evento

**Estado:** Implementado en `feat/busqueda-categoria` (agente y backend). Sin merge. El `UPDATE` de prompts, el vendedor y el backoffice quedan en el [109](./109-mitigacion-fusion-busqueda-categoria.md), en la misma ventana de deploy.  
**Fecha:** 2026-10-12  
**Repos:** `agente-conversacional-multi_tenant` (scoring de `search_products`, tools, prompt), `backend-supabase` (columna `evento`, `diagnosticar_busqueda`)  
**Ramas sugeridas:** `feat/busqueda-categoria` en el agente y en el backend  
**Relaciona:** [100](./100-mcp-seccion-prompt-busqueda.md) (`diagnosticar_busqueda`), spec 136 del agente (re-rank híbrido en `app/agent/tools/rag.py`), [109](./109-mitigacion-fusion-busqueda-categoria.md) (prompts, vendedor, backoffice)  
**Tenant que lo pidió:** `almaro`

---

## Objetivo

«Golosinas», «navidad», «pascua» y «snacks» tienen que devolver productos con stock de esas familias, en el top, sin preguntar entre categorías.

Hoy el prompt de Almaro manda la categoría amplia a `search_products_by_category`. Esa tool matchea la palabra contra el nombre de la categoría. «Golosinas» cae en `HALLOWEEN GOLOSINAS` y `NAVIDAD GOLOSINAS`. La categoría padre `GOLOSINAS` (id 1870) tiene hijas `CARAMELOS DE GOMA`, `CHUPETINES` y `GOMITAS`, cuyos nombres no contienen la palabra, y el agente no las usa.

`search_products` puntúa nombre y alias. Un alias no puede repetirse en otro código: `previsualizar_aliases` lo rechaza si ya pertenece a otro SKU. Para cubrir un evento hubo que cargar 149 alias distintos a mano. «Navidad» o «pascua» no aparecen en el nombre del producto y quedan fuera.

### Métricas de éxito

En Almaro, con stock, estas consultas devuelven productos de la familia en los primeros resultados y el agente no pregunta «¿cuál categoría?»:

| Consulta | Qué tiene que aparecer arriba |
|---|---|
| `golosinas` | SKUs con stock bajo `GOLOSINAS` (1870) o sus hijas (`GOMITAS`, `CARAMELOS DE GOMA`, `CHUPETINES`) |
| `navidad` | SKUs con stock de categorías `NAVIDAD *` |
| `pan dulce navidad` | Pan dulce cuya categoría o `evento` dice navidad, por encima de un pan dulce sin ese evento |
| `snacks` | SKUs con stock de `SNACKS DE COPETIN`, `SNACKS HORNEADOS` o `SNACKS SALUDABLES` |

`diagnosticar_busqueda` muestra el componente `categoria_token` para esas consultas.

---

## Cómo está el ranking hoy

El CTE `ranked` de `search_products` (`app/agent/tools/rag.py`) arma `final_score` así:

| Componente | Peso |
|---|---|
| `similarity` | 0,40 |
| `name_token` | 0,30 |
| penalización por token faltante | 0,25, restando `(1 - name_token)` |
| ancla (token más largo) | +0,10 si está, −0,30 si falta |
| stock | +0,15 si hay |
| `mental_priority` | 0,03 |
| rotación | 0,02 |
| alias | 0,02 |
| afinidad del cliente | 0,03 |

`name_token` y la ancla miran el nombre y `productos_aliases`. El recall léxico (`lexical_n` = 25) también: un producto entra si algún token de la consulta está en el nombre o en un alias. Si «golosinas» solo está en la categoría, el producto no llega a puntuarse.

`diagnosticar_busqueda` copia esos pesos en `services/mcp_busqueda.py` (`PESO_SIMILARITY`, `PESO_NAME_TOKEN`, `PENALIZACION_TOKEN_FALTANTE`). El comentario del módulo pide actualizar los dos juntos.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Tool de categoría | El agente de WhatsApp deja de ofrecer `search_products_by_category`. La función Python queda, marcada en desuso, para los tests que la llaman directo | La tool responde con categorías y pide elegir. El caso de Almaro pide productos. Sacarla de la lista que ve el modelo evita que el prompt viejo la siga ganando | Borrar el módulo en esta entrega. Lo usan tests y el riel de vendedor. Dejarla ofrecida y confiar solo en el prompt: la descripción actual dice que la categoría entera va por esa tool |
| Regla del prompt | La línea «Categoría amplia → `search_products_by_category`» pasa a `search_products`. La descripción default de `search_products` deja de decir que una categoría entera use la otra tool | Esa línea está en el `system_prompt` de Almaro y en la descripción de la tool (`agent_tools_default_descriptions.json`). Las dos le llegan al modelo | Cambiar solo el markdown de `implementacion/almaro/`. El runtime lee `distribuidoras.system_prompt` |
| Presencia del token | Un token de la consulta cuenta como presente si está en el nombre, en un alias, en el nombre de una categoría del producto, en el nombre de su categoría padre, o en `productos.evento` | Así se cancela la penalización por token faltante, igual que hoy con nombre y alias. «Golosinas» entra por el padre 1870 aunque la hija se llame `GOMITAS`. «Navidad» entra por `NAVIDAD GOLOSINAS` sin un alias por SKU | Sumar el bonus y dejar la penalización mirando solo el nombre. Con `name_token` en 0 la penalización se come el bonus |
| Ancla | La ancla usa el mismo conjunto de presencia | La penalización por ancla ausente es −0,30. El bonus de categoría es +0,15. Si la ancla sigue mirando solo el nombre, «golosinas» hunde a los productos que sí están en la categoría | Dejar la ancla como está |
| Recall léxico | El `EXISTS` que arma candidatos léxicos usa el mismo conjunto. El `ORDER BY` de ese corte, después de «tiene stock», prioriza cobertura de categoría/evento y después `rotacion_index` | El corte es de 25 filas. Si el orden sigue siendo la similitud del nombre, los 25 son un corte arbitrario entre cientos de SKUs cuyo nombre no contiene la palabra | Subir `lexical_n` a todo el catálogo. El re-rank ya está capado a 100 candidatos |
| `categoria_token` | Fracción de tokens de la consulta que aparecen en categoría, padre o `evento`. Peso 0,15. No reemplaza a `name_token`: un token que solo está en el nombre sigue sumando ahí | Es el bonus propio. En «pan dulce navidad», pan y dulce sostienen `name_token` y navidad sostiene `categoria_token` | Meter la categoría dentro de `name_token` y no exponer un componente. `diagnosticar_busqueda` no podría mostrar de dónde salió el punto |
| Pesos que ceden | `similarity` 0,40 → 0,35. `name_token` 0,30 → 0,25. Penalización 0,25 → 0,20. El 0,15 nuevo sale de esos tres recortes de 0,05 | El usuario pidió ese reparto. La suma de similarity + name_token + penalización pasa de 0,95 a 0,95 con el componente nuevo incluido (0,35 + 0,25 + 0,20 + 0,15) | Inventar otro reparto. Bajar solo `similarity` en 0,15: una consulta de marca pura perdería demasiado vector |
| `evento` | Columna `productos.evento` `text` nullable. Tokens con el mismo fold que el nombre (minúsculas, sin acento) | El maestro trae Navidad, Pascua o Halloween aparte del nombre. Un alias no se puede repetir entre códigos, así que no escala a una campaña. En Almaro varias categorías ya llevan la palabra (`NAVIDAD GOLOSINAS`, `HUEVOS DE PASCUA`, `HALLOWEEN GOLOSINAS`); la columna cubre el SKU cuyo evento no es el nombre de la categoría | Seguir cargando un alias distinto por producto. Guardar el evento solo como categoría nueva y obligar a re-colgar el árbol |
| Diagnóstico | `explicar_score` suma `categoria_token` con su peso. Si el token ya está en categoría o evento, no sugiere crear un alias | Si no, el conector sigue pidiendo los 149 alias que este cambio vuelve innecesarios. El módulo ya dice que los pesos tienen que copiar al agente | Diagnosticar llamando al agente por HTTP |
| Prompt de Almaro | Un `UPDATE` revisado, una sola vez, de esa viñeta en `public.distribuidoras.system_prompt` donde aparezca la frase vieja. Se corre después de leer qué tenants matchean | Una migración que reescribe prompts se vuelve a aplicar si alguien replaya el archivo, y puede pisar un párrafo editado a mano | Editar solo el archivo `phase-01-3-system-prompt-v2.md`. No cambia al agente en producción |

Los demás pesos (stock, ancla, rotación, alias, afinidad, mental) quedan igual.

---

## Alcance

### Incluido

- Presencia, ancla y recall léxico: categoría del producto, categoría padre y `evento`.
- Componente `categoria_token` con peso 0,15 y el recorte de 0,05 en similarity, name_token y penalización.
- El agente cliente ya no ofrece `search_products_by_category`. Descripciones default de `search_products` alineadas.
- `diagnosticar_busqueda` expone `categoria_token` y deja de pedir un alias cuando el token ya está cubierto por categoría o evento.
- Reemplazo de la viñeta del prompt en los tenants que todavía dicen `search_products_by_category` para la categoría amplia. Almaro es el caso que hay que verificar.

### Fuera de alcance

- Borrar el código de `search_products_by_category` y sus tests de llamada directa.
- Rearmar el árbol de categorías de Almaro. `HALLOWEEN GOLOSINAS` puede seguir sin `parent_id`. El token sale del nombre de esa categoría.
- Backfill de `evento` desde el Excel. Quien ya tiene la palabra en la categoría no necesita la columna para los cuatro casos de arriba.
- Cambiar el tope de 25 candidatos léxicos o el de 100 del re-rank.
- Alias compartido entre varios productos. Sigue rechazado. Este spec evita necesitarlo para una familia o un evento.
- Tienda, field y backoffice de búsqueda.

---

## Orden de implementación

| Orden | Repo | Rama | Qué | PR |
|---|---|---|---|---|
| 1 | `backend-supabase` | `feat/busqueda-categoria` | Migración `evento`. Nada más en este PR si se quiere mergear el DDL primero | backend |
| 2 | `agente-conversacional-multi_tenant` | `feat/busqueda-categoria` | Scoring, recall, descripciones, dejar de ofrecer la tool | agent |
| 3 | `backend-supabase` | la misma rama | `diagnosticar_busqueda` con los pesos nuevos. Mergear junto con el agente o justo después: si entra antes, el diagnóstico describe una fórmula que el agente todavía no usa | backend |
| 4 | Datos | — | Lo absorbe el [109](./109-mitigacion-fusion-busqueda-categoria.md): prompts, vendedor y backoffice en la misma ventana que este deploy. No hay una segunda pasada | no es PR de producto |

El spec vive en `suplai-platform`.

Si el paso 1 y el 3 van en el mismo PR de backend, el merge del agente tiene que estar desplegado antes de dar por cerrada la prueba humana del diagnóstico. El agente puede desplegar con la columna ya creada: lee `evento` y tolera null.

---

## Migración de base de datos

`backend/sql/161_productos_evento.sql` (si 161 ya está tomado, el número siguiente libre; el último archivo hoy es 160).

- `ALTER TABLE` en cada schema de tenant que tenga `productos`: agregar `evento text` nullable. Sin default, sin backfill.
- No toca `clients` ni `v_cartera` / `v_prospectos`.
- Rollback: `ALTER TABLE … DROP COLUMN evento`. Si ya hay valores cargados, se pierden. No hay índice en esta entrega: el recall lee la categoría por el join que ya existe y `evento` en la fila del producto candidato, no por un barrido nuevo del catálogo.

El reemplazo de la viñeta del prompt no va en ese archivo.

---

## Plan de prueba en CI/CD

Agente:

- Test del score con tokens fijos, sin embeddings: un token solo en el padre cuenta para `name_token`, cancela la penalización, marca la ancla y llena `categoria_token` en 1.
- Un token solo en el nombre deja `categoria_token` en 0 y no pierde `name_token`.
- «pan dulce navidad»: pan y dulce en el nombre, navidad en la categoría, `categoria_token` = 1/3, `name_token` = 1.
- La descripción default de `search_products` no nombra `search_products_by_category` como camino de una categoría entera. El registry del agente cliente no ofrece esa tool.

Backend:

- Migración aplica en un schema de test y `evento` acepta null.
- `explicar_score` incluye `categoria_token` con peso 0,15 y los tres pesos recortados.
- Con el token cubierto por categoría, `sugerir_ajuste` no devuelve `campo: alias`.

Checks actuales de ambos repos en verde. No hace falta un smoke de datos de Almaro en CI.

---

## Plan de prueba humana

Después de desplegar agente y backend, y de aplicar el `UPDATE` de prompts del [109](./109-mitigacion-fusion-busqueda-categoria.md).

Servicios: agente de laboratorio o `probar_agente` contra el schema `almaro`. No hace falta la tienda.

1. Confirmar en el prompt ensamblado que la categoría amplia apunta a `search_products` y que la tool `search_products_by_category` no está en la lista del turno.
2. `diagnosticar_busqueda` con consulta `golosinas` y un `product_code` con stock bajo `GOMITAS` (hija de 1870). El desglose trae `categoria_token` mayor a 0, el token no figura como ausente y no sugiere un alias.
3. La misma tool con `navidad` y un SKU de `NAVIDAD GOLOSINAS` o `NAVIDAD CHOCOLATES` con stock.
4. Turno de cliente, cuatro frases, cada una en limpio: «golosinas», «navidad», «pan dulce navidad», «snacks».
5. En cada una, los primeros productos tienen stock y pertenecen a esa familia. La respuesta no pide elegir entre categorías.
6. Una marca puntual que ya funcionaba (por ejemplo un SKU de los casos reales de Almaro, Halls u Oreo) sigue encontrándose por nombre. El recorte de `similarity` no la saca del top.
