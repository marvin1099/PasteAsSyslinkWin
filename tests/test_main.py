"""Tests for the runtime-only tool dispatch (portable mode, setup delegation)."""

import sys

from src import main as mainmod


class TestPortableMode:
    @staticmethod
    def _isolate(monkeypatch, tmp_path):
        """Tool dispatch must not see temp state from real installs/runs."""
        monkeypatch.setattr(mainmod, "get_install_dir", lambda: str(tmp_path))
        monkeypatch.setattr(mainmod.writeback, "child_args", lambda: None)
        monkeypatch.setattr(mainmod.task_scheduler, "read_args_file", lambda b: [])

    def test_without_config_runs_with_defaults(self, monkeypatch, tmp_path, capsys):
        self._isolate(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "argv", ["mklinktool", "/noclip"])
        errors = []
        monkeypatch.setattr(
            mainmod, "_show_error", lambda title, msg: errors.append(title)
        )
        mainmod._main_impl()
        # Reaches the normal "no destination" path without the wizard.
        assert errors == ["No destination path"]
        assert not (tmp_path / "mklinktool.conf").exists()

    def test_no_config_never_writes_a_conf(self, monkeypatch, tmp_path, capsys):
        self._isolate(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "argv", ["mklinktool"])
        monkeypatch.setattr(mainmod, "_show_error", lambda title, msg: None)
        mainmod._main_impl()
        assert list(tmp_path.iterdir()) == []


class TestSetupDelegation:
    def test_launch_setup_builds_command(self, monkeypatch, tmp_path):
        setup = tmp_path / "mklinktool-setup.exe"
        setup.write_text("", encoding="utf-8")
        monkeypatch.setattr(mainmod, "_find_setup_exe", lambda d: str(setup))
        monkeypatch.setattr(
            mainmod.subprocess, "Popen", lambda cmd: captured.append(cmd)
        )
        captured = []
        assert mainmod._launch_setup(["/uninstall", "/nogui"]) is True
        assert captured == [[str(setup), "/uninstall", "/nogui"]]

    def test_launch_setup_without_args(self, monkeypatch, tmp_path):
        setup = tmp_path / "mklinktool-setup.exe"
        setup.write_text("", encoding="utf-8")
        monkeypatch.setattr(mainmod, "_find_setup_exe", lambda d: str(setup))
        monkeypatch.setattr(
            mainmod.subprocess, "Popen", lambda cmd: captured.append(cmd)
        )
        captured = []
        assert mainmod._launch_setup([]) is True
        assert captured == [[str(setup)]]

    def test_launch_setup_missing_reports(self, monkeypatch, capsys):
        monkeypatch.setattr(mainmod, "_find_setup_exe", lambda d: None)
        assert mainmod._launch_setup([]) is False
        assert "not found" in capsys.readouterr().out

    def test_find_setup_exe_prefers_install_dir(
        self, monkeypatch, tmp_path
    ):
        install_dir = tmp_path / "inst"
        install_dir.mkdir()
        setup = install_dir / "mklinktool-setup.exe"
        setup.write_text("", encoding="utf-8")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "no"))
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "no"))
        monkeypatch.setattr(mainmod, "get_exe_path", lambda: str(tmp_path / "x.exe"))
        assert mainmod._find_setup_exe(str(install_dir)) == str(setup)

    def test_find_setup_exe_none_anywhere(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "no"))
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "no"))
        monkeypatch.setattr(mainmod, "get_exe_path", lambda: str(tmp_path / "x.exe"))
        assert mainmod._find_setup_exe(str(tmp_path)) is None


class TestConfigFlags:
    @staticmethod
    def _prep(monkeypatch, tmp_path):
        TestPortableMode._isolate(monkeypatch, tmp_path)
        conf = tmp_path / "mklinktool.conf"
        conf.write_text("[settings]\n", encoding="utf-8")
        launched = []
        monkeypatch.setattr(mainmod, "_launch_setup", lambda args: launched.append(args))
        return conf, launched

    def test_resetconfig_deletes_and_stops(self, monkeypatch, tmp_path, capsys):
        conf, launched = self._prep(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "argv", ["mklinktool", "/resetconfig"])
        mainmod._main_impl()
        assert not conf.exists()
        assert launched == []
        assert "Config removed" in capsys.readouterr().out

    def test_reconfigure_deletes_and_launches_setup(self, monkeypatch, tmp_path):
        conf, launched = self._prep(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "argv", ["mklinktool", "/reconfigure"])
        mainmod._main_impl()
        assert not conf.exists()
        assert launched == [[]]

    def test_uninstall_flag_delegates_to_setup(self, monkeypatch, tmp_path):
        _conf, launched = self._prep(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "argv", ["mklinktool", "/uninstall", "/nogui"])
        mainmod._main_impl()
        assert launched == [["/uninstall", "/nogui"]]

    def test_install_flag_delegates_to_setup_wizard(self, monkeypatch, tmp_path):
        _conf, launched = self._prep(monkeypatch, tmp_path)
        monkeypatch.setattr(sys, "argv", ["mklinktool", "/install"])
        mainmod._main_impl()
        assert launched == [[]]
