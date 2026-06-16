---
name: suplai-implementation-phase-04
description: Fase 4 red comercial — 3 vendedores, 6 zonas, 50 clientes mock geolocalizados. Usar tras Fase 3.
---

# Fase 4 — Red comercial

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Input (obligatorio)

- [ ] **`ciudad_base`** (ej. "Córdoba, Argentina") — guardar en `manifest.ciudad_base`
- Rubro del distribuidor (pinturería, alimentos, etc.) para nombres de fantasía

## Constantes

- 3 vendedores
- 6 zonas (2 por vendedor)
- 50 clientes (~8–9 por zona)

## Output

1. `phase-04-vendedores.csv`
2. `phase-04-zonas.csv` — `geometry_geojson` simplificado (polígono pequeño alrededor de centro ciudad)
3. `phase-04-clientes.csv` — `lat`, `lng` dispersos en radio 2–10 km

## Generación

- Vendedores: nombres locales, teléfono país correcto (549 AR), email `*@suplaisales.mock`, `is_mock=true`
- Zonas: nombres con barrios/rutas reales de `ciudad_base`; `dia_visita` lunes–sábado rotado; color hex brillante.
  - **Criterio de Tamaño y Topología**: Las 6 zonas deben ser **chicas** e independientes (polígonos de barrios puntuales, no uno gigante que cubra toda la ciudad). Evitar cruces de líneas o vértices inválidos.
  - **Tipado Geométrico**: Representación espacial estrictamente formateada como `MultiPolygon` con SRID 4326: `SRID=4326;MULTIPOLYGON(((lon lat, lon lat, ...)))` para evitar fallas PostGIS.
  - **Enumerador `zone_type`**: Usar valores enums permitidos por el esquema (ej. `'sales'` o `'route'`). NO usar términos no soportados como `'territory'`.
- Clientes: ferreterías/pinturerías/corralones si rubro pintura; `lista_precios_id` 1–4 distribuido; teléfonos únicos.

## Campos OBLIGATORIOS en manifest.yaml (a partir de Fase 4)

Además de los campos base, el manifest del tenant debe incluir:
- `rubro`: texto libre describiendo el negocio (ej: `"carnicería / parrilla"`)
- `coordenadas_centro`: `[lat, lon]` del centro geográfico (ej: `[-31.3547, -64.2442]`)

## Generación (MANDATORIO — Usar Script)

Para generar los 3 CSVs de red comercial usando OpenAI con contexto real de `ciudad_base` y `rubro`:
```bash
python scripts/fase-04-red-comercial/preparar_red_comercial.py --esquema {schema}
```
Este script:
- Lee `ciudad_base`, `rubro` y `coordenadas_centro` del manifest
- Llama a OpenAI para generar vendedores, zonas (barrios REALES) y nombres de clientes acorde al rubro
- Si no hay API key, usa un fallback geométrico genérico
- Permite personalización via `config.json` del tenant (clave `"red_comercial"`)

## Carga a la Base de Datos (MANDATORIO — Usar Script)

Para cargar los datos respetando las FKs en orden correcto:
```bash
python scripts/fase-04-red-comercial/cargar_red_comercial.py --esquema {schema}
```
Este script se encarga de:
1. Limpiar datos mock previos del tenant
2. Insertar vendedores → geo_zones + vendedor_geo_zones → puntos_venta → clients → vendedores_clientes → client_locations
3. Hacer `SET search_path` al esquema del tenant (necesario para resolver los tipos enum `dia_de_visita_enum`)
4. Proveer geometría PostGIS Point en `client_locations` para satisfacer la constraint `client_locations_check`

## Verificación

El script de carga imprime automáticamente los conteos. Verificación manual:
```sql
SELECT COUNT(*) FROM {schema}.clients;    -- 50
SELECT COUNT(*) FROM {schema}.vendedores; -- 3
SELECT COUNT(*) FROM {schema}.geo_zones;  -- 6
```

## Cierre

- manifest fase `04` → `cargado`, `filas_csv = 50`
- Proceder a Fase 5 (flags de clientes).

