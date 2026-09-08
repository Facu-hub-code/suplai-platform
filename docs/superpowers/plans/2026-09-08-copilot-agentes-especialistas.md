# Copilot agentes especialistas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/specs/038-copilot-agentes-especialistas.md`

**Goal:** Reemplazar el Copilot generalista por seis agentes con packs cerrados, misma pantalla de chats, Carlos con el pack de ventas actual.

**Architecture:** Catálogo de producto en backend (`agent_slug` + tools). El orquestador Copilot existente se parametriza por slug (prompt + tool specs). Conversaciones y prefs en `core`. El backoffice lista agentes vía API y filtra chats. Packs no-Carlos se agregan uno por uno envolviendo APIs ya existentes.

**Tech Stack:** FastAPI, asyncpg (pooler 6543, `statement_cache_size=0`), OpenAI function calling, Next.js App Router, SSE.

## Global Constraints

- Spec 038: packs cerrados; `nl_sql_query` solo en `reportes`; funnel en Lucía; sin router generalista; archivos fuera de v1.
- Contrato ventas 042 intacto para Carlos.
- Pooler 6543, `statement_cache_size=0`, pools `min_size=1` / `max_size=2` en tests.
- Schema tenant siempre por path/auth; el LLM no elige schema.
- UI: solo artefactos `table`, `action_preview` y (Sofía) `opens_modal`.
- Cross-repo: merge **backend → backoffice**. Ramas: `feat/copilot-agentes-especialistas` en `backend-supabase`, `product-management-app` y `suplai-platform`.
- No implementar en `main`. Commits solo en esas ramas feature.
- Pulido fino de tools (ej. “consultaron línea X”) no entra en el bootstrap.

## File map

| File | Responsibility |
|------|----------------|
| `backend-supabase/services/copilot/catalog.py` | Packs: slug, nombre, descripción, prompt, tools, chips |
| `backend-supabase/sql/118_copilot_agent_slug.sql` | Columna `agent_slug` + tabla prefs |
| `backend-supabase/services/copilot/persistence.py` | CRUD conversaciones por slug + prefs de nombre |
| `backend-supabase/services/copilot/orchestrator.py` | Prompt + tools del pack; historial 12 msgs |
| `backend-supabase/services/copilot/tools.py` | `dispatch_tool(..., allowed_tools=)`; specs filtradas |
| `backend-supabase/routers/copilot.py` | `GET/PATCH /agents`, chat/list con slug |
| `backend-supabase/models/copilot.py` | `agent_slug` en chat; rename agent |
| `product-management-app/lib/copilot/types.ts` | Agent + `opens_modal` |
| `product-management-app/lib/copilot/api.ts` | Fetch agents, rename, chat con slug, messages cursor |
| `product-management-app/components/copilot/CopilotChatView.tsx` | Dos rieles: agentes → chats |
| `product-management-app/components/copilot/CopilotAgentList.tsx` | Lista + rename inline |
| Packs 7–11 | Tools nuevas en `tools.py` + artefactos |

---

### Task 1: Catálogo de agentes (puro, sin DB)

**Files:**
- Create: `backend-supabase/services/copilot/catalog.py`
- Create: `backend-supabase/tests/test_copilot_catalog.py`

**Interfaces:**
- Consumes: nada
- Produces: `CopilotAgentPack`, `AGENT_SLUGS`, `get_pack(slug: str) -> CopilotAgentPack`, `list_packs() -> list[CopilotAgentPack]`, `openai_tools_for(slug: str, all_specs: list[dict]) -> list[dict]`, `UnknownAgentSlugError`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_copilot_catalog.py
import pytest
from services.copilot.catalog import (
    AGENT_SLUGS,
    UnknownAgentSlugError,
    get_pack,
    list_packs,
    openai_tools_for,
)


def test_six_product_slugs():
    assert AGENT_SLUGS == (
        "reportes",
        "audiencia",
        "plantillas",
        "agendas",
        "catalogo",
        "operaciones",
    )


def test_carlos_has_sales_and_nl_sql_not_grupo():
    pack = get_pack("reportes")
    assert pack.default_name == "Carlos"
    assert "nl_sql_query" in pack.tool_names
    assert "sales_top_products" in pack.tool_names
    assert "grupo_create" not in pack.tool_names
    assert "agenda_create" not in pack.tool_names


