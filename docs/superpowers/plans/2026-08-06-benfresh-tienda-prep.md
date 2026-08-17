# Benfresh Tienda Prod-Ready — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-08-06-benfresh-tienda-prep-design.md`

**Goal:** Dejar la tienda Benfresh lista para prod: higiene WA USA→`existente`, PDV Christian, imágenes top-100 hotlink, flag link post-pedido, `origen=tienda` + badge/filtro en Pedidos.

**Architecture:** Ops + scripts en `suplai-platform`; persistencia de canal en `backend-supabase` (`tienda_login` + pedidos v2); UI en `product-management-app` (`pedidos-table`). Sin DDL. Sin auto-`validado` (manual post-primer envío).

**Tech Stack:** Python/asyncpg scripts, FastAPI/asyncpg, Next.js backoffice, Supabase MCP para applies de datos.

## Global Constraints

- Pooler **6543**, `statement_cache_size=0`, pools `min_size=1` / `max_size=2`.
- Tenant schema: `benfresh`.
- Phone USA OK: regex `^1[2-9]\d{9}$` (solo dígitos).
- `whatsapp_estado` bulk → `existente` solo desde `no_validado` (no pisar `validado` / `no_existente`).
- Hotlink imágenes: `https://www.benfreshfood.com/...` (no Storage).
- Origen carrito nuevo: literal `'tienda'`.
- Repos: editar en rama feature en hub (no troncal); worktree solo si el usuario lo pide.
- Commits solo cuando el usuario lo pida (salvo que el ejecutor acuerde lo contrario).

## File map

| Path | Rol |
|------|-----|
| `suplai-platform/scripts/benfresh/backfill_whatsapp_existente_usa.py` | Dry-run/apply higiene WA |
| `suplai-platform/scripts/benfresh/scrape_benfresh_images.py` | Scrape + match + apply image_url |
| `suplai-platform/implementacion/benfresh/outputs/*.csv` | Reportes dry-run |
| `backend-supabase/services/tienda_login.py` | INSERT con `origen` |
| `backend-supabase/services/pedidos_list_filters.py` | Filtro `origen` |
| `backend-supabase/routers/pedidos.py` | SELECT v2 incluye `p.origen` + query param |
| `backend-supabase/tests/test_tienda_login_origen.py` | Test insert origen |
| `backend-supabase/tests/test_pedidos_list_filters.py` | Extender filtros |
| `product-management-app/components/pedidos-table.tsx` | Badge + filtro origen |

---

### Task 1: Script higiene WhatsApp USA → `existente`

**Repo:** `suplai-platform` · rama `feat/benfresh-tienda-prep`

**Files:**
- Create: `scripts/benfresh/backfill_whatsapp_existente_usa.py`
- Create (output): `implementacion/benfresh/outputs/whatsapp_usa_existente_dryrun.csv`

**Interfaces:**
- Consumes: `SUPABASE_DB_URL` / `DATABASE_URL` (rewrite `:5432/` → `:6543/` si hace falta)
- Produces: CSV con columnas `id,nombre,phone_number,digits,whatsapp_estado_prev,action` (`mark_existente` \| `skip_invalid` \| `skip_fake99` \| `skip_already`)

- [ ] **Step 1: Crear script con dry-run default**

