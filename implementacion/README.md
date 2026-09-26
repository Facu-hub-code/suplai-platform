# Implementación de tenants — Guía para implementadores

Esta carpeta es tu **escritorio de trabajo** para cargar un distribuidor nuevo en Suplai Sales con ayuda del agente en Cursor.

## Antes de empezar (5 minutos)

1. El tenant ya debe existir (registro web) con **schema vacío**.
2. Tené el **Excel de productos y precios** del cliente.
3. En Cursor: **Settings → Tools & MCP** → servidor `supabase` conectado.
4. Para **cargar datos** a la base, editá [`.cursor/mcp.json`](../.cursor/mcp.json) y **quitá** `&read_only=true` de la URL del MCP.  
   Al terminar la sesión, **volvé a poner** `read_only=true` por seguridad.

   ```json
   "url": "https://mcp.supabase.com/mcp?project_ref=cvlbietibaaehgeimxgw"
   ```

5. Decile al agente: **"Implementar {nombre del schema}"** (ej. `colormix`).

Credenciales del owner del backoffice (siempre las mismas):

- Email: `admin@{schema}.com` (o el dominio real del cliente si hace falta)
- Contraseña: **`Suplai2026`**

**Default: datos finales.** Se carga el catálogo completo (SKUs con Precio > 0), `is_mock=false`, las listas y fotos que existan. No se inventan vendedores, clientes, pedidos ni promociones: esas fases se omiten hasta tener origen real.

La **demo agéntica** (recorte 80–100 SKUs + mocks) solo se usa si lo pedís explícitamente. En ese caso el universo queda en `inputs/catalogo-completo.csv`.

## Estructura por tenant

Copiá `_template/` a una carpeta con el nombre del schema:

```text
implementacion/colormix/
  manifest.yaml      ← progreso de fases
  inputs/            ← Excel original
  outputs/           ← CSV que genera cada fase (revisalos en Excel)
```

## Reglas de oro

- **Sin rama git.** Abrí `implementacion/{schema}/` en el checkout actual; no hace falta `feat/` ni PR para cargar datos ni avanzar fases.
- **Una fase a la vez.** No saltés la Fase 0.
- **Siempre revisá el CSV** antes de decir "confirmar carga".
- **Confirmá dos veces** el nombre del schema (`colormix`, etc.).
- Si algo falla, no improvises: pedí ayuda a ingeniería Suplai.

## Fases (resumen)

| Fase | Qué hace | CSV principal |
|------|----------|---------------|
| 0 | Verifica tenant vacío | `phase-00-preflight.csv` |
| 1 | Catálogo desde Excel | `phase-01-productos.csv` |
| 1.2 | Mejora de descripciones | `vista_previa_enriquecimiento.csv` |
| 1.3 | Prompt del agente | `phase-01-3-prompt-config.json` |
| 2–8 | Promos, red, pedidos, chats (solo con origen real; en demo: mocks) | `phase-0N-*.csv` |
| 9 | Pruebas E2E | `outputs/reporte_e2e_*.md` |
| 10 | Purga mock (solo si hubo demo) | `phase-10-purga-log.csv` |

Detalle técnico: [docs/implementacion/flujo-agentico-resumen.md](../docs/implementacion/flujo-agentico-resumen.md).

## Piloto Colormix

Ver [docs/implementacion/colormix-notas.md](../docs/implementacion/colormix-notas.md).

## Purga de datos de prueba

Cuando exista la columna `is_mock` en la base (migración en [`docs/implementacion/migrations/20260615_add_is_mock_columns_demo_and_tenants.sql`](../docs/implementacion/migrations/20260615_add_is_mock_columns_demo_and_tenants.sql)).  
Aplicarla: Supabase SQL Editor, o MCP Supabase **sin** `read_only=true` en `.cursor/mcp.json`.  
Debés escribir exactamente: **`PURGE MOCK colormix`** (cambiá el schema si aplica).
