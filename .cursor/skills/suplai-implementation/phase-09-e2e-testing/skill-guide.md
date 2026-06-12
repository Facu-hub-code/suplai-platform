# Guía de Uso — Fase 9: Testing E2E y Healthcheck del Agente (suplai-implementation-phase-09)

Esta guía sirve como fuente de verdad para entender, preparar, ejecutar y auditar el estado del agente conversacional de un tenant en Suplai como parte de la validación final del onboarding.

---

## 📋 Requisitos Previos

Antes de ejecutar la skill, asegúrate de cumplir con los siguientes prerrequisitos en el entorno local:

### 1. Variables de Entorno (`.env`)
Debes tener un archivo `.env` configurado en la raíz del proyecto (`suplai-platform/`) con las siguientes credenciales:
```env
SUPABASE_DB_URL=postgresql://<usuario>:<password>@db.nxmeezcvjltlqfybbczt.supabase.co:5432/postgres
OPENAI_API_KEY=tu-api-key-de-openai
OPENAI_MODEL=gpt-4o-mini
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
python scripts/healthcheck_schema.py --schema <nombre_esquema>

# Modo aplicación de auto-fixes (previo acuerdo con el usuario)
python scripts/healthcheck_schema.py --schema <nombre_esquema> --fix-tools
```

### Validaciones que realiza:
1. **Teléfono del Agente:** Que `agent_phone_number` en `public.distribuidoras` esté configurado.
2. **Productos Activos con Stock:** Que haya filas en `{esquema}.productos` con `en_catalogo = true` y `stock > 0`.
3. **Descripciones:** Que los productos tengan descripción comercial (sin fluff publicitario).
4. **Categorías (Tags):** Que los productos tengan al menos una categoría asociada en `{esquema}.product_tags`.
5. **RAG de Productos y Categorías:** Que los productos y categorías activas estén vectorizados en la base de datos.
6. **Clientes:** Que exista al menos un cliente en `{esquema}.clients` para asociar la conversación.
7. **Exceso de Herramientas:** Si hay 0 tools deshabilitadas, el script sugerirá desactivar un set de herramientas innecesarias según el perfil de vendedor/cliente final.

---

## 🧪 Paso 2: Ejecución del Suite de Pruebas E2E (`test_agent_e2e.py`)

Este script genera un conjunto de 10 casos de prueba conversacionales, los ejecuta contra el webhook de producción y mide la precisión en la respuesta y la correcta selección de herramientas.

### Forma de uso:
```bash
# Ejecutar pruebas independientes con aislamiento total (carrito/contexto limpio por cada caso, recomendado)
python scripts/test_agent_e2e.py --schema <nombre_esquema>

# Ejecutar pruebas para perfil vendedor asistente
python scripts/test_agent_e2e.py --schema <nombre_esquema> --seller
```

---

## 📈 Paso 3: Validación Crítica y Optimización por el Agente

Al finalizar el test, el agente del IDE debe realizar un análisis crítico de los resultados:

### 1. Auditoría de Falsos Negativos (FAIL incorrectos)
Revisa detalladamente las respuestas y trazas de las pruebas marcadas como `🔴 FAIL`.
* Si el bot resolvió correctamente la conversación pero el auditor de OpenAI lo reprobó por rigidez sintáctica, **edita el archivo Markdown del reporte** (`implementacion/{esquema}/outputs/reporte_e2e_{timestamp}.md`).
* Cambia el estado en la tabla resumen a `🟢 PASS`, ajusta el conteo del Resumen Ejecutivo, y añade la aclaración `*[Corrección del Agente del IDE]*` en la sección del caso correspondiente.

### 2. Protocolo ante Errores Críticos
Si durante la auditoría o la ejecución de las pruebas detectas fallos generalizados de base de datos o de configuración:
1. **Detenerse de inmediato**: No realices re-ejecuciones de prueba en bucle.
2. **Inspeccionar y analizar** mediante scripts o consultas SQL para encontrar la causa raíz.
3. **Explicar al usuario** la causa raíz y proponer la solución.
4. **Obtener aprobación** explícita del usuario antes de aplicar el fix.
5. **Re-correr** la prueba una vez solucionado.

---

## 🏁 Cierre de la Fase
1. Actualizar `manifest.yaml` estableciendo `fases["09"].estado = "cargado"` y registrando la fecha en `cargado_at`.
2. Proceder a la Fase 10 (Purga Mock) si se requiere limpiar los datos simulados de pruebas.
