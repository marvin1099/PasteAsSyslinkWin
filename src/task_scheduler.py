"""Windows Task Scheduler integration for privilege elevation."""

import os
import subprocess
import tempfile


def _task_name(basename: str) -> str:
    return f"{basename}elevationtask"


def task_exists(basename: str) -> bool:
    """Check if the scheduled task exists."""
    name = _task_name(basename)
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", name],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode == 0


def create_task(basename: str, exe_path: str) -> bool:
    """Create an ONCE task with HIGHEST run level for auto-elevation."""
    name = _task_name(basename)
    result = subprocess.run(
        [
            "schtasks",
            "/Create",
            "/SC",
            "ONCE",
            "/ST",
            "00:00",
            "/F",
            "/RL",
            "HIGHEST",
            "/TN",
            name,
            "/TR",
            f'"{exe_path}"',
        ],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode == 0


def run_task(basename: str) -> bool:
    """Run the scheduled task (ends any running instance first)."""
    name = _task_name(basename)
    subprocess.run(
        ["schtasks", "/End", "/TN", name],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    result = subprocess.run(
        ["schtasks", "/Run", "/TN", name],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode == 0


def delete_task(basename: str) -> bool:
    """Delete the scheduled task."""
    name = _task_name(basename)
    result = subprocess.run(
        ["schtasks", "/Delete", "/F", "/TN", name],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode == 0


def write_args_file(basename: str, args: list[str]) -> str:
    """Write arguments to temp file for the elevated task to read. Returns path."""
    temp_dir = tempfile.gettempdir()
    arg_file = os.path.join(temp_dir, f"{basename}.args.temp")
    with open(arg_file, "w", encoding="utf-8") as f:
        for arg in args:
            if arg:
                f.write(arg + "\n")
    return arg_file


def read_args_file(basename: str) -> list[str]:
    """Read arguments from temp file written by non-admin process."""
    temp_dir = tempfile.gettempdir()
    arg_file = os.path.join(temp_dir, f"{basename}.args.temp")
    if not os.path.exists(arg_file):
        return []
    with open(arg_file, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines


def delete_args_file(basename: str) -> None:
    """Clean up the temp argument file."""
    temp_dir = tempfile.gettempdir()
    arg_file = os.path.join(temp_dir, f"{basename}.args.temp")
    if os.path.exists(arg_file):
        os.remove(arg_file)
