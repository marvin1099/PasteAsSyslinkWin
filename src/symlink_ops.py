"""Symlink creation with conflict resolution dialog."""

import os
import secrets
import subprocess
import tkinter as tk

PROBE_PREFIX = ".mklinktool_probe_"
PROBE_SUFFIX = ".tmp"


def create_write_probe(dest_dir: str) -> str | None:
    """Create a write-proof probe file inside ``dest_dir``.

    The probe is created by the *unprivileged* caller and left in place so
    the elevated process can verify it before acting. Because the file can
    only exist when the caller could genuinely write to the destination, a
    silent (task-scheduler) elevation is only safe when the probe verifies.

    Args:
        dest_dir: Directory to probe.

    Returns:
        Full path of the created probe, or None when the directory is
        missing or not writable.
    """
    if not dest_dir or not os.path.isdir(dest_dir):
        return None
    token = secrets.token_hex(8)
    probe = os.path.join(dest_dir, f"{PROBE_PREFIX}{token}{PROBE_SUFFIX}")
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write(token)
        return probe
    except OSError:
        return None


def verify_write_probe(dest_dir: str, probe_path: str) -> bool:
    """Verify a write-probe file and remove it.

    Returns True only when the file sits directly inside ``dest_dir``, its
    name has the expected prefix/suffix, and its content matches the token
    encoded in the name (i.e. it was produced by create_write_probe). The
    dest_dir check prevents an attacker from pointing at a probe they can
    write while the operation targets a protected folder.

    Args:
        dest_dir: The destination directory that must contain the probe.
        probe_path: Full path of the probe to verify.
    """
    if not dest_dir or not probe_path:
        return False
    if os.path.normcase(os.path.dirname(probe_path)) != os.path.normcase(
        os.path.normpath(dest_dir)
    ):
        return False
    name = os.path.basename(probe_path)
    if not (name.startswith(PROBE_PREFIX) and name.endswith(PROBE_SUFFIX)):
        return False
    token = name[len(PROBE_PREFIX) : -len(PROBE_SUFFIX)]
    try:
        with open(probe_path, encoding="utf-8") as f:
            if f.read().strip() != token:
                return False
        os.remove(probe_path)
        return True
    except OSError:
        return False


def remove_probe_files(dest_dir: str) -> int:
    """Remove leftover probe files in ``dest_dir`` (crash cleanup).

    Args:
        dest_dir: Directory to scan.

    Returns:
        Number of probe files removed.
    """
    if not dest_dir or not os.path.isdir(dest_dir):
        return 0
    removed = 0
    try:
        for name in os.listdir(dest_dir):
            if name.startswith(PROBE_PREFIX) and name.endswith(PROBE_SUFFIX):
                try:
                    os.remove(os.path.join(dest_dir, name))
                    removed += 1
                except OSError:
                    pass
    except OSError:
        pass
    return removed


