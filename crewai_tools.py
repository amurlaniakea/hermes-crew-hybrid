#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Herramientas CrewAI reales (BaseTool) para Hermes-Crew Hybrid.

Define herramientas que los agentes de CrewAI pueden usar:
- WebSearchTool: Buscar en la web
- FileReadTool: Leer archivos
- FileWriteTool: Escribir archivos
- ObsidianSearchTool: Buscar en el vault de Obsidian
"""

from crewai.tools import BaseTool
from typing import Optional
import subprocess
import json
from pathlib import Path


class WebSearchTool(BaseTool):
    """Herramienta para buscar en la web."""
    name: str = "web_search"
    description: str = "Search the web for information about a topic"
    
    def _run(self, query: str) -> str:
        """Ejecuta una búsqueda web."""
        try:
            # Usar curl para buscar en DuckDuckGo
            result = subprocess.run(
                ["curl", "-s", f"https://html.duckduckgo.com/html/?q={query}"],
                capture_output=True, text=True, timeout=10
            )
            # Extraer resultados simplificados
            import re
            titles = re.findall(r'<a rel="nofollow" class="result__a" href="[^"]*">([^<]+)</a>', result.stdout)
            snippets = re.findall(r'<a class="result__snippet" href="[^"]*">([^<]+)</a>', result.stdout)
            
            output = []
            for i, (title, snippet) in enumerate(zip(titles[:5], snippets[:5])):
                output.append(f"{i+1}. {title}\n   {snippet}")
            
            return "\n".join(output) if output else f"No results found for: {query}"
        except Exception as e:
            return f"Search error: {e}"


class FileReadTool(BaseTool):
    """Herramienta para leer archivos."""
    name: str = "file_read"
    description: str = "Read the contents of a file"
    
    def _run(self, file_path: str) -> str:
        """Lee un archivo."""
        try:
            path = Path(file_path)
            if not path.exists():
                return f"File not found: {file_path}"
            return path.read_text(encoding="utf-8")[:5000]  # Limitar a 5000 chars
        except Exception as e:
            return f"Read error: {e}"


class FileWriteTool(BaseTool):
    """Herramienta para escribir archivos."""
    name: str = "file_write"
    description: str = "Write content to a file"
    
    def _run(self, file_path: str, content: str) -> str:
        """Escribe contenido en un archivo."""
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Written {len(content)} chars to {file_path}"
        except Exception as e:
            return f"Write error: {e}"


class ObsidianSearchTool(BaseTool):
    """Herramienta para buscar en el vault de Obsidian."""
    name: str = "obsidian_search"
    description: str = "Search for notes in the Obsidian vault"
    
    def _run(self, query: str, vault_path: str = "/mnt/c/Users/Sil/Documents/Obsidian Vault") -> str:
        """Busca notas en el vault de Obsidian."""
        try:
            vault = Path(vault_path)
            if not vault.exists():
                return f"Vault not found: {vault_path}"
            
            results = []
            for md_file in vault.rglob("*.md"):
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                if query.lower() in content.lower():
                    # Extraer contexto alrededor del match
                    idx = content.lower().find(query.lower())
                    start = max(0, idx - 100)
                    end = min(len(content), idx + 200)
                    snippet = content[start:end].replace("\n", " ")
                    results.append(f"📄 {md_file.relative_to(vault)}\n   ...{snippet}...")
            
            return "\n\n".join(results[:10]) if results else f"No notes found for: {query}"
        except Exception as e:
            return f"Search error: {e}"


class ObsidianReadTool(BaseTool):
    """Herramienta para leer notas de Obsidian."""
    name: str = "obsidian_read"
    description: str = "Read a specific note from the Obsidian vault"
    
    def _run(self, note_path: str, vault_path: str = "/mnt/c/Users/Sil/Documents/Obsidian Vault") -> str:
        """Lee una nota específica del vault."""
        try:
            full_path = Path(vault_path) / note_path
            if not full_path.exists():
                # Buscar por nombre
                vault = Path(vault_path)
                matches = list(vault.rglob(f"*{note_path}*.md"))
                if matches:
                    full_path = matches[0]
                else:
                    return f"Note not found: {note_path}"
            
            content = full_path.read_text(encoding="utf-8")
            return f"# {full_path.stem}\n\n{content[:3000]}"
        except Exception as e:
            return f"Read error: {e}"


# ────────────────────────────────────────────────────────────────────────────
# Lista de herramientas disponibles
# ────────────────────────────────────────────────────────────────────────────

ALL_TOOLS = {
    "web_search": WebSearchTool,
    "file_read": FileReadTool,
    "file_write": FileWriteTool,
    "obsidian_search": ObsidianSearchTool,
    "obsidian_read": ObsidianReadTool,
}


def get_tool(tool_name: str) -> Optional[BaseTool]:
    """Obtiene una herramienta por nombre."""
    tool_class = ALL_TOOLS.get(tool_name)
    if tool_class:
        return tool_class()
    return None


def get_tools_list(tool_names: list) -> list:
    """Obtiene una lista de herramientas por nombres."""
    tools = []
    for name in tool_names:
        tool = get_tool(name)
        if tool:
            tools.append(tool)
    return tools


def list_available_tools() -> dict:
    """Lista todas las herramientas disponibles."""
    return {name: cls.__doc__ or "" for name, cls in ALL_TOOLS.items()}


if __name__ == "__main__":
    print("Available CrewAI tools:")
    for name, desc in list_available_tools().items():
        print(f"  - {name}: {desc[:60]}")
    
    # Test web search
    print("\n--- Testing WebSearchTool ---")
    tool = WebSearchTool()
    result = tool._run("AI agent security")
    print(result[:300])
