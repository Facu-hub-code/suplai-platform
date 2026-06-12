# Guía de Uso — Fase 5: Flags de Clientes (suplai-implementation-phase-05)

Esta guía detalla los pasos para actualizar y enriquecer a los 50 clientes mock de la base de datos asignándoles estados de validación de WhatsApp e identificadores del ERP (o marcándolos como prospectos).

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Como agente de IA, lee el CSV de clientes generado en la Fase 4 para actualizar la tabla `{schema}.clients` mediante sentencias `UPDATE` (vía Supabase MCP). No crees registros nuevos; solo actualiza los existentes.

---

## 📋 Requisitos Previos

1. **Fase 4 completada**: Los 50 clientes mock deben estar insertados.
2. **Chequeo de Columnas**: Verificar si el esquema de base de datos tiene campos como `whatsapp_estado`, `whatsapp_validado_at`, o `codigo` (ERP).

---

## 🚀 Paso a Paso de la Ejecución

### 1. Clasificación de Clientes (Distribución Fija)
Clasificar los 50 clientes de la siguiente forma:
- **40 Clientes de Cartera (ERP)**:
  - Asignar un `codigo` ERP numérico secuencial (iniciando en `25001`).
  - Marcar como `is_prospect = false` (o `prospecto = false`).
  - Dividir estados de WhatsApp: 30 marcados como `validado` / con `whatsapp_validado_at` seteado al timestamp actual; y 10 marcados como `existe` o `sin_validar`.
- **10 Clientes Prospectos**:
  - Asignar `codigo = 0`.
  - Marcar como `is_prospect = true`.
  - Mezclar el estado de WhatsApp de manera libre.

### 2. Salida Local (Output)
Generar el archivo CSV en la ruta:
**`implementacion/{schema}/outputs/phase-05-clientes-flags.csv`**

Columnas: `cliente_codigo`, `codigo_erp`, `is_prospect`, `whatsapp_status`.

---

## 💾 Carga a la Base de Datos (MCP Supabase)

1. **Chequear Enums**:
   ```sql
   SELECT DISTINCT whatsapp_estado FROM {schema}.clients;
   ```
2. **Ejecutar Actualizaciones**:
   Realizar actualizaciones por bloque o individuales a `{schema}.clients` buscando a los clientes correspondientes por teléfono o código interno.

---

## 🔍 Verificación Post-Carga
Comprobar los contadores:
```sql
SELECT COUNT(*) FROM {schema}.clients WHERE codigo > 0; -- Debe ser aproximadamente 40
SELECT COUNT(*) FROM {schema}.clients WHERE codigo = 0; -- Debe ser aproximadamente 10
```

---

## 🏁 Cierre de la Fase
1. Actualizar `manifest.yaml` estableciendo `fases["05"].estado = "cargado"` y registrando `cargado_at`.
2. Proceder a la Fase 6.
