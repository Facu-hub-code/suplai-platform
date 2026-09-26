# AB Mauri — notas del Excel (23/09/2026)

Archivo: `2026 - ABMauri - Resumen 23_09.xlsx` (escritorio, copia en esta carpeta).

## Hojas

| Hoja | Filas de datos | Qué trae | Qué no trae |
|---|---:|---|---|
| LISTA PRODUCTOS AL 23092026 | 3028 | SKU, descripción, unidad, división, rubro, segmento | Precio |
| CLIENTES AL 23092026 | 16554 | código, razón social, fantasía, CUIT, calle, localidad, provincia, dirección, email | Teléfono, vendedor, lista de precios |
| PEDIDOS HISTORICOS AL 23092026 | 221515 | cliente, fecha, comprobante, factura, viaje, SKU, descripción, unidad | Cantidad e importe por línea |
| RESUMEN CLIENTE X PRODUCTO | 17734 | cliente, SKU, unidad, cantidad total, primera y última compra | Precio |

Fechas de facturas: casi todo es 2024–2026 (corte 23/09/2026). Hay 33 líneas de 2002.

## Catálogo por división

| División | SKUs |
|---|---:|
| Participaciones publicitarias (merchandising) | 1168 |
| BI (premezclas y afines) | 724 |
| Levadura | 274 |
| Grasos | 255 |
| Pastelería | 234 |
| Margarinas | 99 |
| Productos grasos | 76 |
| COMBOS | 54 |
| Consumo masivo | 45 |
| Aceites | 45 |
| Servicios | 32 |
| Resto | 22 |

Unidades más frecuentes: sin unidad (1238), caja `CS` (1042), bolsa `BAG` (326), balde `BAL` (103).

## Clientes por provincia (top)

CABA 7464, Buenos Aires 5032, Chaco 794, Mendoza 611, Río Negro 451, Entre Ríos 342, Córdoba 315. Con email: 3986.

## Decisiones pendientes

- El schema `abmauri` no existe. Hay que crearlo vacío antes de la Fase 1.
- El Excel no sirve para cargar precios reales. En demo las 4 listas salen de un precio de referencia inventado, marcado `is_mock=true`.
- La Fase 4 del flujo arma ~50 clientes de muestra, no los 16554.
- La hoja de pedidos no alcanza para cargar historia real (falta cantidad por comprobante).
