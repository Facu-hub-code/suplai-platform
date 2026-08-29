# SPEC-036 — Onboarding guiado post-registro (demo agéntica)

**Estado:** In progress  
**Fecha:** 2026-08-28  
**Repos:** `backend-supabase`, `product-management-app`, `suplai-platform` (este spec)  
**Ramas:** `feat/guided-onboarding` en cada repo  

---

## 1) Objetivo

Que un tenant recién registrado **no entre a un ecosistema vacío**. Tras el alta, un recorrido guiado arma una **demo agéntica**: primero el catálogo mock (productos, categorías, listas de precios) a partir de Excel, PDF, URL o invención por rubro. El usuario revisa un preview y confirma. Clientes y el resto del pipeline quedan para la siguiente entrega.

Criterios de aceptación:

- El signup pide nombre de persona, nombre de empresa, ubicación (Google Maps) y teléfono `549…`. **No** pide email ni contraseña.
- El owner queda con `admin@{schema_name}.com` / `Suplai2026`, se auto-loguea y ve esas credenciales una vez.
- `schema_name` no contiene la palabra `distribuidora`. Si el slug ya existe, el siguiente es `{slug}_01`, luego `_02`.
- Tras el alta se entra a `/onboarding` (paso Productos), no al dashboard vacío.
- El catálogo se **propone** (job), se **previsualiza** y recién se **persiste** al confirmar, con `is_mock=true` y 4 listas (1.00 / 1.15 / 0.90 / 0.85).
- Si Excel/PDF/URL fallan, el flujo **no se traba**: se infiere rubro (empresa + ubicación + host) y se inventan ~30 SKUs coherentes.
- Tenants existentes siguen logueándose con su email/password de siempre.

---

## 2) Decisiones de diseño técnico

| Decisión | Elección | Por qué | Alternativa descartada |
|----------|----------|---------|------------------------|
| Wizard vs BulkUploadWizard | Wizard propio en `/onboarding` | El bulk operativo no setea `is_mock`, no inventa listas/taxonomía y pide mapeo manual (fricción) | Reusar `BulkUploadWizard` |
| Propuesta vs persistencia | Job `propose` → preview → `confirm` | El usuario pidió ver SKUs/categorías/listas y poder regenerar antes de guardar | Guardar en caliente y editar después |
| Credenciales | Generadas en backend (`admin@{schema}.com` / `Suplai2026`) | Evitar que olviden una password que ellos eligieron; el login posterior usa esas claves | Seguir pidiendo email/password en el form |
| Colisión de schema | Sufijo `_01`, `_02` | Pedido explícito (`del_corro_01`); el `_2` actual no coincide | Seguir con `_2`, `_3` |
| Slug | Strip `distribuidora(s)`, `distribucion(es)`, `s.a.`, `srl`; fallback `empresa` | Evitar schemas `distribuidora_acme`; nunca usar la palabra como ident | Slug literal del nombre comercial |
| Ubicación | Places Autocomplete (`HqLocationInput`) → `metadata.hq` + `ciudad_base` | Ya existe el control; el mapa comercial y la red futura reutilizan HQ | Texto libre de ciudad |
| Jobs de catálogo | Tabla `public.onboarding_catalog_jobs` | El JSON de ~30 SKUs inflaría `distribuidoras.metadata` | Solo jsonb en metadata |
| Parse + LLM | Heurística primero; LLM enriquece; si falla, inventar | “No frenar” es más importante que extraer el 100% del PDF/JS-site | 400 si el parse falla |
| Async | `BackgroundTasks` + poll 1.5s | Mismo patrón que vectorize/ERP; jobs cortos | Cola Redis/Celery para v1 |
| Taxonomía | `propose-taxonomy` + `apply` en background al confirmar | El preview ya muestra categorías de la propuesta; tags RAG no bloquean el click | Hacer esperar la taxonomía en el confirm |

---

## 3) Alcance explícito

### Incluido (v1)

- Signup nuevo: persona, empresa, Maps, teléfono 549, credenciales fijas, auto-login, tarjeta “guardá esto”.
- Slug sin “distribuidora” + colisión `_01`.
- Ruta `/onboarding` paso Productos: Excel/CSV, PDF, URL, inventar por rubro.
- Preview + confirmar / regenerar.
- Persistencia mock: productos, 4 listas, precios, taxonomía y vectorize en background.
- `metadata.guided_onboarding` (`current_step`, `completed`).
- Teaser “siguiente: clientes” hacia el dashboard (sin implementar clientes).
- Redirect post-login a `/onboarding` si el paso productos no está completo.
- Tests unitarios de slug, teléfono, propose→confirm con LLM mockeado.

