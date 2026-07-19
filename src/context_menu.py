"""Windows context menu registration for Win10 and Win11."""

import contextlib
import os
import sys
import winreg

BASENAME = "mklinktool"


def _exe_command(exe_path: str) -> str:
    """Build the shell command string for the context menu."""
    if getattr(sys, "frozen", False):
        return f'"{exe_path}"'
    python_exe = sys.executable
    return f'"{python_exe}" "{exe_path}"'


def _get_icon_path(exe_path: str) -> str:
    """Get the icon path - exe itself if compiled, else look for .ico."""
    if getattr(sys, "frozen", False):
        return exe_path
    ico = os.path.join(os.path.dirname(exe_path), f"{BASENAME}.ico")
    if os.path.isfile(ico):
        return ico
    return exe_path


def add_context_menu_win10(exe_path: str, file_opts: str = "", folder_opts: str = "") -> None:
    r"""Add context menu entries for Windows 10 (classic context menu).

    Registers under:
        HKCR\Directory\shell\SysLink
        HKCR\Directory\Background\shell\SysLink
    """
    icon = _get_icon_path(exe_path)
    cmd = _exe_command(exe_path)
    full_opts = f"{file_opts} {folder_opts}".strip()
    if full_opts:
        full_opts = full_opts + " "

    entries = [
        (winreg.HKEY_CLASSES_ROOT, r"Directory\shell\SysLink", "Create Symlinks Here", icon),
        (
            winreg.HKEY_CLASSES_ROOT,
            r"Directory\Background\shell\SysLink",
            "Create Symlinks Here",
            icon,
        ),
    ]

    for root, subkey, label, ico in entries:
        try:
            key = winreg.CreateKeyEx(root, subkey, 0, winreg.KEY_ALL_ACCESS)
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, label)
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, ico)
            winreg.CloseKey(key)

            cmd_key = winreg.CreateKeyEx(root, f"{subkey}\\command", 0, winreg.KEY_ALL_ACCESS)
            winreg.SetValueEx(cmd_key, None, 0, winreg.REG_SZ, f'{cmd} {full_opts}"%V"')
            winreg.CloseKey(cmd_key)
        except OSError:
            pass


def add_context_menu_win11(exe_path: str, file_opts: str = "", folder_opts: str = "") -> None:
    """Add a modern Windows 11 context menu entry via CLSID registration.

    This adds a "Direct" entry that appears in the Win11 context menu directly,
    plus a "Show more options" fallback for Win10 compatibility.
    """
    icon = _get_icon_path(exe_path)
    cmd = _exe_command(exe_path)
    full_opts = f"{file_opts} {folder_opts}".strip()
    if full_opts:
        full_opts = full_opts + " "

    clsid = "{8ECA9B20-A7C9-4D6B-B2C5-3B5B8E5C1234}"
    menu_text = "Create Symlinks Here"

    try:
        base_key = winreg.CreateKeyEx(
            winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}\\InprocServer32", 0, winreg.KEY_ALL_ACCESS
        )
        winreg.SetValueEx(base_key, None, 0, winreg.REG_SZ, "")
        winreg.SetValueEx(base_key, "ThreadingModel", 0, winreg.REG_SZ, "Both")
        winreg.CloseKey(base_key)

        shell_key = winreg.CreateKeyEx(
            winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}\\shell", 0, winreg.KEY_ALL_ACCESS
        )
        winreg.SetValueEx(shell_key, None, 0, winreg.REG_SZ, menu_text)
        winreg.CloseKey(shell_key)

        cmd_key = winreg.CreateKeyEx(
            winreg.HKEY_CLASSES_ROOT,
            f"CLSID\\{clsid}\\shell\\open\\command",
            0,
            winreg.KEY_ALL_ACCESS,
        )
        winreg.SetValueEx(cmd_key, None, 0, winreg.REG_SZ, f'{cmd} {full_opts}"%V"')
        winreg.CloseKey(cmd_key)

        icon_key = winreg.CreateKeyEx(
            winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}", 0, winreg.KEY_ALL_ACCESS
        )
        winreg.SetValueEx(icon_key, "Icon", 0, winreg.REG_SZ, icon)
        winreg.CloseKey(icon_key)
    except OSError:
        pass


def remove_context_menu_win10() -> None:
    """Remove Win10 context menu entries."""
    keys = [
        r"Directory\shell\SysLink",
        r"Directory\Background\shell\SysLink",
    ]
    for subkey in keys:
        with contextlib.suppress(OSError):
            winreg.DeleteKeyEx(
                winreg.HKEY_CLASSES_ROOT, f"{subkey}\\command", 0, winreg.KEY_ALL_ACCESS
            )
        with contextlib.suppress(OSError):
            winreg.DeleteKeyEx(winreg.HKEY_CLASSES_ROOT, subkey, 0, winreg.KEY_ALL_ACCESS)


def remove_context_menu_win11() -> None:
    """Remove Win11 context menu entries."""
    clsid = "{8ECA9B20-A7C9-4D6B-B2C5-3B5B8E5C1234}"
    paths = [
        f"CLSID\\{clsid}\\shell\\open\\command",
        f"CLSID\\{clsid}\\shell\\open",
        f"CLSID\\{clsid}\\shell",
        f"CLSID\\{clsid}\\InprocServer32",
        f"CLSID\\{clsid}",
    ]
    for subkey in paths:
        with contextlib.suppress(OSError):
            winreg.DeleteKeyEx(winreg.HKEY_CLASSES_ROOT, subkey, 0, winreg.KEY_ALL_ACCESS)


def detect_windows_version() -> int:
    """Detect Windows version. Returns 11+ or 10."""
    try:
        ver = sys.getwindowsversion()
        if ver.major >= 10 and ver.build >= 22000:
            return 11
        return 10
    except Exception:
        return 10
