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
Crear 6 zonas independientes y pequeñas (polígonos de barrios o avenidas puntuales, no un polígono gigante que cubra toda la ciudad):
- Nombres basados en barrios reales de la `ciudad_base` (ej: "ZONA SUR - Godoy Cruz", "CENTRO - Quinta Sección").
- `dia_visita`: distribuido equitativamente de lunes a sábado.
- Colores HEX de contraste alto para el visualizador del mapa.
- **Formato Geométrico**: La representación espacial de cada zona en la base de datos debe ser formateada estrictamente bajo el estándar PostGIS como **`MultiPolygon`** y con referencia espacial **`SRID=4326`**:
  `SRID=4326;MULTIPOLYGON(((lon lat, lon lat, ...)))`
  *Advertencia: No insertar un Polygon simple, ya que fallará el renderizado o la validación geométrica del mapa en el Backoffice.*
- **Validación de Enumerador `zone_type`**: Usar enums aceptados en base de datos (ej. `'sales'` o `'route'`). Evitar términos no soportados como `'territory'`.
- **Coherencia Topológica**: Validar que los vértices no tengan cruces de líneas o polígonos inválidos (deben cerrarse correctamente repitiendo la primera coordenada al final).

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
1. **Vendedores**: Insertar en `{schema}.vendedores` y rescatar los IDs autogenerados.
2. **Zonas**: Insertar en `{schema}.geo_zones` (aplicando el formato PostGIS `MultiPolygon` y el enum `zone_type` correctos) y asociar en `{schema}.vendedor_geo_zones`.
3. **Puntos de Venta (MANDATORIO)**: Por cada cliente de la lista de 50, primero insertar un registro en la tabla `{schema}.puntos_venta` (`razon_social`, `codigo`, `lista_precios_id`, `is_mock`) y guardar el `id` autogenerado (será el `pdv_id`).
4. **Clientes**: Insertar en `{schema}.clients` asignando la lista de precios, el vendedor, y el **`pdv_id`** obtenido en el paso anterior. Rescatar los `id` autogenerados de cada cliente. ¡Si no se crea y vincula el punto de venta a nivel de base de datos, el cliente no se visualizará en la app o backoffice!
5. **Asociación Vendedor-Cliente (MANDATORIO)**: Para cada cliente insertado, agregar un registro en la tabla `{schema}.vendedores_clientes` vinculando su `vendedor_id` y `cliente_id` (id autogenerado en la tabla clients), con la columna `activo` establecida en `true`.
6. **Geolocalización**: Insertar lat/lng en `{schema}.client_locations` vinculándolo al cliente.

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
