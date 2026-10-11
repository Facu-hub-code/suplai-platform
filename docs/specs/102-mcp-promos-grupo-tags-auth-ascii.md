# 102 — Conector: promo de grupo, tags/categorías y fondo ASCII

**Estado:** Borrador  
**Fecha:** 2026-10-11  
**Repos:** `backend-supabase` (tools, OAuth, tests)  
**Rama:** `feat/mcp-promos-tags-ascii`  
**Relaciona:** [101](./101-mcp-listas-precios-promos.md)

---

## Objetivo

Tras el pool de catálogo (8/8 OK), Claude puede editar una promo de varios SKUs con aviso, editar o borrar un tag o una categoría que ya existe, y ve la esfera ASCII de Field al reconectar el conector.

### Métricas de éxito

- Editar una promo `sku_group` cambia fechas o descuento. El preview avisa cuántos SKUs toca. Si pasan códigos nuevos, el preview dice que reemplazan la lista.
- Crear combo nuevo sigue fuera: sin `promocion_id` el alta es de un SKU.
- `previsualizar_tag_producto` / `previsualizar_categoria` con id renombra y suma productos. Sin id, sigue creando.
- `previsualizar_eliminar_tag_producto` / `previsualizar_eliminar_categoria` + `confirmar` borra. Si hay hijos, el preview se niega.
- Login y consentimiento OAuth muestran la esfera ASCII de Field detrás de la card.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Promo grupo | Editar con `promocion_id`. No crear combo nuevo | El QA pidió editar, no abrir el alta de combos. El backoffice ya no deja cambiar el scope. | Crear `sku_group` desde Claude. |
| Aviso | Texto en el preview: N SKUs, el descuento aplica a todos, códigos nuevos reemplazan | Evita borrar miembros sin querer. | Soft-merge de códigos. |
| Tags/categorías | Mismo preview + `tag_id` / `categoria_id`. Delete en tools nuevas | Igual que promo. No suma tools de “editar”. Delete es destructivo y Claude lo ve aparte. | Una tool `accion=borrar`. |
| Asignar productos | Suma, no saca | El alta ya era aditiva. Sacar es otro caso. | Reemplazar el set. |
| Hijos | No se borra un padre con hijos | Igual que el DELETE de categorías del backoffice. | CASCADE. |
| ASCII | Canvas + script de `AnimatedSphere` en `services/oauth/screens.py` | El HTML OAuth no es React. Portar el loop evita un bundle. | Iframe a Field. |
| CHECK | `sql/155` suma `lista_precios`, `eliminar_promocion`, `eliminar_tag`, `eliminar_categoria` | El 101 se mergeó sin migración y falló el preview. | Reusar el tipo `tag_producto` para borrar. |

---

## Alcance

### Incluido

- Editar promo `sku_group` (descripción, fechas, descuento, lista de SKUs).
- Editar tag/categoría (nombre, padre, sumar códigos).
- Borrar tag/categoría.
- Fondo ASCII en login y consentimiento OAuth.
- Recetas, descripciones, catálogo 43 tools.

### Fuera de alcance

- Crear una promo combo nueva.
- Sacar un SKU de un tag/categoría sin borrar el grupo.
- Cambiar `promo_scope`.
- ASCII en el widget embebido del chat.

---

## Orden de implementación

1. Migración CHECK 155 (también cubre los tipos del 101).
2. Promos grupo + tests.
3. Tags/categorías edit/delete + tests.
4. ASCII OAuth + test de HTML.
5. Superficie 43, recetas, spec.

Un PR de `backend-supabase`. El spec vive en `suplai-platform`.

---

## Migración de base de datos

`sql/155_mcp_accion_previews_lista_promo.sql`: amplia `mcp_accion_previews_tipo_check` con `lista_precios`, `eliminar_promocion`, `eliminar_tag`, `eliminar_categoria`.

Sin columnas nuevas. Rollback: restaurar el check de `sql/153`.

---

## Plan de prueba en CI/CD

- `test_mcp_qa_conector.py`: promo grupo con aviso; tag/categoría edit y delete; check SQL cubre handlers.
- `test_mcp_superficie.py`: 43 tools.
- `test_mcp_carga.py`: consentimiento sigue listando permisos; HTML trae `#ascii-bg`.
- Checks existentes verdes.

---

## Plan de prueba humana (antes del PR)

Servicios: backend `8000`. Tenant: `demo`. Claude conectado.

1. `listar_catalogo` entidad `promocion`. Editar una de varios SKUs (fecha o %). El preview avisa N productos. Confirmar.
2. Intentar crear un combo nuevo sin id: el conector pide un solo código.
3. `listar_catalogo` entidad `tag`. Renombrar uno y sumar un SKU. Confirmar. Borrar un tag de prueba sin hijos.
4. Igual con una categoría hoja.
5. Intentar borrar un padre con hijos: se niega.
6. Desconectar el conector y volver a conectar: login y consentimiento muestran la esfera ASCII detrás de la card.
