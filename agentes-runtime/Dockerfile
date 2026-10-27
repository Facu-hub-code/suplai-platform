# Imagen del contenedor de un run (spec 138).
# Versión 0: sin harness. Solo prueba la red cerrada y los permisos de agente-run.

# Base chica con Python. La versión fija evita que un rebuild cambie algo sin aviso.
FROM python:3.12-slim

# Usuario sin privilegios: lo que corra el bot no puede tocar el sistema del contenedor.
RUN useradd --create-home --uid 10001 agente
WORKDIR /home/agente/app

# Solo librería estándar de Python en esta versión: no hay requirements todavía.
COPY prueba_red.py .

USER agente

# Lo que corre cuando Cloud Run arranca la ejecución. Cuando termina, termina el run.
ENTRYPOINT ["python", "-u", "prueba_red.py"]
