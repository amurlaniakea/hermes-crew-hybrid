FROM python:3.12.6-slim

LABEL maintainer="Pedro Sordo Martínez <amurlaniakea@gmail.com>"
LABEL description="Isolated container for CrewAI micro-crews"

# Instalar dependencias de CrewAI + crear directorios + usuario no-root
RUN pip install --no-cache-dir --only-binary :all: \
    crewai==0.115.10 \
    crewai-tools==0.115.10 \
    litellm==1.90.0 \
 && mkdir -p /workspace /output \
 && useradd -m crewuser \
 && chown -R crewuser:crewuser /workspace /output

WORKDIR /workspace
USER crewuser

ENTRYPOINT ["python"]
