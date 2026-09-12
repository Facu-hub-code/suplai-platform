# Campi (`del_corro`) — conciliación de clientes duplicados por teléfono

Fecha: 2026-09-11. Proyecto Supabase `cvlbietibaaehgeimxgw`. Escritura explícita pedida por el usuario.

## Conteos

| Métrica | Before | After |
|---|---:|---:|
| `del_corro.clients` | 6367 | 6367 (sin DELETE duro) |
| `del_corro.pedidos` / vivos | 17118 / 17113 | 17118 / 17113 |
| Grupos suffix10 (todas las filas) | 75 | 44 |
| Grupos suffix10 con `activo_ai` vivo | 75 | 43 |
| Filas dummy `dup-merged-*` | 0 | 32 |
| Pedido Hot Corner 17493 `cliente_id` | 64550 | **64465** |

## Qué se hizo en cada merge

1. Reasignar `pedidos.cliente_id` (vivos e históricos).
2. Mover FKs: locations, memory, favoritos, etiquetas, conversations, vendedores_clientes, routes, field_tasks, agenda, estrategia_*, aliases. Conflictos de PK: se conservó la fila del keeper.
3. Duplicado: `activo_ai=false`, `is_primary=false`, `phone_number=dup-merged-{id}`, metadata `merged_into`.
4. Keeper: teléfono Meta `549`+últimos 10, salvo 2 casos. Conserva `pdv_id`. PDV huérfano del duplicado no se borró.
5. `items_pedido.client_id` es el **codigo ERP** (varchar), no el `clients.id`. No se tocó.

## Merges (32)

| suffix | keeper_id | merged_id | phone_final | pedidos_movidos |
|---|---:|---:|---|---:|
| 3512019202 | 31204 | 46654 | 5493512019202 | 0 |
| 3512029370 | 33159 | 35852 | 5493512029370 | 5 |
| 3512257669 | 33160 | 35646 | 5493512257669 | 5 |
| 3512375072 | 36687 | 64283 | 5493512375072 | 1 |
| 3512502411 | 33161 | 35433 | 5493512502411 | 4 |
| 3512753060 | 33162 | 35663 | 5493512753060 | 3 |
| 3512955167 | 35608 | 41816 | 5493512955167 | 0 |
| 3513207374 | 33165 | 35611 | 5493513207374 | 12 |
| 3513267158 | 33166 | 35849 | 5493513267158 | 7 |
| 3513465712 | 64155 | 64547 | 5493513465712 | 0 |
| 3513722237 | 31405 | 35787 | 5493513722237 | 0 |
| 3513795942 | 33171 | 35762 | 5493513795942 | 5 |
| 3513992414 | 64401 | 35202 | 5493513992414 | 0 |
| 3515520055 | 64274 | 64545 | 5493515520055 | 0 |
| 3515916146 | 31440 | 33023 | 5493515916146 | 1 |
| 3516222148 | 32819 | 33025 | 5493516222148 | 4 |
| 3516610831 | 36743 | 64534 | 5493516610831 | 0 |
| 3516810775 | 32854 | 33027 | 5493516810775 | 0 |
| 3517357165 | 31092 | 33028 | 5493517357165 | 0 |
| 3517425361 | 33182 | 35855 | 5493517425361 | 1 |
| 3518086029 | 64007 | 64551 | 5493518086029 | 0 |
| 3525504136 | 64431 | 45769 | 5493525504136 | 11 |
| 3525512008 | 35416 | 40170 | 5493525512008 | 5 |
| 3541602809 | 35885 | 45841 | 5493541602809 | 11 |
| 3543318606 | 64260 | 64552 | 5493543318606 | 0 |
| 3543319756 | 64465 | 64550 | 5493543319756 | 1 |
| 3544467120 | 64470 | 31131 | 5493544467120 | 0 |
| 3544595506 | 31182 | 46614 | 54903544595506 (sin canónico) | 0 |
| 3563402590 | 32903 | 62082 | 5493563402590 | 3 |
| 3571413444 | 33151 | 35894 | 5493571413444 | 4 |
| 3573443384 | 31171 | 46608 | 5493573443384 | 0 |
| 5443462653 | 33266 | 35824 | 54935443462653 (14 dígitos) | 6 |

Total pedidos reasignados: **89**.

Casos destacados: Hot Corner 64465←64550 (pedido 17493); JS 64007←64551; Liliana 64260←64552; Santillán 64155←64547; Claudia Bernoy 36743←64534. 64465 tenía `activo_ai=false` de origen; se activó post-merge para que el 549 vivo atienda el agente.

## Skipped

### Placeholder / mock
- `1111111111`: 35889 Walter andreosi + 32324 Cliente Nuevo SA (ambos ya `activo_ai=false`).
- `client_id=64553` QA Conciliacion (`is_mock`, 5493510000831) — no formaba par.

### Comercios distintos (teléfono compartido) — no tocados
Incluye canvas SHARED + extras: Los dos hermanos/Ledesma; Abrate/Ruggero; Escudero/Llavot; Casale/Market Guada; GIS Nadaya/Garay; Nievas/Quiosco; Lucas Monjes/Ricardo Monjes; Elmercadito/Blangetti; Federico/Pablito; Ramos/Adrian Moreno; Bujon/Heine; Lincmea/Sucomax; Vaudano/Pugliese; Huk/Fattu; Mary Ines Martin/Yasmina; Bordcas/Veliz; Sandri/Auchterlonie; Talabarteria Martinez/Eduardo Martinez; Busto/Mini market Roma; Dupuy/El condor; German/Guadalupe Rivarola (sí se unificaron las dos filas German 31182+46614; Guadalupe 62073 intacta).

### Ambos con código ERP real y distinto — no tocados
Culasso 25641/21402; Fassi 17026/17029; Cañete 31438/16752; Sanchez 24581/20686; Medrano 16226/16842; La Cuesta 19350/16750; Chiara 21477/21511; Moreno 16415/30595; Moya / Suc 2 19081/18607; Herrera 25607/21118; Torino 15108/12816; Caceres Local 2 15968/13832; Ermeninto 35030/5374; Linares 25622/18125; Cobo 17009/14219; Oviedo 15783/12949; Caglieri 31804/13901; Las Palmas 19562/21432; Pacheco 18345/31915; Cardoso 18220/21102; Lourdes 15587/21169; SOR-MER 19312/21174.

## Riesgos residuales
- PDVs huérfanos del duplicado siguen en `puntos_venta` (sin borrar).
- `core.conversations.session_id` de altas 549… del duplicado no se reescribió.
- Jesica Olivo: keeper 64431 codigo 16850; items históricos siguen con `items_pedido.client_id='345'`.
- Valeria Bazan codigo `34` (corto) unificado por mismo codigo + mismo nombre.
- Antoniazzi y German no usan `549`+10: 3544 de 14 dígitos / UNIQUE con Guadalupe.
- Inbound al dummy `dup-merged-*` no matchea teléfono real.
