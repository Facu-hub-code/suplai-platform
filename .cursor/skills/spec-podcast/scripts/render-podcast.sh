#!/usr/bin/env bash
# render-podcast.sh — convierte un guion de texto en podcast.m4a.
#
# Backends de voz (env PODCAST_TTS_BACKEND):
#   auto        (default) → ElevenLabs → OpenAI → macOS (fallback en cadena)
#   elevenlabs  → ElevenLabs; si falla (créditos/red) → OpenAI → macOS
#   openai      → OpenAI; si falla → macOS
#   macos       → TTS nativo (say). Sin red ni credenciales. Voz sintética.
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
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$SKILL_ROOT/.env"
BACKEND_PRESET="${PODCAST_TTS_BACKEND:-}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi
if [[ -n "$BACKEND_PRESET" ]]; then
  PODCAST_TTS_BACKEND="$BACKEND_PRESET"
fi

OUT_DIR="$(dirname "$SCRIPT_TXT")"
AIFF="$OUT_DIR/podcast.aiff"
MP3="$OUT_DIR/podcast.mp3"
M4A="$OUT_DIR/podcast.m4a"

BACKEND="${PODCAST_TTS_BACKEND:-auto}"

MACOS_VOICE="${MACOS_VOICE:-${VOICE:-Reed}}"
RATE="${RATE:-170}"

OPENAI_VOICE="${OPENAI_VOICE:-onyx}"
OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini-tts}"
ELEVEN_VOICE_ID="${PODCAST_VOICE_ID:-${ELEVEN_VOICE_ID:-}}"
ELEVEN_MODEL="${ELEVEN_MODEL:-eleven_multilingual_v2}"

USED_BACKEND=""

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Error: falta '$1'." >&2; exit 1; }
}

has_elevenlabs() {
  [[ -n "${ELEVENLABS_API_KEY:-}" && -n "$ELEVEN_VOICE_ID" ]]
}

has_openai() {
  [[ -n "${OPENAI_API_KEY:-}" ]]
}

to_m4a_from() {
  require_cmd afconvert
  afconvert "$1" "$M4A" -f m4af -d aac -q 127
}

run_neural() {
  local provider="$1"
  require_cmd python3
  python3 "$SCRIPT_DIR/tts_neural.py" \
    --provider "$provider" \
    --text-file "$SCRIPT_TXT" \
    --out "$MP3" \
    --openai-voice "$OPENAI_VOICE" \
    --openai-model "$OPENAI_MODEL" \
    --eleven-voice-id "$ELEVEN_VOICE_ID" \
    --eleven-model "$ELEVEN_MODEL"
}

run_macos() {
  require_cmd say
  echo "Generando con macOS say (voz=$MACOS_VOICE rate=$RATE) ..."
  say -v "$MACOS_VOICE" -r "$RATE" -o "$AIFF" -f "$SCRIPT_TXT"
  to_m4a_from "$AIFF"
  USED_BACKEND="macos"
}

try_elevenlabs() {
  if ! has_elevenlabs; then
    return 1
  fi
  echo "Intentando ElevenLabs (voz neuronal) ..."
  if run_neural elevenlabs; then
    to_m4a_from "$MP3"
    USED_BACKEND="elevenlabs"
    return 0
  fi
  echo "⚠ ElevenLabs falló (créditos, auth o red). Probando siguiente proveedor ..." >&2
  return 1
}

try_openai() {
  if ! has_openai; then
    echo "ℹ OpenAI omitido: agregá OPENAI_API_KEY en spec-podcast/.env para fallback neuronal." >&2
    return 1
  fi
  echo "Intentando OpenAI TTS (voz=$OPENAI_VOICE) ..."
  if run_neural openai; then
    to_m4a_from "$MP3"
    USED_BACKEND="openai"
    return 0
  fi
  echo "⚠ OpenAI TTS falló. Probando macOS say ..." >&2
  return 1
}

run_chain_from_elevenlabs() {
  try_elevenlabs || try_openai || run_macos
}

run_chain_from_openai() {
  try_openai || run_macos
}

case "$BACKEND" in
  auto)
    echo "Modo auto: ElevenLabs → OpenAI → macOS"
    run_chain_from_elevenlabs
    ;;
  elevenlabs)
    run_chain_from_elevenlabs
    ;;
  openai)
    run_chain_from_openai
    ;;
  macos)
    run_macos
    ;;
  *)
    echo "Error: backend desconocido '$BACKEND' (usa auto|macos|openai|elevenlabs)." >&2
    exit 1
    ;;
esac

DURATION=""
if command -v afinfo >/dev/null 2>&1; then
  DURATION="$(afinfo "$M4A" 2>/dev/null | awk -F': ' '/estimated duration/ {printf "%.0f", $2; exit}')"
fi
SIZE="$(du -h "$M4A" | cut -f1)"
echo "Backend usado: ${USED_BACKEND:-desconocido}"
echo "OK: $M4A ($SIZE${DURATION:+, ~${DURATION}s})"
