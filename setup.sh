#!/bin/bash
set -euo pipefail

echo "=== Hermes-Crew Setup ==="
python_cmd=${PYTHON_CMD:-python3}

# 1. Verificar Python 3.10+
python_version=$($python_cmd --version 2>/dev/null | awk '{print $2}')
major=$(echo $python_version | cut -d. -f1)
minor=$(echo $python_version | cut -d. -f2)
if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 10 ]); then
    echo "ERROR: Python 3.10+ requerido (tienes $python_version)"
    exit 1
fi
echo "OK: Python $python_version"

# 2. Crear venv
if [ ! -d "venv" ]; then
    $python_cmd -m venv venv
    echo "OK: venv creado"
else
    echo "OK: venv existente"
fi

# 3. Instalar dependencias
source venv/bin/activate 2>/dev/null || . venv/bin/activate 2>/dev/null || true
if command -v uv &> /dev/null; then
    uv pip install -r requirements.txt --only-binary :all:
else
    pip install --upgrade pip --only-binary :all:
    pip install --only-binary :all: -r requirements.txt
fi
echo "OK: dependencias instaladas"

# 4. Copiar .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "OK: .env creado desde .env.example"
    else
        echo "AVISO: .env.example no encontrado"
    fi
fi

# 5. Verificar rutas (opcional, no fallar si faltan)
echo "Verificando rutas configuradas..."
for var in MCP_CORE_DEFENSE_PATH HERMES_CREW_VENV AGENT_FIXER_PATH; do
    val=${!var:-}
    if [ -z "$val" ]; then
        echo "  AVISO: $var no configurado (opcional para modo básico)"
    else
        echo "  OK: $var = $val"
    fi
done

echo "=== Setup completo. Próximos pasos: ==="
echo "  1. Configura .env con tus rutas reales"
echo "  2. Ejecuta: python invoke_crew_task.py --task 'prueba inicial'"
