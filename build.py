r"""Build dist\mklinktool\ (onedir console build with custom icon).

Run with:  uv run build.py [--run]   (or double-click build.bat / build-run.bat)

Prepares the project venv (uv sync installs project + dev deps such as
PyInstaller) and bundles src/main.py into a console onedir bundle
(mklinktool.exe + _internal) that carries src/mklinktool.ico. Onedir
launches in a few hundred ms; a onefile build re-extracts on every start
(1-10s), which is too slow for CLI use.

Flash policy: when a terminal exists the tool attaches to it; when none
exists it must not create a console window (or hides the one Windows
makes). A mklinktool.bat CLI shim is written next to the bundle so
`mklinktool` works from cmd/PowerShell with output and exit codes.
With --run the freshly built executable is launched.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(ROOT, "dist")
EXE_PATH = os.path.join(DIST_DIR, "mklinktool", "mklinktool.exe")
SHIM_PATH = os.path.join(DIST_DIR, "mklinktool.bat")

SHIM_CONTENT = (
    "@echo off\r\n"
    '"%~dp0mklinktool\\mklinktool.exe" %*\r\n'
    "exit /b %errorlevel%\r\n"
)


def _write_shim(path: str) -> None:
    """Write the CLI batch shim next to the executable."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(SHIM_CONTENT)


def _clean() -> None:
    """Remove leftover artifacts from a previous build."""
    for name in ("dist", "build"):
        path = os.path.join(ROOT, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)
    for spec in glob.glob(os.path.join(ROOT, "*.spec")):
        os.remove(spec)


def _remove_build_artifacts() -> None:
    """Remove the PyInstaller work dir and spec that are not shipped."""
    shutil.rmtree(os.path.join(ROOT, "build"), ignore_errors=True)
    for spec in glob.glob(os.path.join(ROOT, "*.spec")):
        os.remove(spec)


def _uv_sync() -> None:
    subprocess.run(["uv", "sync"], cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dist\\mklinktool\\")
    parser.add_argument(
        "--run",
        action="store_true",
        help="run the built executable after the build finishes",
    )
    parsed = parser.parse_args()

    os.chdir(ROOT)
    _clean()
    _uv_sync()

    try:
        from PyInstaller.__main__ import run
    except ImportError:
        print("PyInstaller is not available in this Python.", file=sys.stderr)
        print("Run this script with: uv run build.py", file=sys.stderr)
        return 1

    pyinstaller_args = [
        "--onedir",
        "--console",
        "--name", "mklinktool",
        "--icon", "src/mklinktool.ico",
        "--add-data", "src/mklinktool.ico;.",
        "--hidden-import", "src.uninstall_registry",
        "--distpath", "dist",
        "src/main.py",
    ]
    try:
        run(pyinstaller_args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code != 0:
            return code

    _remove_build_artifacts()
    _write_shim(SHIM_PATH)
    print("Build complete: dist\\mklinktool\\ (+ mklinktool.bat shim)")

    if parsed.run:
        print(f"Running {SHIM_PATH}")
        return subprocess.run([SHIM_PATH], cwd=ROOT).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
