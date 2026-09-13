---
name: novedades-from-chat
description: Use when drafting a landing novedad from a real customer chat dump, WhatsApp export, or call notes about a distributor symptom such as cobertura, frecuencia, mix, rotación de vendedores, cumplimiento de objetivos, or atención.
---

# Novedades from chat

Turn a trusted customer's chat into a **draft** novedad for `suplai-sales-landing`. The chat is the language source. The published page is a symptom, not a feature announcement.

**Repo / path:** `/Users/facundolorenzo/Documents/SuplaiSales/source/suplai-sales-landing`  
**Write to:** `content/novedades/{slug}.md` with `draft: true`  
**Template:** `content/novedades/_template.md`  
**Do not publish** (`draft: false`) unless video, poster and real transcript are already in the repo.

## Output (this order)

1. **Síntoma** — one sentence, in the customer's words.
2. **Banco de lenguaje** — 5–12 verbatim phrases (anonymized). No paraphrases here.
3. **Categoría** — exactly one of: `cobertura` | `frecuencia` | `cumplimiento-objetivos` | `mix-productos` | `rotacion-vendedores` | `atencion-servicio`.
4. **Gaps** — what is missing (video, duration, transcript, FAQ). Never fill a gap with fiction.
5. **Borrador markdown** — a complete file matching the template. Stop after writing the file.

## Draft contract

```yaml
slug: kebab-case-sin-fecha-ni-id
title: Pregunta o síntoma real (H1)
summary: 1–2 líneas para el listado
category: cobertura
publishedAt: YYYY-MM-DD
draft: true
video:            # omitir el bloque entero si no hay assets
  src: /novedades/{slug}/video.mp4
  poster: /novedades/{slug}/poster.jpg
  posterAlt: descripción del poster
  # duration: PT3M20S  solo si está medida
faqs:             # 2 a 4, sacadas de objeciones o dudas del chat
  - question: ...
    answer: ...
```

Body: only `##` / `###`. One H2 per subtopic the customer actually named. If there is no video transcript, write a short **guion-borrador** labeled as such, or leave placeholders — never a fake transcript.

## Rules

- Anonymize tenant, people, cities that identify the account, and internal SKUs.
- Keep rioplatense voseo if the chat uses it.
- The H1 is the symptom ("Cómo aumento cobertura sin sumar vendedores"), not "Lanzamos Field 2.0".
- If the chat is not about a distributor commercial symptom, stop and say so. Do not force a novedad.

| Excuse | Reality |
|--------|---------|
| "Le pongo una métrica de ejemplo" | Sin número en el chat o en el brief, no va. |
| "El video todavía no está, invento la transcripción" | `draft: true` y gap explícito. |
| "Queda más claro si hablo del feature" | El feature entra solo como respuesta al síntoma. |
| "duration se puede estimar" | Se omite. |

## Red flags

- Changelog, versión, "ahora podés".
- Métricas, duration o nombres de cliente inventados.
- H1 de marketing ("La plataforma que revoluciona…").
- `draft: false` sin video + poster + transcripción real.
