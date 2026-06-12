# Guía de Uso — Fase 0: Preflight (suplai-implementation-phase-00)

Esta guía detalla las tareas para auditar, verificar y registrar que un tenant nuevo se encuentre en un estado vacío e ideal para iniciar el onboarding agéntico de Suplai Sales.

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Como agente de IA, debes correr estas validaciones de base de datos de manera autónoma utilizando el MCP de Supabase. Genera el reporte CSV en la carpeta de outputs y actualiza el archivo manifest con el `tenant_id` encontrado.

---

## 📋 Requisitos Previos

1. **schema_name**: El implementador debe haber provisto el nombre del esquema (ej. `colormix`).
2. **manifest.yaml**: Confirmar que se copió la estructura de la carpeta `implementacion/_template/` a `implementacion/{schema}/`.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Auditoría de Base de Datos (MCP Supabase)
Ejecutar las siguientes consultas para auditar el estado del tenant:

- **Existe distribuidora**:
  ```sql
  SELECT id, schema_name, nombre FROM public.distribuidoras WHERE schema_name = '{schema}';
  ```
- **Catálogo vacío**:
  ```sql
  SELECT COUNT(*) FROM {schema}.productos;
  ```
- **Clientes vacíos**:
  ```sql
  SELECT COUNT(*) FROM {schema}.clients;
  ```

### 2. Generación del Reporte CSV
Guardar los resultados obtenidos en `implementacion/{schema}/outputs/phase-00-preflight.csv` siguiendo el formato:
```csv
check_id,descripcion,resultado,evidencia
distribuidora_existe,Registro en public.distribuidoras,ok,tenant_id: UUID
schema_existe,Tablas en {schema},ok,schema verificado
productos_vacio,COUNT productos = 0,ok,0 productos encontrados
clients_vacio,COUNT clients = 0,ok,0 clientes encontrados
mcp_conectado,MCP supabase responde,ok,conectado
carpeta_implementacion,manifest.yaml presente,ok,verificado
```

---

## 🛑 Gate (Criterio de Aceptación)
Si `productos` o `clients` devuelven un conteo mayor a 0, detenerse de inmediato. Reportar la situación al implementador y no avanzar a la Fase 1 sin autorización explícita para evitar sobrescribir datos productivos.

---

## 🏁 Cierre de la Fase
1. Guardar el UUID obtenido de `public.distribuidoras` en el campo `tenant_id` de `implementacion/{schema}/manifest.yaml`.
2. Actualizar `manifest.yaml` estableciendo `fases["00"].estado = "cargado"` y registrando la fecha en `cargado_at`.
3. Informar al implementador y proceder a la Fase 1.
