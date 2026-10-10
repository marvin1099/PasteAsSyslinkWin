"""Symlink creation with conflict resolution dialog."""

import ctypes
import os
import secrets
import struct
from ctypes import wintypes

PROBE_PREFIX = ".mklinktool_probe_"
PROBE_SUFFIX = ".tmp"

# ── Win32 API bindings ──────────────────────────────────────────────────────
# Direct API calls are ~26x faster than spawning cmd /c mklink per link
# (benchmarked: 1.1s vs 28s for 300 hardlinks).

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_kernel32.CreateSymbolicLinkW.argtypes = [
    wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
]
_kernel32.CreateSymbolicLinkW.restype = wintypes.BOOLEAN

_kernel32.CreateHardLinkW.argtypes = [
    wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
]
_kernel32.CreateHardLinkW.restype = wintypes.BOOLEAN

_kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
]
_kernel32.CreateFileW.restype = wintypes.HANDLE

_kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
_kernel32.DeviceIoControl.restype = wintypes.BOOL

_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL

SYMBOLIC_LINK_FLAG_DIRECTORY = 0x1
SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE = 0x2

GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FSCTL_SET_REPARSE_POINT = 0x000900A4
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

_MAX_PATH = 260


def _symlink(source: str, dest: str, is_dir: bool) -> bool:
    """Create a symbolic link via CreateSymbolicLinkW.

    Tries with ALLOW_UNPRIVILEGED_CREATE first (works in Developer Mode),
    then without it (works when elevated with SeCreateSymbolicLinkPrivilege).
    """
    flags = SYMBOLIC_LINK_FLAG_DIRECTORY if is_dir else 0
    result = _kernel32.CreateSymbolicLinkW(
        dest, source, flags | SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE
    )
    if not result:
        result = _kernel32.CreateSymbolicLinkW(dest, source, flags)
    return bool(result)


def _hardlink(source: str, dest: str) -> bool:
    """Create a hard link via CreateHardLinkW."""
    return bool(_kernel32.CreateHardLinkW(dest, source, None))


def _junction(source: str, dest: str) -> bool:
    """Create a directory junction at ``dest`` pointing to ``source``.

    Junctions use a reparse point with an NT namespace substitute name
    (\\??\\C:\\path) and a Win32 print name (C:\\path). Unlike symlinks,
    junctions require no special privilege.
    """
    target = os.path.abspath(source)

    substitute = f"\\??\\{target}".encode("utf-16-le")
    print_name = target.encode("utf-16-le")
    sub_len = len(substitute)
    prt_len = len(print_name)

    # MountPointReparseBuffer: SubstituteNameOffset, SubstituteNameLength,
    # PrintNameOffset, PrintNameLength, then PathBuffer (null-terminated UTF-16).
    mount_header = struct.pack("<HHHH", 0, sub_len, sub_len + 2, prt_len)
    path_buffer = substitute + b"\x00\x00" + print_name + b"\x00\x00"
    mount_data = mount_header + path_buffer

    reparse_buffer = struct.pack(
        "<LHH", IO_REPARSE_TAG_MOUNT_POINT, len(mount_data), 0
    ) + mount_data

    os.makedirs(dest, exist_ok=True)
    handle = _kernel32.CreateFileW(
        dest, GENERIC_WRITE, 0, None, OPEN_EXISTING,
        FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, None,
    )
    if handle == INVALID_HANDLE_VALUE:
        return False
    try:
        buf = ctypes.create_string_buffer(reparse_buffer)
        returned = wintypes.DWORD(0)
        return bool(_kernel32.DeviceIoControl(
            handle, FSCTL_SET_REPARSE_POINT, buf, len(reparse_buffer),
            None, 0, ctypes.byref(returned), None,
        ))
    finally:
        _kernel32.CloseHandle(handle)


def create_link(source: str, dest: str, flags: str) -> bool:
    """Create a symlink, hardlink, or junction using direct Win32 API calls.

    Args:
        source: The original file/folder path.
        dest: The destination path (where the link goes).
        flags: mklink-style flags: "" for file symlink, "/h" hardlink,
               "/d" directory symlink, "/j" directory junction.

    Returns:
        True on success, False on failure.
    """
    flag_set = flags.split()
    if "/j" in flag_set:
        return _junction(source, dest)
    if "/h" in flag_set:
        return _hardlink(source, dest)
    if "/d" in flag_set:
        return _symlink(source, dest, is_dir=True)
    return _symlink(source, dest, is_dir=False)


# Backwards-compatible alias (older call sites may import create_symlink).
create_symlink = create_link


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
        import tkinter as tk  # lazy: only loaded when conflicts actually occur

        self._tk = tk
        self.items = items
        self.results: dict[str, str] = {}
        self.apply_to_all = False

        self.root = tk.Tk()
        self.root.title("Symlink Conflict")
        self.root.geometry("600x450")
        self.root.resizable(True, True)
        self._build_ui()
        self.root.mainloop()

    def _build_ui(self):
        tk = self._tk
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
        tk.Checkbutton(
            action_frame,
            text="Apply to all remaining conflicts",
            variable=self.apply_all_var,
            command=self._on_apply_all_changed,
        ).pack(side="left")

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=12, pady=(0, 12))

        for label, action in (
            ("Overwrite", self.OVERWRITE),
            ("Rename (-N)", self.RENAME),
            ("Skip", self.SKIP),
        ):
            tk.Button(
                btn_frame, text=label, width=14,
                command=lambda a=action: self._choose(a),
            ).pack(side="left", padx=(0, 4) if label == "Overwrite" else 4)

        self.status_label = tk.Label(
            btn_frame, text=f"1 / {len(self.items)} resolved", fg="gray",
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
    return ConflictDialog(items).results


def process_links(
    file_paths: list[str],
    folder_paths: list[str],
    dest_dir: str,
    file_flags: str,
    folder_flags: str,
) -> tuple[int, int]:
    """Create links for all files and folders.

    If a conflict is encountered, shows the conflict dialog.

    Returns:
        Tuple of (success_count, skip_count).
    """
    conflicts = []

    for src in file_paths:
        dest = os.path.join(dest_dir, os.path.basename(src))
        if os.path.exists(dest):
            conflicts.append((src, dest, False))

    for src in folder_paths:
        dest = os.path.join(dest_dir, os.path.basename(src))
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

        if create_link(src, dest, file_flags):
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

        if create_link(src, dest, folder_flags):
            success += 1
        else:
            skipped += 1

    return success, skipped
