# Auditoría de conversaciones — Gonzalez Garcia (gonzales)

**Ventana:** 2026-06-16 → 2026-08-19 (UTC)
**Segmento:** 6 PDV RESPONDE sin pedido cerrado (excluye tester 123)
**Conversaciones con actividad:** 6
**Analizadas en detalle:** 6

## Resumen ejecutivo

Tres de seis se trabaron en el canal (stock, SKU equivocado, cantidades disparatadas o pedido que “no llegó”) y pidieron baja o vendedor humano. Los otros tres interactuaron poco o preguntaron precios/promos sin romper el flujo: quedan en el experimento visual 2.0. Plantillas personalizadas para PROBLEMA CANAL quedan fuera de este paso.

## Métricas de señal

| Señal | Cantidad |
|-------|----------|
| Errores de tool (`agent_tool_runs`) | 0 en estas sesiones |
| Búsquedas de catálogo (snapshots) | 4 (todas Menaldi, 19 ago) |
| Tickets IA (client_id = teléfono) | 5 cerrados (inactividad de pedidos 241/247/250) |
| Sesiones con frustración / corrección | 3 (MICI 138, MICI 139, Pérez) |
| Pedidos abiertos auto-cerrados | 241, 247, 250 |

## Hallazgos por categoría

### Alta — `order_logic_error` + `product_not_found`

- **Sesión:** `5493515731010` — MICI SRL (client 138)
- **Evidencia usuario:** "Hola que paso con el pedido???" / "Y ya que no llego quería saber si puedo sumar algo mas" / "Formis quiero sumar" / "Quiero hablar con un vendedor"
- **Respuesta agente:** cargó Merengadas Frutilla en lugar de Formis; `insufficient_stock` / `out_of_stock` en 13996, 6901, 14248; ofreció ticket.
- **Señal técnica:** pedidos 241 y 250 eliminados por inactividad (tickets 7, 19, 36).
- **Acción sugerida:** plantilla personalizada de disculpa + stock Formis/Topline; no mandar promo genérica.

- **Sesión:** `5493513882214` — MICI SRL (client 139)
- **Evidencia usuario:** lista Topline 4 + Saladix + Tatin caja + Formis chicas; después "Saladix bolsa 16"; "Dalo de baja"
- **Respuesta agente:** demora técnica (outbound de disculpa); Saladix 120 u. y Tatin 56 u. (mal UMV); luego 3136 unidades de Tatin (total millonario).
- **Señal técnica:** pedido 247 a revisión y luego borrado (tickets 2, 27).
- **Acción sugerida:** plantilla 1:1 pidiendo rehacer el pedido con cantidades de caja; no mix promo.

- **Sesión:** `5493516538316` — Pérez Viviana (client 264)
- **Evidencia usuario:** "Gómitas 360, Mogul 360, ¿habrá?" / "me parece que te equivocaste mi pedido es tres cajas de mogul 360 cubo" / "No me mandes nada por ahora porque el Mould 360 era lo que me hacía falta"
- **Respuesta agente:** cargó Cofler Block 60 u. + Jelly Beans; Mogul 360 cubo `no disponible`.
- **Señal técnica:** `wrong_product` + `product_not_found`.
- **Acción sugerida:** avisar cuando vuelva Mogul 360; no promo Arcor genérica.

### Media — promo no visible / pedido no cerrado

- **Sesión:** `5493516859324` — Menaldi (client 131)
- **Evidencia usuario:** "Promo top line seven?" / "Hay promociones?" / 19 ago "Promo puré de tomate Arcor" y "Promo alfajores Tatin simple"
- **Respuesta agente:** 24 jun dijo que no había promo Seven; armó pedido 242 (Seven Strong ×2) sin confirmar. 19 ago sí encontró promo puré 25% y combo Tatín.
- **Señal técnica:** 4 `catalog_search_snapshot`. Encaja con hipótesis 2.0 (imagen/carrusel).
- **Acción sugerida:** dejar en RESPONDE PROMO.

### Baja — consulta de precio / saludo

- **Sesión:** `5493512081658` — Villarreal (client 166). Preguntó precios Mana/Tatín; un humano mandó cotización 23 jul; no confirmó. Sin trabazón técnica.
- **Sesión:** `5493515413384` — Dávila (client 271). Un solo inbound: "Gracias". Sin problema de canal.

## Patrones recurrentes

1. Stock insuficiente de Formis chocolate/DDL corta el pedido MICI.
2. UMV/caja mal interpretada infla Saladix y Tatín.
3. mje1 de “primera compra / masticables” se siguió mandando semanas después del primer contacto.
4. Quien pregunta promo (Menaldi) es el mejor candidato al carrusel.

## Recomendaciones priorizadas

| # | Prioridad | Acción | Capa | Esfuerzo |
|---|-----------|--------|------|----------|
| 1 | Alta | Etiquetar 138, 139, 264 como PROBLEMA CANAL y sacarlos de RESPONDE PROMO | ops | hecho |
| 2 | Alta | Plantillas 1:1 (stock Formis / rehacer pedido MICI / Mogul 360) | comms | después |
| 3 | Media | Secuencia visual 2.0 a Menaldi, Villarreal, Dávila | comms | este paso |
| 4 | Media | Alias UMV caja vs unidad en Saladix/Tatín/Formis | catálogo | medio |

## Sesiones revisadas

| session_id | perfil | motivo selección |
|------------|--------|------------------|
| 5493515731010 | client | pedido no llegó + vendedor |
| 5493513882214 | client | cantidades disparatadas |
| 5493516538316 | client | SKU equivocado + stock |
| 5493516859324 | client | busca promos |
| 5493512081658 | client | consulta precio |
| 5493515413384 | client | un saludo |

## Limitaciones

- Sin Loki ni `agent_tool_runs` en estas sesiones; evidencia en `core.conversation_events`.
- Tickets de “hablar con vendedor” de MICI 138 no aparecen como ticket humano; sí hay tickets de inactividad de carrito.
- Tester Agustin (123) excluido.