def test_lucia_owns_funnel_and_groups():
    pack = get_pack("audiencia")
    assert pack.default_name == "Lucía"
    assert "grupo_create" in pack.tool_names
    assert "nl_sql_query" not in pack.tool_names


def test_unknown_slug_raises():
    with pytest.raises(UnknownAgentSlugError):
        get_pack("copilot")


def test_openai_tools_for_filters_specs():
    specs = [
        {"type": "function", "function": {"name": "sales_top_products"}},
        {"type": "function", "function": {"name": "grupo_create"}},
        {"type": "function", "function": {"name": "nl_sql_query"}},
    ]
    names = {
        s["function"]["name"]
        for s in openai_tools_for("reportes", specs)
    }
    assert names == {"sales_top_products", "nl_sql_query"}


def test_list_packs_order_stable():
    slugs = [p.slug for p in list_packs()]
    assert slugs == list(AGENT_SLUGS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend-supabase && python -m pytest tests/test_copilot_catalog.py -v`

Expected: FAIL `ModuleNotFoundError: services.copilot.catalog`

- [ ] **Step 3: Write catalog.py**

```python
"""Catálogo de agentes Copilot — spec 038. Packs de producto, no custom GPTs."""
from __future__ import annotations

from dataclasses import dataclass


class UnknownAgentSlugError(ValueError):
    def __init__(self, slug: str):
        super().__init__(slug)
        self.slug = slug


@dataclass(frozen=True)
class CopilotAgentPack:
    slug: str
    default_name: str
    description: str
    system_prompt: str
    tool_names: tuple[str, ...]
    suggested_chips: tuple[str, ...]
    capabilities: tuple[str, ...]


AGENT_SLUGS: tuple[str, ...] = (
    "reportes",
    "audiencia",
    "plantillas",
    "agendas",
    "catalogo",
    "operaciones",
)

_REPORTES_PROMPT = """Sos Carlos, analista comercial del back office.
Reglas:
- Nunca inventes cifras; usá siempre las tools.
- Clientes / quién compró más → sales_top_clients. Productos → sales_top_products.
- Ventas = pedidos confirmados; cantidades UMV; precio de línea.
- Si piden crear agenda, grupo, plantilla, sync ERP o imágenes de catálogo, decí qué colega lo hace (Martín, Lucía, Sofía, Omar, Nina) y no llames tools ajenas.
- Respondé en el idioma del usuario (español por defecto). Sé breve; tablas en artefacto table.
"""

_AUDIENCIA_PROMPT = """Sos Lucía, especialista en audiencia y funnel.
Podés consultar el funnel en un periodo, listar clientes de una etapa (no responden, no compran, carrito), etiquetar en bulk y crear grupos (siempre dry_run).
No consultes rankings de ventas ni crees agendas o plantillas.
"""

_PLANTILLAS_PROMPT = """Sos Sofía, especialista en plantillas Meta.
Listá plantillas del WABA. Para crear una, usá plantilla_create_draft (abre el modal en UI). No ejecutes envíos ni agendas.
"""

_AGENDAS_PROMPT = """Sos Martín, especialista en agendas HSM.
Creá o listá agendas. La hora es local al timezone del tenant. Preview + confirmación. No crees grupos ni plantillas.
"""

_CATALOGO_PROMPT = """Sos Nina, especialista en catálogo de tienda.
Respondé cobertura de imágenes y listados de productos. No subas archivos. No hables de ventas confirmadas ni ERP.
"""

_OPERACIONES_PROMPT = """Sos Omar, especialista en sync ERP.
Consultá el estado de la última sync (listas, productos, precios, clientes, pedidos). No dispares un sync.
"""

_PACKS: dict[str, CopilotAgentPack] = {
    "reportes": CopilotAgentPack(
        slug="reportes",
        default_name="Carlos",
        description="Reportes comerciales: ventas, clientes, periodos y el agente WhatsApp.",
        system_prompt=_REPORTES_PROMPT,
        tool_names=(
            "sales_top_products",
            "sales_top_clients",
            "sales_largest_order",
            "sales_compare_periods",
            "sales_time_series",
            "metrics_agent_summary",
            "nl_sql_query",
        ),
        suggested_chips=(
            "¿Cuál fue el producto más vendido el mes pasado?",
            "¿Quién hizo el pedido más grande el último mes?",
            "Resumen del agente esta semana",
            "Compará ventas de este mes vs el anterior",
        ),
        capabilities=("read",),
    ),
    "audiencia": CopilotAgentPack(
        slug="audiencia",
        default_name="Lucía",
        description="Funnel, etiquetas y grupos: no responden, no compran, armar audiencia.",
        system_prompt=_AUDIENCIA_PROMPT,
        tool_names=(
            "funnel_overview",
            "funnel_clients",
            "estrategia_funnel",
            "etiquetas_list",
            "etiquetas_assign_bulk",
            "grupo_create",
        ),
        suggested_chips=(
            "Funnel de esta semana",
            "¿Quiénes no responden?",
            "Creá un grupo de clientes por zona",
        ),
        capabilities=("read", "write_confirm"),
    ),
    "plantillas": CopilotAgentPack(
        slug="plantillas",
        default_name="Sofía",
        description="Plantillas de WhatsApp: listar y crear con el modal de Meta.",
        system_prompt=_PLANTILLAS_PROMPT,
        tool_names=("plantillas_list", "plantilla_get", "plantilla_create_draft"),
        suggested_chips=("Listá las plantillas aprobadas", "Quiero crear una plantilla nueva"),
        capabilities=("read", "opens_modal"),
    ),
    "agendas": CopilotAgentPack(
        slug="agendas",
        default_name="Martín",
        description="Agendas de envío HSM con horario en el timezone de la distribuidora.",
        system_prompt=_AGENDAS_PROMPT,
        tool_names=("agenda_list", "tenant_timezone", "agenda_create"),
        suggested_chips=("¿Qué agendas hay activas?", "Creá una agenda para el grupo X los martes a las 10"),
        capabilities=("read", "write_confirm"),
    ),
    "catalogo": CopilotAgentPack(
        slug="catalogo",
        default_name="Nina",
        description="Catálogo de tienda: productos sin imagen y cobertura.",
        system_prompt=_CATALOGO_PROMPT,
        tool_names=("productos_diagnostico", "get_productos"),
        suggested_chips=("¿Cuántos productos no tienen imagen?", "Listá productos sin imagen en catálogo"),
        capabilities=("read",),
    ),
    "operaciones": CopilotAgentPack(
        slug="operaciones",
        default_name="Omar",
        description="Estado de sincronización con el ERP.",
        system_prompt=_OPERACIONES_PROMPT,
        tool_names=("erp_sync_status",),
        suggested_chips=("¿Cómo está la sync con el ERP?"),
        capabilities=("read",),
    ),
}


def get_pack(slug: str) -> CopilotAgentPack:
    pack = _PACKS.get((slug or "").strip())
    if pack is None:
        raise UnknownAgentSlugError(slug)
    return pack


def list_packs() -> list[CopilotAgentPack]:
    return [_PACKS[s] for s in AGENT_SLUGS]


def openai_tools_for(slug: str, all_specs: list[dict]) -> list[dict]:
    allowed = set(get_pack(slug).tool_names)
    out: list[dict] = []
    for spec in all_specs:
        name = ((spec.get("function") or {}).get("name") or "")
        if name in allowed:
            out.append(spec)
    return out
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_copilot_catalog.py -v`

Expected: PASS (6 tests)

- [ ] **Step 5: Commit** (rama `feat/copilot-agentes-especialistas` en **backend-supabase**, crearla desde `origin/main` si no existe)

```bash
git add services/copilot/catalog.py tests/test_copilot_catalog.py
git commit -m "$(cat <<'EOF'
feat(copilot): catálogo de seis agentes especialistas

Packs cerrados por slug para que el orquestador no mezcle tools.
EOF
)"
```

---

### Task 2: Migración `agent_slug` + prefs

**Files:**
- Create: `backend-supabase/sql/118_copilot_agent_slug.sql`

**Interfaces:**
- Consumes: `core.copilot_conversations` (33 + 90 soft delete)
- Produces: columna `agent_slug`, índice, `core.copilot_agent_prefs`

- [ ] **Step 1: Write SQL**

```sql
-- Copilot agentes especialistas (spec 038).
ALTER TABLE core.copilot_conversations
  ADD COLUMN IF NOT EXISTS agent_slug text NOT NULL DEFAULT 'reportes';

