# Almaro — reporte de implementación

**Tenant:** `almaro` (`98f02431-a66f-40bf-9551-9bf66faf204d`)  
**Fecha:** 2026-09-17  
**Fuente:** Supabase producción + conector GEV (sin rama nueva)  
**Path:** `implementacion/almaro/`

Ventana de sync GEV (UTC): espejo productos/precios `2026-09-17 12:00`, clientes `12:01`. Job de precios/stock a `productos` cada 6 h (`last_sync_at` 06:00).

---

## Veredictos

| # | Pregunta | Estado |
|---|----------|--------|
| 1 | Precios y stock por API GEV nueva | **Sí, operativos** (con matices) |
| 2 | Unidades (bulto/caja/display) desde GEV | **No.** GEV no nos da UMV usable. Gonzales sí, para el overlap |
| 3 | Clientes por Excel + lista de precios por API | **Excel no cargado.** La lista GEV **sí** viene en la API |
| 4 | E2E con la distribuidora | **Todavía no** (WhatsApp sí está; faltan clientes reales, prompt Almaro y UMV) |

---

## 1. Sync GEV — precios y stock

**Conector:** `gev` · `https://almaro-api.dns-xionico.com/api` · `id_vendedor` 1463 · push de pedidos **apagado**.

| Espejo / tabla | Count (hoy) |
|---|---:|
| `erp_products_raw` | 3244 |
| `erp_prices_raw` | 51517 |
| `erp_price_lists_raw` | 16 |
| `productos` | 3300 (943 mock Gonzales + 2357 altas GEV) |
| `listas_precios` | 21 (5 mock sin `erp_list_id` + 16 GEV) |
| `precios_productos` | 54992 |
| SKUs con stock > 0 | 999 |
| Filas de precio GEV sin producto en catálogo | 297 (igual que el 16-sep) |

**Qué está bien**

- El job periódico pega a la API nueva (`X-API-Key`) y persiste stock + precios.
- Precio GEV = `PRECIO_NETO_SIN_IMPUESTOS × 1.21` (IVA AR). Cruce SKU `1002` lista `06` TRADICIONAL: crudo = persistido (`770.37…`).
- Las 16 listas GEV están linkeadas (`erp_list_id`: `06` TRADICIONAL, `01` TRADICIONAL CADENIZA, `LP` SUPERMERCADO, etc.).
- Stock del espejo de las 12:00 está alineado en ~2981/3244 SKUs. Los ~263 desfasajes son esperables: el espejo se refresca al mediodía y `productos.stock` se escribe en el ciclo 6 h (06:00).

**Matices**

- Siguen las **listas mock 1–4** (precios clonados de Gonzales ERP_01). Un PdV en lista 1 no ve precio Almaro. Ejemplo `1009` Rocklets: lista mock 1 ≈ `$20.616` vs GEV TRADICIONAL ≈ `$729`.
- `default_lista_precios` del tenant sigue en **1** (mock).
- Decimales sucios por el ×1.21 (ej. `770.370337`). No rompe sync; sí ensucia cotización.
- Productos mock **no se purgaron**. Overlap mock ∩ GEV conserva nombre/UMV de Gonzales y recibe stock/precio GEV en las listas 6–21.

---

## 2. Unidades de medida (bulto, caja, display)

**La API GEV que consumimos no trae UMV.** El conector solo mapea `CODIGO_ARTICULO`, `DESCRIPCION_ARTICULO`, `STOCK`. El espejo `erp_products_raw.raw_payload` queda `{sku, nombre, cantidad}`. Igual en Gonzales.

Al promover SKUs nuevos, el backend pone default:

- `unidad_minima_de_venta = 'unidades'`
- `umv_tipo = 'unidad'`
- `unidades_por_bulto = 1`

| Origen | n | UMV real |
|---|---:|---|
| Mock clon Gonzales (`is_mock=true`) | 943 | UNIDAD / DISPLAY / BULTO + pack (12, 24, 120…) |
| Altas GEV (`is_mock=false`) | 2357 | **todas** `unidades` × 1 |

**Gonzales como referencia: sí, para el overlap.**

