# SPEC-035 — Tenant Demo listo para videollamadas de ventas

**Estado:** Implemented (datos en schema `demo`; workflow n8n `zBDJRgEDeuJuKe62` activo)  
**Fecha:** 2026-08-24  
**Repos:** `suplai-platform` (datos + n8n JSON). Escrituras acotadas al schema `demo` en Suplai-east.  
**Tenant:** `demo` (`public.distribuidoras.id` = `8f8fcf47-c191-4cc7-a7d2-5703d474bb8a`)

---

## 1) Objetivo

Dejar el tenant **Demo** navegable en videollamadas de ventas, usando la totalidad del sistema (catálogo, mapa, Field, Copilot, inbox, promos, tienda) **sin huecos ni configuración errónea**.

Criterios de aceptación:

- 250 productos en catálogo con imagen, descripción, tags, `rotacion_index` y precio en 4 listas.
- 70 clientes geolocalizados en 5 barrios de CABA, con PDV, vendedor y flags WhatsApp/ERP.
- Mapa: 5 zonas MultiPolygon irregulares + HQ en Chacarita/Paternal.
- 3 vendedores ficticios con cartera ~14 / 28 / 28.
- Field: tareas de los 3 tipos, 2 objetivos vigentes, torneo del mes.
- Workflow n8n diario 01:00 ART que desplaza fechas para que tareas y objetivos se sigan creando.
- Las 5 preguntas default del Copilot responden con datos.

---

## 2) Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Estrategia de datos | Curar el tenant existente (ocultar, no borrar FKs) | 910 SKUs y 943 pedidos ya alimentan Copilot/ML; recrear de cero pierde historial | Onboarding greenfield; `DELETE` masivo |
| Catálogo 250 | `en_catalogo=true` en el cruce imagen ∩ ventas de los 70 clientes | Copilot y Field combo/hábito no pueden quedar mudos | 250 SKUs aleatorios con foto |
| Geografía | Palermo, Belgrano, Colegiales, Villa Crespo, Caballito + HQ Chacarita | Compacto para zoom en videollamada; confirmado con el usuario | Eje sur (Barracas/Patricios) o Rosario (manifest viejo) |
| Vendedores | Reusar ids mock 10/11/12; `activo=false` en 1/2/3 | Evita romper FKs de `field_tasks` / cartera | Insertar 3 filas nuevas |
| Zonas | Update in-place ids 1, 14–17; desactivar 18–20 | PDVs ya apuntan a esos ids; menos churn de FK | Borrar y recrear polígonos |
| Fechas vivas | Función `demo.shift_sales_demo_dates()` + n8n 01:00 ART, `delta = today - MAX(fecha)` | Self-healing: si hay pedido de hoy, no mueve; corre antes del cron Field 02:30 | Cron en backend; shift fijo de +1 día |
| Conector n8n | Nodo Postgres al pooler Supabase **6543** ejecutando la RPC | El nodo REST de Supabase no corre CTEs; el pooler es el conector a Supabase | Nodo Supabase REST; scripts locales diarios |
| Listas de precios | Activar las 4 y completar precios 1.00 / 1.15 / 0.90 / 0.85 | Onboarding estándar; lista 4 se llamaba “Probando” y 3/4 estaban vacías | Dejar 2 listas |
| Tickets | Dejar 18 (10 open / 8 closed); el resto se cierra y se marca fuera de demo | 55 tickets abiertos ensucian Insights | Borrar todos |

---

## 3) Alcance explícito

### Incluido (v1)

- Curado de catálogo, red comercial CABA, HQ, flags, promos vigentes.
- Field: templates, objetivos, torneo agosto 2026, seed 30 días, trigger 6 días, retrain ML.
- Conversaciones recientes (10–15) e insights recortados.
- Función SQL + workflow n8n versionado en `workflows/demo_shift_fechas_pedidos.json`.
- Manifest `implementacion/demo/` y CSVs de salida.
- QA Copilot (5 chips + evals `demo` si el backend local está disponible).

### Fuera de alcance (v1)

- Código nuevo de follow-ups Copilot (`follow_ups.py`, spec 044).
- Cambiar el system prompt del agente salvo que QA lo exija.
- `PURGE MOCK demo` (purga física).
- Migraciones de schema (demo es plantilla DDL: no alterar estructura).
- Worktrees / cambios en `backend-supabase` o `product-management-app` salvo verificación.

---

## 4) Orden de implementación

| Orden | Repo | Rama | Qué |
|-------|------|------|-----|
| 1 | `suplai-platform` | `feat/demo-videollamadas` | Spec, script `scripts/demo-videollamadas/curar_tenant_demo.py`, CSVs, manifest |
| 2 | Supabase `demo` | (datos) | Ejecutar el script contra pooler 6543 |
| 3 | `suplai-platform` | misma rama | JSON n8n + función `demo.shift_sales_demo_dates()` |
| 4 | n8n Railway | UI / API | Publicar workflow, credential Postgres, activar schedule |
| 5 | QA | local | Backoffice `:3000` + backend `:8000`, tenant Demo |

**Merge humano:** solo platform (docs/scripts/workflow). Datos ya quedan en Supabase al correr el script.

---

## 5) Migración de base de datos

Sin migración de schema (no hay tablas/columnas nuevas en el modelo compartido).

**Datos (backfill) en schema `demo`:**

- `productos.en_catalogo`, `precios_productos` (4 listas), tags faltantes.
- `geo_zones` geometría CABA, `vendedores`, `clients`, `puntos_venta`, `client_locations`, `vendedores_clientes`.
- `public.distribuidoras.reglas_negocio.order_fulfillment.location_hub` (HQ).
- Función `demo.shift_sales_demo_dates()` (solo este schema).

**Rollback:** no hay backup automático. Riesgo bajo: no se borran productos ni pedidos; se ocultan (`en_catalogo=false`, `activo=false`). Zonas Rosario quedan `active=false` y se pueden reactivar. HQ se revierte quitando `order_fulfillment` del JSONB.

---

## 6) Plan de prueba en CI/CD

- Evals Copilot tenant `demo` (`scripts/copilot-evals/`, `critical: true`) deben seguir verdes cuando corre el job de backend.
- No hay test automatizado del seed de datos ni del workflow n8n en el PR de platform.
- Gap: el PR de platform es docs + scripts + JSON; el mínimo aceptable es que el script termine con conteos 250 / 70 / 3 / 5 impresos y la función SQL exista (`SELECT demo.shift_sales_demo_dates()` en dry-run con delta 0).

---

## 7) Plan de prueba humana (antes del PR)

Servicios: backend `:8000` + backoffice `:3000`. Tenant **Demo**.

1. Mapa comercial: 5 polígonos CABA, 70 pines, HQ Chacarita, filtro por 3 vendedores.
2. Catálogo: ~250 en catálogo, con foto y precio.
3. Copilot chips: producto más vendido mes pasado; pedido más grande; resumen del agente esta semana; este mes vs anterior; crear grupo por zona (Palermo).
4. Field (un vendedor mock): `REPOSICION_HABITO`, `CROSS_SELL_COMBO`, `REACTIVAR_CLIENTE`; objetivos con progreso; torneo con ranking.
5. Inbox: conversaciones de esta semana. Promos: al menos una vigente.
6. Tienda `demo`: catálogo carga.
7. n8n: ejecución manual del workflow; `MAX(fecha)::date` de pedidos = hoy (si no había pedido de hoy).