### Fuera de alcance (v1)

- Paso clientes / vendedores / pedidos / conversaciones / Field (siguiente iteración).
- Imágenes reales de producto (placeholder por rubro alcanza).
- Enriquecimiento web masivo F1.2 (Serper).
- Cambiar login de tenants ya existentes.
- Purga mock (F10) desde la UI.
- UI admin de provisioning (`POST /admin/provision/tenant`).

---

## 4) Orden de implementación

| Orden | Repo | Rama | Qué | Dependencia |
|-------|------|------|-----|-------------|
| 1 | `suplai-platform` | `feat/guided-onboarding` | Este spec | — |
| 2 | `backend-supabase` | `feat/guided-onboarding` | Tenancy, signup, SQL jobs, propose/confirm, tests | Spec |
| 3 | `product-management-app` | `feat/guided-onboarding` | Form signup, credenciales, `/onboarding` | Merge **después** de backend (API nueva) |

**Merge humano:** backend (migración + API) → backoffice. El spec puede mergear en cualquier momento.

---

## 5) Migración de base de datos

Nueva tabla en `public` (no toca schemas tenant):

```sql
CREATE TABLE public.onboarding_catalog_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  distribuidora_id uuid NOT NULL REFERENCES public.distribuidoras(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'ready', 'failed', 'confirmed')),
  source text NOT NULL
    CHECK (source IN ('excel', 'pdf', 'url', 'invent')),
  source_meta jsonb NOT NULL DEFAULT '{}',
  proposal jsonb,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
```

- **Seed / backfill:** ninguno.
- **Tenant tables:** sin columnas nuevas. Se reutiliza `is_mock` donde exista (migración platform `20260615_add_is_mock_columns_demo_and_tenants.sql`). Si un tenant clonado aún no tiene la columna, el confirm inserta sin ella.
- **`public.distribuidoras.metadata`:** claves nuevas `hq`, `ciudad_base`, `guided_onboarding` (jsonb existente, sin ALTER).
- **Orden:** aplicar `sql/109_onboarding_catalog_jobs.sql` en Supabase **antes** de usar propose/confirm en un entorno real.
- **Rollback:** `DROP TABLE public.onboarding_catalog_jobs;` Metadata huérfana es inofensiva.

---

## 6) Contrato API

### Signup — `POST /distribuidoras/signup`

Request (ya no exige email/password):

- `profile_nombre`
- `contact_phone` (dígitos, `^549\d{8,12}$`)
- `hq`: `{ label, latitude, longitude }`
- `distribuidora.nombre`

Response: session + profile + distribuidora + `generated_credentials: { email, password }`.

### Onboarding

- `GET /{schema}/onboarding/status` → `{ current_step, completed, has_products }`
- `POST /{schema}/onboarding/catalog/propose` (multipart o JSON) → `{ job_id, status }`
- `GET /{schema}/onboarding/catalog/jobs/{id}` → `{ status, proposal?, error? }`
- `POST /{schema}/onboarding/catalog/confirm` `{ job_id, products? }` → conteos insertados

Fuentes `source`: `excel` | `pdf` | `url` | `invent`.

---

## 7) Plan de prueba en CI/CD

- **Backend:** pytest
  - `slugify_schema_name("Distribuidora Del Corro") == "del_corro"`
  - colisión → `_01`
  - teléfono inválido (sin 549) → 422
  - propose invent (LLM mock) → job `ready` con SKUs + 4 listas
  - confirm persiste productos `is_mock` (query mockeada)
- **Backoffice:** `tsc` / build de las páginas tocadas; no hay suite e2e de signup hoy (gap aceptable: verificación humana).
- Checks existentes de cada PR deben quedar verdes.
- Smoke de migración: el SQL es `CREATE TABLE IF NOT EXISTS` (idempotente).

---

## 8) Plan de prueba humana (antes del PR)

Servicios: backend `localhost:8000`, backoffice `localhost:3000` (Maps).

1. Signup con empresa que ya exista (probar `_01`), Maps (Córdoba), teléfono `54911…`.
2. Ver tarjeta `admin@{schema}.com` / `Suplai2026` y poder copiar. Continuar a `/onboarding`.
3. Productos: (a) Excel/CSV chico, (b) PDF, (c) URL que falle → inventar, (d) sin archivo + rubro “fiambres”.
4. Preview → Regenerar → Confirmar. Ver productos y 4 listas en el backoffice. Filas nuevas con `is_mock` si la columna existe.
5. Logout y login con las credenciales generadas.
6. Tenant viejo: login con email propio sigue igual; no entra a `/onboarding` si ya tiene catálogo / paso completo.
