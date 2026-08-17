# Documento de funcionalidades — Tools del agente

**Estado:** Draft v1  
**Fecha:** 2026-07-16  
**Audiencia:** implementadores, producto, soporte  
**Fuentes:** agente `app/agent/tools/` (registry, orders, free_text, rag, seller, fulfillment), `tools_meta`, spec 024/025  

Este documento describe **qué hace cada tool** y las **reglas de negocio** que aplican (stock, unidades, mínimo de compra, etc.). No reemplaza el código: ante duda, prevalece el runtime del agente.

**Convenciones**

| Símbolo | Significado |
|---------|-------------|
| PdV / client | Perfil punto de venta |
| Vendedor / seller | Perfil vendedor WhatsApp |
| Recepcionista | Grafo de alta de clientes (registration) |
| Opt-in | Arranca **apagada**; hay que habilitarla por tenant |
| Field-only | Solo si `metadata.field_app_enabled` |
| Carga parcial | Algunos SKUs entran al pedido; otros van a `missing` sin abortar el lote |

---

## 1. Mapa rápido por perfil

| Perfil | Tools típicas |
|--------|----------------|
| **PdV** | Catálogo, pedido (`create`/`edit`/`confirm`), promos, boost, fulfillment B2C, occasion, link tienda |
| **Vendedor** | Selección de cliente, carga por texto/SKU, edit/confirm Field, consultas QnA, Field (ruta/tareas) |
| **Recepcionista** | `registration_*` (alta de cliente) |
| **Compartidas** | `search_products`, `get_product_by_code`, ticket, agenda |

---

## 2. Reglas críticas (casos que más consultan)

### 2.1 Stock al agregar ítems al pedido

Aplica a: `create_order`, `edit_order`, `create_order_for_client`, `edit_order_for_client` (misma validación de líneas).

| Situación | ¿Qué pasa? | ¿Qué **no** pasa? |
|-----------|------------|-------------------|
| Stock = 0 (o ≤ 0) | El SKU va a `data.missing` con reason `out_of_stock`. **No se inserta.** | No se agrega “igual” ni en cantidad 0 |
| Stock insuficiente (pedido + carrito > disponible) | `missing` con `insufficient_stock`. **Se omite el ítem entero.** | **No** se trunca a “lo que hay” (ej. pedís 10, hay 3 → no carga 3) |
| `stock` NULL en BD | Se trata como **sin tope** (no bloquea por stock) | — |
| Varios SKUs en un lote; algunos fallan | **Carga parcial**: los OK entran; los malos van a `missing`. Status suele ser `ok` | No se cancela todo el lote por un SKU malo |
| SKU ya está en el pedido abierto (`create_order`) | Se **omite** (no suma cantidad). Contador `skipped_existing_count` | No duplica línea ni hace “+N” automático → para cambiar qty usar `edit_order` / replace |

**Ejemplo:** el usuario pide A (sin stock) + B (con stock). Resultado: B cargado; A informado como sin stock. El pedido no se “rompe”.

### 2.2 Sustitución de presentación (¿agrega “otro” producto?)

| Flujo | ¿Sustituye por otra presentación con stock? |
|-------|---------------------------------------------|
| `create_order` / `edit_order` con **SKU exacto** | **No.** Sin stock → `missing`. No busca hermana (ej. 10lb ↔ 20lb). |
| Vendedor: `load_seller_order_text` / `resolve_free_text_order` | **Sí, a veces.** Si el código no tiene stock, puede resolver por nombre vía RAG otra presentación con stock (`substitution_reason=out_of_stock`) y aclararlo en el mensaje. Ambiguos **no** se cargan. |

### 2.3 Catálogo vs pedido: ¿se ven productos sin stock?

| Tool | Sin stock |
|------|-----------|
| `search_products` / `search_products_by_category` | **Sí se muestran**, con `disponible: false`. El agente debe informar, no prometer entrega. |
| `get_product_by_code` | Match exacto; si stock ≤ 0 → **error** “sin stock” (con datos del producto). |
| Carga a pedido | Rechazo → `missing` (ver §2.1). |
| `suggest_order_boost` | Solo sugiere candidatos con stock disponible (o stock NULL). |

