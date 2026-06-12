---
name: analyze-system-prompt
description: >-
  Analiza la composición del system prompt de un tenant Suplai (agente + tools):
  capas ensambladas, duplicaciones, incoherencias, tokens y impacto en latencia.
  Usar cuando el usuario pida auditar, revisar o optimizar el prompt de un
  distribuidor, detectar reglas repetidas, o diagnosticar degradación de
  performance por contexto inflado.
---

# Analizar composición del system prompt (tenant)

Auditoría **read-only** del contexto que consume el LLM en cada turno del agente WhatsApp. No modifica BD ni código salvo que el usuario lo pida después del reporte.

> **Leer antes de ejecutar:** [checklist.md](checklist.md) — dimensiones de análisis y clusters de duplicación conocidos.

## Cuándo usar

- Revisar prompt de un tenant existente (post-implementación o producción).
- Diagnosticar latencia alta atribuible a prompt/tools inflados (ver `agent/docs/improvements_roadmap.md` QW3/QW6).
- Validar migración legacy → `system_prompt` v2.
- Comparar perfiles **client** vs **seller**.

**No confundir con:** `suplai-implementation/phase-01.3-prompt` (crea prompts nuevos en onboarding).

---

## Inputs requeridos

| Dato | Obligatorio | Default |
|------|-------------|---------|
| `schema_name` | Sí | — |
| Perfil | No | ambos (`client` + `seller`) |
| Incluir tool descriptions | No | sí |

---

## Flujo de trabajo

### 1. Cargar composición canónica (fuente de verdad)

**Preferir preview server-side** (mismo ensamblado que runtime):

```http
POST https://web-production-f544f.up.railway.app/{schema}/system-prompt/preview
Content-Type: application/json
x-schema-name: {schema}

{"actor_profile": "client"}   # o "seller"
```

Respuesta: secciones `prompt_mode`, `base_editable`, `tenant_editable`, `full_prompt`.

**Alternativa MCP Supabase** (`project_ref=nxmeezcvjltlqfybbczt`):

```sql
SELECT schema_name, identidad, contexto, system_prompt,
       agent_base_prompt_client, agent_base_prompt_seller,
       reglas_negocio, metadata, tools_descripciones, tools_habilitadas
FROM public.distribuidoras
WHERE schema_name = :schema
LIMIT 1;
```

Reconstruir mentalmente con `agent/app/agent/system_prompt_builder.py` (mismo contrato que backend `services/system_prompt_builder.py`):

```
full = base_block
     + channel_blocks (si deterministic_channel en metadata)
     + unit_policy (desde reglas_negocio.unit_policy)
     + open_order_snapshot (runtime; vacío en preview estático)
     + tenant_profile
```

### 2. Cargar tool descriptions efectivas

Para cada perfil, listar tools habilitadas y su texto:

- Defaults: `agent/app/agent/tools/registry.py` → `DEFAULT_TOOL_DESCRIPTIONS`
- Overrides: `distribuidoras.tools_descripciones[tool_name]`
- Filtro: `tools_habilitadas[tool_name] !== false`

Las tools **no** van dentro del `SystemMessage`, pero sí en cada llamada `bind_tools` → cuentan para latencia y selección.

### 3. Descomponer en capas

Etiquetar cada párrafo/regla con su capa:

| Capa | Editable en backoffice | Origen |
|------|------------------------|--------|
| `base` | Sí (v2) | `agent_base_prompt_{client\|seller}` o default código |
| `channel` | metadata | `assistant_channels.*.deterministic_channel` |
| `unit_policy` | parcial | `reglas_negocio.unit_policy` + bloque fijo código |
| `tenant` | Sí | `system_prompt` (v2) o identidad+contexto+reglas_y (legacy) |
| `snapshot` | runtime | pedido abierto del turno |
| `tools` | parcial | registry + `tools_descripciones` |

### 4. Ejecutar análisis (ver checklist.md)

Prioridad de hallazgos:

1. **🔴 Crítico** — contradicción operativa (ej. tenant pide narrar totales + canal determinístico prohíbe redactar).
2. **🟠 Performance** — mismo concepto en ≥2 capas sin valor añadido (SKU, confirm_order, unidades, list_seller_clients).
3. **🟡 Mantenimiento** — legacy duplicado con v2, JSON crudo en texto, reglas obsoletas.
4. **🟢 OK / informativo** — redundancia menor aceptable por claridad.

### 5. Métricas

Ejecutar script local (opcional):

```bash
python .cursor/skills/analyze-system-prompt/scripts/measure_context.py \
  --system-prompt-file /tmp/{schema}-full-client.txt \
  --tools-json /tmp/{schema}-tools.json
```

O estimar manualmente:

- Caracteres y tokens (~1 token ≈ 4 caracteres en español técnico).
- Separar **system** vs **tools** vs **historial** (historial no entra en esta skill salvo mención).

Umbrales orientativos del roadmap Suplai:

| Bloque | Objetivo orientativo |
|--------|----------------------|
| System prompt completo | < 3 000 tokens |
| Suma tool descriptions habilitadas | < 4 000 tokens |
| Duplicación cross-layer del mismo concepto | ≤ 1 vez (regla en un solo lugar) |

### 6. Entregar reporte

Guardar en `implementacion/{schema}/outputs/auditoria_prompt_{YYYYMMDD}.md` (o ruta que indique el usuario).

Usar plantilla de [checklist.md](checklist.md#plantilla-de-reporte).

### 7. Recomendaciones accionables

Por cada hallazgo 🔴/🟠, proponer **un** cambio concreto:

- **Dónde cortar** (quitar de tenant y dejar en base/tools, o viceversa).
- **Qué comprimir** (lista de tools candidatas a acortar — alinear con QW3).
- **Qué activar** (`deterministic_channel` si el tenant repite reglas de “no redactar pedidos”).
- **Qué migrar** (unificar en `system_prompt` si aún hay identidad+contexto duplicados en legacy).

**No aplicar cambios en BD** hasta confirmación explícita del usuario.

---

## Referencias de código

| Qué | Dónde |
|-----|-------|
| Ensamblado runtime | `agent/app/agent/system_prompt_builder.py` |
| Defaults base client/seller | `agent/app/agent/agent_prompt_defaults.py` |
| Flag v2 | `metadata.use_new_system_prompt` |
| Preview API | `backend/routers/system_prompt.py` |
| Tool registry | `agent/app/agent/tools/registry.py` |
| Spec unificado | `backoffice/doc/specs/042-system-prompt-unificado-backoffice.md` |

---

## Ejemplo de invocación

> "Analizá el system prompt de benfresh en modo client y seller, buscá duplicaciones y cosas que inflen la latencia."

El agente debe: preview API → tools habilitadas → checklist → reporte markdown con métricas y prioridades.
