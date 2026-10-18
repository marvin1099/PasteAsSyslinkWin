"""Tests for the mklinktool-setup entry point and installer core."""

import sys

import pytest

from src import installer
from src.setup_main import parse_setup_args


class TestSetupArgDispatch:
    def test_no_args_is_wizard(self):
        assert parse_setup_args([]) == "wizard"

    def test_help_flags(self):
        assert parse_setup_args(["/help"]) == "help"
        assert parse_setup_args(["/?"]) == "help"
        assert parse_setup_args(["/nogui", "/help"]) == "help"

    def test_uninstall_modes(self):
        assert parse_setup_args(["/uninstall"]) == "uninstall"
        assert parse_setup_args(["/uninstall", "/nogui"]) == "uninstall"

    def test_repair_mode(self):
        assert parse_setup_args(["/repair"]) == "repair"

    def test_silent_install_scopes(self):
        assert parse_setup_args(["/nogui"]) == "install_user"
        assert parse_setup_args(["/noguiall"]) == "install_all"

    def test_restart_elevation_relaunch_keeps_mode(self):
        # /restart is added by the UAC relaunch and must not change the mode.
        assert parse_setup_args(["/restart", "/nogui"]) == "install_user"
        assert parse_setup_args(["/restart", "/repair"]) == "repair"
        assert parse_setup_args(["/restart"]) == "wizard"

    def test_unknown_flags_fall_back_to_wizard(self):
        assert parse_setup_args(["/bogus"]) == "wizard"


class TestPayloadDir:
    def test_source_run_has_no_payload(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert installer._payload_dir() is None

    def test_frozen_with_payload(self, tmp_path, monkeypatch):
        payload = tmp_path / "payload"
        payload.mkdir()
        (payload / "mklinktool.exe").write_text("x", encoding="utf-8")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        assert installer._payload_dir() == str(payload)

    def test_frozen_missing_payload(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        assert installer._payload_dir() is None


class TestSilentInstallConfigPreservation:
    @staticmethod
    def _write_config(install_dir, monkeypatch, tmp_path, **overrides):
        install_dir.mkdir(parents=True, exist_ok=True)
        values = {
            "task": "False",
            "wildcardloops": "True",
            "scriptdefaultfileoptions": "/h",
            "scriptdefaultfolderoptions": "/d",
            "adminfileoptions": "/f",
            "adminfolderoptions": "/j",
            "adminfree": "True",
            "allusers": "False",
        }
        values.update(overrides)
        lines = ["[settings]"] + [f"{k} = {v}" for k, v in values.items()]
        (install_dir / "mklinktool.conf").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "pf"))

    def test_existing_settings_survive_silent_upgrade(
        self, monkeypatch, tmp_path, capsys
    ):
        install_dir = tmp_path / "mklinktool"
        self._write_config(install_dir, monkeypatch, tmp_path)
        captured = {}
        monkeypatch.setattr(
            installer,
            "_do_install",
            lambda basename, cfg: captured.update(cfg),
        )
        with pytest.raises(SystemExit):
            installer.run_installer_silent("mklinktool", all_users=False)

        assert captured["install_dir"] == str(install_dir)
        assert captured["use_task"] is False
        assert captured["wildcard_loops"] is True
        assert captured["admin_free"] is True
        assert captured["file_opts"] == "/h"
        assert captured["folder_opts"] == "/d"
        assert captured["admin_file_opts"] == "/f"
        assert captured["admin_folder_opts"] == "/j"
        # Scope stays whatever the caller asked for.
        assert captured["all_users"] is False
        assert "Installation complete!" in capsys.readouterr().out

    def test_fresh_install_uses_defaults(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "pf"))
        captured = {}
        monkeypatch.setattr(
            installer,
            "_do_install",
            lambda basename, cfg: captured.update(cfg),
        )
        with pytest.raises(SystemExit):
            installer.run_installer_silent("mklinktool", all_users=True)

        assert captured["install_dir"] == str(tmp_path / "pf" / "mklinktool")
        assert captured["use_task"] is True
        assert captured["file_opts"] == "/f"
        assert captured["all_users"] is True


class TestRepair:
    def test_repair_reuses_installed_location_and_settings(
        self, monkeypatch, tmp_path, capsys
    ):
        install_dir = tmp_path / "mklinktool"
        install_dir.mkdir()
        (install_dir / "mklinktool.conf").write_text(
            "[settings]\n"
            "task = False\n"
            "wildcardloops = False\n"
            "scriptdefaultfileoptions = /h\n"
            "scriptdefaultfolderoptions = /j\n"
            "adminfileoptions = /f\n"
            "adminfolderopts = /d\n"
            "adminfree = True\n"
            "allusers = False\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "pf"))
        monkeypatch.setattr(
            installer, "_existing_install", lambda basename: str(install_dir)
        )
        captured = {}
        monkeypatch.setattr(
            installer,
            "_do_install",
            lambda basename, cfg: captured.update(cfg),
        )
        installer.run_repair("mklinktool")
        assert captured["install_dir"] == str(install_dir)
        assert captured["file_opts"] == "/h"
        assert "Repair complete!" in capsys.readouterr().out

    def test_repair_without_installation_reports(self, monkeypatch, capsys):
        monkeypatch.setattr(installer, "_existing_install", lambda basename: None)
        installer.run_repair("mklinktool")
        out = capsys.readouterr().out
        assert "No installation found to repair" in out

    def test_repair_rebuilds_config_when_conf_is_lost(
        self, monkeypatch, tmp_path, capsys
    ):
        install_dir = tmp_path / "mklinktool"
        install_dir.mkdir()
        monkeypatch.setattr(
            installer, "_existing_install", lambda basename: str(install_dir)
        )
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "pf"))
        captured = {}
        monkeypatch.setattr(
            installer,
            "_do_install",
            lambda basename, cfg: captured.update(cfg),
        )
        installer.run_repair("mklinktool")
        assert captured["install_dir"] == str(install_dir)
        assert captured["all_users"] is False
        assert captured["file_opts"] == "/f"
