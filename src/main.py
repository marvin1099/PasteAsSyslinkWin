"""PasteAsSyslinkWin - Main entry point.

A CLI tool and context menu integration for creating symlinks
by copying files/folders and pasting them as symlinks.
"""

import os
import sys

from src import task_scheduler
from src.cli import build_file_flags, build_folder_flags, parse_flags
from src.clipboard import get_clipboard_paths
from src.config import Config
from src.context_menu import (
    add_context_menu_win10,
    add_context_menu_win11,
    detect_windows_version,
)
from src.elevation import elevate, is_admin
from src.installer import run_installer, run_uninstaller
from src.pathresolver import resolve_paths
from src.symlink_ops import process_links

BASENAME = "mklinktool"


def get_install_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def get_exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def main() -> None:
    install_dir = get_install_dir()
    config = Config(install_dir, BASENAME)

    if not config.exists():
        run_installer(BASENAME, get_exe_path())
        return

    config.load()

    cli_args = [a for a in sys.argv[1:] if a != "/restart"]
    temp_args = task_scheduler.read_args_file(BASENAME)
    all_args = cli_args + temp_args

    normal_parsed = parse_flags(all_args, "")

    wildcard = normal_parsed["wildcard"]
    if wildcard is None:
        wildcard = config.wildcard_loops

    install_mode = normal_parsed["install_mode"]
    if install_mode is True:
        task_scheduler.delete_args_file(BASENAME)
        run_uninstaller(BASENAME, install_dir, config.task)
        return

    if install_mode is False:
        task_scheduler.delete_args_file(BASENAME)
        if config.task:
            task_scheduler.create_task(BASENAME, get_exe_path())

        root_args = (
            (f"{config.script_default_file_opts} {config.script_default_folder_opts}")
            .strip()
            .split()
        )
        root_parsed = parse_flags(root_args, "")

        win_ver = detect_windows_version()
        f_opts = build_file_flags(root_parsed)
        d_opts = build_folder_flags(root_parsed)
        add_context_menu_win10(get_exe_path(), f_opts, d_opts)
        if win_ver >= 11:
            add_context_menu_win11(get_exe_path(), f_opts, d_opts)
        return

    file_opts_combined = (
        (f"{config.script_default_file_opts} {config.script_default_folder_opts}").strip().split()
    )
    combined_args = file_opts_combined + all_args

    admin_check = parse_flags(combined_args, "/e")
    normal_full = parse_flags(combined_args, "")

    file_flags = build_file_flags(normal_full)
    folder_flags = build_folder_flags(normal_full)

    paths_from_args = [a for a in combined_args if not a.startswith("/")]
    clipboard_paths = get_clipboard_paths()
    all_paths = paths_from_args + clipboard_paths

    file_paths, folder_paths = resolve_paths(all_paths, wildcard)

    has_files = len(file_paths) > 0
    has_folders = len(folder_paths) > 0

    if not has_folders or (not has_files and len(folder_paths) < 2):
        _show_no_paths_error()
        task_scheduler.delete_args_file(BASENAME)
        return

    dest_dir = folder_paths.pop(0)

    needs_admin = _check_needs_admin(
        has_files,
        has_folders,
        file_flags,
        folder_flags,
        admin_check,
    )

    if not is_admin() and needs_admin:
        task_scheduler.delete_args_file(BASENAME)
        elevate(BASENAME, sys.argv[1:])
        return

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


def _check_needs_admin(
    has_files: bool,
    has_folders: bool,
    file_flags: str,
    folder_flags: str,
    admin_check: dict,
) -> bool:
    """Check if admin elevation is needed based on configured admin-required ops."""
    admin_ff = admin_check["admin_file_flags"]
    admin_df = admin_check["admin_folder_flags"]

    if has_files and admin_ff:
        ff = file_flags.strip().split() if file_flags.strip() else []
        for flag in admin_ff:
            if flag in ff:
                return True

    if has_folders and admin_df:
        df = folder_flags.strip().split() if folder_flags.strip() else []
        for flag in admin_df:
            if flag in df:
                return True

    return False


def _show_no_paths_error() -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "PasteAsSyslinkWin",
        "Error: No valid paths found.\n\n"
        "At least 1 valid folder (destination) and 1 valid path\n"
        "(file or additional folder as source) are required.\n\n"
        "Copy files/folders first (Ctrl+C), then paste as symlinks.",
    )
    root.destroy()


if __name__ == "__main__":
    main()
