# Gonzales — default lista de precios ERP_04

**Fecha:** 2026-08-10  
**Motivo:** Cliente nuevo (Claudia Betiana Altamirano) se registró por WhatsApp con `lista_precios_id=1` (LISTA ARCOR, 0 precios) y no podía ver precios (p.ej. COFLER BLOCK SKU 5312).

## Cambios aplicados (Supabase `cvlbietibaaehgeimxgw`)

Migración MCP: `gonzales_default_lista_precios_erp04`

1. `public.distribuidoras.default_lista_precios = 75` (ERP_04) para `schema_name = gonzales`
2. `gonzales.clients.lista_precios_id` DEFAULT → `75`
3. `gonzales.puntos_venta.lista_precios_id` DEFAULT → `75`
4. Backfill clientes/PDV con lista `1` → `75` (Claudia / PDV 120)

## Verificación

- Claudia (`clients.id=291`): `lista_precios_id=75`
- Precio SKU 5312 en su lista: ~1829.71
- 0 clientes/PDV restantes en lista 1

## Código agente

Rama: `feat/gonzales-default-lista-erp04`  
El registro ahora setea `lista_precios_id` desde `tenant.default_lista_precios` en el alta (no solo el DEFAULT de columna).
