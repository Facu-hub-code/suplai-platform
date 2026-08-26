# Cianbox pull productos e imágenes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Traer el catálogo Cianbox a `erp_products_raw`, reconstruir `product_id_map` para el push de pedidos, y copiar la primera imagen a Storage/`productos.image_url` sin volcar el ERP al catálogo WhatsApp de Córdoba Frost.

**Architecture:** Reusar `load_products_to_raw` + botón backoffice existente. Implementar `CianboxConnector.fetch_products()` (hoy `return []`). Un servicio aparte descarga fotos (no va en el job 6h). El mapa SKU→id se mergea en `erp.credentials` cifrado. Spec: `docs/specs/036-cianbox-pull-productos-imagenes.md`.

**Tech Stack:** Python 3 / FastAPI backend, httpx, asyncpg, Supabase Storage, Next.js backoffice.

## Global Constraints

- Tenant piloto: `cordoba_frost`. Conector: `cianbox`. No tocar schemas de otros tenants.
- Ningún job automático INSERT en `{schema}.productos`. Promote masivo **prohibido** en CF v1.
- WhatsApp sigue vendiendo solo combos con `en_catalogo=true`; este trabajo no cambia ese flag.
- Pooler Postgres puerto `6543`; `statement_cache_size=0`.
- No loguear tokens Cianbox, `erp.credentials` ni URLs firmadas.
- Backoffice local: puerto `3000` + backend `8000`.
- Commits solo en ramas feature (`backend/feat/cianbox-pull-productos-imagenes`, `backoffice/feat/cianbox-sync-product-images`). Nunca en `main`.
- API Cianbox: `GET /api/v2/productos` paginado, campos `id,producto,codigo_interno,imagenes,stock_total,vigente`.

## File map

| File | Responsabilidad |
|---|---|
| `backend/erp/connectors/cianbox.py` | Paginación + mapper producto |
| `backend/erp/services/erp_cianbox_product_map.py` | Merge `product_id_map` en secrets |
| `backend/erp/services/erp_product_image_sync.py` | Download → Storage → `image_url` |
| `backend/sql/106_cianbox_pull_products.sql` | `pull_products: true` |
| `backend/routers/erp.py` | `POST /sync-product-images` |
| `backend/tests/erp/connectors/test_cianbox_connector.py` | Fetch / mapper |
| `backend/tests/erp/services/test_cianbox_product_id_map.py` | Merge mapa |
| `backend/tests/erp/services/test_erp_product_image_sync.py` | Imágenes |
| `backend/docs/external/cianbox_erp.md` | Contrato GET productos |
| `backoffice/components/erp-integrations-section.tsx` | Botón sync imágenes |
| `backoffice/app/api/erp/sync-product-images/route.ts` | Proxy |
| `backend/scripts/dev/probe_cianbox_products.py` | Probe read-only |

---

### Task 0: Probe live Cianbox (read-only, bloqueante)

**Files:**
- Create: `backend-supabase/scripts/dev/probe_cianbox_products.py`

**Interfaces:**
- Consumes: `erp.credentials` cifradas + `CREDENTIALS_MASTER_KEY` (mismo patrón que `implementacion/cordoba_frost/scripts/ping_notif_vendedor.py`).
- Produces: conteo de páginas, sample de 5 SKUs, si existen `COM-COR-01826` / `COM-HEL-INICIAL` como `codigo_interno`, cuántos tienen `imagenes`.

- [ ] **Step 1: Escribir el probe**

Script asyncpg + urllib/httpx. **No** imprimir token. Output permitido:

```
pages=N products=M with_codigo_interno=X with_images=Y
sample: id=… sku=… images=0|1
match COM-COR-01826: yes/no id=…
match COM-HEL-INICIAL: yes/no id=…
```

Auth: reutilizar login `POST /auth/credentials` del conector (copiar `_fetch_tokens` mínimo, no importar FastAPI).