- 1025 SKUs Almaro existen también en `gonzales.productos`.
- 942 ya tienen la misma UMV+pack (casi todo el mock).
- **82 altas GEV** están en Gonzales con pack real y en Almaro quedaron en 1. Ejemplos:
  - `14230` CH TOP LINE → Gonzales DISPLAY ×480 vs Almaro unidades ×1
  - `15388` BONOBON DUBAI → DISPLAY ×288 vs ×1
  - `15073` ROCKLETS P. BUTTER → DISPLAY ×216 vs ×1

El **nombre GEV** suele traer el pack (`12X24X20 GRS`, `6X20X26G`) pero **no lo parseamos**. No hay campo `CAJA`/`BULTO` persistido.

**Conclusión:** no se pueden cargar bulto/caja desde la API actual. Camino práctico: copiar UMV de Gonzales en los ~1025 SKUs comunes + parsear `NxN` del nombre para el resto, o pedir a IT GEV un campo de UOM si existe y no lo estamos leyendo.

---

## 3. Clientes Excel + lista de precios por API

**El Excel de clientes reales no está cargado.**  
`implementacion/almaro/inputs/` no tiene xlsx/csv de PdVs. En este turno no llegó archivo adjunto.

Lo que hay en `almaro.clients`: **24 PdVs mock** de Fase 4 (ChocoRincón, Golosinas del Barrio, etc.), listas **1–4**, `is_mock=true`. Cero cliente `suplai-platform-test`.

**La API sí trae la lista de cada cliente.** `getClientes` → `ID_LISTA_PRECIO`. Hoy en espejo:

| Dato | n |
|---|---:|
| `erp_customers_raw` | 2452 |
| Con `lista_precios_erp_id` | **2452 / 2452** |
| Matchean una lista GEV ya linkeada | **2452 / 2452** |
| Con teléfono usable | **79** |
| Flag `phone_missing` | 2373 |
| Alta en `clients` / cola onboarding | 0 |

Distribución de listas GEV en clientes:

| `erp_list_id` | Lista Suplai | n |
|---|---|---:|
| `06` | TRADICIONAL (id 20) | 1807 |
| `07` | INTERIOR (id 10) | 336 |
| `01` | TRADICIONAL CADENIZA (id 21) | 122 |
| `02` | AUTOSERV Y ORIENTALE (id 7) | 95 |
| `LP` | SUPERMERCADO (id 19) | 44 |
| `99` / `91` / `PETRO` / `05` | resto | 48 |

El Excel hace falta sobre todo por **teléfono WhatsApp** (GEV casi no lo trae). Cruce propuesto: código cuenta / CUIT / nombre del Excel → `erp_customers_raw` → `lista_precios_erp_id` → `listas_precios.erp_list_id`.

Vendedores: 50 (2 mock + 48 con `erp_codigo` GEV). No están atados a los 24 PdVs mock.

---

## 4. ¿E2E con la distribuidora?

**No estamos en condiciones de una prueba conjunta seria** (mensajes reales + plantilla + pedido de punta a punta con ellos). WhatsApp del tenant **sí está provisionado**.

| Pieza | Estado |
|---|---|
| Número agente | `5493795151208` (prefijo 379 Corrientes) |
| Secretos WABA | `whatsapp.long_live_token`, `phone_id`, `waba`, client id/secret |
| Plantillas locales | 4 genéricas Suplai (`suplai_global_*` holiday/weather). Ninguna Almaro |
| `create_order` | habilitada (opt-out) |
| Prompt en BD | **Tato / Córdoba / Suplai Sales Distribution** — no Maro/Almaro. Fase **01.3 pendiente** |
| Lista default | **1 (mock Gonzales)** |
| Clientes reales + teléfono | no |
| Pedidos reales | 0 (72 mock) |
| Conversaciones | 25 / ~111 eventos, casi todos mock Fase 7 |
| Inyección pedido a GEV | `push_orders_enabled=false` |
| UMV GEV | incorrecta en 2357 SKUs |
| Fase 9 E2E | pendiente |

Si mandamos un mensaje hoy, el agente se presenta como Tato de Córdoba, cotiza por lista mock si el PdV no está en una lista GEV, y trata las altas GEV como “1 unidad”.

