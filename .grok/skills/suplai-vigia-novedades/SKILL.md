---
name: suplai-vigia-novedades
description: >-
  Use when the Vigía bot runs its daily check, or when someone asks which new
  products entered dimer, almaro or gonzales and what each one is missing for
  the sales agent to find it (photo, description, alias, category, embedding,
  stock, price). Read-only on Supabase.
when-to-use: novedades, productos nuevos, vigía, dimer, almaro, gonzales, ficha lista
---

# Vigía de novedades

Detectás los productos nuevos de cada tenant y anotás qué le falta a cada uno para que el agente lo encuentre. **Solo leés:** no escribís en la base ni en Linear.

Definición completa: `docs/grok-bot/novedad-lista.md`.

## Entradas

| Dato | Valor |
|---|---|
| Tenants | `almaro`, `gonzales`, `dimer`, en ese orden |
| MCP | Supabase, `project_id: cvlbietibaaehgeimxgw`, tool `execute_sql`, solo `SELECT` |
| Última corrida | `~/suplai-bots/estado/vigia-{schema}.json` → `{"desde": "<ISO con -03:00>"}`. Si no existe, usá hace 7 días. |

## Pasos

1. Por cada tenant, leé `desde` del archivo de estado y corré la consulta de abajo, reemplazando `{schema}` y `{desde}`. Es una sola llamada por tenant: nada de loops por producto.
2. Guardá el resultado en `~/suplai-bots/novedades/{AAAA-MM-DD}-{schema}.json`, con la fecha de Argentina. El bot de catálogo y el jefe lo leen de ahí.
3. Solo si la consulta salió bien, actualizá el archivo de estado con el `created_at` más nuevo que viste. Si falló, no lo toques: la próxima corrida vuelve a mirar el mismo tramo.
4. Si la consulta devuelve 200 filas, hay más: corré de nuevo con `desde` igual al último `created_at` del lote.
5. Avisale al jefe (handoff o group chat) con el resumen.

## Consulta

```sql
with n as (
  select p.product_code, p.nombre, p.created_at, p.en_catalogo, p.motivo_baja, p.stock,
    exists (select 1 from {schema}.precios_productos pp join {schema}.listas_precios l on l.id = pp.lista_precios_id
            where pp.product_code = p.product_code and l.activa and pp.precio_unidad > 0) as precio,
    coalesce(p.image_url, '') <> '' as foto,
    coalesce(length(p.descripcion), 0) >= 20
      and lower(p.descripcion) <> lower(p.nombre)
      and p.descripcion not like 'Combo GEV [%' as descripcion,
    exists (select 1 from {schema}.productos_aliases a where a.product_code = p.product_code) as alias,
    exists (select 1 from {schema}.product_categories c where c.product_code = p.product_code) as categoria,
    exists (select 1 from {schema}.documents d
            where d.metadata->>'product_code' = p.product_code and d.metadata->>'chunk' = 'producto'
              and (p.descripcion is null or strpos(d.content, p.descripcion) > 0)) as embedding
  from {schema}.productos p
  where coalesce(p.is_mock, false) = false
    and p.created_at > '{desde}'
)
select product_code, nombre, created_at, en_catalogo and motivo_baja is null as en_catalogo,
  stock > 0 as stock, precio, foto, descripcion, alias, categoria, embedding,
  (en_catalogo and motivo_baja is null and stock > 0 and precio and foto and descripcion and alias and categoria and embedding) as lista,
  nombre ilike 'COMBO%' as combo
from n
order by created_at
limit 200;
```

## Cómo leer el resultado

| Falta | Quién lo resuelve |
|---|---|
| `foto`, `descripcion`, `alias`, `categoria`, `embedding` | Bot de catálogo |
| `stock`, `precio` | El ERP. No se inventan: el jefe lo reporta como bloqueo del ERP |
| `en_catalogo` falso | Nadie: el agente no lo ofrece. Se cuenta aparte |

## Resumen para el jefe

Por tenant: novedades (cuántas son combos), cuántas en catálogo, cuántas listas y cuántas les faltan por campo. Después, los códigos que trabaja el catálogo y los bloqueados por el ERP. Números exactos, en español.

## Errores

| Error | Qué hacer |
|---|---|
| Columna o tabla no existe | `list_tables` con `verbose: true` en ese schema. No adivines y avisale al jefe. |
| Timeout | Reintentá una vez. Si vuelve a fallar, seguí con el próximo tenant y reportalo. |
| Muchas más novedades que lo normal (más de 300 en un día) | Probablemente es una recarga del ERP. Reportala sin tocar el archivo de estado y esperá al jefe. |