UPDATE core.copilot_conversations
SET agent_slug = 'reportes'
WHERE agent_slug IS NULL OR btrim(agent_slug) = '';

CREATE INDEX IF NOT EXISTS idx_copilot_conversations_user_agent
  ON core.copilot_conversations (tenant_id, user_id, agent_slug, updated_at DESC)
  WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS core.copilot_agent_prefs (
    tenant_id uuid NOT NULL REFERENCES public.distribuidoras(id) ON DELETE CASCADE,
    user_id uuid NOT NULL,
    agent_slug text NOT NULL,
    display_name text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id, agent_slug)
);
```

- [ ] **Step 2: Aplicar en el proyecto Supabase** `cvlbietibaaehgeimxgw` vía MCP `apply_migration` (nombre `copilot_agent_slug`) **cuando el usuario autorice writes**. Hasta entonces dejar el archivo en `sql/` y no aplicar a prod a ciegas.

- [ ] **Step 3: Commit**

```bash
git add sql/118_copilot_agent_slug.sql
git commit -m "$(cat <<'EOF'
feat(copilot): persistir agent_slug y nombres por operador

Los chats viejos quedan en reportes (Carlos); los apodos no se pisan entre usuarios.
EOF
)"
```

---

### Task 3: Persistencia por slug + prefs

**Files:**
- Modify: `backend-supabase/services/copilot/persistence.py`
- Create: `backend-supabase/tests/test_copilot_persistence_agents.py`

**Interfaces:**
- Consumes: `get_pack` (para validar slug al crear)
- Produces:
  - `list_conversations(..., agent_slug: str) -> list[dict]` (incluye `agent_slug` en cada fila)
  - `create_conversation(..., agent_slug: str) -> UUID`
  - `get_conversation_for_user(...) -> dict` incluye `agent_slug`
  - `list_agent_prefs(tenant_id, user_id) -> dict[str, str]`
  - `upsert_agent_pref(tenant_id, user_id, agent_slug, display_name) -> dict`

- [ ] **Step 1: Write failing tests** (mock `get_connection` no hace falta si testeás SQL builders; preferí tests de contrato sobre funciones puras de serialización + un test de `create_conversation` que falle porque falta el kwarg)

Si el repo no mockea asyncpg, testeá helpers:

```python
# tests/test_copilot_persistence_agents.py
from services.copilot.catalog import get_pack, UnknownAgentSlugError
import pytest

