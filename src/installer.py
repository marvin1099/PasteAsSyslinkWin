"""Interactive installation wizard with proper Windows install conventions."""

import os
import shutil
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

from src import task_scheduler
from src.cli import parse_flags
from src.config import Config
from src.context_menu import (
    add_context_menu_win10,
    add_context_menu_win11,
    detect_windows_version,
)
from src.elevation import elevate, is_admin
from src.path_env import add_to_path, remove_from_path


def _default_user_path(basename: str) -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), basename)


def _default_allusers_path(basename: str) -> str:
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    return os.path.join(pf, basename)


class _InstallerDialog:
    """Single-window installer with all options."""

    def __init__(self, basename: str):
        self.basename = basename
        self.result = None

        self.root = tk.Tk()
        self.root.title("PasteAsSyslinkWin - Installation")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.scope_var = tk.StringVar(value="user")
        self.task_var = tk.BooleanVar(value=True)
        self.context_var = tk.BooleanVar(value=True)
        self.add_to_path_var = tk.BooleanVar(value=True)
        self.wildcard_var = tk.BooleanVar(value=False)

        self._build_ui()
        self._center_window(520, 420)
        self.scope_var.trace_add("write", lambda *_: self._on_scope_change())

    def _build_ui(self):
        pad = {"padx": 10, "pady": 3}

        # -- Scope --
        scope_lf = tk.LabelFrame(self.root, text="Install Scope", padx=8, pady=6)
        scope_lf.pack(fill="x", **pad)

        tk.Radiobutton(
            scope_lf,
            text="Current user (no admin needed)",
            variable=self.scope_var,
            value="user",
        ).pack(anchor="w")
        tk.Radiobutton(
            scope_lf,
            text="All users (requires admin)",
            variable=self.scope_var,
            value="all",
        ).pack(anchor="w")

        # -- Path --
        path_lf = tk.LabelFrame(self.root, text="Installation Folder", padx=8, pady=6)
        path_lf.pack(fill="x", **pad)

        self.path_var = tk.StringVar(value=_default_user_path(self.basename))
        self.path_entry = tk.Entry(path_lf, textvariable=self.path_var, width=58)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        tk.Button(path_lf, text="Browse...", command=self._browse).pack(side="right")

        # -- Options --
        opt_lf = tk.LabelFrame(self.root, text="Options", padx=8, pady=6)
        opt_lf.pack(fill="x", **pad)

        tk.Checkbutton(
            opt_lf,
            text="Use Task Scheduler (auto-elevation without UAC prompts)",
            variable=self.task_var,
        ).pack(anchor="w")
        tk.Checkbutton(
            opt_lf,
            text='Add "Create Symlinks Here" to right-click context menu',
            variable=self.context_var,
        ).pack(anchor="w")
        tk.Checkbutton(
            opt_lf,
            text="Add install folder to PATH",
            variable=self.add_to_path_var,
        ).pack(anchor="w")
        tk.Checkbutton(
            opt_lf,
            text="Enable wildcard loop expansion by default",
            variable=self.wildcard_var,
        ).pack(anchor="w")

        # -- Buttons --
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", **pad)

        tk.Button(btn_frame, text="Install", width=14, command=self._on_ok).pack(
            side="right", padx=4
        )
        tk.Button(btn_frame, text="Cancel", width=14, command=self._on_cancel).pack(side="right")

    def _center_window(self, w: int, h: int):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _on_scope_change(self):
        if self.scope_var.get() == "user":
            self.path_var.set(_default_user_path(self.basename))
        else:
            self.path_var.set(_default_allusers_path(self.basename))

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
            "use_task": self.task_var.get(),
            "add_context": self.context_var.get(),
            "add_to_path": self.add_to_path_var.get(),
            "wildcard_loops": self.wildcard_var.get(),
        }
        self.root.destroy()

    def _on_cancel(self):
        self.root.destroy()

    def show(self) -> dict | None:
        self.root.mainloop()
        return self.result


