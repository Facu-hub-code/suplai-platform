# Guía de Uso — Fase 6: Pedidos (suplai-implementation-phase-06)

Esta guía describe el flujo para simular la bandeja de pedidos del distribuidor, combinando un histórico cerrado (para estadísticas y analíticas de ML) con 6 o 7 pedidos pendientes y activos hoy.

> [!NOTE]
> **Ejecución por scripts (obligatoria)**
> La Fase 6 consume el resultado de la Fase 5 ya cargada con `scripts/fase-05-clientes-flags/`. Antes de generar pedidos, asegurate de que los clientes mock tienen `lista_precios_id`, `codigo` y estados de WhatsApp consistentes. Después ejecuta `preparar_pedidos.py` y `cargar_pedidos.py`.

---

## 📋 Requisitos Previos

1. **Catálogo y Precios cargados**: Las Fases 1, 1.1 y 1.3 deben estar completas.
2. **Red comercial**: Los clientes deben estar cargados en base de datos con sus respectivas relaciones de vendedor y zona comercial.
3. **Fase 5 cargada con scripts**: Debe existir `implementacion/{schema}/outputs/phase-05-clientes-flags.csv` y la tabla `{schema}.clients` debe reflejar esos flags.
4. **Promociones cargadas**: Tener disponibles `phase-02-promociones.csv` y `phase-01-listas-precios.csv` para calcular precios y el pedido abierto ancla con marca líder.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Generación de Pedidos
Ejecutar:

```bash
python scripts/fase-06-pedidos/preparar_pedidos.py --esquema <schema>
```

La preparación genera de forma determinista:
- **Pedidos Históricos**: ~150 registros (~3 pedidos por cada uno de los 50 clientes).
  - Fechas: Entre marzo y mayo de 2026 por defecto, configurables por `config.json` o flags CLI.
  - Estado: Cerrados (`entregado`, `facturado`, `confirmado`).
- **Pedidos Abiertos**: **6 o 7** registros en total.
  - Fechas: Hoy por defecto, también configurable.
  - Estado: Abierto / Pendiente (`abierto`, `pendiente`).
  - *Must*: al menos uno de los pedidos abiertos debe usar un producto de la `marca_lider` y aplicar la promo activa de la Fase 2 si existe.

### 2. Generación de Ítems
Los scripts hacen esto de forma automática:
- Asociar a cada pedido de 1 a 4 productos del catálogo.
- Tomar el precio desde `phase-01-listas-precios.csv` según el `lista_precios_id` del cliente.
- Aplicar la promo de Fase 2 en el pedido abierto ancla cuando corresponde.
- Escribir la nota del ítem con el formato:
  `Pedido: {qty} {unidad} (normalizado: {canon}; equiv: {qty_umv} {umv})`

### 3. Salida Local (Outputs)
Escribir:
1. `outputs/phase-06-pedidos.csv`
2. `outputs/phase-06-items-pedido.csv`

Los CSV pueden incluir columnas auxiliares como `cliente_phone`, `cliente_razon_social`, `lista_precios_id`, `nombre` y `promo_aplicada` para facilitar la carga y el consumo por Fase 7.

---

## 💾 Carga a la Base de Datos (MCP Supabase)

Ejecutar:

```bash
python scripts/fase-06-pedidos/cargar_pedidos.py --esquema <schema>
```

El script:
1. Limpia pedidos mock previos.
2. Inserta cabeceras en `{schema}.pedidos`.
3. Inserta ítems en `{schema}.items_pedido`.
4. Recalcula y actualiza el `total` de cada pedido.

---

## 🔍 Verificación Post-Carga
```sql
SELECT COUNT(*) FROM {schema}.pedidos WHERE es_pedido_abierto = true; -- Debe retornar 6 o 7
```

---

## 🏁 Cierre de la Fase
1. Actualizar `manifest.yaml` estableciendo `fases["06"].estado = "cargado"` y registrando la fecha en `cargado_at`.
2. Proceder a la Fase 7.
