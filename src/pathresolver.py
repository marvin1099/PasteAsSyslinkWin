"""Path resolution with wildcard/glob support."""

# Module-level ctypes setup: avoids re-declaring argtypes on every call.
import ctypes
import glob
import os
from ctypes import wintypes

_mpr = ctypes.WinDLL("mpr", use_last_error=True)
_mpr.WNetGetConnectionW.argtypes = [
    wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
]
_mpr.WNetGetConnectionW.restype = wintypes.DWORD


def to_unc_path(path: str) -> str:
    """Convert a mapped-drive path to its UNC form; return other paths unchanged.

    Mapped network drives (net use) are per-session, so an elevated process
    may not see them. Resolving the drive letter to its UNC share makes the
    path usable in the elevated process.
    """
    drive, rest = os.path.splitdrive(path)
    if not drive:
        return path
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if _mpr.WNetGetConnectionW(drive, buf, ctypes.byref(size)) == 0 and buf.value:
            return buf.value + rest
    except Exception:
        pass
    return path


def resolve_paths(
    patterns: list[str], wildcard_loops: bool = False
) -> tuple[list[str], list[str]]:
    """Resolve path patterns to actual files and folders.

    Args:
        patterns: List of path patterns (may contain wildcards like * and ?).
        wildcard_loops: If True, expand wildcards to all matches.
                        If False, use only the first match per pattern.

    Returns:
        Tuple of (file_paths, folder_paths).
    """
    files: list[str] = []
    folders: list[str] = []

    for pattern in patterns:
        if not pattern:
            continue
        pattern = pattern.rstrip("\\")
        if not pattern:
            continue

        if any(c in pattern for c in "*?"):
            for match in glob.glob(pattern, recursive=False):
                if os.path.isdir(match):
                    folders.append(os.path.normpath(match))
                elif os.path.isfile(match):
                    files.append(os.path.normpath(match))
                if not wildcard_loops:
                    break
        elif os.path.exists(pattern):
            norm = os.path.normpath(pattern)
            if os.path.isdir(norm):
                folders.append(norm)
            elif os.path.isfile(norm):
                files.append(norm)

    return files, folders
