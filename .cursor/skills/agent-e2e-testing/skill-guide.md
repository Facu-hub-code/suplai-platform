# Guía de Uso — Testing E2E y Healthcheck del Agente (`agent_e2e_testing`)

Esta guía sirve como fuente de verdad para entender, preparar, ejecutar y auditar el estado del agente conversacional de un tenant en Suplai.

---

## 📋 Requisitos Previos

Antes de ejecutar la skill, asegúrate de cumplir con los siguientes prerrequisitos en el entorno local:

### 1. Variables de Entorno (`.env`)
Debes tener un archivo `.env` configurado en la raíz del proyecto (`suplai-platform/`) con las siguientes credenciales:
```env
SUPABASE_DB_URL=postgresql://<usuario>:<password>@db.nxmeezcvjltlqfybbczt.supabase.co:5432/postgres
OPENAI_API_KEY=tu-api-key-de-openai
OPENAI_MODEL=gpt-4o-mini
# Solo para --suite real|hybrid con perfil vendedor (teléfono en {schema}.vendedores):
E2E_SELLER_PHONE=5493XXXXXXXX
```

### 2. Dependencias de Python
Instala las librerías necesarias:
```bash
pip install asyncpg requests python-dotenv httpx
```

---

## 🚀 Paso 1: Healthcheck de Base de Datos (`healthcheck_schema.py`)

Este script se conecta directamente a Supabase para verificar si la distribuidora cumple con los requisitos mínimos para el correcto funcionamiento del agente.

### Forma de uso:
```bash
# Modo solo lectura (auditoría)
python scripts/fase-09-e2e/healthcheck_schema.py --schema <nombre_esquema>

# Modo aplicación de auto-fixes (previo acuerdo con el usuario)
python scripts/fase-09-e2e/healthcheck_schema.py --schema <nombre_esquema> --fix-tools
```

### Validaciones que realiza:
1. **Teléfono del Agente:** Que `agent_phone_number` en `public.distribuidoras` esté configurado.
2. **Productos Activos con Stock:** Que haya filas en `{esquema}.productos` con `en_catalogo = true` y `stock > 0`.
3. **Descripciones:** Que los productos tengan descripción comercial (sin fluff publicitario). Si faltan, el script sugerirá correr la skill `enhance-descriptions`.
4. **Categorías (Tags):** Que los productos tengan al menos una categoría asociada en `{esquema}.product_tags`. Si faltan, sugerirá proponer y aplicar taxonomía.
5. **RAG de Productos:** Que los productos activos tengan su correspondiente embedding en `{esquema}.documents`. Si faltan, encolará la re-vectorización.
6. **RAG de Categorías:** Que los tags del catálogo tengan su correspondiente embedding en `{esquema}.category_documents`. Si faltan, encolará la re-vectorización.
7. **Clientes:** Que exista al menos un cliente en `{esquema}.clients` para asociar la conversación. Si no hay ninguno, creará un cliente de prueba.
8. **Exceso de Herramientas:** Si hay 0 tools deshabilitadas (lo que degrada el rendimiento de la IA), el script te sugerirá desactivar un set de herramientas innecesarias según el perfil de vendedor/cliente final.

---

## 🧪 Paso 2: Ejecución del Suite de Pruebas E2E (`test_agent_e2e.py`)

Este script genera dinámicamente un conjunto de 10 casos de prueba conversacionales, los ejecuta contra el webhook de producción y mide la precisión en la respuesta y la correcta selección de herramientas.

### Forma de uso:
```bash
# Ejecutar pruebas independientes con aislamiento total (carrito/contexto limpio por cada caso, recomendado)
python scripts/fase-09-e2e/test_agent_e2e.py --schema <nombre_esquema>

# Ejecutar pruebas en un flujo secuencial continuado (manteniendo estado de carrito/conversación entre casos 1-9)
python scripts/fase-09-e2e/test_agent_e2e.py --schema <nombre_esquema> --sequential

# Ejecutar pruebas para perfil vendedor asistente
python scripts/fase-09-e2e/test_agent_e2e.py --schema <nombre_esquema> --seller

# Limitar cantidad de casos para smoke-test rápido
python scripts/fase-09-e2e/test_agent_e2e.py --schema <nombre_esquema> --limit 2

# --- Casos reales del distribuidor (fixtures en implementacion/{schema}/casos-reales/) ---
python scripts/fase-09-e2e/test_agent_e2e.py --schema <nombre_esquema> --suite real --seller --sequential
python scripts/fase-09-e2e/test_agent_e2e.py --schema <nombre_esquema> --suite real --seller --sequential --expand 3
python scripts/fase-09-e2e/test_agent_e2e.py --schema <nombre_esquema> --suite hybrid --seller
```