def test_create_requires_known_slug():
    from services.copilot.persistence import normalize_agent_slug
    assert normalize_agent_slug("reportes") == "reportes"
    with pytest.raises(UnknownAgentSlugError):
        normalize_agent_slug("nope")
```

Implementá `normalize_agent_slug` llamando `get_pack(slug).slug`.

- [ ] **Step 2: Run — FAIL** (`normalize_agent_slug` no existe)

- [ ] **Step 3: Implement**

En `persistence.py`:

```python
from services.copilot.catalog import get_pack, UnknownAgentSlugError

def normalize_agent_slug(slug: str) -> str:
    return get_pack(slug).slug
```

Cambiar `list_conversations` para filtrar `AND agent_slug = $4` y devolver `agent_slug`.

Cambiar `create_conversation` INSERT: agregar columna `agent_slug` (valor ya normalizado).

Cambiar `get_conversation_for_user` SELECT: incluir `agent_slug`.

Agregar:

```python
async def list_agent_prefs(*, tenant_id: UUID, user_id: UUID) -> dict[str, str]:
    ...
    # SELECT agent_slug, display_name FROM core.copilot_agent_prefs WHERE tenant_id=$1 AND user_id=$2
    # return {slug: name}

async def upsert_agent_pref(
    *,
    tenant_id: UUID,
    user_id: UUID,
    agent_slug: str,
    display_name: str,
) -> dict:
    slug = normalize_agent_slug(agent_slug)
    name = display_name.strip()[:80]
    if not name:
        raise ValueError("DISPLAY_NAME_EMPTY")
    ...
    # INSERT ... ON CONFLICT (tenant_id, user_id, agent_slug) DO UPDATE SET display_name, updated_at
    return {"slug": slug, "display_name": name}
```

- [ ] **Step 4: Run tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add services/copilot/persistence.py tests/test_copilot_persistence_agents.py
git commit -m "$(cat <<'EOF'
feat(copilot): conversaciones y prefs scoped por agente

Cada hilo pertenece a un slug; el nombre visible es por operador.
EOF
)"
```

---

### Task 4: Orquestador y dispatch filtrados por pack

**Files:**
- Modify: `backend-supabase/services/copilot/tools.py` (`dispatch_tool`, `heuristic_plan`)
- Modify: `backend-supabase/services/copilot/orchestrator.py`
- Create: `backend-supabase/tests/test_copilot_dispatch_pack.py`

