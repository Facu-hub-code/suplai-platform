#!/usr/bin/env python3
"""
Métricas rápidas de tamaño de contexto para auditoría de prompt.

Uso:
  python measure_context.py --system-prompt-file full.txt
  python measure_context.py --system-prompt-file full.txt --tools-json tools.json
  python measure_context.py --text "contenido inline"

tools.json formato:
  {"search_products": "desc...", "create_order": "desc..."}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def estimate_tokens(text: str) -> int:
    """Heurística: ~4 chars por token en español técnico."""
    n = len(text or "")
    return max(1, n // 4) if n else 0


def normalize_line(line: str) -> str:
    s = line.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[`'\"*#]", "", s)
    return s


def find_duplicate_lines(text: str, *, min_len: int = 40) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for raw in text.splitlines():
        norm = normalize_line(raw)
        if len(norm) < min_len:
            continue
        counts[norm] = counts.get(norm, 0) + 1
    dups = [(line, n) for line, n in counts.items() if n > 1]
    dups.sort(key=lambda x: (-x[1], x[0]))
    return dups[:20]


def keyword_hits(text: str, keywords: list[str]) -> dict[str, int]:
    lower = text.lower()
    return {k: lower.count(k.lower()) for k in keywords}


def main() -> int:
    parser = argparse.ArgumentParser(description="Medir tamaño de system prompt y tools")
    parser.add_argument("--system-prompt-file", type=Path, help="Archivo con prompt completo")
    parser.add_argument("--tools-json", type=Path, help="JSON nombre_tool -> descripción")
    parser.add_argument("--text", help="Texto inline en lugar de archivo")
    args = parser.parse_args()

    if args.text:
        system_text = args.text
    elif args.system_prompt_file:
        system_text = args.system_prompt_file.read_text(encoding="utf-8")
    else:
        parser.error("Indicá --system-prompt-file o --text")
        return 2

    tools: dict[str, str] = {}
    if args.tools_json:
        raw = json.loads(args.tools_json.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            tools = {k: str(v) for k, v in raw.items()}

    tools_blob = "\n\n".join(f"## {name}\n{desc}" for name, desc in sorted(tools.items()))
    combined = system_text + "\n\n" + tools_blob

    keywords = [
        "product_code",
        "confirm_order",
        "create_order",
        "resolve_free_text_order",
        "list_seller_clients",
        "search_products",
        "unit",
        "caja",
        "equipo",
        "camión",
        "user_facing_message",
        "no inventes",
        "determinístico",
    ]

    print("=== Métricas ===")
    print(f"System chars: {len(system_text)}")
    print(f"System ~tokens: {estimate_tokens(system_text)}")
    if tools:
        print(f"Tools count: {len(tools)}")
        print(f"Tools chars: {len(tools_blob)}")
        print(f"Tools ~tokens: {estimate_tokens(tools_blob)}")
    print(f"Combined ~tokens: {estimate_tokens(combined)}")
    print()

    print("=== Keyword hits (duplicación indicativa) ===")
    hits = keyword_hits(combined, keywords)
    for k, n in sorted(hits.items(), key=lambda x: -x[1]):
        if n > 0:
            flag = " ⚠" if n >= 3 else ""
            print(f"  {k}: {n}{flag}")
    print()

    dups = find_duplicate_lines(combined)
    if dups:
        print("=== Líneas repetidas (>=40 chars normalizados) ===")
        for line, n in dups:
            preview = line[:90] + ("…" if len(line) > 90 else "")
            print(f"  [{n}x] {preview}")
    else:
        print("=== Sin líneas duplicadas largas detectadas ===")

    return 0


if __name__ == "__main__":
    sys.exit(main())
