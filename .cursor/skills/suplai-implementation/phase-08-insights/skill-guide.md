# Guía de Uso — Fase 8: Insights y Notificaciones (suplai-implementation-phase-08)

Esta guía detalla los pasos para poblar las alertas de calidad, logística, administración y comercial (ia_tickets) de forma determinista, simulando un "efecto cruzado" exacto en el historial de chat con los clientes a través del pipeline de scripts.

> [!NOTE]
> **Ejecución por scripts (obligatoria)**
> La Fase 8 no se resuelve con inserciones manuales ni alucinadas por el agente. Primero se genera el resumen local mediante `preparar_insights.py` mapeando los datos reales del catálogo y quejas de la Fase 7, y luego se impacta la base de datos con `cargar_insights.py`. El objetivo es garantizar una coherencia relacional del 100%.

---

## 📋 Requisitos Previos

1. **Fase 7 completada**: El historial de chat y sus archivos resultantes (`phase-07-conversaciones-resumen.csv` y `phase-07-mensajes.csv`) deben existir.
2. **Estructura de ia_tickets**: Confirmar mediante introspección que la tabla `{schema}.ia_tickets` cuente con los campos reales del sistema: `id`, `created_at`, `description`, `client_id`, `status`, `closed_at` e `is_mock`.
3. **Estructura de Chats**: Validar que `{schema}.n8n_chat_histories` esté disponible para la inyección del efecto cruzado.

---

## 🚀 Paso a Paso de la Ejecución

### 1. Preparación de insights
Ejecutar:

```bash
python scripts/fase-08-insights/preparar_insights.py --esquema <schema>
```

El preparador:

- Lee la configuración del tenant bajo `fase_08` en `config.json` para obtener el total de tickets (entre 15 y 20) y las proporciones esperadas.
- Escanea el catálogo real del tenant e identifica la `marca_lider` del manifest para estructurar reclamos realistas.
- Cruza los datos con `phase-07-mensajes.csv` buscando palabras clave de quejas (`reclamo`, `demora`, `falto`, `roto`, etc.) para priorizar a esos clientes en los tickets abiertos.
- Divide los estados siguiendo la regla: ~60% abiertos (`open`) y ~40% cerrados (`closed`).
- Distribuye los tickets deterministamente en 4 categorías: **Calidad**, **Logistica**, **Comercial** y **Administracion**.

### 2. Regla del "Efecto Cruzado" (MANDATORIO)
Para cada ticket en estado `open` que pertenezca a **Calidad** o **Logistica**:
- El script asocia al cliente correspondiente y redacta un texto de incidente (`description`).
- Simultáneamente, genera la contraparte exacta en formato de mensaje entrante de chat (`mensaje_cruzado_incoming`), simulando que el cliente originó el reclamo por WhatsApp de forma natural.

### 3. Salida Local
Se genera un único archivo consolidado listo para la lectura del cargador:

`implementacion/{schema}/outputs/phase-08-notificaciones.csv`

El archivo contiene las columnas de control, marcas de tiempo deterministas calculadas sobre la `fecha_base` y el flag `is_mock` seteado en `true`.

---

## 💾 Carga a la Base de Datos

Ejecutar:

```bash
python scripts/fase-08-insights/cargar_insights.py --esquema <schema>
```

El cargador:
- Realiza una limpieza previa de los registros mock existentes en `{schema}.ia_tickets`.
- Mapea el identificador telefónico (`client_phone`) para resolver el ID interno de la tabla de clientes (`client_id`) requerido por la clave foránea.
- Realiza el `INSERT` de la colección de tickets en `{schema}.ia_tickets`.
- **Inyección Cruzada en Chat**: Para cada fila con un `mensaje_cruzado_incoming` válido, el script realiza un insert automático en `{schema}.n8n_chat_histories` estructurando el payload como un tipo `human` (utilizando el formato exacto `jsonb` de la tabla si corresponde) para reflejar la queja entrante en la cronología del chat.

---

## 🔍 Verificación Post-Carga

```sql
SELECT COUNT(*) FROM {schema}.ia_tickets WHERE is_mock = true;
```

Adicionalmente, el script de carga imprimirá en consola las métricas de control: cantidad total de tickets subidos, proporción de abiertos y volumen de mensajes inyectados de forma cruzada en el historial de chat.

## 🏁 Cierre de la Fase

1. Actualizar manifest.yaml estableciendo fases["08"].estado = "cargado" y registrando la fecha en cargado_at.

2. El onboarding mock se declara formalmente completo. Se le ofrece al usuario la prueba interactiva del agente en el entorno de backoffice o lab usando los datos consolidados del tenant.