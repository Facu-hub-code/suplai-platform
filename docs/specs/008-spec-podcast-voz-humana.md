# Spec Podcast — voz humana "Facundo"

**Estado:** Diseño (propuesta)
**Fecha:** 2026-06-20
**Skill afectada:** `.cursor/skills/spec-podcast/`
**Anexo:** [008-spec-podcast-voz-humana-anexo-facundo.md](./008-spec-podcast-voz-humana-anexo-facundo.md)
**Alcance de esta entrega:** **solo documentación** (archivos `.md`). No incluye cambios de código ni de scripts.

---

## 1) Contexto

La skill `spec-podcast` ya convierte un spec markdown en audio usando el TTS nativo de macOS (`say` + voz `Paulina`/`Mónica`). Funciona, pero el resultado **suena robótico**: prosodia plana, sin respiración, sin muletillas ni ritmo conversacional, y con acento neutro/mexicano-españolizado que no representa la identidad deseada.

Queremos que el podcast tenga un **host con identidad propia**, voz **humana, argentina (rioplatense), masculina y joven**, idealmente **la voz del propio usuario** (clonada). El host se llama **Facundo**.

> Esta spec define el **diseño objetivo** y las decisiones. La implementación del pipeline de voz neuronal/clonada se hará en una entrega posterior (código + scripts), no acá.

---

## 2) Objetivos

| # | Objetivo |
|---|----------|
| 1 | Reemplazar el TTS robótico de macOS por una voz **neuronal natural**. |
| 2 | Dar identidad al host: **Facundo**, persona definida (ver anexo). |
| 3 | Voz **argentina rioplatense, masculina, joven** (~25–35), tono cercano/conversacional. |
| 4 | Soportar **clonación de la voz del usuario** ("mi voz") como meta final. |
| 5 | Humanizar el **guion** (no solo la voz): ritmo, pausas, muletillas, lenguaje rioplatense. |
| 6 | Mantener el flujo y la salida existentes (resolver spec → guion → audio `.m4a` → reproducir). |

---

## 3) Decisiones de diseño

| # | Tema | Decisión |
|---|------|----------|
| 1 | Nombre del host | **Facundo** (fijo). |
| 2 | Perfil de voz | Masculino, argentino rioplatense, joven, registro informal-profesional. |
| 3 | Meta de voz | **Clonar la voz del usuario** (Facundo real). Hasta tener el clon, usar una voz argentina masculina pre-hecha como fallback. |
| 4 | Proveedor recomendado | **ElevenLabs** (clonación + multilingüe natural). Fallback sin clonación: **Azure `es-AR-TomasNeural`**. |
| 5 | Formato de salida | Se mantiene `.m4a` (y guion `.txt`). |
| 6 | Humanización | Combinar **voz neuronal** + **guion humanizado** + **marcas de prosodia** (pausas/énfasis). |
| 7 | Identidad sonora | Intro/outro con frase fija de Facundo (ver anexo); sin música obligatoria en V1. |
| 8 | Secretos | API key del proveedor vía **variable de entorno**, nunca hardcodeada ni commiteada. |

---

## 4) Estrategia de voz (dos niveles)

### Nivel 1 — Voz argentina neuronal (sin clonar) · mejora inmediata

Voz pre-hecha masculina rioplatense. Quita lo robótico sin necesitar muestras del usuario.

| Proveedor | Voz / modelo | Notas |
|-----------|--------------|-------|
| **Azure Speech** | `es-AR-TomasNeural` | Nativo argentino, masculino. Soporta SSML (pausas, énfasis, estilo). |
| **OpenAI TTS** | voces `onyx` / `ash` | Muy natural; acento no garantizado argentino. |
| **ElevenLabs** | voz pre-hecha ES masculina | Natural; acento configurable por prompt/sample. |

### Nivel 2 — Clonación de la voz del usuario ("mi voz") · meta final

| Proveedor | Capacidad | Requisito |
|-----------|-----------|-----------|
| **ElevenLabs** | Instant / Professional Voice Cloning | Muestras de audio del usuario (limpias, ~1–30 min según calidad). |