### 2.4 Unidades (UMV)

| Regla | Comportamiento |
|-------|----------------|
| Unidades | `unidad`/`umv`, `caja`, `display`, `bulto`, `pallet`, `equipo` → conversión a UMV del SKU |
| “Caja” | Respeta `caja_semantica` del producto (no traducir a bulto/display a mano) |
| Equipo / camión | `unit=equipo` — **no** confundir con `pallet` |
| Sin unidad indicada | Default UMV/unidad |
| Cantidad &lt; mínimo de venta del SKU | **Ajusta al mínimo** (`min_sale_adjustments`), no rechaza |

### 2.5 Pedido abierto

| Regla | Comportamiento |
|-------|----------------|
| Reuso | Si el cliente tiene `pedidos.estado='abierto'`, se **reutiliza**. No se crea otro. |
| Pedido vacío | No se crea pedido sin líneas válidas. |
| Edición | `edit_order` / `edit_order_for_client` sobre el abierto (o `order_id` si sigue abierto). |

### 2.6 Precios, promos, mínimo de compra

| Regla | Cuándo | Comportamiento |
|-------|--------|----------------|
| Lista de precios | Al validar ítems | Lista del cliente (fallback lista default del tenant). Sin precio → `no_price_for_list`. |
| Catálogo agente | Si política `agent_catalog_only` | SKU fuera de catálogo → `not_in_agent_catalog`. |
| Promos | Tras carga / pre-confirm | Reprice single-SKU + grupos mix&match; no aplica promo peor que lista. |
| **Mínimo de compra** | En **`confirm_order`** (cliente), si policy `block_confirm` | Bloquea confirmación si subtotal pre-promo &lt; mínimo. **No** bloquea al cargar ítems. |
| Boost | `suggest_order_boost` | Puede apuntar a cerrar el gap del mínimo (`reach_minimum`). |

### 2.7 Confirmación: cliente ≠ vendedor

| Tool | Comportamiento |
|------|----------------|
| `confirm_order` (PdV) | Valida abierto, no vacío, mínimo, fulfillment B2C si aplica; reprice; confirma y dispara side-effects (ERP/notificaciones según modo). |
| `confirm_order_for_client` (vendedor) | Confirma vía **backend Field** (`field_confirm_pedido`); limpia cliente seleccionado. **No** es el mismo path que `confirm_order`. |
| Guard runtime vendedor | Si el vendedor pide confirmar y el LLM no llamó la tool, el runtime puede **forzar** `confirm_order_for_client`. |

### 2.8 Fulfillment B2C (delivery / pickup)

| Tool | Regla |
|------|-------|
| `quote_delivery` | Cotiza por GPS; fuera de zona → bloqueado. No inventar montos sin tool. |
| `configure_order_fulfillment` | Requiere pedido abierto. Pickup: schedule. Delivery: `quote_id` válido. |
| `confirm_order` | Si la policy exige fulfillment y no está configurado → error `fulfillment_required`. |

### 2.9 Cliente no resuelto

Sin cliente (PdV sin match de teléfono / vendedor sin cliente seleccionado): las tools de pedido, promos y fulfillment **no operan**; piden identificar cliente.

---

## 3. Catálogo de tools (cuadro)

Leyenda perfiles: **C** = client/PdV · **S** = seller · **R** = reception · **★** = shared

### 3.1 Catálogo y descubrimiento

| Tool | Perfil | Qué hace | Reglas / notas |
|------|--------|----------|----------------|
| `search_products` | C S ★ | Búsqueda semántica (RAG) | Incluye sin stock (`disponible: false`). Usar SKU solo si hay stock para pedir. |
| `search_products_by_category` | C S ★ | Productos por categoría/tags | Disponibilidad booleana; sin cantidades de stock. |
| `get_product_by_code` | C S ★ | Lookup exacto por SKU | Sin stock → error (no “ok con warning”). |
| `get_catalog_link` | C | Link tienda `tienda.suplaisales.com/{schema}?wp=…` | Deriva a catálogo web. |
| `list_promotions` | C | Promos vigentes de la lista del cliente | Requiere cliente; filtro opcional por SKU. |

