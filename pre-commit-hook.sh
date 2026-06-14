#!/bin/bash
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Pre-commit hook: Code Safety con CrewAI + Ollama + Agent Fixer Stage
#
# Instalación:
#   1. Copiar a .git/hooks/pre-commit: cp pre-commit-hook.sh .git/hooks/pre-commit
#   2. Dar permisos: chmod +x .git/hooks/pre-commit
#   3. Configurar .env con las rutas de tu sistema
#
# Para forzar el commit (no recomendado): git commit --no-verify

set -e

# ── Detectar directorio del repo ─────────────────────────────────────────────

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
    echo "⚠️  No se pudo detectar el directorio del repo. Saltando análisis."
    exit 0
fi

# ── Cargar .env si existe ────────────────────────────────────────────────────

ENV_FILE="$REPO_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

# ── Configuración (con valores por defecto) ──────────────────────────────────

CREW_SCRIPT="${CREW_SCRIPT:-$REPO_ROOT/git_safety_crew.py}"
OBSIDIAN_VAULT="${OBSIDIAN_VAULT_PATH:-}"
LOG_DIR="${GIT_SAFETY_LOG_DIR:-/tmp/git_safety_logs}"

# Detectar python3 del sistema o venv
if [ -n "$VENV_PYTHON" ] && [ -f "$VENV_PYTHON" ]; then
    PYTHON3="$VENV_PYTHON"
elif [ -f "$REPO_ROOT/venv/bin/python3" ]; then
    PYTHON3="$REPO_ROOT/venv/bin/python3"
else
    PYTHON3="$(command -v python3 2>/dev/null)"
fi

if [ -z "$PYTHON3" ] || [ ! -f "$PYTHON3" ]; then
    echo "⚠️  python3 no encontrado. Saltando análisis de seguridad."
    exit 0
fi

# ── Check dependencies ──────────────────────────────────────────────────────

if [ ! -f "$CREW_SCRIPT" ]; then
    echo "⚠️  git_safety_crew.py no encontrado en $CREW_SCRIPT. Saltando análisis."
    exit 0
fi

# Verificar que crewai está instalado
if ! "$PYTHON3" -c "import crewai" 2>/dev/null; then
    echo "⚠️  crewai no instalado en $PYTHON3. Saltando análisis de seguridad."
    exit 0
fi

# ── Get staged diff ─────────────────────────────────────────────────────────

GIT_DIFF=$(git diff --cached --diff-algorithm=minimal)

# If no code changes, allow commit immediately
if [ -z "$GIT_DIFF" ]; then
    exit 0
fi

# Count changed files
CHANGED_FILES=$(git diff --cached --name-only | wc -l)
echo "🛡️  Code Safety: Analizando $CHANGED_FILES archivo(s) con CrewAI + Ollama..."

# ── Run CrewAI analysis ─────────────────────────────────────────────────────

mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/safety_$TIMESTAMP.log"

CREW_REPORT=$(echo "$GIT_DIFF" | env PYTHONUNBUFFERED=1 "$PYTHON3" -u "$CREW_SCRIPT" 2>&1) || true

# Log the report
echo "$CREW_REPORT" > "$LOG_FILE"
echo "📝 Log guardado: $LOG_FILE"

# ── Run Agent Fixer Stage ───────────────────────────────────────────────────

FIXER_RESULT=$(echo "$CREW_REPORT" | env PYTHONUNBUFFERED=1 "$PYTHON3" -c "
import sys, os

# Añadir paths del repo
repo_root = os.environ.get('REPO_ROOT', '$REPO_ROOT')
sys.path.insert(0, repo_root)

# Buscar agent-fixer-stage
fixer_paths = [
    os.path.join(repo_root, '..', 'agent-fixer-stage'),
    os.path.join(repo_root, 'agent-fixer-stage'),
    '/home/sil/agent-fixer-stage',
]
for fp in fixer_paths:
    if os.path.isdir(fp):
        sys.path.insert(0, fp)
        break

from security_gateway import SecurityGateway

report = sys.stdin.read()
gateway = SecurityGateway(scope='Git pre-commit security analysis', sensitivity='medium')
result = gateway.process(report)

print(f'FIXER_STATUS: {result[\"action_taken\"]}')
print(f'FIXER_SCORE: {result[\"score\"]:.2f}')
if result['reason']:
    print(f'FIXER_REASON: {result[\"reason\"]}')
" 2>&1) || true

echo "$FIXER_RESULT"

# ── Parse verdict ───────────────────────────────────────────────────────────

CREW_FAIL=false
if echo "$CREW_REPORT" | grep -qi "VERDICT: FAIL"; then
    CREW_FAIL=true
fi

FIXER_FAIL=false
if echo "$FIXER_RESULT" | grep -qi "FIXER_STATUS: reject"; then
    FIXER_FAIL=true
fi

# ── Decision ────────────────────────────────────────────────────────────────

if [ "$CREW_FAIL" = true ] || [ "$FIXER_FAIL" = true ]; then
    echo ""
    echo "❌ [COMMIT RECHAZADO] Code Safety detectó riesgos:"
    echo ""
    
    if [ "$CREW_FAIL" = true ]; then
        echo "  → CrewAI detectó vulnerabilidades:"
        echo "$CREW_REPORT" | grep -A 3 "VERDICT: FAIL" | head -10
    fi
    
    if [ "$FIXER_FAIL" = true ]; then
        echo "  → Agent Fixer Stage detectó anomalías:"
        echo "$FIXER_RESULT" | grep "FIXER_REASON"
    fi
    
    echo ""
    echo "Para forzar el commit (no recomendado): git commit --no-verify"
    exit 1
else
    echo ""
    echo "✅ [COMMIT APROBADO] Código verificado por CrewAI + Agent Fixer Stage."
    
    # Save report to Obsidian (si está configurado)
    if [ -n "$OBSIDIAN_VAULT" ] && [ -d "$OBSIDIAN_VAULT" ]; then
        OBSIDIAN_FILE="$OBSIDIAN_VAULT/git_safety_$(git rev-parse --abbrev-ref HEAD)_${TIMESTAMP}.md"
        cat > "$OBSIDIAN_FILE" << OBSHEADER
---
title: Git Safety Report - ${TIMESTAMP}
date: $(date +%Y-%m-%d)
tags: [git, security, crewai, pre-commit]
branch: $(git rev-parse --abbrev-ref HEAD)
commit: $(git rev-parse HEAD 2>/dev/null || echo "pending")
status: APPROVED
---

# Git Safety Report

**Fecha:** $(date)
**Branch:** $(git rev-parse --abbrev-ref HEAD)
**Archivos cambiados:** $CHANGED_FILES

## CrewAI Analysis

\`\`\`
$CREW_REPORT
\`\`\`

## Agent Fixer Stage

\`\`\`
$FIXER_RESULT
\`\`\`
OBSHEADER
        echo "📝 Reporte guardado en Obsidian: $OBSIDIAN_FILE"
    fi
    
    exit 0
fi
