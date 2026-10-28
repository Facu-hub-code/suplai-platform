"""Entrypoint del contenedor de un run (spec 138).

Versión 1: harness sin MCP. Arranca Claude Agent SDK con bash y archivos, le da un
pedido y registra en los logs cada tool que usa, el resultado y el costo. Sirve para
probar en GCP el modelo, el harness y la ejecución de código antes de sumar el MCP.

Variables de la ejecución:
  PROVEEDOR_MODELO  anthropic (API directa) o vertex (Claude en Vertex)
  MODELO            claude-opus-5-5 por defecto
  ANTHROPIC_API_KEY la inyecta Cloud Run desde Secret Manager (solo con anthropic)
  PEDIDO            lo que tiene que hacer el bot
  TOPE_USD          corta el run si el costo estimado llega a este valor
  MAX_TURNOS        corta el run después de esta cantidad de vueltas del loop
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import anyio
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, ToolUseBlock, query

PROVEEDOR = os.environ.get("PROVEEDOR_MODELO", "anthropic")
MODELO = os.environ.get("MODELO", "claude-opus-5-5")
TOPE_USD = float(os.environ.get("TOPE_USD", "1.0"))
MAX_TURNOS = int(os.environ.get("MAX_TURNOS", "20"))
TRABAJO = Path.home() / "trabajo"

PEDIDO = os.environ.get(
    "PEDIDO",
    "Con Python y pandas, generá 1.000 ventas al azar del año 2025 (fecha, cliente entre 30 "
    "clientes, monto entre 1.000 y 50.000 pesos) con semilla 42 y guardalas en ventas.csv. "
    "Calculá el total vendido por mes y el cliente que más compró. Respondé con una tabla "
    "de los 12 meses, el mes más alto y el mejor cliente.",
)

INSTRUCCIONES = (
    "Sos un analista de ventas que trabaja en segundo plano para una distribuidora. "
    "Trabajás en tu carpeta de trabajo con bash y Python. Calculá siempre con código; "
    "no inventes números. No tenés acceso a internet. Respondé en español rioplatense, corto."
)


def log(**campos: object) -> None:
    """Una línea JSON por evento: Cloud Logging la muestra como entrada con campos."""
    print(json.dumps(campos, ensure_ascii=False, default=str), flush=True)


def esperar_red(max_seg: int = 120) -> float:
    """Direct VPC egress tarda unos segundos en programar la red al arrancar."""
    url = "https://api.anthropic.com" if PROVEEDOR == "anthropic" else "https://aiplatform.googleapis.com"
    inicio = time.monotonic()
    while time.monotonic() - inicio < max_seg:
        try:
            urllib.request.urlopen(url, timeout=5)
            break
        except urllib.error.HTTPError:
            break  # respondió algo: la red ya está
        except Exception:
            time.sleep(5)
    return round(time.monotonic() - inicio, 1)


def entorno_harness() -> dict[str, str]:
    env = {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}  # sin telemetría: el firewall la bloquearía
    if PROVEEDOR == "vertex":
        env |= {
            "CLAUDE_CODE_USE_VERTEX": "1",
            "ANTHROPIC_VERTEX_PROJECT_ID": os.environ.get("PROYECTO", "suplai-agentes"),
            "CLOUD_ML_REGION": "global",
        }
    elif not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Falta ANTHROPIC_API_KEY (secreto anthropic-api-key).")
    return env


async def correr() -> int:
    TRABAJO.mkdir(exist_ok=True)
    opciones = ClaudeAgentOptions(
        model=MODELO,
        system_prompt=INSTRUCCIONES,
        cwd=str(TRABAJO),
        tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
        disallowed_tools=["WebFetch", "WebSearch"],
        permission_mode="bypassPermissions",  # nadie aprueba nada: el límite lo pone el entorno
        max_turns=MAX_TURNOS,
        max_budget_usd=TOPE_USD,
        env=entorno_harness(),
    )

    resultado: ResultMessage | None = None
    async for mensaje in query(prompt=PEDIDO, options=opciones):
        if isinstance(mensaje, AssistantMessage):
            for bloque in mensaje.content:
                if isinstance(bloque, ToolUseBlock):
                    entrada = bloque.input.get("command") or bloque.input.get("file_path") or ""
                    log(evento="tool", tool=bloque.name, detalle=str(entrada)[:300])
        elif isinstance(mensaje, ResultMessage):
            resultado = mensaje

    if resultado is None:
        log(evento="fin", ok=False, motivo="el harness terminó sin resultado")
        return 1

    log(
        evento="fin",
        ok=not resultado.is_error,
        subtipo=resultado.subtype,
        turnos=resultado.num_turns,
        segundos=round(resultado.duration_ms / 1000, 1),
        costo_usd=resultado.total_cost_usd,
        uso=resultado.usage,
    )
    log(evento="respuesta", texto=resultado.result)
    return 1 if resultado.is_error else 0


def main() -> int:
    log(evento="inicio", proveedor=PROVEEDOR, modelo=MODELO, tope_usd=TOPE_USD, max_turnos=MAX_TURNOS)
    log(evento="red_lista", espera_seg=esperar_red())
    return anyio.run(correr)


if __name__ == "__main__":
    sys.exit(main())
