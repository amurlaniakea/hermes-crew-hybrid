#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
invoke_crew_task — Skill de Hermes para invocar micro-tripulaciones de CrewAI.

Soporta dos modos de ejecución:
- "venv": ejecuta en el venv local (rápido, menos aislamiento)
- "docker": ejecuta en contenedor Docker aislado (más seguro, más lento)
- "auto": elige automáticamente basado en recursos disponibles

Flujo:
    1. Hermes llama invoke_crew_task() con la tarea y los roles
    2. Se genera un script Python temporal con la estructura CrewAI
    3. Se ejecuta en venv local O Docker (según mode)
    4. El output pasa por Agent Fixer Stage (security gateway)
    5. Hermes recibe el resultado limpio
"""

import json
import subprocess
import os
from pathlib import Path
from datetime import datetime


# ────────────────────────────────────────────────────────────────────────────
# Template del script CrewAI
# ────────────────────────────────────────────────────────────────────────────

CREW_SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
"""Auto-generated crew script — {timestamp}"""
import sys
sys.path.insert(0, "/output")

from crewai import Agent, Task, Crew

{agents_def}

{tasks_def}

crew = Crew(
    agents=[{agents_list}],
    tasks=[{tasks_list}],
    verbose=False
)

result = crew.kickoff()

output_path = "/output/result.md"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(str(result))

print(f"[CREW] Output written to {{output_path}}")
print(f"[CREW] Result length: {{len(str(result))}} chars")
'''


# ────────────────────────────────────────────────────────────────────────────
# Selección de modo de ejecución
# ────────────────────────────────────────────────────────────────────────────

def _determine_execution_mode(preferred: str) -> str:
    """Determina el modo de ejecución basado en recursos disponibles."""
    if preferred in ("venv", "docker"):
        return preferred
    
    # Auto-detect
    # 1. Check RAM (need at least 2GB free for Docker)
    ram_ok = True
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if "MemAvailable" in line:
                    available_kb = int(line.split()[1])
                    ram_ok = available_kb > 2_000_000  # 2GB
                    break
    except:
        pass
    
    # 2. Check Docker
    docker_ok = False
    try:
        docker_check = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5
        )
        if docker_check.returncode == 0:
            img_check = subprocess.run(
                ["docker", "images", "-q", "hermes-crew:latest"],
                capture_output=True, text=True, timeout=5
            )
            docker_ok = img_check.stdout.strip() != ""
    except:
        pass
    
    # 3. Check venv
    venv_ok = False
    try:
        venv_python = "/home/sil/mcp-core-defense/venv/bin/python3"
        if Path(venv_python).exists():
            check = subprocess.run(
                [venv_python, "-c", "import crewai; print('ok')"],
                capture_output=True, text=True, timeout=10
            )
            venv_ok = check.returncode == 0
    except:
        pass
    
    # 4. Decisión
    if docker_ok and ram_ok:
        return "docker"
    elif venv_ok:
        return "venv"
    elif docker_ok:
        return "docker"
    else:
        return "venv"


# ────────────────────────────────────────────────────────────────────────────
# Ejecutores
# ────────────────────────────────────────────────────────────────────────────

def _execute_in_venv(script_path: str, output_dir: str, timeout: int) -> dict:
    """Ejecuta el script de CrewAI en el venv local."""
    venv_python = "/home/sil/mcp-core-defense/venv/bin/python3"
    result = subprocess.run(
        [venv_python, script_path],
        capture_output=True, text=True, timeout=timeout,
        cwd=output_dir
    )
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _execute_in_docker(script_path: str, output_dir: str, timeout: int) -> dict:
    """Ejecuta el script de CrewAI en un contenedor Docker aislado."""
    container_name = f"crew_{os.getpid()}"
    result = subprocess.run(
        ["docker", "run", "--rm", "--name", container_name,
         "-v", f"{script_path}:/crew.py:ro", "-v", f"{output_dir}:/output",
         "--network", "none", "--memory", "512m", "--cpus", "1.0", "--read-only",
         "hermes-crew:latest", "python", "/crew.py"],
        capture_output=True, text=True, timeout=timeout
    )
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


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
    mode: str = "auto",
) -> dict:
    """
    Invoca una micro-tripulación de CrewAI.
    
    Args:
        task: Descripción de la tarea principal
        crew: Lista de dicts con role, goal, tools para cada agente
        scope: Scope original (para el Agent Fixer Stage)
        output_dir: Directorio de output (default: /tmp/crew_output_{pid})
        timeout: Timeout en segundos (default: 300)
        cleanup: Si True, elimina archivos temporales
        mode: "auto", "venv", "docker"
    
    Returns:
        dict con status, execution_mode, raw_output, security, output_file, duration_seconds, crew_size
    """
    start_time = datetime.now()
    
    if output_dir is None:
        output_dir = f"/tmp/crew_output_{os.getpid()}"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generar script CrewAI
    agents_def, tasks_def, agents_list, tasks_list = [], [], [], []
    for i, member in enumerate(crew):
        role = member["role"]
        goal = member["goal"]
        tools = member.get("tools", [])
        backstory = member.get("backstory", f"Expert {role}")
        
        agents_def.append(f'agent_{i} = Agent(role="{role}", goal="{goal}", backstory="{backstory}", tools={tools}, verbose=False, allow_delegation=False)')
        agents_list.append(f"agent_{i}")
        tasks_def.append(f'task_{i} = Task(description="{goal}", agent=agent_{i}, expected_output="Detailed result")')
        tasks_list.append(f"task_{i}")
    
    script = CREW_SCRIPT_TEMPLATE.format(
        timestamp=datetime.now().isoformat(),
        agents_def="\n".join(agents_def),
        tasks_def="\n".join(tasks_def),
        agents_list=", ".join(agents_list),
        tasks_list=", ".join(tasks_list),
    )
    
    script_path = f"/tmp/crew_{os.getpid()}.py"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    
    # Determinar modo y ejecutar
    execution_mode = _determine_execution_mode(mode)
    print(f"[CREW] Mode: {execution_mode}")
    
    if execution_mode == "docker":
        exec_result = _execute_in_docker(script_path, output_dir, timeout)
    else:
        exec_result = _execute_in_venv(script_path, output_dir, timeout)
    
    duration = (datetime.now() - start_time).total_seconds()
    
    # Leer output
    output_file = Path(output_dir) / "result.md"
    raw_output = output_file.read_text(encoding="utf-8") if output_file.exists() else exec_result.get("stdout", "") + "\n" + exec_result.get("stderr", "")
    
    # Pasar por Agent Fixer Stage
    security_result = None
    try:
        import sys as _sys
        _fixer_path = "/home/sil/agent-fixer-stage"
        if _fixer_path not in _sys.path:
            _sys.path.insert(0, _fixer_path)
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
        security_result = {"status": "error", "error": str(e), "score": 0.0, "reason": str(e), "cleaned_output": raw_output, "layer": "none", "details": {}}
    
    if cleanup:
        try: os.remove(script_path)
        except: pass
    
    return {
        "status": "success" if exec_result.get("returncode", 0) == 0 else "error",
        "execution_mode": execution_mode,
        "raw_output": raw_output,
        "security": security_result,
        "output_file": str(output_file) if output_file.exists() else None,
        "duration_seconds": round(duration, 2),
        "crew_size": len(crew),
    }


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Invoke a micro-crew of CrewAI")
    parser.add_argument("--task", required=True)
    parser.add_argument("--crew", required=True, help="JSON array")
    parser.add_argument("--scope", default="")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--mode", default="auto", choices=["auto", "venv", "docker"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    result = invoke_crew_task(
        task=args.task,
        crew=json.loads(args.crew),
        scope=args.scope,
        output_dir=args.output_dir,
        timeout=args.timeout,
        mode=args.mode,
    )
    
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Status: {result['status']} | Mode: {result['execution_mode']} | Duration: {result['duration_seconds']}s")
        if result['security']:
            print(f"Security: {result['security']['status']} (score: {result['security']['score']:.2f})")
        print(f"\n{result['raw_output'][:500]}")
