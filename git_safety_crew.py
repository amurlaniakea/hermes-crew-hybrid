#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
git_safety_crew.py — Analiza git diffs con CrewAI + Ollama para detectar
vulnerabilidades de seguridad antes de cada commit.

Uso:
    git diff --cached | python3 git_safety_crew.py

Salida:
    VERDICT: PASS — Código seguro
    VERDICT: FAIL — Riesgos detectados
"""

import sys
import os

from pathlib import Path

# ── Load .env configuration ──────────────────────────────────────────────────
# Allows each user to configure their own Ollama model

_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Force unbuffered output
os.environ["PYTHONUNBUFFERED"] = "1"

from crewai import Agent, Task, Crew, LLM

# ── LLM Configuration ───────────────────────────────────────────────────────

local_llm = LLM(
    model=f"ollama/{OLLAMA_MODEL}",
    base_url=OLLAMA_BASE_URL,
)

# ── Read git diff from stdin ────────────────────────────────────────────────

git_diff_content = sys.stdin.read()

if not git_diff_content.strip():
    print("STATUS: SUCCESS | No hay cambios en el diff para analizar.")
    sys.exit(0)

# ── Security patterns to flag ───────────────────────────────────────────────

DANGEROUS_PATTERNS = [
    "subprocess.call(", "subprocess.run(", "subprocess.Popen(",
    "os.system(", "os.popen(", "os.exec", "os.spawn(",
    "eval(", "exec(", "__import__",
    "pickle.loads(", "yaml.load(", "json.loads(input",
    "password", "secret", "api_key", "apikey", "token",
    "curl ", "wget ", "requests.get(input",
    "rm -rf", "format(user_input", "f\"{user",
    ".execute(", "RAW_QUERY", "text(user_input",
]

# Quick pre-scan for obvious threats
found_threats = []
for pattern in DANGEROUS_PATTERNS:
    if pattern.lower() in git_diff_content.lower():
        found_threats.append(pattern)

if found_threats:
    print(f"⚠️  QUICK SCAN: Patrones peligrosos detectados: {found_threats}")

# ── CrewAI Agents ───────────────────────────────────────────────────────────

diff_analyst = Agent(
    role="Senior Git Diff Analyst",
    goal="Identificar vulnerabilidades de seguridad, tokens expuestos y malas prácticas en el código modificado.",
    backstory="Eres un auditor de código obsesivo. Tu trabajo es leer git diffs y encontrar fallos de seguridad (inyecciones SQL, ejecuciones de shell, credenciales hardcodeadas) antes de que lleguen a producción. Analiza las líneas agregadas (+) y modificadas.",
    llm=local_llm,
    allow_delegation=False,
)

threat_modeler = Agent(
    role="CI/CD Gatekeeper",
    goal="Emitir un veredicto definitivo de PASS o FAIL basado en el análisis del diff.",
    backstory="Eres el responsable último de la seguridad del repositorio. No dejas pasar ningún commit que reduzca la postura de seguridad del software. Eres estricto. Si hay riesgo de severidad Alta o Media, el veredicto es FAIL.",
    llm=local_llm,
    allow_delegation=False,
)

# ── Tasks ───────────────────────────────────────────────────────────────────

task_analyze = Task(
    description=f"""Analiza detalladamente las líneas agregadas (+) en este diff de Git:

{git_diff_content[:2000]}

Busca ESPECÍFICAMENTE estos riesgos de seguridad REALES:
1. Inyección SQL: concatenación de strings en queries SQL (ej: "SELECT * FROM " + user_input)
2. Ejecución de comandos: os.system(), subprocess.call(), eval(), exec() con input del usuario
3. Credenciales hardcodeadas: passwords, API keys, tokens en texto plano
4. XSS: renderizado de HTML sin escapar input del usuario
5. Deserialización insegura: pickle.loads(), yaml.load() sin SafeLoader

NO marques como riesgo:
- Variables normales (name, count, result)
- Funciones matemáticas (add, multiply)
- Strings normales que no sean credenciales
- Código de documentación o markdown

Si el diff es de documentación, markdown o configuración no sensible, considéralo seguro.""",
    expected_output="Un informe conciso con los riesgos REALES encontrados. Si no hay riesgos reales, indicar 'Sin riesgos de seguridad detectados'.",
    agent=diff_analyst,
)

task_verdict = Task(
    description="""Revisa el informe de riesgos anterior. Emite una decisión final estricta.

REGLAS:
- Si hay CUALQUIER riesgo de severidad Alta o Media: VERDICT: FAIL
- Si hay credenciales hardcodeadas: VERDICT: FAIL
- Si hay uso de eval/exec/os.system con input del usuario: VERDICT: FAIL
- Si todo es seguro: VERDICT: PASS

Tu respuesta DEBE contener exactamente una de estas líneas:
VERDICT: PASS
o
VERDICT: FAIL

Seguido de una justificación de máximo 2 líneas.""",
    expected_output="VERDICT: PASS o VERDICT: FAIL con justificación breve.",
    agent=threat_modeler,
)

# ── Execute Crew ────────────────────────────────────────────────────────────

crew = Crew(
    agents=[diff_analyst, threat_modeler],
    tasks=[task_analyze, task_verdict],
    verbose=False,
)

try:
    result = crew.kickoff()
    
    # Output the result for Agent Fixer Stage processing
    if hasattr(result, 'raw'):
        print(result.raw)
    else:
        print(str(result))
    
except Exception as e:
    print(f"ERROR: CrewAI execution failed: {e}")
    print("VERDICT: FAIL | Error en el análisis de seguridad")
    sys.exit(1)
