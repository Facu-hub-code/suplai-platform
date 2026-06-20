---
name: spec-podcast
description: >-
  Convierte un spec markdown en un resumen hablado estilo podcast (guion +
  audio m4a). Usar cuando el usuario pida "leeme el spec", "podcast del spec",
  "resumen en audio", "spec cast" o quiera escuchar una spec/skill sin leerla.
---

# Spec Podcast — resumen en audio

Genera un episodio corto (~2–4 min) a partir de un spec `.md`: guion hablado en español rioplatense + audio `.m4a`. El host es **Facundo** (voz masculina, joven, argentina).

**Backends de voz:**

| Backend | Calidad | Requiere | Acento argentino |
|---------|---------|----------|------------------|
| `macos` | Sintética | nada (`say`, `afconvert`) | aproximado (voz masculina + guion) |
| `openai` | Neuronal natural | `OPENAI_API_KEY` | guiado por instrucciones |
| `elevenlabs` | Neuronal / clonable | `ELEVENLABS_API_KEY` + `PODCAST_VOICE_ID` | configurable por voz |

Por defecto (`auto`) usa el neuronal si hay credenciales; si no, cae a `macos`. Diseño completo: [docs/specs/008-spec-podcast-voz-humana.md](../../../docs/specs/008-spec-podcast-voz-humana.md).

## Cuándo usar

- "Leeme el spec 004"
- "Podcast del spec de clasificación de productos"
- "Resumen en audio de la spec que tengo abierta"
- Cualquier spec en `platform/docs/specs/`, `backend/docs/specs/`, etc.

## Flujo

```
1. Resolver path del spec     → scripts/resolve-spec.sh
2. Leer el markdown completo
3. Escribir guion podcast     → output/{slug}/podcast.txt
4. Renderizar audio           → scripts/render-podcast.sh
5. Abrir reproductor          → scripts/play-podcast.sh
```

## 1. Resolver el spec

Desde la raíz de `platform/`:

```bash
.cursor/skills/spec-podcast/scripts/resolve-spec.sh "004"
.cursor/skills/spec-podcast/scripts/resolve-spec.sh "clasificacion-productos"
.cursor/skills/spec-podcast/scripts/resolve-spec.sh "backend/docs/specs/050-admin-permisos-roles-areas.md"
```

Si hay varios matches, listarlos y pedir confirmación. Para consultas **solo numéricas** (`004`), el script prioriza `platform/docs/specs/`.

## 2. Escribir el guion (`podcast.txt`)

**El host es Facundo.** Hablá como él: rioplatense, cercano, una sola voz.

**Reglas del guion:**

- **Voseo** rioplatense: *tenés, mirá, fijate, dale, acordate*. Nada de tuteo.
- Frases **cortas**, una idea por vez. Muletillas naturales y moderadas (*mirá, ojo, te tiro el dato*).
- **No leer** tablas, SQL, paths ni checkboxes literalmente — traducir a lenguaje hablado, con metáforas cotidianas, sin perder precisión.
- Marcar **pausas** con puntuación y guiones largos para que respire.
- Estructura fija:
  1. Intro de Facundo: "¡Buenas! Soy Facundo y esto es Suplai Spec Cast. Hoy te resumo, en pocos minutos, la spec {número}: {título}. Dale que arrancamos."
  2. Contexto / problema
  3. Decisiones clave (máx. 5)
  4. Modelo técnico resumido (si aplica)
  5. Consumidores / impacto downstream
  6. Alcance / migración
  7. Cierre: criterios de aceptación en una frase + outro de Facundo: "…Soy Facundo, nos vemos en la próxima. ¡Chau!"
- Longitud objetivo: **400–600 palabras** (~2.5–4 min).
- Solo texto plano, una línea por párrafo. Sin markdown, emojis ni URLs.

> Character brief completo y ejemplos antes/después: [docs/specs/008-spec-podcast-voz-humana-anexo-facundo.md](../../../docs/specs/008-spec-podcast-voz-humana-anexo-facundo.md).

Guardar en:

```
.cursor/skills/spec-podcast/output/{slug}/podcast.txt
```

`{slug}` = basename del spec sin extensión (ej. `004-clasificacion-productos-comerciales`).

## 3. Renderizar audio

```bash
.cursor/skills/spec-podcast/scripts/render-podcast.sh \
  .cursor/skills/spec-podcast/output/{slug}/podcast.txt
```

Opciones (env vars):

| Variable | Default | Notas |
|----------|---------|-------|
| `PODCAST_TTS_BACKEND` | `auto` | `auto` \| `macos` \| `openai` \| `elevenlabs` |
| `OPENAI_API_KEY` | — | habilita backend `openai` (voz `onyx` por defecto) |
| `OPENAI_VOICE` | `onyx` | voz OpenAI (`onyx`, `ash`, etc.) |
| `ELEVENLABS_API_KEY` | — | habilita backend `elevenlabs` |
| `PODCAST_VOICE_ID` | — | voice id de ElevenLabs (clon o pre-hecha) |
| `MACOS_VOICE` | `Reed` | voz masculina del fallback `say` |
| `RATE` | `170` | palabras/min (solo `macos`) |

Para voz **neuronal humana** basta exportar una key, por ejemplo:

```bash
export OPENAI_API_KEY=sk-...   # luego render usa backend openai automáticamente
```

Salida: `output/{slug}/podcast.m4a` (+ intermedio `podcast.aiff` o `podcast.mp3`).

## 4. Reproducir

```bash
.cursor/skills/spec-podcast/scripts/play-podcast.sh \
  .cursor/skills/spec-podcast/output/{slug}/podcast.m4a
```

Abre el reproductor por defecto de macOS (`open`). Pasar `--background` para `afplay` sin ventana.

## Entrega al usuario

Informar:

- Path del audio `.m4a`
- Path del guion `.txt`
- Duración estimada (de la salida de `render-podcast.sh`)
- Comando para volver a reproducir

## Ejemplo completo

```bash
# Resolver
SPEC=$(.cursor/skills/spec-podcast/scripts/resolve-spec.sh "004")

# (agente escribe guion en output/004-clasificacion-productos-comerciales/podcast.txt)

# Render + play
.cursor/skills/spec-podcast/scripts/render-podcast.sh \
  .cursor/skills/spec-podcast/output/004-clasificacion-productos-comerciales/podcast.txt

.cursor/skills/spec-podcast/scripts/play-podcast.sh \
  .cursor/skills/spec-podcast/output/004-clasificacion-productos-comerciales/podcast.m4a
```

## Limitaciones

- El empaquetado a `.m4a` usa `afconvert` (macOS). El backend `macos` además requiere `say`.
- Sin API key, la voz es **sintética** (no suena humana ni argentina nativa). Para voz neuronal real, setear `OPENAI_API_KEY` o `ELEVENLABS_API_KEY`.
- Backends neuronales requieren **red** y consumen créditos del proveedor.
- Specs muy largas (>300 líneas): priorizar decisiones y alcance; omitir detalle de implementación fino.
