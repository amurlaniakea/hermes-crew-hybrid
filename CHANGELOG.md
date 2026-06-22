# Changelog

All notable changes to Hermes-Crew Hybrid will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-22

### Added
- Hermes as Conductor: orchestrates CrewAI micro-crews
- Dual execution mode: venv (fast) or Docker (isolated)
- Auto-detection of execution mode based on RAM, Docker availability, and repo type
- LiteLLM multi-model support (8+ providers: Ollama, OpenAI, Anthropic, Gemini, Groq, DeepSeek, OpenRouter, AWS Bedrock, Azure)
- 3 security layers: MCP Tool Auditor + Agent Fixer Stage + Code Safety Hook
- Obsidian integration for automatic report generation
- Pre-commit hook for code safety scanning
- Docker Compose stack with Ollama
- 28 tests (unit + integration)
- pyproject.toml with dependencies declared
- Makefile with standard targets
- ruff, mypy, black configuration
- Coverage configuration (minimum 70%)
- SECURITY.md and CHANGELOG.md

### Security
- Fixed 5 bare `except:` clauses that could silently swallow errors
- Docker isolation: network disabled, memory/CPU limits, read-only filesystem
- Agent Fixer Stage filters all CrewAI output before delivery
