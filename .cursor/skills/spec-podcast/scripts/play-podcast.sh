#!/usr/bin/env bash
# play-podcast.sh — abre un archivo de audio en QuickTime Player (macOS).
set -euo pipefail

PLAYER_APP="${PODCAST_PLAYER_APP:-QuickTime Player}"

AUDIO="${1:-}"
MODE="${2:-}"

if [[ -z "$AUDIO" || ! -f "$AUDIO" ]]; then
  echo "Uso: play-podcast.sh <archivo.m4a|aiff|mp3> [--background]" >&2
  exit 1
fi

AUDIO="$(realpath "$AUDIO")"

if [[ "$MODE" == "--background" ]]; then
  if ! command -v afplay >/dev/null 2>&1; then
    echo "Error: 'afplay' no disponible." >&2
    exit 1
  fi
  echo "Reproduciendo en segundo plano: $AUDIO"
  afplay "$AUDIO" &
  exit 0
fi

echo "Abriendo $PLAYER_APP: $AUDIO"
open -a "$PLAYER_APP" "$AUDIO"
