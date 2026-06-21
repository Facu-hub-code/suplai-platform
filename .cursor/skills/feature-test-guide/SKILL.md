---
name: feature-test-guide
description: >-
  Genera una guía de pruebas manuales para una feature nueva: entorno localhost,
  pre-checks, datos requeridos, mapa de pantallas y casos de prueba, más guion
  hablado y audio m4a (macOS). Usar cuando el usuario pida "guía de pruebas",
  "cómo probar la feature", "test plan manual", "QA localhost", "guía de QA en
  audio" o quiera validar un release antes de mergear.
---

# Feature Test Guide — guía de pruebas + audio

Arma un **plan de prueba ejecutable en localhost** a partir de specs, diffs de rama o contexto de la conversación. Entrega:

1. `guide.md` — markdown estructurado (entorno, datos, pantallas, casos CP-XX)
2. `guide-audio.txt` — guion hablado paso a paso (voseo rioplatense, host Facundo)
3. `guide-audio.m4a` — audio para escuchar mientras probás (TTS macOS o neuronal vía spec-podcast)

Reutiliza el pipeline de voz de [spec-podcast](../spec-podcast/SKILL.md).

## Cuándo usar

- "Armame la guía de pruebas de Field V2"
- "Cómo pruebo en localhost lo que acabamos de implementar"
- "Qué datos necesito antes de testear la feature"
- "Guía de QA con audio para la release"

## Flujo del agente

```
1. Identificar feature     → scripts/resolve-feature.sh (o inferir de rama/specs/diff)
2. Leer specs + código     → backend/, backoffice/, field-app/ según aplique
3. Detectar ramas/repos    → git branch en cada repo tocado
4. Escribir guide.md       → templates/guide-template.md
5. Escribir guide-audio.txt (400–700 palabras, walkthrough hablado)
6. Renderizar audio        → scripts/render-guide-audio.sh
7. (Opcional) Reproducir   → scripts/play-guide-audio.sh
```

## 1. Resolver la feature

```bash
.cursor/skills/feature-test-guide/scripts/resolve-feature.sh field-v2
.cursor/skills/feature-test-guide/scripts/resolve-feature.sh "004,005,006,007"
```

**Bundles conocidos:**

| Slug | Specs |
|------|-------|
| `field-v2-productos-vendedores` | 004, 005, 006, 007 |

Si no hay bundle, usar número/slug de spec individual o nombre descriptivo (`slug` = kebab-case).

Salida en:

```
.cursor/skills/feature-test-guide/output/{slug}/
├── guide.md
├── guide-audio.txt
└── guide-audio.m4a
```

## 2. Investigar antes de escribir

**Obligatorio** para cada guía:

| Fuente | Qué extraer |
|--------|-------------|
| Specs `platform/docs/specs/` | Alcance, decisiones, criterios de aceptación |
| Migraciones `backend/sql/` | Números SQL a aplicar (`apply_migration_XX.py`) |
| Ramas git | Nombre exacto por repo |
| `AGENTS.md` / `platform-overview` | Puertos, URLs, multi-tenant |
| Código implementado | Rutas UI reales, endpoints, flags |

**Multi-repo Suplai** — incluir siempre tabla de servicios:

| Servicio | Repo carpeta | Puerto dev |
|----------|--------------|------------|
| Backend | `backend/` | 8000 |
| **Backoffice** | `backoffice/` | **3000** (obligatorio — Google Maps SDK) |
| Field app | `field-app/` | 3001 (si backoffice usa 3000) |
| Tienda | `tienda/` | 3002 |

Regla: `.cursor/rules/backoffice-local-dev-port.mdc`. **No** usar 3001 para backoffice local.

Usar `-p` en `next dev` solo para field-app/tienda si comparten máquina con backoffice. Frontends: `BACKEND_URL=http://localhost:8000`.

**Pre-checks estándar Suplai:**

