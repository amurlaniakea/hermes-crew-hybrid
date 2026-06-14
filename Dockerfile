FROM python:3.12-slim

LABEL maintainer="Pedro Sordo Martínez <amurlaniakea@gmail.com>"
LABEL description="Isolated container for CrewAI micro-crews"

# Instalar dependencias de CrewAI
RUN pip install --no-cache-dir \
    crewai==0.100.0 \
    crewai-tools \
    langchain \
    langchain-community \
    duckduckgo-search \
    beautifulsoup4 \
    requests

# Crear directorio de trabajo
WORKDIR /workspace

# Output directory
RUN mkdir -p /output

# No root
RUN useradd -m crewuser
USER crewuser

ENTRYPOINT ["python"]
