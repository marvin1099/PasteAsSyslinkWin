"""Installation wizard and installer core (used only by mklinktool-setup.exe).

The setup executable embeds the tool bundle as a payload and copies it into
the install location; it also copies itself next to the tool so uninstall
and repair stay available offline. The tool (mklinktool.exe) never runs
any of this - it only delegates to the setup executable.
"""

import contextlib
import os
import shutil
import sys

from src import task_scheduler
from src.config import (
    APP_EXE_NAME,
    CLI_SHIM_NAME,
    LEGACY_EXE_NAME,
    SETUP_EXE_NAME,
    Config,
)
from src.context_menu import add_context_menu
from src.elevation import elevate_force_uac, get_exe_path, get_launch_command, is_admin
from src.path_env import add_to_path, remove_from_path
from src.uninstall_registry import (
    add_uninstall_entry,
    get_installed_location,
    remove_uninstall_entry,
)

tk = None
filedialog = None
messagebox = None


def _ensure_tk() -> None:
    """Import tkinter on first GUI use (keeps CLI/quiet paths tkinter-free)."""
    global tk, filedialog, messagebox
    if tk is None:
        import tkinter as _tk
        from tkinter import filedialog as _fd
        from tkinter import messagebox as _mb

        tk = _tk
        filedialog = _fd
        messagebox = _mb


def _topmost_msgbox(kind: str, title: str, msg: str) -> None:
    """Show a messagebox that appears above the console window."""
    _ensure_tk()
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    getattr(messagebox, kind)(title, msg, parent=root)
    root.destroy()


def _default_user_path(basename: str) -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), basename)


def _default_allusers_path(basename: str) -> str:
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    return os.path.join(pf, basename)


