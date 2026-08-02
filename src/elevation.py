"""Auto-elevation via Task Scheduler with UAC fallback."""

import ctypes
import os
import sys

from src import task_scheduler, writeback


def is_admin() -> bool:
    """Check if the current process has admin privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def elevate(basename: str, args: list[str]) -> None:
    """Elevate the current process. Uses Task Scheduler if available, else UAC.

    This function does NOT return. The current process exits after launching
    the elevated instance.

    Args:
        basename: Tool basename for task scheduler lookup.
        args: Arguments to pass to the elevated process.
    """
    if is_admin():
        if not task_scheduler.task_exists(basename):
            exe_path = get_exe_path()
            task_scheduler.create_task(basename, exe_path)
        return

    exe_path = get_exe_path()

    if task_scheduler.task_exists(basename):
        if writeback.should_relay():

            def launch(full_args: list[str]) -> bool:
                task_scheduler.write_port_file(basename, int(full_args[-1]))
                return task_scheduler.run_task(basename)

            _exit_process(writeback.run_writeback_parent(launch, args))
        task_scheduler.write_args_file(basename, args)
        task_scheduler.run_task(basename)
        _exit_process()
    else:
        if writeback.should_relay():
            _exit_process(
                writeback.run_writeback_parent(
                    lambda full: _launch_uac(exe_path, full), args
                )
            )
        _launch_uac(exe_path, args)
        _exit_process()


def elevate_force_uac(basename: str, args: list[str]) -> None:
    """Force UAC elevation (e.g., when script name is wrong)."""
    if is_admin():
        return
    exe_path = get_exe_path()
    if writeback.should_relay():
        _exit_process(
            writeback.run_writeback_parent(
                lambda full: _launch_uac(exe_path, full), args
            )
        )
    _launch_uac(exe_path, args)
    _exit_process()


def get_exe_path() -> str:
    """Get the path to the current executable/script."""
    if getattr(sys, "frozen", False):
        exe = os.path.abspath(sys.executable)
        if os.path.isfile(exe):
            return exe
        argv0 = os.path.abspath(sys.argv[0])
        if os.path.isfile(argv0):
            return argv0
        return sys.executable
    path = os.path.abspath(sys.argv[0])
    if os.path.isfile(path):
        return path
    if not os.path.splitext(path)[1] and os.path.isfile(path + ".exe"):
        return path + ".exe"
    return path


def _launch_uac(exe_path: str, args: list[str]) -> bool:
    """Launch via ShellExecuteW runas verb to trigger UAC prompt.

    Returns True when the process was launched (UAC accepted).
    """
    arg_str = " ".join(f'"{a}"' for a in args if a)
    verb = "runas"
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        verb,
        exe_path,
        f"/restart {arg_str}" if arg_str else "/restart",
        None,
        0,  # SW_HIDE: the elevated console must not pop up
    )
    return result > 32


def _exit_process(code: int = 0) -> None:
    """Exit the current process cleanly."""
    os._exit(code)
