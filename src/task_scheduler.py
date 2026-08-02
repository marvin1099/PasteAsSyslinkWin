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
    """Create a task with no triggers and HIGHEST run level.

    The task has no auto-trigger; it is only started via run_task(). The
    task is marked Hidden so it is not shown in the Task Scheduler UI, and
    running it does not flash a console window.
    """
    name = _task_name(basename)
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
      <Command>"{exe_path}"</Command>
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
        lines = [line.strip() for line in f if line.strip()]
    return lines


def delete_args_file(basename: str) -> None:
    """Clean up the temp argument and port-marker files."""
    temp_dir = tempfile.gettempdir()
    for name in (f"{basename}.args.temp", f"{basename}.port"):
        path = os.path.join(temp_dir, name)
        if os.path.exists(path):
            os.remove(path)
