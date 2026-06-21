---
name: agent_e2e_testing
description: Healthcheck de BD, pruebas E2E genéricas o basadas en casos reales del distribuidor (fixtures en implementacion/{schema}/casos-reales), con expansión LLM de variantes similares y análisis de trazas.
---

# E2E Testing & Healthcheck del Agente (agent_e2e_testing)

Este flujo permite validar que el agente de Suplai Sales de una distribuidora esté configurado correctamente en base de datos y funcione sin errores ni latencias excesivas en sus flujos de conversación típicos.

> [!IMPORTANT]
> **REGLA DE OBLIGADA LECTURA PARA EL AGENTE**: Antes de ejecutar cualquier paso de esta skill, el agente **DEBE LEER obligatoriamente** la guía de uso detallada en [skill-guide.md](./skill-guide.md). Esto asegura que se sigan las reglas de deshabilitación de herramientas, la creación del cliente de pruebas y el flujo de análisis/optimización.

### Skills vendor relacionadas (Tier 4 — no reemplazan este flujo)

| Skill vendor | Rol vs `agent-e2e-testing` |
|--------------|----------------------------|
| `llm-evaluation` | Diseñar métricas y detectar regresiones tras cambios de prompt — **antes/después** de correr E2E. |
| `eval-harness` | Definir criterios pass/fail formales (EDD) para nuevos casos de prueba. |
| `agent-evaluation` | Framework evals multi-turn (opcional; ver `skills-vendor.manifest.json`). |

**Regla:** Para validar un tenant en Suplai, **usar siempre esta skill** (`healthcheck_schema.py` + `test_agent_e2e.py`). Las vendor complementan diseño de evals, no sustituyen los scripts ni el cliente `suplai-platform-test`.

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

### 3a. Suite genérica (default)
1. Confirmar con el usuario si el agente opera en modo **Asistente de Vendedor** (`--seller`) o **Cliente Final** (sin flag).
2. Correr el script — genera 10 casos desde el catálogo real del tenant:
   ```bash
   python scripts/fase-09-e2e/test_agent_e2e.py --schema {esquema} [--seller] [--sequential] [--limit N]
   ```

### 3b. Suite de casos reales del distribuidor (nuevo)
Usar cuando el distribuidor comparte **mensajes reales, fotos de listas, flujos AS-IS** que quieren automatizar (ej. Benfresh: vendedores reenvían pedidos a un teléfono central).

**Estructura obligatoria:**
```
implementacion/{esquema}/casos-reales/
  manifest.json
  contexto.md
  casos/NN-slug/
    caso.json
    mensaje.txt | mensaje_simulado.txt
    imagen.* (opcional, referencia visual)
```

**Rol del agente del IDE al preparar casos:**
1. Leer `contexto.md` y materiales del distribuidor (textos, capturas en la carpeta del tenant).
2. Crear o completar `casos/*/caso.json` con `expected_behavior`, `expected_tools` / `expected_tools_any` y SKUs del catálogo.
3. Para fotos de listas: copiar la imagen como referencia y escribir `mensaje_simulado.txt` con prefijo `[Consulta con foto por WhatsApp]` + texto OCR/simulado (el webhook E2E actual no envía binario).
4. Plantilla de referencia: [templates/casos-reales/](./templates/casos-reales/) y ejemplo completo: `implementacion/benfresh/casos-reales/`.

**Variables extra para perfil vendedor:**
```env
E2E_SELLER_PHONE=5493XXXXXXXX  # teléfono registrado en {schema}.vendedores
```

**Comandos:**
```bash
# Solo casos reales (secuencial si manifest.sequential_default=true)
python scripts/fase-09-e2e/test_agent_e2e.py --schema {esquema} --suite real --seller --sequential

# Casos reales + N variantes similares generadas por LLM desde contexto.md
python scripts/fase-09-e2e/test_agent_e2e.py --schema {esquema} --suite real --seller --sequential --expand 3

# Híbrido: casos reales primero, luego suite genérica de catálogo
python scripts/fase-09-e2e/test_agent_e2e.py --schema {esquema} --suite hybrid --seller
```

**Modos de suite:** `generic` (default) | `real` | `hybrid`

3. El script consulta `core.agent_tool_runs` y marca en el reporte el origen de cada caso: `[real]`, `[generado]` o genérico.

---

## 4. Análisis Proactivo de Resultados e Iteración
1. Abrir y analizar el reporte final generado en:
   `implementacion/{esquema}/outputs/reporte_e2e_{timestamp}.md`
2. **Validar y Corregir el Reporte (Rol del Agente del IDE):** Como agente del IDE con acceso a todo el código, base de datos e historial de ejecución, debes verificar críticamente los resultados clasificados como `🔴 FAIL` por el auditor de OpenAI. Si identificas falsos negativos (por ejemplo, el auditor juzgando rígidamente una desambiguación correcta, o penalizando la acumulación de estado/herramientas de edición en modo secuencial), **modifica el archivo del reporte markdown por tu cuenta**. Cambia el estado del caso a `🟢 PASS`, actualiza los contadores del resumen ejecutivo y añade una aclaración en la sección de análisis del caso (ej: `*[Corrección del Agente del IDE]*: El auditor marcó FAIL por X, pero el comportamiento es correcto porque Y`).
3. Identificar las herramientas que provocaron alta latencia o respuestas incorrectas del LLM.
4. **Resolución de cliente fallida:** Si el reporte muestra `set_seller_selected_client` en error, cliente incorrecto (ej. match por `razon_social` genérica del ERP) o repregunta innecesaria con apodo comercial ("Nutrispa", "Dixie"), **proponer crear o actualizar la spec de aliases de clientes** (`agent/docs/specs/031-client-aliases-busqueda-vendedor.md`) documentando el alias recomendado en el fixture (`client_alias_recommended` en `caso.json`) y, tras aprobación, seed en BD o implementación del feature.
5. Proponer mejoras específicas al usuario (ej: desactivar tools no usadas, ajustar directrices de formato en el prompt de sistema del distribuidor en `public.distribuidoras.contexto`).
6. Si el usuario aprueba, aplicar los cambios en base de datos y volver a ejecutar las pruebas conversacionales para contrastar resultados.

---

## 5. Diagnóstico de Errores Críticos de Configuración o Datos (e.g. `no_price_for_list`, errores de red/BD)
Si durante el healthcheck o la ejecución de las pruebas E2E se identifican errores recurrentes o estructurales de configuración/datos (por ejemplo, fallas masivas con `no_price_for_list` debido a listas de precios sin productos asignados, errores de conexión, herramientas críticas deshabilitadas, etc.):
1. **Detenerse de inmediato**: No continuar con ejecuciones automáticas repetitivas sin corregir la causa raíz.
2. **Analizar la causa raíz**: Realizar las consultas o inspecciones necesarias en la base de datos o el código del agente para entender por qué ocurre el error.
3. **Explicar y Proponer**: Explicar de forma clara y concisa el problema al usuario y proponer la modificación exacta para solucionarlo (ya sea en el código de prueba, scripts, o registros de la base de datos).
4. **Esperar Aprobación**: No aplicar cambios que modifiquen la base de datos o el código del proyecto sin antes tener el visto bueno explícito del usuario.
5. **Solucionar y Proponer Re-ejecución**: Una vez aprobada la solución, aplicar los cambios requeridos y proponer al usuario volver a ejecutar la prueba. **Deberás esperar la confirmación y aprobación explícita del usuario en el chat antes de disparar la nueva ejecución.**

