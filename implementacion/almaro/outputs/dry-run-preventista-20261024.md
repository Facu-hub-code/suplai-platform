# Dry run de almaro: los de siempre + novedades (24 oct 2026)

Solo lectura contra la base de producción. No se cambió nada. Es lo que el plantel de bots (spec 132) encontraría en su primera corrida y los borradores que propondría. Reglas en el spec 133.

## Lo que hay

| Qué | Dato |
|---|---|
| Clientes | 150 |
| Con favoritos marcados en la tienda | 0 |
| Con habituales calculados (`top_products`) | 0 |
| Con pedidos confirmados en Suplai | 42 (16 con 3 o más) |
| Sin pedidos en Suplai | 108: su historial está en GEV |
| Líneas por pedido | 5,2 en promedio, 164 SKUs distintos |
| Productos que un cliente repite | 17,8 % de los pares cliente-producto |

**Cantidad habitual** (mediana por cliente y producto, solo los que repite):

| Cantidad | Pares | Clientes | % |
|---|---|---|---|
| 1 | 14 | 10 | 16,9 % |
| 2 | 10 | 7 | 12,0 % |
| 3 | 14 | 8 | 16,9 % |
| 4 a 6 | 31 | 13 | 37,3 % |
| 7 a 12 | 10 | 8 | 12,0 % |
| 13 o más | 4 | 4 | 4,8 % |

No es «de a 1 o de a 3»: cada cliente tiene la suya por producto. Se usa la mediana.

**Novedades** (últimos 40 ingresos con catálogo, del 12 al 21 de octubre): 39 tienen foto, todas tienen precio en la lista 20, solo 2 se pidieron alguna vez.

| SKU | Producto | Problema |
|---|---|---|
| 503516 | SET MATERO | Sin foto (stock 2) |
| 14537 | TALLARÍN ARCOR MS 20X500G | Sin stock |

**Promociones por lista:**

| Lista | Clientes | Promos vigentes | Con stock |
|---|---|---|---|
| 20 TRADICIONAL | 147 | 70 | 62 |
| 10 INTERIOR | 2 | 70 | 62 |
| 21 TRADICIONAL CADENIZA | 1 (ZACARIAZ PABLA ALEJANDRA, id 592) | 0 | 0 |

## Borradores que propondrían los bots

Ninguno se armó: es la lista para la primera corrida real.

| Bot | Borrador | Riesgo | Autonomía |
|---|---|---|---|
| Analista | Calcular los habituales (`top_products` con mediana) de los 42 clientes con historial en Suplai | bajo | auto |
| Analista | Traer el historial de GEV para los 108 sin pedidos en Suplai | — | Falta la capacidad: hoy el MCP no importa pedidos del ERP |
| Catálogo | Pedir la foto de 503516 SET MATERO (la consigue Grok y la carga con `editar_productos`) | medio | auto |
| Catálogo | Avisar que 14537 TALLARÍN figura como novedad sin stock | — | Solo aviso |
| Activador | Cliente 592 en la lista 21 sin promos: pasarlo a la 20 o copiar las promos a la 21 | medio | auto |
| Jefe de cuenta | Lote de la semana: «Arrancar lo de siempre + novedades en almaro», con lo de arriba | — | Al dueño |

## Lo que falta para que esto funcione

1. **Historial del ERP.** Sin él, 108 de 150 clientes no tienen favoritos. Es lo primero.
2. **Mediana en `top_products`.** Hoy guarda el total pedido, no la cantidad habitual.
3. **Favoritos en la tienda** desde los habituales, con «Repetir lo de siempre».
4. **Lista 21 sin promos:** decidir si se mueve el cliente o se copian las promos.
