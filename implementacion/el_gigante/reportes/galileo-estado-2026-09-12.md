# El Gigante — estado integración Galileo

**Tenant:** `el_gigante` (`965a6919-7967-4f3b-93bd-2b468b3ccb2e`)  
**Fecha del reporte:** 12-sep-2026 (sondeo MySQL live: 13-sep-2026 10:13 hora del servidor espejo)  
**Alcance:** diagnóstico + prueba de lectura al MySQL espejo. No se actualizó `erp.credentials` ni se disparó sync.

---

## Resumen ejecutivo

**Semáforo: rojo.** Galileo está vivo y la contraseña nueva **funciona**. El corte está del lado Suplai: el job de pull no corre desde el **4-sep** y los pedidos canónicos (los que miran Field, métricas y sales-engine) están cortados el **28-jul**.

| Pregunta | Respuesta |
|---|---|
| ¿La clave nueva entra al MySQL espejo? | Sí. Host `srv561.hstgr.io:3306`, DB `u606379220_gigan_suplai`. |
| ¿El mapeo de columnas es correcto? | Sí, las tablas `SUPLAI_*` coinciden con spec y conector. Drift menor abajo. |
| ¿Galileo actualiza al menos 1 vez al día? | **Pedidos sí** en días hábiles (último `updated_at` 11-sep). Productos/precios a saltos (último 8-sep). Clientes puntual (último 10-sep). Listas/vendedores no. |
| ¿Suplai está al día? | No. Último job 4-sep. Pedidos canónicos ERP hasta 28-jul. |
| ¿Se proyectan los pedidos al canónico? | No desde julio. 217 filas en `erp_orders_raw` sin `suplai_pedido_id` (75 de agosto). |

Tres acciones para apurar (no ejecutadas en este turno):

1. Guardar la clave nueva en `public.tenant_secrets` (`erp.credentials`) vía `save_erp_config` y disparar sync productos / precios / clientes / pedidos.
2. Proyectar `erp_orders_raw` → `pedidos` (`POST /erp/orders-raw/project`, `dry_run=false`) y revisar los 217 sin proyectar.
3. Promover los ~95 SKUs solo-ERP, luego retrain de sales-engine tenant `el_gigante`.

Hard wipe (spec 072) **no** hace falta para destrabar. Primero catch-up.

---

## 1. Conectividad y job

| Dato | Valor |
|---|---|
| Conector | `galileo` en `core.erp_connector_configs` |
| Frecuencia configurada | `6h` |
| `last_sync_at` | **2026-09-04 12:00 UTC** |
| `orders_last_sync_at` | 2026-09-04 12:00 UTC |
| `customers_last_sync_at` | 2026-09-04 12:00 UTC |
| `orders_sync_days` | 30 |
| `orders_fecha_min` (perfil) | 2025-08-01 |
| Push | `push_orders_enabled=true` |
| Override de tenant | ninguno (`erp_tenant_profiles` vacío) |
| Credenciales | cifradas en `public.tenant_secrets` nombre `erp.credentials` — **siguen siendo las viejas** |

La clave nueva se probó solo en lectura. Hasta que alguien la persista en el secreto, el job de Railway va a seguir fallando o usando la clave anterior.

---

## 2. Mapeo de columnas (Galileo → Suplai)

Sondeo `SHOW COLUMNS` vs spec `backend-supabase/docs/external/galileo_el_gigante_erp.md` y `erp/connectors/galileo.py`.

### 2.1 Tablas del contrato

