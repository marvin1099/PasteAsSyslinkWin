"""PasteAsSyslinkWin - Main entry point.

A CLI tool and context menu integration for creating symlinks
by copying files/folders and pasting them as symlinks.
"""

import contextlib
import os
import subprocess
import sys

from src import task_scheduler, writeback
from src.cli import (
    build_file_flags,
    build_folder_flags,
    parse_admin_opts,
    parse_flags,
    validate_args,
)
from src.clipboard import get_clipboard_paths
from src.config import SETUP_EXE_NAME, Config
from src.elevation import (
    elevate,
    elevate_force_uac,
    get_exe_path,
    is_admin,
)
from src.pathresolver import resolve_paths, to_unc_path
from src.symlink_ops import (
    create_write_probe,
    process_links,
    remove_probe_files,
    verify_write_probe,
)

BASENAME = "mklinktool"


def get_install_dir() -> str:
    """Find the install directory by searching for the config file."""
    script_dir = os.path.dirname(sys.executable)
    # 1. Config next to exe/script (normal install or running from install dir)
    if os.path.isfile(os.path.join(script_dir, f"{BASENAME}.conf")):
        return script_dir
    # 2. Check known install locations (when launched from PATH / context menu)
    candidates = [
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""), BASENAME
        ),
        os.path.join(
            os.environ.get("PROGRAMFILES", ""), BASENAME
        ),
    ]
    for path in candidates:
        if path and os.path.isfile(os.path.join(path, f"{BASENAME}.conf")):
            return path
    # 3. Fallback: exe/script directory (portable mode: no config anywhere)
    return script_dir


HELP_TEXT = """PasteAsSyslinkWin - Usage:
  mklinktool [/flags] [paths...]   Create symlinks from clipboard
  mklinktool /resetconfig            Remove config
  mklinktool /reconfigure            Remove config and re-run setup
  mklinktool /adminfree             Skip admin-needing ops instead of elevating
  mklinktool /help                  Show this help
  mklinktool /?                     Show this help

Setup (mklinktool-setup.exe):
  (no flags)          Interactive install/repair wizard
  /nogui              Silent install (current user)
  /noguiall           Silent install (all users)
  /repair             Repair installation (keeps settings)
  /uninstall [/nogui] Uninstall (add /nogui to skip prompts)

Flags (for symlink creation):
  /f   File symlink (mklink default, no flag needed)
  /d   Directory symlink (mklink /d)
  /h   File hard link (mklink /h)
  /j   Directory junction (mklink /j)
  /w   Enable wildcard loop expansion
  /m   Disable wildcard loop expansion (overrides installed config)

Path logic:
  Last argument is always the destination folder.
  All other arguments are source paths (files/folders to link).
  Clipboard is used as sources only (never destination).
  With 2+ args: clipboard ignored unless /clip is set.
  With 1 arg: clipboard provides sources (disable with /noclip).

Clipboard control:
  /clip    Force include clipboard as additional sources
  /noclip  Disable clipboard entirely
"""


