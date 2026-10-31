FROM python:3.12.6-slim

LABEL maintainer="Pedro Sordo Martínez <amurlaniakea@gmail.com>"
LABEL description="Isolated container for CrewAI micro-crews"

# Copiar y usar el archivo de dependencias actualizado (evita desincronización)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --only-binary :all: -r /tmp/requirements.txt  && rm /tmp/requirements.txt  && mkdir -p /workspace /output  && useradd -m crewuser  && chown -R crewuser:crewuser /workspace /output

WORKDIR /workspace
USER crewuser

ENTRYPOINT ["python"]