class _OptionsDialog:
    """Second dialog for link type and admin-required options."""

    def __init__(self):
        self.result = None

        self.root = tk.Tk()
        self.root.title("PasteAsSyslinkWin - Link Options")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._build_ui()
        self._center_window(440, 310)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 3}

        tk.Label(
            self.root,
            text="Default link types:\n"
            "/f = file symlink, /d = dir symlink, /h = hard link, /j = junction",
            justify="left",
            fg="gray40",
        ).pack(fill="x", **pad)

        # -- Script defaults --
        s_lf = tk.LabelFrame(self.root, text="Script Default Options", padx=8, pady=6)
        s_lf.pack(fill="x", **pad)

        self.file_opts_var = tk.StringVar(value="/f")
        self.folder_opts_var = tk.StringVar(value="/d /j")

        row1 = tk.Frame(s_lf)
        row1.pack(fill="x", pady=1)
        tk.Label(row1, text="File ops:", width=12, anchor="w").pack(side="left")
        tk.Entry(row1, textvariable=self.file_opts_var, width=30).pack(side="left", padx=4)

        row2 = tk.Frame(s_lf)
        row2.pack(fill="x", pady=1)
        tk.Label(row2, text="Folder ops:", width=12, anchor="w").pack(side="left")
        tk.Entry(row2, textvariable=self.folder_opts_var, width=30).pack(side="left", padx=4)

        # -- Context menu defaults --
        c_lf = tk.LabelFrame(self.root, text="Context Menu Defaults (same syntax)", padx=8, pady=6)
        c_lf.pack(fill="x", **pad)

        self.ctx_file_var = tk.StringVar(value="/f")
        self.ctx_folder_var = tk.StringVar(value="/d /j")

        row3 = tk.Frame(c_lf)
        row3.pack(fill="x", pady=1)
        tk.Label(row3, text="File ops:", width=12, anchor="w").pack(side="left")
        tk.Entry(row3, textvariable=self.ctx_file_var, width=30).pack(side="left", padx=4)

        row4 = tk.Frame(c_lf)
        row4.pack(fill="x", pady=1)
        tk.Label(row4, text="Folder ops:", width=12, anchor="w").pack(side="left")
        tk.Entry(row4, textvariable=self.ctx_folder_var, width=30).pack(side="left", padx=4)

        # -- Admin-required --
        a_lf = tk.LabelFrame(self.root, text="Admin-Required Options", padx=8, pady=6)
        a_lf.pack(fill="x", **pad)

        tk.Label(
            a_lf,
            text="Double a flag to mark admin-required (e.g. /f /f /h = file hardlinks need admin)",
            fg="gray40",
        ).pack(anchor="w")

        self.admin_opts_var = tk.StringVar(value="/f /f /h /d /d /h /j")
        tk.Entry(a_lf, textvariable=self.admin_opts_var, width=44).pack(fill="x", pady=2)

        # -- Buttons --
        btn = tk.Frame(self.root)
        btn.pack(fill="x", **pad)
        tk.Button(btn, text="Install", width=14, command=self._on_ok).pack(side="right", padx=4)
        tk.Button(btn, text="Cancel", width=14, command=self._on_cancel).pack(side="right")

    def _center_window(self, w: int, h: int):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _on_ok(self):
        self.result = {
            "file_opts": self.file_opts_var.get().strip(),
            "folder_opts": self.folder_opts_var.get().strip(),
            "ctx_file_opts": self.ctx_file_var.get().strip(),
            "ctx_folder_opts": self.ctx_folder_var.get().strip(),
            "admin_opts": self.admin_opts_var.get().strip(),
        }
        self.root.destroy()

    def _on_cancel(self):
        self.root.destroy()

    def show(self) -> dict | None:
        self.root.mainloop()
        return self.result


