"""Interactive installation wizard with proper Windows install conventions."""

import os
import shutil
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

from src import task_scheduler
from src.config import Config
from src.context_menu import add_context_menu
from src.elevation import elevate_force_uac, is_admin
from src.path_env import add_to_path, remove_from_path
from src.uninstall_registry import add_uninstall_entry, remove_uninstall_entry


def _topmost_msgbox(kind: str, title: str, msg: str) -> None:
    """Show a messagebox that appears above the console window."""
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
    ):
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

    if all_users and not is_admin():
        elevate_force_uac(basename, [])
        if not is_admin():
            _topmost_msgbox(
                "showerror",
                "PasteAsSyslinkWin",
                "Admin rights are required for 'All users' install.\n"
                "Please accept the UAC prompt or choose 'Current user'.",
            )
            sys.exit(1)

    os.makedirs(install_dir, exist_ok=True)

    test_file = os.path.join(install_dir, ".install_test")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except OSError:
        if not is_admin():
            elevate_force_uac(basename, [])
            if not is_admin():
                _topmost_msgbox(
                    "showerror",
                    "PasteAsSyslinkWin",
                    f"Cannot write to: {install_dir}\n"
                    "Please run as administrator or choose a different folder.",
                )
                sys.exit(1)

    if cfg["use_task"] and not is_admin():
        elevate_force_uac(basename, [])

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

    _copy_script(install_dir, basename)

    script_dest = os.path.join(install_dir, os.path.basename(sys.executable))

    if cfg["add_context"]:
        add_context_menu(script_dest, file_opts, folder_opts)

    if cfg["use_task"]:
        task_scheduler.create_task(basename, script_dest)

    if cfg["add_to_path"]:
        add_to_path(install_dir, all_users=all_users)

    add_uninstall_entry(install_dir, script_dest, all_users=all_users)


def run_installer(basename: str, *, reinstall: bool = False) -> None:
    """Run the single-step interactive installation wizard."""
    dialog = _InstallerDialog(basename, reinstall_mode=reinstall)
    cfg = dialog.show()

    if dialog.uninstall_requested:
        from src.uninstall_registry import get_installed_location

        installed_loc = get_installed_location()
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


def run_installer_silent(
    basename: str, *, all_users: bool = True, reinstall: bool = False
) -> None:
    """Silent install with defaults. No GUI."""
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
    _do_install(basename, cfg)
    sys.exit(0)


def _copy_script(install_dir: str, basename: str) -> None:
    """Copy the executable to the installation directory."""
    src = sys.executable
    dst = os.path.join(install_dir, os.path.basename(sys.executable))
    if os.path.normpath(src) != os.path.normpath(dst):
        shutil.copy2(src, dst)


def run_uninstaller(basename: str, install_dir: str, use_task: bool) -> None:
    """Remove all installed components."""
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

    ico = os.path.join(install_dir, f"{basename}.ico")
    if os.path.exists(ico):
        os.remove(ico)

    exe_path = os.path.join(install_dir, f"{basename}.exe")
    running_from_install = (
        getattr(sys, "frozen", False)
        and os.path.isfile(exe_path)
        and os.path.normcase(os.path.normpath(sys.executable))
        == os.path.normcase(os.path.normpath(exe_path))
    )
    if running_from_install:
        _schedule_self_delete(install_dir, exe_path)

    _topmost_msgbox("showinfo", "PasteAsSyslinkWin", "Uninstallation complete!")


def _schedule_self_delete(install_dir: str, exe_path: str) -> None:
    """Spawn a detached cleanup process that deletes the exe and install dir after exit."""
    import subprocess

    exe_quoted = f'"{exe_path}"'
    dir_quoted = f'"{install_dir}"'
    cmd = (
        f'cmd /c "timeout /t 5 /nobreak >nul '
        f'&& del /f /q {exe_quoted} 2>nul '
        f'&& rmdir {dir_quoted} 2>nul"'
    )
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        cmd,
        shell=True,
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )
