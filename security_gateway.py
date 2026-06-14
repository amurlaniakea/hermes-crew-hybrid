#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Security Gateway — Middleware de seguridad para outputs de CrewAI.

Todo output de CrewAI debe pasar por este gateway antes de llegar a Hermes.
Usa Agent Fixer Stage (v0.2.0) como motor de detección.
"""

import sys
import json
from pathlib import Path
from typing import Optional

# Añadir Agent Fixer Stage al path
FIXER_PATH = "/home/sil/agent-fixer-stage"
if FIXER_PATH not in sys.path:
    sys.path.insert(0, FIXER_PATH)

try:
    from agent_fixer import AgentFixer, FixerStatus
    _FIXER_AVAILABLE = True
except ImportError:
    _FIXER_AVAILABLE = False


class SecurityGateway:
    """
    Gateway de seguridad que todo output de CrewAI debe cruzar.
    
    Usa Agent Fixer Stage para detectar:
    - Inyección de prompts
    - Exfiltración de datos
    - Ejecución de comandos
    - Obfuscación (leetspeak, homoglyphs, cross-line)
    """

    def __init__(self, scope: str, sensitivity: str = "medium", mode: str = "medium"):
        self.scope = scope
        self.sensitivity = sensitivity
        self.mode = mode
        self._fixer = None

    @property
    def fixer(self):
        if self._fixer is None and _FIXER_AVAILABLE:
            self._fixer = AgentFixer(
                scope=self.scope,
                sensitivity=self.sensitivity,
                action="clean",
                mode=self.mode,
            )
        return self._fixer

    def process(self, crew_output: str) -> dict:
        """
        Procesa el output de CrewAI a través del Agent Fixer Stage.

        Returns:
            {
                "safe": bool,
                "output": str,  # limpio o vacío
                "score": float,
                "reason": str,
                "action_taken": str,  # "pass" | "clean" | "reject"
                "details": dict
            }
        """
        if not _FIXER_AVAILABLE:
            return {
                "safe": True,
                "output": crew_output,
                "score": 0.0,
                "reason": "Fixer Stage not available, bypassing",
                "action_taken": "pass",
                "details": {"warning": "Security gateway bypassed"},
            }

        if not crew_output or not crew_output.strip():
            return {
                "safe": True,
                "output": "",
                "score": 0.0,
                "reason": "Empty output",
                "action_taken": "pass",
                "details": {},
            }

        result = self.fixer.check(crew_output)

        if result.status == FixerStatus.PASS:
            return {
                "safe": True,
                "output": result.cleaned_output,
                "score": result.score,
                "reason": result.reason,
                "action_taken": "pass",
                "details": result.details,
            }
        elif result.status == FixerStatus.CLEAN:
            return {
                "safe": True,
                "output": result.cleaned_output,
                "score": result.score,
                "reason": result.reason,
                "action_taken": "clean",
                "details": result.details,
            }
        else:  # REJECT
            return {
                "safe": False,
                "output": "",
                "score": result.score,
                "reason": result.reason,
                "action_taken": "reject",
                "details": result.details,
            }


def process_crew_output(crew_output: str, scope: str, sensitivity: str = "medium") -> dict:
    """
    Función de conveniencia para procesar output de CrewAI.
    
    Args:
        crew_output: Texto generado por la tripulación CrewAI
        scope: Scope/tarea original
        sensitivity: "low", "medium", "high"
    
    Returns:
        dict con safe, output, score, reason, action_taken
    """
    gateway = SecurityGateway(scope=scope, sensitivity=sensitivity)
    return gateway.process(crew_output)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Security Gateway — Filtra outputs de CrewAI"
    )
    parser.add_argument("--input", "-i", help="Archivo de input (o stdin)")
    parser.add_argument("--scope", "-s", required=True, help="Scope de la tarea")
    parser.add_argument("--sensitivity", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--json", action="store_true", help="Output como JSON")

    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            crew_output = f.read()
    else:
        crew_output = sys.stdin.read()

    result = process_crew_output(crew_output, args.scope, args.sensitivity)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Safe: {result['safe']}")
        print(f"Action: {result['action_taken']}")
        print(f"Score: {result['score']:.2f}")
        if result['reason']:
            print(f"Reason: {result['reason']}")
        if result['output']:
            print(f"\n--- Output ---\n{result['output'][:500]}")
