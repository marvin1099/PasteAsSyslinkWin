"""Tests for the wscript hidden launcher (no console window)."""

from src.vbs_launcher import write_hidden_launcher


def test_content_hides_waits_and_sets_cwd(tmp_path):
    path = str(tmp_path / "hide.vbs")
    cwd = r"C:\Program Files\mklinktool"
    assert write_hidden_launcher(path, cwd) == path
    content = (tmp_path / "hide.vbs").read_text(encoding="utf-8")
    assert 'WShell.CurrentDirectory = "C:\\Program Files\\mklinktool"' in content
    assert "WShell.Run cmd, 0, True" in content
    assert 'CreateObject("WScript.Shell")' in content


def test_every_argument_is_requoted(tmp_path):
    write_hidden_launcher(str(tmp_path / "x.vbs"), str(tmp_path))
    content = (tmp_path / "x.vbs").read_text(encoding="utf-8")
    assert 'cmd = """" & WScript.Arguments(0) & """"' in content
    assert 'cmd = cmd & " " & """" & WScript.Arguments(i) & """"' in content


def test_crlf_line_endings(tmp_path):
    write_hidden_launcher(str(tmp_path / "x.vbs"), str(tmp_path))
    data = (tmp_path / "x.vbs").read_bytes()
    assert b"\r\n" in data
    assert data.count(b"\r\n") == data.count(b"\n")


def test_empty_cwd_uses_process_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_hidden_launcher(str(tmp_path / "x.vbs"), "")
    content = (tmp_path / "x.vbs").read_text(encoding="utf-8")
    assert str(tmp_path) in content
