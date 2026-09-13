# El Gigante — estado integración Galileo

**Tenant:** `el_gigante` (`965a6919-7967-4f3b-93bd-2b468b3ccb2e`)  
**Fecha del reporte:** 12-sep-2026 / catch-up 13-sep-2026  
**Alcance:** diagnóstico de la integración Galileo + validación del catch-up de MySQL y ERP. La clave nueva quedó solo en `public.tenant_secrets` (`erp.credentials`); no se commiteó secreto.

---

## Resumen ejecutivo

**Semáforo: rojo a amarillo con recuperación parcial.** Galileo sigue vivo y la clave nueva funciona. El job de pull estaba cortado desde el **4-sep** y el canónico ERP quedó estancado en pedidos hasta el **28-jul**, pero el catch-up del 13-sep reanudó la ingesta de catálogo, precios, clientes y pedidos. El problema principal dejó de ser “sin datos” y pasó a ser “datos nuevos pero con huecos pendientes”:

| Pregunta | Respuesta |
|---|---|
| ¿La clave nueva entra al MySQL espejo? | Sí. Host `srv561.hstgr.io:3306`, DB `u606379220_gigan_suplai`. |
| ¿El mapeo de columnas es correcto? | Sí. Las tablas `SUPLAI_*` coinciden con spec y conector; hay drift menor, pero no rompe el pull. |
| ¿Galileo actualiza al menos 1 vez al día? | Pedidos sí, en días hábiles. Productos/precios a saltos; clientes puntual. Listas/vendedores casi no cambian. |
| ¿Suplai está al día? | No al inicio del diagnóstico; sí se recuperó parcialmente con catch-up del 13-sep. |
| ¿Se proyectan los pedidos al canónico? | Sí, parcialmente. Tras el catch-up, `MAX(fecha)` ERP volvió a **2026-09-11** con 793 pedidos sep proyectados; quedan 69 raw sep sin proyectar. |

Acciones clave del turno de diagnóstico/catch-up:

1. Persistir la nueva clave en `public.tenant_secrets` (`erp.credentials`) y revalidar `POST /el_gigante/erp/connect`.
2. Re-sync pull de catálogo, precios, clientes y pedidos (`force` / ventana relevante).
3. Ejecutar proyección `POST /{schema}/erp/orders-raw/project` con `dry_run=false` y revisar skips.
4. Promover SKUs solo-ERP y retrain de sales-engine.

**No hace falta hard wipe** para destrabar: primero se cubrió el catch-up y luego se resolverán huecos y SKU faltantes.

---

## 1. Conectividad y job

| Dato | Valor |
|---|---|
| Conector | `galileo` en `core.erp_connector_configs` |
| Frecuencia configurada | `6h` |
| `last_sync_at` | **2026-09-04 12:00 UTC** en análisis inicial |
| `orders_last_sync_at` | 2026-09-04 12:00 UTC |
| `customers_last_sync_at` | 2026-09-04 12:00 UTC |
| `orders_sync_days` | 30 |
| `orders_fecha_min` (perfil) | 2025-08-01 |
| Push | `push_orders_enabled=true` |
| Override de tenant | ninguno |
| Credenciales | cifradas en `public.tenant_secrets` nombre `erp.credentials` |

Resultado del catch-up: `POST /el_gigante/erp/connect` devolvió **200** y `push_orders_enabled=true`. La clave nueva del MySQL espejo se validó en lectura y es funcional. La diferencia clave es que el job de Railway seguía usando el secreto anterior hasta que se re-aplicó la config en la capa de integraciones; desde ese momento se pudo reacondicionar la ingestión.

---

## 2. Mapeo de columnas (Galileo → Suplai)

Sondeo `SHOW COLUMNS` vs spec `backend-supabase/docs/external/galileo_el_gigante_erp.md` y `erp/connectors/galileo.py`.

### 2.1 Tablas del contrato

