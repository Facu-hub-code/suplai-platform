# Maps ICP Prospección Implementation Plan

> **For agentic workers:** Execute inline in this session (tasks are tightly coupled: backend → backoffice → agent). User asked to implement immediately. Do not commit unless the user requests it.

**Goal:** Wizard ICP en el mapa comercial (Places → tildar → HSM ahora/agenda) + tool `refer_decision_maker` en el agente comercial.

**Architecture:** Backend expande canales canónicos a queries Places, da de alta el lote y envía/agenda. Config de plantillas en `metadata.prospeccion`. El agente llama `POST /{schema}/pdv/{id}/refer-decision-maker` para swap primario + HSM decisor.

**Tech Stack:** FastAPI/asyncpg, Next.js backoffice, LangGraph agent tools, WhatsApp Cloud API templates.

## Global Constraints

- Spec: `docs/specs/071-maps-icp-prospeccion-decisor.md`
- Pooler 6543, `statement_cache_size=0`; no loops N+1 de queries
- Tope 40 Places, 20 envíos ahora
- Tool opt-in `refer_decision_maker`
- Copilot 069 no se toca
- Ramas: `feat/maps-icp-prospeccion` en platform, backend, backoffice, agent
- No implementar en `main`/`master`

---

### Task 1: Backend mapping + white-zones ICP

**Files:**
- Create: `backend-supabase/services/prospeccion_channels.py`
- Modify: `backend-supabase/services/geo_zones_service.py`
- Test: `backend-supabase/tests/test_prospeccion_channels.py`, `tests/test_geo_zones.py`

**Produces:** `expand_place_queries(canales, business_types) -> list[str]`, ranking helper, white-zones body accepts `canales`/`tamano_pdv`.

### Task 2: Backend config slots prospección

**Files:**
- Modify: `models/distribuidoras_config.py`, `routers/distribuidoras_config.py`
- Test: `tests/test_distribuidoras_config.py`

**Produces:** `GET/PATCH /{schema}/distribuidora/config/prospeccion-meta-plantillas`

### Task 3: Backend outreach

**Files:**
- Create: `services/prospeccion_outreach_service.py`
- Modify: `routers/geo_zones.py`
- Test: `tests/test_prospeccion_outreach.py`

**Produces:** `POST /{schema}/geo-zones/{zone_id}/prospects/outreach`

### Task 4: Backend refer-decision-maker

**Files:**
- Create/modify: `services/pdv_service.py`, `routers/pdv.py`
- Test: `tests/test_refer_decision_maker.py`

**Produces:** `POST /{schema}/pdv/{pdv_id}/refer-decision-maker`

### Task 5: Backoffice wizard + slots UI

**Files:**
- Replace/extend: `WhiteZonesModal.tsx`, `commercial-map-context.tsx`, i18n
- Create: proxies outreach + prospeccion-meta-plantillas
- Modify: `meta-templates-modal.tsx`

### Task 6: Agent tool

**Files:**
- Create: `app/agent/tools/refer_decision_maker.py`, `app/integrations/pdv_refer_proxy.py`
- Modify: registry, tool_activation_policy, prompt defaults
- Test: `tests/test_refer_decision_maker.py`
