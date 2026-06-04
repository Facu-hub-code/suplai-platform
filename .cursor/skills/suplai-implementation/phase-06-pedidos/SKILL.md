---
name: suplai-implementation-phase-06
description: Fase 6 pedidos — histórico cerrado y 6-7 pedidos abiertos. Usar tras Fases 1 y 4-5.
---

# Fase 6 — Pedidos

Prerequisito: Productos, clientes y precios cargados.

## Input

- Clientes con `lista_precios_id`
- Catálogo y promos Fase 2

## Output

1. `phase-06-pedidos.csv` — `pedido_ref,cliente_codigo,fecha,estado,total,notas,is_mock,es_pedido_abierto`
2. `phase-06-items-pedido.csv` — líneas por pedido

## Volumen

| Tipo | Regla |
|------|--------|
| Histórico | ~3 pedidos × 50 clientes; estados `entregado` / `facturado` / `confirmado` (usar valores válidos del tenant); fechas mar–may 2026 |
| Abiertos | **6–7** pedidos; `es_pedido_abierto=true`; estado `abierto` o `pendiente`; fecha = NOW() |

## Ítems

- 1–4 productos por pedido; precio según `lista_precios_id` del cliente en `precios_productos`
- `notas` con patrón: `Pedido: {qty} {unidad} (normalizado: {canon}; equiv: {qty_umv} {umv})` cuando aplique
- Incluir al menos 1 pedido abierto con producto de `marca_lider` y promo Fase 2

## Carga MCP

1. `INSERT {schema}.pedidos` → obtener `id`
2. `INSERT {schema}.items_pedido` con `pedido_id`, `client_id`, `cantidad_solicitada`, `precio_unitario`, `lista_precios`
3. Actualizar `total` en pedido

Estados válidos: consultar `SELECT DISTINCT estado FROM {schema}.pedidos` en tenant con datos o usar `abierto`, `confirmado`, `entregado`.

## Verificación

- COUNT pedidos abiertos = 6 o 7
- SUM items por pedido coherente con total

## Cierre

manifest fase `06` → `cargado`
