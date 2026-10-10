"""Build dist\\mklinktoolw.exe (onefile windowed build with custom icon).

Run with:  uv run build.py [--run]   (or double-click build.bat / build-run.bat)

Prepares the project venv (uv sync installs project + dev deps such as
PyInstaller) and bundles src/main.py into a single windowed exe that carries
src/mklinktool.ico. A mklinktool.bat CLI shim is written next to it so
`mklinktool` keeps working from cmd/PowerShell with output and exit codes.
With --run the freshly built executable is launched.
"""

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
EXE_PATH = os.path.join(ROOT, "dist", "mklinktoolw.exe")
SHIM_PATH = os.path.join(ROOT, "dist", "mklinktool.bat")

SHIM_CONTENT = (
    "@echo off\r\n"
    '"%~dp0mklinktoolw.exe" %*\r\n'
    "exit /b %errorlevel%\r\n"
)


def _write_shim(path: str) -> None:
    """Write the CLI batch shim next to the executable."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(SHIM_CONTENT)


def _clean() -> None:
    """Remove leftover artifacts from a previous build."""
    for name in ("dist", "build", "mklinktool.spec"):
        path = os.path.join(ROOT, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)


def _remove_build_artifacts() -> None:
    """Remove the PyInstaller work dir and spec that are not shipped."""
    shutil.rmtree(os.path.join(ROOT, "build"), ignore_errors=True)
    spec = os.path.join(ROOT, "mklinktool.spec")
    if os.path.exists(spec):
        os.remove(spec)


def _uv_sync() -> None:
    subprocess.run(["uv", "sync"], cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dist\\mklinktoolw.exe")
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
        "--onefile",
        "--noconsole",
        "--name", "mklinktoolw",
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
    print("Build complete: dist\\mklinktoolw.exe (+ mklinktool.bat shim)")

    if parsed.run:
        print(f"Running {SHIM_PATH}")
        return subprocess.run([SHIM_PATH], cwd=ROOT).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
