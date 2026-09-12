# Altas e-commerce Centralo — `del_corro` (Campi)

Fecha: 2026-09-12. Excel: `Users-2026-04-24 (1).xlsx`. Proyecto `cvlbietibaaehgeimxgw`.

## Resultado

| Métrica | Valor |
|---|---:|
| Filas Excel | 185 |
| Teléfonos únicos | 183 |
| Ya existían (etiquetados, sin duplicar) | 86 |
| Insertados nuevos | 97 |
| `del_corro.clients` after | 6464 |
| PDV + location de los nuevos | 97 |
| Destinos del grupo (activo + tel) | 183 |

## Plantilla y envío

Ya existía **`clientes_web`** (`384f5f6f-74a1-4d46-aa00-b9af2d76af35`, MARKETING, variable `nombre`). No se creó otra.

| Recurso | Id |
|---|---|
| Etiqueta `Clientes Web` | 257 |
| Grupo `Clientes Web e-commerce` | 182 |
| Agenda puntual | 356 |

- Tipo: puntual
- Fecha ART: 2026-09-12
- Hora: 11:30
- Origen: `ecommerce_welcome`
- El cron de agenda (cada ~15 min) la toma en el slot 11:30–12:00 ART.

## Criterio de carga

- Teléfono canónico: `549` + últimos 10 dígitos.
- Si el suffix10 ya existía: **no** se insertó otra fila. Se etiquetó un keeper (mejor match de nombre, luego `549…`, luego código ERP).
- Nuevos: `lista_precios_id=1`, `etiqueta=CLIENTES_WEB`, `whatsapp_estado=no_validado`, `activo_ai=true`, metadata `origen=ecommerce_centralo`.
- Excel dups omitidos: Oriana Lopez (queda 415375) y Mariano (Prueba) Miles (queda 402271).

## Riesgos

Algunos teléfonos del Excel ya eran otro comercio (p. ej. Oriana López / Fernando Blangetti). El WhatsApp de bienvenida va al keeper existente, no se creó un segundo `549`.
