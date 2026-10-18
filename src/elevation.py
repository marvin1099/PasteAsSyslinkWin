"""Auto-elevation via Task Scheduler with UAC fallback."""

import contextlib
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


def get_launch_command() -> tuple[str, str]:
    """Return (command, arguments) needed to launch this tool elevated.

    Frozen builds launch the exe directly. Source runs need the Python
    interpreter plus the script path, since CreateProcess (task scheduler)
    cannot start a bare .py file.
    """
    exe_path = get_exe_path()
    if getattr(sys, "frozen", False):
        return exe_path, ""
    return sys.executable, f'"{exe_path}"'


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
            exe_path, task_args = get_launch_command()
            task_scheduler.create_task(basename, exe_path, task_args)
        return

    command, task_args = get_launch_command()

    if task_scheduler.task_exists(basename):
        if writeback.should_relay():

            def launch(full_args: list[str]) -> bool:
                task_scheduler.write_port_file(basename, int(full_args[-1]))
                if task_scheduler.run_task(basename, command, task_args):
                    return True
                # Child never started: nobody will verify/clean the probe.
                task_scheduler.delete_args_file(basename)
                _remove_probe_arg(full_args)
                return False

            _exit_process(writeback.run_writeback_parent(launch, args))
        task_scheduler.write_args_file(basename, args)
        if task_scheduler.run_task(basename, command, task_args):
            _exit_process()
        # Task run failed (e.g. task deleted or disabled): fall back to UAC.
        task_scheduler.delete_args_file(basename)

    if writeback.should_relay():
        _exit_process(
            writeback.run_writeback_parent(
                lambda full: _launch_uac(command, task_args, full), args
            )
        )
    launched = _launch_uac(command, task_args, args)
    _exit_process(0 if launched else 1)


def elevate_force_uac(basename: str, args: list[str]) -> None:
    """Force UAC elevation (e.g., when the silent path is untrusted)."""
    if is_admin():
        return
    command, task_args = get_launch_command()
    if writeback.should_relay():
        _exit_process(
            writeback.run_writeback_parent(
                lambda full: _launch_uac(command, task_args, full), args
            )
        )
    launched = _launch_uac(command, task_args, args)
    _exit_process(0 if launched else 1)


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


def _launch_uac(command: str, command_args: str, args: list[str]) -> bool:
    """Launch via ShellExecuteW runas verb to trigger UAC prompt.

    Returns True when the process was launched (UAC accepted).
    """
    arg_str = " ".join(f'"{a}"' for a in args if a)
    params = " ".join(p for p in (command_args, "/restart", arg_str) if p)
    verb = "runas"
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        verb,
        command,
        params,
        None,
        0,  # SW_HIDE: the elevated console must not pop up
    )
    if result <= 32:
        # Declined or failed: no child will verify the write-probe, so
        # remove it here instead of leaving it in the destination.
        _remove_probe_arg(args)
        return False
    return True


def _remove_probe_arg(args: list[str]) -> None:
    """Delete a /probe: file that no elevated child will clean up."""
    for arg in args:
        if arg.startswith("/probe:"):
            path = arg[len("/probe:") :]
            if os.path.isfile(path):
                with contextlib.suppress(OSError):
                    os.remove(path)


def _exit_process(code: int = 0) -> None:
    """Exit the current process cleanly."""
    os._exit(code)
