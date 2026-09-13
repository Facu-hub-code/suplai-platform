# SPEC: 068 — Alerta de hueco mensual de pedidos ERP

**Estado:** Implementación  
**Fecha:** 2026-09-13  
**Índice cross-repo:** este documento (platform) · backend `docs/specs/129-erp-pedidos-hueco-mensual.md` (mismo contrato)  
**Repos:** `backend-supabase` (job + `ia_tickets`), `product-management-app` (sin PR: usa Notificaciones existentes)

---

## 1) Objetivo

Avisar en Notificaciones del backoffice cuando un mes calendario (ART) tiene un volumen de pedidos canónicos anómalo — típico de un corte de sync ERP — para no enterarnos semanas después por Field o métricas.

## 2) Decisiones de diseño técnico

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| Contar `{schema}.pedidos` confirmado/descargado, no `erp_orders_raw` | Field, métricas y sales-engine leen el canónico. Un espejo lleno con canónico vacío es exactamente el bug de El Gigante (raw agosto, `pedidos` cortados en julio). | Alertar solo el raw: no explica por qué Field está ciego. |
| Ticket `ia_tickets` tag `[ERP_PEDIDOS_HUECO]`, sin WhatsApp | Mismo canal que `[LISTA_PRECIOS_ERP]`. El operador ya mira Notificaciones. | Slack/email: segundo canal; campanita nueva: trabajo de UI. |
| Hueco = `n=0` con vecino ≥ 100, o `n < 15%` de la mediana de los últimos 6 meses con `n>0` | Simple, atrapa agosto-2026 de El Gigante (0 vs ~3k) y no un mes flojo de 500. | Desvío estadístico / z-score: overkill y frágil con estacionalidad. |
| Excluir el mes calendario en curso | Evita falso positivo a mitad de mes. | Incluir el mes actual con umbral diario: más reglas. |
| Un ticket `open` por `(schema, YYYY-MM)`; se cierra si el mes deja de ser hueco | Idempotente en el job 6h. | Un ticket eterno: ruido cuando el catch-up ya arregló. |
| Corre al final del job ERP 6h y tras proyección Galileo | Ahí es cuando el canónico cambia. | Cron aparte: otro schedule que olvidar. |
| Todos los tenants con `pull_orders` | El cálculo es barato (12 agregados). El Gigante es el primer caso. | Solo `el_gigante`: hay que tocar código al sumar tenants. |

## 3) Alcance

**Incluido (v1)**

- Servicio de detección + upsert/cierre de `ia_tickets`.
- Hook post `run_erp_sync_job` y post auto-proyección Galileo / `orders-raw/project` (`dry_run=false`).
- Tests unitarios del cálculo y de idempotencia (mocks DB).
- Spec + runbook de catch-up El Gigante.

**Fuera de alcance**

- UI nueva en backoffice (el listado de Notificaciones ya muestra `description`).
- WhatsApp / `on_ia_ticket_created`.
- Rellenar meses vacíos en Galileo (agosto-2026 no existe en el espejo MySQL).
- Hard wipe spec 072.

## 4) Orden de implementación

1. Catch-up El Gigante (clave + sync + proyectar) — ops, este worktree.
2. Backend `feat/el-gigante-galileo-huecos` → PR hacia `main`. Merge **antes** de depender del job 6h para la alerta.
3. Retrain sales-engine y wipe/regenerar Field (después de pedidos al día).
4. Backoffice: sin PR.

## 5) Migración de base de datos

Sin migración de BD. Reusa `{schema}.ia_tickets` (`description`, `status`, `closed_at`).

## 6) Plan de prueba en CI/CD

- Unit: julio 3000 / agosto 0 / septiembre 800 → agosto es hueco; mes actual excluido.
- Unit: todos los meses ~3000 → 0 huecos.
- Unit: mes con 400 vs mediana 3000 → no hueco (≥15%).
- Unit: mes con 200 vs mediana 3000 → hueco.
- Idempotencia: segundo run no inserta duplicado; mes reparado cierra el ticket.
- Checks existentes del backend deben quedar verdes.

## 7) Plan de prueba humana (antes del PR)

1. Backend local `8000` (pooler `6543`, `statement_cache_size=0`). Backoffice `3000` si se quiere ver el ticket.
2. Tenant `el_gigante` (o `demo` con un mes vacío inventado en staging).
3. Tras sync+proyección, `POST /{schema}/erp/orders-raw/project` (`dry_run=false`) o esperar el job.
4. En Notificaciones: ticket `[ERP_PEDIDOS_HUECO]` del mes 2026-08 (El Gigante) o del mes forzado.
5. Si se proyectan pedidos de ese mes, el siguiente run deja el ticket `closed`.

## 8) Contrato del ticket

```
[ERP_PEDIDOS_HUECO] |2026-08| Pedidos del mes anómalos (n=0; mediana reciente=3016). Revisá sync/proyección ERP.
```

Marker `|YYYY-MM|` para parsear e idempotencia.