### 3.2 Pedido — punto de venta

| Tool | Perfil | Qué hace | Reglas / notas |
|------|--------|----------|----------------|
| `create_order` | C | Crea/reutiliza abierto + agrega ítems | Stock §2.1; no suma SKU ya existente; UMV §2.4; carga parcial. |
| `edit_order` | C | Agrega / reemplaza / quita líneas | Mismas reglas de stock; replace fallido no borra línea vieja. |
| `confirm_order` | C | Confirma el abierto | Mínimo de compra; fulfillment B2C; reprice. |
| `get_open_order_status` | C | Snapshot del carrito abierto | — |
| `get_order_status` | C | Estado de un pedido por id | — |
| `list_recent_orders` | C | Últimos pedidos | — |
| `suggest_order_boost` | C | Cross/up-sell del abierto | Excluye sin stock; modos mínimo/ticket. |
| `plan_occasion_bundle` | C (opt-in) | Bundle por ocasión (asado, etc.) | Policy tenant; B2C suele persistir carrito. |
| `quote_delivery` | C (opt-in) | Cotiza envío GPS | §2.8 |
| `configure_order_fulfillment` | C (opt-in) | Pickup o delivery en el abierto | Antes de confirm si B2C lo exige. |
| `register_client_location` | C | Guarda ubicación de entrega | — |
| `get_delivery_details_form_link` | C | Link formulario de dirección | — |

### 3.3 Pedido — vendedor

| Tool | Perfil | Qué hace | Reglas / notas |
|------|--------|----------|----------------|
| `set_seller_selected_client` | S | Fija cliente activo | Guard de selección. |
| `get_seller_selected_client` | S | Lee cliente activo | — |
| `list_seller_clients` | S | Lista cartera | — |
| `get_seller_client_details` | S | Detalle + selecciona | — |
| `load_seller_order_text` | S | Carga pedido desde texto libre | **Única** tool de carga por texto; puede sustituir presentación (§2.2). Guards de carga. |
| `resolve_free_text_order` | S | Alias / compat → free-text | Misma familia que load. |
| `create_order_for_client` | S | Carga ítems con SKUs al cliente | Misma lógica stock/UMV que `create_order`. **No** usar `create_order` en vendedor. |
| `edit_order_for_client` | S | Edita abierto del cliente | — |
| `get_open_order_status_for_client` | S | Abierto del cliente | — |
| `confirm_order_for_client` | S | Confirma vía Field | Distinto de `confirm_order` (§2.7). Guard runtime. |
| `suggest_order_boost_for_client` | S | Boost para el cliente | — |
| `clear_seller_context` | S | Limpia selección + historial | Reinicio de sesión vendedor. |
| `seller_help` | S | Manual de uso | — |

### 3.4 Consultas vendedor (QnA, varias opt-in)

| Tool | Perfil | Qué hace | Reglas / notas |
|------|--------|----------|----------------|
| `seller_catalog_query` | S (opt-in) | Stock / precio / novedades | Modes |
| `seller_promo_pricing_query` | S (opt-in) | Promos / lista / mínimo | Modes |
| `seller_client_query` | S (opt-in) | Último pedido / resumen / WA | — |
| `seller_my_metrics` | S (opt-in) | Ruta / tareas / torneo / ventas | — |
| `seller_orders_query` | S (opt-in) | Abiertos / error ERP | — |

### 3.5 Field (solo con Field app enabled)

| Tool | Perfil | Qué hace |
|------|--------|----------|
| `get_seller_daily_route` | S Field | Ruta / visitas del día |
| `get_seller_tasks` | S Field | Tareas gamificadas |
| `get_seller_progress` | S Field | Puntos / torneo |
| `get_seller_client_summary` | S Field | KPIs + tareas del cliente |
| `check_order_sync_status` | S Field | Sync ERP del pedido |
| `get_field_app_link` | S Field | Deep link a Field |

### 3.6 Soporte y utilidades

