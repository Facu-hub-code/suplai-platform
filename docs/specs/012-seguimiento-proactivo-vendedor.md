# Seguimiento proactivo vendedor por WhatsApp — Índice cross-repo

**Estado:** Aprobado (diseño)
**Fecha:** 2026-06-24
**Plan:** [`.cursor/plans/field-proactivo-whatsapp_029ca33e.plan.md`](../../.cursor/plans/field-proactivo-whatsapp_029ca33e.plan.md)

---

## 1) Objetivo de negocio

Liberarle tiempo al **jefe de ventas** delegando en el agente:

1. **Q&A reactivo:** preguntas operativas frecuentes que los vendedores le hacen hoy al jefe vía WhatsApp (promos vigentes, listas de precios, stock, mi progreso vs objetivos, ranking del torneo, etc.).
2. **Podcast diario proactivo:** briefing en audio (3–5 min) que cada vendedor recibe todas las mañanas con un resumen de su ruta, tareas, objetivos y posición en el torneo.

---

## 2) Decisiones de producto (cerradas)

| # | Tema | Decisión |
|---|------|----------|
| 1 | Canal Q&A | **Extender el canal seller del agente** (spec [025 del agente](../../../agente-conversacional-multi_tenant/docs/specs/025-canal-deterministico-asistente-vendedor.md)) con **5 tools paraguas** determinísticas (`mode` de operación) — sin narrativa LLM. La respuesta es el `user_facing_message` de la tool, no texto del modelo. Evita inflar el registry a ~40 tools atómicas (degradación de routing LLM). |
| 2 | Persona del podcast | **Voz configurable por tenant** (no se fija "Facundo" como persona única del ecosistema). Cada distribuidora elige proveedor TTS, voice_id y nombre del host en `distribuidoras.metadata.field_podcast.*`. |
| 3 | Pipeline TTS | Reutiliza la decisión de la [spec 008 del podcast spec-cast](./008-spec-podcast-voz-humana.md) §4: backends `azure | elevenlabs | openai`. Descartamos `macos` (corre en cloud). |
| 4 | Delivery WhatsApp | **Audio nativo** (upload Meta media → `media_id` → mensaje `type: audio`). No se envía como link. |
| 5 | Backoffice playback | Renderizado en la **sección Conversaciones del agente** (vista seller), no UI nueva. Player `<audio>` + transcripción colapsable. |
| 6 | Storage | Bucket privado dedicado **`field-podcasts`** en Supabase Storage, path `{schema}/{vendedor_id}/{YYYY-MM-DD}.m4a`. URL firmada con TTL 24h. Lifecycle 90 días. |
| 7 | Generación | **CRON nocturno** ~05:30 TZ tenant (después del cron de tareas, ver [005-field-tareas-v2-diseno](./005-field-tareas-v2-diseno.md) §6 y [007-field-app-v2-mejoras](./007-field-app-v2-mejoras.md) §1.6). |
| 8 | Envío | **CRON cada 15 min** que despacha jobs `READY` cuyo `send_time_local` ya pasó. Default 06:30 TZ tenant. |
| 9 | Ventana 24h Meta | Si el vendedor está fuera de la ventana de servicio, plantilla HSM `field_daily_briefing` (texto) + audio como segundo mensaje. |
| 10 | Repos sin cambios | `field-app/`, `tienda/`, `sniffer/`, `sales-engine/` — no se tocan. |

---

## 3) Specs hijas

