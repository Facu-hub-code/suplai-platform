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

## Carga MCP

Orden:

1. `{schema}.vendedores` → guardar IDs
2. `{schema}.geo_zones` + `{schema}.vendedor_geo_zones`
3. `{schema}.puntos_venta` (CRÍTICO) → Crear un punto de venta por cliente (`razon_social`, `codigo`, `lista_precios_id`, `is_mock`) y guardar el `pdv_id` retornado.
4. `{schema}.clients` (sin flags ERP aún — Fase 5) → Insertar asociando la columna `pdv_id` rescatada de la tabla `puntos_venta` (guardar los `cliente_id` insertados). ¡Si no se asocia al PDV, los clientes no se mostrarán en el Backoffice/Frontend!
5. `{schema}.vendedores_clientes` (CRÍTICO) → Vincular cada cliente con su vendedor correspondiente insertando en esta tabla usando `vendedor_id`, `cliente_id` y `activo = true`.
6. `{schema}.client_locations` si aplica (lat/lng)

Verificar columnas: `clients` usa `phone_number`, `razon_social`, `codigo`, `lista_precios_id`, `vendedor`, `pdv_id`.

## Verificación

- COUNT clients = 50
- COUNT vendedores = 3
- COUNT geo_zones = 6

## Cierre

manifest fase `04` → `cargado`; Fase 5 enriquece flags.