**Decisión:** arrancar en **Nivel 1** (rápido, sin dependencias del usuario) y migrar a **Nivel 2** cuando el usuario provea muestras y se configure el clon.

> Comparativa ampliada de proveedores y trade-offs: ver anexo §3.

---

## 5) Humanización del guion

La voz natural no alcanza si el guion está escrito como documento técnico. El guion de Facundo debe:

- Hablar en **rioplatense**: voseo (*tenés, mirá, fijate, dale*), conectores orales (*así que, posta, la idea es*).
- Frases **cortas**, una idea por frase; evitar subordinadas largas.
- **Muletillas** moderadas y naturales (*bueno, mirá, ojo con esto, te tiro el dato*).
- **Pausas** marcadas para respiración y énfasis (puntuación + SSML `<break>`).
- Arranque y cierre con **identidad de Facundo** (ver anexo §2).
- Cero lectura literal de tablas, SQL, paths o checkboxes (regla ya existente en la skill).

> Ejemplo "antes robótico → después humano" en el anexo §4.

---

## 6) Cambios previstos en la skill (para implementación futura)

> No se implementan en esta entrega; se documentan para el PR de código siguiente.

| Área | Cambio previsto |
|------|-----------------|
| `SKILL.md` | Sección de identidad "Facundo" + reglas de guion humanizado. |
| `scripts/render-podcast.sh` | Backend de voz seleccionable: `macos` (actual) \| `elevenlabs` \| `azure`. |
| Config | Variables de entorno: proveedor, API key, voice id, modelo. |
| Guion | Plantilla con intro/outro de Facundo y marcas de prosodia. |
| Salida | Igual (`output/{slug}/podcast.m4a` + `podcast.txt`). |

### Variables de entorno previstas (no usar valores reales en docs)

| Variable | Propósito | Ejemplo |
|----------|-----------|---------|
| `PODCAST_TTS_BACKEND` | `macos` \| `elevenlabs` \| `azure` | `elevenlabs` |
| `ELEVENLABS_API_KEY` | Auth proveedor | *(secreto)* |
| `PODCAST_VOICE_ID` | Voz/clon a usar | `facundo-clone-v1` |

---

## 7) Requisitos para Nivel 2 (clon)

1. Muestras de audio del usuario: voz clara, mono, sin ruido, ~1–30 min (según calidad instant vs professional).
2. Cuenta + API key del proveedor (ElevenLabs).
3. Consentimiento explícito de uso de la voz (es la voz del propio usuario).
4. `voice_id` del clon configurado en la skill.

---

## 8) Alcance

| En esta entrega (V0 · docs) | Implementación posterior | Fuera de alcance |
|-----------------------------|--------------------------|------------------|
| Spec + anexo (`.md`) | Backend de voz neuronal en la skill | Música/jingle producido |
| Diseño de identidad "Facundo" | Clonación de voz del usuario | Multi-host / diálogo a dos voces |
| Estrategia de proveedores | Plantilla de guion humanizado | Publicación en plataformas (Spotify, etc.) |

---

## 9) Criterios de aceptación (de esta entrega documental)

- [ ] Existe la spec `008-spec-podcast-voz-humana.md` con objetivos, decisiones y estrategia de voz.
- [ ] Existe el anexo con el **character brief de Facundo** y un ejemplo de guion humanizado.
- [ ] Los archivos están en una **rama aparte** (`docs/spec-podcast-voz-humana`), sin mezclar con el trabajo de field V2.
- [ ] La entrega es **solo `.md`**: no modifica scripts ni código de la skill.
- [ ] Quedan documentados proveedores, niveles de voz, variables de entorno y requisitos del clon.

---

## 10) Roadmap

1. **V0 (esta spec):** diseño aprobado en docs.
2. **V1:** implementar Nivel 1 (voz argentina neuronal) en `render-podcast.sh` + guion humanizado.
3. **V2:** clonar la voz del usuario (ElevenLabs) y setear `PODCAST_VOICE_ID=facundo-clone`.
4. **V3 (opcional):** jingle de intro/outro y ajustes finos de prosodia.
