"""Tests for context menu command building (uv-launcher regression)."""

import sys

from src.context_menu import _exe_command


def test_py_script_runs_via_python(tmp_path, monkeypatch):
    """.py script → "<python>" "<script>"""""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\py\python.exe")
    script = tmp_path / "main.py"
    script.write_text("")
    cmd = _exe_command(str(script))
    assert cmd == f'"C:\\py\\python.exe" "{script}"'


def test_launcher_exe_runs_directly(tmp_path, monkeypatch):
    """uv/pip launcher exe → direct invocation, not via python."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    launcher = tmp_path / "mklinktool.exe"
    launcher.write_bytes(b"MZ")
    cmd = _exe_command(str(launcher))
    assert cmd == f'"{launcher}"'


def test_frozen_runs_directly(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    cmd = _exe_command(r"C:\Program Files\mklinktool\mklinktool.exe")
    assert cmd == '"C:\\Program Files\\mklinktool\\mklinktool.exe"'