def _main_impl() -> None:
    if "/help" in sys.argv or "/?" in sys.argv:
        writeback.dbg(f"help-dispatch silent={writeback.is_silent()}")
        print(HELP_TEXT)
        return

    install_dir = get_install_dir()
    config = Config(install_dir, BASENAME)

    if "/resetconfig" in sys.argv or "/reconfigure" in sys.argv:
        config.delete()
        print(f"Config removed: {config.path}")
        if "/resetconfig" in sys.argv:
            return
        _launch_setup([])
        return

    if config.exists():
        config.load()
    else:
        # No installation anywhere: portable mode - run with the defaults in
        # memory, never write a config and never open the setup wizard.
        writeback.dbg("config-missing portable-defaults")

    _skip_flags = {
        "/restart",
        "/nogui",
        "/noguiall",
        "/adminfree",
        "/help",
        "/?",
        "/resetconfig",
        "/reconfigure",
        "/writeback",
    }
    cli_raw = [a for a in sys.argv[1:] if a not in _skip_flags]
    temp_raw = writeback.child_args()
    if temp_raw is None:
        temp_raw = task_scheduler.read_args_file(BASENAME)

    probe_arg = _find_probe_arg(cli_raw) or _find_probe_arg(temp_raw)

    cli_flags, cli_paths = validate_args(cli_raw)
    temp_flags, temp_paths = validate_args(temp_raw)
    all_args = cli_flags + cli_paths + temp_flags + temp_paths

    file_opts_combined = (
        (f"{config.script_default_file_opts} {config.script_default_folder_opts}").strip().split()
    )
    combined_args = file_opts_combined + all_args
    parsed = parse_flags(combined_args)

    wildcard = parsed["wildcard"]
    if wildcard is None:
        wildcard = config.wildcard_loops

    install_mode = parsed["install_mode"]
    if install_mode is True:
        # Uninstall belongs to the setup executable now - delegate to it.
        task_scheduler.delete_args_file(BASENAME)
        quiet = ["/nogui"] if "/nogui" in sys.argv else []
        _launch_setup(["/uninstall", *quiet])
        return

    if install_mode is False:
        # /install: open the setup wizard (it re-registers everything).
        task_scheduler.delete_args_file(BASENAME)
        _launch_setup([])
        return

    admin_file_flags = parse_admin_opts(config.admin_file_opts)
    admin_folder_flags = parse_admin_opts(config.admin_folder_opts)

    file_flags = build_file_flags(parsed)
    folder_flags = build_folder_flags(parsed)

    paths_from_args = cli_paths + temp_paths
    clip_mode = parsed["clip"]

    if len(paths_from_args) >= 2:
        dest_path_arg = paths_from_args[-1]
        source_paths_raw = paths_from_args[:-1]
        if clip_mode is True:
            clipboard_paths = get_clipboard_paths()
            source_paths_raw = source_paths_raw + clipboard_paths
    elif len(paths_from_args) == 1:
        dest_path_arg = paths_from_args[0]
        if clip_mode is not False:
            clipboard_paths = get_clipboard_paths()
            source_paths_raw = list(clipboard_paths)
        else:
            source_paths_raw = []
    else:
        dest_path_arg = None
        source_paths_raw = []

    dest_dir = None
    if dest_path_arg:
        dest_dir = dest_path_arg if os.path.isdir(dest_path_arg) else None
        if dest_dir is None:
            _show_error(
                "Invalid destination",
                f"Destination path is not a valid directory:\n{dest_path_arg}",
            )
            task_scheduler.delete_args_file(BASENAME)
            return

    if dest_dir is None:
        _show_error(
            "No destination path",
            "No destination folder specified.\n\n"
            "Pass a destination folder as the last argument,\n"
            "or right-click a folder in Explorer.",
        )
        task_scheduler.delete_args_file(BASENAME)
        return

    file_paths, folder_paths = resolve_paths(source_paths_raw, wildcard)

    has_files = len(file_paths) > 0
    has_folders = len(folder_paths) > 0

    if not has_files and not has_folders:
        msg = "No source files or folders found."
        if clip_mode is False:
            msg += "\n\nClipboard is disabled (/noclip)."
        elif not source_paths_raw and clip_mode is not False:
            msg += "\n\nClipboard is empty. Copy files or folders first."
        _show_error("No sources", msg)
        task_scheduler.delete_args_file(BASENAME)
        return

    needs_admin = _check_needs_admin(
        has_files,
        has_folders,
        parsed["file_flags"],
        parsed["folder_flags"],
        admin_file_flags,
        admin_folder_flags,
    )

    admin_free = "/adminfree" in sys.argv or config.admin_free

    # Elevation safety:
    # The silent task-scheduler elevator can be triggered by any user, so it is
    # only trusted when a write-probe (created by THIS process inside the
    # destination) can be verified by the elevated child. Without that proof we
    # fall back to an explicit UAC prompt, where the OS shows a consent dialog.
    if is_admin():
        # An elevated token is not proof by itself: the silent task-scheduler
        # path also runs elevated but can be triggered by any user. Accept the
        # operation only when the caller proved write access (verified probe),
        # or when the request arrived with consent (UAC /restart flag, or args
        # typed directly in an already-elevated shell). A silent launch whose
        # args came only from the user-writable temp file is refused.
        verified = bool(probe_arg) and verify_write_probe(dest_dir, probe_arg)
        if not verified and "/restart" not in sys.argv and not cli_paths:
            _show_error(
                "Access denied",
                "Write access to the destination could not be verified."
                "\nOperation refused.",
            )
            task_scheduler.delete_args_file(BASENAME)
            return
        remove_probe_files(dest_dir)
    elif admin_free:
        probe = create_write_probe(dest_dir)
        need = needs_admin or probe is None
        if probe:
            remove_probe_files(dest_dir)
        if need:
            print(
                "Skipped: admin-free mode — operation needs admin or the"
                " destination is not writable."
                " Run as admin or disable admin-free."
            )
            task_scheduler.delete_args_file(BASENAME)
            return
    else:
        probe = create_write_probe(dest_dir)
        if needs_admin or probe is None:
            task_scheduler.delete_args_file(BASENAME)
            elevate_args = [
                to_unc_path(a) if not a.startswith("/") else a
                for a in sys.argv[1:]
            ]
            if probe is not None:
                # Proven writable: silent task-scheduler elevation is safe.
                elevate_args.append(f"/probe:{to_unc_path(probe)}")
                elevate(BASENAME, elevate_args)
            else:
                # Cannot prove write access: require an explicit UAC prompt.
                elevate_force_uac(BASENAME, elevate_args)
            return
        remove_probe_files(dest_dir)

    task_scheduler.delete_args_file(BASENAME)

    success, skipped = process_links(
        file_paths,
        folder_paths,
        dest_dir,
        file_flags,
        folder_flags,
    )

    if success > 0:
        print(f"Created {success} symlink(s) in {dest_dir}")
    if skipped > 0:
        print(f"Skipped {skipped} item(s)")


