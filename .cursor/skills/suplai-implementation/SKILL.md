---
name: suplai-implementation
description: Orquesta el onboarding agéntico de un tenant Suplai Sales (Excel → catálogo → mocks). Usar cuando el implementador dice implementar tenant, onboarding distribuidora, colormix, o cargar Excel de productos.
---

# Suplai Implementation — Orquestador

Guía al **implementador no técnico** fase por fase. No mezclar fases en un solo paso.

## Inicio

1. Preguntar **`schema_name`** (ej. `colormix`) si no está claro.
2. Verificar carpeta `implementacion/{schema_name}/`. Si no existe, copiar desde `implementacion/_template/`.
3. Leer `implementacion/{schema_name}/manifest.yaml`.
4. Aplicar reglas: `suplai-implementation-guardrails`, `suplai-implementation-mcp-writes`.

## Orden de fases

| # | Skill | Carpeta |
|---|-------|---------|
| 0 | `phase-00-preflight` | `.cursor/skills/suplai-implementation/phase-00-preflight/` |
| 1 | `phase-01-catalogo` | `phase-01-catalogo/` |
| 1.1 | `phase-01.1-tags` | `phase-01.1-tags/` |
| 1.2 | `phase-01.2-mejora-descripciones` | `phase-01.2-mejora-descripciones/` |
| 1.3 | `phase-01.3-prompt` | `phase-01.3-prompt/` |
| 2 | `phase-02-promociones` | `phase-02-promociones/` |
| 3 | `phase-03-cross-upsell` | `phase-03-cross-upsell/` |
| 4 | `phase-04-red-comercial` | `phase-04-red-comercial/` |
| 5 | `phase-05-clientes-flags` | `phase-05-clientes-flags/` |
| 6 | `phase-06-pedidos` | `phase-06-pedidos/` |
| 7 | `phase-07-conversaciones` | `phase-07-conversaciones/` |
| 8 | `phase-08-insights` | `phase-08-insights/` |
| 9 | `phase-09-purga-mock` | `phase-09-purga-mock/` |

## Lógica del orquestador

```
SI fase N está pendiente Y fase N-1 está cargado (o N=0):
  → invocar skill de fase N
SI implementador pide fase concreta ("fase 1 colormix"):
  → verificar prerequisito; si falla, explicar qué fase falta
SI todas hasta 8 cargadas:
  → felicitar y ofrecer sandbox agente + Fase 9 solo si is_mock existe
```

## Actualizar manifest

Tras cada fase:

- `estado`: `csv_listo` cuando el CSV existe y el implementador lo revisó; `cargado` tras MCP OK.
- `filas_csv`: conteo de líneas de datos (sin header).
- `cargado_at`: ISO timestamp.
- `marca_lider` / `tenant_id`: completar cuando corresponda.

## Documentación

- Flujo completo: `docs/implementacion/flujo-agentico-resumen.md`
- Colormix: `docs/implementacion/colormix-notas.md`
- Guía humana: `implementacion/README.md`

## Mensaje tipo al implementador

> Estás en **{schema}**, fase **{N} — {nombre}**.  
> Entregable: `{csv}`.  
> Cuando lo revises en Excel, decime **confirmar carga** para subir a Supabase.
