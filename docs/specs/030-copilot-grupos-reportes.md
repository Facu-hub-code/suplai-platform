# Spec 030 — Copilot: grupos de clientes + fix métricas semanales + deprecar Slack reports

**Estado:** In progress  
**Fecha:** 2026-08-04  
**Tipo:** Cross-repo (backend + backoffice; platform docs)  
**Rama:** `feat/copilot-grupos-reportes` (mismo PR/rama, sin splits)

## 1) Objetivo

Ampliar Suplai Copilot para operaciones de back office (crear grupos) y corregir el resumen semanal del agente. Deprecar los reportes diarios a Slack (reutilizar capa de datos).

## 2) Decisiones de diseño técnico

| Decisión | Por qué |
|----------|---------|
| Modo `geo_zone_id` en `{schema}.grupos` | Membresía dinámica (como lista/etiqueta); clientes vía `puntos_venta.geo_zone_id`. Evita tabla N:M. |
| Copilot pregunta el modo si falta | UX: lista / etiqueta / geo-zona son mutuamente excluyentes. |
| Write con `confirm_token` | Mismo patrón que agenda (preview → confirmar en UI). |
| `this_week` = lun→hoy | Alinea Copilot con dashboard de métricas del agente. |
| Slack jobs apagados por defecto | Canal push frágil; datos siguen en `services/reports/*`. Alertas Slack de logging no se tocan. |

## 3) Alcance

**Incluido**
- Migración `95_grupos_geo_zone_id.sql`
- API grupos: create/preview/list/update + membership geo
- Tool Copilot `grupo_create` + artefact `action_preview`
- Fix `date_resolver` `this_week` + heuristic/prompt
- Deprecar jobs Slack diarios (`SLACK_REPORTS_ENABLED` default false)

**Fuera de alcance**
- UI wizard de estrategias con selector geo (puede venir después)
- Reemplazo email/PDF de los reportes Slack
- Reactivar `agenda_create` en Copilot

## 4) Orden de implementación

1. Backend (migración + grupos + copilot tools + slack off)
2. Backoffice (tipos, preview UI, chips sugeridos)
3. Docs platform

## 5) Migración de BD

- Columna `{schema}.grupos.geo_zone_id` (FK a `geo_zones` si existe)
- Índice `idx_grupos_geo_zone_id`
- Script: `backend-supabase/sql/95_grupos_geo_zone_id.sql`
- Rollback: `ALTER TABLE … DROP COLUMN geo_zone_id` por schema

## 6) Plan de prueba CI/CD

- `pytest tests/test_copilot_date_resolver.py tests/test_grupos_membership.py`
- Smoke manual Copilot: “Resumen del agente esta semana” → lun→hoy
- Smoke: “Creá un grupo…” → pregunta modo → preview → confirmar

## 7) Plan de prueba humana

1. Aplicar `sql/95_grupos_geo_zone_id.sql` en Supabase.
2. Backend local `8000` + backoffice `3000`.
3. Copilot → chip “Resumen del agente esta semana” → verificar rango lun–hoy.
4. Copilot → “Creá un grupo de clientes por zona” → elegir modo → confirmar.
5. Verificar en BO que el grupo existe y lista clientes correctos.
6. Confirmar en logs Railway: `SLACK_REPORTS_DEPRECATED` / jobs no programados.
