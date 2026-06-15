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

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "batiai/gemma4-e2b:q4")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Formato LiteLLM: ollama/model_name, openai/model_name, anthropic/model_name, etc.
LITELLM_MODEL = os.getenv("LITELLM_MODEL", f"ollama/{OLLAMA_MODEL}")

# Force unbuffered output
os.environ["PYTHONUNBUFFERED"] = "1"

from crewai import Agent, Task, Crew, LLM

# ── LLM Configuration ───────────────────────────────────────────────────────

local_llm = LLM(model=LITELLM_MODEL, base_url=OLLAMA_BASE_URL)

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
    # Leetspeak / obfuscated variants
    "p@ssw0rd", "p@ssword", "passw0rd", "p@55w0rd",
    "secret", "s3cret", "s3cr3t", "@pi_key", "api_k3y",
    "3x3cut3", "3x3c", "ex3cute",
    "1gn0r3", "ign0r3", "ignor3", "1nstruct10n", "1nstruct1on",
    "cur1", "wget", "rm -rf",
    "byp@ss", "byp4ss", "bypass",
    "0v3rr1d3", "ov3rr1d3", "override",
]

def _normalize_for_scanning(text: str) -> str:
    """Normaliza texto para el quick scan — convierte leetspeak a ASCII."""
    # Leetspeak → ASCII mapping (subset of full homoglyph map)
    leet_map = str.maketrans({
        '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's',
        '6': 'g', '7': 't', '8': 'b', '9': 'q',
        '@': 'a', '$': 's', '!': 'i', '|': 'l', '+': 't',
        # Cirílico lookalike
        'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c',
        'х': 'x', 'у': 'y', 'і': 'i',
    })
    # Aplicar normalización + lowercase
    return text.translate(leet_map).lower()

# Quick pre-scan for obvious threats
found_threats = []
scan_text = _normalize_for_scanning(git_diff_content)
for pattern in DANGEROUS_PATTERNS:
    if pattern.lower() in scan_text:
        found_threats.append(pattern)

quick_scan_note = ""
if found_threats:
    quick_scan_note = f"\n\n[QUICK SCAN DETECTED: {', '.join(found_threats)}]"
else:
    quick_scan_note = "\n\n[QUICK SCAN: No dangerous patterns detected]"

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
    description=f"""Revisa el informe de riesgos anterior Y el resultado del quick scan. Emite una decisión final.

{quick_scan_note}

REGLAS OBLIGATORIAS (NO NEGOCIABLES):
- Si el quick scan detectó CUALQUIER patrón peligroso: VERDICT: FAIL
- Si el quick scan NO detectó patrones Y el informe no encontró riesgos: VERDICT: PASS
- Si el quick scan NO detectó patrones PERO el informe encontró riesgos: VERDICT: FAIL

El quick scan es la fuente de verdad principal. Si detectó patrones, el veredicto DEBE ser FAIL sin importar lo que diga el informe de análisis.

Tu respuesta DEBE empezar con exactamente una de estas líneas:
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
