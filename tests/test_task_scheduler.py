"""Tests for hidden-launcher task creation (no console popup)."""

import os
import subprocess
import tempfile

from src import task_scheduler


def test_create_task_marks_hidden_and_runs_exe_direct(monkeypatch, tmp_path):
    exe = tmp_path / "mklinktool.exe"
    captured = {}

    class Result:
        returncode = 0

    def fake_run(argv, **kwargs):
        xml_path = argv[argv.index("/XML") + 1]
        with open(xml_path, encoding="utf-16") as f:
            captured["xml"] = f.read()
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert task_scheduler.create_task("testtool", str(exe)) is True

    xml = captured["xml"]
    assert f'<Command>"{exe}"</Command>' in xml
    assert "<Hidden>true</Hidden>" in xml


def test_create_task_cleans_up_xml(tmp_path, monkeypatch):
    exe = tmp_path / "mklinktool.exe"

    class Result:
        returncode = 0

    def fake_run(argv, **kwargs):
        xml_path = argv[argv.index("/XML") + 1]
        assert os.path.exists(xml_path)
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    task_scheduler.create_task("testtool", str(exe))
    xml = os.path.join(tempfile.gettempdir(), "testtool_task.xml")
    assert not os.path.exists(xml)
