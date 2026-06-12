# Guía de Uso — Fase 4: Red Comercial (suplai-implementation-phase-04)

Esta guía detalla las pautas para generar y cargar los 3 vendedores, 6 zonas geográficas y 50 clientes mock dispersos geográficamente a partir de la ciudad base del distribuidor.

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Como agente de IA, busca la variable `ciudad_base` en el manifest. A partir de esa ubicación geográfica, genera coordenadas realistas dispersas (latitud y longitud) en un radio de 2 a 10 kilómetros y utiliza nombres de comercios simulados coherentes con el rubro del tenant.

---

## 📋 Requisitos Previos

1. **Ciudad Base**: Confirmada en el `manifest.ciudad_base` (ej. "Mendoza, Argentina").
2. **Tablas de Red Comercial**: Confirmar la estructura de `{schema}.vendedores`, `{schema}.geo_zones`, `{schema}.vendedor_geo_zones`, y `{schema}.clients`.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Generación de Vendedores
Crear 3 vendedores mock:
- Nombres locales de Argentina (ej. Martín Gómez, Valeria Díaz).
- Números de teléfono válidos con formato internacional (ej. `54911...`).
- Correos simulados con dominio `@suplaisales.mock`.
- `is_mock = true`.

### 2. Generación de Zonas
Crear 6 zonas (asociando 2 a cada vendedor):
- Nombres basados en barrios reales de la `ciudad_base` (ej: "ZONA SUR - Godoy Cruz", "CENTRO - Quinta Sección").
- `dia_visita`: distribuido equitativamente de lunes a sábado.
- Colores HEX de contraste alto para el visualizador del mapa.
- `geometry_geojson`: Crear un polígono pequeño en formato GeoJSON alrededor del barrio indicado.

### 3. Generación de Clientes
Crear 50 clientes mock geolocalizados:
- **Dispersión**: Latitud y longitud con desviaciones aleatorias de `0.01` a `0.08` grados desde las coordenadas del centro de la ciudad base.
- **Nombres**: Razones sociales y nombres comerciales acordes al rubro (ej. "Ferretería El Tornillo" para rubro ferretería).
- **Lista de Precios**: Asignar equitativamente `lista_precios_id` del 1 al 4.

### 4. Salidas locales (Outputs)
Escribir:
1. `outputs/phase-04-vendedores.csv`
2. `outputs/phase-04-zonas.csv`
3. `outputs/phase-04-clientes.csv`

---

## 💾 Carga a la Base de Datos (MCP Supabase)

Realizar la inserción secuencial (respetando llaves foráneas):
1. Insertar en `{schema}.vendedores` y rescatar los IDs autogenerados.
2. Insertar en `{schema}.geo_zones` y asociar en `{schema}.vendedor_geo_zones`.
3. Insertar en `{schema}.clients` (asignando listas de precios y vendedor correspondiente).
4. Insertar lat/lng en `{schema}.client_locations` si la estructura del schema lo requiere.

---

## 🔍 Verificación Post-Carga
```sql
SELECT COUNT(*) FROM {schema}.clients; -- 50
SELECT COUNT(*) FROM {schema}.vendedores; -- 3
SELECT COUNT(*) FROM {schema}.geo_zones; -- 6
```

---

## 🏁 Cierre de la Fase
1. Actualizar `manifest.yaml` estableciendo `fases["04"].estado = "cargado"` y registrando la fecha en `cargado_at`.
2. Proceder a la Fase 5.