**Interfaces:**
- Consumes: `get_pack`, `openai_tools_for`, `OPENAI_TOOL_SPECS`
- Produces: `dispatch_tool(..., agent_slug: str)`; `stream_chat_turn(..., agent_slug: str)`; `run_chat_turn(..., agent_slug: str)`

- [ ] **Step 1: Failing test**

```python
# tests/test_copilot_dispatch_pack.py
import pytest
from services.copilot.tools import dispatch_tool
import asyncio

@pytest.mark.asyncio
async def test_reportes_cannot_dispatch_grupo_create():
    result = await dispatch_tool("demo", "grupo_create", {}, agent_slug="reportes")
    assert result["error"] == "tool_not_in_pack"
    assert "Lucía" in result.get("message", "") or "audiencia" in result.get("message", "").lower()
```

`dispatch_tool` hoy no acepta `agent_slug` → FAIL.

- [ ] **Step 2: Implement filter**

```python
async def dispatch_tool(schema, name, args, *, ctx=None, agent_slug: str = "reportes"):
    from services.copilot.catalog import get_pack
    pack = get_pack(agent_slug)
    if name not in pack.tool_names:
        return {
            "tool": name,
            "error": "tool_not_in_pack",
            "message": f"Eso no lo hago yo. Probá con el agente que corresponde ({pack.default_name} atiende otra cosa).",
            "data": {},
        }
    # deprecated trio solo si alguien las pide fuera de agendas:
    if name in {"report_generate_pdf", "clients_geojson"}:
        return {"tool": name, "error": "deprecated", "message": "...", "data": {}}
    if name == "grupo_create":
        return await run_grupo_create(schema, args or {}, ctx)
    ...
```

Ajustar el mensaje para citar al colega dueño de la tool (opcional: mapa tool→slug). Mínimo: `tool_not_in_pack`.

`heuristic_plan(user_message, *, allowed_tools: set[str] | None = None)`: si `allowed_tools`, descartar planes cuyo name no esté permitido; si queda vacío, `[]` (el orquestador responde texto sin tools).

- [ ] **Step 3: Orchestrator**

`_call_openai_with_tools(..., agent_slug: str)`:

- `pack = get_pack(agent_slug)`
- system = `pack.system_prompt + f"\nTenant schema: {schema}. Locale: {locale}."` (reemplaza `SYSTEM_PROMPT` global para el turno)
- `"tools": openai_tools_for(agent_slug, OPENAI_TOOL_SPECS)` — si la lista está vacía, no mandar `tools` (Sofía/Nina pueden no tener specs todavía; el modelo solo habla)
- `dispatch_tool(..., agent_slug=agent_slug)`

`run_chat_turn` / `stream_chat_turn`:

- Requieren `agent_slug: str`
- Si hay `conversation_id`, el slug **sale de la conversación**; si el body manda otro, 409 `AGENT_SLUG_MISMATCH` (eso va en el router; acá `ValueError("AGENT_SLUG_MISMATCH")`)
- `create_conversation(..., agent_slug=normalize_agent_slug(agent_slug))`

Historial: seguir usando `_HISTORY_MESSAGE_LIMIT = 12`.

- [ ] **Step 4: Tests PASS** + `pytest tests/test_copilot_catalog.py tests/test_copilot_dispatch_pack.py tests/test_copilot_nl_sql.py tests/test_copilot_date_resolver.py -v`

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(copilot): orquestar solo las tools del pack

Carlos ya no ve grupo_create; un slug desconocido no mezcla oficios.
EOF
)"
```

---

### Task 5: API agents + chat/list con slug

**Files:**
- Modify: `backend-supabase/models/copilot.py`
- Modify: `backend-supabase/routers/copilot.py`
- Create: `backend-supabase/tests/test_copilot_agents_router.py` (si el suite de routers usa TestClient; si no, tests unitarios de `_serialize_agent`)

**Interfaces:**
- Consumes: `list_packs`, `list_agent_prefs`, `upsert_agent_pref`, `list_conversations(..., agent_slug=)`
- Produces:
  - `GET /{schema}/copilot/agents` → `[{slug, default_name, display_name, description, suggested_chips, capabilities}]`
  - `PATCH /{schema}/copilot/agents/{slug}` body `{display_name}`
  - `GET /{schema}/copilot/conversations?agent_slug=reportes`
  - `POST /{schema}/copilot/chat` body incluye `agent_slug` (obligatorio si no hay `conversation_id`)

- [ ] **Step 1: Models**

```python
class CopilotChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    conversation_id: UUID | None = None
    agent_slug: str | None = None
    refresh_token: str | None = None
    locale: str = "es"
    stream: bool = True

class CopilotAgentRenameRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=80)
```

- [ ] **Step 2: Router helpers**

```python
def serialize_agent(pack, display_name: str | None) -> dict:
    return {
        "slug": pack.slug,
        "default_name": pack.default_name,
        "display_name": display_name or pack.default_name,
        "description": pack.description,
        "suggested_chips": list(pack.suggested_chips),
        "capabilities": list(pack.capabilities),
    }
```

`GET /agents`: prefs + `list_packs()`.

`PATCH /agents/{slug}`: `upsert_agent_pref`; 400 si slug desconocido (`UnknownAgentSlugError` → `{"code":"UNKNOWN_AGENT_SLUG"}`).

`GET /conversations`: query `agent_slug: str` **required** (sin default que liste todos los agentes mezclados).

`POST /chat`: si no hay `conversation_id` y falta `agent_slug` → 400 `AGENT_SLUG_REQUIRED`. Si hay conversación, usar su slug.

Pasar `agent_slug` a `stream_chat_turn` / `run_chat_turn`.

- [ ] **Step 3: Tests** — al menos `serialize_agent` + `normalize` 400. Si hay patrón TestClient en `tests/test_agenda_router.py`, copiar auth skip/mock para `GET /demo/copilot/agents` 401 sin token (smoke de ruta registrada).

- [ ] **Step 4: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(copilot): API de agentes y chats filtrados por slug

La UI deja de hardcodear especialistas; el chat nuevo exige agente.
EOF
)"
```

---

### Task 6: UI — lista de agentes + chats filtrados

**Repos:** `product-management-app`, rama `feat/copilot-agentes-especialistas` desde `origin/main`.

**Files:**
- Modify: `lib/copilot/types.ts`
- Modify: `lib/copilot/api.ts`
- Create: `app/api/copilot/agents/route.ts`
- Create: `app/api/copilot/agents/[slug]/route.ts`
- Create: `components/copilot/CopilotAgentList.tsx` (lista + rename; < 200 LOC)
- Modify: `components/copilot/CopilotChatView.tsx`
- Modify: `lib/copilot/i18n.ts` (sacar q5 de Carlos; chips vienen de API)

**Interfaces:**
- Consumes: `GET /copilot/agents`, `PATCH /copilot/agents/{slug}`, `GET /conversations?agent_slug=`
- Produces: `CopilotAgent`, `fetchCopilotAgents`, `renameCopilotAgent`, `postCopilotChat` con `agent_slug`

- [ ] **Step 1: Types + API**

```ts
export interface CopilotAgent {
  slug: string
  default_name: string
  display_name: string
  description: string
  suggested_chips: string[]
  capabilities: string[]
}

export interface CopilotConversation {
  id: string
  title: string | null
  agent_slug?: string
  created_at: string
  updated_at: string
}
```

`fetchCopilotConversations(..., agentSlug: string)` → `/api/copilot/conversations?agent_slug=`

`postCopilotChat` body agrega `agent_slug`.

BFF:

```ts
// app/api/copilot/agents/route.ts
export async function GET(request: Request) {
  const schema = request.headers.get("x-schema-name")
  if (!schema) return Response.json({ error: "x-schema-name required" }, { status: 400 })
  return proxyCopilot(request, schema, "/agents", { method: "GET" })
}
```

PATCH: `proxyCopilot(request, schema, `/agents/${slug}`, { method: "PATCH", body })`

Conversations GET: reenviar query string `agent_slug` en `proxyCopilot` — si `proxy` no copia searchParams, extender `proxyCopilot` para append `new URL(request.url).search` al path.

- [ ] **Step 2: CopilotAgentList**

Props: `agents`, `selectedSlug`, `onSelect(slug)`, `onRenamed(agent)`. Rename inline (mismo patrón que títulos de chat). Click selecciona agente y dispara `startNewChat` del padre o limpia el hilo.

- [ ] **Step 3: CopilotChatView**

Estado `selectedSlug` default `"reportes"`. `useEffect` carga agents. `refreshConversations` depende de `selectedSlug`. Al cambiar de agente: `startNewChat` + reload list. Composer chips = `selectedAgent.suggested_chips`. Placeholder según agente. Footer disclaimer solo en `reportes`.

