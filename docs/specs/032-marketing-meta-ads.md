# Spec 032 — Módulo Marketing Meta Ads (Click-to-WhatsApp)

**Estado:** In progress  
**Fecha:** 2026-08-05  
**Tipo:** Cross-repo (platform docs + backend + agent + backoffice)  
**Relaciona:** geo_zones (territorio), promociones_semanales, WhatsApp Cloud API / CTWA

**Ramas:**

| Repo | Rama |
|------|------|
| `suplai-platform` | `docs/marketing-meta-ads` |
| `backend-supabase` | `feat/marketing-meta-ads` |
| `agente-conversacional-multi_tenant` | `feat/marketing-ctwa-attribution` |
| `product-management-app` | `feat/marketing-meta-ads` |

---

## 1) Objetivo

Agregar al backoffice un módulo **Marketing** con tres pantallas (editor de creatividades, creador de campañas, dashboard) para publicar anuncios Click-to-WhatsApp vía Marketing API de Meta, reutilizando zonas de cobertura y promociones existentes, y midiendo el embudo hasta pedido con atribución `ctwa_clid`.

---

## 2) Decisiones de diseño técnico

| Tema | Decisión | Por qué (alternativa descartada) |
|------|----------|----------------------------------|
| Promos vs zonas | Independientes: zona = targeting Meta; promos = contexto del editor (copy/foto) | No hay FK zona↔promo; filtrar por grupos/listas mentiría al usuario. |
| Credenciales Meta Ads | Secrets por tenant: `meta_ads.ad_account_id`, `meta_ads.page_id`, `meta_ads.access_token` | El token WhatsApp no garantiza `ads_management`. Descartado: reutilizar `whatsapp.long_live_token` o Ad Account única de plataforma. |
| UI | Sección sidebar + 3 Tabs en SPA backoffice | Patrón `CommercialDashboard`; no app separada. |
| Geo → Meta | Polígonos `geo_zones` → `custom_locations` (centroide + radio bbox) | Meta no acepta MultiPolygon PostGIS. |
| Atribución | Capturar `ctwa_clid` en webhook del agente → `core.conversation_ad_attribution` | Sin esto no hay cruzamiento conversación→pedido. |
| Objetivo campaña | `OUTCOME_ENGAGEMENT` + ad set `destination_type=WHATSAPP` | Doc oficial CTWA Graph v26. |
| Motor de reglas | Fuera de v1 (nota / stub en docs) | Misma lógica futura que re-targeting; no implementar ahora. |
| Imagen | Upload a bucket `meta_ads_creatives` + `adimages` al publicar | Sin generación IA en v1. |

---

## 3) Alcance explícito

### Incluido (v1)

- Nav **Marketing** con Tabs: Creatividades | Campañas | Dashboard.
- CRUD `marketing_creative_packages` (zonas multi, promos multi contexto, imagen, copy, headline, CTA, welcome message, draft/ready).
- CRUD + publish `marketing_campaigns` (budget daily/lifetime, fechas, subasta, IDs Meta).
- Mapa read-only de zonas del package.
- Insights Meta por ad set + funnel propio (impresiones→clics→conversaciones→pedidos).
- Performance por zona / promo; costo/conversación; costo/pedido; alertas simples.
- Docs oficiales Meta en `docs/integrations/meta-marketing-api/`.

### Fuera de alcance (v1)

- Motor de reglas / auto-mutación de campañas.
- Reach & Frequency.
- Generación de imagen con IA.
- OAuth UI Meta (secrets por admin/ops).
- Carousel / Advantage+ catalog complejo.

---

## 4) Orden de implementación

1. Platform: este spec + docs Meta.  
2. Backend: migración SQL + bucket + API + cliente Graph.  
3. Agent: persistencia `ctwa_clid` / referral.  
4. Backoffice: UI + proxies.

**Merge:** platform docs → backend → agent → backoffice.

---

## 5) Migración de base de datos

Migración: `backend-supabase/sql/96_marketing_meta_ads.sql`.

| Objeto | Notas |
|--------|-------|
| `{tenant}.marketing_creative_packages` | `zona_ids`, `promo_ids`, copy, imagen, status |
| `{tenant}.marketing_campaigns` | FK package + IDs Meta + budget/fechas |
| `core.conversation_ad_attribution` | `ctwa_clid`, referral raw, conversation_id |
| Bucket Storage | `meta_ads_creatives` (crear en Supabase) |
| Secrets | `meta_ads.*` en `public.tenant_secrets` (sin DDL; ops) |

**Rollback:** drop tablas nuevas por tenant + drop `core.conversation_ad_attribution` (sin tocar zonas/promos).

**Sin migración:** N/A — sí hay migración.

---

## 6) Plan de prueba en CI/CD

- Unit tests backend: cliente Meta (httpx mock), geo→custom_locations, `page_welcome_message`, orquestación publish.
- Unit tests agent: extractor referral / insert atribución (mock conn).
- Checks existentes de cada PR deben quedar verdes.
- Gap: no hay e2e Meta real en CI (sandbox humano).

---

## 7) Plan de prueba humana (antes del PR)

1. Backend `uvicorn` en `:8000`; backoffice en `:3000` (`BACKEND_URL=http://localhost:8000`).
2. Tenant con secrets `meta_ads.*` de sandbox + Page con WhatsApp linked.
3. Marketing → Creatividades: elegir zonas + promos, subir imagen, copy, guardar `ready`.
4. Campañas: seleccionar package, budget/fechas, ver mapa RO, publish **PAUSED**.
5. Verificar IDs en Meta Ads Manager.
6. Simular inbound WhatsApp con `referral.ctwa_clid` → fila en `core.conversation_ad_attribution`.
7. Dashboard: funnel + tabla campañas; alerta zona sin actividad si aplica.

---

## 8) Criterios de aceptación

- Desde backoffice se crea un creative package y se publica una campaña CTWA atada a zonas reales.
- Los IDs Meta quedan persistidos en `marketing_campaigns`.
- El dashboard muestra insights Meta y pedidos atribuidos vía `ctwa_clid` cuando hay datos.
- El motor de reglas no está implementado; queda documentado como futuro.

---

## Referencias

- [Click to WhatsApp](https://developers.facebook.com/documentation/ads-commerce/marketing-api/ad-creative/messaging-ads/click-to-whatsapp)
- [Marketing API](https://developers.facebook.com/documentation/ads-commerce/marketing-api)
- Local: `docs/integrations/meta-marketing-api/`
