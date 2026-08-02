"""Windows 'Apps & Features' uninstall registry entry management."""

import os
import winreg

_UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\mklinktool"


def add_uninstall_entry(
    install_dir: str, exe_path: str, all_users: bool = False
) -> bool:
    """Create an uninstall entry in Windows Settings > Apps."""
    hive = winreg.HKEY_LOCAL_MACHINE if all_users else winreg.HKEY_CURRENT_USER
    subkey = _UNINSTALL_KEY
    icon_path = os.path.join(install_dir, "mklinktool.ico")
    icon = icon_path if os.path.isfile(icon_path) else exe_path
    try:
        key = winreg.CreateKeyEx(hive, subkey, 0, winreg.KEY_ALL_ACCESS)
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "PasteAsSyslinkWin")
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, icon)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "0.9")
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, 5000)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "PasteAsSyslinkWin")
        uninstall_cmd = f'"{exe_path}" /uninstall'
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninstall_cmd)
        quiet_cmd = f'"{exe_path}" /uninstall /nogui'
        winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, quiet_cmd)
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def remove_uninstall_entry(all_users: bool = False) -> bool:
    """Remove the uninstall entry from the registry."""
    hive = winreg.HKEY_LOCAL_MACHINE if all_users else winreg.HKEY_CURRENT_USER
    subkey = _UNINSTALL_KEY
    try:
        winreg.DeleteKeyEx(hive, subkey)
        return True
    except OSError:
        return False


def get_installed_location() -> str | None:
    """Read InstallLocation from the uninstall registry entry.

    Checks both HKLM and HKCU. Returns the path if found, None otherwise.
    """
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(hive, _UNINSTALL_KEY, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "InstallLocation")
            winreg.CloseKey(key)
            if value:
                return str(value)
        except OSError:
            pass
    return None