### Modos de suite (`--suite`)

| Modo | Origen de casos | Cuándo usarlo |
|------|-----------------|---------------|
| `generic` (default) | LLM genera 10 casos desde catálogo/tags | Smoke test de catálogo, regresión general |
| `real` | Fixtures en `implementacion/{schema}/casos-reales/` | Validar un caso de uso concreto del distribuidor |
| `hybrid` | Casos reales + suite genérica | Regresión amplia tras validar el flujo prioritario |

El módulo `scripts/e2e_real_cases.py` carga manifest, contexto y casos; valida SKUs/tools; y con `--expand N` genera variantes similares leyendo `contexto.md`.

### Preparar casos reales (rol del agente del IDE)

1. **Crear carpeta** `implementacion/{schema}/casos-reales/` (copiar plantilla desde `.cursor/skills/agent-e2e-testing/templates/casos-reales/`).
2. **Escribir `contexto.md`**: narrativa AS-IS / TO-BE que el LLM usa al expandir (ej. Benfresh: teléfono central, reenvíos de vendedores, carga manual → automatización).
3. **Configurar `manifest.json`**: `profile` (`seller`|`client`), `sequential_default`, `seller_phone_env`.
4. **Por cada escenario**, carpeta `casos/NN-slug/` con:
   - `caso.json` — metadatos y expectativas (`expected_tools`, `expected_tools_any`, `expected_skus`, `client_identifier` para seller).
   - `mensaje.txt` — texto WhatsApp que se envía al webhook.
   - `mensaje_simulado.txt` (opcional) — para fotos: `[Consulta con foto por WhatsApp]` + OCR simulado.
   - `imagen.jpg/png` (opcional) — solo referencia documental; no se sube al webhook v1.
5. **Consultar catálogo** (MCP Supabase o healthcheck) para SKUs y tools habilitadas del tenant antes de definir expectativas.
6. **Referencia completa:** `implementacion/benfresh/casos-reales/` (4 casos: seleccionar cliente, lista texto, foto simulada, confirmar pedido).

### Detalle del Flujo de Ejecución:
1. **Cliente de pruebas:** El script verifica que exista el cliente de pruebas `suplai-platform-test` con teléfono `5491133333333` (creado previamente por el healthcheck).
2. **Aislamiento de Estado Limpio (Cleanup):**
   * **Modo Aislamiento (Por Defecto):** Antes de ejecutar **cada** caso de prueba individual del bucle, el script limpia por completo los pedidos del cliente en base de datos (`{schema}.pedidos` y `{schema}.items_pedido`) y su contexto en el backend (`DELETE /{schema}/conversaciones/{conversation_id}/context`). Esto previene que la memoria conversacional anterior afecte el resultado actual.
   * **Modo Secuencial (`--sequential`):** Limpia la base de datos y la memoria conversacional **únicamente una vez al iniciar la suite**. Los casos 1 al 9 se ejecutan de manera encadenada (e.g. agregando ítems, sugiriendo cross-sell y finalmente confirmando la compra), mientras que el caso 10 simula un flujo onboarding desde un número diferente.
3. **Generación / carga de casos:**
   * **Modo `generic`:** Lee productos y categorías del catálogo y genera 10 casos (Directo, Multi-ítem, Consulta de precio, Desambiguación, Filtro semántico, Código de producto, Presentación de empaque, Ticket alto/Premium, Cross-sell/Follow-up, Teléfono no registrado).
   * **Modo `real`:** Carga `implementacion/{schema}/casos-reales/casos/*/caso.json` + mensajes; respeta `sequential_order`; usa `E2E_SELLER_PHONE` si `profile=seller`.
   * **Modo `hybrid`:** Ejecuta casos reales primero y luego añade la suite genérica.
   * **`--expand N`:** Tras cargar casos reales, el LLM genera N variantes similares usando `contexto.md` y el catálogo (marcadas `[generado]` en el reporte).
4. **Validación Determinista Rigurosa:**
   * Verifica la correcta estructura del JSON, IDs correlativos de 1 a 10 y herramientas existentes.
   * Valida la presencia de herramientas requeridas por tipología (ej: Caso 1 debe esperar `search_products`, Caso 2 herramientas de orden, etc.) según el rol (`seller` vs `client`).
   * Para casos específicos de producto (Casos 1, 2, 3, 6, 7), valida que el mensaje simulado mencione explícitamente el código SKU o alguna palabra significativa del nombre del producto real, evitando falsos positivos o alucinaciones del LLM en la generación.
