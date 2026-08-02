"""Windows context menu registration (classic context menu)."""

import contextlib
import os
import sys
import winreg

BASENAME = "mklinktool"


def _exe_command(exe_path: str) -> str:
    """Build the shell command string for the context menu."""
    if getattr(sys, "frozen", False):
        return f'"{exe_path}"'
    if os.path.splitext(exe_path)[1].lower() == ".py":
        return f'"{sys.executable}" "{exe_path}"'
    return f'"{exe_path}"'


def _get_icon_path(exe_path: str) -> str:
    """Get the icon path - exe itself if compiled, else look for .ico."""
    if getattr(sys, "frozen", False):
        return exe_path
    ico = os.path.join(os.path.dirname(exe_path), f"{BASENAME}.ico")
    if os.path.isfile(ico):
        return ico
    return exe_path


def _write_entry(
    root, subkey: str, label: str, ico: str, cmd: str, full_opts: str
) -> bool:
    """Write one context menu entry under ``root``. Returns True on success."""
    try:
        key = winreg.CreateKeyEx(root, subkey, 0, winreg.KEY_ALL_ACCESS)
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, label)
        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, ico)
        winreg.CloseKey(key)

        cmd_key = winreg.CreateKeyEx(root, f"{subkey}\\command", 0, winreg.KEY_ALL_ACCESS)
        winreg.SetValueEx(cmd_key, None, 0, winreg.REG_SZ, f'{cmd} {full_opts}"%V"')
        winreg.CloseKey(cmd_key)
        return True
    except OSError:
        return False


def add_context_menu(exe_path: str, file_opts: str = "", folder_opts: str = "") -> None:
    r"""Add context menu entries to the classic context menu.

    Tries machine-wide first (HKCR, requires admin), falling back to the
    current user's classes view (HKCU\Software\Classes, no admin needed).

    Note: On Windows 11 the classic menu appears via "Show more options".
    """
    icon = _get_icon_path(exe_path)
    cmd = _exe_command(exe_path)
    full_opts = f"{file_opts} {folder_opts}".strip()
    if full_opts:
        full_opts = full_opts + " "

    entries = [
        (r"Directory\shell\SysLink", "Create Symlinks Here", icon),
        (r"Directory\Background\shell\SysLink", "Create Symlinks Here", icon),
    ]

    for subkey, label, ico in entries:
        for root in (winreg.HKEY_CLASSES_ROOT, winreg.HKEY_CURRENT_USER):
            full_subkey = (
                subkey if root is winreg.HKEY_CLASSES_ROOT else "Software\\Classes\\" + subkey
            )
            if _write_entry(root, full_subkey, label, ico, cmd, full_opts):
                break


def remove_context_menu() -> None:
    """Remove classic context menu entries (machine-wide and per-user)."""
    keys = [
        r"Directory\shell\SysLink",
        r"Directory\Background\shell\SysLink",
    ]
    for root in (winreg.HKEY_CLASSES_ROOT, winreg.HKEY_CURRENT_USER):
        for subkey in keys:
            full_subkey = (
                subkey if root is winreg.HKEY_CLASSES_ROOT else "Software\\Classes\\" + subkey
            )
            with contextlib.suppress(OSError):
                winreg.DeleteKeyEx(root, f"{full_subkey}\\command")
            with contextlib.suppress(OSError):
                winreg.DeleteKeyEx(root, full_subkey)
