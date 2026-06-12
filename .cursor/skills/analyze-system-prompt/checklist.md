# Checklist — Auditoría de system prompt

## A. Modo de ensamblado

- [ ] ¿`metadata.use_new_system_prompt` es `true` (v2) o legacy?
- [ ] En v2: ¿`system_prompt` tiene contenido y **no** se mezcla con identidad/contexto legacy activos?
- [ ] En legacy: ¿identidad, contexto y `reglas_y_comportamiento` están duplicados entre sí (misma frase en dos campos)?
- [ ] ¿`prompt_base` se usa como fallback de contexto vacío (riesgo de texto viejo)?

## B. Coherencia tenant vs plataforma

Buscar contradicciones entre `tenant` y bloques de código:

| Tema | Código dice | Riesgo si tenant dice lo opuesto |
|------|-------------|----------------------------------|
| Redacción de pedidos | `deterministic_channel` → no redactar totales/SKUs | Tenant pide "respuestas detalladas con totales" |
| Stock | `search_products` incluye sin stock (`disponible: false`) | Tenant: "solo ofrecé lo que hay" |
| Confirmación | Solo válida tras `confirm_order` / `confirm_order_for_client` | Tenant: "confirmá el pedido cuando el cliente diga dale" sin tool |
| Tickets | `create_distributor_ticket` solo escalamiento | Tenant: "creá ticket por cualquier consulta" |
| Horarios | Puede estar en tenant | Tools de agenda (`manage_contact_agenda`) vs texto libre |

## C. Clusters de duplicación (performance)

Marcar si el concepto aparece en **más de una** capa (base / tenant / unit_policy / tool desc):

### C1 — SKU y `product_code`
- Base: "usá SIEMPRE el SKU..."
- Tenant: repetición de no inventar códigos
- Tools: `search_products`, `create_order`, `create_order_for_client`, `resolve_free_text_order`

**Acción típica:** dejar regla operativa en **tool** `create_order*`; en tenant solo tono/comercial.

### C2 — Confirmación de pedido
- Base: bloque largo sobre `confirm_order`
- Tenant: "cuando digan dale, confirmá"
- Tool: `confirm_order` description

**Acción:** una sola fuente (base o tool); tenant solo excepciones comerciales.

### C3 — Unidades (UMV, caja, bulto, equipo/camión)
- `unit_policy` (código, ~15 líneas)
- Base client/seller
- Tools `create_order`, `create_order_for_client`

**Acción:** no repetir tabla de unidades en tenant; confiar en `unit_policy` + tools.

### C4 — Pedido desde texto libre / listas pegadas
- Base seller: `resolve_free_text_order`
- Tool `resolve_free_text_order` (muy larga)
- Tool `create_order_for_client` (solapa obligación de llamar tool)

**Acción:** comprimir tools (QW3); eliminar párrafos espejo en tenant.

### C5 — Búsqueda de clientes (vendedor)
- Base: `get_seller_client_details` vs `list_seller_clients`
- Tenant: "buscá al cliente X"
- Tools seller

**Acción:** una regla clara; evitar tercera copia en tenant.

### C6 — Snapshot de pedido abierto
- Base: no llamar `get_open_order_status` si snapshot alcanza
- Runtime: bloque snapshot variable
- Tenant: "siempre consultá el pedido antes de editar"

**Acción:** alinear tenant con snapshot; quitar instrucciones que fuercen tool extra.

### C7 — Identidad comercial duplicada
- Nombre asistente + rubro en `identidad` y otra vez en `contexto` / `system_prompt`
- Mismo párrafo copiado de implementación Fase 1.3

**Acción:** identidad = tono/persona; contexto = operación/zona/horario (sin repetir nombre/rubro).

### C8 — Promociones / mínimo de compra
- `reglas_negocio` estructurado (mínimo) — **no** debe volcarse JSON al prompt
- Tenant menciona mínimo
- Tools `suggest_order_boost`, `confirm_order`

**Acción:** mínimo solo en reglas estructuradas + tools; tenant una línea comercial si hace falta.

## D. Tool descriptions

- [ ] ¿Tools deshabilitadas (`tools_habilitadas: false`) siguen con overrides largos en `tools_descripciones`? (ruido si se reactivan)
- [ ] ¿Overrides **alargan** el default sin aportar reglas nuevas?
- [ ] ¿Alguna tool habilitada tiene descripción > 800 caracteres?
- [ ] ¿Perfil seller tiene tools de client habilitadas sin uso? (inflate bind_tools)

Tools suele ser el mayor palanca de QW3 (−10–15% latencia).

## E. Ruido y mantenibilidad

- [ ] Párrafos "prompt engineering" genéricos ("sos muy inteligente", "piensa paso a paso")
- [ ] Listas enormes de ejemplos de SKU o frases usuario
- [ ] Reglas en inglés mezcladas con español sin motivo
- [ ] Referencias a tools descontinuadas o renombradas
- [ ] Instrucciones que el runtime ya enforcea (guards en código)

## F. Impacto estimado en performance

| Factor | Efecto |
|--------|--------|
| +1000 tokens system | Más latencia en **cada** turno (input al LLM) |
| +2000 tokens tools | Peor tool selection; más confusión entre tools similares |
| Duplicación contradictoria | Reintentos, tools erróneas, turnos extra → multiplica latencia |
| `deterministic_channel` off + reglas largas de formato | Modelo genera texto que el sistema descarta |

Correlacionar con Grafana/`tool_end` si el usuario provee schema y fechas.

---

## Plantilla de reporte

```markdown
# Auditoría system prompt — {schema} — {fecha}

## Resumen ejecutivo
- Modo: v2 | legacy
- Perfiles analizados: client | seller
- Tokens estimados: system ~X | tools ~Y | total contexto fijo ~Z
- Hallazgos: 🔴 n | 🟠 n | 🟡 n

## Composición por capas
| Capa | Chars | ~Tokens | Notas |
|------|-------|---------|-------|
| base | | | |
| channel | | | |
| unit_policy | | | |
| tenant | | | |
| tools (habilitadas) | | | |

## Hallazgos

### 🔴 Críticos
1. ...

### 🟠 Performance / duplicación
1. ...

### 🟡 Mantenimiento
1. ...

## Matriz de duplicación
| Concepto | base | tenant | unit_policy | tools | Veredicto |
|----------|------|--------|-------------|-------|-----------|
| SKU | ✓ | ✓ | — | ✓✓ | Comprimir |

## Recomendaciones priorizadas
1. [Alta] ...
2. [Media] ...

## Próximos pasos sugeridos
- [ ] Aprobar edición en backoffice (`system_prompt` / `tools_descripciones`)
- [ ] Re-correr E2E (`agent-e2e-testing`) tras cambios
```
