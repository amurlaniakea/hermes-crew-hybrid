#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Consolidación: CrewAI → Hermes → Obsidian.

Toma el output sanitizado de CrewAI, extrae el valor puro,
descarta el ruido de conversación interna entre agentes,
y genera notas estructuradas para Obsidian.

Formato de salida: Markdown con frontmatter YAML compatible con Obsidian.
"""

import re
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


# ────────────────────────────────────────────────────────────────────────────
# Parser de output CrewAI
# ────────────────────────────────────────────────────────────────────────────

class CrewOutputParser:
    """
    Parsea el output de una tripulación CrewAI y extrae valor puro.
    
    El output de CrewAI suele contener:
    - Conversación interna entre agentes (ruido)
    - Resultados intermedios (ruido)
    - El resultado final (valor)
    
    Este parser extrae solo el valor.
    """
    
    def __init__(self):
        # Patrones de ruido comunes en outputs de CrewAI
        self._noise_patterns = [
            r'Agent:\s*.*?\n',  # Mensajes entre agentes
            r'Thinking\.\.\.',   # Pensamiento interno
            r'Action:.*?\n',     # Acciones internas
            r'Observation:.*?\n', # Observaciones
            r'\[CREW\].*?\n',    # Logs del contenedor
        ]
    
    def parse(self, raw_output: str) -> dict:
        """
        Parsea el output de CrewAI y extrae secciones estructuradas.
        
        Returns:
            {
                "title": str,
                "summary": str,
                "sections": [{"heading", "content"}],
                "key_findings": [str],
                "metadata": {"crew_size", "duration", "timestamp"}
            }
        """
        # 1. Limpiar ruido
        cleaned = self._clean_noise(raw_output)
        
        # 2. Extraer título (primer heading o primera línea)
        title = self._extract_title(cleaned)
        
        # 3. Extraer secciones (headings + contenido)
        sections = self._extract_sections(cleaned)
        
        # 4. Extraer hallazgos clave (listas con bullets)
        key_findings = self._extract_key_findings(cleaned)
        
        # 5. Generar resumen (primer párrafo significativo)
        summary = self._extract_summary(cleaned)
        
        return {
            "title": title,
            "summary": summary,
            "sections": sections,
            "key_findings": key_findings,
            "metadata": {
                "parsed_at": datetime.now().isoformat(),
                "original_length": len(raw_output),
                "cleaned_length": len(cleaned),
            }
        }
    
    def _clean_noise(self, text: str) -> str:
        """Elimina ruido de conversación interna entre agentes."""
        cleaned = text
        for pattern in self._noise_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        # Limpiar líneas vacías excesivas
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()
    
    def _extract_title(self, text: str) -> str:
        """Extrae el título del documento."""
        # Buscar primer heading
        match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
        if match:
            return match.group(1).strip()
        # Fallback: primera línea no vacía
        for line in text.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                return line[:80]
        return "CrewAI Output"
    
    def _extract_sections(self, text: str) -> list:
        """Extrae secciones (heading + contenido)."""
        sections = []
        current_heading = None
        current_content = []
        
        for line in text.split('\n'):
            heading_match = re.match(r'^#{1,3}\s+(.+)$', line)
            if heading_match:
                if current_heading:
                    sections.append({
                        "heading": current_heading,
                        "content": '\n'.join(current_content).strip()
                    })
                current_heading = heading_match.group(1)
                current_content = []
            else:
                current_content.append(line)
        
        # Última sección
        if current_heading:
            sections.append({
                "heading": current_heading,
                "content": '\n'.join(current_content).strip()
            })
        
        return sections
    
    def _extract_key_findings(self, text: str) -> list:
        """Extrae hallazgos clave (líneas con bullets o numeradas)."""
        findings = []
        for line in text.split('\n'):
            line = line.strip()
            # Bullets
            if re.match(r'^[-*•]\s+(.+)', line):
                findings.append(re.match(r'^[-*•]\s+(.+)', line).group(1))
            # Numerados
            elif re.match(r'^\d+\.\s+(.+)', line):
                findings.append(re.match(r'^\d+\.\s+(.+)', line).group(1))
        return findings[:20]  # Máximo 20 hallazgos
    
    def _extract_summary(self, text: str) -> str:
        """Extrae un resumen (primer párrafo significativo)."""
        for paragraph in text.split('\n\n'):
            paragraph = paragraph.strip()
            if len(paragraph) > 50 and not paragraph.startswith('#'):
                return paragraph[:500]
        return ""


# ────────────────────────────────────────────────────────────────────────────
# Generador de notas Obsidian
# ────────────────────────────────────────────────────────────────────────────

class ObsidianNoteGenerator:
    """
    Genera notas en formato Obsidian (Markdown + frontmatter YAML).
    """
    
    def __init__(self, vault_path: str = "/mnt/c/Users/Sil/Documents/Obsidian Vault/Memorias/IA y Computacion"):
        self.vault_path = Path(vault_path)
    
    def generate_note(self, parsed_output: dict, tags: list = None, source: str = "crewai") -> str:
        """
        Genera una nota de Obsidian a partir del output parseado.
        
        Args:
            parsed_output: Output de CrewOutputParser.parse()
            tags: Tags para el frontmatter
            source: Fuente del contenido ("crewai", "manual", etc.)
        
        Returns:
            String con la nota en formato Markdown + frontmatter
        """
        if tags is None:
            tags = ["agents", "crewai", "auto-generated"]
        
        # Frontmatter
        frontmatter = {
            "title": parsed_output["title"],
            "date": datetime.now().strftime("%Y-%m-%d"),
            "tags": tags,
            "source": source,
            "auto_generated": True,
        }
        
        if parsed_output["metadata"]:
            frontmatter["original_length"] = parsed_output["metadata"].get("original_length", 0)
            frontmatter["cleaned_length"] = parsed_output["metadata"].get("cleaned_length", 0)
        
        # Construir nota
        lines = ["---"]
        for key, value in frontmatter.items():
            if isinstance(value, list):
                lines.append(f"{key}: [{', '.join(value)}]")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        lines.append("")
        
        # Título
        lines.append(f"# {parsed_output['title']}")
        lines.append("")
        
        # Resumen
        if parsed_output["summary"]:
            lines.append(f"> {parsed_output['summary']}")
            lines.append("")
        
        # Hallazgos clave
        if parsed_output["key_findings"]:
            lines.append("## Key Findings")
            lines.append("")
            for finding in parsed_output["key_findings"]:
                lines.append(f"- {finding}")
            lines.append("")
        
        # Secciones
        for section in parsed_output["sections"]:
            lines.append(f"## {section['heading']}")
            lines.append("")
            if section["content"]:
                lines.append(section["content"])
                lines.append("")
        
        # Metadata
        lines.append("---")
        lines.append(f"*Generated by CrewAI + Agent Fixer Stage on {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
        
        return "\n".join(lines)
    
    def save_note(self, content: str, filename: str, subfolder: str = None) -> str:
        """
        Guarda la nota en el vault de Obsidian.
        
        Args:
            content: Contenido de la nota
            filename: Nombre del archivo (sin extensión)
            subfolder: Subcarpeta dentro del vault (opcional)
        
        Returns:
            Path al archivo guardado
        """
        if subfolder:
            target_dir = self.vault_path / subfolder
        else:
            target_dir = self.vault_path
        
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Limpiar filename
        safe_filename = re.sub(r'[^\w\s-]', '', filename).strip().replace(' ', '_')
        filepath = target_dir / f"{safe_filename}.md"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return str(filepath)


# ────────────────────────────────────────────────────────────────────────────
# Función de consolidación completa
# ────────────────────────────────────────────────────────────────────────────

def consolidate_crew_output(
    crew_result: dict,
    tags: list = None,
    vault_path: str = None,
    save: bool = True,
) -> dict:
    """
    Función de consolidación: CrewAI → Hermes → Obsidian.
    
    Toma el resultado de invoke_crew_task(), lo parsea,
    genera la nota de Obsidian y la guarda.
    
    Args:
        crew_result: Resultado de invoke_crew_task()
        tags: Tags para la nota
        vault_path: Path al vault de Obsidian
        save: Si True, guarda la nota en el vault
    
    Returns:
        dict con:
            - parsed: output parseado
            - note_content: contenido de la nota
            - note_path: path al archivo guardado (si save=True)
            - status: "success" | "error"
    """
    try:
        # 1. Parsear output
        parser = CrewOutputParser()
        security_output = crew_result.get("security", {}).get("cleaned_output", "")
        raw_output = crew_result.get("raw_output", "")
        
        # Usar output sanitizado si está disponible, sino el raw
        output_to_parse = security_output if security_output else raw_output
        parsed = parser.parse(output_to_parse)
        
        # 2. Generar nota
        generator = ObsidianNoteGenerator(vault_path=vault_path)
        note_content = generator.generate_note(parsed, tags=tags)
        
        # 3. Guardar en Obsidian
        note_path = None
        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = re.sub(r'[^\w\s-]', '', parsed["title"]).strip().replace(' ', '_')[:50]
            filename = f"crew_{safe_title}_{timestamp}"
            note_path = generator.save_note(note_content, filename)
        
        return {
            "status": "success",
            "parsed": parsed,
            "note_content": note_content,
            "note_path": note_path,
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "parsed": None,
            "note_content": None,
            "note_path": None,
        }


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Consolidate CrewAI output into Obsidian notes"
    )
    parser.add_argument("--input", "-i", required=True, help="Archivo de output de CrewAI")
    parser.add_argument("--vault", "-v", default=None, help="Path al vault de Obsidian")
    parser.add_argument("--tags", "-t", nargs="+", default=["agents", "crewai"], help="Tags")
    parser.add_argument("--no-save", action="store_true", help="No guardar, solo mostrar")
    
    args = parser.parse_args()
    
    with open(args.input) as f:
        raw_output = f.read()
    
    # Simular resultado de invoke_crew_task
    crew_result = {
        "raw_output": raw_output,
        "security": {"cleaned_output": raw_output}
    }
    
    result = consolidate_crew_output(
        crew_result,
        tags=args.tags,
        vault_path=args.vault,
        save=not args.no_save,
    )
    
    if result["status"] == "success":
        print(f"✅ Nota generada")
        print(f"Título: {result['parsed']['title']}")
        print(f"Secciones: {len(result['parsed']['sections'])}")
        print(f"Hallazgos: {len(result['parsed']['key_findings'])}")
        if result["note_path"]:
            print(f"Guardado: {result['note_path']}")
        print(f"\n--- Preview ---\n{result['note_content'][:500]}")
    else:
        print(f"❌ Error: {result['error']}")