| Tool | Perfil | Qué hace |
|------|--------|----------|
| `create_distributor_ticket` | C S ★ | Ticket humano a la distribuidora |
| `manage_contact_agenda` | C S ★ | Preferencias / recordatorios de contacto |
| `resolve_client` | C | Resuelve cliente por session/phone |
| `ping` | C S ★ | Diagnóstico |

### 3.7 Recepcionista (grafo aparte)

| Tool | Perfil | Qué hace | Reglas / notas |
|------|--------|----------|----------------|
| `registration_get_state` | R | Estado del onboarding | — |
| `registration_check_client_exists` | R | ¿Ya existe por teléfono? | — |
| `registration_save_fields` | R | Persiste campos parciales | — |
| `registration_upsert_client` | R | Crea/actualiza cliente | Required fields según modo full vs low-friction |

---

## 4. Matriz “si pasa X → Y” (pedido)

| # | Entrada | Resultado |
|---|---------|-----------|
| 1 | Agregar SKU sin stock (create/edit por código) | No entra; aviso `out_of_stock` |
| 2 | Pedir más UMV de las disponibles | No entra el ítem; `insufficient_stock` (sin truncar) |
| 3 | Mix OK + fallidos en un mensaje | Parcial: OK cargados, fallidos en `missing` |
| 4 | Mismo SKU ya en el abierto + `create_order` | Skip (no suma); editar con `edit_order` |
| 5 | Texto vendedor con código sin stock | Puede cargar **otra presentación** con stock (free-text) |
| 6 | Buscar producto sin stock en RAG | Se lista con `disponible: false` |
| 7 | Confirmar con subtotal &lt; mínimo (policy on) | Bloquea confirm (PdV) |
| 8 | Confirmar B2C sin pickup/delivery | Bloquea si policy lo exige |
| 9 | Vendedor usa `create_order` (cliente) | Incorrecto: puede grabar en el WhatsApp del vendedor |
| 10 | Stock NULL en producto | No bloquea por stock |

---

## 5. Opt-in conocidas (referencia)

Requieren enable explícito en `tools_habilitadas` (lista sujeta a cambios en código):

- `seller_catalog_query`, `seller_promo_pricing_query`, `seller_client_query`, `seller_my_metrics`, `seller_orders_query`
- `plan_occasion_bundle`, `quote_delivery`, `configure_order_fulfillment`

---

## 6. Relación con Configuración / Admin Tools

| Concepto UI | Efecto |
|-------------|--------|
| Habilitada | Runtime: el agente puede llamar la tool |
| Visible en canvas | Solo UI del mapa (spec 025); no cambia WhatsApp |
| Nombre / “qué hace” | Editorial global (`core.agent_tools`) |
| Descripción LLM | Override por tenant (`tools_descripciones`) |
| Mensaje post-éxito | Texto anexo tras éxito |

Ver: [Spec 025](../specs/025-admin-tools-agente-visibilidad-canvas.md), [Spec 024](../specs/024-agent-tools-modal-explicativo-logs-dry-run.md).

---

## 7. Evidencia en código (atajos)

| Tema | Path principal |
|------|----------------|
| Registry / descripciones | `agente…/app/agent/tools/registry.py` |
| Pedidos / stock / UMV | `agente…/app/agent/tools/orders.py` |
| Free-text / sustitución | `agente…/app/agent/tools/free_text_order.py` |
| RAG | `agente…/app/agent/tools/rag.py` |
| Seller confirm Field | `agente…/app/agent/tools/seller.py` |
| Fulfillment | `agente…/app/agent/tools/fulfillment.py` |
| Meta / guards / field_only | `backend…/services/agent_tools_catalog_meta.json` |
| Opt-in | `agente…/app/agent/tool_activation_policy.py` |

---

## 8. Próximos pasos (opcional)

- Completar fichas editoriales en Admin → Tools del agente para todas las tools del §3.
- Enlazar cada fila del cuadro a un deeplink `/?section=agent-config&tab=herramientas&tool=…` o `/admin?section=agent-tools&tool=…`.
- Mantener este doc al agregar tools nuevas (checklist en PR del agente: actualizar §3 + §2 si hay regla nueva).
