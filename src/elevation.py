"""Auto-elevation via Task Scheduler with UAC fallback."""

import ctypes
import os
import subprocess
import sys

from src import task_scheduler


def is_admin() -> bool:
    """Check if the current process has admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def is_restart() -> bool:
    """Check if this process was launched as an admin restart."""
    return "/restart" in sys.argv


def elevate(basename: str, args: list[str], fallback_uac: bool = True) -> None:
    """Elevate the current process. Uses Task Scheduler if available, else UAC.

    This function does NOT return. The current process exits after launching
    the elevated instance.

    Args:
        basename: Tool basename for task scheduler lookup.
        args: Arguments to pass to the elevated process.
        fallback_uac: If True, fall back to RunAs (UAC prompt) when task
                      scheduler is unavailable. If False, only use task scheduler.
    """
    if is_admin():
        if not task_scheduler.task_exists(basename):
            exe_path = _get_exe_path()
            task_scheduler.create_task(basename, exe_path)
        return

    exe_path = _get_exe_path()

    if task_scheduler.task_exists(basename) and fallback_uac:
        task_scheduler.write_args_file(basename, args)
        task_scheduler.run_task(basename)
        _exit_process()
    else:
        _launch_uac(exe_path, args)
        _exit_process()


def elevate_force_uac(basename: str, args: list[str]) -> None:
    """Force UAC elevation (e.g., when script name is wrong)."""
    if is_admin():
        return
    exe_path = _get_exe_path()
    _launch_uac(exe_path, args)
    _exit_process()


def _get_exe_path() -> str:
    """Get the path to the current executable/script."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def _launch_uac(exe_path: str, args: list[str]) -> None:
    """Launch via RunAs to trigger UAC prompt."""
    arg_str = " ".join(f'"{a}"' for a in args if a)
    full_cmd = f'"{exe_path}" /restart {arg_str}'
    subprocess.Popen(
        full_cmd,
        shell=True,
        executable="cmd.exe",
    )


def _exit_process() -> None:
    """Exit the current process cleanly."""
    os._exit(0)
