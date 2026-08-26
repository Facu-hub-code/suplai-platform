# vendedores-tere (Gonzales / Gonzalez Garcia)

Fuente: Hoja1 de CLIENTES OFICIALES TERE.xlsx (VENDEDOR2 + COD. + DIA).

- vendedores.csv: 8 vendedores; nombre completo para gonzales.vendedores.nombre; pila para clients.vendedor.
- match.csv: 63/63 COD. encontrados en gonzales.clients.codigo (2026-08-26).
- no-match.csv: vacio (ningun COD. de Hoja1 sin cliente).

telefono: el Excel no trae telefonos. `gonzales.vendedores.telefono` es NOT NULL y UNIQUE, asi que no se puede cargar NULL ni string vacio repetido. Se usa un placeholder unico `pendiente-<slug>` (no es WhatsApp). Sin telefono real no entran a Field.

No se pisan Facundo Lorenzo (id 1) ni Ceci (id 2).

## Aplicado en BD (2026-08-26)

Vendedores nuevos (ids): Silvina 5, Pablo 6, Noelia 7, Alan 8, Lorenzo 9, Lautaro 10, Celeste 11, Gabriela 12.

- `clients.vendedor` = nombre de pila en 63/63 COD. de Hoja1 (Gabriela 4, Alan 4, Lorenzo 22, Celeste 2, Noelia 3, Pablo 3, Lautaro 16, Silvina 9).
- `vendedores_clientes`: +63 links (total 69; 6 previos de Facundo/Ceci intactos).

Agendas puntuales carrusel (`gg_carousel_promos_arcor_v1`, `carousel_config` copiado de agenda 17, 7 cards):

| id | fecha | hora ART | grupo |
|----|-------|----------|-------|
| 48 | 2026-08-26 | 15:00 | VISITA MIÉRCOLES (10) |
| 49 | 2026-08-27 | 15:00 | VISITA JUEVES (14) |
| 50 | 2026-08-28 | 15:00 | VISITA VIERNES (13) |

Recurrentes de la mañana siguen activos (17, 26, 27, 38). En mié/jue/vie: 0 clientes sin `vendedor`.
