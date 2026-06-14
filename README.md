# Hermes-Crew Hybrid

> Arquitectura híbrida: Hermes como Director de Orquesta + micro-tripulaciones CrewAI + LiteLLM multi-modelo + 3 capas de seguridad + Code Safety pre-commit hook.

## Visión

```
Hermes (Director Soberano)
    │
    ├── invoke_crew_task() → crea micro-tripulación
    │
    ├── MCP Tool Auditor → audita herramientas (pre-ejecución)
    │
    ├── Ejecución: venv local O Docker aislado
    │       ├── Agente 1: Investigador
    │       ├── Agente 2: Analista
    │       └── Agente 3: Redactor
    │
    ├── Security Gateway (Agent Fixer Stage) → filtra output (<1ms)
    │
    ├── Consolidator → parsea output + genera nota Obsidian
    │
    └── Hermes absorbe resultado limpio

Code Safety Hook (git pre-commit)
    │
    ├── git diff --cached
    ├── Quick scan (pattern matching)
    ├── CrewAI analiza diff (LiteLLM + Ollama local)
    ├── Agent Fixer Stage filtra output
    ├── VERDICT: PASS → commit aprobado + reporte Obsidian
    └── VERDICT: FAIL → commit rechazado + alerta
```

## Características

- **LiteLLM multi-modelo**: Funciona con Ollama local, OpenAI, Anthropic, Gemini, Groq, DeepSeek, etc.
- **Dual mode**: venv local (rápido) o Docker aislado (seguro)
- **Auto-detect**: elige modo basado en RAM y Docker disponible
- **3 capas de seguridad**: MCP Tool Auditor + Agent Fixer Stage + Code Safety Hook
- **Herramientas CrewAI reales**: WebSearchTool, FileReadTool, FileWriteTool, ObsidianSearchTool, ObsidianReadTool
- **Output capture**: PYTHONUNBUFFERED + python -u para captura en tiempo real
- **Obsidian integration**: reportes automáticos en vault de Obsidian
- **Portable**: sin rutas hardcodeadas, configuración vía .env

## Requisitos

- Python 3.10+
- Docker (opcional, para modo Docker)
- Ollama (con modelo local instalado) o API key de cualquier proveedor soportado por LiteLLM
- Dependencias: `pip install crewai crewai-tools langchain litellm`

## Configuración

### 1. Archivo .env

```bash
cp .env.example .env
```

Edita `.env` con tu configuración:

```env
# Modelo Ollama local (REQUERIDO si usas Ollama)
OLLAMA_MODEL=batiai/gemma4-e2b:q4
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_API_KEY=ollama

# LiteLLM Multi-Model (OPCIONAL)
# Permite usar cualquier proveedor de LLM (no solo Ollama)
# Si está vacío, se usa ollama/OLLAMA_MODEL automáticamente
# Ejemplos:
#   LITELLM_MODEL=ollama/qwen2.5:0.5b
#   LITELLM_MODEL=openai/gpt-4o
#   LITELLM_MODEL=anthropic/claude-sonnet-4-20250514
#   LITELLM_MODEL=gemini/gemini-1.5-pro
#   LITELLM_MODEL=groq/llama-3.1-70b-versatile
#LITELLM_MODEL=

# Obsidian Vault Path (OPCIONAL)
# Si no se configura, los reportes se guardan en ./ObsidianNotes
OBSIDIAN_VAULT_PATH=

# Python path (OPCIONAL)
VENV_PYTHON=
```

### 2. Instalar dependencias

```bash
pip install crewai crewai-tools langchain litellm
```

### 3. Instalar pre-commit hook

```bash
cp pre-commit-hook.sh /ruta/al/repo/.git/hooks/pre-commit
chmod +x /ruta/al/repo/.git/hooks/pre-commit
```

## Uso

### Invocar una tripulación

```python
from invoke_crew_task import invoke_crew_task

result = invoke_crew_task(
    task="Investigar las últimas tendencias en seguridad de agentes de IA",
    crew=[
        {"role": "Investigador", "goal": "Buscar información", "tools": ["web_search"]},
        {"role": "Redactor", "goal": "Escribir resumen", "tools": ["file_write"]}
    ],
    scope="Análisis de tendencias",
    mode="venv"  # o "docker" o "auto"
)

print(result["status"])           # "success" | "error"
print(result["execution_mode"])   # "venv" | "docker"
print(result["security"]["status"])  # "pass" | "clean" | "rejected"
print(result["raw_output"])       # Output sanitizado
```

### Consolidar en Obsidian

```python
from consolidate import consolidate_crew_output

consolidated = consolidate_crew_output(
    result,
    tags=["agents", "security", "crewai"],
    save=True
)

print(f"Nota guardada: {consolidated['note_path']}")
```

## Modelos soportados (LiteLLM)

| Proveedor | Formato | Ejemplo |
|-----------|---------|---------|
| Ollama local | `ollama/modelo` | `ollama/batiai/gemma4-e2b:q4` |
| OpenAI | `openai/modelo` | `openai/gpt-4o` |
| Anthropic | `anthropic/modelo` | `anthropic/claude-sonnet-4-20250514` |
| Google | `gemini/modelo` | `gemini/gemini-1.5-pro` |
| Groq | `groq/modelo` | `groq/llama-3.1-70b-versatile` |
| DeepSeek | `deepseek/modelo` | `deepseek/deepseek-coder` |
| **OpenRouter** | `openrouter/modelo` | `openrouter/meta-llama/llama-3.1-8b-instruct:free` |
| AWS | `bedrock/modelo` | `bedrock/anthropic.claude-3-sonnet` |
| Azure | `azure/modelo` | `azure/gpt-4o` |

## Seguridad: 3 capas complementarias

| Capa | Componente | Qué controla | Momento |
|------|-----------|------------|---------|
| **Pre-ejecución** | MCP Tool Auditor | Qué herramientas se registran | Antes de CrewAI |
| **Runtime** | Agent Fixer Stage | Qué output generan | Durante CrewAI |
| **Pre-commit** | Code Safety Hook | Qué código se commitea | Antes de git commit |

## Tests

```bash
pytest test_pipeline.py -v
pytest test_consolidate.py -v

# Test de git safety
echo 'password = "secret123"' | python3 git_safety_crew.py
# Output esperado: VERDICT: FAIL

echo 'def greet(name): return f"Hello, {name}"' | python3 git_safety_crew.py
# Output esperado: VERDICT: PASS
```

## Licencia

AGPL-3.0-or-later

---

*Desarrollado por Pedro Sordo Martínez (OWL / Hermes Agent) — 2026*