def create_symlink(source: str, dest: str, flags: str) -> bool:
    """Create a symlink/hardlink/junction via mklink.

    Args:
        source: The original file/folder path.
        dest: The destination path (where the link goes).
        flags: mklink flags string (e.g. "/f /h", "/d", "/d /j").

    Returns:
        True on success, False on failure.
    """
    flag_parts = flags.strip().split()
    cmd_parts = ["cmd", "/c", "mklink"] + flag_parts + [dest, source]
    result = subprocess.run(
        subprocess.list2cmdline(cmd_parts),
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode == 0


def _next_available_name(dest_path: str, name: str, is_dir: bool) -> str:
    """Generate next available name with (N) suffix."""
    base, ext = os.path.splitext(name)
    candidate = os.path.join(dest_path, name)
    counter = 1
    while os.path.exists(candidate):
        if is_dir:
            candidate = os.path.join(dest_path, f"{base} ({counter})")
        else:
            candidate = os.path.join(dest_path, f"{base} ({counter}){ext}")
        counter += 1
    return candidate


class ConflictDialog:
    """Tkinter dialog for file/folder conflict resolution."""

    OVERWRITE = "overwrite"
    RENAME = "rename"
    SKIP = "skip"

    def __init__(self, items: list[tuple[str, str, bool]]):
        """
        Args:
            items: List of (source, dest, is_dir) tuples for conflicting items.
        """
        self.items = items
        self.results: dict[str, str] = {}
        self.apply_to_all = False
        self.apply_to_all_action: str | None = None

        self.root = tk.Tk()
        self.root.title("Symlink Conflict")
        self.root.geometry("600x450")
        self.root.resizable(True, True)
        self._build_ui()
        self.root.mainloop()

    def _build_ui(self):
        title = tk.Label(
            self.root,
            text=f"{len(self.items)} item(s) already exist at destination:",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )
        title.pack(fill="x", padx=12, pady=(12, 4))

        list_frame = tk.Frame(self.root)
        list_frame.pack(fill="both", expand=True, padx=12, pady=4)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set,
            font=("Consolas", 9), selectmode="single",
        )
        self.listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)

        for src, _dst, is_dir in self.items:
            kind = "folder" if is_dir else "file"
            self.listbox.insert("end", f"[{kind}] {os.path.basename(src)}")

        if self.items:
            self.listbox.select_set(0)
            self.listbox.see(0)

        action_frame = tk.Frame(self.root)
        action_frame.pack(fill="x", padx=12, pady=8)

        self.apply_all_var = tk.BooleanVar(value=False)
        apply_check = tk.Checkbutton(
            action_frame,
            text="Apply to all remaining conflicts",
            variable=self.apply_all_var,
            command=self._on_apply_all_changed,
        )
        apply_check.pack(side="left")

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=12, pady=(0, 12))

        overwrite_btn = tk.Button(
            btn_frame,
            text="Overwrite",
            width=14,
            command=lambda: self._choose(self.OVERWRITE),
        )
        overwrite_btn.pack(side="left", padx=(0, 4))

        rename_btn = tk.Button(
            btn_frame,
            text="Rename (-N)",
            width=14,
            command=lambda: self._choose(self.RENAME),
        )
        rename_btn.pack(side="left", padx=4)

        skip_btn = tk.Button(
            btn_frame,
            text="Skip",
            width=14,
            command=lambda: self._choose(self.SKIP),
        )
        skip_btn.pack(side="left", padx=4)

        self.status_label = tk.Label(
            btn_frame,
            text=f"1 / {len(self.items)} resolved",
            fg="gray",
        )
        self.status_label.pack(side="right")

    def _on_apply_all_changed(self):
        self.apply_to_all = self.apply_all_var.get()

    def _choose(self, action: str):
        if self.apply_to_all:
            for _, dst, _ in self.items:
                self.results[dst] = action
            self.root.destroy()
            return

        selected = self.listbox.curselection()
        if selected:
            idx = selected[0]
            if idx < len(self.items):
                _, dst, _ = self.items[idx]
                self.results[dst] = action
                self.listbox.delete(idx)
                self.items.pop(idx)
                resolved = len(self.results)
                total = resolved + len(self.items)
                self.status_label.config(text=f"{resolved} / {total} resolved")

                if self.items:
                    next_idx = min(idx, len(self.items) - 1)
                    self.listbox.select_set(next_idx)
                    self.listbox.see(next_idx)

        if not self.items:
            self.root.destroy()


def resolve_conflicts(items: list[tuple[str, str, bool]]) -> dict[str, str]:
    """Show the conflict dialog and return resolution map.

    Args:
        items: List of (source, dest, is_dir) for items that conflict.

    Returns:
        Dict mapping destination path to action ("overwrite", "rename", "skip").
    """
    if not items:
        return {}
    dialog = ConflictDialog(items)
    return dialog.results


def process_links(
    file_paths: list[str],
    folder_paths: list[str],
    dest_dir: str,
    file_flags: str,
    folder_flags: str,
) -> tuple[int, int]:
    """Create symlinks for all files and folders.

    If a conflict is encountered, shows the conflict dialog.

    Returns:
        Tuple of (success_count, skip_count).
    """
    conflicts = []

    for src in file_paths:
        name = os.path.basename(src)
        dest = os.path.join(dest_dir, name)
        if os.path.exists(dest):
            conflicts.append((src, dest, False))

    for src in folder_paths:
        name = os.path.basename(src)
        dest = os.path.join(dest_dir, name)
        if os.path.exists(dest):
            conflicts.append((src, dest, True))

    resolutions = resolve_conflicts(conflicts) if conflicts else {}

    success = 0
    skipped = 0

    for src in file_paths:
        name = os.path.basename(src)
        dest = os.path.join(dest_dir, name)

        if dest in resolutions:
            action = resolutions[dest]
            if action == "skip":
                skipped += 1
                continue
            elif action == "rename":
                dest = _next_available_name(dest_dir, name, False)
            elif action == "overwrite":
                try:
                    if os.path.islink(dest):
                        os.unlink(dest)
                    elif os.path.isfile(dest):
                        os.remove(dest)
                except OSError:
                    skipped += 1
                    continue

        if create_symlink(src, dest, file_flags):
            success += 1
        else:
            skipped += 1

    for src in folder_paths:
        name = os.path.basename(src)
        dest = os.path.join(dest_dir, name)

        if dest in resolutions:
            action = resolutions[dest]
            if action == "skip":
                skipped += 1
                continue
            elif action == "rename":
                dest = _next_available_name(dest_dir, name, True)
            elif action == "overwrite":
                try:
                    if os.path.islink(dest):
                        os.unlink(dest)
                    elif os.path.isdir(dest):
                        os.rmdir(dest)
                except OSError:
                    skipped += 1
                    continue

        if create_symlink(src, dest, folder_flags):
            success += 1
        else:
            skipped += 1

    return success, skipped