```python
#!/usr/bin/env python3
"""Marca clients Benfresh con phone USA válido como whatsapp_estado=existente.

Uso:
  set -a && source ../backend-supabase/.env && set +a
  python scripts/benfresh/backfill_whatsapp_existente_usa.py
  python scripts/benfresh/backfill_whatsapp_existente_usa.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "implementacion" / "benfresh" / "outputs"
SCHEMA = "benfresh"
USA_RE = re.compile(r"^1[2-9]\d{9}$")

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / "backend-supabase" / ".env")


def _db_url() -> str:
    url = (os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("Falta SUPABASE_DB_URL / DATABASE_URL")
    if ":5432/" in url:
        url = url.replace(":5432/", ":6543/")
    return url


def classify(digits: str, estado: str | None) -> str:
    if estado == "validado":
        return "skip_already"
    if estado == "existente":
        return "skip_already"
    if estado == "no_existente":
        return "skip_already"
    if digits.startswith("99"):
        return "skip_fake99"
    if USA_RE.match(digits):
        return "mark_existente"
    return "skip_invalid"


async def main(apply: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "whatsapp_usa_existente_dryrun.csv"
    conn = await asyncpg.connect(_db_url(), statement_cache_size=0)
    try:
        rows = await conn.fetch(
            f"""
            SELECT id, nombre, phone_number, whatsapp_estado::text AS wa
            FROM {SCHEMA}.clients
            ORDER BY id
            """
        )
        report = []
        to_mark: list[int] = []
        for r in rows:
            digits = re.sub(r"\D", "", r["phone_number"] or "")
            action = classify(digits, r["wa"])
            report.append({
                "id": r["id"],
                "nombre": r["nombre"],
                "phone_number": r["phone_number"],
                "digits": digits,
                "whatsapp_estado_prev": r["wa"],
                "action": action,
            })
            if action == "mark_existente":
                to_mark.append(int(r["id"]))

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(report[0].keys()) if report else [
                "id", "nombre", "phone_number", "digits", "whatsapp_estado_prev", "action"
            ])
            w.writeheader()
            w.writerows(report)

        print(f"[*] total={len(report)} mark_existente={len(to_mark)} csv={csv_path}")
        if not apply:
            print("[*] Dry-run: no writes. Pass --apply to update.")
            return

        updated = await conn.execute(
            f"""
            UPDATE {SCHEMA}.clients
            SET whatsapp_estado = 'existente'::core.whatsapp_estado_cliente_enum,
                whatsapp_existencia_verificada_at = now(),
                whatsapp_validado_at = NULL,
                whatsapp_validado_por = NULL,
                updated_at = now()
            WHERE id = ANY($1::int[])
              AND whatsapp_estado = 'no_validado'::core.whatsapp_estado_cliente_enum
            """,
            to_mark,
        )
        print(f"[*] apply result: {updated}")
    finally:
        await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    asyncio.run(main(apply=args.apply))
```

- [ ] **Step 2: Correr dry-run y verificar conteos**

```bash
cd /Users/facundolorenzo/Documents/SuplaiSales/source/suplai-platform
set -a && source ../backend-supabase/.env && set +a
python scripts/benfresh/backfill_whatsapp_existente_usa.py
```

Expected: `mark_existente` ≈ 278; CSV escrito; sin writes.

- [ ] **Step 3: Commit (si el usuario lo pide)**

```bash
git add scripts/benfresh/backfill_whatsapp_existente_usa.py
git commit -m "feat(benfresh): script backfill whatsapp existente USA"
```

---

### Task 2: Script imágenes Benfresh (top 100 + hotlink)

**Repo:** `suplai-platform` · misma rama

**Files:**
- Create: `scripts/benfresh/scrape_benfresh_images.py`
- Output: `implementacion/benfresh/outputs/image_matches.csv`

**Interfaces:**
- Consumes: HTML `https://www.benfreshfood.com`, tabla `benfresh.items_pedido` + `productos`
- Produces: CSV `product_code,nombre,qty_rank,matched_url,score,status`; `--apply` actualiza solo `image_url` vacío

- [ ] **Step 1: Implementar scrape + match**

Lógica mínima:

1. `urllib` GET homepage; regex `assets/images/product/([^\"']+)` → absolutizar base `https://www.benfreshfood.com/`.
2. Preferir filenames con `frente` / sin `dorso` cuando haya par.
3. Top 100:

```sql
SELECT p.product_code, p.nombre, p.image_url,
       SUM(ip.cantidad_solicitada)::float AS qty
FROM benfresh.items_pedido ip
JOIN benfresh.productos p ON p.product_code = ip.product_code
WHERE COALESCE(ip.is_mock, false) = false
  AND COALESCE(p.is_mock, false) = false
GROUP BY p.product_code, p.nombre, p.image_url
ORDER BY qty DESC NULLS LAST
LIMIT 100
```

4. Normalizar tokens (lowercase, quitar no-alfanuméricos); score = |intersection| / |union| (Jaccard) entre tokens del nombre DB y del filename (sin extensión, split `_`/`-`).
5. Match si score ≥ 0.45 **o** ≥ 2 tokens compartidos de largo ≥ 4; un sitio-image → un producto (greedy por score).
6. Dry-run CSV; `--apply`:

```sql
UPDATE benfresh.productos
SET image_url = $1, updated_at = now()
WHERE product_code = $2
  AND (image_url IS NULL OR btrim(image_url) = '')
```

Pool: `asyncpg.connect(..., statement_cache_size=0)`.

- [ ] **Step 2: Dry-run**

```bash
python scripts/benfresh/scrape_benfresh_images.py
```

Expected: CSV con matches + unmatched; print counts.

- [ ] **Step 3: Commit (si el usuario lo pide)**

---

### Task 3: Ops datos Benfresh (cliente Christian + flag + apply higiene)

**Repo:** datos vía MCP Supabase `cvlbietibaaehgeimxgw` (o SQL del script Task 1 `--apply`)

