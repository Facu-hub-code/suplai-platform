# 109 — Mitigación: fusionar la búsqueda y sacar `search_products_by_category` de prompts, backoffice y vendedor

**Estado:** Borrador  
**Fecha:** 2026-10-12  
**Repos:** `agente-conversacional-multi_tenant`, `backend-supabase`, `product-management-app`, `suplai-platform` (e2e y docs de producto)  
**Ramas sugeridas:** si [108](./108-agente-busqueda-por-categoria.md) sigue sin merge, la misma `feat/busqueda-categoria` en agente y backend, y `feat/mitigacion-busqueda-categoria` en backoffice. Si el 108 ya está en la troncal, rama nueva con el mismo slug en los tres repos.  
**Relaciona:** [108](./108-agente-busqueda-por-categoria.md) (el cliente ya no recibe la tool y `search_products` pesa categoría y evento)  
**Tenant que lo pidió:** `almaro`, y el resto de los prompts que todavía nombran la tool

---

## Objetivo

El 108 deja de ofrecer `search_products_by_category` al agente de cliente y mete el peso de categoría en `search_products`. Este spec cierra lo que queda alrededor de esa fusión, para que el modelo no reciba la orden de llamar una tool que no está en el turno, y para que el backoffice no la muestre como un interruptor que prende algo.

Hay dos fallas concretas, y las dos dependen del orden:

- Si el prompt se reescribe y el agente viejo sigue en producción, `search_products` corre sin el peso de categoría. «Golosinas» y «navidad» siguen fallando, con una tool que sí existe.
- Si el agente del 108 se despliega y el prompt sigue nombrando `search_products_by_category`, el modelo llama una tool que el schema del turno no tiene.

La mitigación es una sola ventana: el agente que no ofrece la tool, el texto que ya no la nombra, y la pantalla que ya no la prende, salen juntos.

### Métricas de éxito

- Ningún `system_prompt` ni `contexto` de `public.distribuidoras` contiene `search_products_by_category`.
- El agente de cliente y el de vendedor arman el turno sin esa tool.
- En el backoffice la ficha queda visible para los logs históricos, con estado en desuso, y el interruptor no la vuelve a ofrecer.
- Un turno de Almaro con «golosinas» llama `search_products`. La respuesta no pide elegir categoría.
- En las 48 h siguientes al deploy no aparecen ejecuciones con error de tool desconocida `search_products_by_category`.

---

## Inventario medido el 2026-10-12

El runtime lee un solo texto. Con `metadata.use_new_system_prompt = true` y `system_prompt` no vacío, usa ese campo. Si el flag no está, usa identidad + contexto + reglas, y el `system_prompt` no entra aunque esté cargado (`use_new_system_prompt_enabled` en el agente).

| Schema | Flag v2 | Dónde está el nombre | Qué lee el turno hoy |
|---|---|---|---|
| almaro | sí | `system_prompt` y `contexto` | `system_prompt` |
| ruggeri | sí | `system_prompt` | `system_prompt` |
| colormix, distribuidora_lyl, el_quesero, mayorius, molinos_minetti | no | los dos | `contexto` |
| curlo, distribuidora_moreno, independiente, quimica_austral, suplai | no | solo `contexto` | `contexto` |
| benfresh, gonzales | sí | solo `contexto` | `system_prompt` (el nombre está dormido) |

La clave `search_products_by_category` aparece en `tools_habilitadas` de `al_fuego`, `almaro`, `cordoba_frost`, `demo`, `forsa`, `gonzales`, `vadra` y `valaice`. Esos ocho no entran al SQL de prompts salvo que el nombre también esté en el texto. Después de este spec la clave deja de tener efecto: el bind no la consulta para ofrecer la tool.

Tres frases distintas, medidas en los prompts. No son intercambiables:

1. **Routing.** Almaro: la viñeta «Categoría amplia … → `search_products_by_category`».
2. **Link de catálogo.** colormix, distribuidora_lyl, molinos_minetti, mayorius, el_quesero: «cuando uses la herramienta `search_products_by_category`, anexa el link…».
3. **Alternativa.** Ruggeri: «usá `search_products` o `search_products_by_category`».

curlo, distribuidora_moreno, independiente, quimica_austral, suplai, benfresh y gonzales se clasifican en uno de esos tres al leer la frase, antes de escribir el `UPDATE`.

Superficies de código que todavía la nombran y cambian comportamiento:

