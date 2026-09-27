# Rawson — integración ERP Sistel

**Tenant:** `rawson`
**Tenant id:** `cba04456-bd69-434c-b257-9e8fcf12b144`
**Fecha:** 2026-09-26
**Fuente:** `Manual Sistel API Rawson.pdf` (manual de uso para clientes e integradores, 6 páginas)

## Host y auth

| Campo | Valor |
|---|---|
| Host | `asp12.selfip.net:3448` |
| IP real | `186.123.180.126` (DNS dinámico, TTL 60 — no cablearla) |
| `base_url` | `http://asp12.selfip.net:3448` — **HTTP plano**, Sistel descartó HTTPS |
| Auth | JWT — `POST /auth/login` → `access_token` + `refresh_token` |
| Header | `Authorization: Bearer <access_token>` |
| Usuario | `SuplaiSales` |
| Contraseña | fuera de git — `implementacion/rawson/.env` (`SISTEL_PASS`) |
| Alias semilla | `raw_productos` |
| Conector Suplai | ninguno — `core.erp_connector_configs` sin fila para el tenant |

## Estado del tenant (verificado 2026-09-27)

La carga actual es la **demo agéntica** de 2026-08-21, no datos reales:

| Tabla | Filas | `is_mock` |
|---|---|---|
| `rawson.productos` | 80 | 80 — recorte de 148 del catálogo web |
| `rawson.clients` | 50 | 50 |
| `rawson.vendedores` | 3 | 3 |
| `rawson.listas_precios` | 4 | sin flag |
| `rawson.precios_productos` | 320 | sin flag |
| `rawson.pedidos` | 141 | **139** — hay 2 pedidos sin marcar |

Pasar a datos reales del ERP implica **purga previa** (Fase 10, frase `PURGE MOCK rawson`) antes de recargar Fases 1, 4 y 5. Los 2 pedidos sin `is_mock` hay que revisarlos a mano antes de purgar: o son residuo de la demo sin marcar, o tráfico real de alguna prueba con el agente.

## BLOQUEANTE — el host filtra nuestro tráfico TCP

Diagnóstico del 2026-09-27. Son **dos problemas distintos**, uno ya resuelto de nuestro lado:

### 1. DNS envenenado (resuelto en el script)

| Resolver | Respuesta |
|---|---|
| Resolver del sistema (Vodafone ES) | `208.91.112.55` — IP de parking de `selfip.net`, no es el servidor |
| DoH Google y Cloudflare | `186.123.180.126` — IP real, TTL 60 |

Coincide con lo que reportó Sistel por WhatsApp: su `ping` devolvía `186.123.180.126` y concluyeron *"algo está resolviendo mal tu cliente DNS"*. `asp12.selfip.net` es DNS dinámico con TTL 60; el resolver del ISP sirve la IP de parking.

`probe_sistel.py` ya no depende del resolver del sistema: resuelve por DoH, pega contra la IP y manda `Host: asp12.selfip.net`. Como el servicio es HTTP plano, no hay TLS que valide el nombre.

### 2. Firewall con whitelist de IP (bloqueante real)

Contra la IP correcta, desde `46.25.71.106` (Vodafone España, Valencia):

| Prueba | Resultado |
|---|---|
| `ping 186.123.180.126` | **responde** — 3/3 paquetes, 277 ms, ruta a Argentina |
| TCP `186.123.180.126:3448` | timeout |
| TCP puertos 80, 443, 8080 | timeout |
| `POST /auth/login` (IP + Host header) | timeout |

El host está vivo y enrutable — contesta ICMP — pero **descarta en silencio todo TCP**, no solo el 3448. Descarte silencioso en todos los puertos con ICMP OK es firewall con lista blanca de IP de origen, muy probablemente restringido a Argentina. Encaja con que Sistel vea el `404 Cannot GET /` del servicio desde su red y nosotros no lleguemos.

### Qué pedirle a Sistel

Bloqueante:

1. **Habilitar en el firewall la IP de salida** del implementador (`46.25.71.106`, dinámica de Vodafone: puede cambiar) y confirmar si la restricción es por IP o por geolocalización.
2. Para el sync recurrente en producción hace falta una **IP de salida fija**. Railway no garantiza egress estático en el plan actual: hay que decidir entre proxy de salida con IP fija, VPN site-to-site, o que Sistel exponga el servicio con autenticación fuerte sin whitelist.

Contrato (se pueden responder en paralelo, no bloquean la whitelist):

3. ¿La API corre en **modo simple** o **flexible**? Cambia qué rutas y filtros están permitidos (manual §4).
4. Tabla de alias `raw_*` → significado de negocio, y qué vistas existen además de `raw_productos` (clientes, vendedores, precios, listas, stock, pedidos).
5. Límite máximo de `limit` por página.
6. Si vamos a inyectar pedidos: alias y nombres de campos de `POST /operaciones/:alias` o `POST /deal`.
7. Vigencia del `access_token` y si `POST /auth/refresh` está habilitado (define si cacheamos token o relogueamos por corrida).

## Contrato de la API (resumen del manual)

