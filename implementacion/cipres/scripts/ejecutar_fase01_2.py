#!/usr/bin/env python3
"""Fase 1.2 cipres — candidatos, enriquecimiento y aplicación (carga env backend)."""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts" / "fase-01-catalogo"
CIPRES = Path(__file__).resolve().parents[1]
INPUTS = CIPRES / "inputs"
OUTPUTS = CIPRES / "outputs"

load_dotenv(ROOT.parent / "backend-supabase" / ".env")
load_dotenv(ROOT / ".env")


def run_py(script: Path, args: list[str]) -> int:
    env = os.environ.copy()
    cmd = [sys.executable, str(script), *args]
    print("$", " ".join(cmd))
    return subprocess.call(cmd, env=env, cwd=str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fase 1.2 mejora descripciones — cipres")
    parser.add_argument("--limite", type=int, default=100, help="Candidatos a enriquecer")
    parser.add_argument("--aplicar", action="store_true", help="Persistir vista previa en Supabase")
    parser.add_argument(
        "--csv-entrada",
        default=str(OUTPUTS / "vista_previa_enriquecimiento.csv"),
        help="CSV de preview o revisado",
    )
    args = parser.parse_args()

    if not os.getenv("SUPABASE_DB_URL") and not os.getenv("SUPABASE_DB_URL_POOLER"):
        print("[FAIL] Falta SUPABASE_DB_URL en backend-supabase/.env", file=sys.stderr)
        return 1
    if not os.getenv("OPENAI_API_KEY"):
        print("[FAIL] Falta OPENAI_API_KEY en backend-supabase/.env", file=sys.stderr)
        return 1

    if args.aplicar:
        return run_py(
            SCRIPTS / "enriquecer_catalogo.py",
            ["--esquema", "cipres", "--aplicar", "--csv-entrada", args.csv_entrada],
        )

    rc = run_py(
        SCRIPTS / "buscar_candidatos.py",
        ["--esquema", "cipres", "--limite", str(args.limite)],
    )
    if rc != 0:
        return rc

    return run_py(
        SCRIPTS / "enriquecer_catalogo.py",
        [
            "--esquema",
            "cipres",
            "--csv-entrada",
            str(INPUTS / "candidatos_a_enriquecer.csv"),
            "--csv-salida",
            str(OUTPUTS / "vista_previa_enriquecimiento.csv"),
        ],
    )


if __name__ == "__main__":
    raise SystemExit(main())
