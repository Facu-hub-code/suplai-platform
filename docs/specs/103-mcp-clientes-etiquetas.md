# 103 — Conector: clientes, etiquetas y resumen

**Estado:** Borrador  
**Fecha:** 2026-10-11  
**Repos:** `backend-supabase` (tools, preview, recetas, tests), `suplai-platform` (este spec)  
**Rama:** `feat/mcp-clientes-etiquetas`  
**Relaciona:** [095](./095-claude-mcp-carga-clientes-productos.md), [097](./097-claude-mcp-grupos-agendas.md), [102](./102-mcp-promos-grupo-tags-auth-ascii.md), [076](./076-grupos-conjuncion-etiqueta-lista-dias.md)

---

## Objetivo

Tras el QA de la sección clientes, Claude deja de ver códigos `9002.0`, el `resumen` deja de quedar en 0, puede crear una etiqueta por códigos (sin grupo), y puede renombrar o borrar etiquetas de clientes. Los códigos que no existen salen en el preview.

### Métricas de éxito

- `explorar_clientes` y `buscar_clientes` muestran `9002`, no `9002.0`. Un código alfanumérico en la carga sigue rechazado.
- Confirm de carga: `resumen.aceptadas` coincide con `insertadas`.
- Preview de etiqueta por códigos: `resumen.aceptadas` coincide con los clientes que matchearon; el código inventado aparece en `rechazadas`.
- `audiencia=codigos` + `nombre` crea la etiqueta y la asigna. No hace falta un grupo.
- `previsualizar_editar_etiqueta` + `confirmar` renombra. `previsualizar_eliminar_etiqueta` + `confirmar` borra una hoja y saca el id de `grupos.etiqueta_ids`.

---

## Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|---|---|---|---|
| Código | Solo formato en las tools MCP (`codigo_txt`). Columna sigue `numeric` | El QA pidió dejar de ver `.0`. Cambiar a texto toca PDV, vistas `v_cartera`/`v_prospectos` y todos los casts | `ALTER` numeric→text en esta entrega |
| Alfanuméricos | Siguen rechazados en `_codigo()` | Sin migración no hay dónde guardarlos | Aceptarlos y truncar |
| `resumen` | `asegurar_preview` mapea `insertadas`, `clientes`, `conteo`, `asignados` y filas `aceptada` | El wrapper inventaba `aceptadas: 0` en confirm y en etiquetas | Parchear cada return |
| Crear por códigos | `nombre` o `etiqueta_id` con `audiencia=codigos`. `nombre` no cuenta como grupo | El error “pasá grupo o códigos” mentía: faltaba el id | Seguir exigiendo grupo para crear |
| Códigos faltantes | Lista `rechazadas`. Si ninguno matchea, error que nombra los códigos | La receta ya lo prometía | Preview vacío de 0 clientes |
| Editar / borrar | Tools nuevas, scope `estrategias:escribir` | Delete es destructivo; mezclarlo en `previsualizar_etiqueta` confunde assign vs rename | `accion=borrar` |
| Hijos | No se borra una etiqueta con hijas | Igual que tags/categorías | CASCADE de hijas |
| Grupos al borrar | `array_remove` del id en `grupos.etiqueta_ids` | Ese array no tiene FK. Si queda el id, el grupo cuenta 0 y parece cache | Dejar el id huérfano |
| Duplicados de grupo | Aviso + receta. Sin UNIQUE | Ya hay ocho “No responden”. UNIQUE rompe el alta | Merge automático |
| Lista 1 en 23 | No se cambia el AND (076). Aviso si `total=0` y hay etiquetas | El conteo es en vivo. Los 9 nuevos no entran si falta un eje | Cachear el total |
| `activo_ai` | Sigue `true`. Aviso en preview/receta | La carga operativa prende la IA. El 555 es un número de prueba, no un default nuevo | Apagar IA en el insert |

---

## Alcance

### Incluido

- Formato de código en `explorar_clientes`, `buscar_clientes` y previews de etiqueta.
- `resumen.aceptadas` correcto en preview y confirm.
- Crear etiqueta por códigos; listar códigos rechazados.
- Editar y borrar etiquetas de clientes (preview + `confirmar`).
- Avisos de grupo vacío / nombre repetido y recetas (etiquetas, carga, grupos).
- Catálogo 45 tools. `sql/156` para el CHECK de previews.

### Fuera de alcance

- Migración `clients.codigo` / `puntos_venta.codigo` a texto.
- Validar WhatsApp en la carga (089) o apagar `activo_ai` por defecto.
- Deduplicar grupos ya existentes.
- Cambiar la conjunción AND de grupos.
- CRUD de etiquetas en el backoffice.

---

## Orden de implementación

1. Spec (este documento) en `suplai-platform`.
2. `asegurar_preview` + formato de código.
3. Etiqueta por códigos + rechazadas.
4. Edit/delete + `sql/156` + dispatch.
5. Avisos de grupos y recetas.
6. Tests. PR backend, después spec.

Ramas: `feat/mcp-clientes-etiquetas` en ambos repos. Merge: backend (aplicar 156 en prod) → platform.

---

## Migración de base de datos

`sql/156_mcp_accion_previews_etiquetas.sql`: amplia `mcp_accion_previews_tipo_check` con `editar_etiqueta` y `eliminar_etiqueta`.

Sin columnas nuevas. Sin backfill. Rollback: restaurar el check de `sql/155`.

`clients.codigo` no cambia.

Aplicar 156 en producción **antes** de probar edit/delete contra Railway. Si no, el preview falla con `CheckViolationError` (misma causa que listas/promos).

---

## Plan de prueba en CI/CD

- `test_mcp_superficie.py`: 45 tools; `asegurar_preview` con `insertadas` / `conteo`.
- `test_mcp_qa_conector.py`: el CHECK cubre `_HANDLERS`.
- Tests nuevos de etiqueta por códigos, rechazadas, edit, delete (hijos se niegan; `array_remove` en grupos).
- `fila_cliente` / `codigo_txt` sin `.0`. `_codigo()` sigue rechazando alfanuméricos.
- Checks existentes verdes.

---

## Plan de prueba humana (antes del PR)

Servicios: no hace falta backoffice. Claude o el conector contra el tenant de prueba. Si se prueba contra Railway, aplicar `sql/156` primero.

1. Cargar 2 clientes con código `9002`. `explorar_clientes` y `buscar_clientes` muestran `9002`. Un código `AB12` se rechaza.
2. Confirm de carga: `resumen.aceptadas` = `insertadas`. El aviso dice IA prendida y WhatsApp no validado.
3. Etiquetar 10 códigos (uno inventado): el preview lista el que falta; `resumen` no queda en 0.
4. `nombre` + códigos crea la etiqueta y la asigna, sin grupo.
5. Renombrar esa etiqueta. Borrarla. Los grupos que la usaban ya no la tienen en `etiqueta_ids`. Intentar borrar un padre con hijas: se niega.
6. `listar_envios` entidad `grupo`: “Lista 1” muestra lista/día/etiqueta. Si no sumó los 9, se ve qué AND los deja afuera. Duplicados históricos siguen con `nombre_repetido`.
