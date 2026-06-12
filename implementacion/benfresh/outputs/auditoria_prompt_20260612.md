# Auditoría system prompt — benfresh — 2026-06-12

## Resumen ejecutivo

- **Modo:** v2 (`metadata.use_new_system_prompt = true`)
- **Perfiles analizados:** client + seller
- **Tokens estimados (fijo por turno):**
  - System prompt client: **~2 474**
  - System prompt seller: **~2 426**
  - Tool descriptions habilitadas: **~2 272** (18 tools)
  - **Total contexto fijo (system + tools): ~4 750 tokens** antes de historial y snapshot de pedido
- **Hallazgos:** 🔴 4 | 🟠 6 | 🟡 4
- **E2E reciente (2026-06-11):** latencia promedio **29 s**; casos 8–9 fallaron (confirmación sin tool, suggest_order_boost)

Objetivos del roadmap Suplai: system < 3 000 tokens, tools < 4 000 tokens. Benfresh cumple tools, pero el **system supera el objetivo** y la **duplicación cross-layer** empeora selección de tools y latencia.

---

## Composición por capas (perfil client)

| Capa | Chars | ~Tokens | Notas |
|------|-------|---------|-------|
| `base` (default código, sin override) | 4 632 | 1 158 | Reglas operativas estándar Suplai |
| `unit_policy` (código + permissive) | ~1 081 | ~270 | Bloque fijo; solapa con tenant y tools |
| `channel` determinístico | 0 | 0 | No activo en metadata |
| `tenant` (`system_prompt`) | 4 140 | 1 035 | Editable backoffice |
| **Full system (preview API)** | **9 897** | **2 474** | Fuente: `POST /benfresh/system-prompt/preview` |

**Seller:** mismo bloque tenant (4 140 chars); base seller 4 439 chars → full **9 704** chars (~2 426 tokens).

**Campos legacy en BD (no ensamblados en v2, pero siguen cargados):**

| Campo | Chars | Riesgo |
|-------|-------|--------|
| `identidad` | 2 728 | Confusión al editar; posible re-backfill accidental |
| `contexto` | 1 410 | Idem |
| `system_prompt` | 4 140 | **Fuente activa** |

---

## Hallazgos

### 🔴 Críticos

**1. Contradicción de unidades: `caja`**

| Fuente | Regla |
|--------|--------|
| Código (`unit_policy`) | `caja` → enviar `unit="caja"` **sin** traducir a bulto/display |
| Tenant (`system_prompt`) | UMV = caja/pack/display (comercial OK) |
| Tool override `create_order` | `'caja' → bulto` |
| Tool override `edit_order` | `'caja' → bulto` |

