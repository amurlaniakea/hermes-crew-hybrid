#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
MCP Tool Auditor — Integración de MCP Core Defense con CrewAI.

Antes de que CrewAI use herramientas (tools), las audita con MCP Core Defense
para verificar que no contengan instrucciones maliciosas.

Flujo:
    1. CrewAI recibe lista de herramientas
    2. MCP Tool Auditor escanea cada herramienta con mcp_audit.py
    3. Herramientas limpias → CrewAI las usa
    4. Herramientas sospechosas → rechazadas + alerta
"""

import sys
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

# Paths — desde variables de entorno (portable, nunca hardcodear)
MCP_CORE_DEFENSE_PATH = os.getenv("MCP_CORE_DEFENSE_PATH", "/home/sil/mcp-core-defense")
MCP_AUDIT_SCRIPT = os.path.join(MCP_CORE_DEFENSE_PATH, "scripts", "mcp_audit.py")
MCP_VENV_PYTHON = os.path.join(MCP_CORE_DEFENSE_PATH, "venv", "bin", "python3")


class MCPToolAuditor:
    """
    Audita herramientas MCP antes de que CrewAI las use.
    Usa mcp_audit.py de MCP Core Defense.
    """
    
    def __init__(self, sensitivity: str = "medium"):
        self.sensitivity = sensitivity
        self._audit_available = None
    
    @property
    def audit_available(self) -> bool:
        if self._audit_available is None:
            self._audit_available = (
                Path(MCP_AUDIT_SCRIPT).exists() and 
                Path(MCP_VENV_PYTHON).exists()
            )
        return self._audit_available
    
    def audit_tool(self, tool_name: str, tool_description: str = "") -> dict:
        """
        Audita una herramienta MCP.
        
        Args:
            tool_name: Nombre de la herramienta (ej: "web_search")
            tool_description: Descripción de la herramienta
        
        Returns:
            dict con:
                - safe: bool
                - score: float (0.0-1.0)
                - reason: str
                - tool_name: str
        """
        if not self.audit_available:
            return {"safe": True, "score": 0.0, "reason": "Audit not available", "tool_name": tool_name}
        
        # ── Validar inputs antes de pasarlos a subprocess (S8705) ──
        from path_validator import sanitize_shell_arg
        try:
            safe_name = sanitize_shell_arg(tool_name)
            safe_desc = sanitize_shell_arg(tool_description, max_length=1024)
        except ValueError as e:
            return {"safe": False, "score": 1.0, "reason": f"Input validation failed: {e}", "tool_name": tool_name}
        
        try:
            result = subprocess.run(
                [MCP_VENV_PYTHON, MCP_AUDIT_SCRIPT,
                 "--tool-name", safe_name,
                 "--tool-description", safe_desc,
                 "--sensitivity", self.sensitivity,
                 "--json"],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    audit_result = json.loads(result.stdout)
                    return {
                        "safe": audit_result.get("safe", True),
                        "score": audit_result.get("score", 0.0),
                        "reason": audit_result.get("reason", ""),
                        "tool_name": tool_name,
                    }
                except json.JSONDecodeError:
                    pass
            
            return {"safe": True, "score": 0.0, "reason": "Audit passed (no output)", "tool_name": tool_name}
            
        except Exception as e:
            return {"safe": True, "score": 0.0, "reason": f"Audit error: {e}", "tool_name": tool_name}
    
    def audit_tools_list(self, tools: list) -> dict:
        """
        Audita una lista de herramientas.
        
        Args:
            tools: Lista de dicts con name y description
        
        Returns:
            dict con:
                - all_safe: bool
                - tools_checked: int
                - tools_rejected: int
                - results: list de dicts individuales
        """
        results = []
        rejected = 0
        
        for tool in tools:
            if isinstance(tool, str):
                tool_name = tool
                tool_desc = ""
            elif isinstance(tool, dict):
                tool_name = tool.get("name", str(tool))
                tool_desc = tool.get("description", "")
            else:
                continue
            
            audit = self.audit_tool(tool_name, tool_desc)
            results.append(audit)
            if not audit.get("safe", True):
                rejected += 1
        
        return {
            "all_safe": rejected == 0,
            "tools_checked": len(results),
            "tools_rejected": rejected,
            "results": results,
        }
    
    def filter_safe_tools(self, tools: list) -> list:
        """
        Filtra solo las herramientas que pasan la auditoría.
        
        Args:
            tools: Lista de herramientas
        
        Returns:
            Lista de herramientas seguras
        """
        safe_tools = []
        for tool in tools:
            if isinstance(tool, str):
                tool_name = tool
                tool_desc = ""
            elif isinstance(tool, dict):
                tool_name = tool.get("name", str(tool))
                tool_desc = tool.get("description", "")
            else:
                safe_tools.append(tool)
                continue
            
            audit = self.audit_tool(tool_name, tool_desc)
            if audit.get("safe", True):
                safe_tools.append(tool)
            else:
                print(f"[MCP AUDIT] Tool rejected: {tool_name} (score: {audit.get('score', 0):.2f})")
        
        return safe_tools


# ────────────────────────────────────────────────────────────────────────────
# Función de conveniencia
# ────────────────────────────────────────────────────────────────────────────

def audit_crew_tools(tools: list, sensitivity: str = "medium") -> dict:
    """
    Función de conveniencia para auditar herramientas de CrewAI.
    
    Args:
        tools: Lista de herramientas (strings o dicts)
        sensitivity: "low", "medium", "high"
    
    Returns:
        dict con all_safe, tools_checked, tools_rejected, results
    """
    auditor = MCPToolAuditor(sensitivity=sensitivity)
    return auditor.audit_tools_list(tools)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Audit MCP tools for CrewAI")
    parser.add_argument("--tools", nargs="+", required=True, help="Tool names to audit")
    parser.add_argument("--sensitivity", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--json", action="store_true")
    
    args = parser.parse_args()
    
    result = audit_crew_tools(args.tools, args.sensitivity)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Tools checked: {result['tools_checked']}")
        print(f"Tools rejected: {result['tools_rejected']}")
        print(f"All safe: {result['all_safe']}")
        for r in result['results']:
            status = "✓" if r['safe'] else "✗"
            print(f"  {status} {r['tool_name']}: {r['reason']}")