class _InstallerDialog:
    """Single-window installer with all options."""

    def __init__(
        self,
        basename: str,
        *,
        all_users: bool = False,
        reinstall_mode: bool = False,
        initial_cfg: dict | None = None,
    ):
        _ensure_tk()
        self.basename = basename
        self.reinstall_mode = reinstall_mode
        self.result = None
        self.uninstall_requested = False
        self._admin = is_admin()

        self.root = tk.Tk()
        self.root.title(
            "PasteAsSyslinkWin - Reinstall"
            if reinstall_mode
            else "PasteAsSyslinkWin - Settings"
        )
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.scope_var = tk.StringVar(value="all" if all_users else "user")
        self.task_var = tk.BooleanVar(value=all_users)
        self.context_var = tk.BooleanVar(value=True)
        self.add_to_path_var = tk.BooleanVar(value=True)
        self.wildcard_var = tk.BooleanVar(value=False)
        self.admin_free_var = tk.BooleanVar(value=not all_users)

        self._build_ui()
        self._center_window(520, 710)
        self.root.attributes("-topmost", True)
        self.scope_var.trace_add("write", lambda *_: self._on_scope_change())
        self._on_scope_change()
        if initial_cfg:
            self._apply_initial(initial_cfg)

    def _apply_initial(self, cfg: dict) -> None:
        """Pre-fill the wizard from an existing installation's settings."""
        # Scope first: its trace resets path/task/admin-free to scope defaults.
        self.scope_var.set("all" if cfg.get("all_users") else "user")
        if cfg.get("install_dir"):
            self.path_var.set(cfg["install_dir"])
        if "use_task" in cfg:
            self.task_var.set(bool(cfg["use_task"]))
        if "admin_free" in cfg:
            self.admin_free_var.set(bool(cfg["admin_free"]))
        if "add_context" in cfg:
            self.context_var.set(bool(cfg["add_context"]))
        if "add_to_path" in cfg:
            self.add_to_path_var.set(bool(cfg["add_to_path"]))
        if "wildcard_loops" in cfg:
            self.wildcard_var.set(bool(cfg["wildcard_loops"]))
        if cfg.get("file_opts"):
            self.file_opt_var.set(cfg["file_opts"])
        if cfg.get("folder_opts"):
            self.folder_opt_var.set(cfg["folder_opts"])
        admin_file = cfg.get("admin_file_opts", "").split()
        admin_folder = cfg.get("admin_folder_opts", "").split()
        self.admin_file_symlink_var.set("/f" in admin_file)
        self.admin_file_hardlink_var.set("/h" in admin_file)
        self.admin_folder_symlink_var.set("/d" in admin_folder)
        self.admin_folder_junction_var.set("/j" in admin_folder)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 3}
        admin = self._admin

        tk.Label(
            self.root,
            text="Welcome! Configure PasteAsSyslinkWin.",
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(12, 4))

        if not admin:
            elev_frame = tk.Frame(self.root)
            elev_frame.pack(fill="x", **pad)
            self._elevate_btn = tk.Button(
                elev_frame,
                text="Elevate to Admin",
                command=self._on_elevate,
                fg="#8B0000",
            )
            self._elevate_btn.pack(side="left")
            tk.Label(
                elev_frame,
                text="Some options require admin privileges.",
                fg="gray40",
            ).pack(side="left", padx=8)

        scope_lf = tk.LabelFrame(self.root, text="Install Scope", padx=8, pady=6)
        scope_lf.pack(fill="x", **pad)

        self._scope_user = tk.Radiobutton(
            scope_lf,
            text="Current user (no admin needed)",
            variable=self.scope_var,
            value="user",
            state="normal" if admin else "disabled",
        )
        self._scope_user.pack(anchor="w")
        self._scope_all = tk.Radiobutton(
            scope_lf,
            text="All users (requires admin)",
            variable=self.scope_var,
            value="all",
            state="normal" if admin else "disabled",
        )
        self._scope_all.pack(anchor="w")
        if not admin:
            self.scope_var.set("user")
            tk.Label(
                scope_lf, text="  Run as admin to install for all users", fg="gray40"
            ).pack(anchor="w")

        path_lf = tk.LabelFrame(self.root, text="Installation Folder", padx=8, pady=6)
        path_lf.pack(fill="x", **pad)

        self.path_var = tk.StringVar(value=_default_user_path(self.basename))
        self.path_entry = tk.Entry(path_lf, textvariable=self.path_var, width=58)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        tk.Button(path_lf, text="Browse...", command=self._browse).pack(side="right")

        # -- Link defaults (radio buttons, mutually exclusive) --
        link_lf = tk.LabelFrame(self.root, text="Default Link Options", padx=8, pady=6)
        link_lf.pack(fill="x", **pad)

        self.file_opt_var = tk.StringVar(value="/f")
        self.folder_opt_var = tk.StringVar(value="/j")

        file_frame = tk.Frame(link_lf)
        file_frame.pack(fill="x", pady=1)
        tk.Label(file_frame, text="Files:", width=8, anchor="w").pack(side="left")
        tk.Radiobutton(
            file_frame, text="Symlink (/f)", variable=self.file_opt_var, value="/f"
        ).pack(side="left", padx=4)
        tk.Radiobutton(
            file_frame, text="Hardlink (/h)", variable=self.file_opt_var, value="/h"
        ).pack(side="left", padx=4)

        folder_frame = tk.Frame(link_lf)
        folder_frame.pack(fill="x", pady=1)
        tk.Label(folder_frame, text="Folders:", width=8, anchor="w").pack(side="left")
        tk.Radiobutton(
            folder_frame, text="Symlink (/d)", variable=self.folder_opt_var, value="/d"
        ).pack(side="left", padx=4)
        tk.Radiobutton(
            folder_frame, text="Junction (/j)", variable=self.folder_opt_var, value="/j"
        ).pack(side="left", padx=4)

        # -- Admin opts (which operations need admin elevation) --
        admin_lf = tk.LabelFrame(self.root, text="Require Admin For", padx=8, pady=6)
        admin_lf.pack(fill="x", **pad)

        tk.Label(
            admin_lf,
            text="Uncheck if your system allows symlinks without admin:",
            fg="gray40",
        ).pack(anchor="w")

        self.admin_file_symlink_var = tk.BooleanVar(value=True)
        self.admin_file_hardlink_var = tk.BooleanVar(value=True)
        self.admin_folder_symlink_var = tk.BooleanVar(value=True)
        self.admin_folder_junction_var = tk.BooleanVar(value=False)

        aframe = tk.Frame(admin_lf)
        aframe.pack(fill="x", pady=1)
        tk.Label(aframe, text="Files:", width=8, anchor="w").pack(side="left")
        tk.Checkbutton(
            aframe, text="Symlink (/f)", variable=self.admin_file_symlink_var
        ).pack(side="left", padx=4)
        tk.Checkbutton(
            aframe, text="Hardlink (/h)", variable=self.admin_file_hardlink_var
        ).pack(side="left", padx=4)

        aframe2 = tk.Frame(admin_lf)
        aframe2.pack(fill="x", pady=1)
        tk.Label(aframe2, text="Folders:", width=8, anchor="w").pack(side="left")
        tk.Checkbutton(
            aframe2, text="Symlink (/d)", variable=self.admin_folder_symlink_var
        ).pack(side="left", padx=4)
        tk.Checkbutton(
            aframe2, text="Junction (/j)", variable=self.admin_folder_junction_var
        ).pack(side="left", padx=4)

        # -- Options --
        opt_lf = tk.LabelFrame(self.root, text="Options", padx=8, pady=6)
        opt_lf.pack(fill="x", **pad)

        self.task_checkbutton = tk.Checkbutton(
            opt_lf,
            text="Use Task Scheduler (auto-elevation without UAC prompts, requires admin)",
            variable=self.task_var,
            state="normal" if admin else "disabled",
        )
        self.task_checkbutton.pack(anchor="w")
        self.admin_free_checkbutton = tk.Checkbutton(
            opt_lf,
            text="Admin-free mode (skip operations that need admin instead of elevating)",
            variable=self.admin_free_var,
        )
        self.admin_free_checkbutton.pack(anchor="w")
        tk.Checkbutton(
            opt_lf,
            text='Add "Create Symlinks Here" to right-click context menu',
            variable=self.context_var,
        ).pack(anchor="w")
        self._path_checkbutton = tk.Checkbutton(
            opt_lf,
            text="Add install folder to PATH",
            variable=self.add_to_path_var,
            state="normal" if admin else "disabled",
        )
        self._path_checkbutton.pack(anchor="w")
        if not admin:
            tk.Label(
                opt_lf,
                text="  Admin needed for system PATH. User PATH is always available.",
                fg="gray40",
            ).pack(anchor="w")
        tk.Checkbutton(
            opt_lf,
            text="Enable wildcard loop expansion by default",
            variable=self.wildcard_var,
        ).pack(anchor="w")

        # -- Buttons --
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", **pad)

        if self.reinstall_mode:
            tk.Button(
                btn_frame,
                text="Uninstall",
                width=14,
                command=self._on_uninstall,
                fg="#8B0000",
            ).pack(side="right", padx=4)

        tk.Button(
            btn_frame,
            text="Install",
            width=14,
            command=self._on_ok,
        ).pack(side="right", padx=4)
        tk.Button(btn_frame, text="Cancel", width=14, command=self._on_cancel).pack(side="right")

    def _center_window(self, w: int, h: int):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _on_scope_change(self):
        is_all = self.scope_var.get() == "all"
        if is_all:
            self.admin_free_var.set(False)
            self.task_var.set(True)
        else:
            self.admin_free_var.set(True)
            self.task_var.set(False)
        self.path_var.set(
            _default_allusers_path(self.basename)
            if is_all
            else _default_user_path(self.basename)
        )
        if not self._admin:
            path_state = "disabled" if is_all else "normal"
            self._path_checkbutton.config(state=path_state)
            task_state = "disabled"
            self.task_checkbutton.config(state=task_state)
        else:
            self._path_checkbutton.config(state="normal")
            self.task_checkbutton.config(state="normal")

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.path_var.get(), title="Select Install Folder")
        if d:
            self.path_var.set(d)

    def _on_ok(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning(
                "PasteAsSyslinkWin", "Please enter an installation folder.", parent=self.root
            )
            return
        self.result = {
            "install_dir": os.path.normpath(path),
            "all_users": self.scope_var.get() == "all",
        }

        admin_file = []
        if self.admin_file_symlink_var.get():
            admin_file.append("/f")
        if self.admin_file_hardlink_var.get():
            admin_file.append("/h")
        admin_folder = []
        if self.admin_folder_symlink_var.get():
            admin_folder.append("/d")
        if self.admin_folder_junction_var.get():
            admin_folder.append("/j")

        self.result.update(
            {
                "use_task": self.task_var.get(),
                "admin_free": self.admin_free_var.get(),
                "add_context": self.context_var.get(),
                "add_to_path": self.add_to_path_var.get(),
                "wildcard_loops": self.wildcard_var.get(),
                "file_opts": self.file_opt_var.get(),
                "folder_opts": self.folder_opt_var.get(),
                "admin_file_opts": " ".join(admin_file),
                "admin_folder_opts": " ".join(admin_folder),
            }
        )
        self.root.destroy()

    def _on_cancel(self):
        self.root.destroy()

    def _on_elevate(self):
        """Relaunch the installer elevated via UAC."""
        self.root.destroy()
        elevate_force_uac(self.basename, ["/restart"])

    def _on_uninstall(self):
        """Request uninstall and close the dialog."""
        self.uninstall_requested = True
        self.root.destroy()

    def show(self) -> dict | None:
        self.root.mainloop()
        return self.result


def _do_install(basename: str, cfg: dict) -> None:
    """Shared install logic. cfg must contain all required keys."""
    install_dir = cfg["install_dir"]
    all_users = cfg["all_users"]
    # Keep a silent install silent across the elevated relaunch.
    elev_flags = [a for a in sys.argv[1:] if a in ("/nogui", "/noguiall", "/repair")]

    if all_users and not is_admin():
        elevate_force_uac(basename, elev_flags)
        return  # elevate_force_uac exits; never reached unless already admin

    os.makedirs(install_dir, exist_ok=True)

    test_file = os.path.join(install_dir, ".install_test")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except OSError:
        if not is_admin():
            elevate_force_uac(basename, elev_flags)
            return
        _topmost_msgbox(
            "showerror",
            "PasteAsSyslinkWin",
            f"Cannot write to: {install_dir}\n"
            "Please run as administrator or choose a different folder.",
        )
        sys.exit(1)

    if cfg["use_task"] and not is_admin():
        elevate_force_uac(basename, elev_flags)
        return

    file_opts = cfg.get("file_opts", "/f").strip()
    folder_opts = cfg.get("folder_opts", "/j").strip()
    admin_file = cfg.get("admin_file_opts", "/f /h").strip()
    admin_folder = cfg.get("admin_folder_opts", "/d").strip()

    config = Config(install_dir, basename)
    config.task = cfg["use_task"]
    config.admin_free = cfg.get("admin_free", not all_users)
    config.wildcard_loops = cfg["wildcard_loops"]
    config.script_default_file_opts = file_opts
    config.script_default_folder_opts = folder_opts
    config.admin_file_opts = admin_file
    config.admin_folder_opts = admin_folder
    config.all_users = all_users
    config.save()

    frozen = getattr(sys, "frozen", False)
    if frozen:
        payload = _payload_dir()
        if payload is None:
            print("ERROR: installer payload missing - mklinktool-setup.exe is broken.")
            sys.exit(1)
        _copy_payload(install_dir, basename, payload)
        script_dest = os.path.join(install_dir, APP_EXE_NAME)
        task_command, task_args = script_dest, ""
        # Keep the setup executable next to the tool so uninstall/repair stay
        # available after the download is gone; Apps & Features points at it.
        setup_src = os.path.abspath(sys.executable)
        setup_dst = os.path.join(install_dir, SETUP_EXE_NAME)
        if os.path.normcase(setup_src) != os.path.normcase(setup_dst):
            shutil.copy2(setup_src, setup_dst)
        cmd_prefix = f'"{setup_dst}"'
    else:
        # Source run: register the tool script (src/main.py), not the setup
        # entry point that is executing right now.
        entry = os.path.abspath(get_exe_path())
        tool_script = os.path.join(os.path.dirname(entry), "main.py")
        if os.path.isfile(tool_script):
            script_dest = tool_script
            task_command, task_args = sys.executable, f'"{tool_script}"'
        else:
            script_dest = entry
            task_command, task_args = get_launch_command()
        # Apps & Features must invoke the setup entry (install/uninstall/repair).
        cmd_prefix = f'"{sys.executable}" "{entry}"'
        _write_cli_shim(install_dir, task_command, task_args)

    if cfg["add_context"]:
        add_context_menu(script_dest, file_opts, folder_opts)

    if cfg["use_task"]:
        task_scheduler.create_task(basename, task_command, task_args)

    if cfg["add_to_path"]:
        add_to_path(install_dir, all_users=all_users)

    add_uninstall_entry(install_dir, script_dest, all_users=all_users, command=cmd_prefix)


def run_installer(basename: str, *, reinstall: bool = False) -> None:
    """Run the single-step interactive installation wizard."""
    initial_cfg = None
    if reinstall:
        existing = _existing_install(basename)
        if existing:
            initial_cfg = _config_as_cfg(existing, basename)
    dialog = _InstallerDialog(basename, reinstall_mode=reinstall, initial_cfg=initial_cfg)
    cfg = dialog.show()

    if dialog.uninstall_requested:
        installed_loc = _existing_install(basename)
        if installed_loc:
            cfg_inst = Config(installed_loc, basename)
            cfg_inst.load()
            run_uninstaller(basename, installed_loc, cfg_inst.task)
        else:
            _topmost_msgbox(
                "showinfo",
                "PasteAsSyslinkWin",
                "No existing installation found to uninstall.",
            )
        sys.exit(0)

    if cfg is None:
        sys.exit(0)

    _do_install(basename, cfg)

    _topmost_msgbox(
        "showinfo",
        "PasteAsSyslinkWin",
        f"Installation complete!\n\nInstalled to: {cfg['install_dir']}\n"
        f"{'(All users)' if cfg['all_users'] else '(Current user)'}",
    )
    sys.exit(0)


def run_installer_silent(basename: str, *, all_users: bool = True) -> None:
    """Silent install with defaults. No GUI.

    Settings that already exist at the target location are preserved so a
    silent upgrade or repair never resets the user's configuration. The
    scope stays whatever the caller asked for (/nogui vs /noguiall).
    """
    cfg = {
        "install_dir": _default_allusers_path(basename)
        if all_users
        else _default_user_path(basename),
        "all_users": all_users,
        "use_task": all_users,
        "admin_free": not all_users,
        "add_context": True,
        "add_to_path": True,
        "wildcard_loops": False,
        "file_opts": "/f",
        "folder_opts": "/j",
        "admin_file_opts": "/f /h",
        "admin_folder_opts": "/d",
    }
    existing = Config(cfg["install_dir"], basename)
    if existing.load():
        cfg.update(
            use_task=existing.task,
            admin_free=existing.admin_free,
            wildcard_loops=existing.wildcard_loops,
            file_opts=existing.script_default_file_opts,
            folder_opts=existing.script_default_folder_opts,
            admin_file_opts=existing.admin_file_opts,
            admin_folder_opts=existing.admin_folder_opts,
        )
    _do_install(basename, cfg)
    print(f"Installation complete! {cfg['install_dir']}")
    sys.exit(0)


def _write_cli_shim(install_dir: str, command: str, command_args: str = "") -> None:
    """Write the mklinktool.bat CLI shim so shells get CLI semantics.

    The shim gives cmd/PowerShell a stable ``mklinktool`` command with
    inherited std handles and exit codes; the console exe itself blocks
    shells normally.
    """
    target = f'"{command}"'
    if command_args:
        target += f" {command_args}"
    content = "@echo off\r\n" f"{target} %*\r\n" "exit /b %errorlevel%\r\n"
    with open(os.path.join(install_dir, CLI_SHIM_NAME), "w", encoding="utf-8", newline="") as f:
        f.write(content)


def _payload_dir() -> str | None:
    """Directory of the embedded tool payload inside the frozen setup exe.

    Returns None for source runs (nothing embedded) and when the payload
    is missing (broken setup executable - callers must refuse to install).
    """
    if not getattr(sys, "frozen", False):
        return None
    payload = os.path.join(getattr(sys, "_MEIPASS", ""), "payload")
    return payload if os.path.isdir(payload) else None


def _copy_payload(install_dir: str, basename: str, payload: str) -> None:
    """Copy the embedded tool bundle (exe + _internal) and refresh the shim."""
    src_n = os.path.normcase(os.path.normpath(payload))
    dst_n = os.path.normcase(os.path.normpath(install_dir))
    if src_n != dst_n:
        shutil.copytree(payload, install_dir, dirs_exist_ok=True)
    # Upgrade path: drop the exe of the intermediate windowed build.
    legacy = os.path.join(install_dir, LEGACY_EXE_NAME)
    if os.path.isfile(legacy):
        with contextlib.suppress(OSError):
            os.remove(legacy)
    _write_cli_shim(install_dir, os.path.join(install_dir, APP_EXE_NAME))


def _existing_install(basename: str) -> str | None:
    """Locate an existing installation: registry first, then default folders.

    The registry location wins when the folder exists (even if the config
    file was deleted - repairing a broken install must still find it).
    """
    loc = get_installed_location()
    if loc and os.path.isdir(loc):
        return loc
    for path in (_default_user_path(basename), _default_allusers_path(basename)):
        if os.path.isfile(os.path.join(path, f"{basename}.conf")):
            return path
    return None


def _config_as_cfg(install_dir: str, basename: str) -> dict | None:
    """Translate an installed config into wizard cfg values (None if absent)."""
    config = Config(install_dir, basename)
    if not config.load():
        return None
    return {
        "install_dir": install_dir,
        "all_users": config.all_users,
        "use_task": config.task,
        "admin_free": config.admin_free,
        "add_context": True,
        "add_to_path": True,
        "wildcard_loops": config.wildcard_loops,
        "file_opts": config.script_default_file_opts,
        "folder_opts": config.script_default_folder_opts,
        "admin_file_opts": config.admin_file_opts,
        "admin_folder_opts": config.admin_folder_opts,
    }


def run_repair(basename: str) -> None:
    """Repair an installation: re-copy tool files, re-register, keep settings."""
    install_dir = _existing_install(basename)
    if not install_dir:
        print("No installation found to repair. Run mklinktool-setup.exe to install.")
        return
    cfg = _config_as_cfg(install_dir, basename)
    if cfg is None:
        # Config lost but files present: rebuild it from the detected scope.
        all_users = os.path.normcase(install_dir) == os.path.normcase(
            _default_allusers_path(basename)
        )
        cfg = {
            "install_dir": install_dir,
            "all_users": all_users,
            "use_task": all_users,
            "admin_free": not all_users,
            "add_context": True,
            "add_to_path": True,
            "wildcard_loops": False,
            "file_opts": "/f",
            "folder_opts": "/j",
            "admin_file_opts": "/f /h",
            "admin_folder_opts": "/d",
        }
    _do_install(basename, cfg)
    print(f"Repair complete! {install_dir}")


def run_uninstaller(
    basename: str, install_dir: str, use_task: bool, *, quiet: bool = False
) -> None:
    """Remove all installed components.

    With ``quiet`` no GUI is shown (used by QuietUninstallString and the
    CLI ``/uninstall /nogui``); a message is printed instead when possible.
    """
    if use_task:
        task_scheduler.delete_task(basename)

    from src.context_menu import remove_context_menu

    remove_context_menu()

    remove_from_path(install_dir, all_users=False)
    remove_from_path(install_dir, all_users=True)

    remove_uninstall_entry(all_users=False)
    remove_uninstall_entry(all_users=True)

    config = Config(install_dir, basename)
    config.delete()

    # The setup exe may be this very process (Apps & Features flow): the
    # immediate remove then fails silently and the scheduled cleanup below
    # deletes it once the process has exited.
    for name in (f"{basename}.ico", CLI_SHIM_NAME, LEGACY_EXE_NAME, APP_EXE_NAME, SETUP_EXE_NAME):
        path = os.path.join(install_dir, name)
        if os.path.isfile(path):
            with contextlib.suppress(OSError):
                os.remove(path)
    internal = os.path.join(install_dir, "_internal")
    if os.path.isdir(internal):
        shutil.rmtree(internal, ignore_errors=True)

    _schedule_self_delete(
        install_dir,
        [
            os.path.join(install_dir, APP_EXE_NAME),
            os.path.join(install_dir, SETUP_EXE_NAME),
        ],
    )

    if quiet:
        print("Uninstallation complete!")
    else:
        _topmost_msgbox("showinfo", "PasteAsSyslinkWin", "Uninstallation complete!")


def _schedule_self_delete(install_dir: str, exe_paths: list[str]) -> None:
    """Spawn a detached cleanup process that deletes the exes and install dir after exit.

    The steps are chained with ``&`` (not ``&&``) so the directory removal is
    attempted even when a file is already gone. Waiting a few seconds lets
    the running setup process exit before its own file is deleted.
    """
    import subprocess

    dels = " ".join(f'& del /f /q "{p}" 2>nul' for p in exe_paths)
    dir_quoted = f'"{install_dir}"'
    cmd = f'cmd /c "timeout /t 5 /nobreak >nul {dels} & rmdir /s /q {dir_quoted} 2>nul"'
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        cmd,
        shell=True,
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )
