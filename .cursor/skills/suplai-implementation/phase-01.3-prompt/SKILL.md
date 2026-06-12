---
name: suplai-implementation-phase-01-3
description: Fase 1.3 Personalización del Prompt — Definir identidad, contexto y reglas de negocio del agente mediante LLM. Usar tras Fase 1.1 cargada.
---

# Fase 1.3 — Personalización del Prompt del Agente

> [!IMPORTANT]
> **MANDATORIO**: Antes de proceder con esta fase, el agente debe leer **SIEMPRE** el archivo `skill-guide.md` correspondiente a esta skill para asegurar la correcta ejecución del flujo y validación de los datos.

## Input

- [ ] Rubro comercial del distribuidor (ej. ferretería, golosinas, vinos).
- [ ] Reglas específicas e identidad del distribuidor (ej. "solo vende productos Arcor", "horario de atención de lunes a viernes de 8 a 17hs", etc.).
- [ ] Muestra del catálogo y nombre comercial del tenant (desde manifest).

## Output

1. **`phase-01-3-prompt-config.json`** (obligatorio) — JSON guardado en `implementacion/{schema}/outputs/` que contiene:
   - `identidad`: Definición del rol y personalidad del agente de WhatsApp.
   - `contexto`: Rubro, reglas generales, restricciones de zona y horario.
   - `reglas_negocio`: Objeto JSON con políticas de envío, marcas permitidas y mínimos de pedido.
   - `agent_phone_number`: Cadena de texto con un número telefónico aleatorio asignado para simular WhatsApp.

## Proceso de Ejecución

### 1. Inferencia del Prompt
Usar LLM pasándole la información comercial y restricciones del distribuidor para que redacte e infiera de forma estructurada:
- Una descripción en primera/tercera persona para `identidad`.
- Una especificación detallada de restricciones para `contexto`.
- Un set de propiedades clave en `reglas_negocio` (ej. `{"solo_marcas": ["arcor"], "monto_minimo_envio": 20000}`).

### 2. Generación del Archivo de Configuración
Escribir la propuesta estructurada en:
`implementacion/{schema}/outputs/phase-01-3-prompt-config.json`

### 3. Carga a la Base de Datos (MCP Supabase)
Realizar una actualización en la tabla maestra `public.distribuidoras` buscando por el `schema_name` del cliente para guardar la identidad, contexto, reglas de negocio y un número aleatorio de WhatsApp para simulación:
```sql
UPDATE public.distribuidoras 
SET 
  identidad = :identidad,
  contexto = :contexto,
  reglas_negocio = :reglas_negocio::jsonb,
  agent_phone_number = :agent_phone_number, -- Generar un número aleatorio de WhatsApp (ej: string de 10-12 dígitos numéricos)
  updated_at = NOW()
WHERE schema_name = :schema_name;
```

## Cierre de la Fase

- Registrar en `manifest.yaml`:
  - `fases["01.3"].estado = cargado`
  - `fases["01.3"].cargado_at = {timestamp_actual}`
- Invitar a la Fase 2 (Promociones).
