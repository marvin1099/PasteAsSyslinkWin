"""Path resolution with wildcard/glob support."""

import glob
import os


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
        import ctypes

        mpr = ctypes.windll.mpr
        mpr.WNetGetConnectionW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(len(buf))
        result = mpr.WNetGetConnectionW(drive, buf, ctypes.byref(size))
    except Exception:
        return path
    if result == 0 and buf.value:
        return buf.value + rest
    return path


def resolve_paths(patterns: list[str], wildcard_loops: bool = False) -> tuple[list[str], list[str]]:
    """Resolve path patterns to actual files and folders.

    Args:
        patterns: List of path patterns (may contain wildcards like * and ?).
        wildcard_loops: If True, expand wildcards to all matches.
                        If False, use only the first match per pattern.

    Returns:
        Tuple of (file_paths, folder_paths).
    """
    files = []
    folders = []

    for pattern in patterns:
        if not pattern:
            continue
        pattern = pattern.rstrip("\\")
        if not pattern:
            continue

        if any(c in pattern for c in "*?"):
            matches = glob.glob(pattern, recursive=False)
            for match in matches:
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