Paginación: `limit=50`, loop `page=1..total_pages` con tope 200 páginas.

- [ ] **Step 2: Correr contra cordobafrost**

```bash
cd backend-supabase
python scripts/dev/probe_cianbox_products.py --schema cordoba_frost
```

Expected: `products>0`. Si `match COM-HEL-INICIAL: no`, el mapa no se auto-completa para helados: hay que mapear a mano o por nombre en Task 3 (fallback por `producto` normalizado solo si es único).

- [ ] **Step 3: Pegar el resumen (sin secretos) en el PR / chat**

Si el probe falla (401/404 de `/productos`), **STOP** — no implementar fetch a ciegas.

- [ ] **Step 4: Commit (backend)**

```bash
git add scripts/dev/probe_cianbox_products.py
git commit -m "$(cat <<'EOF'
chore: add read-only Cianbox product probe for Córdoba Frost

EOF
)"
```

---

### Task 1: Mapper puro Cianbox JSON → Product

**Files:**
- Modify: `backend-supabase/erp/connectors/cianbox.py`
- Test: `backend-supabase/tests/erp/connectors/test_cianbox_connector.py`

**Interfaces:**
- Produces: `normalize_cianbox_product(row: dict) -> Product | None`

- [ ] **Step 1: Test que falla**

Agregar en `test_cianbox_connector.py`:

```python
from erp.connectors.cianbox import normalize_cianbox_product

def test_normalize_cianbox_product_uses_codigo_interno():
    p = normalize_cianbox_product({
        "id": 1500,
        "producto": "Combo 2 SuperMedialuna",
        "codigo_interno": "COM-COR-01827",
        "stock_total": 12,
        "vigente": True,
        "imagenes": ["https://cianbox.org/x/a.jpg"],
        "categoria": "Combos",
        "marca": "CF",
    })
    assert p["sku"] == "COM-COR-01827"
    assert p["nombre"] == "Combo 2 SuperMedialuna"
    assert p["cantidad"] == 12
    assert p["extra"]["cianbox_id"] == 1500
    assert p["extra"]["image_src"] == "https://cianbox.org/x/a.jpg"
    assert p["extra"]["vigente"] is True


def test_normalize_cianbox_product_fallback_sku():
    p = normalize_cianbox_product({"id": 9, "producto": "Sin codigo", "codigo_interno": ""})
    assert p["sku"] == "CBX-9"


def test_normalize_cianbox_product_skips_without_id():
    assert normalize_cianbox_product({"producto": "x"}) is None
```

- [ ] **Step 2: Correr tests (FAIL)**

```bash
cd backend-supabase
pytest -q tests/erp/connectors/test_cianbox_connector.py::test_normalize_cianbox_product_uses_codigo_interno -v
```

Expected: `ImportError` o `normalize_cianbox_product` no existe.

- [ ] **Step 3: Implementar mapper**

En `cianbox.py` (funciones de módulo, no métodos, para testear sin HTTP):

```python
def normalize_cianbox_product(row: dict) -> Product | None:
    if not isinstance(row, dict):
        return None
    cid = row.get("id")
    try:
        cianbox_id = int(cid)
    except (TypeError, ValueError):
        return None
    codigo = str(row.get("codigo_interno") or "").strip()
    sku = codigo or f"CBX-{cianbox_id}"
    imagenes = row.get("imagenes") if isinstance(row.get("imagenes"), list) else []
    image_src = ""
    for img in imagenes:
        if isinstance(img, str) and img.strip():
            image_src = img.strip()
            break
    stock = row.get("stock_total")
    try:
        cantidad = max(0, int(stock or 0))
    except (TypeError, ValueError):
        cantidad = 0
    return {
        "sku": sku,
        "nombre": str(row.get("producto") or sku)[:500],
        "cantidad": cantidad,
        "extra": {
            "cianbox_id": cianbox_id,
            "codigo_interno": codigo or None,
            "vigente": bool(row.get("vigente", True)),
            "image_src": image_src or None,
            "categoria": row.get("categoria"),
            "marca": row.get("marca"),
        },
    }
```

