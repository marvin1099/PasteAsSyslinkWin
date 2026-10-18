"""Windows Task Scheduler integration for privilege elevation."""

import contextlib
import os
import subprocess
import tempfile
import winreg

from src.vbs_launcher import write_hidden_launcher

_TASK_CACHE = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\TaskCache\Tree"


def _task_name(basename: str) -> str:
    return f"{basename}elevationtask"


def _launcher_path(basename: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"{basename}_hidden.vbs")


def _ensure_launcher(basename: str, exe_path: str) -> str:
    """(Re)write the wscript launcher for the task action.

    Rewritten on every run so a temp-file cleaner cannot leave the task
    pointing at a missing script; a missing launcher would silently turn
    every elevation into the UAC fallback.
    """
    cwd = os.path.dirname(exe_path) or os.getcwd()
    return write_hidden_launcher(_launcher_path(basename), cwd)


def _xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def task_exists(basename: str) -> bool:
    """Check if the scheduled task exists via the registry (no subprocess).

    Task entries are registered under the Task Scheduler cache tree.
    Reading the registry is ~100x faster than spawning schtasks /Query.
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            f"{_TASK_CACHE}\\{_task_name(basename)}",
            0,
            winreg.KEY_READ,
        )
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def create_task(basename: str, exe_path: str, arguments: str = "") -> bool:
    """Create a task with no triggers and HIGHEST run level.

    The task has no auto-trigger; it is only started via run_task(). The
    task is marked Hidden so it is not shown in the Task Scheduler UI, and
    the action runs through a VBScript launcher with window style 0, so
    running it never shows a console window. ``arguments`` is passed
    through verbatim (used for non-frozen launches: the python executable
    plus the script path).
    """
    name = _task_name(basename)
    launcher = _ensure_launcher(basename, exe_path)
    action_args = f'"{launcher}" "{exe_path}"'
    if arguments:
        action_args += f" {arguments}"
    wscript = os.path.join(
        os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32", "wscript.exe"
    )
    xml = f"""\
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>PasteAsSyslinkWin privilege elevation</Description>
  </RegistrationInfo>
  <Triggers />
  <Principals>
    <Principal>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{_xml_escape(wscript)}</Command>
      <Arguments>{_xml_escape(action_args)}</Arguments>
    </Exec>
  </Actions>
</Task>"""
    temp_dir = tempfile.gettempdir()
    xml_path = os.path.join(temp_dir, f"{basename}_task.xml")
    try:
        with open(xml_path, "w", encoding="utf-16") as f:
            f.write(xml)
        result = subprocess.run(
            ["schtasks", "/Create", "/F", "/TN", name, "/XML", xml_path],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    finally:
        if os.path.exists(xml_path):
            os.remove(xml_path)


def run_task(basename: str, exe_path: str, arguments: str = "") -> bool:
    """Run the scheduled task (ends any running instance first).

    The launcher is rewritten first so the action cannot point at a
    missing script when the temp directory was cleaned.
    """
    _ensure_launcher(basename, exe_path)
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
    """Delete the scheduled task and its wscript launcher."""
    name = _task_name(basename)
    result = subprocess.run(
        ["schtasks", "/Delete", "/F", "/TN", name],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    with contextlib.suppress(OSError):
        os.remove(_launcher_path(basename))
    return result.returncode == 0


def write_port_file(basename: str, port: int) -> str:
    """Write the writeback port marker for the elevated task to read."""
    temp_dir = tempfile.gettempdir()
    port_file = os.path.join(temp_dir, f"{basename}.port")
    with open(port_file, "w", encoding="utf-8") as f:
        f.write(str(port) + "\n")
    return port_file


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
        return [line.strip() for line in f if line.strip()]


def delete_args_file(basename: str) -> None:
    """Clean up the temp argument and port-marker files."""
    temp_dir = tempfile.gettempdir()
    for name in (f"{basename}.args.temp", f"{basename}.port"):
        path = os.path.join(temp_dir, name)
        if os.path.exists(path):
            os.remove(path)
