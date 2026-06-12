# Guía de Uso — Fase 7: Conversaciones (suplai-implementation-phase-07)

Esta guía detalla los pasos para poblar el historial de chat del agente en la base de datos (n8n_chat_histories) para simular conversaciones activas y pendientes.

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Como agente de IA, lee el catálogo de clientes insertados y genera de 3 a 5 mensajes mock por cliente para construir la ilusión de un historial de chat en el backoffice de Suplai Sales.

---

## 📋 Requisitos Previos

1. **Clientes cargados**: La Fase 4 y la Fase 5 deben estar completas.
2. **Estructura de Chats**: Confirmar las columnas reales de la tabla `{schema}.n8n_chat_histories`.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Simulación del Historial
Para cada uno de los clientes:
- Generar un bloque de conversación simulado de **3 a 5 mensajes**:
  1. *Mensaje del agente*: Saludo inicial y presentación (ej: "Hola, soy Facu de Colormix...").
  2. *Mensaje del agente*: Oferta o recordatorio de la promoción generada en la Fase 2.
  3. *Respuesta del cliente*: Mensaje corto comercial (ej: "Hola, anotame una caja", "Buen día, pasame precios").

- **Distribución de Chats Recientes**:
  - **10 a 15 clientes**: Su último mensaje debe tener marca temporal de hoy (`NOW() - 0 a 12 horas`) y marcarse como `live_feed = true` / `is_unread = true`.
  - **35 a 40 clientes**: Conversaciones archivadas. Último mensaje de hace 1 o 2 días.

### 2. Salida Local (Output)
Generar el archivo CSV de control en:
**`implementacion/{schema}/outputs/phase-07-conversaciones-resumen.csv`**

Columnas: `client_phone`, `cantidad_mensajes`, `ultimo_mensaje_at`, `is_unread`, `live_feed`, `is_mock`.

---

## 💾 Carga a la Base de Datos (MCP Supabase)

Realizar inserciones en lotes en la tabla `{schema}.n8n_chat_histories`:
```sql
INSERT INTO {schema}.n8n_chat_histories (
    session_id, sender_type, message, created_at, is_mock
) VALUES (...)
```
*(Nota: `session_id` suele coincidir con el número telefónico del cliente sin el símbolo +).*

---

## 🔍 Verificación Post-Carga
```sql
SELECT COUNT(*) FROM {schema}.n8n_chat_histories WHERE is_mock = true;
```

---

## 🏁 Cierre de la Fase
1. Actualizar `manifest.yaml` estableciendo `fases["07"].estado = "cargado"` y registrando la fecha en `cargado_at`.
2. Proceder a la Fase 8.
