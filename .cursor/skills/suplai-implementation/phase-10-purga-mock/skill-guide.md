# Guía de Uso — Fase 10: Purga Mock (suplai-implementation-phase-10)

Esta guía detalla el proceso para eliminar de manera destructiva y controlada todos los datos simulados (`is_mock = true`) del tenant, dejándolo listo para su uso en producción.

> [!CAUTION]
> **OPERACIÓN DESTRUCCIÓN DE DATOS**
> Esta fase eliminará registros de la base de datos de manera definitiva. No ejecutes este paso sin cumplir de forma estricta los criterios de confirmación y verificar el soporte del campo `is_mock` en las tablas.

---

## 📋 Requisitos Previos

1. **Columna is_mock**: Verificar que todas las tablas afectadas posean la columna `is_mock`. Si la base de datos no tiene esta columna (bloqueo por migración pendiente de ingeniería), detén el proceso.
2. **Confirmación textual**: El implementador debe haber escrito la frase exacta: `PURGE MOCK {schema_name}`.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Verificación del Gate
- Si en el manifest `manifest.yaml` la clave `blocked.is_mock_migration` está seteada en `true`, abortar la purga y registrar en el log: `ok=false, notas=requiere migración is_mock`.

### 2. Orden de Borrado (Respetar Integridad Referencial)
Para evitar fallas de Llave Foránea (FK), eliminar los registros simulados (`is_mock = true`) en este orden estricto:

1. **Líneas de Pedido y Chats**:
   `DELETE FROM {schema}.items_pedido WHERE is_mock = true;`
   Chats mock (spec 013 — fuente canónica core):
   `DELETE FROM core.conversation_events WHERE tenant_id = '{tenant_id}' AND event_payload->>'is_mock' = 'true';`
   (Legacy/fallback, si el tenant aún tiene datos ahí: `DELETE FROM {schema}.n8n_chat_histories WHERE is_mock = true;`)
2. **Cabecera de Pedidos e ia_tickets**:
   `DELETE FROM {schema}.pedidos WHERE is_mock = true;`
   `DELETE FROM {schema}.ia_tickets WHERE is_mock = true;`
3. **Zonas y Vendedores**:
   `DELETE FROM {schema}.vendedor_geo_zones WHERE is_mock = true;` (si aplica)
   `DELETE FROM {schema}.geo_zones WHERE is_mock = true;`
   `DELETE FROM {schema}.vendedores WHERE is_mock = true;`
4. **Clientes**:
   `DELETE FROM {schema}.clients WHERE is_mock = true;`
5. **Catálogo y Precios**:
   `DELETE FROM {schema}.promociones_semanales WHERE is_mock = true;`
   `DELETE FROM {schema}.precios_productos WHERE is_mock = true;`
   `DELETE FROM {schema}.productos_aliases WHERE product_code IN (SELECT product_code FROM {schema}.productos WHERE is_mock = true);`
   `DELETE FROM {schema}.productos WHERE is_mock = true;`
6. **Mapeos de Ventas Globales**:
   `DELETE FROM public.tenant_cross_sell_mappings WHERE tenant_id = '{tenant_id}' AND is_mock = true;`
   `DELETE FROM public.tenant_up_sell_mappings WHERE tenant_id = '{tenant_id}' AND is_mock = true;`

### 3. Salida Local (Output)
Generar el reporte de la purga en:
**`implementacion/{schema}/outputs/phase-10-purga-log.csv`**

Columnas: `tabla`, `filas_borradas`, `ok`, `notes`.

---

## 🔒 Restaurar Seguridad en MCP
> [!IMPORTANT]
> Inmediatamente después de completar la purga, recuerda restaurar el valor `&read_only=true` en el archivo `.cursor/mcp.json` para bloquear accesos de escritura accidentales en futuras sesiones.

---

## 🏁 Cierre de la Fase
1. Actualizar `manifest.yaml` estableciendo `fases["10"].estado = "cargado"` y registrando la fecha en `cargado_at`.
2. Informar al implementador. El tenant queda purgado y listo para producción.
