"""Tests for executable/script path resolution (uv-launcher regression)."""

import os
import sys

from src.elevation import get_exe_path


def test_script_path_returned_as_is(tmp_path, monkeypatch):
    """.py script path is returned unchanged."""
    script = tmp_path / "main.py"
    script.write_text("")
    monkeypatch.setattr(sys, "argv", [str(script)])
    assert get_exe_path() == str(script)


def test_extensionless_path_resolves_to_exe(tmp_path, monkeypatch):
    """uv launcher reports argv[0] without .exe → resolve to real exe."""
    launcher = tmp_path / "mklinktool.exe"
    launcher.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "argv", [os.path.join(tmp_path, "mklinktool")])
    assert get_exe_path() == str(launcher)


def test_missing_path_no_exe_returns_argv0(tmp_path, monkeypatch):
    """Neither argv[0] nor .exe variant exists → return argv[0] unchanged."""
    base = os.path.join(tmp_path, "nope")
    monkeypatch.setattr(sys, "argv", [base])
    assert get_exe_path() == base
