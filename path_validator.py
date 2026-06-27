#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Path validation utilities — prevención de path traversal y escape de sandbox.

Todas las operaciones de filesystem deben pasar por estas validaciones
antes de construir rutas o acceder a archivos. Resuelve:
  - pythonsecurity:S8707 (LLM path traversal)
  - python:S5443 (publicly writable directories)
  - pythonsecurity:S8705 (shell argument injection)
"""

import os
import re
from pathlib import Path
from typing import Optional, Union


# ── Directorios del sistema que NUNCA deben ser objetivo de escritura ─────────
# Nota: /home NO está aquí porque es un directorio legítimo de usuario.
# La validación real es contra base_dir (path traversal), no contra un blacklist.
_SYSTEM_FORBIDDEN: list[str] = [
    "/etc", "/var", "/usr", "/bin", "/sbin", "/boot", "/dev", "/proc", "/sys",
    "/root",
]


def _is_system_path(resolved: str) -> bool:
    """Comprueba si una ruta cae en un directorio de sistema protegido."""
    for prefix in _SYSTEM_FORBIDDEN:
        if resolved == prefix or resolved.startswith(prefix + "/"):
            return True
    return False


def validate_path(
    user_path: str,
    base_dir: str | Path | None = None,
    must_exist: bool = False,
) -> Path:
    """
    Valida una ruta de filesystem para prevenir path traversal.

    Args:
        user_path: Ruta proporcionada (potencialmente maliciosa)
        base_dir: Directorio base permitido (la ruta debe quedar dentro)
        must_exist: Si True, verifica que la ruta existe

    Returns:
        Path validado y resuelto

    Raises:
        ValueError: Si la ruta es peligrosa o escapa del base_dir
        FileNotFoundError: Si must_exist=True y la ruta no existe
    """
    if not user_path or not user_path.strip():
        raise ValueError("Path cannot be empty")

    # Rechazar patrones obvios de traversal
    dangerous_patterns: list[str] = ["..", "//", "\\\\", "\0"]
    for pattern in dangerous_patterns:
        if pattern in user_path:
            raise ValueError(f"Path contains forbidden pattern: {pattern!r}")

    # Resolver ruta absoluta
    resolved: Path = Path(user_path).resolve()

    # Comprobar que no escapa a directorios de sistema
    if _is_system_path(str(resolved)):
        raise ValueError(f"Path escapes to system directory: {resolved}")

    # Si hay base_dir, la ruta debe quedar dentro
    if base_dir is not None:
        resolved_base: Path = Path(base_dir).resolve()
        try:
            resolved.relative_to(resolved_base)
        except ValueError:
            raise ValueError(
                f"Path escapes base directory: {resolved} is not under {resolved_base}"
            )

    # Verificar existencia si se requiere
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")

    return resolved


def get_safe_output_dir(prefix: str = "crew_output") -> str:
    """
    Devuelve un directorio de output seguro (no /tmp prohibido).

    Usa ~/.local/share/hermes-crew-hybrid/ como base, que:
    - No es mundialmente escribible (a diferencia de /tmp)
    - Respeta XDG_DATA_HOME si está definido
    - Crea el directorio si no existe

    Args:
        prefix: Prefijo para el subdirectorio

    Returns:
        Ruta absoluta al directorio de output
    """
    xdg_data: str = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    base: Path = Path(xdg_data) / "hermes-crew-hybrid"
    base.mkdir(parents=True, exist_ok=True)

    # Verificar permisos: solo el dueño debe tener write
    mode: int = base.stat().st_mode
    if mode & 0o022:
        base.chmod(mode & ~0o022)

    output_dir: Path = base / f"{prefix}_{os.getpid()}"
    output_dir.mkdir(exist_ok=True)
    return str(output_dir)


def get_safe_script_path(prefix: str = "crew") -> str:
    """
    Devuelve una ruta segura para scripts temporales.

    Usa get_safe_output_dir() como base en vez de /tmp.

    Args:
        prefix: Prefijo para el archivo

    Returns:
        Ruta absoluta al script temporal
    """
    output_dir: str = get_safe_output_dir(prefix=prefix)
    return str(Path(output_dir) / f"{prefix}_{os.getpid()}.py")


# ── Validación de entrada para comandos shell ────────────────────────────────

_SHELL_DANGEROUS: re.Pattern[str] = re.compile(
    r'[;&|`$\(\)\{\}\[\]<>\!\n\r\\]'
)


def sanitize_shell_arg(value: str, max_length: int = 256) -> str:
    """
    Valida y sanitiza un argumento antes de pasarlo a subprocess.

    Rechaza cualquier string que contenga caracteres de shell metastack.
    String vacío es válido (herramientas sin descripción).

    Args:
        value: Valor a sanitizar
        max_length: Longitud máxima permitida

    Returns:
        El valor sanitizado

    Raises:
        ValueError: Si contiene caracteres peligrosos o excede longitud
    """
    if not value:
        return value  # String vacío es válido

    if len(value) > max_length:
        raise ValueError(f"Shell argument exceeds max length ({max_length}): {value!r}")

    if _SHELL_DANGEROUS.search(value):
        raise ValueError(
            f"Shell argument contains dangerous characters: {value!r}"
        )

    return value
