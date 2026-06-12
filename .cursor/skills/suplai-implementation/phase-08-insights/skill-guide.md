# Guía de Uso — Fase 8: Insights y Notificaciones (suplai-implementation-phase-08)

Esta guía detalla los pasos para poblar las alertas de calidad, logística, administración y comercial (ia_tickets), simulando un "efecto cruzado" en el historial de chat con los clientes.

> [!NOTE]
> **Ejecución Directa por el Agente (Recomendado)**
> Como agente de IA, diseña de 15 a 20 tickets mock. El 60% debe estar abierto. Para los tickets abiertos de Calidad y Logística, es obligatorio inyectar un mensaje entrante (incoming) en el chat del cliente que narre el incidente para que el historial sea 100% coherente.

---

## 📋 Requisitos Previos

1. **Fases 1–7 completadas**: Los clientes y las conversaciones de chat deben estar cargados.
2. **Estructura de ia_tickets**: Verificar si la tabla en base de datos es `{schema}.ia_tickets` o `{schema}.tickets`.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Generación de Tickets
Crear entre 15 y 20 tickets mock distribuidos en 4 categorías:
- **Calidad**: Reclamo de mercadería dañada (ej: "Látex con pérdidas en envase de marca [Marca Líder]").
- **Logística**: Demoras en la entrega (ej: "El transporte no entregó el pedido del martes").
- **Comercial**: Consultas de cuentas o precios (ej: "Solicita hablar con el vendedor asignado").
- **Administración**: Errores de datos (ej: "Actualización de CUIT o razón social").

- **Volumen**:
  - 60% en estado `Abierto`.
  - 40% en estado `Cerrado` (o resuelto).
  - Fechas: Los abiertos deben tener fecha de hoy o hace máximo 3 días. Los cerrados deben ser de hace 5 a 20 días.

### 2. Lógica del "Efecto Cruzado" (MANDATORIO)
Por cada ticket en estado **Abierto** de Calidad o Logística:
- Identificar al cliente asociado.
- Inyectar en la tabla `{schema}.n8n_chat_histories` un mensaje entrante del cliente describiendo exactamente la misma problemática (ej. si el ticket es *"Rodillo roto"*, inyectar un mensaje del cliente diciendo *"Hola, me llegó el rodillo que compré quebrado, ¿me lo cambian?"*).

### 3. Salida Local (Output)
Generar el archivo CSV:
`outputs/phase-08-notificaciones.csv`

---

## 💾 Carga a la Base de Datos (MCP Supabase)
1. Insertar en `{schema}.ia_tickets`.
2. Insertar en `{schema}.n8n_chat_histories` los mensajes cruzados.

---

## 🔍 Verificación Post-Carga
```sql
SELECT COUNT(*) FROM {schema}.ia_tickets WHERE is_mock = true;
```

---

## 🏁 Cierre de la Fase
1. Actualizar `manifest.yaml` estableciendo `fases["08"].estado = "cargado"` y registrando la fecha en `cargado_at`.
2. Ofrecer formalmente al usuario realizar pruebas de chat con el agente cargado, informando que el onboarding ha finalizado con éxito.