| Tema | Detalle |
|---|---|
| Login | `POST /auth/login` con `{"username","password"}` (público). Devuelve `access_token`, `refresh_token`, `user`. |
| Refresh / logout | `POST /auth/refresh`, `POST /auth/logout` |
| Descubrimiento | `GET /vistas` → objeto `alias → nombre interno` |
| Lectura | `GET /vistas/:alias?page=&limit=` + filtros como query params |
| Modo simple | Filtros de **igualdad exacta** por nombre de columna; respuesta siempre `{data, pagination}` |
| Modo flexible | Texto se traduce a `LIKE '%valor%'`; exige `id` en path o filtros; suma `GET /vistas/:alias/:id` y `/vistas/:alias/search`. Llamar rutas flexibles en modo simple devuelve **400**. |
| Fechas | `<Columna>_desde` / `_hasta` (o `_from`/`_to`), o genéricos `fecha_desde`/`fecha_hasta` si el proveedor mapeó la columna. Formatos `yyyy-MM-dd`, `dd/MM/yyyy`, ISO. |
| Operaciones | `POST /operaciones/:alias` — ejecuta stored procedure; el proveedor define alias y campos |
| Pedidos | `POST /deal` o `POST /deal/:alias` — cabecera en la raíz + arreglo `items` |
| Errores | 400 params/deal inválido · 401 token vencido · 404 alias inexistente · 500 error SQL. Lista vacía `[]` no siempre es 404. |

## Plan

### Etapa 0 — desbloquear la conexión (bloqueante)

Conseguir la whitelist de IP (punto 1 de arriba). Verificación: `probe_sistel.py` imprime `[tcp] … abierto` y `[login] OK`.

Si Sistel tarda, hay dos caminos para no frenar el descubrimiento: correr el probe desde una salida en Argentina (VPN o una VM), o pedirles un volcado de `GET /vistas` y 5 filas por alias para ir armando el mapeo a ciegas.

### Etapa 1 — descubrimiento y mapeo

`python3 implementacion/rawson/scripts/probe_sistel.py`

Deja en `outputs/`:

- `erp-sistel-vistas.json` — catálogo de alias del ERP
- `erp-sistel-probe.json` — por alias: modo (simple/flexible), columnas, 3 filas de muestra, paginación

Con eso se arma la tabla de mapeo **columna ERP → campo Suplai** para productos, clientes, vendedores, listas y precios, y se decide qué vistas alimentan cada fase.

### Etapa 2 — extracción a CSV de fases

Script `scripts/extraer_sistel.py` (a escribir tras la Etapa 1): pagina cada vista con el `limit` máximo permitido y genera los CSV que ya consume el pipeline de implementación:

| Fase | CSV | Vista ERP esperada |
|---|---|---|
| 01 catálogo | `phase-01-productos.csv` | `raw_productos` |
| 01 precios | `phase-01-listas-precios.csv`, `phase-01-lista-precios-N.csv` | vista de precios / listas |
| 04 red comercial | `phase-04-vendedores.csv`, `phase-04-zonas.csv`, `phase-04-clientes.csv` | vistas de vendedores y clientes |
| 05 flags | `phase-05-clientes-flags.csv` | derivado de clientes (`partner_erp_id`, prospecto, WhatsApp) |

Revisión humana de los CSV **antes** de tocar la base (guardrail de implementación).

### Etapa 3 — purga del mock y carga real

1. `manifest.yaml`: `modo: demo` → `modo: completo`.
2. Resolver los 2 pedidos sin `is_mock` (ver estado del tenant) y después Fase 10 con la frase exacta `PURGE MOCK rawson`.
3. Recargar Fase 1 (catálogo completo, `is_mock=false`), Fase 1.1 categorías, Fase 1.2 descripciones, Fase 4 y Fase 5 desde los CSV del ERP.
4. Verificar conteos CSV vs `COUNT(*)` y actualizar `manifest.yaml`.

### Etapa 4 — conector `sistel` en el backend (opcional, posterior)

La extracción por script es una foto: no hay sync recurrente ni inyección de pedidos. Para eso hace falta un conector de producto en `backend-supabase`, que **sí requiere rama feature + PR** (es código de producto, no carga de tenant).

El conector genérico `custom_rest` no alcanza: solo acepta api_key, bearer estático o basic, y Sistel exige `POST /auth/login` para obtener el token. Hay que escribir uno nuevo.

| Paso | Archivo |
|---|---|
| Conector | `erp/connectors/sistel.py` — implementa `ERPConnector`; login JWT con cache/refresh, modelo más cercano: `cianbox.py` |
| Registro | `erp/connectors/factory.py` — rama `connector_type == "sistel"` |
| Migración | CHECK de `core.erp_connector_configs.connector` + fila en `core.erp_connector_profiles` con `capabilities` |
| Endpoint | `routers/erp.py` — sumar `"sistel"` a `allowed` de `POST /{schema}/erp/connect` |
| Credenciales | `public.tenant_secrets`, nombre `erp.credentials`, cifrado Fernet |
| Sync | APScheduler `run_erp_sync_job`, cron `*/6h` en `main.py` |

`capabilities` tentativas según lo que exponga la API (a cerrar en Etapa 1):

```json
{ "pull_products": true, "pull_prices": true, "pull_price_list_headers": true,
  "pull_customers": true, "pull_sellers": true, "pull_orders": false,
  "push_orders": false, "customer_onboarding_queue": true }
```

## Referencias

- Conectores existentes y patrón JWT: `backend-supabase/erp/connectors/cianbox.py`
- Precedente de alta ERP en un tenant: [`erp-almaro-api-xionico.md`](../../almaro/outputs/erp-almaro-api-xionico.md)
- Specs: `docs/specs/021`, `022`, `023` (aislamiento, cierre de loop, operación)
