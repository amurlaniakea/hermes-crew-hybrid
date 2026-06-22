# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.0   | Yes       |

## Reporting a Security Vulnerability

If you discover a security vulnerability in Hermes-Crew Hybrid, please report it responsibly.

**Do NOT open a public GitHub Issue for security vulnerabilities.**

Instead, report via email:
- **Email:** amurlaniakea@gmail.com
- **Subject:** `[SECURITY] Hermes-Crew Hybrid vulnerability`

You will receive a response within 48 hours.

## Architecture

Hermes-Crew Hybrid implements 3 security layers:

| Layer | Component | When |
|-------|-----------|------|
| Pre-execution | MCP Tool Auditor | Before CrewAI runs |
| Runtime | Agent Fixer Stage | During CrewAI execution |
| Pre-commit | Code Safety Hook | Before git commit |

## Security Considerations

- **Docker mode** provides process isolation with `--network none`, `--memory 512m`, `--cpus 1.0`, `--read-only`.
- **venv mode** is faster but provides no isolation. Use only for trusted local repos.
- **Agent Fixer Stage** filters CrewAI output but is not foolproof (~85-90% detection rate).
- **MCP Tool Auditor** is only active when `mcp_tool_auditor` module is available.

## Dependencies

Runtime: `crewai`, `crewai-tools`, `litellm`
Dev: `pytest`, `pytest-cov`
