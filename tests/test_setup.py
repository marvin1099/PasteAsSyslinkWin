"""Tests for the mklinktool-setup entry point and installer core."""

import os
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


class TestSelfDelete:
    def test_cleanup_cmd_runs_outside_install_dir(self, monkeypatch, tmp_path):
        """The hidden launcher sets our cwd into the install dir - a cmd
        whose own cwd is the target cannot rmdir it, so spawn it elsewhere."""
        import subprocess

        captured = {}
        monkeypatch.setattr(
            subprocess,
            "Popen",
            lambda cmd, **kwargs: captured.update(cmd=cmd, **kwargs),
        )
        monkeypatch.setenv("SystemRoot", r"C:\Windows")
        installer._schedule_self_delete(
            str(tmp_path), [str(tmp_path / "mklinktool-setup.exe")]
        )
        assert captured["cwd"] == r"C:\Windows"
        assert str(tmp_path) in captured["cmd"]


class TestInstalledFromSelf:
    def test_source_run_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
        assert installer._installed_from_self("mklinktool") is None

    def test_frozen_setup_with_conf_marks_installation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "mklinktool-setup.exe"))
        (tmp_path / "mklinktool.conf").write_text("[settings]\n", encoding="utf-8")
        assert installer._installed_from_self("mklinktool") == str(tmp_path)

    def test_frozen_setup_beside_tool_exe_marks_installation(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "mklinktool-setup.exe"))
        (tmp_path / "mklinktool.exe").write_text("MZ", encoding="utf-8")
        assert installer._installed_from_self("mklinktool") == str(tmp_path)

    def test_frozen_setup_outside_installation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "mklinktool-setup.exe"))
        assert installer._installed_from_self("mklinktool") is None


class TestUninstallDispatch:
    """The uninstall must target the installation the setup exe lives in."""

    @staticmethod
    def _run(monkeypatch, tmp_path, argv, setup_dir):
        from src import setup_main

        monkeypatch.setattr(sys, "argv", ["mklinktool-setup.exe", *argv])
        monkeypatch.setattr(
            installer,
            "_installed_from_self",
            lambda b: str(setup_dir) if setup_dir else None,
        )
        monkeypatch.setattr(
            installer, "_existing_install", lambda b: str(tmp_path / "registry")
        )
        captured = {}
        monkeypatch.setattr(
            installer,
            "run_uninstaller",
            lambda basename, install_dir, use_task, quiet=False: captured.update(
                install_dir=install_dir, quiet=quiet
            ),
        )
        setup_main._main_impl()
        return captured

    def test_uninstall_prefers_self_directory(self, monkeypatch, tmp_path):
        setup_dir = tmp_path / "inst"
        setup_dir.mkdir()
        (setup_dir / "mklinktool.conf").write_text(
            "[settings]\ntask = False\n", encoding="utf-8"
        )
        captured = self._run(monkeypatch, tmp_path, ["/uninstall", "/nogui"], setup_dir)
        assert captured["install_dir"] == str(setup_dir)
        assert captured["quiet"] is True

    def test_uninstall_falls_back_to_registry(self, monkeypatch, tmp_path):
        captured = self._run(monkeypatch, tmp_path, ["/uninstall"], None)
        assert captured["install_dir"] == str(tmp_path / "registry")
        assert captured["quiet"] is False


class TestUninstallFlow:
    @staticmethod
    def _recorder(monkeypatch):
        import src.context_menu as context_menu

        calls = []
        monkeypatch.setattr(
            installer,
            "elevate_force_uac",
            lambda basename, flags: calls.append(("elevate", tuple(flags))),
        )
        monkeypatch.setattr(
            installer.task_scheduler,
            "delete_task",
            lambda b: calls.append(("task", b)),
        )
        monkeypatch.setattr(
            installer,
            "remove_from_path",
            lambda d, all_users=False: calls.append(("path", all_users)),
        )
        monkeypatch.setattr(
            installer,
            "remove_uninstall_entry",
            lambda all_users=False: calls.append(("entry", all_users)),
        )
        monkeypatch.setattr(
            installer,
            "_schedule_self_delete",
            lambda install_dir, paths: calls.append(("selfdel",)),
        )
        monkeypatch.setattr(
            context_menu, "remove_context_menu", lambda: calls.append(("ctx",))
        )
        return calls

    @staticmethod
    def _write_conf(install_dir, all_users):
        install_dir.mkdir(parents=True, exist_ok=True)
        (install_dir / "mklinktool.conf").write_text(
            f"[settings]\ntask = False\nallusers = {all_users}\n", encoding="utf-8"
        )

    def test_all_users_uninstall_relaunches_elevated(self, monkeypatch, tmp_path):
        install_dir = tmp_path / "pf" / "mklinktool"
        self._write_conf(install_dir, "True")
        monkeypatch.setattr(installer, "is_admin", lambda: False)
        calls = self._recorder(monkeypatch)
        installer.run_uninstaller("mklinktool", str(install_dir), False, quiet=True)
        # Only the elevation relaunch - no half-removal from the medium shell.
        assert calls == [("elevate", ("/uninstall", "/nogui"))]

    def test_user_uninstall_runs_directly(self, monkeypatch, tmp_path, capsys):
        install_dir = tmp_path / "mklinktool"
        self._write_conf(install_dir, "False")
        monkeypatch.setattr(installer, "is_admin", lambda: False)
        calls = self._recorder(monkeypatch)
        installer.run_uninstaller("mklinktool", str(install_dir), False, quiet=True)
        kinds = [c[0] for c in calls]
        assert "elevate" not in kinds
        assert "ctx" in kinds and "selfdel" in kinds
        assert calls.count(("entry", True)) == 1 and calls.count(("entry", False)) == 1
        assert "Uninstallation complete!" in capsys.readouterr().out

    def test_config_delete_failure_does_not_abort(self, monkeypatch, tmp_path, capsys):
        install_dir = tmp_path / "mklinktool"
        self._write_conf(install_dir, "False")
        monkeypatch.setattr(installer, "is_admin", lambda: False)

        class GrumpyConfig:
            def __init__(self, install_dir, basename):
                self.path = os.path.join(install_dir, "mklinktool.conf")
                self.all_users = False
                self.task = False

            def load(self):
                return True

            def delete(self):
                raise PermissionError(13, "Access is denied")

        monkeypatch.setattr(installer, "Config", GrumpyConfig)
        calls = self._recorder(monkeypatch)
        installer.run_uninstaller("mklinktool", str(install_dir), True, quiet=True)
        out = capsys.readouterr().out
        assert "Warning: could not remove" in out
        assert "Uninstallation complete!" in out
        kinds = [c[0] for c in calls]
        assert "task" in kinds and "ctx" in kinds and "selfdel" in kinds
