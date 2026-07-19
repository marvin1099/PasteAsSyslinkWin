"""Configuration management for PasteAsSyslinkWin."""

import configparser
import os


class Config:
    """Manages the tool's INI configuration file."""

    DEFAULTS = {
        "task": "True",
        "wildcardloops": "False",
        "scriptdefaultfileoptions": "/f",
        "scriptdefaultfolderoptions": "/d /j",
        "adminfileoptions": "/f /h",
        "adminfolderoptions": "/d /h /j",
    }

    def __init__(self, install_dir: str, basename: str = "mklinktool"):
        self.install_dir = install_dir
        self.basename = basename
        self.path = os.path.join(install_dir, f"{basename}.conf")
        self._parser = configparser.ConfigParser()
        self._loaded = False

        self.task: bool = True
        self.wildcard_loops: bool = False
        self.script_default_file_opts: str = "/f"
        self.script_default_folder_opts: str = "/d /j"
        self.admin_file_opts: str = "/f /h"
        self.admin_folder_opts: str = "/d /h /j"
        self.all_users: bool = False

    def exists(self) -> bool:
        return os.path.isfile(self.path)

    def load(self) -> bool:
        """Load config from disk. Returns True if successful."""
        if not self.exists():
            return False
        self._parser.read(self.path, encoding="utf-8")
        if not self._parser.has_section("settings"):
            return False

        self.task = self._parser.get("settings", "task", fallback="True").lower() == "true"
        self.wildcard_loops = (
            self._parser.get("settings", "wildcardloops", fallback="False").lower() == "true"
        )
        self.script_default_file_opts = self._parser.get(
            "settings", "scriptdefaultfileoptions", fallback="/f"
        )
        self.script_default_folder_opts = self._parser.get(
            "settings", "scriptdefaultfolderoptions", fallback="/d /j"
        )
        self.admin_file_opts = self._parser.get("settings", "adminfileoptions", fallback="/f /h")
        self.admin_folder_opts = self._parser.get(
            "settings", "adminfolderoptions", fallback="/d /h /j"
        )
        self.all_users = (
            self._parser.get("settings", "allusers", fallback="False").lower() == "true"
        )
        self._loaded = True
        return True

    def save(self) -> bool:
        """Write config to disk."""
        self._parser["settings"] = {
            "task": str(self.task),
            "wildcardloops": str(self.wildcard_loops),
            "scriptdefaultfileoptions": self.script_default_file_opts,
            "scriptdefaultfolderoptions": self.script_default_folder_opts,
            "adminfileoptions": self.admin_file_opts,
            "adminfolderoptions": self.admin_folder_opts,
            "allusers": str(self.all_users),
        }
        os.makedirs(self.install_dir, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            self._parser.write(f)
        return True

    def delete(self) -> None:
        """Remove the config file."""
        if self.exists():
            os.remove(self.path)