| Repo | Archivo | Contenido |
|------|---------|-----------|
| `agente-conversacional-multi_tenant` | [033-seller-qna-tools-proactivas.md](../../../agente-conversacional-multi_tenant/docs/specs/033-seller-qna-tools-proactivas.md) | **5 tools paraguas** de Q&A (`seller_catalog_query`, `seller_promo_pricing_query`, `seller_client_query`, `seller_my_metrics`, `seller_orders_query`) con modos de operación; contratos `user_facing_message`; `seller_help` y `_system_prompt`. |
| `backend-supabase` | [055-field-podcast-diario.md](../../../backend-supabase/docs/specs/055-field-podcast-diario.md) | Migración `field_podcast_jobs`, dossier builder, sender WhatsApp nativo, endpoints admin, integración CRON. |
| `backend-supabase` | [056-field-podcast-tts-provider.md](../../../backend-supabase/docs/specs/056-field-podcast-tts-provider.md) | Adaptador multi-proveedor TTS (Azure / ElevenLabs / OpenAI), config por tenant, bucket `field-podcasts` y RLS. |
| `product-management-app` | [048-field-podcast-backoffice.md](../../../product-management-app/doc/specs/048-field-podcast-backoffice.md) | UI player en conversación seller, proxy `/api/field/podcast/[event_id]/audio`, sección admin de briefings. |

---

## 4) Arquitectura end-to-end

```mermaid
flowchart TD
    cronTareas[CRON 05:30 TZ tenant<br/>field_daily_tasks] --> tareas[ensure_daily_tasks por vendedor]
    tareas --> trigger[trigger podcast job<br/>field_podcast_jobs status=PENDING]
    trigger --> worker[PodcastWorker]
    worker --> dataLayer[Recolecta datos<br/>ruta, tareas, objetivos, torneo]
    dataLayer --> guion[LLM redacta guion humanizado<br/>3-5 min, persona por tenant]
    guion --> ttsRouter{TTS backend<br/>tenant.metadata.field_podcast.voice_provider}
    ttsRouter -->|azure| azure[Azure es-AR-TomasNeural<br/>o voz configurada]
    ttsRouter -->|elevenlabs| eleven[ElevenLabs voice_id]
    ttsRouter -->|openai| openai[OpenAI TTS]
    azure --> mediaFile[.m4a generado]
    eleven --> mediaFile
    openai --> mediaFile
    mediaFile --> bucket[Supabase Storage<br/>field-podcasts/{schema}/{vendedor}/{fecha}.m4a]
    bucket --> jobReady[job status=READY<br/>signed_url + transcripcion]
    jobReady --> cronEnvio[CRON envio configurable<br/>default 06:30 TZ]
    cronEnvio --> sender[PodcastSender<br/>Meta media upload]
    sender --> waMedia[Meta Cloud API<br/>media_id]
    waMedia --> waMessage[WhatsApp audio message<br/>al telefono del vendedor]
    waMessage --> persist[core.conversation_events<br/>outbound_message + media]
    persist --> backoffice[Backoffice Conversaciones<br/>player audio + transcripcion]
```

---

## 5) Catálogo de preguntas que el agente debe responder (Q&A)

Las preguntas del enunciado del usuario más las propuestas, agrupadas por **tool paraguas + `mode`**. Detalle de contratos en la [spec 033 del agente](../../../agente-conversacional-multi_tenant/docs/specs/033-seller-qna-tools-proactivas.md).

| Tool paraguas | Modos principales | Preguntas que cubre |
|---------------|-------------------|---------------------|
| `seller_catalog_query` | `stock`, `price_for_client`, `news` | Stock SKU, precio producto×cliente, novedades catálogo |
| `seller_promo_pricing_query` | `active_promotions`, `expiring_soon`, `price_list`, `minimum_order` | Promos vigentes/vencen, lista precios, pedido mínimo |
| `seller_client_query` | `last_order`, `purchase_summary`, `contact`, `whatsapp_status` | Último pedido, compras período, ficha PDV, estado WA |
| `seller_my_metrics` | `route`, `tasks`, `task_detail`, `objectives`, `tournament`, `sales` | Ruta del día, tareas/puntos, objetivos, torneo, facturación |
| `seller_orders_query` | `open_orders`, `erp_failed` | Pedidos abiertos, errores inyección ERP |

Tools existentes que siguen usándose sin paraguas: `search_products`, `get_product_by_code`, `seller_help`. Field 032 (`get_seller_daily_route`, etc.) permanece; `seller_my_metrics` es la entrada preferida para Q&A.

