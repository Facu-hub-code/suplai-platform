# CURLO — datos desde API ERP

**Tenant:** `curlo`  
**Fecha:** 2026-10-01  
**Path:** `implementacion/curlo/` (sin rama)  
**Estado:** CSV listos. **No se escribió en Supabase.**

Origen: API de solo lectura documentada en el escritorio (`api_curlo.md`). Token **no** se guarda en el repo. Dumps en `inputs/erp/` (gitignored).

## Qué hay hoy en `curlo` (todo mock)

| Tabla | Filas | is_mock |
|---|---|---|
| productos | 793 | 793 |
| listas_precios | 4 (inventadas) | sí |
| precios_productos | 3172 | 3172 |
| clients | 50 | 50 |
| pedidos | 622 | 622 |
| vendedores | 3 ficticios | 3 |

## Qué armamos desde la API

| Entidad | CSV | Filas | Criterio |
|---|---|---|---|
| Productos | `phase-01-productos.csv` | 929 | 871 activos con precio > 0 (`en_catalogo=true`) + 58 inactivos vendidos en 12m (`en_catalogo=false`) |
| Lista 1 | `phase-01-lista-precios-1.csv` | 928 | Precios reales, `is_mock=false` |
| Lista 2 | `phase-01-lista-precios-2.csv` | 315 | Solo SKUs con precio > 0 en esa lista |
| Lista 3 | `phase-01-lista-precios-3.csv` | 246 | Idem |
| Lista 4 | — | 0 | **No existe en el ERP.** La mock se elimina al cargar |
| Clientes | `phase-04-clientes.csv` | 1664 | Activos ERP. 847 con WhatsApp normalizado. Sin lat/lng (la API no trae coords) |
| Vendedores | `phase-04-vendedores.csv` | 6 | De pedidos 12m, no inventados. El maestro de clientes no trae vendedor (`vendedor_id=-10`) |
| Zonas | — | 0 | **No inventamos** polígonos. La API no trae zonas |
| Pedidos | `phase-06-pedidos.csv` | 5762 | Ventana **2025-10-01 a 2026-10-01**. Cancelados afuera. 10 abiertos (RESERVA) |
| Ítems | `phase-06-items-pedido.csv` | 31943 | 0 SKU huérfano |

Marca líder: **BRIGEL** (140 SKUs en catálogo).

## Decisiones

| Decisión | Por qué |
|---|---|
| Pedidos solo 12 meses (~6k), no los 50k+ desde 2019 | Alcanza para ciclo/RFM; el histórico completo es pesado y viejo |
| 3 listas reales, no 4 | El ERP solo tiene Lista 1/2/3. Casi todos los clientes están en Lista 1 |
| `is_mock=false` | Datos finales del cliente |
| Fotos `https://curlomayorista.com.ar/imagenesproductos/{foto_1}` | Mismo patrón que el catálogo anterior; el ERP solo manda el filename |
| Vendedor del cliente = el que más le vendió en 12m | El maestro no trae vendedor |
| Sin zonas ni coordenadas | No hay origen real; no se inventan |
| Incluir CONSUMIDOR FINAL | Tiene `cliente_id=1` y pedidos reales |

## Qué se rompe si reemplazamos el mock

Chats (fase 7), tickets (fase 8), field/torneo (fase 6.1), promos y cross-sell (fases 2–3) apuntan a los 50 clientes y 793 SKUs mock. Al reemplazar quedan huérfanos. Se pueden purgar después.

## Carga (después de confirmar)

Orden: listas 1–3 → productos + precios → vendedores → PdV/clientes → pedidos/ítems. Borrar mock antes. Schema a tocar: **`curlo`**.
