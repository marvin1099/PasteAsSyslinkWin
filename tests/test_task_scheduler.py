"""Tests for the wscript-launched hidden task (no console popup)."""

import os
import subprocess

from src import task_scheduler


def _fake_run(captured):
    def fake_run(argv, **kwargs):
        captured.setdefault("calls", []).append(list(argv))
        if "/XML" in argv:
            xml_path = argv[argv.index("/XML") + 1]
            with open(xml_path, encoding="utf-16") as f:
                captured["xml"] = f.read()

        class Result:
            returncode = 0

        return Result()

    return fake_run


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(task_scheduler.tempfile, "gettempdir", lambda: str(tmp_path))
    captured = {}
    monkeypatch.setattr(subprocess, "run", _fake_run(captured))
    return captured


def _wscript():
    return os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32", "wscript.exe")


def test_create_task_action_is_wscript_with_launcher(monkeypatch, tmp_path):
    captured = _isolate(monkeypatch, tmp_path)
    exe = tmp_path / "mklinktool.exe"
    assert task_scheduler.create_task("testtool", str(exe)) is True

    xml = captured["xml"]
    assert f"<Command>{_wscript()}</Command>" in xml
    launcher = os.path.join(str(tmp_path), "testtool_hidden.vbs")
    assert f'"{launcher}" "{exe}"' in xml
    assert "<Hidden>true</Hidden>" in xml
    assert (tmp_path / "testtool_hidden.vbs").is_file()


def test_create_task_passes_source_arguments(monkeypatch, tmp_path):
    captured = _isolate(monkeypatch, tmp_path)
    task_scheduler.create_task("testtool", "python.exe", '"C:\\repo\\src\\main.py"')
    xml = captured["xml"]
    assert '"python.exe" "C:\\repo\\src\\main.py"' in xml


def test_run_task_rewrites_missing_launcher(monkeypatch, tmp_path):
    captured = _isolate(monkeypatch, tmp_path)
    exe = tmp_path / "mklinktool.exe"
    task_scheduler.create_task("testtool", str(exe))
    launcher = tmp_path / "testtool_hidden.vbs"
    launcher.unlink()
    assert task_scheduler.run_task("testtool", str(exe)) is True
    assert launcher.is_file()
    commands = [argv[1] for argv in captured["calls"] if argv[0] == "schtasks"]
    assert "/End" in commands and "/Run" in commands


def test_delete_task_removes_launcher(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    exe = tmp_path / "mklinktool.exe"
    task_scheduler.create_task("testtool", str(exe))
    assert (tmp_path / "testtool_hidden.vbs").is_file()
    assert task_scheduler.delete_task("testtool") is True
    assert not (tmp_path / "testtool_hidden.vbs").exists()


def test_create_task_cleans_up_xml(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    exe = tmp_path / "mklinktool.exe"
    task_scheduler.create_task("testtool", str(exe))
    assert not (tmp_path / "testtool_task.xml").exists()


def test_launcher_xml_escapes_special_chars(monkeypatch, tmp_path):
    captured = _isolate(monkeypatch, tmp_path)
    exe = tmp_path / "my tool&co.exe"
    task_scheduler.create_task("testtool", str(exe))
    assert "my tool&amp;co.exe" in captured["xml"]
