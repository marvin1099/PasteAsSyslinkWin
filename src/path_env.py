"""Windows PATH environment variable management via registry."""

import ctypes
import winreg

BroadcastMessage = ctypes.windll.user32.SendMessageW
HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A

HKLM_ENV = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
HKCU_ENV = r"Environment"


def _read_path(hive: int) -> str:
    """Read the PATH value from the registry."""
    try:
        key = winreg.OpenKey(
            hive, HKCU_ENV if hive == winreg.HKEY_CURRENT_USER else HKLM_ENV, 0, winreg.KEY_READ
        )
        value, _ = winreg.QueryValueEx(key, "Path")
        winreg.CloseKey(key)
        return value or ""
    except OSError:
        return ""


def _write_path(hive: int, path: str) -> None:
    """Write the PATH value to the registry."""
    subkey = HKCU_ENV if hive == winreg.HKEY_CURRENT_USER else HKLM_ENV
    key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, path)
    winreg.CloseKey(key)


def _broadcast() -> None:
    """Broadcast WM_SETTINGCHANGE so other processes pick up PATH changes."""
    BroadcastMessage(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment")


def add_to_path(directory: str, all_users: bool = False) -> bool:
    """Add a directory to the user or system PATH.

    Returns True if the path was added (or already present).
    """
    directory = directory.rstrip("\\")
    hive = winreg.HKEY_LOCAL_MACHINE if all_users else winreg.HKEY_CURRENT_USER
    current = _read_path(hive)
    entries = [e for e in current.split(";") if e.strip()]

    normalized = [e.rstrip("\\").lower() for e in entries]
    if directory.lower() in normalized:
        return True

    entries.append(directory)
    new_path = ";".join(entries)
    try:
        _write_path(hive, new_path)
        _broadcast()
        return True
    except OSError:
        return False


def remove_from_path(directory: str, all_users: bool = False) -> bool:
    """Remove a directory from the user or system PATH.

    Returns True if the path was removed (or was not present).
    """
    directory = directory.rstrip("\\").lower()
    hive = winreg.HKEY_LOCAL_MACHINE if all_users else winreg.HKEY_CURRENT_USER
    current = _read_path(hive)
    entries = [e for e in current.split(";") if e.strip()]

    new_entries = [e for e in entries if e.rstrip("\\").lower() != directory]
    if len(new_entries) == len(entries):
        return True

    new_path = ";".join(new_entries)
    try:
        _write_path(hive, new_path)
        _broadcast()
        return True
    except OSError:
        return False


def is_in_path(directory: str, all_users: bool = False) -> bool:
    """Check if a directory is already in PATH."""
    directory = directory.rstrip("\\").lower()
    hive = winreg.HKEY_LOCAL_MACHINE if all_users else winreg.HKEY_CURRENT_USER
    current = _read_path(hive)
    return any(e.rstrip("\\").lower() == directory for e in current.split(";") if e.strip())
