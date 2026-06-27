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
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


# ────────────────────────────────────────────────────────────────────────────
# Configuración del modelo Ollama
# ────────────────────────────────────────────────────────────────────────────

_env_file: Path = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _value = _line.split("=", 1)
            os.environ.setdefault(_key.strip(), _value.strip())

OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "batiai/gemma4-e2b:q4")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LITELLM_MODEL: str = os.getenv("LITELLM_MODEL", f"ollama/{OLLAMA_MODEL}")
HERMES_CREW_VENV: str = os.getenv("HERMES_CREW_VENV", "/home/sil/mcp-core-defense/venv/bin/python3")

# Mapeo de nombres de herramientas a clases CrewAI
TOOL_CLASS_MAP: dict[str, str] = {
    "web_search": "WebSearchTool",
    "file_read": "FileReadTool",
    "file_write": "FileWriteTool",
    "obsidian_search": "ObsidianSearchTool",
    "obsidian_read": "ObsidianReadTool",
}


# ────────────────────────────────────────────────────────────────────────────
# Template del script CrewAI
# ────────────────────────────────────────────────────────────────────────────

CREW_SCRIPT_TEMPLATE: str = '''#!/usr/bin/env python3
"""Auto-generated crew script — {timestamp}"""
import os
import sys
sys.path.insert(0, "/output")

# Configure Ollama
os.environ["OPENAI_API_BASE"] = "{ollama_base_url}/v1"
os.environ["OPENAI_API_KEY"] = "ollama"

from crewai import Agent, Task, Crew, LLM

# Create LLM — supports both Ollama direct and LiteLLM
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

def _check_ram_available() -> bool:
    """Verifica si hay al menos 2GB de RAM disponible."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if "MemAvailable" in line:
                    return int(line.split()[1]) > 2_000_000
    except Exception:
        pass
    return True


def _check_docker_available() -> bool:
    """Verifica si Docker está disponible y la imagen existe."""
    try:
        dc = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        if dc.returncode == 0:
            img = subprocess.run(
                ["docker", "images", "-q", "hermes-crew:latest"],
                capture_output=True, text=True, timeout=5,
            )
            return img.stdout.strip() != ""
    except Exception:
        pass
    return False


def _check_venv_available() -> bool:
    """Verifica si CrewAI está instalado en el venv local."""
    try:
        vp = HERMES_CREW_VENV
        if Path(vp).exists():
            ck = subprocess.run(
                [vp, "-c", "import crewai; print('ok')"],
                capture_output=True, text=True, timeout=10,
            )
            return ck.returncode == 0
    except Exception:
        pass
    return False


def _check_repo_is_shared(repo_path: Optional[str]) -> bool:
    """Verifica si el repo tiene remotos (repo compartido -> Docker)."""
    if not repo_path or not Path(repo_path).exists():
        return False
    try:
        remotes = subprocess.run(
            ["git", "-C", repo_path, "remote", "-v"],
            capture_output=True, text=True, timeout=3,
        )
        return len(remotes.stdout.strip().split("\n")) > 0
    except Exception:
        return False


def _determine_execution_mode(preferred: str, repo_path: Optional[str] = None) -> str:
    """
    Determina el modo de ejecución basado en recursos y contexto.

    Returns: "venv" o "docker"
    """
    if preferred in ("venv", "docker"):
        return preferred

    ram_ok = _check_ram_available()
    docker_ok = _check_docker_available()
    venv_ok = _check_venv_available()
    repo_shared = _check_repo_is_shared(repo_path)

    if repo_shared and docker_ok:
        return "docker"
    if docker_ok and ram_ok:
        return "docker"
    if venv_ok:
        return "venv"
    if docker_ok:
        return "docker"
    return "venv"


# ────────────────────────────────────────────────────────────────────────────
# Ejecución
# ────────────────────────────────────────────────────────────────────────────

def _execute_in_venv(script_path: str, output_dir: str, timeout: int) -> dict:
    """Ejecuta el script de CrewAI en el venv local con output sin buffer."""
    from path_validator import validate_path
    safe_script = validate_path(script_path, must_exist=True)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    result = subprocess.run(
        [HERMES_CREW_VENV, "-u", str(safe_script)],
        capture_output=True, text=True, timeout=timeout,
        cwd=output_dir, env=env,
    )
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _execute_in_docker(script_path: str, output_dir: str, timeout: int) -> dict:
    """Ejecuta el script de CrewAI en un contenedor Docker aislado."""
    result = subprocess.run(
        ["docker", "run", "--rm", "--name", f"crew_{os.getpid()}",
         "-v", f"{script_path}:/crew.py:ro", "-v", f"{output_dir}:/output",
         "--network", "none", "--memory", "512m", "--cpus", "1.0", "--read-only",
         "hermes-crew:latest", "python", "/crew.py"],
        capture_output=True, text=True, timeout=timeout,
    )
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _run_crew_script(script_path: str, output_dir: str, timeout: int, mode: str) -> dict:
    """Ejecuta el script en el modo seleccionado."""
    if mode == "docker":
        return _execute_in_docker(script_path, output_dir, timeout)
    return _execute_in_venv(script_path, output_dir, timeout)


# ────────────────────────────────────────────────────────────────────────────
# Preparación del script CrewAI
# ────────────────────────────────────────────────────────────────────────────

def _audit_tools(crew: list[dict]) -> Optional[dict]:
    """Audita las herramientas del crew con MCP Core Defense."""
    try:
        from mcp_tool_auditor import MCPToolAuditor
        auditor = MCPToolAuditor(sensitivity="medium")

        all_tools: list[dict] = []
        for member in crew:
            for tool in member.get("tools", []):
                if isinstance(tool, str):
                    all_tools.append({"name": tool, "description": ""})
                elif isinstance(tool, dict):
                    all_tools.append(tool)

        if not all_tools:
            return None

        audit_result = auditor.audit_tools_list(all_tools)
        if not audit_result["all_safe"]:
            print(f"[MCP AUDIT] {audit_result['tools_rejected']} tools rejected!")
            for r in audit_result["results"]:
                if not r["safe"]:
                    print(f"  ✗ {r['tool_name']}: {r['reason']}")
        return audit_result
    except Exception as e:
        print(f"[MCP AUDIT] Error: {e}")
        return None


def _collect_tool_imports(crew: list[dict]) -> str:
    """Genera las líneas de import de herramientas CrewAI."""
    all_tool_classes: set[str] = set()
    for member in crew:
        for tool in member.get("tools", []):
            if isinstance(tool, str) and tool in TOOL_CLASS_MAP:
                all_tool_classes.add(TOOL_CLASS_MAP[tool])

    if all_tool_classes:
        return "from crewai_tools import " + ", ".join(sorted(all_tool_classes))
    return "# No tools imported"


def _build_agent_definitions(crew: list[dict]) -> tuple[list[str], list[str], list[str], list[str]]:
    """
    Genera las definiciones de agentes y tareas para el script.

    Returns: (agents_def, tasks_def, agents_list, tasks_list)
    """
    agents_def: list[str] = []
    tasks_def: list[str] = []
    agents_list: list[str] = []
    tasks_list: list[str] = []

    for i, member in enumerate(crew):
        role: str = member["role"]
        goal: str = member["goal"]
        tools = member.get("tools", [])
        backstory: str = member.get("backstory", f"Expert {role}")

        tool_instances: list[str] = []
        for tool in tools:
            if isinstance(tool, str) and tool in TOOL_CLASS_MAP:
                tool_instances.append(f"{TOOL_CLASS_MAP[tool]}()")
            elif isinstance(tool, dict):
                tool_instances.append(f"{tool.get('name', 'unknown')}()")

        tools_str = "[" + ", ".join(tool_instances) + "]" if tool_instances else "[]"

        agents_def.append(
            f'agent_{i} = Agent(role="{role}", goal="{goal}", '
            f'backstory="{backstory}", tools={tools_str}, '
            f'verbose=False, allow_delegation=False, llm=llm)'
        )
        agents_list.append(f"agent_{i}")
        tasks_def.append(
            f'task_{i} = Task(description="{goal}", '
            f'agent=agent_{i}, expected_output="Detailed result")'
        )
        tasks_list.append(f"task_{i}")

    return agents_def, tasks_def, agents_list, tasks_list


def _generate_crew_script(crew: list[dict], output_dir: str) -> str:
    """Genera el script Python completo de CrewAI."""
    agents_def, tasks_def, agents_list, tasks_list = _build_agent_definitions(crew)
    tools_import = _collect_tool_imports(crew)

    return CREW_SCRIPT_TEMPLATE.format(
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


# ────────────────────────────────────────────────────────────────────────────
# Post-procesado: lectura de output + seguridad
# ────────────────────────────────────────────────────────────────────────────

def _read_crew_output(output_dir: str, exec_result: dict) -> str:
    """Lee el output del crew, validando paths ante traversal (S8707)."""
    from path_validator import validate_path

    output_file = Path(output_dir) / "result.md"
    if output_file.exists():
        validated = validate_path(str(output_file), base_dir=output_dir)
        return validated.read_text(encoding="utf-8")

    return exec_result.get("stdout", "") + "\n" + exec_result.get("stderr", "")


def _apply_security_check(raw_output: str, scope: str) -> dict:
    """Pasa el output por Agent Fixer Stage para detección de inyecciones."""
    try:
        _fixer_path = os.getenv("AGENT_FIXER_PATH", "/home/sil/agent-fixer-stage")
        if _fixer_path not in sys.path:
            sys.path.insert(0, _fixer_path)
        from agent_fixer import AgentFixer

        fixer = AgentFixer(scope=scope, action="clean", mode="medium")
        fixer_result = fixer.check(raw_output)
        return {
            "status": fixer_result.status.value,
            "score": fixer_result.score,
            "reason": fixer_result.reason,
            "cleaned_output": fixer_result.cleaned_output,
            "layer": fixer_result.layer,
            "details": fixer_result.details,
        }
    except Exception as e:
        return {
            "status": "error", "error": str(e), "score": 0.0,
            "reason": str(e), "cleaned_output": raw_output,
            "layer": "none", "details": {},
        }


# ────────────────────────────────────────────────────────────────────────────
# Función principal (orquestador limpio)
# ────────────────────────────────────────────────────────────────────────────

def invoke_crew_task(
    task: str,
    crew: list[dict],
    scope: str,
    output_dir: Optional[str] = None,
    timeout: int = 300,
    cleanup: bool = True,
    mode: str = "auto",
    repo_path: Optional[str] = None,
) -> dict:
    """
    Invoca una micro-tripulación de CrewAI.

    Args:
        task: Descripción de la tarea principal
        crew: Lista de dicts con role, goal, tools para cada agente
        scope: Scope original (para el Agent Fixer Stage)
        output_dir: Directorio de output (default: seguro bajo XDG)
        timeout: Timeout en segundos (default: 300)
        cleanup: Si True, elimina archivos temporales
        mode: "auto", "venv", "docker"
        repo_path: Path al repo Git (para detectar si es compartido)

    Returns:
        dict con status, execution_mode, raw_output, security, output_file,
        duration_seconds, crew_size
    """
    from path_validator import validate_path, get_safe_output_dir, get_safe_script_path

    start_time = datetime.now()

    # 1. Preparar directorio de output seguro
    if output_dir is None:
        output_dir = get_safe_output_dir()
    else:
        output_dir = str(validate_path(output_dir))
    os.makedirs(output_dir, exist_ok=True)

    # 2. Auditar herramientas con MCP Core Defense
    mcp_audit_result = _audit_tools(crew)

    # 3. Generar script CrewAI
    script = _generate_crew_script(crew, output_dir)
    script_path = get_safe_script_path()
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    # 4. Determinar modo y ejecutar
    effective_repo_path = repo_path or os.getcwd()
    execution_mode = _determine_execution_mode(mode, repo_path=effective_repo_path)
    print(f"[CREW] Mode: {execution_mode}, Model: {OLLAMA_MODEL}, Repo: {effective_repo_path}")

    exec_result = _run_crew_script(script_path, output_dir, timeout, execution_mode)
    duration = (datetime.now() - start_time).total_seconds()

    # 5. Leer output
    raw_output = _read_crew_output(output_dir, exec_result)

    # 6. Security check (Agent Fixer Stage)
    security_result = _apply_security_check(raw_output, scope)

    # 7. Limpieza
    if cleanup:
        try:
            os.remove(script_path)
        except OSError:
            pass

    output_file = Path(output_dir) / "result.md"
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
        status = result['status']
        exec_mode = result['execution_mode']
        dur = result['duration_seconds']
        print(f"Status: {status} | Mode: {exec_mode} | Duration: {dur}s")
        if result['security']:
            sec_status = result['security']['status']
            sec_score = result['security']['score']
            print(f"Security: {sec_status} (score: {sec_score:.2f})")
        print(f"\n{result['raw_output'][:500]}")