- Migraciones SQL aplicadas en Supabase (MCP o scripts locales)
- `public.distribuidoras.sales_assistant_enabled = true` (o legacy `metadata.field_app_enabled`)
- Vendedor activo con teléfono conocido para login Field (`?wp=549...`)
- Productos con `tipo_venta` A/B si la feature lo requiere
- Cartera vendedor ↔ clientes asignada

**Datos vía MCP Supabase** (solo lectura salvo flag explícito): consolidar queries en una sola llamada; puerto 6543.

## 3. Estructura de `guide.md`

Seguir [templates/guide-template.md](templates/guide-template.md). Secciones obligatorias:

1. **Resumen** — qué se prueba en una frase
2. **Qué levantar** — comandos copy-paste por terminal
3. **Pre-checks** — checklist + SQL smoke
4. **Datos requeridos** — tabla con "cómo prepararlos"
5. **Mapa de pantallas** — rutas URL + qué mirar (backoffice y/o field-app)
6. **Casos CP-XX** — precondición, pasos numerados, resultado esperado
7. **Criterios de aceptación** — checkboxes finales
8. **Troubleshooting** — síntoma → fix

**Casos de prueba:** mínimo 1 happy path + 1 edge case por área tocada (backoffice, field-app, API).

## 4. Guion de audio (`guide-audio.txt`)

**Host: Facundo.** Tono de "te guío mientras levantás el entorno y clickeás".

**Reglas:**

- Voseo rioplatense; frases cortas; orden **cronológico** (primero terminal, después UI)
- Decir **puertos, URLs y tenant de prueba** en voz alta (ej. "demo", "localhost tres mil")
- No leer SQL ni paths literales — traducir ("activá el flag del asistente de vendedor")
- Estructura:
  1. Intro: qué feature vas a probar
  2. Qué repos y ramas checkoutear
  3. Comandos para levantar (backend → backoffice → field-app)
  4. Pre-checks en BD (flags, migraciones, datos mínimos)
  5. Recorrido pantalla por pantalla (CP principales)
  6. Cierre: checklist final + "si algo falla, mirá la tabla de troubleshooting del markdown"
- 400–700 palabras (~3–5 min)
- Texto plano, sin markdown

## 5. Renderizar y reproducir audio

Cadena TTS (compartida con spec-podcast): **ElevenLabs → OpenAI → macOS**. Configurar `spec-podcast/.env` con ambas API keys; si ElevenLabs se queda sin créditos, cae a OpenAI automáticamente.

```bash
# No usar PODCAST_TTS_BACKEND=macos salvo offline
.cursor/skills/feature-test-guide/scripts/render-guide-audio.sh \
  .cursor/skills/feature-test-guide/output/{slug}/guide-audio.txt

.cursor/skills/feature-test-guide/scripts/play-guide-audio.sh \
  .cursor/skills/feature-test-guide/output/{slug}/guide-audio.m4a
```

## Entrega al usuario

Informar:

- Path de `guide.md` (principal — compartible en PR)
- Path de `guide-audio.m4a` + duración estimada
- Comando para re-escuchar
- Tenant/schema recomendado para la prueba
- Lista corta "empezá por esto" (3 bullets)

## Ejemplo completo

```bash
# Bundle Field V2
.cursor/skills/feature-test-guide/scripts/resolve-feature.sh field-v2

# (agente escribe output/field-v2-productos-vendedores/guide.md y guide-audio.txt)

.cursor/skills/feature-test-guide/scripts/render-guide-audio.sh \
  .cursor/skills/feature-test-guide/output/field-v2-productos-vendedores/guide-audio.txt

.cursor/skills/feature-test-guide/scripts/play-guide-audio.sh \
  .cursor/skills/feature-test-guide/output/field-v2-productos-vendedores/guide-audio.m4a
```

## Limitaciones

- Guía **manual** (no reemplaza E2E automatizado ni skill `agent-e2e-testing`)
- Audio macOS requiere `say` + `afconvert`; calidad neuronal requiere API keys
- Bundles en `resolve-feature.sh` son extensibles — agregar entradas `case` para nuevas releases