**No code PR** — ejecutar tras dry-runs revisados.

- [ ] **Step 1: Liberar phone Dixie + asignar a #11**

```sql
-- Dixie: placeholder único que no colisione
UPDATE benfresh.clients
SET phone_number = '9990000000013', updated_at = now()
WHERE id = 13 AND phone_number = '17864035046';

UPDATE benfresh.clients
SET phone_number = '17864035046',
    lista_precios_id = 24,
    updated_at = now()
WHERE id = 11;
```

- [ ] **Step 2: Flag catalog_store**

```sql
UPDATE public.distribuidoras
SET metadata = jsonb_set(
  COALESCE(metadata, '{}'::jsonb),
  '{catalog_store}',
  '{"append_link_after_order_tools": true}'::jsonb,
  true
)
WHERE schema_name = 'benfresh';
```

- [ ] **Step 3: Apply higiene WA**

```bash
python scripts/benfresh/backfill_whatsapp_existente_usa.py --apply
```

- [ ] **Step 4: Verificar**

```sql
SELECT id, nombre, phone_number, lista_precios_id FROM benfresh.clients WHERE id IN (11,13);
SELECT metadata->'catalog_store' FROM public.distribuidoras WHERE schema_name='benfresh';
SELECT whatsapp_estado::text, COUNT(*) FROM benfresh.clients GROUP BY 1 ORDER BY 2 DESC;
```

Expected: `#11` phone `17864035046` lista 24; `#13` placeholder; flag true; ~278 `existente`.

---

### Task 4: Backend — `origen='tienda'` en carrito nuevo

**Repo:** `backend-supabase` · rama `feat/benfresh-tienda-origen` desde `origin/main`

**Files:**
- Modify: `services/tienda_login.py`
- Create: `tests/test_tienda_login_origen.py`
- Modify (RETURNING): incluir `origen` en SELECT/RETURNING para que el caller lo vea

**Interfaces:**
- Consumes: `ensure_open_pedido_for_client(schema, cliente_id)`
- Produces: fila con `origen='tienda'` en INSERT nuevo; abiertos existentes sin rewrite

- [ ] **Step 1: Test que falla (mock fetchrow)**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_ensure_open_pedido_inserts_origen_tienda():
    from services.tienda_login import ensure_open_pedido_for_client

    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[
        None,  # no abierto
        {"id": 1, "cliente_id": 11, "estado": "abierto", "origen": "tienda",
         "items": [], "total": 0, "notas": None, "fecha": None},
    ])
    conn.close = AsyncMock()

    with patch("services.tienda_login.get_connection", AsyncMock(return_value=conn)), \
         patch("services.tienda_login.validate_schema", AsyncMock(return_value="benfresh")):
        row = await ensure_open_pedido_for_client("benfresh", 11)

    insert_sql = conn.fetchrow.await_args_list[1].args[0]
    assert "origen" in insert_sql
    assert "'tienda'" in insert_sql.replace(" ", "") or "tienda" in insert_sql
    assert row["origen"] == "tienda"
```

- [ ] **Step 2: Correr test → FAIL**

```bash
cd ../backend-supabase && pytest tests/test_tienda_login_origen.py -v
```

- [ ] **Step 3: Implementar INSERT**

En `services/tienda_login.py`, cambiar INSERT a:

```sql
INSERT INTO "{schema}".pedidos (cliente_id, fecha, items, total, estado, notas, origen)
VALUES ($1, now(), '[]'::jsonb, 0, 'abierto', NULL, 'tienda')
RETURNING id, cliente_id, fecha, items, total, estado, notas, origen;
```

Y el SELECT de abierto existente puede incluir `origen` en la lista de columnas.

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit (si el usuario lo pide)**

---

### Task 5: Backend — exponer y filtrar `origen` en pedidos v2

**Repo:** `backend-supabase` · misma rama Task 4

**Files:**
- Modify: `services/pedidos_list_filters.py`
- Modify: `routers/pedidos.py` (`get_pedidos_v2` + SELECT)
- Modify: `tests/test_pedidos_list_filters.py`

**Interfaces:**
- `PedidosListFilters(origen: str | None = None)`
- Query param `origen` en `GET /{schema}/pedidos/v2`
- SELECT añade `p.origen`

- [ ] **Step 1: Extender filtros + tests**

```python
@dataclass
class PedidosListFilters:
    search: str | None = None
    estado: str | None = None
    origen: str | None = None


# en build_pedidos_v2_where:
origen = (filters.origen or "").strip().lower()
if origen and origen != "todos":
    where_clauses.append(f"p.origen = {add_param(origen)}")