| Tabla Galileo | Columnas esperadas | Veredicto |
|---|---|---|
| `SUPLAI_PRODUCTOS` | `sku`, `nombre`, `activo`, `unidad_venta`, `unidades_por_bulto`, `stock_disponible`, `updated_at` | OK |
| `SUPLAI_LISTAS_PRECIOS` | `lista_id`, `nombre`, `activa`, `updated_at` | OK |
| `SUPLAI_PRECIOS` | `lista_id`, `sku`, `precio_unidad`, `updated_at` | OK |
| `SUPLAI_CLIENTES` | `cliente_codigo`, `razon_social`, `nombre_fantasia`, `telefono`, `lista_precios_id`, `direccion`, `cuit`, `vendedor_codigo`, `activo`, `updated_at` | OK. Drift: `razon_social` es `NOT NULL` en live (spec decía nullable). El conector ya hace fallback a fantasia. |
| `SUPLAI_VENDEDORES` | `vendedor_codigo`, `nombre`, `telefono`, `email`, `activo`, `updated_at` | OK |
| `SUPLAI_PEDIDOS` | `pedido_id`, `cliente_codigo`, `fecha`, `estado`, `total`, `origen`, `updated_at` | OK |
| `SUPLAI_PEDIDO_ITEMS` | `pedido_id`, `linea_nro`, `sku`, `cantidad`, `precio_unitario` | OK |
| `SUPLAI_ESTADO_PEDIDOS_SUPLAI` | `suplai_pedido_id`, `erp_pedido_id`, `estado_erp`, `updated_at` | Schema OK, **0 filas** |
| `SUPLAI_PEDIDOS_PENDIENTES` | `suplai_pedido_id`, `cliente_codigo`, `fecha_solicitud`, `estado_sync`, `erp_pedido_id`, `mensaje_error`, `notas`, `created_at` | OK |
| `SUPLAI_PEDIDO_ITEMS_PENDIENTES` | `suplai_pedido_id`, `linea_nro`, `sku`, `cantidad`, `precio_unitario` | OK |

Tablas extra en el MySQL (no las usa el conector; no rompen el mapeo): `USUARIOS`, `SUPLAI_PEDIDO_ITEMS_old` (0 filas), `envio_datos_sync_log` (0 filas).

### 2.2 Destino operativo

| Entidad | Galileo | DTO / espejo | Canónico Suplai | Estado |
|---|---|---|---|---|
| Producto | `sku` | `erp_products_raw.sku` | `productos.product_code` | 235 en ambos; **95 solo ERP** (espejo 330 vs 250 activos live — el raw no baja inactivos) |
| Stock | `stock_disponible` | `cantidad` | `productos.stock` (UPDATE si el SKU ya existe) | Congelado al 4-sep |
| Bulto / UMV | `unidad_venta`, `unidades_por_bulto` | `raw_payload.extra` | **no entra al alta masiva** | Si se promueven SKUs, hay que copiar bulto a mano o extender promote |
| Precio | `precio_unidad` + `lista_id` | `erp_prices_raw` | `precios_productos` si la lista tiene `erp_list_id` | 5 listas vinculadas (`1`–`4`, `5` = Precio sin IVA). Raw de precios: 7-ago |
| Cliente | `cliente_codigo` | debería ir a `erp_partner_id` | `clients.codigo` / `partner_erp_id` | **Bug de staging** (abajo) |
| Pedido pull | `pedido_id` | `erp_orders_raw.erp_order_id` | `pedidos` (`confirmado`) vía proyección | Auto-project muerto post 28-jul |
| Pedido push | — | — | → `SUPLAI_PEDIDOS_PENDIENTES` | 1 fila `pendiente` desde el 20-ago (`SUPPLAI-36759`). Galileo no la ingirió |

### 2.3 Bug de IDs de cliente (staging)

En `el_gigante.erp_customers_raw` el código Galileo **no** se guarda en `erp_partner_id` (sale NULL). Queda en `partner_odoo_id` (columna legacy).

En `clients` el código sí está en `codigo` y `partner_erp_id`.

| Join | Filas |
|---|---|
| `clients.partner_erp_id = raw.erp_partner_id` | **0** |
| `clients.partner_odoo_id = raw.partner_odoo_id` | 1 |
| `clients.codigo = raw.partner_odoo_id` | **1.716 / 1.716** clients |

El mapeo declarado del perfil (`datos_extra.cliente_codigo` → `partner_erp_id`) no se materializa en el espejo. La operación diaria “funciona” por `clients.codigo`. Cualquier job que joinee por `erp_partner_id` va a ver 0 matches. La cola `erp_customer_onboarding_queue` tiene **307** `sin_match` (varias con `erp_partner_id` NULL).

Casi no hay teléfono en Galileo: **3 de 2.485** clientes activos tienen `telefono`. Field / agente no van a matchear WhatsApp desde el ERP.

---

## 3. Freshness — Galileo live vs Suplai

Criterio pedido: “¿Galileo refresca al menos 1 vez al día?” se mide por `updated_at` **incremental**, no por reescritura de toda la tabla.

### 3.1 MySQL espejo (13-sep 10:13)

