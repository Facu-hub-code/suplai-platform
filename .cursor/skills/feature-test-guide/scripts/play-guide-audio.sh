#!/usr/bin/env bash
# play-guide-audio.sh — reproduce la guía de pruebas en audio (QuickTime / afplay).
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PODCAST_PLAY="$(cd "$SCRIPT_DIR/../../spec-podcast/scripts" && pwd)/play-podcast.sh"

exec "$PODCAST_PLAY" "$@"