### 5.1 Catálogo / producto

- ¿Hay stock del SKU/producto X?
- ¿Cuánto sale el producto X para el cliente Y (lista aplicada)?
- ¿Qué productos nuevos hay en el catálogo este mes?
- ¿Qué reemplazo / equivalente tiene el producto X si no hay stock?
- ¿Cuál es la presentación / unidad de venta del SKU X? (UMV, alineado a spec [027 del agente](../../../agente-conversacional-multi_tenant/docs/specs/027-caja-semantica-umv-display.md))

### 5.2 Promos y precios

- ¿Qué promos están vigentes hoy? (todas / para el cliente X)
- ¿Qué promos vencen esta semana?
- ¿Cuál es la lista de precios asignada al cliente X?
- ¿Cuánto es el pedido mínimo / mínimo facturable del cliente X?

### 5.3 Cliente / PDV

- ¿Cuándo fue el último pedido del cliente X? ¿Qué incluía?
- ¿Cuánto compró el cliente X este mes / mes pasado / últimos 90 días?
- ¿Cuál es la dirección / teléfono / contacto del PDV X?
- ¿Qué día de visita tiene el cliente X?
- ¿El cliente X está activo en WhatsApp con el agente? (estado WA, [spec 039 backend](../../../backend-supabase/docs/specs/039-cliente-whatsapp-estado.md))
- ¿Cuántos clientes inactivos tengo hoy en mi ruta?
- ¿Qué clientes de mi ruta faltan visitar hoy?

### 5.4 Mis métricas y objetivos

- ¿Cómo voy con mis objetivos comerciales activos? (% cumplido por objetivo, usa `field_objetivos` — [spec 053 backend](../../../backend-supabase/docs/specs/053-field-objetivos-comerciales.md))
- ¿En qué puesto estoy del torneo / leaderboard del mes?
- ¿Cuántas tareas tengo pendientes hoy y cuántos puntos posibles?
- ¿Cuánto facturé esta semana / hoy?
- ¿Cuántos pedidos tomé hoy / esta semana?
- ¿Qué SKUs del combo de la tarea X me faltan?

### 5.5 Operativo del propio vendedor

- ¿Cuáles son mis pedidos abiertos (no confirmados)?
- ¿Hay pedidos rechazados / con error de inyección ERP en mis clientes? ([spec 001 agente](../../../agente-conversacional-multi_tenant/docs/specs/001-inyeccion-erp-al-confirmar-pedido.md))
- Ayuda / qué puedo preguntarte (manual `seller_help`)

---

## 6) Modelo del podcast diario

### 6.1 Dossier (datos crudos, sin LLM)

Por vendedor, el motor compone un dossier estructurado JSON con:

- `vendedor`: nombre, zonas, teléfono.
- `ruta_hoy`: PDVs, cantidad, geozonas.
- `tareas_hoy`: por tipo (`REACTIVAR_CLIENTE`, `MEJORAR_MIX_RENTABLE`), SKUs combo, puntos posibles.
- `objetivos_vigentes`: por cada uno, `unidades_vendidas / meta_unidades`, días restantes.
- `torneo`: posición actual, diferencia con #1, puntos del día anterior.
- `highlights_ayer`: pedidos confirmados, tareas cumplidas, clientes contactados.
- `prioridad`: cliente más inactivo en la ruta o con mayor potencial.

### 6.2 Guion (LLM)

Prompt parametrizado por persona del tenant:

```text
Sos {persona_nombre}, el copiloto del vendedor {nombre_vendedor} en {distribuidora}.
Tono: {persona_tono}. Idioma/acento: {persona_idioma}.
Generá un guion hablado de 3 a 5 minutos (~500-800 palabras) con esta info:
{dossier_json}
Reglas:
- No leer JSON, listas largas ni SKUs uno por uno: agrupá (ej. "tenés 4 reactivaciones en zona Norte").
- Frases cortas, conversacionales, ritmo respirado.
- Cerrá motivando al cumplimiento del objetivo más al alcance.
- No inventes números: usá solo los del dossier.
```