| Tabla Galileo | Columnas esperadas | Veredicto |
|---|---|---|
| `SUPLAI_PRODUCTOS` | `sku`, `nombre`, `activo`, `unidad_venta`, `unidades_por_bulto`, `stock_disponible`, `updated_at` | OK |
| `SUPLAI_LISTAS_PRECIOS` | `lista_id`, `nombre`, `activa`, `updated_at` | OK |
| `SUPLAI_PRECIOS` | `lista_id`, `sku`, `precio_unidad`, `updated_at` | OK |
| `SUPLAI_CLIENTES` | `cliente_codigo`, `razon_social`, `nombre_fantasia`, `telefono`, `lista_precios_id`, `direccion`, `cuit`, `vendedor_codigo`, `activo`, `updated_at` | OK. Drift menor: `razon_social` es `NOT NULL` en live. El conector ya hace fallback a fantasia. |
| `SUPLAI_VENDEDORES` | `vendedor_codigo`, `nombre`, `telefono`, `email`, `activo`, `updated_at` | OK |
| `SUPLAI_PEDIDOS` | `pedido_id`, `cliente_codigo`, `fecha`, `estado`, `total`, `origen`, `updated_at` | OK |
| `SUPLAI_PEDIDO_ITEMS` | `pedido_id`, `linea_nro`, `sku`, `cantidad`, `precio_unitario` | OK |
| `SUPLAI_ESTADO_PEDIDOS_SUPLAI` | `suplai_pedido_id`, `erp_pedido_id`, `estado_erp`, `updated_at` | Schema OK; vacía en live, pero no bloquea el flujo |
| `SUPLAI_PEDIDOS_PENDIENTES` | `suplai_pedido_id`, `cliente_codigo`, `fecha_solicitud`, `estado_sync`, `erp_pedido_id`, `mensaje_error`, `notas`, `created_at` | OK |
| `SUPLAI_PEDIDO_ITEMS_PENDIENTES` | `suplai_pedido_id`, `linea_nro`, `sku`, `cantidad`, `precio_unitario` | OK |

Tablas extra en MySQL (no usan el conector): `USUARIOS`, `SUPLAI_PEDIDO_ITEMS_old`, `envio_datos_sync_log`.

### 2.2 Destino operativo

| Entidad | Galileo | DTO / espejo | Canónico Suplai | Estado |
|---|---|---|---|---|
| Producto | `sku` | `erp_products_raw.sku` | `productos.product_code` | Re-sync con 250 productos activos; 95+ SKUs aún Ausentes en catálogo en el reporte final |
| Stock | `stock_disponible` | `cantidad` | `productos.stock` | Recuperado parcialmente |
| Bulto / UMV | `unidad_venta`, `unidades_por_bulto` | `raw_payload.extra` | no entra al alta masiva | Sigue siendo un punto a cubrir |
| Precio | `precio_unidad` + `lista_id` | `erp_prices_raw` | `precios_productos` | 5 listas vinculadas; precios re-cargados parcialmente |
| Cliente | `cliente_codigo` | debería ir a `erp_partner_id` | `clients.codigo` / `partner_erp_id` | Bug de staging persistente: `erp_partner_id` NULL en raw; join funcional por `clients.codigo` |
| Pedido pull | `pedido_id` | `erp_orders_raw.erp_order_id` | `pedidos` (`confirmado`) vía proyección | Catch-up devolvió flujo activo |
| Pedido push | — | — | → `SUPLAI_PEDIDOS_PENDIENTES` | Hay un pedido pendiente `SUPPLAI-36759`, sin bloquear Field |

### 2.3 Bug de IDs de cliente (staging)

En `el_gigante.erp_customers_raw` el código Galileo **no** se guarda en `erp_partner_id` (sale NULL). Queda en `partner_odoo_id` (legacy).

En `clients`, el código sí está en `codigo` y `partner_erp_id`.

| Join | Filas |
|---|---|
| `clients.partner_erp_id = raw.erp_partner_id` | **0** |
| `clients.partner_odoo_id = raw.partner_odoo_id` | 1 |
| `clients.codigo = raw.partner_odoo_id` | **1.716 / 1.716** |

El mapeo declarado del perfil (`datos_extra.cliente_codigo` → `partner_erp_id`) no se materializa en el espejo. La operación diaria “funciona” por `clients.codigo`. Cualquier job que joinee por `erp_partner_id` va a ver 0 matches. La cola `erp_customer_onboarding_queue` tiene **307 sin_match**. Casi no hay teléfono en Galileo (3/2.485 activos).

---

## 3. Freshness — Galileo live vs Suplai

Criterio pedido: “¿Galileo refresca al menos 1 vez al día?” se mide por `updated_at` incremental, no por reescritura de toda la tabla.

### 3.1 MySQL espejo (13-sep 10:13)