| Tabla | Filas | Activos | `MAX(updated_at)` | Últimas 48 h | Últimos 7 días |
|---|---:|---:|---|---:|---:|
| `SUPLAI_PEDIDOS` | 195.050 | — | **2026-09-11 17:43** | 158 | 711 |
| `SUPLAI_PEDIDO_ITEMS` | 584.806 | — | (sin `updated_at`) | — | — |
| `SUPLAI_PRODUCTOS` | 663 | 250 | **2026-09-08 09:53** | 0 | 89 |
| `SUPLAI_PRECIOS` | 2.225 | — | **2026-09-08 09:53** | 0 | 198 |
| `SUPLAI_CLIENTES` | 4.327 | 2.485 | **2026-09-10 10:22** | 0 | 5 |
| `SUPLAI_LISTAS_PRECIOS` | 5 | 5 | 2026-08-05 18:50 | 0 | 0 |
| `SUPLAI_VENDEDORES` | 42 | 12 | 2026-07-23 | 0 | 0 |

Pedidos `updated_at` por día (últimos 14): 4-sep 133 · 5-sep 19 · **6-sep 0 (sábado)** · 7-sep 112 · 8-sep 134 · 9-sep 137 · 10-sep 170 · 11-sep 158 · **12-sep 0 (sábado)**.

**Veredicto frecuencia:** el agente Galileo escribe pedidos casi todos los días hábiles. El 12-sep (sábado) y el 13-sep (domingo, mañana) sin movimientos es coherente con operación comercial. Productos y precios no son diarios; último lote el **8-sep**. Listas de precio y vendedores no se tocan seguido.

### 3.2 Espejo y canónico Suplai (12-sep)

| Capa | Filas | Último dato |
|---|---:|---|
| `erp_products_raw` | 330 | synced 4-sep |
| `erp_price_lists_raw` | 5 | synced 4-sep |
| `erp_prices_raw` | 2.631 | **synced 7-ago** |
| `erp_customers_raw` | 2.494 | synced 4-sep |
| `erp_orders_raw` | 8.133 | **synced 31-ago** (`max fecha_pedido` 31-ago) |
| `productos` | 235 (todos en catálogo, 0 mock) | updated 4-sep |
| `precios_productos` | 535 | **19-ago** |
| `clients` | 1.716 (1.370 con `partner_erp_id`) | 4-sep |
| `vendedores` | 9 activos, todos con `erp_codigo` | 4-sep |
| `pedidos` origen `erp` | 36.232 confirmados | **`fecha` máx 28-jul-2026** |
| `pedidos` ago–sep | 4 | todos origen `suplai` (4-sep, 6-sep, 8-sep + 1 de ago) |

Galileo live tiene **863 pedidos con `fecha` en septiembre 2026**, todos `origen=preventa`. Suplai no tiene ninguno de esos en `pedidos` ni en raw posterior al 31-ago.

### 3.3 Agujero de agosto en Galileo

En el MySQL **no hay ningún pedido con `fecha` en agosto 2026** (0). El volumen 2025-08 → 2026-07 ronda 2.800–3.700/mes; septiembre ya lleva 863 (4–11 sep). El espejo Suplai sí tiene 75 raw de agosto (sync viejo). Hipótesis: el espejo Galileo se reconstruyó o no publicó agosto. No es un bug del mapeo.

---

## 4. Pedidos: pull, proyección, push

```
Galileo SUPLAI_PEDIDOS (195k; 39.5k desde 2025-08-01 + 863 sep)
        │ pull job 6h  ── cortado 4-sep; orders raw se quedó el 31-ago
        ▼
el_gigante.erp_orders_raw (8.133; 217 sin proyectar)
        │ auto-project  ── no escribe desde el 28-jul
        ▼
el_gigante.pedidos confirmado (36.232 ERP + 4 suplai)
        │
        ▼
Field / métricas / sales-engine
```

**Pull:** el conector filtra `fecha >= 2025-08-01`. Galileo tiene ~40.383 pedidos en esa ventana; raw tiene 8.133. El gap grande es historia ya proyectada a `pedidos` (los 36k) más septiembre no bajado.

**Proyección:** 217 raw sin `suplai_pedido_id`. El pedido raw más nuevo (31-ago, id `5ff26074e204c43-8649`) tampoco está proyectado. Los canónicos ERP terminan el 28-jul. Field y el dashboard **no** leen `erp_orders_raw`.

**Push:** 1 pedido staged `SUPPLAI-36759` / cliente `978`, creado 20-ago 18:00, `estado_sync=pendiente`, sin `erp_pedido_id` ni error. Ítems: SKU 10021×3, 10024×2, 281×5. En Suplai hay 1 `enviado_erp`, 2 `error_sync`, 1 `en_revision`. `SUPLAI_ESTADO_PEDIDOS_SUPLAI` está vacía: Galileo no está devolviendo estado de lo inyectado.

