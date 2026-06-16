---
name: suplai-implementation-phase-06
description: Fase 6 pedidos — histórico cerrado y 6-7 pedidos abiertos. Usar tras Fases 1, 4 y 5 cargadas con los scripts deterministas de `scripts/fase-06-pedidos/`.
---

# Fase 6 — Pedidos

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Input

- Clientes con `lista_precios_id`
- Clientes ya actualizados por la Fase 5 vía `scripts/fase-05-clientes-flags/`
- Catálogo, listas de precios y promos cargadas

## Output

1. `phase-06-pedidos.csv` — `pedido_ref,cliente_codigo,fecha,estado,total,notas,is_mock,es_pedido_abierto`
2. `phase-06-items-pedido.csv` — líneas por pedido

Los scripts de la fase pueden agregar columnas auxiliares reutilizables como `cliente_phone`, `cliente_razon_social`, `lista_precios_id`, `nombre` y `promo_aplicada` para hacer la carga y las fases siguientes más deterministas. El contrato principal sigue siendo el mismo.

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

La fase debe ejecutarse con scripts:

1. Generar los CSV con `python scripts/fase-06-pedidos/preparar_pedidos.py --esquema <schema>`
2. Cargar en BD con `python scripts/fase-06-pedidos/cargar_pedidos.py --esquema <schema>`

El cargador:
- Inserta cabeceras en `{schema}.pedidos` y rescata `id`.
- Inserta líneas en `{schema}.items_pedido`.
- Recalcula `total` del pedido a partir de sus ítems.

Estados válidos: consultar `SELECT DISTINCT estado FROM {schema}.pedidos` en tenant con datos o usar `abierto`, `pendiente`, `confirmado`, `entregado`, `facturado`.

## Verificación

- COUNT pedidos abiertos = 6 o 7
- SUM items por pedido coherente con total

## Cierre

manifest fase `06` → `cargado`
