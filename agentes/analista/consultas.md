# Consultas del Analista

SQL de ejemplo para el dashboard diario, probado en solo lectura contra la base principal (Supabase, `project_ref=cvlbietibaaehgeimxgw`) el 2026-11-04. Todas devuelven **conteos**: ningún mail, teléfono, nombre ni texto de conversación.

Convenciones:

- Los días son de Argentina (`America/Argentina/Buenos_Aires`). "Ayer" es `current_date - 1`.
- `<schema>` es el tenant (`dimer`, `almaro`). Reemplazalo en el texto de la consulta.
- Si una consulta falla dos veces, no insistas: decilo en el dashboard.

## 1. Envíos de plantillas (paso 2)

`{schema}.envios_plantillas` solo tiene los envíos que Meta aceptó; `delivery_status` dice si después se entregó o falló (detalle en la skill `check-hsm-sends`).

### ¿Hubo envío?

```sql
select '<schema>' as tenant,
  count(*) filter (where created_at >= ((current_date - 1)::timestamp at time zone 'America/Argentina/Buenos_Aires')
                     and created_at <  (current_date::timestamp at time zone 'America/Argentina/Buenos_Aires')) as envios_ayer,
  (max(created_at) at time zone 'America/Argentina/Buenos_Aires')::date as ultimo_dia_con_envio
from <schema>.envios_plantillas;
```

### Embudo de un día

`<dias_atras>`: `1` para el envío de ayer, `4` y `7` para volver a medir. Respondieron cuenta destinos con un `user_message` en las 48 h siguientes (sin leer el texto). Pedidos cuenta destinos con un pedido en los 7 días siguientes: `con_pedido` incluye los que entraron por el ERP; `con_pedido_suplai` solo los del agente y la tienda (`origen` `suplai` o `tienda`).

```sql
with dia as (select current_date - <dias_atras> as d),
env as (
  select ep.* from <schema>.envios_plantillas ep, dia
  where ep.created_at >= (dia.d::timestamp at time zone 'America/Argentina/Buenos_Aires')
    and ep.created_at <  ((dia.d + 1)::timestamp at time zone 'America/Argentina/Buenos_Aires')
),
ped as (
  select regexp_replace(cl.phone_number, '\D', '', 'g') as tel,
         p.fecha at time zone 'America/Argentina/Buenos_Aires' as fecha, p.origen
  from <schema>.pedidos p join <schema>.clients cl on cl.id = p.cliente_id
  where p.deleted_at is null
)
select (select d from dia) as dia, env.template_name,
  count(*) as enviados,
  count(*) filter (where env.delivery_status = 'delivered') as entregados,
  count(*) filter (where env.delivery_status = 'failed') as fallidos,
  count(distinct env.session_id) filter (where exists (
    select 1 from core.conversations c
    join core.conversation_events ce on ce.conversation_id = c.id
    where c.schema_name = '<schema>' and c.session_id = env.session_id
      and ce.event_type = 'user_message'
      and ce.created_at > env.created_at
      and ce.created_at < env.created_at + interval '48 hours')) as respondieron,
  count(distinct env.session_id) filter (where exists (
    select 1 from ped
    where ped.tel = regexp_replace(env.session_id, '\D', '', 'g')
      and ped.fecha > env.created_at and ped.fecha < env.created_at + interval '7 days')) as con_pedido,
  count(distinct env.session_id) filter (where exists (
    select 1 from ped
    where ped.tel = regexp_replace(env.session_id, '\D', '', 'g')
      and ped.origen in ('suplai', 'tienda')
      and ped.fecha > env.created_at and ped.fecha < env.created_at + interval '7 days')) as con_pedido_suplai
from env
group by env.template_name
order by enviados desc;
```

Si la ventana de 48 h o de 7 días todavía no terminó, el número es parcial: aclaralo en el dashboard.

## 2. Uso del MCP (paso 3)

Clasifica cada llamada en cliente, interna o demo con la regla de `agentes/README.md`. El mail se compara dentro de la consulta y no se devuelve.

