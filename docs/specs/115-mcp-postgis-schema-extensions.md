# 115 — Conector: el rol del mapa puede usar PostGIS

**Estado:** Borrador  
**Fecha:** 2026-10-14  
**Repos:** `backend-supabase` (grant y alta de tenant), `suplai-platform` (este spec)  
**Rama de este documento:** ninguna. Queda en el hub, sin rama.  
**Rama de implementación:** una rama nueva de `backend-supabase` desde `origin/main`, aparte de `feat/mcp-esquema-gemini`.  
**Relaciona:** [111](./111-mcp-geozonas-mapa.md), [113](./113-mcp-zonas-escritura-y-cobertura.md).

Hay otro agente en `feat/mcp-esquema-gemini` aplanando el JSON Schema para Gemini (`mcp_server/main.py`, `mcp_server/esquema_publico.py`, `tests/test_mcp_esquema_gemini.py`). Esta entrega no toca esos archivos.

---

## Objetivo

`listar_geozonas` y `mapa_zonas` vuelven a responder. El rol `mcp_connector` puede resolver `ST_MakeValid` y el resto de PostGIS que ya usan el mapa y las previsualizaciones de zona.

### Criterios de aceptación

- En un tenant con zonas activas (Campi o `esekau`), `listar_geozonas` devuelve `id`, `nombre`, `clientes` y `con_coordenadas`. No aparece `UndefinedFunctionError` ni `st_makevalid`.
- `mapa_zonas` devuelve el polígono de cada zona activa y el resumen de monto, pedidos y clientes activos.
- Con el id que devolvió el listado, `consultar_pedidos`, `metricas_conversaciones` y `explorar_clientes` filtran por `geozona_id` como hoy.
- Una previsualización de zona (hull o buffer) deja de fallar por una función PostGIS inexistente.
- `has_schema_privilege('mcp_connector', 'extensions', 'USAGE')` queda en true. El `EXECUTE` de `extensions.st_makevalid(extensions.geometry)` sigue en true.
- El aplanado de esquemas para Gemini no entra en este diff.

---

## Cómo está hoy

Medido el 2026-10-14 en Suplai-east (`cvlbietibaaehgeimxgw`).

PostGIS está en el schema `extensions`. Ahí viven `st_makevalid(geometry)`, `st_makevalid(geom geometry, params text)`, `st_asgeojson` y `st_simplifypreservetopology(geometry, double precision)`. La columna `{schema}.geo_zones.geometry` es de tipo `extensions.geometry` (visto en `del_corro`, `demo` y `esekau`).

El conector entra con el rol `mcp_connector` (`MCP_DB_URL`). Ese rol tiene `EXECUTE` sobre `st_makevalid` y **no** tiene `USAGE` sobre el schema `extensions`. Sin `USAGE`, Postgres no ve los objetos del schema: la llamada sin calificar responde `function st_makevalid(extensions.geometry) does not exist`. El `search_path` del rol está vacío (`rolconfig` null).

El código del mapa ya mete `extensions` en el `search_path` de la transacción:

- `services/metricas_zona.py` `_en_schema`: `{schema}, public, extensions`.
- `services/mcp_zonas.py` `_abrir`: el mismo valor.

Eso no alcanza. Un schema en el `search_path` sigue invisible si el rol no tiene `USAGE`.

`listar_geozonas` no llama PostGIS en su `SELECT`. Desde el 113 la tool pone `mostrar_mapa` y `adjuntar_mapa` (`mcp_server/mapa_respuesta.py`) llama `armar_mapa`. Ahí está el polígono:

```sql
ST_AsGeoJSON(
    ST_SimplifyPreserveTopology(ST_MakeValid(geometry), $1::float8),
    5
)
```

`mapa_zonas` entra a la misma sentencia. Por eso las dos tools fallan con el mismo error y, sin el listado, no hay `geozona_id` para los análisis.

`consultar_pedidos` filtra `geozona_id` por columna, con `search_path` `{schema}, public`, sin PostGIS. Si el id ya se conoce, esa tool no depende de este grant. El bloqueo de hoy es no poder resolver el id.

Las previsualizaciones de `services/mcp_zonas.py` usan el mismo rol y las mismas funciones sin calificar (`ST_MakePoint`, `ST_ConvexHull`, `ST_Buffer`, `ST_Contains`, `ST_Area`). Fallan por la misma causa.

`sql/145_mcp_oauth.sql` y `sql/164_mcp_geozonas_grants.sql` dan `USAGE` y `SELECT` sobre los schemas de tenant y sobre `geo_zones` / `client_locations`. No dan `USAGE` sobre `extensions`. `core/tenancy.py::grant_mcp_connector_on_schema` tampoco.

En `extensions` también están `pgcrypto`, `uuid-ossp` y la vista `pg_stat_statements`. `PUBLIC` ya tiene `SELECT` sobre esa vista. Hoy el conector no la lee porque le falta `USAGE` del schema.

---