Si chat a Carlos pide agenda, el texto del backend basta; chip “Abrir Martín” es nice-to-have: botón que `onSelect("agendas")` si el último mensaje menciona el slug. **No bloquea** esta task.

- [ ] **Step 4: Typecheck**

Run: `cd product-management-app && npx tsc --noEmit`

Expected: PASS en archivos tocados.

- [ ] **Step 5: Prueba humana mínima** (backend 8000 + backoffice 3000): seis agentes, rename Carlos, chat viejo bajo reportes, top productos sigue andando, chat de Lucía no aparece en Carlos.

- [ ] **Step 6: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(copilot): pantalla de chats por agente especialista

Lista desde API, historial filtrado y nombre editable por operador.
EOF
)"
```

---

### Task 7: Paginación de mensajes (scroll atrás)

**Files:**
- Modify: `persistence.list_messages` — `before_created_at: datetime | None`, `limit: int = 40`, devolver **los más recientes** del recorte (ORDER BY created_at DESC LIMIT, reverse in Python)
- Modify: `GET .../messages?before=&limit=`
- Modify: `CopilotChatView` — carga inicial últimos 40; al scrollear top, fetch página anterior y prepend

**Interfaces:**
- `list_messages(conversation_id, *, limit=40, before: datetime | None = None) -> list[dict]` orden ASC para el caller

- [ ] Tests unitarios del reverse: dado 5 timestamps mockeados, `before=t3, limit=2` → t1,t2.
- [ ] Front: `onScroll` del thread; no re-fetch si `loadingOlder` o no hay más (`length < limit`).
- [ ] El orquestador **no** cambia: sigue mandando 12 msgs al modelo.
- [ ] Commit: `feat(copilot): paginar historial como WhatsApp`

---

### Task 8: Lucía — funnel, etiquetas, grupos

**Files:**
- Modify: `services/copilot/tools.py` (OPENAI_TOOL_SPECS + handlers)
- Create: `tests/test_copilot_audiencia_tools.py` (descripciones + dispatch pack; mock de servicios)

**Tools (envolver, no reescribir SQL):**

| name | wrap |
|------|------|
| `funnel_overview` | `get_metricas_agente(schema, d_from, d_to)` + `get_performance_por_plantilla(...)` |
| `funnel_clients` | args `stage`: `no_responden` → `get_clientes_inactivos`; `respondieron` / `carritos` / `confirmados` → `get_detalle_*`; `paused_no_reply` si hay `estrategia_id` → query `estrategia_member_state` |
| `estrategia_funnel` | `get_estrategia_funnel` (resolver tenant_id como el router) |
| `etiquetas_list` | `svc_list_etiquetas` |
| `etiquetas_assign_bulk` | dry_run default true: preview count; execute usa el bulk ya existente en `routers/etiquetas.py` (extraer service si está inline) |
| `grupo_create` | ya existe |

Artefactos: `table`. Assign bulk y grupo: `action_preview`.

`clients_by_product_line` **no** en esta task (spec: pulir después).

- [ ] Test: `openai_tools_for("audiencia", OPENAI_TOOL_SPECS)` incluye `funnel_overview`, no `nl_sql_query`.
- [ ] Test: `dispatch_tool(..., "funnel_overview", {"period":"this_week"}, agent_slug="reportes")` → `tool_not_in_pack`.
- [ ] Heurístico: keywords funnel/no responden → `funnel_overview` / `funnel_clients` solo si allowed.
- [ ] Commit: `feat(copilot): pack audiencia (Lucía) con funnel y grupos`

---

### Task 9: Sofía — plantillas + modal

**Files:**
- Modify: `tools.py` specs `plantillas_list`, `plantilla_get`, `plantilla_create_draft`
- Wrap: `services/plantillas_meta_service` / list del router
- `plantilla_create_draft`: no llama Meta; devuelve artefacto

```json
{
  "type": "opens_modal",
  "modal": "create_meta_template",
  "summary": "Abrí el editor de plantillas para crearla con el flujo oficial."
}
```

- Modify: `lib/copilot/types.ts` — literal `opens_modal`
- Modify: `CopilotArtifacts.tsx` + `visibleCopilotArtifacts` incluye `opens_modal`
- Al click: setState que monta `<CreateMetaTemplateModal open onSuccess={...} />` (el de `components/create-meta-template-modal`)
- `onSuccess`: mensaje de sistema en el hilo “Plantilla {name} creada” (append local + opcional POST chat)

- [ ] Test pack filter + artefacto type.
- [ ] Commit: `feat(copilot): Sofía abre el modal de plantillas Meta`

---

### Task 10: Martín — agendas + timezone tenant

**Files:**
- Modify: `tools.py` — **rehabilitar** `agenda_create` solo si `agent_slug=="agendas"` (sacar del bloqueo global `deprecated`)
- Add `agenda_list` (SELECT agenda del tenant, límite 30)
- Add `tenant_timezone`:

```python
async def run_tenant_timezone(schema: str, args: dict) -> dict:
    rows = await query_schema(
        schema,
        "SELECT COALESCE(metadata->>'timezone', 'America/Argentina/Buenos_Aires') AS tz "
        "FROM public.distribuidoras WHERE schema_name = $1 LIMIT 1;",
        schema,
    )
    tz = (rows[0]["tz"] if rows else None) or "America/Argentina/Buenos_Aires"
    return {"tool": "tenant_timezone", "data": {"timezone": tz}}