def run_installer(basename: str, script_path: str) -> None:
    """Run the two-step interactive installation wizard."""
    step1 = _InstallerDialog(basename)
    cfg = step1.show()
    if cfg is None:
        sys.exit(0)

    install_dir = cfg["install_dir"]
    all_users = cfg["all_users"]

    if all_users and not is_admin():
        elevate(basename, [], fallback_uac=True)
        if not is_admin():
            messagebox.showerror(
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
            elevate(basename, [], fallback_uac=True)
            if not is_admin():
                messagebox.showerror(
                    "PasteAsSyslinkWin",
                    f"Cannot write to: {install_dir}\n"
                    "Please run as administrator or choose a different folder.",
                )
                sys.exit(1)

    if cfg["use_task"] and not is_admin():
        elevate(basename, [], fallback_uac=True)

    step2 = _OptionsDialog()
    opts = step2.show()
    if opts is None:
        sys.exit(0)

    file_parsed = parse_flags(opts["file_opts"].split(), "")
    folder_parsed = parse_flags(opts["folder_opts"].split(), "")
    file_flags = " ".join(file_parsed["file_flags"])
    folder_flags = " ".join(folder_parsed["folder_flags"])

    ctx_f_parsed = parse_flags(opts["ctx_file_opts"].split(), "")
    ctx_d_parsed = parse_flags(opts["ctx_folder_opts"].split(), "")
    ctx_file_flags = " ".join(ctx_f_parsed["file_flags"])
    ctx_folder_flags = " ".join(ctx_d_parsed["folder_flags"])

    admin_parsed = parse_flags(opts["admin_opts"].split(), "/e")
    admin_file = " ".join(admin_parsed["admin_file_flags"])
    admin_folder = " ".join(admin_parsed["admin_folder_flags"])

    config = Config(install_dir, basename)
    config.task = cfg["use_task"]
    config.wildcard_loops = cfg["wildcard_loops"]
    config.script_default_file_opts = file_flags
    config.script_default_folder_opts = folder_flags
    config.admin_file_opts = admin_file
    config.admin_folder_opts = admin_folder
    config.all_users = all_users
    config.save()

    _copy_script(install_dir, basename)

    if cfg["add_context"]:
        win_ver = detect_windows_version()
        script_dest = (
            os.path.join(install_dir, f"{basename}.py")
            if not getattr(sys, "frozen", False)
            else sys.executable
        )
        if win_ver >= 11:
            add_context_menu_win11(script_dest, ctx_file_flags, ctx_folder_flags)
        add_context_menu_win10(script_dest, ctx_file_flags, ctx_folder_flags)

    if cfg["use_task"]:
        task_scheduler.create_task(basename, os.path.join(install_dir, f"{basename}.py"))

    if cfg["add_to_path"]:
        add_to_path(install_dir, all_users=all_users)

    messagebox.showinfo(
        "PasteAsSyslinkWin",
        f"Installation complete!\n\nInstalled to: {install_dir}\n"
        f"{'(All users)' if all_users else '(Current user)'}",
    )
    sys.exit(0)


def _copy_script(install_dir: str, basename: str) -> None:
    """Copy the script/EXE and icon to the installation directory."""
    if getattr(sys, "frozen", False):
        src = sys.executable
        dst = os.path.join(install_dir, os.path.basename(sys.executable))
        if os.path.normpath(src) != os.path.normpath(dst):
            shutil.copy2(src, dst)
    else:
        src = os.path.abspath(sys.argv[0])
        dst = os.path.join(install_dir, f"{basename}.py")
        if os.path.normpath(src) != os.path.normpath(dst):
            shutil.copy2(src, dst)

        ico_src = os.path.join(os.path.dirname(src), f"{basename}.ico")
        ico_dst = os.path.join(install_dir, f"{basename}.ico")
        if os.path.isfile(ico_src) and not os.path.isfile(ico_dst):
            shutil.copy2(ico_src, ico_dst)


def run_uninstaller(basename: str, install_dir: str, use_task: bool) -> None:
    """Remove all installed components."""
    if use_task:
        task_scheduler.delete_task(basename)

    from src.context_menu import remove_context_menu_win10, remove_context_menu_win11

    remove_context_menu_win10()
    remove_context_menu_win11()

    remove_from_path(install_dir, all_users=False)
    remove_from_path(install_dir, all_users=True)

    shortcut_names = [
        f"{basename} Uninstaller.lnk",
        f"{basename} Re Adder.lnk",
    ]
    for name in shortcut_names:
        path = os.path.join(install_dir, name)
        if os.path.exists(path):
            os.remove(path)

    config = Config(install_dir, basename)
    config.delete()

    ico = os.path.join(install_dir, f"{basename}.ico")
    if os.path.exists(ico):
        os.remove(ico)

    messagebox.showinfo("PasteAsSyslinkWin", "Uninstallation complete!")
