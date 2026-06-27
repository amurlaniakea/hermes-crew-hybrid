#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Pedro Sordo Martínez <amurlaniakea@gmail.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests para crewai_tools.py — verificación de herramientas CrewAI."""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from crewai_tools import (
    WebSearchTool,
    FileReadTool,
    FileWriteTool,
    ObsidianSearchTool,
    ObsidianReadTool,
    ALL_TOOLS,
    get_tool,
    get_tools_list,
    list_available_tools,
)


class TestWebSearchTool:
    """Tests para WebSearchTool."""

    def test_tool_attributes(self):
        tool = WebSearchTool()
        assert tool.name == "web_search"
        assert "search" in tool.description.lower()

    @patch("crewai_tools.subprocess.run")
    def test_run_with_results(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='<a rel="nofollow" class="result__a" href="http://example.com">AI Security</a>'
                    '<a class="result__snippet" href="http://example.com">Important findings about AI</a>',
            returncode=0,
        )
        tool = WebSearchTool()
        result = tool._run("AI security")
        assert "AI Security" in result
        assert "Important findings" in result

    @patch("crewai_tools.subprocess.run")
    def test_run_no_results(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        tool = WebSearchTool()
        result = tool._run("nonexistent topic xyz")
        assert "No results found" in result

    @patch("crewai_tools.subprocess.run", side_effect=Exception("Network error"))
    def test_run_error(self, mock_run):
        tool = WebSearchTool()
        result = tool._run("test")
        assert "Search error" in result


class TestFileReadTool:
    """Tests para FileReadTool."""

    def test_tool_attributes(self):
        tool = FileReadTool()
        assert tool.name == "file_read"

    def test_read_existing_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello, world!")
            f.flush()
            tool = FileReadTool()
            result = tool._run(f.name)
            assert "Hello, world!" in result
            os.unlink(f.name)

    def test_read_nonexistent_file(self):
        tool = FileReadTool()
        result = tool._run("/nonexistent/path/file.txt")
        assert "File not found" in result


class TestFileWriteTool:
    """Tests para FileWriteTool."""

    def test_tool_attributes(self):
        tool = FileWriteTool()
        assert tool.name == "file_write"

    def test_write_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test_output.md")
            tool = FileWriteTool()
            result = tool._run(filepath, "Test content here")
            assert "Written" in result
            assert os.path.exists(filepath)
            assert Path(filepath).read_text() == "Test content here"


class TestObsidianSearchTool:
    """Tests para ObsidianSearchTool."""

    def test_tool_attributes(self):
        tool = ObsidianSearchTool()
        assert tool.name == "obsidian_search"

    def test_search_without_vault_path(self):
        tool = ObsidianSearchTool()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OBSIDIAN_VAULT_PATH", None)
            result = tool._run("test query")
            assert "OBSIDIAN_VAULT_PATH not configured" in result

    def test_search_nonexistent_vault(self):
        tool = ObsidianSearchTool()
        result = tool._run("test", vault_path="/nonexistent/vault")
        assert "Vault not found" in result

    def test_search_in_vault(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Crear nota con contenido
            note = Path(tmpdir) / "test_note.md"
            note.write_text("# Test Note\n\nThis has keyword Python in it.", encoding="utf-8")

            tool = ObsidianSearchTool()
            result = tool._run("Python", vault_path=tmpdir)
            assert "test_note.md" in result

    def test_search_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            note = Path(tmpdir) / "note.md"
            note.write_text("No relevant content here.", encoding="utf-8")

            tool = ObsidianSearchTool()
            result = tool._run("xyznonexistent", vault_path=tmpdir)
            assert "No notes found" in result


class TestObsidianReadTool:
    """Tests para ObsidianReadTool."""

    def test_tool_attributes(self):
        tool = ObsidianReadTool()
        assert tool.name == "obsidian_read"

    def test_read_without_vault(self):
        tool = ObsidianReadTool()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OBSIDIAN_VAULT_PATH", None)
            result = tool._run("some_note")
            assert "OBSIDIAN_VAULT_PATH not configured" in result

    def test_read_existing_note(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            note = Path(tmpdir) / "test.md"
            note.write_text("# My Note\n\nContent here.", encoding="utf-8")

            tool = ObsidianReadTool()
            result = tool._run("test.md", vault_path=tmpdir)
            assert "Content here" in result

    def test_read_nonexistent_note(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ObsidianReadTool()
            result = tool._run("nonexistent.md", vault_path=tmpdir)
            assert "Note not found" in result


class TestToolRegistry:
    """Tests para el registro de herramientas."""

    def test_all_tools_defined(self):
        assert "web_search" in ALL_TOOLS
        assert "file_read" in ALL_TOOLS
        assert "file_write" in ALL_TOOLS
        assert "obsidian_search" in ALL_TOOLS
        assert "obsidian_read" in ALL_TOOLS

    def test_get_tool_by_name(self):
        tool = get_tool("web_search")
        assert tool is not None
        assert isinstance(tool, WebSearchTool)

    def test_get_unknown_tool(self):
        tool = get_tool("nonexistent_tool")
        assert tool is None

    def test_get_tools_list(self):
        tools = get_tools_list(["web_search", "file_read"])
        assert len(tools) == 2

    def test_get_tools_list_with_unknown(self):
        tools = get_tools_list(["web_search", "unknown"])
        assert len(tools) == 1

    def test_list_available_tools(self):
        available = list_available_tools()
        assert len(available) == 5
        assert all(isinstance(desc, str) for desc in available.values())