- [ ] **Step 4: Tests PASS**

```bash
pytest -q tests/erp/connectors/test_cianbox_connector.py::test_normalize_cianbox_product_uses_codigo_interno tests/erp/connectors/test_cianbox_connector.py::test_normalize_cianbox_product_fallback_sku tests/erp/connectors/test_cianbox_connector.py::test_normalize_cianbox_product_skips_without_id -v
```

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat: map Cianbox product rows to ERP Product DTO

EOF
)"
```

---

### Task 2: `fetch_products` paginado

**Files:**
- Modify: `backend-supabase/erp/connectors/cianbox.py` (`fetch_products` ~línea 596)
- Test: `backend-supabase/tests/erp/connectors/test_cianbox_connector.py`

**Interfaces:**
- Consumes: `normalize_cianbox_product`, `_ensure_token` existente.
- Produces: `async def fetch_products(self) -> list[Product]`

- [ ] **Step 1: Test paginación con httpx mock**

Patrón igual a `test_create_client_success`: mockear `httpx.AsyncClient.get`.

Página 1: `total_pages=2`, un producto. Página 2: otro producto. Assert `len(result)==2` y un solo GET extra.

También: HTTP 401 en el primer GET → llama `_refresh_access_token` y reintenta una vez (si el conector ya hace eso en POST, replicar en GET).

- [ ] **Step 2: FAIL**

```bash
pytest -q tests/erp/connectors/test_cianbox_connector.py::test_fetch_products_paginates -v
```

- [ ] **Step 3: Implementar `fetch_products`**

Reemplazar `return []`. Loop:

```python
PAGE_LIMIT = 50
MAX_PAGES = 200

async def fetch_products(self) -> list[Product]:
    access_token = await self._ensure_token()
    out: list[Product] = []
    seen_skus: set[str] = set()
    page = 1
    total_pages = 1
    fields = "id,producto,codigo_interno,codigo_barras,stock_total,vigente,descripcion,imagenes,categoria,marca"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        while page <= total_pages and page <= MAX_PAGES:
            url = (
                f"{self._api_url}/productos"
                f"?access_token={access_token}&page={page}&limit={PAGE_LIMIT}&fields={fields}"
            )
            resp = await client.get(url)
            if resp.status_code == 401:
                await self._refresh_access_token()
                access_token = await self._ensure_token()
                url = (
                    f"{self._api_url}/productos"
                    f"?access_token={access_token}&page={page}&limit={PAGE_LIMIT}&fields={fields}"
                )
                resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if str(data.get("status") or "").lower() != "ok":
                raise CianboxPushError(f"Cianbox productos status={data.get('status')}")
            try:
                total_pages = max(1, int(data.get("total_pages") or 1))
            except (TypeError, ValueError):
                total_pages = 1
            for row in data.get("body") or []:
                product = normalize_cianbox_product(row)
                if not product or product["sku"] in seen_skus:
                    continue
                seen_skus.add(product["sku"])
                out.append(product)
            page += 1
    return out
```

Log estructurado `CIANBOX_FETCH_PRODUCTS_SUCCESS` con `count` (sin body).

- [ ] **Step 4: PASS + regresión push**

```bash
pytest -q tests/erp/connectors/test_cianbox_connector.py -v
```

Expected: todos verdes (push no se rompe).

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat: pull Cianbox product catalog into fetch_products

EOF
)"
```

---

### Task 3: Merge `product_id_map` tras load

**Files:**
- Create: `backend-supabase/erp/services/erp_cianbox_product_map.py`
- Modify: `backend-supabase/erp/services/erp_sync_service.py` (`load_products_to_raw`, después del INSERT)
- Test: `backend-supabase/tests/erp/services/test_cianbox_product_id_map.py`