```

- Preview de `agenda_create` incluye `timezone` en `details`.
- No agregar columna por fila salvo que al probar Córdoba Frost la hora salga mal (entonces follow-up, no esta task).

- [ ] Test: `dispatch_tool(..., "agenda_create", {}, agent_slug="reportes")` → `tool_not_in_pack`
- [ ] Test: `agent_slug="agendas"` ya no devuelve `deprecated`
- [ ] Commit: `feat(copilot): pack agendas (Martín) con TZ de tenant`

---

### Task 11: Nina + Omar (lectura)

**Files:**
- `productos_diagnostico` → misma query que `GET /{schema}/productos/diagnostico` (extraer helper o llamar lógica; no duplicar el SQL largo: importar/reusar función si se extrae un one-liner de counts `image_url_faltante`)
- `get_productos` args: `search`, `en_catalogo`, `sin_imagen: bool`, `page`, `page_size<=20`. Si `sin_imagen`, `AND (image_url IS NULL OR btrim(image_url)='')`
- `erp_sync_status` → `get_dependency_health(schema)` tabla: entidad, last_sync_at, linked/pending

Descripciones OpenAI **explícitas**: `get_productos` es cobertura de catálogo/tienda, **no** ranking de ventas.

- [ ] Tests de pack + que reportes no despacha `erp_sync_status`
- [ ] Commit: `feat(copilot): packs catálogo y operaciones (Nina, Omar)`

---

### Task 12: Evals Carlos + cierre de spec

**Files:**
- `suplai-platform/scripts/copilot-evals/` — los cases existentes asumen Copilot único; pasar `agent_slug=reportes` en el cliente de eval si pega a `/chat`
- Modify: `docs/specs/038-copilot-agentes-especialistas.md` estado → Aprobado para implementación (si el humano ya lo validó)
- Modify: `docs/specs/001-suplai-copilot.md` si faltó algún enlace

- [ ] Correr evals demo que ya son `critical`
- [ ] `pytest` copilot en backend verde
- [ ] `npx tsc --noEmit` backoffice verde
- [ ] Commit docs evals: `test(copilot): evals contra el pack reportes`

---

## Orden de merge

1. Backend tasks 1–5 (+ SQL aplicada)
2. Backoffice task 6–7
3. Backend+UI tasks 8–11 (PRs chicos o commits en la misma rama)
4. Task 12

No mergear backoffice antes de que `GET /agents` exista.

## Self-review vs spec 038

| Requisito spec | Task |
|----------------|------|
| Catálogo producto / UI desde API | 1, 5, 6 |
| Nombre por operador | 2, 3, 5, 6 |
| Chat = un agente; backfill reportes | 2, 3, 5 |
| Carlos pack ventas + nl_sql | 1, 4 |
| Funnel con Lucía | 8 |
| Sofía modal | 9 |
| Martín TZ tenant | 10 |
| Nina / Omar lectura | 11 |
| Memoria 12 msgs + scroll UI | 4 (12 msgs), 7 (scroll) |
| Sin router generalista | 4, 6 |
| Sin archivos / sin custom GPT / sin nl_sql extra | constraints + catalog |
| CI registry 6 slugs / tool_not_in_pack | 1, 4 |
| Prueba humana bootstrap | 6 step 5 |

Hueco consciente: `clients_by_product_line` queda para un follow-up de Lucía, como dice el spec.