### 6.3 TTS y bucket

Detalle en la [spec 056 backend](../../../backend-supabase/docs/specs/056-field-podcast-tts-provider.md).

---

## 7) Feature flags

```sql
-- Activar podcast para un tenant
UPDATE public.distribuidoras
SET metadata = metadata || jsonb_build_object(
  'field_podcast', jsonb_build_object(
    'enabled', true,
    'voice_provider', 'azure',
    'voice_id', 'es-AR-TomasNeural',
    'persona_nombre', 'Tomás',
    'persona_tono', 'cercano, profesional, rioplatense',
    'persona_idioma', 'es-AR',
    'send_time_local', '06:30',
    'send_days', ARRAY['mon','tue','wed','thu','fri']::text[]
  )
)
WHERE schema_name = 'tu_schema';
```

Tools de Q&A: gate por `seller_assistant.deterministic_channel` ya existente — si está off, las tools nuevas siguen disponibles pero el canal usa narrativa LLM como hoy (no rompe nada).

---

## 8) Fases de entrega

| Fase | Entregable usuario |
|------|-------------------|
| **1** | Q&A canal seller (sin podcast): 5 tools paraguas (catálogo, promos/precios, cliente, mis métricas, pedidos). Despeja gran parte del trabajo del jefe. |
| **2** | Podcast V1: pipeline TTS solo con Azure `es-AR-*`, sin clonación; envío WhatsApp nativo; persistencia en `conversation_events`; UI backoffice player. |
| **3** | Multi-proveedor TTS y voz clonada: adaptador ElevenLabs + voz por tenant; integración con spec 008 (Facundo). |
| **4** | Métricas y A/B: medir engagement (vendedores que escuchan, cumplimiento de tareas pre vs post podcast), tuneo de guion. |

---

## 9) Relación con otras specs

- **No reemplaza** [Suplai Copilot (001)](./001-suplai-copilot.md): el copilot es chat del **jefe de ventas** en el backoffice; este spec es para los **vendedores** por WhatsApp.
- **Complementa** [Suplai Field (003)](./003-suplai-field-app.md) y [motor de tareas V2 (005)](./005-field-tareas-v2-diseno.md): el podcast es la cara "push" diaria del mismo motor de tareas/objetivos.
- **Reutiliza pipeline TTS** del [Spec Cast (008)](./008-spec-podcast-voz-humana.md), parametrizado por tenant en lugar de fijar "Facundo".

---

## 10) Criterios de aceptación (alto nivel)

- [ ] Vendedor puede preguntar por WhatsApp las 3 preguntas del enunciado del usuario (promo vigente, lista precios cliente X, stock SKU X) + al menos 8 de las propuestas y recibe respuesta determinística vía tool paraguas + `mode` correcto.
- [ ] CRON nocturno genera audio para cada vendedor activo con flag `field_podcast.enabled`.
- [ ] Audio guardado en bucket `field-podcasts` con path `{schema}/{vendedor_id}/{fecha}.m4a`.
- [ ] WhatsApp del vendedor recibe el audio nativo a la hora configurada del tenant.
- [ ] Backoffice muestra el audio reproducible y la transcripción en la conversación del vendedor.
- [ ] Voz del podcast configurable por tenant (proveedor + voice_id).
- [ ] Re-run manual de un job de podcast desde API admin (debug).
- [ ] Borrado automático de audios > 90 días.

---

## Referencias

- Plan original: [`.cursor/plans/field-proactivo-whatsapp_029ca33e.plan.md`](../../.cursor/plans/field-proactivo-whatsapp_029ca33e.plan.md)
- Arquitectura workspace: [ARCHITECTURE.md](../ARCHITECTURE.md)
- Investigación cross-repo: [CROSS-REPO-QUERIES.md](../CROSS-REPO-QUERIES.md)
