#!/usr/bin/env python3
"""Genera audio MP3 con un proveedor de TTS neuronal (OpenAI o ElevenLabs).

Sin dependencias externas: usa urllib (stdlib). Las credenciales se leen de
variables de entorno; nunca se reciben por argumento ni se loguean.

Env requeridas:
  - openai:     OPENAI_API_KEY
  - elevenlabs: ELEVENLABS_API_KEY  (+ --eleven-voice-id)
"""
import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

OPENAI_URL = "https://api.openai.com/v1/audio/speech"
ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

# Tono/acento del host "Facundo" (solo lo aplican modelos que aceptan instrucciones).
FACUNDO_INSTRUCTIONS = (
    "Hablá en español rioplatense (argentino), con tono masculino, joven y "
    "cercano, como un host de podcast que explica con claridad y buena onda. "
    "Ritmo ágil pero con pausas naturales para respirar."
)


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # noqa: PLC0415 — opcional; común en macOS Python
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read().strip()
    if not text:
        sys.exit("Error: el guion está vacío.")
    return text


def _post(url: str, headers: dict, payload: dict, out_path: str, provider: str) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120, context=_ssl_context()) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        if exc.code in (402, 429) or "quota_exceeded" in detail or "quota" in detail.lower():
            hint = " (créditos agotados o insuficientes para este texto)"
        elif exc.code in (401, 403):
            hint = " (¿API key inválida o sin permiso?)"
        else:
            hint = ""
        print(f"[{provider}] HTTP {exc.code}{hint}: {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"[{provider}] Error de red: {exc.reason}", file=sys.stderr)
        sys.exit(1)
    if len(audio) < 256:
        print(f"[{provider}] Respuesta demasiado corta; posible error del proveedor.", file=sys.stderr)
        sys.exit(1)
    with open(out_path, "wb") as fh:
        fh.write(audio)


def gen_openai(text: str, out_path: str, voice: str, model: str) -> None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("Error: OPENAI_API_KEY no seteada.")
    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": "mp3",
    }
    # gpt-4o-mini-tts acepta 'instructions' para guiar tono/acento.
    if "gpt-4o" in model:
        payload["instructions"] = FACUNDO_INSTRUCTIONS
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    _post(OPENAI_URL, headers, payload, out_path, "openai")


def gen_elevenlabs(text: str, out_path: str, voice_id: str, model: str) -> None:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("Error: ELEVENLABS_API_KEY no seteada.")
    if not voice_id:
        sys.exit("Error: falta voice_id (PODCAST_VOICE_ID) para ElevenLabs.")
    url = ELEVEN_URL.format(voice_id=voice_id)
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.3},
    }
    headers = {
        "xi-api-key": key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    _post(url, headers, payload, out_path, "elevenlabs")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=["openai", "elevenlabs"])
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--openai-voice", default="onyx")
    ap.add_argument("--openai-model", default="gpt-4o-mini-tts")
    ap.add_argument("--eleven-voice-id", default="")
    ap.add_argument("--eleven-model", default="eleven_multilingual_v2")
    args = ap.parse_args()

    text = _read_text(args.text_file)

    if args.provider == "openai":
        gen_openai(text, args.out, args.openai_voice, args.openai_model)
    else:
        gen_elevenlabs(text, args.out, args.eleven_voice_id, args.eleven_model)

    print(f"Audio generado: {args.out}")


if __name__ == "__main__":
    main()