**Interfaces:**
- Produces: `merge_product_id_map(existing: dict[str, int], products: list[Product]) -> dict[str, int]`
- Produces: `async def persist_cianbox_product_id_map(schema: str, products: list[Product]) -> int` (claves nuevas o cambiadas)

Reglas de merge:

1. Para cada product con `extra.cianbox_id`, set `map[sku] = id`.
2. No borrar claves que no vinieron en este pull (`ENVIO-DOM`, mapeos manuales).
3. Si una clave existe y el id cambió, actualizar (Cianbox re-creó el artículo).

- [ ] **Step 1: Tests unitarios del merge (sin DB)**

```python
from erp.connectors.base import Product
from erp.services.erp_cianbox_product_map import merge_product_id_map

def test_merge_keeps_manual_keys():
    existing = {"ENVIO-DOM": 1503, "COM-COR-01826": 1}
    products: list[Product] = [{
        "sku": "COM-COR-01826",
        "nombre": "x",
        "cantidad": 0,
        "extra": {"cianbox_id": 1501},
    }]
    out = merge_product_id_map(existing, products)
    assert out["ENVIO-DOM"] == 1503
    assert out["COM-COR-01826"] == 1501
```

- [ ] **Step 2: FAIL**

```bash
pytest -q tests/erp/services/test_cianbox_product_id_map.py -v
```

- [ ] **Step 3: Implementar merge + persist**

`persist_cianbox_product_id_map`:

1. `get_connector_for_schema` / decrypt `erp.credentials` (extraer helper `_load_erp_credentials(schema) -> dict` si no existe; no duplicar crypto).
2. Solo si `connector == cianbox`.
3. `credentials["product_id_map"] = merge_product_id_map(...)`.
4. Re-cifrar con el mismo `INSERT ... ON CONFLICT` de `save_erp_config` **sin** pisar `base_url` ni `push_orders_enabled`. Preferir función nueva `update_erp_credentials(schema, credentials: dict)` que solo toca `tenant_secrets`.

Hook en `load_products_to_raw` después del `executemany`, `if connector type cianbox`.

- [ ] **Step 4: PASS**

```bash
pytest -q tests/erp/services/test_cianbox_product_id_map.py tests/erp/services/test_erp_sync_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat: rebuild Cianbox product_id_map from pulled catalog

EOF
)"
```

---

### Task 4: Capability `pull_products` + job 6h

**Files:**
- Create: `backend-supabase/sql/106_cianbox_pull_products.sql`
- Modify: `backend-supabase/sql/102_seed_cianbox_connector_profile.sql` (para clones futuros: `pull_products: true`)
- Modify: `backend-supabase/docs/external/cianbox_erp.md` (sección GET productos)

**Interfaces:**
- El job en `erp_sync_service.py` ~2011 ya llama `load_products_to_raw` si `capability(..., "pull_products")`.

- [ ] **Step 1: Migración**

```sql
UPDATE core.erp_connector_profiles
SET capabilities = capabilities || '{"pull_products": true}'::jsonb,
    updated_at = now()
WHERE connector = 'cianbox';
```

- [ ] **Step 2: Aplicar en el entorno de test / documentar en PR que ops la corre en prod**

No hay test de SQL. Verificar con:

```sql
SELECT capabilities->>'pull_products' FROM core.erp_connector_profiles WHERE connector = 'cianbox';
```

Expected: `true`.

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat: enable Cianbox pull_products capability

