#!/usr/bin/env bash
# render-guide-audio.sh — TTS del guion de guía de pruebas (reusa spec-podcast).
set -eo pipefail

SCRIPT_TXT="${1:-}"
if [[ -z "$SCRIPT_TXT" || ! -f "$SCRIPT_TXT" ]]; then
  echo "Uso: render-guide-audio.sh <guide-audio.txt>" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PODCAST_RENDER="$(cd "$SCRIPT_DIR/../../spec-podcast/scripts" && pwd)/render-podcast.sh"

if [[ ! -x "$PODCAST_RENDER" ]]; then
  echo "Error: no existe render-podcast.sh en spec-podcast." >&2
  exit 1
fi

# Preservar backend explícito aunque spec-podcast/.env lo sobreescriba al sourcear
BACKEND_OVERRIDE="${PODCAST_TTS_BACKEND:-}"

OUT_DIR="$(dirname "$SCRIPT_TXT")"
M4A="$OUT_DIR/guide-audio.m4a"

if [[ -n "$BACKEND_OVERRIDE" ]]; then
  PODCAST_TTS_BACKEND="$BACKEND_OVERRIDE" "$PODCAST_RENDER" "$SCRIPT_TXT"
else
  "$PODCAST_RENDER" "$SCRIPT_TXT"
fi

# Normalizar nombre de salida podcast.m4a → guide-audio.m4a
if [[ -f "$OUT_DIR/podcast.m4a" && "$OUT_DIR/podcast.m4a" != "$M4A" ]]; then
  mv -f "$OUT_DIR/podcast.m4a" "$M4A"
fi

echo "Guía en audio: $M4A"
