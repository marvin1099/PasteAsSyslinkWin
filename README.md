# PasteAsSyslinkWin

Copy files or folders and paste them as symlinks, hardlinks, or junctions  
via the right-click context menu or from the command line.

AI was used heavily during development, with human review and testing of all code.  
This is a personal tool I wanted and I'm sharing it in case it's useful to others.

## How It Works

When you select files or folders in Explorer and press `Ctrl+C`,  
Windows puts their paths (HDROP) on the clipboard.  
PasteAsSyslinkWin reads those paths and creates symlinks at the destination folder using Windows `mklink`.

Because creating symlinks normally requires administrator privileges on Windows,  
the tool uses a **Windows Task Scheduler rule** to elevate itself automatically  
without showing a UAC prompt on every paste. If Task Scheduler is not available,  
it falls back to a standard UAC prompt.

To keep this silent elevation safe, the tool uses a **write challenge** before elevating,  
the current (non-elevated) process writes a temporary probe file inside the destination folder.  
The elevated process only proceeds if it can verify that file,  
proving the caller genuinely had write access to the target.  
If the destination is not writable, no probe can be created  
and the tool instead requires an explicit UAC prompt.  
This prevents unprivileged callers from pointing the silent elevator at protected system folders.  
Probe files are removed automatically after the operation (or by the elevated process as cleanup).  

## Features

- **Right-click context menu** ("Create Symlinks Here") for Windows 10 and 11 (show more menu)
- **CLI tool** for scripting and batch operations
- **Clipboard integration** copy files in Explorer, paste as symlinks
- **Auto-elevation** via Task Scheduler, no repeated UAC prompts
- **Conflict resolution** dialog to overwrite, rename, or skip when a file exists
- **File symlinks, hardlinks, directory symlinks, and junctions** all supported
- **Wildcard/glob support** patterns like `C:\*\*.txt` expand through subdirectories (if enabled)
- **User or All Users install** per-user install to `%LOCALAPPDATA%`, system-wide to `Program Files`

## Installation

### Option 1: Download the prebuilt release (recommended)

Download **`mklinktool-setup.exe`** from the Releases page and run it: the
wizard installs (or repairs) everything — tool files, context menu, Task
Scheduler rule, PATH entry, uninstall entry in Windows Settings. Also
available silently: `mklinktool-setup.exe /nogui` (current user),
`/noguiall` (all users), `/repair` (re-install keeping your settings),
`/uninstall /nogui`.

Only the installer is published — the build also produces a portable
`mklinktool.zip`, but the tool needs the registrations (context menu,
PATH, Task Scheduler, config) that only the installer sets up, so a
standalone zip would not be usable effectively. It can be built from
source below if you want to try it.

### Option 2: Build from source

