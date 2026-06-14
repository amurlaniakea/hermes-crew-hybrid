# Hermes-Crew Hybrid

> Arquitectura híbrida: Hermes como Director de Orquesta + micro-tripulaciones CrewAI en Docker aislado + Agent Fixer Stage como gateway de seguridad.

## Visión

```
Hermes (Director)
    │
    ├── invoke_crew_task() → crea micro-tripulación
    │
    ├── Contenedor Docker aislado
    │       ├── Agente 1: Investigador
    │       ├── Agente 2: Analista
    │       └── Agente 3: Redactor
    │
    ├── Security Gateway (Agent Fixer Stage)
    │       ├── Normalización anti-evasión
    │       ├── Pattern matching (<1ms)
    │       └── Embeddings (solo zona gris)
    │
    └── Hermes absorbe resultado limpio → Obsidian
```

## Estructura

```
hermes-crew-hybrid/
├── invoke_crew_task.py       # Skill de Hermes para invocar tripulaciones
├── security_gateway.py       # Middleware de seguridad (Fixer Stage)
├── Dockerfile                # Imagen Docker para CrewAI
├── docker-compose.yml        # Config del contenedor aislado
├── test_pipeline.py          # Tests del pipeline completo
└── README.md
```

## Seguridad: 3 capas complementarias

| Capa | Proyecto | Qué controla |
|------|----------|--------------|
| Pre-ejecución | Brainstorm-Mode | **Cuándo** ejecutar herramientas |
| Pre-registro | MCP Core Defense | **Qué** herramientas se registran |
| Post-ejecución | Agent Fixer Stage | **Qué** output generan |

## Uso

```python
from invoke_crew_task import invoke_crew_task

result = invoke_crew_task(
    task="Investigar los 22 nichos del mapa de Obsidian",
    crew=[
        {"role": "Investigador", "goal": "Buscar info sobre cada nicho", "tools": ["web_search"]},
        {"role": "Redactor", "goal": "Escribir resumen", "tools": ["write_file"]}
    ],
    scope="Análisis de nichos de seguridad de IA"
)

print(result["status"])  # "success" | "security_flagged" | "error"
print(result["security"]["status"])  # "pass" | "clean" | "rejected"
```

## Tests

```bash
pytest test_pipeline.py -v
```

## Próximos pasos

- [ ] Probar con Docker real
- [ ] Integrar con Hermes (skill)
- [ ] Añadir más tests de integración
- [ ] Documentar casos de uso

## Licencia

AGPL-3.0-or-later
