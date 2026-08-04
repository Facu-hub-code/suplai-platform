# Spec 028 — Memoria de cliente (`metadata`) desde el mapa comercial

**Estado:** Implemented (v1) — **parcialmente supersedido por [SPEC-029](029-client-memory-wizard-agendas-1a1.md)** para wizard multi-paso (preferred_contact, purchase_frequency, top_products) y nearby con tipos configurables.  
**Fecha:** 2026-08-03  
**Tipo:** Cross-repo (backend + backoffice; consumo opcional en estrategias)  
**Relaciona:** Mapa comercial / inteligencia territorial; señales `nearby_places` de estrategias (SPEC-026); SPEC-029

**Ramas:**

| Repo | Rama |
|------|------|
| `backend-supabase` | `feat/client-memory-map` |
| `product-management-app` | `feat/client-memory-map` |
| `suplai-platform` | `feat/client-memory-map` |

---

## 1) Objetivo

Permitir enriquecer y mostrar **contexto de lugares cercanos** (Google Places Nearby) por cliente, persistido en `clients.metadata.nearby`, desde el mapa comercial:

- Acción **1:1** por cliente.
- Acción **masiva** sobre clientes con coordenadas **dentro de la geo-zona seleccionada**.
- Feedback de espera con **Lottie + progreso i/N**.
- En zoom alto (≥ 15), cards compactas en markers con 1–2 places.

## 2) Decisiones de diseño técnico

| Tema | Decisión | Por qué (alternativa descartada) |
|------|----------|----------------------------------|
| Alcance masivo | Solo clientes **dentro de la zona seleccionada** | Reutiliza `selectedZone` + `pointInZone`. Descartado: enrich de todo el tenant (costo Places alto). |
| Persistencia | `clients.metadata` jsonb, clave `nearby` | Flexible para señales futuras; sin tabla hija en v1. |
| Shape `nearby` | `{ places, lat, lon, source, updated_at }` | Estable para UI y para el resolver de estrategias. |
| Orquestación | Loop en el **cliente** (concurrency 2) sobre `POST .../enrich-memory` | Evita jobs/SSE en v1. Batch thin opcional (máx 20) en backend. |
| Progreso UI | Overlay Lottie (`synthwave.json`, patrón ERP sync) | Ya existe en BO; UX consistente. |
| Cache en estrategias | `resolve_nearby_places` lee `metadata.nearby` si fresco (&lt; 30 días) cuando hay 1 `client_id` | Evita Places live en personalización 1:1. Descartado: siempre live (caro / lento). |
| VIP en cards | Badge desde `clientCategory` / `etiqueta` existentes | Sin scoring VIP nuevo en v1. |

## 3) Alcance explícito

**Incluido (v1)**

- Migración `sql/93_clients_metadata.sql`.
- `POST /{schema}/clients/{id}/enrich-memory` (+ batch thin).
- Payload de mapa / map-details con `metadata.nearby`.
- BO: botón zona, overlay Lottie, acción 1:1, cards zoom ≥ 15, i18n ES/PT/EN.
- Preferencia de cache en `resolve_nearby_places`.

**Incluido (v1.1 — tipos de consumo + hints)**

- Nearby Search **tipado** (school, university, supermarket, restaurant, pharmacy, gym).
- Persistencia enriquecida: `place_id`, `primary_type`, `angle`, `product_hints`.
- Theme `nearby_map` usa `nombre (ángulo)` y hints si no hay estacionalidad.
- Filtrado de ruido (bank, route, lodging, etc.).

**Fuera de alcance**

- Weather / calendar en `metadata`.
- Job async Railway / cola.
- Edición manual del JSON en UI.
- Enrich sin zona sobre todo el tenant.

## 4) Orden de implementación

1. Migración + API unitario (+ batch thin).  
2. BO zona + Lottie + loop.  
3. Acción 1:1 (sidebar + perfil).  
4. Cards zoom + `metadata` en fetch del mapa.  
5. Cache en `resolve_nearby_places`.  
6. Spec + smoke manual.

**Merge sugerido:** backend (migración ya aplicada en Suplai-east) → backoffice → platform docs.

## 5) Migración de base de datos

- Archivo: `backend-supabase/sql/93_clients_metadata.sql`.
- Cambio: `ALTER TABLE {schema}.clients ADD COLUMN metadata jsonb NOT NULL DEFAULT '{}'::jsonb` en schemas de distribuidoras activas.
- Seed/backfill: no (se llena on-demand desde el mapa).
- Rollback: `ALTER TABLE ... DROP COLUMN metadata` por schema (pierde memoria enriquecida).
- **Estado:** aplicada en proyecto `cvlbietibaaehgeimxgw` (30 schemas con columna al momento del deploy).

## 6) Plan de prueba en CI/CD

- Unitarios backend: `tests/test_client_memory.py` (frescura de `nearby`).
- Checks existentes de client-locations / mapa deben seguir verdes (payload aditivo).
- Gap: no hay E2E automatizado de Places (depende de API key); smoke manual obligatorio antes del merge.

## 7) Plan de prueba humana (antes del PR)

**Servicios**

| Servicio | Puerto |
|----------|--------|
| Backend | `8000` |
| Backoffice | `3000` (Maps SDK) |

```bash
# Terminal 1
cd backend-supabase && source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2
cd product-management-app
BACKEND_URL=http://localhost:8000 npm run dev
```

**Tenant:** uno con clientes geolocalizados y al menos una `geo_zone` (ej. `demo` / `del_corro`).

**Checklist**

1. Abrir mapa comercial en `http://localhost:3000` (no otro puerto).
2. Seleccionar una zona con clientes → **Enriquecer memoria (zona)** → ver Lottie y progreso i/N → toast resumen.
3. Zoom ≥ 15 → hover en marker → card con nombre, VIP/etiqueta si aplica, 1–2 places.
4. Abrir perfil de un cliente → **Enriquecer memoria** → places visibles en header.
5. (Opcional) Verificar en BD: `clients.metadata->'nearby'` tiene `updated_at` y `places`.
6. (Opcional) Llamar personalización estrategias 1:1 / `resolve_nearby_places` y confirmar `from_cache: true` si fresco.

## 8) Criterios de aceptación

- [x] Columna `metadata` existe en tenants activos.
- [x] Endpoint unitario persiste `metadata.nearby` vía Places.
- [x] BO enriquece zona con progreso Lottie.
- [x] Acción 1:1 en perfil/sidebar.
- [x] Cards en zoom alto leen `metadata.nearby`.
- [x] Resolver nearby prefiere cache &lt; 30 días.
