---
name: suplai-implementation-phase-09
description: Fase 9 pruebas e2e — Suite de pruebas y validaciones conversacionales. Usar tras Fase 8.
---

# Fase 9 — Pruebas E2E y Healthcheck del Agente

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

Este flujo permite validar que el agente de Suplai Sales de una distribuidora esté configurado correctamente en base de datos y funcione sin errores ni latencias excesivas en sus flujos de conversación típicos.

---

## 1. Identificar el Esquema del Tenant
1. Preguntar al usuario por el **`esquema`** de la distribuidora (ej: `vadra`). Si ya fue provisto en el prompt inicial, proceder directamente.

---

## 2. Ejecutar Healthcheck de Base de Datos
1. Ejecutar el script `scripts/fase-09-e2e/healthcheck_schema.py` para analizar el estado de configuración de la distribuidora:
   ```bash
   python scripts/fase-09-e2e/healthcheck_schema.py --schema {esquema}
   ```
2. Si el healthcheck reporta fallos:
   - **Herramientas (tools_habilitadas):** Si hay demasiadas tools asignadas, **NO** editarlas de forma automática. Detenerse y sugerir al usuario la desactivación interactiva de las herramientas innecesarias según el perfil (seller o client). Si da su aprobación, correr el script con el flag `--fix-tools`.
   - **Cliente de prueba:** Si no existe el cliente `suplai-platform-test` con teléfono `5491133333333`, el script de E2E lo creará al iniciar las pruebas o el healthcheck lo insertará al correr con `--fix-tools`.
   - **Descripciones vacías:** Recomendar al usuario ejecutar la skill `enhance-descriptions` para enriquecerlas.
   - **Tags o categorías vacías:** Recomendar y pedir aprobación para disparar la taxonomía automática. Si se aprueba, el script puede automatizar las llamadas a la API del backend.
   - **Category/Product RAG:** Si faltan vectorizar productos o categorías, el script encolará la re-vectorización vía endpoints REST del backend.

---

## 3. Generar y Ejecutar Pruebas Conversacionales E2E
1. Confirmar con el usuario si el agente a probar opera en modo **Asistente de Vendedor** (`--seller=true`) o modo **Cliente Final** (`--seller=false`).
2. Correr el script de pruebas E2E, que generará 10 casos específicos y disparará los mensajes midiendo latencia y validando llamadas a herramientas:
   ```bash
   python scripts/fase-09-e2e/test_agent_e2e.py --schema {esquema} [--seller {true/false}]
   ```
3. El script consultará el log de ejecución de herramientas (`core.agent_tool_runs`) para cada paso mediante consultas directas a PostgreSQL.

---

## 4. Análisis Proactivo de Resultados e Iteración
1. Abrir y analizar el reporte final generado en:
   `implementacion/{esquema}/outputs/reporte_e2e_{timestamp}.md`
2. **Validar y Corregir el Reporte (Rol del Agente del IDE):** Como agente del IDE con acceso a todo el código, base de datos e historial de ejecución, debes verificar críticamente los resultados clasificados como `🔴 FAIL` por el auditor de OpenAI. Si identificas falsos negativos, modifica el archivo del reporte markdown por tu cuenta. Cambia el estado del caso a `🟢 PASS`, actualiza los contadores del resumen ejecutivo y añade una aclaración en la sección de análisis del caso (ej: `*[Corrección del Agente del IDE]*: El auditor marcó FAIL por X, pero el comportamiento es correcto porque Y`).
3. Identificar las herramientas que provocaron alta latencia o respuestas incorrectas del LLM y sugerir optimizaciones.

---

## 5. Cierre de la Fase

1. Escribir el reporte final y validado en el directorio de outputs del tenant.
2. Actualizar `manifest.yaml` estableciendo `fases["09"].estado = "cargado"` y registrando la fecha en `cargado_at`.
3. Proceder a la Fase 10 (Purga Mock).