EOF
)"
```

---

### Task 5: Sync de imágenes (servicio + endpoint)

**Files:**
- Create: `backend-supabase/erp/services/erp_product_image_sync.py`
- Modify: `backend-supabase/routers/erp.py`
- Modify: `backend-supabase/models/erp.py` (request/response)
- Test: `backend-supabase/tests/erp/services/test_erp_product_image_sync.py`

**Interfaces:**
- Produces: `async def sync_erp_product_images(schema: str, *, force: bool = False, limit: int = 200) -> dict`

Comportamiento:

1. Leer `erp_products_raw` con `raw_payload->'extra'->>'image_src'` no vacío.
2. JOIN `productos` por `product_code = sku`.
3. Skip si no hay fila en `productos` (no crear producto).
4. Skip si `image_url` tiene valor y no es placeholder (`via.placeholder.com`) y `force=false`.
5. GET de `image_src` (timeout 20s, max 5 MB).
6. POST Storage `products-{schema}/{sku}.{ext}` con `x-upsert: true` (mismo patrón que `scripts/fase-01-catalogo/cargar_imagenes_excel.py`).
7. `UPDATE productos SET image_url = public_url`.
8. Caps: `limit` 1..500; concurrency 4.

Dry-run: `dry_run=true` no descarga; devuelve `{would_update: N, skipped_has_image: M, skipped_no_product: K}`.

- [ ] **Step 1: Tests con httpx/storage mock**

Casos: skip sin producto; skip con image_url; update si vacío; force pisa.

- [ ] **Step 2: FAIL → implementar → PASS**

```bash
pytest -q tests/erp/services/test_erp_product_image_sync.py -v
```

- [ ] **Step 3: Router**

```python
@router.post("/sync-product-images")
async def sync_product_images(schema: str, dry_run: bool = True, force: bool = False, limit: int = 200):
    ...
```

Default `dry_run=true` para no disparar descargas accidentalmente desde Swagger.

- [ ] **Step 4: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat: copy Cianbox product images into Suplai storage

EOF
)"
```

---

### Task 6: Backoffice — botón Sincronizar imágenes

**Files:**
- Create: `product-management-app/app/api/erp/sync-product-images/route.ts`
- Modify: `product-management-app/components/erp-integrations-section.tsx` (junto a `handleLoadProducts`)

**Interfaces:**
- Consumes: `POST /{schema}/erp/sync-product-images?dry_run=false&force=false`
- Produces: toast con `updated` / `skipped_has_image`

- [ ] **Step 1: Proxy route** (copiar `app/api/erp/load-products/route.ts`, cambiar path y usar `fetchBackendLongRun`).

- [ ] **Step 2: UI**

Junto a «Cargar productos»:

- Botón «Sincronizar imágenes»: primero `dry_run=true`, toast «N fotos pendientes»; confirmar; luego `dry_run=false`.
- No agregar «Promote masivo» nuevo. Si el botón promote ya existe, dejar un hint visible en CF: «No alta masiva — WhatsApp solo combos».

- [ ] **Step 3: Verificar en browser**

`BACKEND_URL=http://localhost:8000 npm run dev` en puerto **3000**. Tenant `cordoba_frost`. Click Cargar productos (si backend ya está mergeado en local) → Sincronizar imágenes.

- [ ] **Step 4: Commit backoffice**

```bash
git commit -m "$(cat <<'EOF'
feat: add ERP product image sync action in backoffice

EOF
)"
```

---

### Task 7: Operación Córdoba Frost (humana, post-merge)

No es código. Checklist:

- [ ] Cargar productos → `loaded > 0`.
- [ ] Verificar `product_id_map` tiene los 6 combos (o anotar cuáles faltan y cargarlos a mano).
- [ ] Pedido test de `COM-HEL-INICIAL` → Cianbox línea con `id` numérico, no vacío.
- [ ] Sync imágenes → foto en combos que no tenían; combos de campaña helados intactos si ya tenían URL.
- [ ] Confirmar que `en_catalogo` de SKUs no-combo sigue `false` / no aparecen en el agente.

---

## Qué no hacer

- No llamar `promote-products-bulk` en `cordoba_frost`.
- No bajar imágenes dentro de `load_products_to_raw`.
- No habilitar `pull_prices` / `pull_orders` en este plan.
