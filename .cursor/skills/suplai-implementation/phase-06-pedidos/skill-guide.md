# Guía de Uso — Fase 6: Pedidos (suplai-implementation-phase-06)

Esta guía describe el flujo para simular la bandeja de pedidos del distribuidor, combinando un histórico cerrado (para estadísticas y analíticas de ML) con 6 o 7 pedidos pendientes y activos hoy.

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Genera los CSVs locales a partir del listado de clientes en base de datos. Asegúrate de calcular correctamente los totales sumando el precio individual de cada ítem según la lista de precios asignada a ese cliente. Luego ejecuta las sentencias de inserción en lotes.

---

## 📋 Requisitos Previos

1. **Catálogo y Precios cargados**: Las Fases 1, 1.1 y 1.3 deben estar completas.
2. **Red comercial**: Los clientes deben estar cargados en base de datos con sus respectivas relaciones de vendedor y zona comercial.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Generación de Pedidos
Dividir el lote de pedidos en:
- **Pedidos Históricos**: ~150 registros (~3 pedidos por cada uno de los 50 clientes).
  - Fechas: Entre marzo y mayo de 2026.
  - Estado: Cerrados (`entregado`, `facturado`, `confirmado`).
- **Pedidos Abiertos**: **6 o 7** registros en total (para clientes diferentes).
  - Fechas: Día de hoy (`NOW()`).
  - Estado: Abierto / Pendiente (`abierto`, `pendiente`).
  - *Must*: Asegurarse de que al menos uno de estos pedidos abiertos sea por un producto de la `marca_lider` y tenga aplicado un precio/descuento de promoción (Fase 2).

### 2. Generación de Ítems
Asociar a cada pedido de 1 a 4 productos del catálogo:
- Consultar la tabla `{schema}.precios_productos` para aplicar el precio unitario correspondiente al `lista_precios_id` asignado al cliente.
- En la columna `notas` del ítem, usar el formato de normalización de compras:
  `Pedido: {qty} {unidad} (normalizado: {canon}; equiv: {qty_umv} {umv})`

### 3. Salida Local (Outputs)
Escribir:
1. `outputs/phase-06-pedidos.csv`
2. `outputs/phase-06-items-pedido.csv`

---

## 💾 Carga a la Base de Datos (MCP Supabase)

1. **Insertar en `{schema}.pedidos`**: Generar las cabeceras de los pedidos y registrar su `id`.
2. **Insertar en `{schema}.items_pedido`**: Mapear cada ítem asociando el `pedido_id` correcto.
3. **Calcular y Actualizar Totales**: Actualizar la cabecera en `{schema}.pedidos` estableciendo la columna `total` como la suma aritmética del precio de sus ítems asociados.

---

## 🔍 Verificación Post-Carga
```sql
SELECT COUNT(*) FROM {schema}.pedidos WHERE es_pedido_abierto = true; -- Debe retornar 6 o 7
```

---

## 🏁 Cierre de la Fase
1. Actualizar `manifest.yaml` estableciendo `fases["06"].estado = "cargado"` y registrando la fecha en `cargado_at`.
2. Proceder a la Fase 7.
