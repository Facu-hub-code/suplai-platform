# Implementación de tenants — Guía para implementadores

Esta carpeta es tu **escritorio de trabajo** para cargar un distribuidor nuevo en Suplai Sales con ayuda del agente en Cursor.

## Antes de empezar (5 minutos)

1. El tenant ya debe existir (registro web) con **schema vacío**.
2. Tené el **Excel de productos y precios** del cliente.
3. En Cursor: **Settings → Tools & MCP** → servidor `supabase` conectado.
4. Para **cargar datos** a la base, editá [`.cursor/mcp.json`](../.cursor/mcp.json) y **quitá** `&read_only=true` de la URL del MCP.  
   Al terminar la sesión, **volvé a poner** `read_only=true` por seguridad.

   ```json
   "url": "https://mcp.supabase.com/mcp?project_ref=nxmeezcvjltlqfybbczt"
   ```

5. Decile al agente: **"Implementar {nombre del schema}"** (ej. `colormix`).

## Estructura por tenant

Copiá `_template/` a una carpeta con el nombre del schema:

```text
implementacion/colormix/
  manifest.yaml      ← progreso de fases
  inputs/            ← Excel original
  outputs/           ← CSV que genera cada fase (revisalos en Excel)
```

## Reglas de oro

- **Una fase a la vez.** No saltés la Fase 0.
- **Siempre revisá el CSV** antes de decir "confirmar carga".
- **Confirmá dos veces** el nombre del schema (`colormix`, etc.).
- Si algo falla, no improvises: pedí ayuda a ingeniería Suplai.

## Fases (resumen)

| Fase | Qué hace | CSV principal |
|------|----------|---------------|
| 0 | Verifica tenant vacío | `phase-00-preflight.csv` |
| 1 | Catálogo desde Excel | `phase-01-productos.csv` |
| 2 | 4 promociones mock | `phase-02-promociones.csv` |
| 3 | Cross-sell y up-sell | `phase-03-cross-sell.csv`, `phase-03-up-sell.csv` |
| 4 | Vendedores, zonas, 50 clientes | `phase-04-*.csv` |
| 5 | Flags ERP y WhatsApp | `phase-05-clientes-flags.csv` |
| 6 | Pedidos históricos y abiertos | `phase-06-*.csv` |
| 7 | Historial de chats | `phase-07-conversaciones-resumen.csv` |
| 8 | Alertas / insights | `phase-08-notificaciones.csv` |
| 9 | Purga mock (opcional) | `phase-09-purga-log.csv` |

Detalle técnico: [docs/implementacion/flujo-agentico-resumen.md](../docs/implementacion/flujo-agentico-resumen.md).

## Piloto Colormix

Ver [docs/implementacion/colormix-notas.md](../docs/implementacion/colormix-notas.md).

## Purga de datos de prueba

Solo cuando exista la columna `is_mock` en la base (migración de ingeniería).  
Debés escribir exactamente: **`PURGE MOCK colormix`** (cambiá el schema si aplica).