- Agente vendedor: `app/agent/tools/providers/catalog.py` la agrega si `actor_profile == "seller"`. `SELLER_BASE_TOOL_NAMES` en `registry.py` la incluye.
- Rail de listado: `build_catalog_listing_retry_messages` en `app/agent/seller/rails/catalog.py` le dice al modelo que llame `search_products`, `search_products_by_category` o `get_product_by_code`. `CATALOG_LISTING_TOOL_NAMES` en `pdv_patterns.py` la trata como listado válido.
- Backoffice: `lib/agent-tools-editorial.ts` la tiene en el set de dry-run. La pantalla de tools (`components/tools-config-section.tsx`, `components/admin/distribuidora-tools.tsx`) prende `tools_habilitadas` para lo que el catálogo declara en `agent_groups`. Hoy `agent_tools_catalog_meta.json` la marca `shared` para `seller` y `client`.
- Ficha: `core.agent_tools`, sembrada en `sql/78_agent_tools_editorial_and_executions.sql` con status `active` y el texto «Lista productos filtrando por rubro».
- E2E: `scripts/fase-09-e2e/` acepta la tool como búsqueda semántica válida. Los casos reales de Almaro en `implementacion/almaro/` traen `expected_tools` con ese nombre.
- Docs de producto vivos: `docs/producto/agent-tools-documento-funcionalidades.md` y `docs/producto/inventario-features-casos-negocio.md`.

La función Python sigue existiendo. La dejan los tests directos y las filas viejas de `core.agent_tool_executions`.

---

## Decisiones de diseño

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| Prompt, agente y backoffice salen en la misma ventana de deploy | El prompt adelantado manda familias a `search_products` sin el peso del 108. El agente adelantado hace que el modelo llame una tool ausente del schema. Juntos, las dos fallas no se abren. | Reescribir los prompts una semana después del deploy, que es lo que el paso 4 del 108 dejaba abierto. |
| Se reescribe el nombre en `system_prompt` y en `contexto`, esté o no en el campo que el turno lee hoy | El flag v2 cambia qué campo entra. Una copia dormida (benfresh, gonzales, y el contexto de Almaro) vuelve a producción el día que alguien da vuelta el flag. | Tocar solo el campo vivo de cada tenant. |
| Tres reemplazos, uno por frase, leídos antes de ejecutarlos | La viñeta de routing, la instrucción del link y la alternativa de Ruggeri no comparten el resto de la oración. Un reemplazo del nombre solo deja «cuando uses la herramienta `search_products`» en un tenant y corta la frase del link en otro. | `replace` global de `search_products_by_category` por `search_products`. |
| El vendedor también deja de recibir la tool | El prompt es el mismo para los dos perfiles. Si el vendedor la conserva, el rail de reintento le sigue enseñando el nombre al modelo y el interruptor del backoffice sigue cambiando un solo perfil. | Dejarla en el vendedor hasta un spec posterior. |
| La ficha y el nombre en los logs se quedan. El interruptor deja de ofrecerla | `core.agent_tool_executions` y los dry-runs históricos citan el nombre. Borrar la fila deja esos logs sin ficha. `status = deprecated`, `agent_groups` vacío, y la UI muestra «en desuso». La clave en `tools_habilitadas` no se borra: el bind ya no la mira para armar el turno. | `DELETE` de `core.agent_tools` y de la clave en `tools_habilitadas`. |
| El set que reconoce un listado ya hecho sigue incluyendo el nombre. El mensaje que le pide al modelo llamar una tool, no | Un hilo que ya llamó la tool vieja no tiene que disparar otro reintento. El system message del reintento, si la nombra, le enseña al modelo a llamarla en el turno nuevo. | Sacarla de los dos lugares, o dejarla en el mensaje de reintento. |
| El editor de prompt del backoffice no guarda un texto que contenga el nombre | El SQL de esta entrega limpia lo que hay hoy. El editor es el camino por el que vuelve a entrar mañana. El guard es un rechazo de ese guardado, con el texto «esa tool ya no se ofrece; usá `search_products`». | Un aviso que deja guardar igual. |
| Los casos de categoría esperan `search_products` | Si `expected_tools` sigue exigiendo la tool vieja, el e2e falla el día del deploy aunque el ranking sea el del 108. | Aceptar las dos como válidas en los casos nuevos, sin fecha de corte. |

---

## Alcance

### Incluido

- Dejar de bindear la tool en el agente de vendedor, igual que el 108 ya hace con el de cliente.
- Mensaje de reintento del rail: nombra `search_products` y `get_product_by_code`.
- `CATALOG_LISTING_TOOL_NAMES` sigue reconociendo la tool vieja como listado ya ejecutado.
- Migración nueva de editorial: `core.agent_tools` de esa tool pasa a `deprecated`, con `short_description` y `when_to_use` que mandan a `search_products`. No se edita `sql/78`.
- `agent_tools_catalog_meta.json`: `agent_groups` vacío para esa tool.
- Backoffice: la fila se ve con badge «en desuso» y sin interruptor que la prenda. El set de dry-run la conserva para abrir un log viejo.
- Editor de prompt: rechaza guardar si el texto contiene `search_products_by_category`.
- `UPDATE` revisado, tenant por tenant, de `system_prompt` y `contexto`, con los tres patrones. Fuera del archivo de migración.
- E2E de plataforma y `expected_tools` de los casos reales de Almaro: la búsqueda de una familia espera `search_products`.
- Una línea en los dos docs de producto vivos. La skill de fase 1.3 no nombra la tool; no se toca.

### Fuera de alcance

