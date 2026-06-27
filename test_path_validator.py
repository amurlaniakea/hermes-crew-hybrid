#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests de seguridad para path_validator — verifica que los fixes S8707/S8705/S5443 funcionan."""

import os
import pytest
import tempfile
from pathlib import Path

from path_validator import validate_path, sanitize_shell_arg, get_safe_output_dir, get_safe_script_path


class TestValidatePath:
    """Verifica que validate_path bloquea path traversal (S8707)."""

    def test_reject_traversal_dotdot(self):
        """No permitir ../etc/passwd."""
        with pytest.raises(ValueError, match="forbidden pattern"):
            validate_path("/home/sil/../../../etc/passwd")

    def test_reject_null_byte(self):
        """No permitir null bytes en paths."""
        with pytest.raises(ValueError, match="forbidden pattern"):
            validate_path("/home/sil/file\x00.txt")

    def test_reject_double_slash(self):
        """No permitir dobles slashes (potencial escape)."""
        with pytest.raises(ValueError, match="forbidden pattern"):
            validate_path("//etc/passwd")

    def test_reject_empty_path(self):
        """No permitir path vacío."""
        with pytest.raises(ValueError, match="empty"):
            validate_path("")

    def test_reject_system_path_etc(self):
        """No permitir escritura en /etc."""
        with pytest.raises(ValueError, match="system directory"):
            validate_path("/etc/passwd")

    def test_reject_system_path_var(self):
        """No permitir escritura en /var."""
        with pytest.raises(ValueError, match="system directory"):
            validate_path("/var/log/syslog")

    def test_reject_system_path_usr(self):
        """No permitir escritura en /usr."""
        with pytest.raises(ValueError, match="system directory"):
            validate_path("/usr/bin/python3")

    def test_allow_home_path(self):
        """Permitir paths bajo /home (directorio legítimo de usuario)."""
        result = validate_path("/home/sil/test.txt")
        assert str(result) == "/home/sil/test.txt"

    def test_allow_tmp_path(self):
        """Permitir /tmp como path válido (la restricción S5443 se maneja en get_safe_output_dir)."""
        # nosemgrep: python.security.path-traversal.insecure-path-construction
        # nosemgrep: python.lang.security.audit.tempfile.tmp-insecure
        result = validate_path("/tmp/test.txt")  # noqa: S5443
        assert "/tmp/test.txt" in str(result)

    def test_base_dir_enforcement(self):
        """Si se especifica base_dir, la ruta no puede escapar."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Path dentro del base → OK
            result = validate_path(os.path.join(tmpdir, "file.txt"), base_dir=tmpdir)
            assert str(result).startswith(tmpdir)

            # Path que escapa → rechazado (usar un path que no sea /etc para evitar system check primero)
            with pytest.raises(ValueError, match="escapes base directory"):
                validate_path("/home/sil/other_dir/file.txt", base_dir=tmpdir)

    def test_must_exist(self):
        """Si must_exist=True, rechazar paths que no existen."""
        with pytest.raises(FileNotFoundError):
            validate_path("/home/sil/no_existe_nunca_12345.txt", must_exist=True)


class TestSanitizeShellArg:
    """Verifica que sanitize_shell_arg bloquea inyección de comandos (S8705)."""

    def test_reject_semicolon(self):
        with pytest.raises(ValueError, match="dangerous"):
            sanitize_shell_arg("tool; rm -rf /")

    def test_reject_pipe(self):
        with pytest.raises(ValueError, match="dangerous"):
            sanitize_shell_arg("tool | cat /etc/passwd")

    def test_reject_backtick(self):
        with pytest.raises(ValueError, match="dangerous"):
            sanitize_shell_arg("tool `whoami`")

    def test_reject_dollar(self):
        with pytest.raises(ValueError, match="dangerous"):
            sanitize_shell_arg("tool $(whoami)")

    def test_reject_newline(self):
        with pytest.raises(ValueError, match="dangerous"):
            sanitize_shell_arg("tool\nrm -rf /")

    def test_reject_ampersand(self):
        with pytest.raises(ValueError, match="dangerous"):
            sanitize_shell_arg("tool & whoami")

    def test_accept_normal_name(self):
        result = sanitize_shell_arg("web_search")
        assert result == "web_search"

    def test_accept_empty_string(self):
        """String vacío es válido (herramientas sin descripción)."""
        result = sanitize_shell_arg("")
        assert result == ""

    def test_reject_too_long(self):
        with pytest.raises(ValueError, match="max length"):
            sanitize_shell_arg("a" * 300, max_length=256)

    def test_reject_redirect(self):
        with pytest.raises(ValueError, match="dangerous"):
            sanitize_shell_arg("tool > /etc/passwd")

    def test_reject_parentheses(self):
        with pytest.raises(ValueError, match="dangerous"):
            sanitize_shell_arg("tool(subprocess)")


class TestGetSafeOutputDir:
    """Verifica que get_safe_output_dir no usa /tmp (S5443)."""

    def test_output_dir_not_in_tmp(self):
        """El directorio de output NO debe estar en /tmp."""
        output_dir = get_safe_output_dir()
        assert not output_dir.startswith("/tmp"), f"Output dir in /tmp: {output_dir}"  # noqa: S5443

    def test_output_dir_under_xdg(self):
        """El directorio de output debe estar bajo XDG_DATA_HOME."""
        output_dir = get_safe_output_dir()
        xdg = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        assert output_dir.startswith(xdg), f"Output dir not under XDG: {output_dir}"

    def test_output_dir_exists(self):
        """El directorio de output debe existir."""
        output_dir = get_safe_output_dir()
        assert Path(output_dir).exists()

    def test_output_dir_not_world_writable(self):
        """El directorio base NO debe ser mundialmente escribible."""
        output_dir = get_safe_output_dir()
        base = Path(output_dir).parent
        mode = base.stat().st_mode
        # Group y other no deben tener write
        assert not (mode & 0o022), f"Base dir is group/other writable: {base} (mode: {oct(mode)})"


class TestGetSafeScriptPath:
    """Verifica que get_safe_script_path no usa /tmp."""

    def test_script_path_not_in_tmp(self):
        path = get_safe_script_path()
        assert not path.startswith("/tmp"), f"Script path in /tmp: {path}"  # noqa: S5443
