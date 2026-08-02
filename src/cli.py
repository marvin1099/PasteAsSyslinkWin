"""CLI argument parsing and flag processing."""

import re
from pathlib import PureWindowsPath

# Each flag maps to exactly one operation:
#   /f = file symlink (mklink default, no flag needed)
#   /d = dir symlink  (mklink /d)
#   /h = file hardlink (mklink /h)
#   /j = dir junction  (mklink /j)
VALID_FLAGS = {
    "/f", "/d", "/h", "/j", "/w", "/m", "/u", "/i",
    "/install", "/uninstall", "/clip", "/noclip",
}

# Shell metacharacters that could enable injection via cmd /c mklink.
# Only characters that stay dangerous even inside list2cmdline quotes are
# blocked: `|`, `<`, `>` are cmd operators, `^` escapes even when quoted,
# `"` breaks quoting. `&` and backtick are inert inside double quotes and
# are valid Windows filename characters, so they are allowed.
_SHELL_METACHARACTERS = re.compile(r'[|<>^"\x00\r\n]')


def parse_flags(args: list[str]) -> dict:
    """Parse mklink-style flags into a structured result.

    Each flag maps to exactly one operation:
        /f → file symlink    /d → dir symlink
        /h → file hardlink   /j → dir junction
    /w and /m control wildcard expansion, /u and /r control install mode,
    /clip and /noclip control clipboard usage.

    Args:
        args: List of flag strings (e.g. ["/f", "/h", "/d", "/j"]).

    Returns:
        Dict with keys:
            file_flags: operation flags for files (e.g. ["/f", "/h"])
            folder_flags: operation flags for folders (e.g. ["/d", "/j"])
            wildcard: bool or None
            install_mode: True (uninstall), False (re-add), None (normal)
    """
    result = {
        "file_flags": [],
        "folder_flags": [],
        "wildcard": None,
        "install_mode": None,
        "clip": None,
    }

    for arg in args:
        flag = arg.strip().lower()
        if flag not in VALID_FLAGS:
            continue

        if flag == "/f":
            result["file_flags"].append("/f")
        elif flag == "/d":
            result["folder_flags"].append("/d")
        elif flag == "/h":
            result["file_flags"].append("/h")
        elif flag == "/j":
            result["folder_flags"].append("/j")
        elif flag == "/w":
            result["wildcard"] = True
        elif flag == "/m":
            result["wildcard"] = False
        elif flag == "/u" or flag == "/uninstall":
            result["install_mode"] = True
        elif flag == "/i" or flag == "/install":
            result["install_mode"] = False
        elif flag == "/clip":
            result["clip"] = True
        elif flag == "/noclip":
            result["clip"] = False

    return result


def parse_admin_opts(opts_str: str) -> list[str]:
    """Parse admin opts string into a list of flags that need elevation.

    Admin opts are operation flags (/f, /h, /d, /j).
    """
    return [f for f in opts_str.split() if f in {"/f", "/h", "/d", "/j"}]


def build_file_flags(result: dict) -> str:
    """Build mklink flag string for file operations.

    /f (file symlink) → "" (mklink default = file symlink)
    /h (file hardlink) → "/h"
    """
    return "/h" if "/h" in result["file_flags"] else ""


def build_folder_flags(result: dict) -> str:
    """Build mklink flag string for folder operations.

    /d (dir symlink) → "/d"
    /j (dir junction) → "/j"
    /j implies directory so /d is not prepended when /j is present.
    Default (no folder flags) → "/d" (dir symlink).
    """
    flags = result["folder_flags"]
    if "/j" in flags:
        return "/j"
    return "/d"


def validate_path(path: str) -> str | None:
    """Check a path for validity and shell injection characters.

    Returns the path if safe, or None if invalid.
    Uses PureWindowsPath for structural validation, then rejects
    shell metacharacters (& | < > ^ ` " etc.) that could enable
    injection via cmd /c mklink.
    """
    if not path:
        return None
    try:
        p = PureWindowsPath(path)
        if p.drive and not p.root:
            return None
    except (ValueError, OSError):
        return None
    if _SHELL_METACHARACTERS.search(path):
        return None
    return path


def validate_args(args: list[str]) -> tuple[list[str], list[str]]:
    """Validate all arguments: flags must be valid, paths must be safe.

    Returns:
        (valid_flags, valid_paths) — lists of validated arguments.
        Invalid args are silently dropped.
    """
    flags = []
    paths = []
    for arg in args:
        arg_stripped = arg.strip()
        if not arg_stripped:
            continue
        # A forward-slash UNC path (//server/share) must not be mistaken for
        # a flag just because it starts with "/".
        if arg_stripped.startswith("//"):
            if validate_path(arg_stripped) is not None:
                paths.append(arg_stripped)
        elif arg_stripped.startswith("/"):
            if arg_stripped.lower() in VALID_FLAGS:
                flags.append(arg_stripped)
        else:
            if validate_path(arg_stripped) is not None:
                paths.append(arg_stripped)
    return flags, paths