Estados Galileo (universo total): 190.333 confirmado · 4.616 pendiente · 98 abierto · 3 anulado. 5 pedidos de septiembre sin líneas.

---

## 5. Impacto Field, métricas y sales-engine

Las tres superficies leen `{schema}.pedidos` con `estado IN (confirmado, descargado)`, no el espejo.

| Superficie | Qué usa | Qué está pasando |
|---|---|---|
| Métricas backoffice | Pedidos confirmados/descargados | Facturación, cobertura, frecuencia y ticket **sin agosto ni septiembre ERP**. El último mes “lleno” es julio. |
| Alarmas comerciales | Misma tabla | Baja frecuencia / mix / facturación sobre historia vieja. Falsos “cliente frío” si compraron en sep. |
| Field — reposiciones | `REPOSICION_HABITO` + sales-engine sobre `items_pedido` | 2.777 `field_tasks` (último update 11-sep) se recalculan sobre ventas ≤ 28-jul. Hábitos desfasados. |
| Field — mix / reactivar | `MEJORAR_MIX_RENTABLE`, `REACTIVAR_CLIENTE` | Mismo sesgo. 1 objetivo cargado. |
| Field — catálogo / precio | `productos` + `precios_productos` | 95 SKUs Galileo no existen. Precios operativos del **19-ago**; Galileo tocó 198 precios el 8-sep. |
| Field — cartera | `clients` + `vendedores` | 9 vendedores sync (Galileo tiene 12 activos; el conector excluye los sin pedidos post-floor). ~778 clientes raw sin ficha. 307 en cola approve. Casi sin teléfono ERP. |
| sales-engine | Entrena con pedidos/ítems canónicos | El `.pkl` de `el_gigante` no vio ~6 semanas de preventa. Retrain **después** del catch-up, no antes. |

`items_pedido`: 115.450 filas, `max(fecha_pedido)` 8-sep — esa cola es de los 4 pedidos origen `suplai`, no del ERP.

---

## 6. Volúmenes para el catch-up

| | Galileo live (activos / ventana) | Espejo Suplai | Canónico |
|---|---:|---:|---:|
| Productos | 250 activos (663 total) | 330 raw | 235 |
| Precios | 2.225 (5 listas) | 2.631 | 535 |
| Clientes | 2.485 activos | 2.494 | 1.716 |
| Pedidos desde 2025-08-01 | 40.383 | 8.133 raw | 36.232 ERP |
| Pedidos sep-2026 | 863 | 0 | 0 |

---

## 7. Próximos pasos (cuando se pida)

1. Persistir la clave nueva en `erp.credentials` (`save_erp_config` / Integraciones ERP). No dejarla en markdown ni env suelto.
2. Sync pull: productos, listas, precios, clientes, vendedores, pedidos (`force` o ventana ≥ 1-sep; el piso 2025-08-01 sigue valiendo).
3. `POST /{schema}/erp/orders-raw/project` con `dry_run=false`. Anotar skips `missing_customer` / `missing_product`.
4. Promover SKUs solo-ERP (hoy ~95; live activos 250 vs catálogo 235 — el número exacto sale post-sync). Copiar `unidades_por_bulto` si se puede; el promote actual no lo hace.
5. Revisar cola de 307 clientes y el push `SUPPLAI-36759` (pedir a Galileo que procese `SUPLAI_PEDIDOS_PENDIENTES`).
6. Retrain sales-engine `el_gigante`. Recalcular tareas Field.

Fuera de este plan: hard wipe spec 072; cambios de código del conector (salvo el backfill de `erp_partner_id` si se quiere cerrar el bug de join).

---

## Hecho vs hipótesis

**Hecho (SQL / MySQL):** clave nueva válida; columnas del contrato alineadas; Galileo escribe pedidos en días hábiles hasta el 11-sep; agosto-2026 con `fecha` = 0 en Galileo; job Suplai 4-sep; canónico ERP 28-jul; 217 raw sin proyectar.

**Hipótesis:** el job se cayó por la rotación de password (no se leyó el secreto viejo ni logs de Railway en este turno). El auto-project dejó de escribir en julio por skips de cliente/SKU o porque el pull de orders se cortó antes que el de maestros. Agosto vacío en Galileo es decisión/carga del vendor, no de Suplai.
