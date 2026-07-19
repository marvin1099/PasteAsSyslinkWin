"""CLI argument parsing and flag processing."""

VALID_FLAGS = {"/f", "/d", "/h", "/j", "/w", "/m", "/u", "/r", "/e"}


def parse_flags(args: list[str], filter_mode: str = "") -> dict:
    """Parse mklink-style flags into a structured result.

    /f and /d are MODE SWITCHERS that control whether subsequent flags
    apply to files or folders. They are NOT passed to mklink directly.
    Only /h and /j are actual mklink flags.

    Args:
        args: List of flag strings (e.g. ["/f", "/h", "/d", "/j"]).
        filter_mode: If "/e", detect admin-required operations.
                     Empty for normal operation.

    Returns:
        Dict with keys:
            file_flags: mklink flags for file operations (e.g. ["/h"])
            folder_flags: mklink flags for folder operations (e.g. ["/d", "/j"])
            wildcard: bool or None
            install_mode: True (uninstall), False (re-add), None (normal)
            admin_file_flags: admin-required file flags (only when filter_mode="/e")
            admin_folder_flags: admin-required folder flags (only when filter_mode="/e")
    """
    result = {
        "file_flags": [],
        "folder_flags": [],
        "wildcard": None,
        "install_mode": None,
        "admin_file_flags": [],
        "admin_folder_flags": [],
    }

    is_file_mode = True
    is_admin_detect = filter_mode == "/e"

    track_admin_files = [] if is_admin_detect else None
    track_admin_folders = [] if is_admin_detect else None

    for arg in args:
        flag = arg.strip().lower()
        if flag not in VALID_FLAGS:
            continue

        if flag == "/f":
            is_file_mode = True
            if is_admin_detect and track_admin_files is not None:
                track_admin_files.append("/f")

        elif flag == "/d":
            is_file_mode = False
            if is_admin_detect and track_admin_folders is not None:
                track_admin_folders.append("/d")

        elif flag == "/h":
            if is_file_mode:
                result["file_flags"].append("/h")
                if is_admin_detect and track_admin_files is not None:
                    track_admin_files.append("/h")
            else:
                result["folder_flags"].append("/h")
                if is_admin_detect and track_admin_folders is not None:
                    track_admin_folders.append("/h")

        elif flag == "/j":
            result["folder_flags"].append("/j")
            if is_admin_detect and track_admin_folders is not None:
                track_admin_folders.append("/j")

        elif flag == "/w":
            result["wildcard"] = True

        elif flag == "/m":
            result["wildcard"] = False

        elif flag == "/u":
            result["install_mode"] = True

        elif flag == "/r":
            result["install_mode"] = False

    if is_admin_detect:
        admin_file_flags = []
        admin_folder_flags = []
        if track_admin_files and len(track_admin_files) >= 2:
            admin_file_flags = [f for f in track_admin_files if f != "/f"]
            if not admin_file_flags:
                admin_file_flags = ["/f"]
        if track_admin_folders and len(track_admin_folders) >= 2:
            admin_folder_flags = [f for f in track_admin_folders if f != "/d"]
            if not admin_folder_flags:
                admin_folder_flags = ["/d"]
        result["admin_file_flags"] = admin_file_flags
        result["admin_folder_flags"] = admin_folder_flags

    return result


def build_file_flags(result: dict) -> str:
    """Build mklink flag string for file operations (no /f prefix)."""
    flags = result["file_flags"]
    return " ".join(flags) if flags else ""


def build_folder_flags(result: dict) -> str:
    """Build mklink flag string for folder operations (includes /d prefix)."""
    flags = result["folder_flags"]
    other = [f for f in flags if f != "/d"]
    parts = ["/d"] + other
    return " ".join(parts)