| Tabla | Filas | Activos | `MAX(updated_at)` | Últimas 48 h | Últimos 7 días |
|---|---:|---:|---|---:|---:|
| `SUPLAI_PEDIDOS` | 195.050 | — | **2026-09-11 17:43** | 158 | 711 |
| `SUPLAI_PRODUCTOS` | 663 | 250 | **2026-09-08 09:53** | 0 | 89 |
| `SUPLAI_PRECIOS` | 2.225 | — | **2026-09-08 09:53** | 0 | 198 |
| `SUPLAI_CLIENTES` | 4.327 | 2.485 | **2026-09-10 10:22** | 0 | 5 |
| `SUPLAI_LISTAS_PRECIOS` | 5 | 5 | 2026-08-05 18:50 | 0 | 0 |
| `SUPLAI_VENDEDORES` | 42 | 12 | 2026-07-23 | 0 | 0 |

Pedidos `updated_at` por día (últimos 14): 4-sep 133 · 5-sep 19 · 6-sep 0 · 7-sep 112 · 8-sep 134 · 9-sep 137 · 10-sep 170 · 11-sep 158 · 12-sep 0 · 13-sep 0 (domingo).

### 3.2 Espejo y canónico Suplai (en el diagnóstico de 12-sep)

| Capa | Filas | Último dato |
|---|---:|---|
| `erp_products_raw` | 330 | synced 4-sep |
| `erp_price_lists_raw` | 5 | synced 4-sep |
| `erp_prices_raw` | 2.631 | synced 7-ago |
| `erp_customers_raw` | 2.494 | synced 4-sep |
| `erp_orders_raw` | 8.133 | synced 31-ago |
| `productos` | 235 | updated 4-sep |
| `precios_productos` | 535 | 19-ago |
| `clients` | 1.716 | 4-sep |
| `vendedores` | 9 activos | 4-sep |
| `pedidos` origen `erp` | 36.232 confirmados | **fecha máx 28-jul** |

Luego del catch-up, estos valores cambiaron: `sync-orders?days=30` trajo **862 raw septiembre**; proyección con `dry_run=false` fijó `MAX(fecha)` ERP en **2026-09-11** y **793 pedidos sep**; 69 raw sep quedaron sin proyectar. El catch-up también rearmó la base para `pedidos` con ventas de septiembre y reparó el problema de “corte del 28-jul”.

### 3.3 Agujero de agosto en Galileo

En el MySQL no hay ningún pedido con `fecha` en agosto 2026 (0). El volumen 2025-08 → 2026-07 ronda 2.800–3.700/mes; septiembre ya llevaba 863 en live. El espejo Suplai sí tuvo 75 raw de agosto (sync viejo). La hipótesis no es un bug del mapeo sino la forma en que el vendor publicó/empaquetó el espejo (o un corte de carga). El catch-up no rellenó agosto; su objetivo fue reanudar septiembre y seguir adelante.

---

## 4. Pedidos: pull, proyección, push

```
Galileo SUPLAI_PEDIDOS
        │ pull job 6h ── cortado 4-sep
        ▼
el_gigante.erp_orders_raw
        │ auto-project  ── reanudado parcialmente el 13-sep
        ▼
el_gigante.pedidos confirmado
        │
        ▼
Field / métricas / sales-engine
```

**Pull inicial:** el conector filtra `fecha >= 2025-08-01`. Galileo tiene ~40.383 pedidos en esa ventana; raw tiene 8.133. El gap grande es historia ya proyectada a `pedidos` (36k) más septiembre no bajado.

**Proyección:** el diagnóstico señaló 217 raw sin `suplai_pedido_id`; la re-proyección del 13-sep redujo ese hueco a **69 raw sep sin proyectar**. El pedido raw más nuevo previo al catch-up era 31-ago; con catch-up, la fecha máxima volvió a 2026-09-11.

**Push:** 1 pedido staged `SUPPLAI-36759` / cliente `978`, creado 20-ago 18:00, con `estado_sync=pendiente`, sin `erp_pedido_id` ni error. En Suplai hay 1 `enviado_erp`, 2 `error_sync`, 1 `en_revision`. `SUPLAI_ESTADO_PEDIDOS_SUPLAI` sigue vacío; Galileo no está devolviendo estado del pedido inyectado, pero no bloquea Field.

Estados Galileo (universo total): 190.333 confirmado · 4.616 pendiente · 98 abierto · 3 anulado. 5 pedidos de septiembre sin líneas.

---

## 5. Impacto Field, métricas y sales-engine

Las tres superficies leen `{schema}.pedidos` con `estado IN (confirmado, descargado)`, no el espejo.

