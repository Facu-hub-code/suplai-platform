# Campi (`del_corro`) — corrección día de visita y zona

Fecha: 2026-09-12. Schema **`del_corro`**. Maestro: `M. de clientes 08.09.xlsx`.

Warning del backoffice: **⚠️ Sin zona / Día de visita** (PDV sin `geo_zone_id` o sin `dia_de_visita`).

## Resultado

| Métrica | Before | Tras r1 | Tras r2 |
|---|---:|---:|---:|
| PDV con warning | 1215 | 773 | **665** |
| PDV actualizados (acumulado) | — | 442 | **550** |
| Clientes actualizados | — | 442 | **550** |

Muestra post-update: Villarroel → Zona 13 miércoles; Monjes → Zona 13 miércoles; Marque → Zona 15 viernes; Falcón → Zona 21 lunes; Cañete → Zona 11 lunes.

## Qué se hizo

1. Cruce por **código ERP**, y si no había código, por **teléfono** (últimos 10 dígitos).
2. Día de visita = último dígito de la zona del maestro (1 lunes … 6 sábado).
3. Si la zona ya existía → se asignó `geo_zone_id` + día.
4. Rutas que el maestro trae y el tenant no tenía:
   - Vendedores **14 FAERMAN, David**, **17 HERRERA, Maria**, **18 Vendedor 18**
   - Zonas **141, 143–146, 171–176, 181** (polígonos válidos). Zona **181** sin GPS: anillo placeholder en el centro de Córdoba.

## Ronda 2 (nombre único + zonas especiales)

+**108** PDVs. 56 por código ERP (depósito/robot/PV que r1 había salteado) y 52 por nombre único de 2+ tokens (sin usar solo el nombre de pila).

Zonas nuevas: **40, 98, 99, 142, 231, 1010, 1020, 8881–8885**. Vendedores: FARIAS, GARCIA Jesus, Deposito, Axum Robot, Punto de venta 1/2, vacante.

No se cruzó por apellido suelto ni por dirección sola (generaba falsos: Marta→MARTA, Ariel→Ariel, misma calle otro comercio).

## Todavía con warning (665)

| Motivo | PDVs |
|---|---:|
| Sin match estricto en el maestro | 634 (435 sin código ERP) |
| Maestro sin zona | 26 |
| Equipo interno (Facundo, Dottori, etc.) | 5 |

## Archivos

- `asignables.csv` / `aplicados.csv` — 442 filas escritas
- `omitidos.csv` — 773 sin cambio
- `zonas_a_crear.csv`
- `resumen.json`
- script: `implementacion/del_corro/scripts/corregir_zona_dia_warning.py`
