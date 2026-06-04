---
name: suplai-implementation-phase-04
description: Fase 4 red comercial — 3 vendedores, 6 zonas, 50 clientes mock geolocalizados. Usar tras Fase 3.
---

# Fase 4 — Red comercial

Prerequisito: Fases 1–3 cargadas.

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
- Zonas: nombres con barrios/rutas reales de `ciudad_base`; `dia_visita` lunes–sábado rotado; color hex brillante
- Clientes: ferreterías/pinturerías/corralones si rubro pintura; `lista_precios_id` 1–4 distribuido; teléfonos únicos

## Carga MCP

Orden:

1. `{schema}.vendedores` → guardar IDs
2. `{schema}.geo_zones` + `{schema}.vendedor_geo_zones`
3. `{schema}.clients` (sin flags ERP aún — Fase 5)
4. `{schema}.client_locations` si aplica (lat/lng)

Verificar columnas: `clients` usa `phone_number`, `razon_social`, `codigo`, `lista_precios_id`, `vendedor`.

## Verificación

- COUNT clients = 50
- COUNT vendedores = 3
- COUNT geo_zones = 6

## Cierre

manifest fase `04` → `cargado`; Fase 5 enriquece flags.