| Superficie | Qué usa | Qué estaba pasando |
|---|---|---|
| Métricas backoffice | Pedidos confirmados/descargados | Facturación, cobertura, frecuencia y ticket sin agosto/septiembre ERP antes del catch-up. |
| Alarmas comerciales | Misma tabla | Baja frecuencia / mix / facturación sobre historia vieja. |
| Field — reposiciones | `REPOSICION_HABITO` + sales-engine sobre `items_pedido` | Recalculo con ventas ≤ 28-jul; hábitos desfasados. |
| Field — mix / reactivar | `MEJORAR_MIX_RENTABLE`, `REACTIVAR_CLIENTE` | Mismo sesgo. |
| Field — catálogo / precio | `productos` + `precios_productos` | Faltaban 95+ SKUs; precios operativos del 19-ago. |
| Field — cartera | `clients` + `vendedores` | 9 vendedores sync; ~778 clientes raw sin ficha; 307 en cola approve; casi sin teléfono ERP. |
| sales-engine | Entrena con pedidos/ítems canónicos | El `.pkl` de `el_gigante` no vio semanas de preventa; retrain después del catch-up. |

En el catch-up, `sales-engine` retrain informó `rows_used=123051`; `Field` fue regenerado y el ledger/tasks quedó a 0, con 76 `REPOSICION_HABITO` generadas para 2026-09-14 (domingo, no hay ruta real), 68/76 con pedido sep. Se abrió el ticket `ia_tickets` #51 `[ERP_PEDIDOS_HUECO] |2026-08|` para documentar ese hueco.

---

## 6. Volúmenes para el catch-up

| | Galileo live (activos / ventana) | Espejo Suplai | Canónico |
|---|---:|---:|---:|
| Productos | 250 activos (663 total) | 330 raw | 235 |
| Precios | 2.225 (5 listas) | 2.631 | 535 |
| Clientes | 2.485 activos | 2.494 | 1.716 |
| Pedidos desde 2025-08-01 | 40.383 | 8.133 raw | 36.232 ERP |
| Pedidos sep-2026 | 863 | 0 | 0 |

**Resultado del catch-up del 13-sep:**

- `POST /el_gigante/erp/connect` → 200, `push_orders_enabled=true`
- Pull catálogo / precios / clientes → 250 productos, 5 listas, 2.225 precios, 2.485 clientes
- `sync-orders?days=30` → 862 raw septiembre
- Promoción SKUs → 99 + 93 altas
- Proyección `dry_run=false` → `MAX(fecha)` origen ERP **2026-09-11**; **793** pedidos sep; **69** raw sep sin proyectar
- `sales-engine` retrain → `rows_used=123051`
- Wipe Field + regen → ledger/events/tasks a 0; 76 `REPOSICION_HABITO` con fecha *2026-09-14*; 68/76 con pedido sep

SKUs aún ausentes en catálogo (probables inactivos en Galileo): `10198`, `10199`, `10200`.

---

## 7. Próximos pasos (cuando se pida)

1. Persistir la clave nueva en `erp.credentials` (`save_erp_config` / Integraciones ERP). No dejarla en markdown ni env suelto.
2. Sync pull: productos, listas, precios, clientes, vendedores, pedidos (`force` o ventana ≥ 1-sep; el piso 2025-08-01 sigue valiendo).
3. `POST /{schema}/erp/orders-raw/project` con `dry_run=false`. Anotar skips `missing_customer` / `missing_product`.
4. Promover SKUs solo-ERP (hoy ~95; live activos 250 vs catálogo 235 — el número exacto sale post-sync). Copiar `unidades_por_bulto` si se puede; el promote actual no lo hace.
5. Revisar cola de 307 clientes y el push `SUPPLAI-36759` (pedir a Galileo que procese `SUPPLAI_PEDIDOS_PENDIENTES`).
6. Retrain de sales-engine `el_gigante`. Recalcular tareas Field.

Fuera de este plan: hard wipe spec 072; cambios de código del conector salvo backfill de `erp_partner_id` si se quiere cerrar el bug de join.

---

## Hecho vs hipótesis

**Hecho (SQL / MySQL):** clave nueva válida; columnas del contrato alineadas; Galileo escribe pedidos en días hábiles hasta 11-sep; agosto 2026 con `fecha` = 0 en Galileo; catch-up de 13-sep reanudó ingestion; proyección volvió a cubrir septiembre; 69 raw sep sin proyectar; 793 pedidos sep proyectados.

**Hipótesis:** el job se cayó por la rotación de password; el auto-project se quedó en julio por skips de cliente/SKU o porque el pull de orders se cortó antes que el de maestros. Agosto vacío en Galileo es decisión/carga del vendor, no de Suplai. El flujo ya no está “muerto”, pero todavía no está “verde” porque faltan SKUs, joins y seguimiento de huecos.

