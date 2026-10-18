"""Tests for executable/script path resolution (uv-launcher regression)
and write-probe cleanup on failed UAC launches."""

import os
import sys

from src import elevation
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


def _fake_shell_execute(monkeypatch, result):
    monkeypatch.setattr(
        elevation.ctypes.windll.shell32, "ShellExecuteW", lambda *a: result
    )


def test_declined_uac_removes_probe(tmp_path, monkeypatch):
    """UAC refused → the probe no child will verify must be deleted."""
    probe = tmp_path / ".mklinktool_probe_deadbeefdeadbeef"
    probe.write_text("deadbeefdeadbeef", encoding="utf-8")
    _fake_shell_execute(monkeypatch, 2)  # <= 32 means failure
    launched = elevation._launch_uac("C:\\tool.exe", "", [f"/probe:{probe}"])
    assert launched is False
    assert not probe.exists()


def test_accepted_uac_keeps_probe_for_child(tmp_path, monkeypatch):
    probe = tmp_path / ".mklinktool_probe_deadbeefdeadbeef"
    probe.write_text("deadbeefdeadbeef", encoding="utf-8")
    _fake_shell_execute(monkeypatch, 42)
    launched = elevation._launch_uac("C:\\tool.exe", "", [f"/probe:{probe}"])
    assert launched is True
    assert probe.exists()


def test_remove_probe_arg_tolerates_missing_and_unrelated_args(tmp_path):
    missing = str(tmp_path / ".mklinktool_probe_gone")
    unrelated = tmp_path / "keepme.txt"
    unrelated.write_text("x", encoding="utf-8")
    elevation._remove_probe_arg(["/restart", f"/probe:{missing}", str(unrelated)])
    assert unrelated.exists()