Requires [uv](https://docs.astral.sh/uv/) and Python 3.10+.

1. Clone the repository:
   ```
   git clone https://codeberg.org/marvin1099/PasteAsSyslinkWin.git
   cd PasteAsSyslinkWin
   ```
2. Build. Easiest: double-click `build.bat`, it will build it automatically:
   ```
   build.bat
   ```
   To build and immediately run the installer (opens the setup GUI),
   double-click `build-run.bat` instead.

   If you prefer to run the steps manually (also requires 1.), run them in this order:
   ```
   uv sync
   uv run build.py
   ```
   (or `uv run build.py --run` to also launch the setup executable afterwards).
3. Three artifacts are created in `dist\`:
   - `mklinktool\` — the tool (executable plus `_internal` bundle) with a
     `mklinktool.bat` shim next to it for cmd/PowerShell
   - `mklinktool-setup.exe` — the standalone installer (carries the tool
     bundle inside, copies it into place)
   - `mklinktool.zip` — the portable bundle for releases

## Usage

### Context Menu (Recommended)

After installation, right-click any folder in Explorer and select **"Create Symlinks Here"**.  
The tool will read any files you have copied to the clipboard and create symlinks in that folder.

- **Windows 10**: the entry appears directly in the context menu
- **Windows 11**: the entry appears under "Show more options" (Shift+F10)  
  the modern context menu only shows shell-extension items, which requires a DLL (not used)

### Command Line

After installation (with *Add to PATH* enabled),  
the `mklinktool` command is available from the command line:

```
mklinktool [/flags] C:\source\* C:\destination
```

**Commands (tool):**

| Command | Description |
|---------|-------------|
| `/resetconfig` | Remove config only |
| `/reconfigure` | Remove config and open the setup wizard |
| `/install` | Open the setup wizard (installs/repairs) |
| `/uninstall` | Delegate uninstall to the setup executable |
| `/adminfree` | Skip admin-needing operations instead of elevating |
| `/help`, `/?` | Show this help |

**Commands (mklinktool-setup.exe):**

| Command | Description |
|---------|-------------|
| *(no flags)* | Interactive install/repair wizard |
| `/nogui` | Silent install to the current user |
| `/noguiall` | Silent install for all users (admin) |
| `/repair` | Re-copy tool files and re-register, keep settings |
| `/uninstall` | Uninstall (asks for confirmation) |
| `/uninstall /nogui` | Uninstall silently |

**Symlink flags:**

| Flag | Description |
|------|-------------|
| `/f` | File symlink (mklink default, no flag needed) |
| `/d` | Directory symlink (`mklink /d`) |
| `/h` | File hard link (`mklink /h`) |
| `/j` | Directory junction (`mklink /j`) |
| `/w` | Enable wildcard loop expansion |
| `/m` | Disable wildcard loop expansion |

**Clipboard control:**

| Flag | Description |
|------|-------------|
| `/clip` | Force include clipboard as additional sources |
| `/noclip` | Disable clipboard entirely |

File sources use `/f` (symlink) or `/h` (hard link).  
Folder sources use `/d` (directory symlink) or `/j` (junction).

**Path logic:** the last argument is always the destination folder.  
All other arguments are source paths.  
The clipboard is only used as a source, never as the destination.  
With 2+ arguments the clipboard is ignored unless `/clip` is set.  
With a single argument the clipboard provides the sources (disable with `/noclip`).

**Examples:**

```
mklinktool /w /h C:\source\*.txt C:\dest
```
Create file hard links for all `.txt` files.

```
mklinktool /j C:\source\subfolder C:\dest
```
Create a directory junction to the folder.

```
mklinktool /f /j C:\dest
```
Read from clipboard; create file symlinks and folder junctions.

## Configuration

The installed tool stores its settings in `mklinktool.conf` alongside the
executable (written by the installer). The portable build runs with the
defaults below and never writes a config:

```ini
[settings]
task = True
wildcardloops = False
scriptdefaultfileoptions = /f
scriptdefaultfolderoptions = /j
adminfileoptions = /f /h
adminfolderoptions = /d
allusers = False
```

- **task**: Use Task Scheduler for auto-elevation
- **wildcardloops**: Expand wildcards through subdirectories by default
- **scriptdefaultfileopts / folderopts**: Default link types for CLI use
- **adminfileopts / folderopts**: Which operations require admin elevation
- **allusers**: Whether the tool was installed for all users

## Uninstalling

Use **Settings > Apps > PasteAsSyslinkWin > Uninstall**, or run
`mklinktool-setup.exe /uninstall` (`/nogui` to skip prompts). This removes
the context menu entry, Task Scheduler rule, PATH entry, config files, and
the installed files themselves. `mklinktool /uninstall` delegates to the
setup executable when it is installed.

## Project Structure

```
build.py           Build script (run: uv sync ; then: uv run build.py)
build.bat          Build only — double-click entry point
build-run.bat      Build and run — double-click entry point
src/
  main.py               Tool entry point (runtime only - never installs itself)
  setup_main.py         mklinktool-setup.exe entry (install/repair/uninstall)
  cli.py                Flag parsing
  config.py             INI configuration
  clipboard.py          HDROP + text clipboard via Windows API
  elevation.py          Task Scheduler auto-elevation + UAC fallback
  task_scheduler.py     schtasks create/check/run/delete + args IPC
  context_menu.py       Classic context menu registry entries
  installer.py          Install wizard + installer core (payload copy, repair)
  path_env.py           PATH management via registry
  pathresolver.py       Glob/wildcard path resolution
  symlink_ops.py        mklink execution + conflict dialog
  uninstall_registry.py Registry cleanup for uninstall
  writeback.py          Writeback socket + console hiding for elevated children
```

## Requirements

- Windows 10 or 11
- Python 3.10+ and [uv](https://docs.astral.sh/uv/) (only when building from source)
- Administrator privileges for file symlinks and hardlinks to protected directories
  (junctions do not require elevation)
