# Gonzalez Garcia — gateway GG API (Xionico)

**Tenant:** `gonzales`  
**Fecha:** 2026-09-15  
**Origen:** IT GEV / Xionico (hostname nuevo + `X-API-Key`)

## Estado en producción (2026-09-16)

| Campo | Valor |
|---|---|
| Conector | `gev` |
| `base_url` | `https://gg-api.dns-xionico.com/api/` |
| Token | en `tenant_secrets` (`erp.credentials`) |
| `id_vendedor` | `07` |
| Push pedidos | off |
| Sync post-deploy | 200 — 0 errores precios, 1130 stock |

IT puede apagar `agente-gg`: el sync de producción ya consume el host nuevo.

## Hosts

| Rol | Host |
|---|---|
| Producción actual (sin token) | `https://agente-gg.dns-xionico.com` |
| Gateway nuevo (con token) | `https://gg-api.dns-xionico.com` |

IT mantiene el anterior a propósito hasta migrar. Después lo dan de baja.

## Prueba 2026-09-15 (desde esta máquina)

`https://gg-api.dns-xionico.com`

| Request | Resultado |
|---|---|
| Artículos **sin** token | 401 |
| Artículos con `X-API-Key` | 200, 1131 filas |
| Artículos con `Authorization: Api-Key` (contrato actual GEV) | **401** |
| Clientes `getClientes/?id_vendedor=07` + `X-API-Key` | 200, 31 filas |
| `getDetallePrecios` con o sin `id_vendedor=07` | 200, 40424 filas (mismo volumen) |
| `getListaPrecios/` | 200, 36 listas |

`agente-gg` sigue 200 con o sin `Authorization` (el sync 6 h no se rompe).

## Código (rama `feat/gev-xionico-x-api-key`)

El conector ya manda `X-API-Key` + `Authorization: Api-Key`, y pull de vendedores/clientes/direcciones. Capabilities GEV: `pull_customers` + `pull_sellers` (migración 124).

**Todavía no cambiar `base_url` en producción** hasta el deploy de esa rama. El job viejo seguiría mandando solo `Authorization` y el host nuevo responde 401.

Post-deploy:

1. `base_url` → `https://gg-api.dns-xionico.com/api/`
2. `POST /gonzales/erp/sync`
3. Recién ahí avisar a IT que pueden apagar `agente-gg`

## Token

No guardar el valor en git. Vive cifrado en `tenant_secrets`. Para probar a mano: variable de entorno `GG_X_API_KEY` y `scripts/probe_gg_api.sh`.
