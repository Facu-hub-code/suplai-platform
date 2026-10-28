# Imagen del contenedor de un run (spec 138).
# Versión 1: Claude Agent SDK con bash, archivos y Python, sin MCP todavía.

FROM python:3.12-slim

# Usuario sin privilegios. Además, el harness no acepta bypassPermissions como root.
RUN useradd --create-home --uid 10001 agente
WORKDIR /home/agente/app

# Dependencias con versión fija. El wheel de claude-agent-sdk trae el CLI de Claude Code.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY entrypoint.py prueba_red.py ./

USER agente

ENTRYPOINT ["python", "-u", "entrypoint.py"]
