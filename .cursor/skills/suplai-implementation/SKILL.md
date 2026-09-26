---
name: suplai-implementation
description: Orquesta el onboarding de un tenant Suplai Sales (Excel → catálogo real; demo mock solo si se pide). Usar cuando el implementador dice implementar tenant, onboarding distribuidora, o cargar Excel de productos.
---

# Suplai Implementation — Orquestador

Guía al **implementador no técnico** fase por fase. No mezclar fases en un solo paso.

## Inicio

1. Preguntar **`schema_name`** (ej. `colormix`) si no está claro.
2. Verificar carpeta `implementacion/{schema_name}/`. Si no existe, copiar desde `implementacion/_template/`.
3. Leer `implementacion/{schema_name}/manifest.yaml`.
4. Aplicar reglas: `suplai-implementation-guardrails`, `suplai-implementation-mcp-writes`, `suplai-implementation-no-branch`.
5. **No abrir rama git** ni worktree: trabajar en el checkout actual, en `implementacion/{schema_name}/`.

## Credenciales del owner (obligatorio)

Al crear el owner del backoffice:

- **Email:** `admin@{schema_name}.com` (ej. `admin@kikimarket.com` si el dominio `{schema}.com` es inválido, usar el dominio real del cliente).
- **Contraseña:** `Suplai2026` — **siempre**. No inventar otra clave por tenant.

Guardar `admin_email` en `manifest.yaml`. No inventar otra password salvo pedido explícito del implementador. Alineado con spec 036 (onboarding guiado).

## Modo por defecto — datos finales

**Default:** `manifest.modo = completo`. La implementación carga **datos finales** del cliente, no una demo simulada.

1. **Catálogo completo**: todos los SKUs con Precio > 0. Sin recorte 80–100.
2. **`is_mock=false`** en productos, precios, aliases y en cualquier otra fila que sí tenga origen real.
3. **Listas de precios**: solo las que vengan del Excel/CSV (una lista si hay una columna de precio). **MUST NOT** inventar 4 listas con multiplicadores.
4. **Fotos**: si hay Excel/CSV con imágenes reales, cargar esas URLs. **MUST NOT** escribir placeholders.
5. **Fase 1.2**: enriquecer **todos** los productos cargados (no un cupo de 100).
6. **Fase 1.1 (taxonomía)**: opcional sobre el catálogo real; no inventa productos. Correr si el implementador la pide.
7. **Fases 2–8**: cargar **solo** si hay origen real (Excel, CSV, ERP, lista de vendedores/clientes/pedidos/promos). Si no hay origen → `estado: omitido`. **MUST NOT** inventar red comercial, pedidos, chats, tickets ni promociones mock.
8. **Fase 10 (purga mock)**: no aplica. Marcar `omitido` si no hay filas `is_mock=true`.

Anotar en `manifest.notas` qué fases se omiten por falta de origen (no por “demo liviana”).

## Modo demo agéntica (solo si se pide)

Activar **únicamente** si el implementador dice **demo agéntica** o `manifest.modo = demo`:

1. **No cargar el catálogo completo** cuando hay más de ~150 SKUs con precio. El Excel/PDF original y un `inputs/catalogo-completo.csv` quedan para la implementación real.
2. **Seleccionar 80–100 productos** que sean descriptivos del negocio (ver Fase 1). Si el origen ya tiene ≤100 SKUs con precio, cargar todos.
3. **Nutrir esos 80–100**: descripciones 10–25 palabras, aliases con UMV local (`caja`/`bulto` si el PdV lo dice así), categorías 4 niveles, 4 listas de precios, `is_mock=true`.
4. **Fase 1.2 no se omite**: enriquecer los 80–100 cargados (todos), no un subconjunto chico ni 25 SKUs.
5. Anotar en `manifest.demo.productos_cargados` el conteo real. Omitir solo Fase 9 (E2E) si la demo es liviana; no omitir 1.2.

Criterio de selección (en orden):

| Prioridad | Qué incluir | Cupo orientativo |
|-----------|-------------|------------------|
| 1 | Marca líder / exclusiva del tenant | 20–35% del recorte |
| 2 | Líneas comerciales que el cliente nombra en la reunión | ≥3 SKUs por línea relevante |
| 3 | Variantes de formato que se piden por WhatsApp (caja 500 / 1,5 / 2,25) | las de la marca líder |
| 4 | Marcas locales o de zona | 4–10 |
| 5 | Competencia que el PdV nombra | 6–12 |
| 6 | Completar hasta 80–100 con mix del resto (sin 40 whiskies iguales) | el saldo |

Solo SKUs con **Precio Final > 0**. Documentar el recorte en `outputs/phase-01-productos.csv` y pedir **"confirmar carga"** antes de insertar.

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
| 6.1 | `phase-06.1-field-setup` | `phase-06.1-field-setup/` |
| 7 | `phase-07-conversaciones` | `phase-07-conversaciones/` |
| 8 | `phase-08-insights` | `phase-08-insights/` |
| 9 | `phase-09-e2e-testing` | `phase-09-e2e-testing/` |
| 10 | `phase-10-purga-mock` | `phase-10-purga-mock/` |

## Lógica del orquestador

```
SI manifest.modo es vacío → tratar como completo (datos finales)
SI fase N está pendiente Y fase N-1 está cargado u omitido (o N=0):
  → invocar skill de fase N
SI modo=completo Y la fase requiere origen real que no existe:
  → omitir (no inventar mock) y seguir
SI implementador pide fase concreta ("fase 1 colormix"):
  → verificar prerequisito; si falla, explicar qué fase falta
SI catálogo + prompt cargados y el resto omitido o cargado:
  → ofrecer sandbox agente + Fase 9 (E2E). Fase 10 solo si hay is_mock=true
```

## Actualizar manifest

Tras cada fase:

- `estado`: `csv_listo` cuando el CSV existe y el implementador lo revisó; `cargado` tras MCP OK; `omitido` si no hay origen real.
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
