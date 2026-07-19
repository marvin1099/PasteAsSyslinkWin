# PasteAsSyslinkWin

Copy files or folders and paste them as symlinks, hardlinks, or junctions
via the right-click context menu or from the command line.

## How It Works

When you select files or folders in Explorer and press `Ctrl+C`, Windows puts
their paths (HDROP) on the clipboard. PasteAsSyslinkWin reads those paths and
creates symlinks at the destination folder using Windows `mklink`.

Because creating symlinks normally requires administrator privileges on Windows,
the tool uses a **Windows Task Scheduler rule** to elevate itself automatically
without showing a UAC prompt on every paste. If Task Scheduler is not available,
it falls back to a standard UAC prompt.

The tool does **not** allow unprivileged users to create symlinks that would
override files in protected system folders. If the target directory requires
admin access and the process is not elevated, it will re-request elevation
before proceeding. If elevation fails, the operation is skipped.

## Features

- **Right-click context menu** ("Create Symlinks Here") for Windows 10 and 11
- **CLI tool** for scripting and batch operations
- **Clipboard integration** — copy files in Explorer, paste as symlinks
- **Auto-elevation** via Task Scheduler — no repeated UAC prompts
- **Conflict resolution** — dialog to overwrite, rename, or skip when a file exists
- **File symlinks, hardlinks, directory symlinks, and junctions** all supported
- **Wildcard/glob support** — patterns like `C:\*\*.txt` expand through subdirectories
- **User or All Users install** — per-user install to `%LOCALAPPDATA%`, system-wide to `Program Files`

## Installation

### Option 1: Pre-built Installer

1. Download the latest `.whl` file from [Releases](https://codeberg.org/marvin1099/PasteAsSyslinkWin/releases)
2. Install with [uv](https://docs.astral.sh/uv/):
   ```
   uv tool install paste_as_symlink_win-2.0.0-py3-none-any.whl
   ```
   Or with pip:
   ```
   pip install paste_as_symlink_win-2.0.0-py3-none-any.whl
   ```
3. Run `mklinktool` — the installer GUI will open on first run

### Option 2: Run from Source

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```
git clone https://codeberg.org/marvin1099/PasteAsSyslinkWin.git
cd PasteAsSyslinkWin
git checkout new-python-version
uv sync
uv run mklinktool
```

### Option 3: Build Yourself

```
uv build
```

This creates a wheel in `dist/` that can be installed with `uv tool install` or `pip install`.

## Usage

### Context Menu (Recommended)

After installation, right-click any folder in Explorer and select
**"Create Symlinks Here"**. The tool will read any files you have copied to
the clipboard and create symlinks in that folder.

- **Windows 10**: the entry appears directly in the context menu
- **Windows 11**: the entry appears in the modern context menu; if not, use
  "Show more options" (Shift+F10) for the classic menu

### Command Line

```
mklinktool /f /h /d /j C:\destination C:\source\*
```

**Flags:**

| Flag | Description |
|------|-------------|
| `/f` | Switch to file mode (subsequent flags apply to files) |
| `/d` | Switch to folder mode (subsequent flags apply to folders) |
| `/h` | Use hardlinks |
| `/j` | Use junctions (folders only) |
| `/w` | Enable wildcard loop expansion |
| `/m` | Disable wildcard loop expansion |
| `/u` | Uninstall the tool |
| `/r` | Re-add context menu entry and task |

Flags `/f` and `/d` are **mode switches** that control which items receive which
link type. They are not passed to `mklink` directly. Only `/h` and `/j` are
actual `mklink` flags.

**Examples:**

```
mklinktool /f /h C:\dest C:\source\*.txt
```
Create hardlinks for all `.txt` files.

```
mklinktool /d /j C:\dest C:\source\subfolder
```
Create a junction to a folder.

```
mklinktool /f /d /j C:\dest
```
Read from clipboard, create file symlinks and folder junctions.

## Configuration

The tool stores its settings in `mklinktool.conf` alongside the executable:

```ini
[settings]
task = True
wildcardloops = False
scriptdefaultfileoptions = /f
scriptdefaultfolderoptions = /d /j
adminfileoptions = /f /h
adminfolderoptions = /d /h /j
allusers = False
```

- **task**: Use Task Scheduler for auto-elevation
- **wildcardloops**: Expand wildcards through subdirectories by default
- **scriptdefaultfileopts / folderopts**: Default link types for CLI use
- **adminfileopts / folderopts**: Which operations require admin elevation
- **allusers**: Whether the tool was installed for all users

## Uninstalling

Run `mklinktool /u` to remove the context menu entries, Task Scheduler rule,
PATH entry, and config files.

## Project Structure

```
src/
  main.py           Entry point and orchestration
  cli.py            Flag parsing
  config.py         INI configuration
  clipboard.py      HDROP + text clipboard via Windows API
  elevation.py      Task Scheduler auto-elevation + UAC fallback
  task_scheduler.py schtasks create/check/run/delete + args IPC
  context_menu.py   Win10 and Win11 registry entries
  installer.py      Interactive tkinter install wizard
  path_env.py       PATH management via registry
  pathresolver.py   Glob/wildcard path resolution
  symlink_ops.py    mklink execution + conflict dialog
```

## Requirements

- Windows 10 or 11
- Python 3.10+ (if running from source)
- Administrator privileges for file symlinks and junctions to protected directories
  (hardlinks do not require elevation)

## License

[GNU Affero General Public License v3.0](LICENSE)
