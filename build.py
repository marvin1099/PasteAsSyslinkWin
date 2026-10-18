r"""Build the three release artifacts.

Run with:  uv run build.py [--run]   (or double-click build.bat / build-run.bat)

Stages:
1. dist\mklinktool\      onedir console tool (mklinktool.exe + _internal)
                         plus the dist\mklinktool.bat CLI shim. Onedir
                         launches in a few hundred ms; a onefile build
                         re-extracts on every start (1-10s) - too slow
                         for the tool.
2. dist\mklinktool-setup.exe
                         onefile console installer that carries the whole
                         tool bundle as an embedded payload and copies it
                         into place (install / repair / uninstall). Its
                         slower start only matters on install runs.
3. dist\mklinktool.zip   portable bundle (mklinktool\ + mklinktool.bat)
                         for users who run without installing.

Flash policy: when a terminal exists the tool attaches to it; when none
exists it must not create a console window (or hides the one Windows
makes). With --run the freshly built setup executable is launched.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(ROOT, "dist")
EXE_PATH = os.path.join(DIST_DIR, "mklinktool", "mklinktool.exe")
SHIM_PATH = os.path.join(DIST_DIR, "mklinktool.bat")
SETUP_EXE_PATH = os.path.join(DIST_DIR, "mklinktool-setup.exe")
ZIP_PATH = os.path.join(DIST_DIR, "mklinktool.zip")

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


def _run_pyinstaller(run, args: list[str]) -> int:
    """Invoke PyInstaller, mapping SystemExit to a return code."""
    try:
        run(args)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    return 0


def _write_zip() -> str:
    """Zip the portable bundle (mklinktool folder + mklinktool.bat) for releases."""
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(SHIM_PATH, "mklinktool.bat")
        bundle = os.path.join(DIST_DIR, "mklinktool")
        for root, _dirs, files in os.walk(bundle):
            for name in files:
                full = os.path.join(root, name)
                zf.write(full, os.path.relpath(full, DIST_DIR))
    return ZIP_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the release artifacts")
    parser.add_argument(
        "--run",
        action="store_true",
        help="run mklinktool-setup.exe after the build finishes",
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

    code = _run_pyinstaller(
        run,
        [
            "--onedir",
            "--console",
            "--name", "mklinktool",
            "--icon", "src/mklinktool.ico",
            "--add-data", "src/mklinktool.ico;.",
            "--hidden-import", "src.uninstall_registry",
            "--distpath", "dist",
            "src/main.py",
        ],
    )
    if code != 0:
        return code
    _remove_build_artifacts()
    _write_shim(SHIM_PATH)

    # Stage 2: the standalone setup exe, tool bundle embedded as payload.
    code = _run_pyinstaller(
        run,
        [
            "--onefile",
            "--console",
            "--name", "mklinktool-setup",
            "--icon", "src/mklinktool.ico",
            "--add-data", "src/mklinktool.ico;.",
            "--add-data", "dist/mklinktool;payload",
            "--hidden-import", "src.uninstall_registry",
            "--distpath", "dist",
            "src/setup_main.py",
        ],
    )
    if code != 0:
        return code
    _remove_build_artifacts()

    zip_path = _write_zip()
    print("Build complete:")
    print(f"  {EXE_PATH}")
    print(f"  {SETUP_EXE_PATH}")
    print(f"  {zip_path}")

    if parsed.run:
        print(f"Running {SETUP_EXE_PATH}")
        return subprocess.run([SETUP_EXE_PATH], cwd=ROOT).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
