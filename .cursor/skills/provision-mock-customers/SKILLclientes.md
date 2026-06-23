---
name: provision-mock-customers
description: Aprovisiona clientes mock/inventados en cualquier esquema de base de datos para pruebas. Úsalo cuando el usuario o un flujo requiera crear una red de clientes ficticios geolocalizados para simulaciones.
---

# Aprovisionar Clientes Mock (provision-mock-customers)

Esta skill permite poblar la base de datos de cualquier tenant/esquema con clientes inventados (nombres realistas argentinos acordes al rubro, teléfonos de prueba únicos, visitas/entregas y ubicaciones geográficas dispersas alrededor de las zonas de operaciones).

Es útil para:
- Simulaciones comerciales.
- Pruebas E2E del agente conversacional o del backoffice.
- Validar flujos de geolocalización o rutas sin usar clientes reales.

---

## 1. Funcionamiento y Robustez

El script de aprovisionamiento realiza las siguientes validaciones y tareas automáticas:
1. **Detección del Entorno**: Carga las credenciales de base de datos desde `.env`.
2. **Contextualización Geográfica**: Lee `manifest.yaml` de la carpeta del tenant para obtener `coordenadas_centro` y `rubro`. Si no existe, usa la Ciudad de Córdoba como fallback.
3. **Generación Adaptativa al Rubro**: Modifica los tipos de comercios según el rubro (ej: usa carnicerías para rubro de carnes, pinturerías para pintura, y almacenes/kioscos para rubro general).
4. **Auto-inicialización de Red**: 
   - Si no existen **vendedores** en la base de datos, crea 3 vendedores por defecto.
   - Si no existen **geo_zones**, crea 6 zonas en direcciones distribuidas y genera sus polígonos MultiPolygon (SRID 4326).
5. **Inserción de Clientes**: Genera y guarda la estructura completa requerida:
   - `puntos_venta`
   - `clients` (vinculado a punto de venta)
   - `vendedores_clientes` (vínculos comerciales)
   - `client_locations` (ubicaciones de prueba en PostGIS)

---

## 2. Instrucciones de Uso

Para ejecutar el aprovisionamiento, utiliza la herramienta `run_command` y ejecuta el script de python indicando el esquema correspondiente.

### Ejemplo A: Carga estándar (50 clientes)
```bash
python .cursor/skills/provision-mock-customers/scripts/provision_mock_customers.py --esquema {esquema}
```

### Ejemplo B: Carga personalizada (ej. 20 clientes)
```bash
python .cursor/skills/provision-mock-customers/scripts/provision_mock_customers.py --esquema {esquema} --cantidad 20
```

---

## 3. Limpieza de Clientes Mock

Para remover todos los registros mock creados, puedes ejecutar una consulta SQL para eliminar en orden de dependencias en el esquema del tenant:

```sql
-- 1. Eliminar ubicaciones
DELETE FROM {esquema}.client_locations WHERE client_id IN (SELECT id FROM {esquema}.clients WHERE is_mock = true);

-- 2. Eliminar vínculos
DELETE FROM {esquema}.vendedores_clientes WHERE cliente_id IN (SELECT id FROM {esquema}.clients WHERE is_mock = true);

-- 3. Eliminar clientes
DELETE FROM {esquema}.clients WHERE is_mock = true;

-- 4. Eliminar puntos de venta
DELETE FROM {esquema}.puntos_venta WHERE is_mock = true;
```
