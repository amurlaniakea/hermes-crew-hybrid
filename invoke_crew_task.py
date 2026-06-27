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

Configuración LLM: Ollama local (modelo configurable)
"""

import json
import subprocess
import os
from pathlib import Path
from datetime import datetime


# ────────────────────────────────────────────────────────────────────────────
# Configuración del modelo Ollama
# ────────────────────────────────────────────────────────────────────────────
# Lee de .env si existe, sino usa defaults
from pathlib import Path

_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "batiai/gemma4-e2b:q4")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Formato LiteLLM: ollama/model_name, openai/model_name, anthropic/model_name, etc.
# El operador puede usar cualquier proveedor soportado por LiteLLM
LITELLM_MODEL = os.getenv("LITELLM_MODEL", f"ollama/{OLLAMA_MODEL}")

# Paths dinámicos — desde variables de entorno (portability)
HERMES_CREW_VENV = os.getenv("HERMES_CREW_VENV", "/home/sil/mcp-core-defense/venv/bin/python3")


# ────────────────────────────────────────────────────────────────────────────
# Template del script CrewAI
# ────────────────────────────────────────────────────────────────────────────

CREW_SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
"""Auto-generated crew script — {timestamp}"""
import os
import sys
sys.path.insert(0, "/output")

# Configure Ollama
os.environ["OPENAI_API_BASE"] = "{ollama_base_url}/v1"
os.environ["OPENAI_API_KEY"] = "ollama"

from crewai import Agent, Task, Crew, LLM

# Create LLM — supports both Ollama direct and LiteLLM
# Model format: ollama/model_name (CrewAI uses LiteLLM internally)
llm = LLM(model="{litellm_model}", base_url="{ollama_base_url}")

# Import tools if needed
{tools_import}

# ── Agents ──────────────────────────────────────────────────────────────────

{agents_def}

# ── Tasks ───────────────────────────────────────────────────────────────────

{tasks_def}

# ── Crew ────────────────────────────────────────────────────────────────────

crew = Crew(agents=[{agents_list}], tasks=[{tasks_list}], verbose=False)

# ── Execute ─────────────────────────────────────────────────────────────────

result = crew.kickoff()

# ── Write output ────────────────────────────────────────────────────────────

output_path = "{output_dir}/result.md"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(str(result))

print("[CREW] Done. Output written to " + output_path)
'''


# ────────────────────────────────────────────────────────────────────────────
# Selección de modo de ejecución
# ────────────────────────────────────────────────────────────────────────────

def _determine_execution_mode(preferred: str, repo_path: str = None) -> str:
    """
    Determina el modo de ejecución basado en recursos y contexto.
    
    Lógica:
    1. Si mode es "venv" o "docker" explícitamente → usar ese
    2. Si mode es "auto":
       a. Verificar RAM disponible (mínimo 2GB para Docker)
       b. Verificar si Docker está disponible y la imagen existe
       c. Verificar si CrewAI está instalado en venv
       d. Si el repo tiene remotos compartidos → Docker (seguro)
       e. Si el repo es local/personal → venv (rápido)
       f. Fallback: venv
    """
    if preferred in ("venv", "docker"):
        return preferred
    
    # Check RAM
    ram_ok = True
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if "MemAvailable" in line:
                    ram_ok = int(line.split()[1]) > 2_000_000
                    break
    except Exception:
        pass
    
    # Check Docker
    docker_ok = False
    try:
        dc = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        if dc.returncode == 0:
            img = subprocess.run(["docker", "images", "-q", "hermes-crew:latest"], capture_output=True, text=True, timeout=5)
            docker_ok = img.stdout.strip() != ""
    except Exception:
        pass
    
    # Check venv
    venv_ok = False
    try:
        vp = HERMES_CREW_VENV
        if Path(vp).exists():
            ck = subprocess.run([vp, "-c", "import crewai; print('ok')"], capture_output=True, text=True, timeout=10)
            venv_ok = ck.returncode == 0
    except Exception:
        pass
    
    # Check if repo has shared remotes (collaborative repo → Docker for safety)
    repo_is_shared = False
    if repo_path and Path(repo_path).exists():
        try:
            remotes = subprocess.run(
                ["git", "-C", repo_path, "remote", "-v"],
                capture_output=True, text=True, timeout=3  # Timeout corto
            )
            # If repo has remotes (origin, upstream, etc.), it's shared
            repo_is_shared = len(remotes.stdout.strip().split("\n")) > 0
        except subprocess.TimeoutExpired:
            pass  # Si tarda mucho, asumir que no es compartido
        except Exception:
            pass
    
    # Decision
    if repo_is_shared and docker_ok:
        return "docker"  # Shared repo → maximum isolation
    elif docker_ok and ram_ok:
        return "docker"  # Docker available and enough RAM
    elif venv_ok:
        return "venv"  # Fallback to venv
    elif docker_ok:
        return "docker"  # Docker available but low RAM
    else:
        return "venv"  # Last resort


def _execute_in_venv(script_path: str, output_dir: str, timeout: int) -> dict:
    """Ejecuta el script de CrewAI en el venv local con output sin buffer."""
    from path_validator import validate_path
    safe_script = validate_path(script_path, must_exist=True)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    result = subprocess.run(
        [HERMES_CREW_VENV, "-u", str(safe_script)],
        capture_output=True, text=True, timeout=timeout,
        cwd=output_dir, env=env
    )
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _execute_in_docker(script_path: str, output_dir: str, timeout: int) -> dict:
    """Ejecuta el script de CrewAI en un contenedor Docker aislado."""
    result = subprocess.run(
        ["docker", "run", "--rm", "--name", f"crew_{os.getpid()}",
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
    repo_path: str = None,
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
        repo_path: Path al repo Git (para detectar si es compartido)
    
    Returns:
        dict con status, execution_mode, raw_output, security, output_file, duration_seconds, crew_size
    """
    start_time = datetime.now()
    
    # ── Usar directorio seguro en vez de /tmp (S5443 + S8707) ──
    from path_validator import validate_path, get_safe_output_dir, get_safe_script_path
    if output_dir is None:
        output_dir = get_safe_output_dir()
    else:
        output_dir = str(validate_path(output_dir))
    os.makedirs(output_dir, exist_ok=True)
    
    # ── MCP Core Defense: Auditar herramientas antes de ejecutar ──────────────
    mcp_audit_result = None
    try:
        from mcp_tool_auditor import MCPToolAuditor
        auditor = MCPToolAuditor(sensitivity="medium")
        
        # Recolectar todas las herramientas del crew
        all_tools = []
        for member in crew:
            tools = member.get("tools", [])
            for tool in tools:
                if isinstance(tool, str):
                    all_tools.append({"name": tool, "description": ""})
                elif isinstance(tool, dict):
                    all_tools.append(tool)
        
        if all_tools:
            mcp_audit_result = auditor.audit_tools_list(all_tools)
            if not mcp_audit_result["all_safe"]:
                print(f"[MCP AUDIT] {mcp_audit_result['tools_rejected']} tools rejected!")
                for r in mcp_audit_result["results"]:
                    if not r["safe"]:
                        print(f"  ✗ {r['tool_name']}: {r['reason']}")
    except Exception as e:
        print(f"[MCP AUDIT] Error: {e}")
    
    # Generar script CrewAI con el LLM embebido y herramientas reales
    agents_def, tasks_def, agents_list, tools_import_lines, tasks_list = [], [], [], [], []
    
    # Mapeo de nombres de herramientas a clases
    tool_class_map = {
        "web_search": "WebSearchTool",
        "file_read": "FileReadTool", 
        "file_write": "FileWriteTool",
        "obsidian_search": "ObsidianSearchTool",
        "obsidian_read": "ObsidianReadTool",
    }
    
    # Generar imports de herramientas usadas
    all_tool_classes = set()
    for member in crew:
        for tool in member.get("tools", []):
            if isinstance(tool, str) and tool in tool_class_map:
                all_tool_classes.add(tool_class_map[tool])
    
    if all_tool_classes:
        tools_import_lines.append("from crewai_tools import " + ", ".join(sorted(all_tool_classes)))
    else:
        tools_import_lines.append("# No tools imported")
    
    tools_import = "\n".join(tools_import_lines)
    
    # Generar agentes con herramientas instanciadas
    for i, member in enumerate(crew):
        role = member["role"]
        goal = member["goal"]
        tools = member.get("tools", [])
        backstory = member.get("backstory", f"Expert {role}")
        
        # Generar lista de herramientas instanciadas
        tool_instances = []
        for tool in tools:
            if isinstance(tool, str) and tool in tool_class_map:
                tool_instances.append(f"{tool_class_map[tool]}()")
            elif isinstance(tool, dict):
                # Herramienta personalizada
                tool_name = tool.get("name", "unknown")
                tool_instances.append(f"{tool_name}()")
        
        tools_str = "[" + ", ".join(tool_instances) + "]" if tool_instances else "[]"
        
        agents_def.append(f'agent_{i} = Agent(role="{role}", goal="{goal}", backstory="{backstory}", tools={tools_str}, verbose=False, allow_delegation=False, llm=llm)')
        agents_list.append(f"agent_{i}")
        tasks_def.append(f'task_{i} = Task(description="{goal}", agent=agent_{i}, expected_output="Detailed result")')
        tasks_list.append(f"task_{i}")
    
    script = CREW_SCRIPT_TEMPLATE.format(
        timestamp=datetime.now().isoformat(),
        ollama_model=OLLAMA_MODEL,
        ollama_base_url=OLLAMA_BASE_URL,
        litellm_model=LITELLM_MODEL,
        output_dir=output_dir,
        tools_import=tools_import,
        agents_def="\n".join(agents_def),
        tasks_def="\n".join(tasks_def),
        agents_list=", ".join(agents_list),
        tasks_list=", ".join(tasks_list),
    )
    
    script_path = get_safe_script_path()
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    
    # Determinar modo y ejecutar
    effective_repo_path = repo_path or os.getcwd()
    execution_mode = _determine_execution_mode(mode, repo_path=effective_repo_path)
    print(f"[CREW] Mode: {execution_mode}, Model: {OLLAMA_MODEL}, Repo: {effective_repo_path}")
    
    if execution_mode == "docker":
        exec_result = _execute_in_docker(script_path, output_dir, timeout)
    else:
        exec_result = _execute_in_venv(script_path, output_dir, timeout)
    
    duration = (datetime.now() - start_time).total_seconds()
    
    # Leer output — validar path antes de acceder (S8707)
    output_file = Path(output_dir) / "result.md"
    raw_output = ""
    if output_file.exists():
        validated_output = validate_path(str(output_file), base_dir=output_dir)
        raw_output = validated_output.read_text(encoding="utf-8")
    else:
        raw_output = exec_result.get("stdout", "") + "\n" + exec_result.get("stderr", "")
    
    # Pasar por Agent Fixer Stage
    security_result = None
    try:
        import sys as _sys
        _fixer_path = os.getenv("AGENT_FIXER_PATH", "/home/sil/agent-fixer-stage")
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
        try:
            os.remove(script_path)
        except OSError:
            pass
    
    return {
        "status": "success" if exec_result.get("returncode", 0) == 0 else "error",
        "execution_mode": execution_mode,
        "mcp_audit": mcp_audit_result,
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
