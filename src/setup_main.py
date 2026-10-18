"""mklinktool-setup - installer entry point (install / repair / uninstall).

The setup executable is a onefile console build that carries the tool
bundle as an embedded payload and places it where it belongs:

- no flags            interactive install wizard (reinstall when present)
- /nogui              silent install for the current user
- /noguiall           silent install for all users (admin)
- /repair             re-copy tool files and re-register, keep settings
- /uninstall [/nogui] uninstall (quiet with /nogui)
- /help, /?           show usage

Flash policy is the tool's: attach to a terminal when one exists,
otherwise hide the console so only the wizard shows.
"""

import sys

from src import writeback

BASENAME = "mklinktool"

SETUP_HELP = """PasteAsSyslinkWin Setup - Usage:
  mklinktool-setup.exe                   Interactive install wizard
  mklinktool-setup.exe /nogui            Silent install (current user)
  mklinktool-setup.exe /noguiall         Silent install (all users, admin)
  mklinktool-setup.exe /repair           Repair installation (keeps settings)
  mklinktool-setup.exe /uninstall        Uninstall (asks for confirmation)
  mklinktool-setup.exe /uninstall /nogui Uninstall silently
  mklinktool-setup.exe /help             Show this help
  mklinktool-setup.exe /?                Show this help

The wizard also offers Uninstall when an installation is detected.
"""


def parse_setup_args(argv: list[str]) -> str:
    """Map CLI args to a setup mode.

    Returns one of ``help``, ``uninstall``, ``repair``, ``install_user``,
    ``install_all`` or ``wizard``. ``/restart`` (elevation relaunch) and
    unknown flags do not change the mode.
    """
    if "/help" in argv or "/?" in argv:
        return "help"
    if "/uninstall" in argv:
        return "uninstall"
    if "/repair" in argv:
        return "repair"
    if "/noguiall" in argv:
        return "install_all"
    if "/nogui" in argv:
        return "install_user"
    return "wizard"


def _main_impl() -> None:
    mode = parse_setup_args(sys.argv[1:])
    writeback.dbg(f"setup-dispatch mode={mode} argv={sys.argv!r}")

    if mode == "help":
        print(SETUP_HELP)
        return

    from src.installer import (
        run_installer,
        run_installer_silent,
        run_repair,
        run_uninstaller,
    )

    if mode == "uninstall":
        from src.config import Config
        from src.installer import _existing_install

        quiet = "/nogui" in sys.argv
        install_dir = _existing_install(BASENAME)
        if not install_dir:
            print("No installation found to uninstall.")
            return
        config = Config(install_dir, BASENAME)
        config.load()
        run_uninstaller(BASENAME, install_dir, config.task, quiet=quiet)
        return

    if mode == "repair":
        run_repair(BASENAME)
        return

    if mode == "install_user":
        run_installer_silent(BASENAME, all_users=False)
        return

    if mode == "install_all":
        run_installer_silent(BASENAME, all_users=True)
        return

    from src.installer import _existing_install

    run_installer(BASENAME, reinstall=_existing_install(BASENAME) is not None)


def main() -> None:
    """Entry point. Mirrors the tool: writeback relay when elevated."""
    writeback.dbg(f"setup-entry argv={sys.argv!r}")
    writeback_child = writeback.activate_child(BASENAME)
    writeback.setup_console_streams(writeback_child)
    code = 0
    try:
        _main_impl()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
    except Exception as e:
        import traceback

        writeback.dbg(f"setup-exception {e!r}")
        print(f"ERROR: {e}")
        print(traceback.format_exc())
        if writeback.is_silent():
            from src.installer import _topmost_msgbox

            _topmost_msgbox(
                "showerror",
                "PasteAsSyslinkWin Setup",
                f"{e}",
            )
        code = 1
    finally:
        if writeback_child is not None:
            writeback_child.finish(code)
    if code:
        sys.exit(code)


if __name__ == "__main__":
    main()
