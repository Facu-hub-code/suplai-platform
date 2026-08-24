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
- Workflow n8n diario 01:00 ART que **crea pedidos del día** (día de visita + hash, sin IA) y mantiene vigentes promos, objetivos, torneo e inbox.
- Las 5 preguntas default del Copilot responden con datos.

---

## 2) Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Estrategia de datos | Curar el tenant existente; **borrar** SKUs/clientes/vendedores fuera del recorte | La UI de backoffice lista todos los productos y clientes, no solo `en_catalogo`/`activo_ai`. El usuario pidió recorte físico. Las líneas históricas de los 70 se conservan (items_pedido no tiene FK a productos) | Seguir ocultando (`en_catalogo=false`); recrear de cero |
| Catálogo 250 | `en_catalogo=true` + DELETE del resto | 352 SKUs vendidos por los 70 no estaban en el cruce imagen∩ventas; se borra el maestro y se dejan las líneas para no distorsionar montos | Remapear ítems al pool 250 |
| Vendedores | Reusar ids 10/11/12; **DELETE** ids 1/2/3 con cascada de tareas/ledger/podcast | Los inactivos seguían apareciendo en la UI | `activo=false` |
| Tickets / notificaciones | 18 existentes estáticos + 4 reclamos nuevos; **fuera del shift diario** | Mostrar cómo el agente escala olor/rotura/factura/logística; no regenerar notificaciones cada noche | Meter tickets en el shift |
| Prompt | `system_prompt` v2 + `metadata.use_new_system_prompt=true`; marca líder COFLER, plaza CABA | El legacy concatenaba identidad+contexto (Arcor, Córdoba) dos veces | Seguir en modo legacy |
| Geografía | Palermo, Belgrano, Colegiales, Villa Crespo, Caballito + HQ Chacarita | Compacto para zoom en videollamada; confirmado con el usuario | Eje sur (Barracas/Patricios) o Rosario (manifest viejo) |
| Zonas | Update in-place ids 1, 14–17; desactivar 18–20 | PDVs ya apuntan a esos ids; menos churn de FK | Borrar y recrear polígonos |
| Fechas vivas | n8n 01:00 ART: `generate_daily_demo_orders()` + `shift_sales_demo_dates()`. Pedidos **nuevos** por día de visita + md5 (~65% de la zona). El shift **ya no mueve pedidos**: solo promos/objetivos/torneo/chats, cada uno con su ancla. Tickets estáticos. Corre antes del cron Field 02:30. A las 03:00, `sanitize_field_task_skus()` deja las tareas con SKUs del catálogo 250 | Si se shifteaban pedidos y además se insertaban, el día de hoy se duplicaba y las métricas de 2 meses se aplastaban. El ML seguía prediciendo códigos borrados y Field mostraba tareas sin producto | Seguir shifteando pedidos; generador con IA; no sanitizar SKUs |
| Conector n8n | Nodo Postgres al pooler Supabase **6543** ejecutando la RPC | El nodo REST de Supabase no corre CTEs; el pooler es el conector a Supabase | Nodo Supabase REST; scripts locales diarios |
| Listas de precios | Activar las 4 y completar precios 1.00 / 1.15 / 0.90 / 0.85 | Onboarding estándar; lista 4 se llamaba “Probando” y 3/4 estaban vacías | Dejar 2 listas |

---

## 3) Alcance explícito

### Incluido (v1)

- Curado de catálogo (250 en catálogo, resto **borrado**), red comercial CABA, HQ, flags, promos vigentes.
- Field: templates, objetivos, torneo agosto 2026, seed 30 días, trigger 6 días, retrain ML.
- Conversaciones recientes (10–15) e insights recortados **sin reescritura** en el follow-up.
- 4 tickets de reclamo (calidad/rotura/factura/logística) estáticos.
- System prompt v2 (Tato, Demo CABA, COFLER; sin Arcor).
- Volumen de pedidos confirmados ≥ 2 meses atrás (backfill de `total` + seed de catálogo).
- Función SQL de pedidos diarios + shift, workflow n8n en `workflows/demo_shift_fechas_pedidos.json`.
- Manifest `implementacion/demo/` y CSVs de salida.
- QA Copilot (5 chips + evals `demo` si el backend local está disponible).

### Fuera de alcance (v1)

- Cambiar polígonos, pines o HQ una vez curados (el script saltea el mapa si ya hay 70 locations).
- Pedidos los **domingos** (ninguna zona tiene visita).
- Variar el mix con IA / sales-engine en el job diario.
- `PURGE MOCK demo` (purga física del tenant entero).
- Migraciones de schema (demo es plantilla DDL: no alterar estructura).
- Worktrees / cambios en `backend-supabase` o `product-management-app` salvo verificación.

