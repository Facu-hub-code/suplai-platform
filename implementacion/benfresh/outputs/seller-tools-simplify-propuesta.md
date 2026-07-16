# Benfresh — simplificar tools vendedor (propuesta dry-run)

**Fecha:** 2026-07-16  
**Estado:** **APLICADO** 2026-07-16 (editorial global + 3 bloqueos Benfresh vía MCP)  
**Ventana de uso:** últimos 45 días (`core.conversation_events` + `core.agent_tool_executions`)  
**Script:** `scripts/benfresh/dry_run_seller_tools_simplify.py`  
**Ramas limpias:** `feat/benfresh-seller-tools-simplify` (platform + backend), `feat/benfresh-seller-tools-canvas` (backoffice)

## 1) Núcleo que SÍ se usa (no tocar enable)

| Llamadas | Tool |
|---------:|------|
| 27 | `load_seller_order_text` |
| 27 | `edit_order_for_client` |
| 19 | `set_seller_selected_client` |
| 11 | `confirm_order_for_client` |
| 9 | `get_open_order_status_for_client` |
| 4 | `get_seller_client_details` |
| 4 | `search_products` |

## 2) Renombre en español (editorial global)

- Afecta `core.agent_tools.display_name` / `short_description` → **todos los tenants** en canvas/admin.
- El `tool_name` técnico **no cambia** (el LLM sigue viendo snake_case + `tools_descripciones`).
- Dry-run: 28 tools vendedor con nombre ES + short hover.
- Artefacto: `seller-tools-rename-dry-run.json`, SQL en `seller-tools-simplify.sql`.

## 3) Bloqueos nuevos propuestos (solo Benfresh)

Ya hay muchas en `false`. Quedan **3** legacy aún ON por defecto y **0 usos**:

| Tool | Por qué bloquear |
|------|------------------|
| `get_product_by_code` | 0 usos; catálogo ya cubierto por `search_products` |
| `get_seller_selected_client` | 0 usos; el flujo usa `set_` / `get_seller_client_details` |
| `check_order_sync_status` | 0 usos; Field sync no opera en Benfresh hoy |

**Opt-in** (`seller_*_query`, etc.): ya apagadas sin `true` → no hace falta tocar.

**Ya bloqueadas** (ej.): Field (`get_seller_*` route/tasks/progress), `ping`, `seller_help`, `list_seller_clients`, `suggest_order_boost_for_client`, etc.

## 4) Cómo correr el dry-run

```bash
cd suplai-platform
python3 scripts/benfresh/dry_run_seller_tools_simplify.py \
  --usage-json implementacion/benfresh/outputs/seller-tools-usage-45d.json \
  --habilitadas-json implementacion/benfresh/outputs/seller-tools-habilitadas-now.json \
  --write-sql
```

Aplicar (solo cuando se apruebe):

```bash
DATABASE_URL='postgresql://...:6543/...' \
  python3 scripts/benfresh/dry_run_seller_tools_simplify.py --from-db --apply --i-understand
```

## 5) Canvas (siguiente paso)

Rama backoffice limpia: `feat/benfresh-seller-tools-canvas`.  
WIP previo de admin tools/canvas sigue en stash `wip: admin agent tools section` — no mezclado todavía.
