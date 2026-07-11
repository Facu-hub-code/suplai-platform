---
name: spec-podcast
description: >-
  Convierte un spec markdown en un resumen hablado estilo podcast (guion +
  audio m4a). Usar cuando el usuario pida "leeme el spec", "podcast del spec",
  "resumen en audio", "spec cast" o quiera escuchar una spec/skill sin leerla.
---

# Spec Podcast — resumen en audio

Genera un episodio (~4–6 min) a partir de un spec `.md`: guion hablado en español rioplatense + audio `.m4a`. La voz es de **Facundo** (masculina, joven, argentina), pero el episodio **presenta al spec**, no al host.

**Backends de voz (cadena de fallback en `auto`):**

| Orden | Backend | Requiere | Notas |
|-------|---------|----------|-------|
| 1 | `elevenlabs` | `ELEVENLABS_API_KEY` + `PODCAST_VOICE_ID` | Preferido — voz natural |
| 2 | `openai` | `OPENAI_API_KEY` | Fallback si ElevenLabs sin créditos / error |
| 3 | `macos` | `say`, `afconvert` | Último recurso — voz sintética |

`PODCAST_TTS_BACKEND=auto` (default) recorre la cadena **ElevenLabs → OpenAI → macOS** hasta que uno funcione.

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

**Voz = Facundo** (rioplatense, cercano). **Protagonista = el spec**, no la presentación personal del host.

**Reglas del guion:**

- **Voseo** rioplatense: *tenés, mirá, fijate, dale, acordate*. Nada de tuteo.
- Frases **cortas**, una idea por vez. Muletillas naturales y moderadas (*mirá, ojo, te tiro el dato*).
- **No leer** tablas, SQL, paths ni checkboxes literalmente — traducir a lenguaje hablado, con metáforas cotidianas, sin perder precisión técnica.
- Marcar **pausas** con puntuación y guiones largos para que respire.
- Ser **detallista** en decisiones de diseño técnico y el *por qué*; no quedarse en el "qué".
- Estructura fija:
  1. **Intro (presenta al spec, no al host):** "¡Buenas! Esto es Suplai Spec Cast. Hoy te resumo la spec {número}: {título}. Dale que arrancamos." — **MUST NOT** usar "Soy Facundo…" ni presentarse a sí mismo.
  2. **Problema / contexto** — por qué existe esta spec.
  3. **Alcance** — qué entra en v1 y qué queda afuera (explícito).
  4. **Decisiones de diseño técnico** — cada decisión clave con el *por qué* se tomó (trade-offs, alternativas descartadas). Priorizar este bloque; no recortar por tiempo.
  5. **Modelo / migración de BD** — si hay tablas nuevas, columnas, seed SQL o backfill: qué cambia y en qué orden se aplica.
  6. **Orden de implementación** — repos/PRs, dependencias (ej. agente → backend → backoffice).
  7. **Cómo se prueba en CI/CD** — tests unitarios, e2e, checks de PR, migraciones en pipeline. Si el spec no lo documenta, decirlo y marcar el hueco.
  8. **Cómo se prueba humanamente antes del PR** — checklist manual local (puertos, tenants, pasos clickeables). Si el spec no lo documenta, decirlo y marcar el hueco.
  9. **Cierre:** criterios de aceptación en una frase + outro: "Eso es todo por la spec {número}. Nos vemos en la próxima." — **MUST NOT** cerrar con "Soy Facundo…".
- Longitud objetivo: **700–1000 palabras** (~4–6 min). Preferir detalle técnico a brevedad.
- Solo texto plano, una línea por párrafo. Sin markdown, emojis ni URLs.

> Character brief y ejemplos: [docs/specs/008-spec-podcast-voz-humana-anexo-facundo.md](../../../docs/specs/008-spec-podcast-voz-humana-anexo-facundo.md).
> Secciones obligatorias al redactar specs: regla `.cursor/rules/spec-draft-required-sections.mdc`.

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
| `PODCAST_TTS_BACKEND` | `auto` | `auto` \| `elevenlabs` \| `openai` \| `macos` — en `auto`/`elevenlabs`/`openai` hay fallback en cadena |
| `ELEVENLABS_API_KEY` | — | primer intento en `auto` |
| `PODCAST_VOICE_ID` | — | voice id ElevenLabs |
| `OPENAI_API_KEY` | — | fallback si ElevenLabs falla |
| `OPENAI_VOICE` | `onyx` | voz OpenAI |
| `MACOS_VOICE` | `Reed` | último fallback local |
| `RATE` | `170` | palabras/min (solo `macos`) |

**No** forzar `PODCAST_TTS_BACKEND=macos` salvo prueba offline. Configurar `.env` con ElevenLabs + OpenAI como respaldo.

Para voz **neuronal** (ElevenLabs u OpenAI), copiar `.env.example` → `.env` en la carpeta de la skill y completar credenciales. `render-podcast.sh` carga `.env` automáticamente.

```bash
cp .cursor/skills/spec-podcast/.env.example .cursor/skills/spec-podcast/.env
# editar .env con ELEVENLABS_API_KEY y PODCAST_VOICE_ID
```

Salida: `output/{slug}/podcast.m4a` (+ intermedio `podcast.aiff` o `podcast.mp3`).

## 4. Reproducir

```bash
.cursor/skills/spec-podcast/scripts/play-podcast.sh \
  .cursor/skills/spec-podcast/output/{slug}/podcast.m4a
```

Abre **QuickTime Player** (`open -a "QuickTime Player"`). Pasar `--background` para `afplay` sin ventana. Otro reproductor: `PODCAST_PLAYER_APP="Music" play-podcast.sh ...`.

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
- Specs muy largas (>300 líneas): priorizar decisiones técnicas + por qué, alcance, migración, orden de implementación y planes de prueba; omitir listings SQL/JSON literales.