- Cambiar pesos, recall o la columna `evento`. Eso es el 108.
- Borrar la función `search_products_by_category` del código. Sigue para un test directo y para leer logs viejos.
- Reescribir specs históricos (018, 024, 071, 103, 128, 130, 132, 136) ni `sql/78`.
- Reparentar categorías de Almaro.
- Borrar la clave de `tools_habilitadas` en los ocho schemas que la tienen.
- Un linter genérico de tools inventadas. Este guard mira este nombre.

---

## Orden de implementación

| Paso | Repo | Rama | Qué entra | Merge |
|---|---|---|---|---|
| 1 | `backend-supabase` | `feat/busqueda-categoria` o `feat/mitigacion-busqueda-categoria` | Migración editorial y `agent_groups` vacío. El backoffice lee el status de esta API | primero |
| 2 | `agente-conversacional-multi_tenant` | la misma rama del 108, o la nueva si el 108 ya se mergeó | Unbind del vendedor y mensaje de reintento. En el mismo deploy que el 108 si ese todavía no salió | con el paso 1 |
| 3 | `product-management-app` | `feat/mitigacion-busqueda-categoria` | Badge, interruptor apagado, rechazo en el editor de prompt | después del paso 1 |
| 4 | `suplai-platform` | `feat/mitigacion-busqueda-categoria` | E2E y la línea de los docs de producto. Los JSON de `implementacion/almaro/` se editan en el hub, sin rama de producto | cuando el paso 2 está en la rama |
| 5 | Datos | — | `UPDATE` revisado de prompts, en la misma ventana en que se despliega el agente del paso 2. No va en la migración: un replay reescribiría prompts ya editados a mano | después del deploy del agente, el mismo día |

Si el 108 y este spec salen juntos, el paso 5 reemplaza el paso 4 del 108. No hay una segunda pasada de prompts.

Orden de merge: backend → agente, en el mismo release. Backoffice después del backend. El SQL de prompts, el día del deploy del agente, no antes.

---

## Migración de base de datos

Archivo nuevo en `backend/sql/`, número siguiente al último aplicado (el 108 reserva el 161 para `evento`).

- `UPDATE core.agent_tools` donde `tool_name = 'search_products_by_category'`: `status = 'deprecated'`, `short_description` y `when_to_use` indican que la búsqueda de una familia va por `search_products`. No se borra la fila.
- No altera `{tenant}.productos`, `clients`, `v_cartera` ni `v_prospectos`.
- Rollback: volver `status` a `active` y restaurar los tres textos de la ficha. No hay columna que dropear.

El `UPDATE` de `system_prompt` y `contexto` es un script revisado, corrido a mano en esa ventana. Cada tenant queda con el diff de su frase en el PR de datos o en el mensaje de la corrida, antes de ejecutarlo.

---

## Plan de prueba en CI/CD

Agente:

- El bind de cliente y el de vendedor no incluyen `search_products_by_category`.
- El system message de `build_catalog_listing_retry_messages` no contiene ese nombre y sí contiene `search_products`.
- `CATALOG_LISTING_TOOL_NAMES` sigue conteniendo el nombre viejo.

Backend:

- La migración deja la fila en `deprecated` y no la borra.
- `agent_tools_catalog_meta.json` tiene `agent_groups` vacío para esa tool.

Backoffice:

- Test del guard del editor: un texto con el nombre no se guarda; un texto con `search_products` sí.
- Si la pantalla de tools no tiene test de componente, el mínimo del PR es el typecheck. La prueba del badge queda en el plan humano.

Plataforma:

- El caso de categoría del e2e espera `search_products`.

Checks actuales de los cuatro repos en verde. No hace falta un smoke de Almaro en CI.

---

## Plan de prueba humana

Antes del SQL de prompts, con backend en `8000` y backoffice en `3000`.

1. En la pantalla de tools de Almaro, `search_products_by_category` se ve «en desuso» y no hay interruptor que la pase a activa. `search_products` sigue prendible.
2. En el editor de prompt, pegar la viñeta vieja de Almaro y guardar. El guardado no entra y el mensaje nombra `search_products`.
3. Sacar esa viñeta del borrador y guardar un cambio inocuo del mismo prompt. Entra.

El día del deploy del agente, después del `UPDATE` revisado:

4. Prompt ensamblado de Almaro (v2, lee `system_prompt`) y de colormix (legacy, lee `contexto`): no aparece el nombre viejo. Ruggeri tampoco. benfresh, con v2, no lo tiene en `system_prompt`; el `contexto` reescrito tampoco lo tiene, por si el flag se apaga.
5. `probar_agente` en Almaro, turno de cliente, «golosinas». La traza llama `search_products`. La respuesta no pide elegir categoría. Un turno de vendedor arma tools sin `search_products_by_category`.
6. Una marca que ya funcionaba (Halls u Oreo en los casos de Almaro) sigue encontrándose por nombre.
7. A las 48 h, `core.agent_tool_executions` no tiene filas nuevas de esa tool con error de tool desconocida. Las filas anteriores a la ventana siguen abriendo la ficha en el backoffice.
