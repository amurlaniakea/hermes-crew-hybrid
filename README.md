# Hermes-Crew Hybrid

> Arquitectura híbrida: Hermes como Director de Orquesta + micro-tripulaciones CrewAI + MCP Core Defense + Agent Fixer Stage + Code Safety pre-commit hook.

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
    ├── CrewAI analiza diff (Ollama local)
    ├── Agent Fixer Stage filtra output
    ├── VERDICT: PASS → commit aprobado + reporte Obsidian
    └── VERDICT: FAIL → commit rechazado + alerta
```

## Características

- **Dual mode**: venv local (rápido) o Docker aislado (seguro)
- **Auto-detect**: elige modo basado en RAM y Docker disponible
- **Ollama local**: funciona con cualquier modelo local (qwen2.5:0.5b, batiai/gemma4-e2b:q4, etc.)
- **3 capas de seguridad**: MCP Tool Auditor + Agent Fixer Stage + Code Safety Hook
- **Herramientas CrewAI reales**: WebSearchTool, FileReadTool, FileWriteTool, ObsidianSearchTool, ObsidianReadTool
- **Output capture**: PYTHONUNBUFFERED + python -u para captura en tiempo real
- **Obsidian integration**: reportes automáticos en vault de Obsidian

## Estructura

```
hermes-crew-hybrid/
├── invoke_crew_task.py       # Skill principal (orquestador)
├── crewai_tools.py           # Herramientas CrewAI reales (BaseTool)
├── security_gateway.py       # Middleware de seguridad (Fixer Stage)
├── mcp_tool_auditor.py       # Auditor MCP Core Defense
├── consolidate.py            # Parser + generador Obsidian
├── git_safety_crew.py        # Análisis de git diffs
├── pre-commit-hook.sh        # Hook de Git para CI/CD local
├── Dockerfile                # Imagen Docker para CrewAI
├── docker-compose.yml        # Config del contenedor aislado
├── .env                      # Config Ollama
├── test_pipeline.py          # Tests de pipeline (13 tests)
├── test_consolidate.py       # Tests de consolidación (14 tests)
└── README.md
```

## Requisitos

- Python 3.10+
- Docker (opcional, para modo Docker)
- Ollama (con modelo local instalado)
- Dependencias: `pip install crewai crewai-tools langchain litellm`

## Instalación

```bash
# Clonar repo
git clone https://github.com/amurlaniakea/hermes-crew-hybrid.git
cd hermes-crew-hybrid

# Instalar dependencias en venv existente
/home/sil/mcp-core-defense/venv/bin/pip install crewai crewai-tools langchain litellm

# Verificar sintaxis
python3 -c "import invoke_crew_task; print('OK')"
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

print(result["status"])  # "success" | "error"
print(result["execution_mode"])  # "venv" | "docker"
print(result["security"]["status"])  # "pass" | "clean" | "rejected"
print(result["raw_output"])  # Output sanitizado
```

### Consolidar en Obsidian

```python
from consolidate import consolidate_crew_output

consolidated = consolidate_crew_output(
    result,
    tags=["agents", "security", "crewai"],
    vault_path="/mnt/c/Users/Sil/Documents/Obsidian Vault/Memorias/IA y Computacion",
    save=True
)

print(f"Nota guardada: {consolidated['note_path']}")
```

### Instalar Code Safety pre-commit hook

```bash
# Copiar hook al repositorio donde quieras usarlo
cp pre-commit-hook.sh /ruta/al/repo/.git/hooks/pre-commit
chmod +x /ruta/al/repo/.git/hooks/pre-commit

# Probar con un commit de prueba
git add .
git commit -m "test"  # El hook analizará el diff automáticamente
```

## Configuración del modelo Ollama

Editar `OLLAMA_MODEL` en `invoke_crew_task.py`:

```python
# Rápido (14s aprox)
OLLAMA_MODEL = "qwen2.5:0.5b"

# Potente (65s aprox) - Requiere 3.4GB RAM
OLLAMA_MODEL = "batiai/gemma4-e2b:q4"
```

## Tests

```bash
# Tests de pipeline
/home/sil/mcp-core-defense/venv/bin/python3 -m pytest test_pipeline.py -v

# Tests de consolidación
/home/sil/mcp-core-defense/venv/bin/python3 -m pytest test_consolidate.py -v

# Test de git safety
echo 'password = "secret123"' | /home/sil/mcp-core-defense/venv/bin/python3 git_safety_crew.py
# Output esperado: VERDICT: FAIL

echo 'def greet(name): return f"Hello, {name}"' | /home/sil/mcp-core-defense/venv/bin/python3 git_safety_crew.py
# Output esperado: VERDICT: PASS
```

## Seguridad: 3 capas complementarias

| Capa | Componente | Qué controla | Momento |
|------|-----------|---------------|---------|
| **Pre-ejecución** | MCP Tool Auditor | Qué herramientas se registran | Antes de CrewAI |
| **Runtime** | Agent Fixer Stage | Qué output generan | Durante CrewAI |
| **Pre-commit** | Code Safety Hook | Qué código se commitea | Antes de git commit |

## Benchmarks

| Operación | Modelo | Tiempo |
|-----------|--------|--------|
| invoke_crew_task (simple) | qwen2.5:0.5b | ~14s |
| invoke_crew_task (simple) | batiai/gemma4-e2b:q4 | ~65s |
| Agent Fixer Stage | — | <1ms |
| MCP Tool Auditor | — | <10ms |
| Git Safety (diff pequeño) | qwen2.5:0.5b | ~30s |

## Licencia

AGPL-3.0-or-later

---

*Desarrollado por Pedro Sordo Martínez (OWL / Hermes Agent) — 2026*