```

Tests:

```python
def test_build_pedidos_v2_where_origen_tienda():
    where, params = build_pedidos_v2_where(PedidosListFilters(origen="tienda"))
    assert "p.origen = $1" in where
    assert params == ["tienda"]


def test_build_pedidos_v2_where_origen_todos_ignored():
    where, params = build_pedidos_v2_where(PedidosListFilters(origen="todos"))
    assert "p.origen" not in where
```

- [ ] **Step 2: Wire router**

En `get_pedidos_v2`:

```python
origen: str | None = Query(None),
...
filters = PedidosListFilters(search=search, estado=estado, origen=origen)
```

En `data_sql` SELECT list, agregar `p.origen` junto a `p.erp_reference_id`.

- [ ] **Step 3: pytest filters + smoke**

```bash
pytest tests/test_pedidos_list_filters.py tests/test_tienda_login_origen.py -v
```

- [ ] **Step 4: Commit (si el usuario lo pide)**

---

### Task 6: Backoffice — badge + filtro origen en Pedidos

**Repo:** `product-management-app` · rama `feat/benfresh-tienda-origen-ui` desde `origin/main`  
**Depende de:** Task 5 mergeado o backend local con el query param

**Files:**
- Modify: `components/pedidos-table.tsx`

**Interfaces:**
- `Pedido.origen?: string | null`
- State `origenFilter: "todos" | "tienda" | "suplai"`
- URL: `&origen=` cuando ≠ todos

- [ ] **Step 1: Extender tipo + state + fetch**

```tsx
interface Pedido {
  // ...existing
  origen?: string | null
}

const [origenFilter, setOrigenFilter] = useState<string>("todos")

// hasActiveFilters incluye origenFilter !== "todos"
// useEffect deps incluyen origenFilter
// fetchPedidos:
if (origenFilter && origenFilter !== "todos") {
  url += `&origen=${encodeURIComponent(origenFilter)}`
}
```

- [ ] **Step 2: Badge helper (junto al título Pedido #id)**

```tsx
const origenBadge = (origen: string | null | undefined) => {
  const o = (origen || "suplai").toLowerCase()
  if (o === "tienda") {
    return (
      <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-700 text-[10px] px-1.5 py-0 h-5">
        Tienda
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="border-blue-500/30 bg-blue-500/10 text-blue-700 text-[10px] px-1.5 py-0 h-5">
      Suplai
    </Badge>
  )
}
```

Render: al lado de `Pedido #{pedido.id}` → `{origenBadge(pedido.origen)}`.

- [ ] **Step 3: Select filtro** (barra sticky, junto a estado)

```tsx
<Select value={origenFilter} onValueChange={(v) => {
  setOrigenFilter(v)
  setPagination((prev) => (prev.page === 1 ? prev : { ...prev, page: 1 }))
}}>
  <SelectTrigger className="w-[160px]"><SelectValue placeholder="Origen" /></SelectTrigger>
  <SelectContent>
    <SelectItem value="todos">Todos los orígenes</SelectItem>
    <SelectItem value="tienda">Tienda</SelectItem>
    <SelectItem value="suplai">Suplai</SelectItem>
  </SelectContent>
</Select>
```

- [ ] **Step 4: Smoke local**

Backend `8000` + backoffice `3000`. Login tienda Benfresh → carrito nuevo → Pedidos muestra badge Tienda; filtro funciona.

- [ ] **Step 5: Commit (si el usuario lo pide)**

---

### Task 7: Apply imágenes + checklist humana final

- [ ] Revisar CSV `image_matches.csv`
- [ ] `python scripts/benfresh/scrape_benfresh_images.py --apply`
- [ ] Checklist del spec (AC-1…AC-7)
- [ ] Abrir PRs: platform (scripts+spec), backend, backoffice — humano mergea

---

## Spec coverage (self-review)

| Spec item | Task |
|-----------|------|
| Higiene USA → existente | T1, T3 |
| Christian #11 / Dixie #13 | T3 |
| Flag catalog_store | T3 |
| get_catalog_link sin cambio | — (noop OK) |
| Imágenes top 100 hotlink | T2, T7 |
| origen=tienda al crear carrito | T4 |
| origen en v2 + UI | T5, T6 |
| Sin auto-validado | documentado / fuera de alcance |
| Sin Storage / sin Meta contacts | fuera de alcance |

## Execution handoff

Plan guardado en `docs/superpowers/plans/2026-08-06-benfresh-tienda-prep.md`.

**Opciones de ejecución:**

1. **Subagent-Driven (recomendado)** — un subagente por task, review entre tasks  
2. **Inline Execution** — ejecutar en esta sesión con checkpoints  

¿Cuál preferís?