def _find_probe_arg(args: list[str]) -> str | None:
    """Find a `/probe:<path>` arg passed for elevation verification."""
    for arg in args:
        if arg.startswith("/probe:"):
            return arg[len("/probe:") :]
    return None


def _check_needs_admin(
    has_files: bool,
    has_folders: bool,
    file_flags: list[str],
    folder_flags: list[str],
    admin_file_flags: list[str],
    admin_folder_flags: list[str],
) -> bool:
    """Check if admin elevation is needed based on configured admin-required ops."""
    return (has_files and bool(set(file_flags) & set(admin_file_flags))) or (
        has_folders and bool(set(folder_flags) & set(admin_folder_flags))
    )


def _find_setup_exe(install_dir: str) -> str | None:
    """Locate mklinktool-setup.exe next to the tool or in a known location."""
    candidates = [
        os.path.join(install_dir, SETUP_EXE_NAME),
        os.path.join(os.path.dirname(get_exe_path()), SETUP_EXE_NAME),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), BASENAME, SETUP_EXE_NAME),
        os.path.join(os.environ.get("PROGRAMFILES", ""), BASENAME, SETUP_EXE_NAME),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _launch_setup(args: list[str]) -> bool:
    """Start the setup executable with ``args``; False when it is missing.

    The tool never installs/uninstalls itself - every install action is
    delegated to mklinktool-setup.exe (or reported as unavailable).
    """
    setup = _find_setup_exe(get_install_dir())
    if not setup:
        print("mklinktool-setup.exe not found - download it from the Releases page.")
        return False
    subprocess.Popen([setup, *args])
    print(f"Launched: {setup}" + (f" {' '.join(args)}" if args else ""))
    return True


def _show_error(title: str, msg: str) -> None:
    writeback.dbg(f"error-show {title!r}")
    print(f"{title}: {msg}")
    if not writeback.is_silent():
        return
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showerror(f"PasteAsSyslinkWin - {title}", msg, parent=root)
    root.destroy()


def main() -> None:
    """Entry point. Relays output to the parent when running elevated."""
    writeback.dbg(f"main-entry argv={sys.argv!r}")
    writeback_child = writeback.activate_child(BASENAME)
    writeback.setup_console_streams(writeback_child)
    code = 0
    try:
        _main_impl()
    except Exception as e:
        import traceback

        writeback.dbg(f"exception {e!r}")
        print(f"ERROR: {e}")
        print(traceback.format_exc())
        if writeback_child is None and sys.stdin is not None and sys.stdin.isatty():
            with contextlib.suppress(EOFError):
                input("Press Enter to exit...")
        code = 1
    finally:
        if writeback_child is not None:
            writeback_child.finish(code)


if __name__ == "__main__":
    main()
