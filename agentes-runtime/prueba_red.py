"""Prueba de humo del contenedor de un run (spec 138, plan de prueba).

Chequea que la red cerrada y la cuenta agente-run se comporten como dice el diseño.
Cada chequeo imprime una línea JSON (Cloud Logging la muestra como entrada estructurada).
Sale con código 1 si algún chequeo no da lo esperado, así la ejecución queda en error.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

METADATA = "http://metadata.google.internal/computeMetadata/v1"
PROYECTO = os.environ.get("PROYECTO", "suplai-agentes")
REGION = os.environ.get("REGION", "us-east4")
BUCKET = os.environ.get("BUCKET_DATOS", "suplai-agentes-datos")
MCP_HOST = os.environ.get("MCP_HOST", "mcp.suplaisales.com")
TIMEOUT = 8


def token() -> str:
    """Token de la cuenta agente-run, pedido al servidor de metadatos del contenedor."""
    req = urllib.request.Request(
        f"{METADATA}/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)["access_token"]


def cuenta() -> str:
    req = urllib.request.Request(
        f"{METADATA}/instance/service-accounts/default/email",
        headers={"Metadata-Flavor": "Google"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode()


def pedir(url: str, bearer: str | None = None) -> int | str:
    """Código HTTP de la respuesta, o el tipo de error de red si no hubo respuesta."""
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # timeout, conexión rechazada, DNS
        return type(e.__cause__ or e).__name__


def esperar_red(url: str, max_seg: int = 120) -> float:
    """Espera a que la salida al MCP quede programada (Direct VPC egress puede tardar
    un minuto o más al arrancar la instancia). Devuelve los segundos que esperó."""
    inicio = time.monotonic()
    while time.monotonic() - inicio < max_seg:
        if isinstance(pedir(url), int):
            break
        time.sleep(5)
    return round(time.monotonic() - inicio, 1)


def chequeo(nombre: str, esperado: str, obtenido: object, ok: bool) -> bool:
    print(json.dumps({"chequeo": nombre, "esperado": esperado, "obtenido": str(obtenido), "ok": ok}))
    return ok


def main() -> int:
    espera = esperar_red(f"https://{MCP_HOST}/health")
    print(json.dumps({"espera_red_seg": espera}))
    tok = token()
    resultados = [
        chequeo("cuenta del contenedor", "agente-run", cuenta(), cuenta().startswith("agente-run@")),
    ]

    ips = sorted({a[4][0] for a in socket.getaddrinfo("storage.googleapis.com", 443)})
    resultados.append(
        chequeo("DNS privado de Google", "199.36.153.8/30", ips, all(ip.startswith("199.36.153.") for ip in ips))
    )

    vertex = pedir(
        f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{PROYECTO}/locations/{REGION}/models", tok
    )
    resultados.append(chequeo("Vertex con la cuenta agente-run", "200", vertex, vertex == 200))

    bucket = pedir(f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o", tok)
    resultados.append(chequeo("listar el bucket de datos", "403 (sin permiso)", bucket, bucket == 403))

    mcp = pedir(f"https://{MCP_HOST}/health")
    resultados.append(chequeo("MCP en Railway", "respuesta HTTP", mcp, isinstance(mcp, int)))

    afuera = pedir("https://example.com")
    resultados.append(chequeo("otro sitio de internet", "bloqueado (sin respuesta)", afuera, not isinstance(afuera, int)))

    todo_ok = all(resultados)
    print(json.dumps({"resultado": "ok" if todo_ok else "fallo", "chequeos": len(resultados)}))
    return 0 if todo_ok else 1


if __name__ == "__main__":
    sys.exit(main())
