# SQL — envíos HSM / carrusel

Reemplazar `<schema>`, `<tenant_id>`, `<dia>` (`YYYY-MM-DD` ART), `<template>` (opcional).

Proyecto MCP: `cvlbietibaaehgeimxgw`. Una sola llamada con los bloques unidos por `;`.

## Ventana ART

```sql
SELECT
  (DATE '<dia>'::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires') AS from_ts,
  ((DATE '<dia>' + 1)::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires') AS to_ts;
```

"Ayer": `<dia> = (CURRENT_DATE AT TIME ZONE 'America/Argentina/Buenos_Aires')::date - 1`.

## 1. Tenant + plantillas carrusel

```sql
SELECT id::text, nombre, schema_name
FROM public.distribuidoras
WHERE schema_name = '<schema>';

SELECT id, template_name, category, variable_columns
FROM public.meta_plantillas
WHERE tenant_id = '<tenant_id>'::uuid
  AND (template_name ILIKE '%carousel%' OR template_name ILIKE '%carrusel%')
ORDER BY template_name;
```

## 2. Agendas del día (puntual + recurrente carrusel)

```sql
SELECT
  a.id, a.activo, a.tipo, a.hora_envio::text, a.fecha_programada,
  a.enviado_at, a.proxima_fecha_envio, a.grupo_id, g.nombre AS grupo_nombre,
  jsonb_typeof(a.carousel_config) AS carousel_type,
  COALESCE(jsonb_array_length(a.carousel_config), 0) AS n_cards,
  mp.template_name
FROM <schema>.agenda a
JOIN public.meta_plantillas mp ON mp.id = a.meta_plantilla_id
LEFT JOIN <schema>.grupos g ON g.id = a.grupo_id
WHERE a.fecha_programada = DATE '<dia>'
   OR (
     a.tipo = 'recurrente'
     AND a.activo
     AND EXISTS (
       SELECT 1 FROM unnest(a.dia_semana) AS d
       WHERE LOWER(TRIM(d::text)) = '<weekday_es>'  -- lunes|martes|miércoles|jueves|viernes|sábado|domingo
     )
     AND (
       mp.template_name ILIKE '%carousel%'
       OR mp.template_name ILIKE '%carrusel%'
       OR jsonb_typeof(a.carousel_config) = 'array'
     )
   )
ORDER BY a.id;
```

Mapa weekday: lun=lunes … jue=jueves … (igual que el backend). Alternativa: recurrentes con `enviado_at` dentro de la ventana UTC del día ART.

## 3. Envíos aceptados en la ventana

```sql
SELECT
  ep.template_name,
  COUNT(*) AS n,
  COUNT(DISTINCT ep.session_id) AS n_destinos,
  MIN(ep.created_at) AS first_at,
  MAX(ep.created_at) AS last_at
FROM <schema>.envios_plantillas ep
WHERE ep.created_at >= (DATE '<dia>'::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires')
  AND ep.created_at <  ((DATE '<dia>' + 1)::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires')
GROUP BY ep.template_name
ORDER BY n DESC;
```

## 4. Esperados del grupo (etiquetas)

`grupos.etiqueta_ids` es `int[]`. Incluir descendientes:

```sql
WITH RECURSIVE etq AS (
  SELECT id FROM <schema>.etiquetas
  WHERE id = ANY((SELECT etiqueta_ids FROM <schema>.grupos WHERE id = <grupo_id>))
  UNION ALL
  SELECT e.id FROM <schema>.etiquetas e
  JOIN etq ON e.parent_id = etq.id
)
SELECT
  COUNT(*) AS n_clientes,
  COUNT(*) FILTER (WHERE c.activo_ai IS NOT FALSE) AS n_activo_ai,
  COUNT(*) FILTER (
    WHERE c.activo_ai IS NOT FALSE
      AND length(regexp_replace(COALESCE(c.phone_number,''), '[^0-9]', '', 'g')) >= 10
  ) AS n_con_tel
FROM <schema>.clients c
JOIN <schema>.clientes_etiquetas ce ON ce.client_id = c.id AND ce.etiqueta_id IN (SELECT id FROM etq);
```

Grupo por `geo_zone_id` o `lista_precios_id`: no usar este CTE; listar `clients` según esas FKs (mismo criterio que `agenda_sender._get_clientes_del_grupo`).

## 5. Replies 48h (canónico: core)

```sql
SELECT COUNT(DISTINCT ep.session_id) AS destinos_con_reply
FROM <schema>.envios_plantillas ep
JOIN core.conversations c
  ON c.schema_name = '<schema>' AND c.session_id = ep.session_id
JOIN core.conversation_events ce
  ON ce.conversation_id = c.id
 AND ce.event_type = 'user_message'
 AND ce.created_at > ep.created_at
 AND ce.created_at < ep.created_at + INTERVAL '48 hours'
WHERE ep.created_at >= (DATE '<dia>'::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires')
  AND ep.created_at <  ((DATE '<dia>' + 1)::timestamp AT TIME ZONE 'America/Argentina/Buenos_Aires')
  AND ep.template_name ILIKE '%<template>%';
```

Fallback: `{schema}.n8n_chat_histories` con `message->>'type' IN ('human','user')`.

## 6. Stats Meta (opcional)

```sql
SELECT template_name, date, sent, delivered, read, replied
FROM <schema>.meta_template_stats_daily
WHERE date = DATE '<dia>'
  AND template_name ILIKE '%carousel%';
```

Tabla vacía ≠ envíos fallidos; el cache a veces no se llena.

## Loki (si SQL no explica el hueco)

```
{service_name="backend-suplai", tenant_name="<schema>", event_code="WHATSAPP_TEMPLATE_SEND_FAILED"}
```

Dashboard típico: Grafana Backend Logs. No inventar el cuerpo del error si no hay logs.