5. **Activar Traza de Lab:** Actualiza `public.distribuidoras.metadata` temporalmente para establecer `implementation_debug.trace_enabled = true` durante el test.
6. **Inbound Webhook:** Envía cada mensaje a `https://agente-conversacional-multitenant-production.up.railway.app/webhook` midiendo el tiempo de respuesta.
7. **Trace Lookup:** Consulta las tablas `core.agent_turns` y `core.agent_tool_runs` usando el schema, teléfono y timestamps del test para extraer exactamente qué tools llamó el agente y su latencia.
8. **Restaurar Configuración:** Reestablece el valor original de `trace_enabled` en la base de datos.
9. **Evaluación de Respuestas (LLM):** Utiliza OpenAI para clasificar el resultado de cada caso como `PASS` o `FAIL` según el comportamiento e intent esperado del agente.
10. **Generación de Reporte:** Escribe el resultado en `implementacion/{esquema}/outputs/reporte_e2e_{timestamp}.md`.

---

## 📈 Paso 3: Validación Crítica y Optimización Proactiva por el Agente

Al finalizar el test, el agente del IDE no debe confiar ciegamente en la evaluación automática de OpenAI. Debe realizar un análisis crítico e interactuar con los resultados antes de presentarlos:

### 1. Auditoría de Falsos Negativos (FAIL incorrectos)
Revisa detalladamente las respuestas y trazas de las pruebas marcadas como `🔴 FAIL`.
* **Criterio de corrección:** Si el bot resolvió correctamente la conversación (ej: listando opciones para desambiguar y pidiendo confirmación, o editando una orden existente en modo secuencial) pero el auditor de OpenAI lo reprobó por rigidez sintáctica, **edita el archivo Markdown del reporte**.
* **Cómo editar:**
  1. Cambia el estado en la tabla resumen a `🟢 PASS`.
  2. Ajusta el conteo del Resumen Ejecutivo (ej: de `6/10` a `8/10` Aprobados y el porcentaje correspondiente).
  3. En la sección de detalle del caso, reemplaza `(🔴 FAIL)` por `(🟢 PASS)`.
  4. Añade una aclaración en negrita al inicio de la sección de análisis del caso: `*[Corrección del Agente del IDE]*: El auditor original clasificó esto como FAIL debido a X, pero tras validar la ejecución determinamos que es un PASS porque Y.`

### 2. Propuestas de Optimización y Diagnóstico de Errores Críticos

#### 🚫 Protocolo ante Errores Críticos (ej: `no_price_for_list`, errores de base de datos)
Si durante la auditoría o la ejecución de las pruebas detectas fallos generalizados o errores críticos de configuración/datos (como productos sin precio en la lista del cliente, herramientas esenciales apagadas o problemas de conectividad):
1. **Detenerse de inmediato**: No realices re-ejecuciones de prueba en bucle.
2. **Inspeccionar y analizar**: Investiga la base de datos o el código del agente (ej. haciendo consultas SQL mediante scripts temporales en `scratch/` o revisando la consola) para encontrar la causa raíz.
3. **Explicar al usuario**: Explica de forma estructurada qué falló, por qué ocurrió (ej. "la lista de precios del cliente no contiene precios para los SKUs seleccionados") y cuál es la solución propuesta.
4. **Obtener aprobación**: Presenta el plan de corrección al usuario y **espera su visto bueno explícito**. No hagas cambios en caliente sin su consentimiento.
5. **Aplicar y proponer re-ejecución**: Tras recibir la aprobación, aplica la solución en la base de datos o en los archivos de configuración y pregunta al usuario si desea volver a lanzar el test. **Espera a que dé su confirmación para disparar el comando de prueba de nuevo.**

#### ⚡ Recomendaciones de Optimización de Performance
Presenta al usuario propuestas de mejora accionables basadas en la ejecución real:
* **Desactivar herramientas:** Si detectas que se ejecutan herramientas que aumentan la latencia y no son necesarias para el rubro (ej: RAG de categorías para consultas simples).
* **Ajustar System Prompt:** Si el agente realmente alucina SKUs o no cumple con directrices de empaque, sugerir refinar el campo `public.distribuidoras.contexto` o `reglas_negocio`.
* **Re-correr:** Si el usuario aprueba los cambios, aplícalos en base de datos y vuelve a correr la prueba para verificar la mejora (siempre esperando su confirmación previa).

