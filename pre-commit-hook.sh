#!/bin/bash
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Pre-commit hook: Code Safety con CrewAI + Ollama + Agent Fixer Stage
#
# Instala este hook:
#   cp pre-commit .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit

set -e

# ── Configuration ────────────────────────────────────────────────────────────

CREW_SCRIPT="/home/sil/hermes-crew-hybrid/git_safety_crew.py"
FIXER_SCRIPT="/home/sil/hermes-crew-hybrid/security_gateway.py"
VENV_PYTHON="/home/sil/mcp-core-defense/venv/bin/python3"
OBSIDIAN_VAULT="/mnt/c/Users/Sil/Documents/Obsidian Vault/Memorias/IA y Computacion"
LOG_DIR="/tmp/git_safety_logs"

# ── Check dependencies ──────────────────────────────────────────────────────

if [ ! -f "$CREW_SCRIPT" ]; then
    echo "⚠️  git_safety_crew.py no encontrado. Saltando análisis de seguridad."
    exit 0
fi

if [ ! -f "$VENV_PYTHON" ]; then
    echo "⚠️  venv no encontrado. Saltando análisis de seguridad."
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

CREW_REPORT=$(echo "$GIT_DIFF" | env PYTHONUNBUFFERED=1 "$VENV_PYTHON" -u "$CREW_SCRIPT" 2>&1) || true

# Log the report
echo "$CREW_REPORT" > "$LOG_FILE"
echo "📝 Log guardado: $LOG_FILE"

# ── Run Agent Fixer Stage ───────────────────────────────────────────────────

FIXER_RESULT=$(echo "$CREW_REPORT" | env PYTHONUNBUFFERED=1 "$VENV_PYTHON" -c "
import sys
sys.path.insert(0, '/home/sil/hermes-crew-hybrid')
sys.path.insert(0, '/home/sil/agent-fixer-stage')
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

# Check CrewAI verdict
CREW_FAIL=false
if echo "$CREW_REPORT" | grep -qi "VERDICT: FAIL"; then
    CREW_FAIL=true
fi

# Check Agent Fixer verdict
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
    
    # Save report to Obsidian
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
    exit 0
fi
