# Almaro — gateway GEV (Xionico)

**Tenant:** `almaro`  
**Fecha:** 2026-09-16  
**Tenant id:** `98f02431-a66f-40bf-9551-9bf66faf204d`

## Host y auth

| Campo | Valor |
|---|---|
| Host | `https://almaro-api.dns-xionico.com` |
| `base_url` a guardar | `https://almaro-api.dns-xionico.com/api/` |
| Header | `X-API-Key` |
| `id_vendedor` precios | `1463` |
| Conector | `gev` — **conectado** 2026-09-16 |

Token: no en git. Variable `ALMARO_X_API_KEY`. Probe: `scripts/probe_almaro_api.sh`.

Typo de IT: `almaro-api.dns-xionico.com.com` → un solo `.com`.

## Probe 2026-09-16

| Endpoint | Resultado |
|---|---|
| `getArticulos` | 200, 3244 filas |
| `getVendedores` | 200, 48 labels `CODIGO - NOMBRE` |
| `getClientes/?id_vendedor=1463` | 200, 128 filas; clave `ID_CUENTA` numérica |
| `getClientesDirecciones/?id_vendedor=1463` | 200, 128 filas |
| `getDetallePrecios/?id_vendedor=1463` | 51517 filas (vía `load-prices`, 2026-09-16) |

## Alta post-deploy (hecha)

`POST /almaro/erp/connect` 200. `POST /almaro/erp/sync` 200 — 0 errores precios, 3244 stock del ERP. Mock de catálogo/clientes **no** se purgó. Clientes/vendedores los trae el job 6 h al espejo (`erp_customers_raw`), sin alta automática en `clients`.

Catálogo/listas/precios promovidos: [erp-catalogo-gev.md](erp-catalogo-gev.md).