El modelo recibe instrucciones opuestas. Riesgo: cantidades incorrectas en pedidos (caso E2E #7 “formato o empaque”).

**Acción:** Alinear overrides de `create_order` / `edit_order` con `unit_policy` del código (o acortar overrides y confiar en el bloque fijo).

---

**2. Perfil seller: tenant instruye `create_order`**

El `system_prompt` incluye “INSTRUCCIONES DE PEDIDO” con **`create_order`**, pero el base seller prohíbe explícitamente `create_order` y exige `create_order_for_client` / `resolve_free_text_order`.

Mismo texto tenant se inyecta en **ambos** perfiles.

**Acción:** Dividir prompt tenant en sección comercial (idioma, Miami, rubro) y sección operativa por perfil; en seller eliminar referencias a `create_order`.

---

**3. Tools deshabilitadas pero reglas activas que las exigen**

| Tool | `tools_habilitadas` | Instrucción que la pide |
|------|---------------------|-------------------------|
| `get_catalog_link` | `false` | Tenant: “usá `get_catalogo_link`” con `search_products_by_category` |
| `search_products_by_category` | `false` | Tenant: directrices de búsqueda por categoría |
| `register_client_location` | `false` | Base: usar para ubicaciones WhatsApp |
| `create_distributor_ticket` | `false` | Base: escalamiento humano |
| `list_promotions` | `false` | — (menor) |

El modelo puede intentar invocar tools inexistentes o “inventar” el link de catálogo.

**Acción:** O habilitar `get_catalog_link` (+ categoría si aplica), o **borrar** del `system_prompt` las directrices que referencian esas tools.

---

**4. Formato de listado contradictorio en tenant**

En el mismo `system_prompt`:

- “Usá **listas con viñetas** para mostrar productos y precios”
- “**NUNCA** uses listas expandidas con viñetas o guiones debajo del nombre”
- “formato de **una sola línea** por ítem”

Además, el base dice que tras tools de pedido el detalle sale de `user_facing_message` (no reconstruir formato).

**Acción:** Una sola regla de formato; preferir “seguir `user_facing_message` de la tool” para pedidos y una línea compacta solo para búsqueda de catálogo.

---

### 🟠 Performance / duplicación

**5. Triple copia del bloque “activación create_order”**

El mismo patrón (palabras clave dame/quiero, sin confirmación, prioridad alta) aparece en:

1. Base client (~implícito en reglas de pedido)
2. Tenant `INSTRUCCIONES DE PEDIDO` (~1 200 chars)
3. Tool override `create_order` (1 543 chars — **la tool más larga**)

**Ahorro estimado:** ~1 500–2 500 tokens si se deja solo en tool (versión corta) o solo en tenant (versión corta).

---

**6. SKU / `product_code` repetido 7+ veces**

Base + tenant (“Código de producto…”) + `search_products` + `create_order` + formato de listado con `(Cód: {CÓDIGO})`.

**Acción:** Mantener en tool `create_order` y una línea en tenant comercial; quitar del bloque INSTRUCCIONES DE PEDIDO.

---

**7. `confirm_order` triplicado**

Base (bloque largo anti-alucinación) + tenant (CTA “¿Querés confirmar?”) + tool `confirm_order` (190 chars).

El CTA del tenant empuja confirmación conversacional sin garantizar llamada a `confirm_order` — correlaciona con **Caso E2E #9 FAIL** (ninguna tool).

**Acción:** CTA tenant: “si confirman, ejecutá `confirm_order`”; acortar base o mover guardrails solo a tool.

---

**8. Tool descriptions infladas (QW3)**

Top 3 por tamaño (habilitadas):

| Tool | Chars |
|------|-------|
| `create_order` | 1 543 |
| `create_order_for_client` | 1 344 |
| `manage_contact_agenda` | 883 |

Muchas repiten reglas ya presentes en system prompt.

---

**9. `search_products` override desalineado**

Override dice “usar por defecto vs categoría”, pero `search_products_by_category` está **deshabilitada**. Texto muerto que confunde al router de tools.

---

**10. Mismo tenant en client y seller (+1 035 tokens × 2 perfiles)**

Contenido idéntico (Ben, Miami, Spanglish, INSTRUCCIONES DE PEDIDO client) se envía también al flujo vendedor.

---

### 🟡 Mantenimiento

**11. `reglas_negocio.catalog_policy.forbidden_brands`: Poett, Sapolio**

Parece **plantilla de otro tenant** (limpieza/hogar), no coherente con Benfresh (IQF / frozen produce Miami).

No se inyecta al prompt (correcto en v2), pero puede afectar lógica futura si se cablea.

---

**12. Typo / nombre de tool:** `get_catalogo_link` en tenant → correcto: `get_catalog_link`.

---

**13. Texto residual en `identidad` + `contexto`**

4 138 chars duplicados/obsoletos en BD respecto al `system_prompt` activo.

**Acción:** Limpiar campos legacy tras validar backoffice, o documentar que solo se edita `system_prompt`.

---

**14. “Tienes la capacidad de esuchcar audios y recibir imagenes”**

El pipeline de fotos usa prefijo `[Consulta con foto por WhatsApp]` (base); audios dependen de transcripción upstream — la frase en tenant puede generar expectativas incorrectas.

---

## Matriz de duplicación (resumen)

| Concepto | base | tenant | unit_policy | tools | Veredicto |
|----------|------|--------|-------------|-------|-----------|
| SKU / product_code | ✓ | ✓ | — | ✓✓ | Comprimir tenant + acortar tools |
| Activación create_order | ✓ | ✓✓ | — | ✓✓✓ | **Dejar una sola capa** |
| confirm_order | ✓✓ | ✓ (CTA) | — | ✓ | Alinear CTA con tool obligatoria |
| Unidades / caja | ✓ | ✓ | ✓ | ✓ (conflicto) | **Fix overrides tools** |
| Formato listas | — | ✓✓ (conflicto) | — | ✓ | Unificar |
| Catálogo / link | — | ✓ | — | ✓ (disabled) | Habilitar tool o quitar regla |
| Bilingüe / Miami | — | ✓ | — | — | OK solo en tenant |

---

## Recomendaciones priorizadas

### Alta (impacto operativo + tokens)

1. **Corregir `create_order` / `edit_order` overrides:** `caja` → `caja`, no `bulto`; alinear con `unit_policy` permissive del código.
2. **Recortar `system_prompt` tenant ~40%:**
   - Mantener: identidad Ben, bilingüe, Miami, nombres de categorías en inglés, UMV comercial Benfresh.
   - Eliminar: bloque completo INSTRUCCIONES DE PEDIDO (ya está en tool override).
   - Unificar: una sola directriz de formato de listado.
3. **Resolver tools deshabilitadas vs instrucciones:** habilitar `get_catalog_link` o eliminar párrafo de categoría/catálogo.
4. **Seller:** quitar del tenant todo lo específico de `create_order`; opcional segundo párrafo mínimo para vendedor.

### Media (performance)

5. Acortar `create_order` tool desc a ~400 chars (solo contrato: SKU, units, loaded/missing).
6. Quitar duplicado en `create_order_for_client` si el base seller ya cubre obligación de tool.
7. Limpiar `identidad` / `contexto` en BD para evitar ediciones en campo equivocado.

### Baja

8. Revisar `forbidden_brands` en `reglas_negocio` para Benfresh.
9. Corregir typo `get_catalogo_link`.
10. Tras cambios, re-ejecutar E2E (`agent-e2e-testing`) — foco casos 8 (suggest_order_boost) y 9 (confirm_order).

---

## Próximos pasos sugeridos

- [ ] Editar `system_prompt` en backoffice (un solo campo v2)
- [ ] Ajustar `tools_descripciones` de `create_order`, `edit_order`, `search_products`
- [ ] Decidir política de catálogo: habilitar `get_catalog_link` o borrar reglas
- [ ] Re-correr E2E y comparar latencia promedio (baseline 29 s)

---

*Generado con skill `analyze-system-prompt`. Preview: API Railway `POST /benfresh/system-prompt/preview`. Datos BD: MCP Supabase `public.distribuidoras`.*