---

## 4) Orden de implementación

| Orden | Repo | Rama | Qué |
|-------|------|------|-----|
| 1 | `suplai-platform` | `feat/demo-videollamadas` | Spec, `curar_tenant_demo.py`, `higiene_tenant_demo.py`, CSVs, manifest |
| 2 | Supabase `demo` | (datos) | Ejecutar el script contra pooler 6543 |
| 3 | `suplai-platform` | misma rama | JSON n8n + `generate_daily_demo_orders` + `shift_sales_demo_dates` |
| 4 | n8n Railway | UI / API | Publicar workflow, credential Postgres, activar schedule |
| 5 | QA | local | Backoffice `:3000` + backend `:8000`, tenant Demo |

**Merge humano:** solo platform (docs/scripts/workflow). Datos ya quedan en Supabase al correr el script.

---

## 5) Migración de base de datos

Sin migración de schema (no hay tablas/columnas nuevas en el modelo compartido).

**Datos (backfill) en schema `demo`:**

- `productos`: 250 `en_catalogo=true`; el resto se **borra** (tags, precios, aliases, documents, categorías).
- `clients`: solo el pool de 70 con pin; el resto se **borra** (pedidos/ítems, flags, cartera, PDV huérfanos).
- `vendedores`: solo 10/11/12; ids 1/2/3 **borrados** (tareas, ledger, podcast jobs).
- `pedidos.total` backfill desde ítems; seed de pedidos recientes con SKUs del catálogo 250.
- `ia_tickets`: 4 reclamos nuevos; no entran al shift diario.
- `public.distribuidoras.system_prompt` v2 + `metadata.use_new_system_prompt=true`.
- `public.distribuidoras.reglas_negocio.order_fulfillment.location_hub` (HQ).
- Función `demo.generate_daily_demo_orders()` (INSERT idempotente, sin tablas nuevas).
- Función `demo.shift_sales_demo_dates()` (ya no UPDATE de `pedidos`/`items_pedido`).
- Función `demo.sanitize_field_task_skus()` (remap de `combo_skus` huérfanos al catálogo 250).

**Rollback:** no hay backup automático. Riesgo: los SKUs/clientes/vendedores borrados no se reponen sin restore. Las líneas `items_pedido` de los 70 sobre SKUs borrados quedan huérfanas de maestro (a propósito). Zonas Rosario siguen `active=false`. HQ se revierte quitando `order_fulfillment` del JSONB.

---

## 6) Plan de prueba en CI/CD

- Evals Copilot tenant `demo` (`scripts/copilot-evals/`, `critical: true`) deben seguir verdes cuando corre el job de backend.
- No hay test automatizado del seed de datos ni del workflow n8n en el PR de platform.
- Gap: el PR de platform es docs + scripts + JSON; el mínimo aceptable es que el script termine con conteos 250 / 70 / 3 / 5 impresos y existan `demo.generate_daily_demo_orders()`, `demo.shift_sales_demo_dates()` y `demo.sanitize_field_task_skus()`.

---

## 7) Plan de prueba humana (antes del PR)

Servicios: backend `:8000` + backoffice `:3000`. Tenant **Demo**.

1. Mapa comercial: 5 polígonos CABA, 70 pines, HQ Chacarita, filtro por 3 vendedores.
2. Catálogo: **250 productos** (lista completa del backoffice = catálogo; no hay SKUs ocultos).
3. Clientes: **70** en la lista. Copilot chips: producto más vendido mes pasado; pedido más grande; resumen del agente esta semana; este mes vs anterior; crear grupo por zona (Palermo).
4. Field (un vendedor mock): `REPOSICION_HABITO`, `CROSS_SELL_COMBO`, `REACTIVAR_CLIENTE`; objetivos con progreso; torneo con ranking.
5. Inbox: conversaciones de esta semana (no regenerar). Notificaciones: las estáticas + 4 reclamos (olor feo, rotura, factura, demora).
6. Agente: system prompt v2, sin mencionar Arcor; se presenta como Demo / COFLER / CABA.
7. Tienda `demo`: catálogo carga.
8. n8n: ejecución manual. Deben aparecer pedidos `n8n_demo_pedido_diario` del día de visita (lunes=Palermo, etc.). La segunda corrida no duplica. Tickets no cambian de fecha. Histórico de pedidos de meses anteriores no se mueve.
9. Field: cada tarea pendiente muestra nombres de SKUs del catálogo 250 (no códigos huérfanos).