**Mínimo antes de sentarlos a probar**

1. Aplicar prompt Almaro (JSON de 01.3, teléfono 379 ya en BD — no el 358 del JSON).
2. Cargar Excel de clientes (o 3–5 PdVs piloto) cruzando lista GEV; `default_lista_precios` → TRADICIONAL (20) o la que definan.
3. Un cliente de prueba con WhatsApp real de ellos (o el nuestro) en lista GEV.
4. Copiar UMV Gonzales al overlap y, si el piloto usa SKUs solo GEV, corregir pack a mano.
5. Plantilla de prueba aprobada en su WABA (las 4 globales pueden servir de humo; no de campaña).
6. Aclarar que el pedido queda en Suplai; **no** entra a GEV hasta encender push.

E2E interno (healthcheck + `test_agent_e2e.py`) se puede correr cuando exista `suplai-platform-test` y la lista default GEV; eso no reemplaza la prueba con la distribuidora.

---

## Orden sugerido (sin rama)

1. Excel clientes → match GEV → alta en `clients` con `lista_precios_id` GEV + teléfono.  
2. Prompt 01.3 + default lista TRADICIONAL.  
3. UMV Gonzales → overlap; sample de SKUs piloto.  
4. Prueba interna con 1 PdV.  
5. Recién ahí sesión conjunta (saludo → catálogo → pedido).  
6. Purga mock (`PURGE MOCK almaro`) **después**, no antes.

---

## Addendum — trabajo aplicado 2026-09-17 (tarde)

Snapshot anterior = estado **antes** de limpiar. Lo de abajo es el estado **después** (sin rama; `implementacion/almaro/`).

### Verificación

| Check | Resultado |
|---|---|
| Listas mock 1–4 | **0** |
| Listas restantes | **17** (Default id 5 + 16 GEV) |
| `default_lista_precios` | **20** TRADICIONAL (`erp_list_id=06`) |
| Productos `is_mock` | **0** / 3244 |
| Clientes piloto | **22** (teléfono único), todos `lista_precios_id=20` |
| Excel omitidos | **28** (`outputs/clientes-excel-omitidos.csv`) |
| Prompt | **Maro / Almaro Corrientes**; teléfono **5493795151208**; `cross_upsell` intacto |
| Plantillas UTILITY | `suplai_nuevo_pedido_vendedor_v3`, `suplai_ticket_asistencia_vendedor_v1`, `suplai_error_sistema_vendedor_v1` en `public.meta_plantillas` |
| Subscribers vendedor | **vacío** — 48 vendedores GEV tienen `telefono=erp-*`, ninguno con WhatsApp numérico |

### Artefactos

| Archivo | Contenido |
|---|---|
| `inputs/Listado Prueba WhatsApp - Septiembre 2026.xlsx` | Copia del Excel de escritorio |
| `outputs/precios-decimales-sucios.csv` | 51160 filas GEV con `precio_unidad <> ROUND(..., 2)` (no se redondeó en BD) |
| `outputs/productos-overlap-decision.csv` | 3300 SKUs: unmark 887, purga_mock_only 56, copiar_umv_gev 82, ok 2275 |
| `outputs/phase-10-purga-log.csv` | DELETE mock + listas 1–4 |
| `outputs/phase-04-clientes-piloto.csv` | 22 altas |
| `outputs/plantillas-notif-log.csv` | Provision Meta + ids |
| `scripts/aplicar_fase01_3.py` | Solo identidad/contexto |
| `scripts/provision_plantillas_sistema.py` | Enable notif + create templates + sync WABA |

### Notas operativas

- Meta aceptó el POST de las 3 UTILITY (HTTP 200). El sync del WABA todavía listó 4 nombres viejos (`hello_world` + globales); las nuevas pueden quedar PENDING hasta que Meta las apruebe.
- Notificaciones a vendedor **no van a salir** hasta cargar un número WhatsApp real en `subscribers` o en `vendedores.telefono`.
- Fuera de este trabajo: redondear precios GEV, parsear pack del nombre, push de pedidos a GEV, campaña `almaro_promo_*`, fase 9 E2E.
