#!/usr/bin/env bash
# render-podcast.sh — convierte un guion de texto en podcast.m4a.
#
# Backends de voz (env PODCAST_TTS_BACKEND):
#   auto        (default) → elevenlabs si hay key; si no openai; si no macos
#   macos       → TTS nativo (say). Sin red ni credenciales. Voz sintética.
#   openai      → OpenAI TTS (voz neuronal natural). Requiere OPENAI_API_KEY.
#   elevenlabs  → ElevenLabs (neuronal/clonable). Requiere ELEVENLABS_API_KEY.
#
# Voz "Facundo" (host): masculina, joven. Acento argentino real solo con
# backend neuronal; en macos se aproxima con voz masculina + guion humanizado.
set -eo pipefail

SCRIPT_TXT="${1:-}"
if [[ -z "$SCRIPT_TXT" || ! -f "$SCRIPT_TXT" ]]; then
  echo "Uso: render-podcast.sh <podcast.txt>" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$(dirname "$SCRIPT_TXT")"
AIFF="$OUT_DIR/podcast.aiff"
MP3="$OUT_DIR/podcast.mp3"
M4A="$OUT_DIR/podcast.m4a"

BACKEND="${PODCAST_TTS_BACKEND:-auto}"

# macOS: voz masculina por defecto (Facundo). Configurable con MACOS_VOICE.
MACOS_VOICE="${MACOS_VOICE:-${VOICE:-Reed}}"
RATE="${RATE:-170}"

# Neuronal
OPENAI_VOICE="${OPENAI_VOICE:-onyx}"          # masculina grave/natural
OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini-tts}"
ELEVEN_VOICE_ID="${PODCAST_VOICE_ID:-${ELEVEN_VOICE_ID:-}}"
ELEVEN_MODEL="${ELEVEN_MODEL:-eleven_multilingual_v2}"

resolve_backend() {
  if [[ "$BACKEND" != "auto" ]]; then echo "$BACKEND"; return; fi
  if [[ -n "${ELEVENLABS_API_KEY:-}" && -n "$ELEVEN_VOICE_ID" ]]; then echo "elevenlabs"; return; fi
  if [[ -n "${OPENAI_API_KEY:-}" ]]; then echo "openai"; return; fi
  echo "macos"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Error: falta '$1'." >&2; exit 1; }
}

to_m4a_from() {
  # $1 = archivo fuente (aiff/mp3) → M4A
  require_cmd afconvert
  afconvert "$1" "$M4A" -f m4af -d aac -q 127
}

EFFECTIVE="$(resolve_backend)"
echo "Backend de voz: $EFFECTIVE"

case "$EFFECTIVE" in
  macos)
    require_cmd say
    echo "Generando con macOS say (voz=$MACOS_VOICE rate=$RATE) ..."
    say -v "$MACOS_VOICE" -r "$RATE" -o "$AIFF" -f "$SCRIPT_TXT"
    to_m4a_from "$AIFF"
    ;;
  openai|elevenlabs)
    require_cmd python3
    echo "Generando con $EFFECTIVE (voz neuronal) ..."
    python3 "$SCRIPT_DIR/tts_neural.py" \
      --provider "$EFFECTIVE" \
      --text-file "$SCRIPT_TXT" \
      --out "$MP3" \
      --openai-voice "$OPENAI_VOICE" \
      --openai-model "$OPENAI_MODEL" \
      --eleven-voice-id "$ELEVEN_VOICE_ID" \
      --eleven-model "$ELEVEN_MODEL"
    to_m4a_from "$MP3"
    ;;
  *)
    echo "Error: backend desconocido '$EFFECTIVE' (usa macos|openai|elevenlabs|auto)." >&2
    exit 1
    ;;
esac

DURATION=""
if command -v afinfo >/dev/null 2>&1; then
  DURATION="$(afinfo "$M4A" 2>/dev/null | awk -F': ' '/estimated duration/ {printf "%.0f", $2; exit}')"
fi
SIZE="$(du -h "$M4A" | cut -f1)"
echo "OK: $M4A ($SIZE${DURATION:+, ~${DURATION}s})"
