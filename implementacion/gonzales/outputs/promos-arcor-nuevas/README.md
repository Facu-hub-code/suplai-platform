# Promos Arcor nuevas (Gonzales) — 26 ago 2026

Fuente: `Desktop/promos arcor` (Hoja1 TERE + 7 flyers). Tenant `gonzales`.

## Promos en BD

Listas de la campaña: 46, 74, 75, 76, 77, 78. Vigencia `2026-08-26` → `2026-11-30`. `is_mock=false`.

| TERE | Label / SKU | Tipo | Desc. | Min UMV | Acción |
|------|-------------|------|-------|---------|--------|
| 04 | COMBO TRIPLES MIXTO | grupo | 15% | 12 | insert (ids 89+) |
| 06 | COMBO GALLETAS RELLENAS | grupo | 15% | 12 | insert |
| 08 | 14336 Surtido Diversión | single | 15% | 10 | reactivada (estaba vencida) |
| 09 | COMBO TRIPLES BAGLEY | grupo | 15% | 12 | insert |
| 10 | COMBO REX KESITAS | grupo | 15% | 12 | insert |
| 11 | 5312 Cofler Block 38g | single | 10% | 10 | reactivada |
| 14 | COMBO MENTHOPLUS | grupo | 15% | 3 | insert |

Las otras TERE de Hoja1 (Tatín, Puré, Águila, Formis, Surtido Bagley, Topline) ya estaban cargadas.

## Plantillas Meta (PENDING aprobación)

7 IMAGE + 1 carrusel. Variables `nombre`, `vendedor`. Botones imagen: Me interesa / No me interesa. Carrusel: CTA `Quiero Mixto`, `Quiero Rellenas`, `Quiero Diversión`, `Quiero Triples Bagley`, `Quiero Rex`, `Quiero Cofler`, `Quiero Menthoplus`.

| Plantilla | UUID BD |
|-----------|---------|
| gg_promo_triples_mixto_v1 | a3da5bac-6603-4919-9a12-1f2f95ede0e4 |
| gg_promo_galletas_rellenas_v1 | 662de326-0beb-4a34-9d00-a80844ae2562 |
| gg_promo_surtido_diversion_v1 | c37de9a9-021a-4e57-b40b-d7de5e10c60c |
| gg_promo_triples_bagley_v1 | 7727234e-b85e-4791-8072-80a128452111 |
| gg_promo_rex_kesitas_v1 | 5d85fb45-1859-4d54-9e0b-5965ecbd2f10 |
| gg_promo_cofler_block_v1 | 29284302-344f-43bf-b5cf-689872e47b74 |
| gg_promo_menthoplus_v1 | 5e3d63d5-8c92-4dab-8e91-2cbf814a4153 |
| gg_carousel_promos_arcor_v2 | 98194d70-157a-453a-8b26-bbf84e90837f |

`carousel_config.json` listo para copiar a una agenda cuando Meta apruebe (no se tocó el carrusel v1 ni las agendas de las 15:00).

Script: `implementacion/gonzales/scripts/crear_plantillas_promos_nuevas.py`
Imágenes: `implementacion/gonzales/inputs/promos-arcor-nuevas/`
