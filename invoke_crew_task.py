#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
invoke_crew_task — Skill de Hermes para invocar micro-tripulaciones de CrewAI.

Cuando Hermes detecta una tarea masiva, lineal o aburrida que puede delegar,
usa esta skill para crear una micro-tripulación temporal de CrewAI que trabaja
en un contenedor Docker aislado.

Flujo:
    1. Hermes llama invoke_crew_task() con la tarea y los roles
    2. Se genera un script Python temporal con la estructura CrewAI
    3. Se ejecuta en un contenedor Docker aislado (sin red, con límites de recursos)
    4. El output pasa por Agent Fixer Stage (security gateway)
    5. Hermes recibe el resultado limpio

Uso:
    result = invoke_crew_task(
        task="Investigar los 22 nichos del mapa de Obsidian",
        crew=[
            {"role": "Investigador", "goal": "Buscar información sobre cada nicho", "tools": ["web_search", "web_scrape"]},
            {"role": "Redactor", "goal": "Escribir resumen ejecutivo de cada nicho", "tools": ["write_file"]}
        ],
        scope="Análisis de nichos de seguridad de agentes de IA",
        output_dir="/tmp/crew_output"
    )
"""

import json
import tempfile
import subprocess
import os
import shutil
from pathlib import Path
from datetime import datetime


# ────────────────────────────────────────────────────────────────────────────
# Template del script CrewAI
# ────────────────────────────────────────────────────────────────────────────

CREW_SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
"""Auto-generated crew script — {timestamp}"""
import sys
import os

# Añadir output dir al path
sys.path.insert(0, "/output")

from crewai import Agent, Task, Crew

# ── Agents ──────────────────────────────────────────────────────────────────

{agents_def}

# ── Tasks ───────────────────────────────────────────────────────────────────

{tasks_def}

# ── Crew ────────────────────────────────────────────────────────────────────

crew = Crew(
    agents=[{agents_list}],
    tasks=[{tasks_list}],
    verbose=False
)

# ── Execute ─────────────────────────────────────────────────────────────────

result = crew.kickoff()

# ── Write output ────────────────────────────────────────────────────────────

output_path = "/output/result.md"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(str(result))

print(f"[CREW] Output written to {{output_path}}")
print(f"[CREW] Result length: {{len(str(result))}} chars")
'''


# ────────────────────────────────────────────────────────────────────────────
# Función principal
# ────────────────────────────────────────────────────────────────────────────

def invoke_crew_task(
    task: str,
    crew: list,
    scope: str,
    output_dir: str = None,
    timeout: int = 300,
    cleanup: bool = True,
) -> dict:
    """
    Invoca una micro-tripulación de CrewAI en un contenedor Docker aislado.

    Args:
        task: Descripción de la tarea principal
        crew: Lista de dicts con role, goal, tools para cada agente
        scope: Scope original (para el Agent Fixer Stage)
        output_dir: Directorio de output (default: /tmp/crew_output_{pid})
        timeout: Timeout en segundos (default: 300)
        cleanup: Si True, elimina archivos temporales al terminar

    Returns:
        dict con:
            - status: "success" | "error" | "timeout"
            - raw_output: texto del output de CrewAI
            - security: resultado del Agent Fixer Stage
            - output_file: path al archivo de output
            - duration_seconds: tiempo de ejecución
            - crew_size: número de agentes
    """
    start_time = datetime.now()

    # 1. Preparar directorio de output
    if output_dir is None:
        output_dir = f"/tmp/crew_output_{os.getpid()}"
    os.makedirs(output_dir, exist_ok=True)

    # 2. Generar definiciones de agentes y tareas
    agents_def = []
    tasks_def = []
    agents_list = []
    tasks_list = []

    for i, member in enumerate(crew):
        role = member["role"]
        goal = member["goal"]
        tools = member.get("tools", [])
        backstory = member.get("backstory", f"Expert {role}")

        agents_def.append(f'''
agent_{i} = Agent(
    role="{role}",
    goal="{goal}",
    backstory="{backstory}",
    tools={tools},
    verbose=False,
    allow_delegation=False
)''')
        agents_list.append(f"agent_{i}")

        tasks_def.append(f'''
task_{i} = Task(
    description="{goal}",
    agent=agent_{i},
    expected_output="Detailed and accurate result"
)''')
        tasks_list.append(f"task_{i}")

    # 3. Generar script de CrewAI
    timestamp = datetime.now().isoformat()
    script = CREW_SCRIPT_TEMPLATE.format(
        timestamp=timestamp,
        agents_def="\n".join(agents_def),
        tasks_def="\n".join(tasks_def),
        agents_list=", ".join(agents_list),
        tasks_list=", ".join(tasks_list),
    )

    # 4. Escribir script temporal
    script_path = f"/tmp/crew_{os.getpid()}.py"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    # 5. Verificar que Docker está disponible
    docker_check = subprocess.run(
        ["docker", "info"],
        capture_output=True, text=True, timeout=10
    )
    if docker_check.returncode != 0:
        return {
            "status": "error",
            "error": "Docker is not available",
            "raw_output": "",
            "security": None,
            "output_file": None,
            "duration_seconds": 0,
            "crew_size": len(crew),
        }

    # 6. Ejecutar en contenedor Docker
    container_name = f"crew_{os.getpid()}"

    docker_result = subprocess.run(
        [
            "docker", "run", "--rm",
            "--name", container_name,
            "-v", f"{script_path}:/crew.py:ro",
            "-v", f"{output_dir}:/output",
            "--network", "none",
            "--memory", "512m",
            "--cpus", "1.0",
            "--read-only",
            "hermes-crew:latest",
            "python", "/crew.py"
        ],
        capture_output=True, text=True, timeout=timeout
    )

    duration = (datetime.now() - start_time).total_seconds()

    # 7. Leer output
    output_file = Path(output_dir) / "result.md"
    if output_file.exists():
        raw_output = output_file.read_text(encoding="utf-8")
    else:
        raw_output = docker_result.stdout + "\n" + docker_result.stderr

    # 8. Pasar por Agent Fixer Stage (security gateway)
    security_result = None
    try:
        # Importar desde el path del proyecto
        import sys
        fixer_path = "/home/sil/agent-fixer-stage"
        if fixer_path not in sys.path:
            sys.path.insert(0, fixer_path)
        from agent_fixer import AgentFixer

        fixer = AgentFixer(scope=scope, action="clean", mode="medium")
        fixer_result = fixer.check(raw_output)

        security_result = {
            "status": fixer_result.status.value,
            "score": fixer_result.score,
            "reason": fixer_result.reason,
            "cleaned_output": fixer_result.cleaned_output,
            "layer": fixer_result.layer,
            "details": fixer_result.details,
        }
    except Exception as e:
        security_result = {
            "status": "error",
            "error": str(e),
            "score": 0.0,
            "reason": f"Fixer Stage failed: {e}",
            "cleaned_output": raw_output,
            "layer": "none",
            "details": {},
        }

    # 9. Limpieza
    if cleanup:
        try:
            os.remove(script_path)
        except OSError:
            pass

    # 10. Determinar status final
    if docker_result.returncode == 0:
        status = "security_result" in security_result and security_result.get("status") != "error"
        final_status = "success" if status else "security_flagged"
    else:
        final_status = "error"

    return {
        "status": final_status,
        "raw_output": raw_output,
        "security": security_result,
        "output_file": str(output_file) if output_file.exists() else None,
        "duration_seconds": round(duration, 2),
        "crew_size": len(crew),
        "docker_exit_code": docker_result.returncode,
        "container_name": container_name,
    }


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Invoke a micro-crew of CrewAI in an isolated Docker container"
    )
    parser.add_argument("--task", required=True, help="Main task description")
    parser.add_argument("--crew", required=True, help="JSON array of crew members")
    parser.add_argument("--scope", default="", help="Scope for Agent Fixer Stage")
    parser.add_argument("--output-dir", default=None, help="Output directory")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    crew = json.loads(args.crew)

    result = invoke_crew_task(
        task=args.task,
        crew=crew,
        scope=args.scope,
        output_dir=args.output_dir,
        timeout=args.timeout,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Status: {result['status']}")
        print(f"Duration: {result['duration_seconds']}s")
        print(f"Crew size: {result['crew_size']}")
        if result['security']:
            print(f"Security: {result['security']['status']} (score: {result['security']['score']:.2f})")
        if result['output_file']:
            print(f"Output: {result['output_file']}")
        print(f"\n--- Output ---\n{result['raw_output'][:500]}")
