# Rawson — integración ERP Sistel

**Tenant:** `rawson`
**Tenant id:** `cba04456-bd69-434c-b257-9e8fcf12b144`
**Fecha:** 2026-09-26
**Fuente:** `Manual Sistel API Rawson.pdf` (manual de uso para clientes e integradores, 6 páginas)

## Host y auth

| Campo | Valor |
|---|---|
| Host | `asp12.selfip.net:3448` |
| `base_url` | `http://asp12.selfip.net:3448` (esquema a confirmar: ver bloqueo) |
| Auth | JWT — `POST /auth/login` → `access_token` + `refresh_token` |
| Header | `Authorization: Bearer <access_token>` |
| Usuario | `SuplaiSales` |
| Contraseña | fuera de git — `implementacion/rawson/.env` (`SISTEL_PASS`) |
| Alias semilla | `raw_productos` |
| Conector Suplai | ninguno — `core.erp_connector_configs` sin fila para el tenant |

## Estado del tenant (2026-09-26)

La carga actual es la **demo agéntica** de 2026-08-21, no datos reales:

| Tabla | Filas | Origen |
|---|---|---|
| `rawson.productos` | 80 | mock demo (recorte de 148 del catálogo web) |
| `rawson.clients` | 50 | mock |
| `rawson.vendedores` | 3 | mock |
| `rawson.listas_precios` | 4 | mock |
| `rawson.pedidos` | 141 | mock |

Pasar a datos reales del ERP implica **purga previa** (Fase 10, frase `PURGE MOCK rawson`) antes de recargar Fases 1, 4 y 5.

## BLOQUEANTE — no hay conectividad al host

Sondeos del 2026-09-26 desde la red del implementador:

| Prueba | Resultado |
|---|---|
| `dig asp12.selfip.net` | resuelve a `208.91.112.55` |
| TCP `asp12.selfip.net:3448` | timeout (sin `connection refused`: puerto filtrado o host caído) |
| `POST http://…:3448/auth/login` | timeout a los 15 s |
| `GET https://…:3448/vistas` | timeout a los 15 s |

El puerto no rechaza la conexión, la descarta: es el patrón de **firewall con whitelist de IP** o de un **DNS dinámico desactualizado** (`selfip.net` es dominio de DNS dinámico; la IP devuelta tiene pinta de parking, no de servidor Sistel).

Hay que resolverlo con Sistel/Rawson antes de cualquier extracción. A pedir al proveedor:

1. ¿El host y puerto son correctos y el servicio está arriba ahora?
2. ¿`http` o `https` en 3448?
3. ¿Hay whitelist de IPs de origen? Si sí, habilitar la IP del implementador y la IP de salida de Railway (backend productivo) para el sync recurrente.
4. ¿La API corre en **modo simple** o **flexible**? Cambia qué rutas y filtros están permitidos (manual §4).
5. Tabla de alias `raw_*` → significado de negocio, y qué vistas existen además de `raw_productos` (clientes, vendedores, precios, listas, stock, pedidos).
6. Límite máximo de `limit` por página.
7. Si vamos a inyectar pedidos: alias y nombres de campos de `POST /operaciones/:alias` o `POST /deal`.

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

Resolver las 7 preguntas de arriba con Sistel. Verificación: `probe_sistel.py` llega a `[login] OK`.

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
2. Fase 10 con la frase exacta `PURGE MOCK rawson` (80 productos, 50 clientes, 3 vendedores, 141 pedidos mock).
3. Recargar Fase 1 (catálogo completo, `is_mock=false`), Fase 1.1 categorías, Fase 1.2 descripciones, Fase 4 y Fase 5 desde los CSV del ERP.
4. Verificar conteos CSV vs `COUNT(*)` y actualizar `manifest.yaml`.

### Etapa 4 — conector `sistel` en el backend (opcional, posterior)

La extracción por script es una foto: no hay sync recurrente ni inyección de pedidos. Para eso hace falta un conector de producto en `backend-supabase`, que **sí requiere rama feature + PR** (es código de producto, no carga de tenant):

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