```sql
with clase as (
  select a.*, d.schema_name as tenant,
    case
      when regexp_replace(coalesce(p.role, ''), '_inactivo$', '') in ('super_admin', 'comercial', 'partner')
        or exists (select 1 from public.usuario_permisos up
                   where up.user_id = a.usuario_id and up.permiso = 'comercial')
        or lower(split_part(u.email, '@', 2)) = 'suplaisales.com' then 'interna'
      when d.schema_name = 'demo' or p.role = 'demo' then 'demo'
      else 'cliente'
    end as tipo
  from public.mcp_auditoria a
  left join public.distribuidoras d on d.id = a.distribuidora_id
  left join public.profiles p on p.id = a.usuario_id
  left join auth.users u on u.id = a.usuario_id
  where a.ts >= now() - interval '7 days'
)
select coalesce(tenant, '(sin tenant)') as tenant, tipo,
  count(distinct usuario_id) as usuarios,
  count(*) filter (where ts >= ((current_date - 1)::timestamp at time zone 'America/Argentina/Buenos_Aires')
                     and ts <  (current_date::timestamp at time zone 'America/Argentina/Buenos_Aires')) as llamadas_ayer,
  count(*) as llamadas_7d,
  count(*) filter (where resultado = 'error') as errores_7d,
  count(*) filter (where resultado = 'rechazado') as rechazados_7d,
  max(ts) as ultima_actividad
from clase
group by 1, 2
order by llamadas_7d desc;
```

`resultado` toma `ok`, `error` o `rechazado`.

### Tools más usadas

```sql
select coalesce(d.schema_name, '(sin tenant)') as tenant, a.herramienta,
  count(*) as llamadas_7d,
  count(*) filter (where a.resultado = 'error') as errores_7d
from public.mcp_auditoria a
left join public.distribuidoras d on d.id = a.distribuidora_id
where a.ts >= now() - interval '7 days'
group by 1, 2
order by llamadas_7d desc
limit 15;
```

No leas `parametros`: puede traer nombres o teléfonos que buscó el usuario.

## 3. Reclamos y pedidos del MCP (paso 4)

### Conteos

`product_feedback` trae `user_role` y `user_email` en la fila: se usan para clasificar y no se devuelven. `preguntas_sin_respuesta` no tiene usuario y queda "sin clasificar".

```sql
with fb as (
  select f.schema_name as tenant, f.section as tipo, f.created_at,
    case
      when f.schema_name in ('comercial', 'partner')
        or regexp_replace(coalesce(f.user_role, ''), '_inactivo$', '') in ('super_admin', 'comercial', 'partner')
        or lower(split_part(f.user_email, '@', 2)) = 'suplaisales.com' then 'interna'
      when f.schema_name = 'demo' or f.user_role = 'demo' then 'demo'
      else 'cliente'
    end as origen
  from public.product_feedback f
  where f.section in ('mcp:error', 'mcp:feature')
),
psr as (
  select coalesce(schema_name, '(sin tenant)') as tenant, 'sin_respuesta'::text as tipo,
         created_at, 'sin clasificar'::text as origen
  from core.preguntas_sin_respuesta
),
todo as (select * from fb union all select * from psr)
select tenant, tipo, origen,
  count(*) filter (where created_at >= ((current_date - 1)::timestamp at time zone 'America/Argentina/Buenos_Aires')
                     and created_at <  (current_date::timestamp at time zone 'America/Argentina/Buenos_Aires')) as nuevos_ayer,
  count(*) filter (where created_at >= now() - interval '7 days') as ultimos_7d,
  count(*) as total,
  max(created_at) as ultimo
from todo
group by 1, 2, 3
order by ultimos_7d desc, total desc;
```

### Texto para el resumen

La tabla del dashboard pide un resumen de cada reclamo. El reclamo lo escribe el usuario del MCP (la distribuidora), no es una conversación de cliente. Esta consulta tapa mails y números largos antes de devolver el texto; igual, resumilo con tus palabras y no copies nombres.

```sql
select f.schema_name as tenant, f.section as tipo, f.created_at,
  left(regexp_replace(regexp_replace(coalesce(f.submitted_text, f.original_text, ''),
    '[[:alnum:]._%+-]+@[[:alnum:].-]+', '[mail]', 'g'),
    '\+?\d[\d\s-]{6,}\d', '[número]', 'g'), 300) as texto
from public.product_feedback f
where f.section in ('mcp:error', 'mcp:feature')
  and f.created_at >= ((current_date - 1)::timestamp at time zone 'America/Argentina/Buenos_Aires')
order by f.created_at;
```

Para `core.preguntas_sin_respuesta`, lo mismo con la columna `pregunta`. No leas `contexto` ni `consulta`.
