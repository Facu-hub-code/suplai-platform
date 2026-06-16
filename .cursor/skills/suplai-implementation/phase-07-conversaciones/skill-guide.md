# Guía de Uso — Fase 7: Conversaciones (suplai-implementation-phase-07)

Esta guía detalla los pasos para poblar el historial de chat del agente en la base de datos de forma determinista, reutilizable por esquema y alineada a los pedidos creados en la Fase 6.

> [!NOTE]
> **Ejecución por scripts (obligatoria)**
> La Fase 7 no se resuelve con inserciones manuales. Primero se genera el resumen local y el detalle de mensajes con `preparar_conversaciones.py`, y luego se carga el historial con `cargar_conversaciones.py`. El objetivo es reutilizar exactamente el mismo flujo para cualquier esquema y evitar alucinaciones.

---

## 📋 Requisitos Previos

1. **Clientes cargados**: Las Fases 4 y 5 deben estar completas.
2. **Pedidos cargados**: Deben existir `phase-06-pedidos.csv` y `phase-06-items-pedido.csv`.
3. **Estructura de Chats**: Confirmar que `{schema}.n8n_chat_histories` tenga `session_id`, `message` (`jsonb`), `created_at` e `is_mock`.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Preparación de conversaciones
Ejecutar:

```bash
python scripts/fase-07-conversaciones/preparar_conversaciones.py --esquema <schema>
```

El preparador:
- Lee `phase-06-pedidos.csv` y `phase-06-items-pedido.csv`.
- Lee los clientes de Fase 4 y los flags de Fase 5.
- Genera entre 10 y 15 clientes con `live_feed=true` e `is_unread=true`.
- Genera el resto como conversaciones archivadas.
- Construye 4 a 5 mensajes por conversación.
- Reserva un subgrupo de 3 a 5 clientes con reclamos coherentes para que la Fase 8 pueda crear tickets correlacionados.

### 2. Regla de cierre seguro
- El último mensaje de cada conversación **DEBE** ser de tipo `ai`.
- Si el flujo natural termina en `human`, el script agrega una respuesta final de contingencia.
- El cargador valida que no queden sesiones cuyo último mensaje sea `human`.

### 3. Salida Local
Se generan dos archivos:

1. `implementacion/{schema}/outputs/phase-07-conversaciones-resumen.csv`
2. `implementacion/{schema}/outputs/phase-07-mensajes.csv`

El resumen usa estas columnas:

`client_phone, cantidad_mensajes, ultimo_mensaje_at, is_unread, live_feed, is_mock`

---

## 💾 Carga a la Base de Datos

Ejecutar:

```bash
python scripts/fase-07-conversaciones/cargar_conversaciones.py --esquema <schema>
```

El cargador:
- Limpia los chats mock previos.
- Inserta el historial desde `phase-07-mensajes.csv`.
- Guarda cada mensaje como `jsonb` en la columna `message` con `sender_type`, `type`, `content`, `created_at` y `session_id`.
- Verifica conteos y que el último mensaje por sesión haya quedado en `ai`.

**Nota:** `session_id` suele coincidir con el número telefónico del cliente sin el símbolo `+`.

---

## 🔍 Verificación Post-Carga

```sql
SELECT COUNT(*) FROM {schema}.n8n_chat_histories WHERE is_mock = true;
```

Adicionalmente, el script reporta si alguna conversación termina en `human`.

---

## 🏁 Cierre de la Fase

1. Actualizar `manifest.yaml` estableciendo `fases["07"].estado = "cargado"` y registrando `cargado_at`.
2. Proceder a la Fase 8.