## Decisiones de diseño técnico

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| `GRANT USAGE ON SCHEMA extensions TO mcp_connector` | El `EXECUTE` ya está. Falta el privilegio para ver el schema. Con el `search_path` que las queries ya arman, `ST_MakeValid` y el resto de PostGIS pasan a resolverse. Un solo grant cubre el listado, el mapa y las previsualizaciones. | Calificar `extensions.st_makevalid(...)` o volver a agregar `extensions` al `search_path`. El `search_path` ya lo incluye. Sin `USAGE`, el nombre calificado pasa a `permission denied for schema extensions`. |
| El grant vive en una migración nueva y, otra vez, al inicio de `grant_mcp_connector_on_schema` | La migración cubre los tenants que ya existen. El alta de un tenant vuelve a emitir el mismo `GRANT`, que es idempotente y no depende del schema nuevo. `extensions` es global. | Dejar el grant solo en la migración y que un entorno nuevo dependa de acordarse de correrla a mano. |
| No se reescriben las sentencias SQL | El fallo es de privilegio, no de la fórmula del polígono. Tocar `metricas_zona.py` o `mcp_zonas.py` abre un diff grande al lado del trabajo de Gemini sin cambiar el resultado. | Prefijar cada `ST_*` en el mapa y en las previsualizaciones. |
| La rama de implementación sale de `origin/main` y no edita los archivos de Gemini | Ese trabajo aplana `inputSchema` para que Gemini no descarte el servidor. Este fallo es el rol de base. Los dos diffs no se pisan si esta entrega se queda en SQL y en `core/tenancy.py`. | Meter el grant en `feat/mcp-esquema-gemini`. |
| Se acepta que, con el login de `mcp_connector`, alguien podría leer `extensions.pg_stat_statements` | `PUBLIC` ya tiene `SELECT` sobre esa vista. El conector no ejecuta SQL libre: corre las tools. El login vive en el servicio MCP. Revocar `PUBLIC` afectaría al resto de los roles que hoy leen la vista. | Un schema puente con funciones `SECURITY DEFINER` solo para PostGIS. Resuelve el hueco de `pg_stat_statements` y obliga a reescribir cada llamada. Queda para otra entrega si el login del conector pasa a estar en un lugar menos cerrado. |

---

## Alcance

### Incluido

- `GRANT USAGE ON SCHEMA extensions TO mcp_connector` para el rol que ya existe.
- El mismo `GRANT` dentro de `grant_mcp_connector_on_schema`, antes de los grants por tabla.
- Un test del helper que exige esa sentencia.

### Fuera de alcance

- Cambiar el JSON Schema, las descripciones o el HTML del mapa.
- Los archivos que está editando la rama de Gemini.
- Calificar funciones PostGIS en el SQL.
- `REVOKE` sobre `pg_stat_statements` o `pgcrypto`.
- Grants para `mcp_readonly`. El backend no lo usa.
- Cambiar el `search_path` de `consultar_pedidos` (`{schema}, public`). Esa tool no llama PostGIS.

---

## Orden de implementación

| Orden | Repo | Rama | Qué |
|---|---|---|---|
| 1 | `suplai-platform` | ninguna | Este spec. |
| 2 | `backend-supabase` | `fix/mcp-postgis-extensions` desde `origin/main` | `sql/167_mcp_extensions_usage.sql` y el `GRANT` en `grant_mcp_connector_on_schema`. Después el test del helper. |

Se puede mergear antes o después de `feat/mcp-esquema-gemini`. No comparte archivos con ese diff.

---

## Migración de base de datos

No hay tablas ni columnas nuevas. No hay seed ni backfill.

`sql/167_mcp_extensions_usage.sql`:

- Si el rol `mcp_connector` existe, `GRANT USAGE ON SCHEMA extensions TO mcp_connector`.
- Si no existe, la migración no hace nada (el alta lo concede cuando el rol aparezca).

`core/tenancy.py::grant_mcp_connector_on_schema` emite el mismo `GRANT` cuando el rol ya existe.

Orden: aplicar la migración en Suplai-east. El helper queda para el próximo alta de tenant. Rollback: `REVOKE USAGE ON SCHEMA extensions FROM mcp_connector`. Las tools de zona vuelven al error de hoy. No se reescriben polígonos.

Riesgo: el login del conector gana visibilidad del schema `extensions`, incluida la vista `pg_stat_statements` (ya concedida a `PUBLIC`). Las tools siguen siendo las sentencias fijas del servidor.

---

## Plan de prueba en CI/CD

En `backend-supabase`, un test del helper con la conexión mockeada:

- Con el rol presente, la primera sentencia es `GRANT USAGE ON SCHEMA extensions TO mcp_connector` y después siguen los grants de tablas que ya emite.
- Sin el rol, no emite grants.

CI no entra a Suplai-east como `mcp_connector`. El `UndefinedFunctionError` se cierra en la prueba humana. Los tests de `tests/test_mcp_geozonas.py` y del esquema Gemini quedan verdes; esta entrega no los modifica.

---

## Plan de prueba humana

MCP en el puerto que ya usa el conector (`8100` en local) contra un backend que haya aplicado la migración. Backoffice en `3000` solo si se quiere contrastar el polígono con el mapa comercial. Tenant: Campi (`del_corro`) o `esekau`.

1. Pedir «listame las zonas». La tool `listar_geozonas` responde con ids y nombres. En el error no aparece `st_makevalid`.
2. Pedir «mostrame el mapa». `mapa_zonas` trae polígonos y totales. El iframe carga.
3. Con el nombre de una zona del paso 1, pedir «¿cómo viene esa zona?». Las tools de análisis van con `geozona_id`.
4. En el schema de prueba, pedir una previsualización de zona a partir de tres clientes con coordenada. El preview vuelve con polígono, sin error de función PostGIS. No hace falta confirmar la escritura.
