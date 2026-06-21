# Suplai Platform Workspace

Proyecto Cursor que agrupa los repositorios del stack Suplai Sales para trabajar con contexto cruzado y consultas a Supabase vía MCP.

## Repos incluidos

| Carpeta | Repo | Rol |
|---------|------|-----|
| `platform/` | `suplai-platform` | Reglas, skills, docs y configuración MCP |
| `agent/` | `agente-conversacional-multi_tenant` | Agente conversacional (FastAPI + LangGraph + WhatsApp) |
| `backend/` | `backend-supabase` | API REST multi-tenant (proxy a Supabase) |
| `backoffice/` | `product-management-app` | Back office Next.js para configurar datos del agente |
| `tienda/` | `wholesale-catalog-app` | Catálogo B2B web; link que envía el agente (`tienda.suplaisales.com`) |
| `sniffer/` | `sniffer-vendedores` | Espejo de conversaciones vendedor–cliente vía Kommo para análisis comercial |
| `sales-engine/` | `sales-engine` | ML de co-ocurrencia / frecuencia de compra por PdV (entrena desde pedidos) |

## Setup del equipo (primera vez)

Los repos deben quedar como **carpetas hermanas** (mismos nombres que en GitHub). El archivo `suplai-platform.code-workspace` usa rutas relativas; no hace falta editar paths por usuario.

```bash
# Opción A: script (desde cualquier máquina con acceso SSH a GitHub)
git clone git@github.com:Facu-hub-code/suplai-platform.git
cd suplai-platform
chmod +x scripts/utils/clone-stack.sh
./scripts/utils/clone-stack.sh ~/SuplaiSales/source   # o la carpeta padre que prefieran

# Opción B: clones manuales en la misma carpeta padre
mkdir -p ~/SuplaiSales/source && cd ~/SuplaiSales/source
git clone git@github.com:Facu-hub-code/suplai-platform.git
git clone git@github.com:Facu-hub-code/agente-conversacional-multi_tenant.git
git clone git@github.com:Facu-hub-code/backend-supabase.git
git clone git@github.com:Facu-hub-code/product-management-app.git
git clone git@github.com:Facu-hub-code/wholesale-catalog-app.git
git clone git@github.com:Facu-hub-code/sniffer-vendedores.git
git clone git@github.com:Facu-hub-code/sales-engine.git
```

Credenciales: `.env` en cada repo de aplicación. Para n8n MCP (opcional), copiar `.cursor/mcp.n8n.example.json` → `.cursor/mcp.n8n.json` y reemplazar el token (ese archivo está en `.gitignore`).

## Cómo abrirlo

1. En Cursor: **File → Open Workspace from File…**
2. Elegir `suplai-platform/suplai-platform.code-workspace` (desde la carpeta padre clonada)
3. Verificar MCP: **Settings → Tools & MCP** → servidor `supabase` activo
4. Si es la primera vez, completar OAuth de Supabase cuando Cursor lo solicite

## Supabase MCP

El proyecto de BD principal es **`nxmeezcvjltlqfybbczt`**. Configurado en `.cursor/mcp.json` con:

- `project_ref` acotado al proyecto de Suplai
- `read_only=true` por defecto (consultas seguras)

Herramientas útiles:

- `list_tables` — esquemas `public`, `core` y el tenant (`gonzales`, `demo`, etc.)
- `execute_sql` — queries de lectura
- `search_docs` — documentación Supabase

**Nota:** `sniffer/` puede usar Postgres propio (tablas Kommo). Confirmar con su `DATABASE_URL` si es el mismo proyecto o uno aparte.

## Flujo de datos (resumen)

```
WhatsApp PdV/vendedor  →  Agente  →  Supabase (tenant + core)
Back office (Next.js)  →  Backend  →  Supabase
Tienda web (Next.js)   →  Backend  →  Supabase
Sales Engine (FastAPI) →  Supabase (pedidos/items) + modelos .pkl
Sniffer (FastAPI)      →  Kommo webhooks → Postgres espejo (Kommo)
Agente                 →  link tienda → Tienda web
```

## Implementación de tenants (onboarding)

Guía para implementadores: [`implementacion/README.md`](implementacion/README.md).  
Skills Cursor: `.cursor/skills/suplai-implementation/` (fases 0–9, CSV + carga MCP).  
Skills vendor (skills.sh): `bash scripts/install-vendor-skills.sh` — ver `skills-vendor.manifest.json`.  
Piloto: `implementacion/colormix/`.

## Documentación

- [Arquitectura](./docs/ARCHITECTURE.md)
- [Mapa de repos y rutas](./docs/REPOS.md)
- [Guía de queries cruzadas](./docs/CROSS-REPO-QUERIES.md)

## Notas

- Cada repo sigue siendo **git independiente**; este workspace no los fusiona.
- Las rutas relativas apuntan a carpetas hermanas en `source/`.
- No commitear secretos en `platform/`; credenciales viven en `.env` de cada repo.
