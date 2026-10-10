"""JSON-socket writeback so elevated child processes relay output to the parent.

Protocol (newline-delimited JSON over a TCP connection to 127.0.0.1):
    {"type": "start", "pid": <int>}
    {"type": "output", "stream": "stdout"|"stderr", "data": "<text>"}
    {"type": "finished", "code": <int>}
"""

import contextlib
import ctypes
import json
import os
import socket
import sys

FLAG = "/writeback"
_CONNECT_TIMEOUT = 300.0
_ARGS_TIMEOUT = 30.0
_silent = False
_child_args: list[str] | None = None


class _NullStream:
    """Sink that discards writes and yields no input."""

    def write(self, data) -> int:
        return len(data)

    def flush(self) -> None:
        pass

    def read(self, size=-1) -> str:
        return ""

    def readline(self) -> str:
        return ""

    def isatty(self) -> bool:
        return False


def dbg(msg: str) -> None:
    """Append a diagnostic line when MKLINKTOOL_DEBUG is set."""
    if os.environ.get("MKLINKTOOL_DEBUG"):
        try:
            import tempfile

            path = os.path.join(tempfile.gettempdir(), "mklinktool_debug.log")
            with open(path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except OSError:
            pass


def _send(sock: socket.socket, obj: dict) -> None:
    with contextlib.suppress(OSError):
        sock.sendall((json.dumps(obj) + "\n").encode("utf-8", "replace"))


class _SocketStream:
    """File-like object that relays each write as a JSON output message."""

    def __init__(self, sock: socket.socket, name: str) -> None:
        self._sock = sock
        self._name = name

    def write(self, data) -> int:
        if data:
            _send(self._sock, {"type": "output", "stream": self._name, "data": data})
        return len(data)

    def flush(self) -> None:
        pass


class ChildWriteback:
    """Child-side handle used to signal the parent when work is done."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    def finish(self, code: int) -> None:
        _send(self._sock, {"type": "finished", "code": code})
        try:
            self._sock.shutdown(socket.SHUT_WR)
            self._sock.close()
        except OSError:
            pass


def _extract_from_args(args: list[str]) -> int | None:
    """Pop the writeback flag and port from ``args`` in place."""
    if FLAG not in args:
        return None
    i = args.index(FLAG)
    port = None
    if i + 1 < len(args):
        try:
            port = int(args[i + 1])
        except ValueError:
            port = None
        del args[i : i + 2]
    else:
        del args[i]
    return port


def _port_from_file(basename: str) -> int | None:
    """Read the writeback port marker written by the task-scheduler parent."""
    import tempfile

    path = os.path.join(tempfile.gettempdir(), f"{basename}.port")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read().strip()
    except OSError:
        return None
    try:
        return int(content)
    except ValueError:
        return None


def _recv_args(sock: socket.socket) -> list[str] | None:
    """Read the parent's args message, blocking up to ``_ARGS_TIMEOUT``."""
    sock.settimeout(_ARGS_TIMEOUT)
    buf = ""
    try:
        while True:
            data = sock.recv(65536)
            if not data:
                return None
            buf += data.decode("utf-8", "replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("type") == "args":
                    return list(msg.get("args") or [])
    except OSError:
        return None


def child_args() -> list[str] | None:
    """Args received from the parent (task-scheduler relay), or None."""
    return _child_args


def activate_child(basename: str) -> ChildWriteback | None:
    """Wire stdout/stderr to the parent when this is an elevated child.

    Returns a handle used to send the final status, or None when the process
    is running normally. When launched by the task scheduler (port comes from
    the marker file), the real arguments arrive over the socket instead of a
    temp args file.
    """
    global _child_args
    from_file = False
    port = _extract_from_args(sys.argv)
    if port is None:
        port = _port_from_file(basename)
        from_file = port is not None
    if port is None:
        return None
    try:
        sock = socket.create_connection(("127.0.0.1", port))
    except OSError:
        return None
    _send(sock, {"type": "start", "pid": os.getpid()})
    if from_file:
        args = _recv_args(sock)
        if args is None:
            sock.close()
            return None
        _child_args = args
    sys.stdout = _SocketStream(sock, "stdout")
    sys.stderr = _SocketStream(sock, "stderr")
    return ChildWriteback(sock)


def should_relay() -> bool:
    """Only host a writeback server when output goes to a real terminal/stream."""
    return not _silent and sys.stdout is not None


def is_silent() -> bool:
    """True when output was routed to null sinks (no terminal available)."""
    return _silent


def _process_exe_map() -> dict[int, str]:
    """Map all running PIDs to their executable names."""
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap == -1:
        return {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        result = {}
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            result[int(entry.th32ProcessID)] = entry.szExeFile
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
        return result
    finally:
        kernel32.CloseHandle(snap)


_TERMINAL_SHELLS = {"cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "zsh.exe", "sh.exe"}


def _launched_from_terminal() -> bool:
    """True when our console is shared with a real terminal shell."""
    try:
        kernel32 = ctypes.windll.kernel32
        if not kernel32.GetConsoleWindow():
            return False
        pids = (ctypes.c_uint * 32)()
        count = kernel32.GetConsoleProcessList(pids, 32)
        if count <= 1:
            return False  # console was created just for this process
        names = _process_exe_map()
        return any(names.get(int(pid), "").lower() in _TERMINAL_SHELLS for pid in pids[:count])
    except Exception:
        return True  # uncertain -> keep the console visible


def _hide_console_window() -> bool:
    """Hide the console window; True when a window existed."""
    try:
        kernel32 = ctypes.windll.kernel32
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
            return True
    except Exception:
        pass
    return False


def _null_streams() -> None:
    """Replace std streams with null sinks (silent, no terminal)."""
    global _silent
    _silent = True
    if not isinstance(sys.stdout, _SocketStream):
        sys.stdout = _NullStream()
    if not isinstance(sys.stderr, _SocketStream):
        sys.stderr = _NullStream()
    if not isinstance(sys.stdin, _SocketStream):
        sys.stdin = _NullStream()


def _attach_to_parent_console() -> bool:
    try:
        kernel32 = ctypes.windll.kernel32
        return bool(kernel32.AttachConsole(0xFFFFFFFF))  # ATTACH_PARENT_PROCESS
    except Exception:
        return False


def _valid_handle(h) -> bool:
    return bool(h) and h != ctypes.c_void_p(-1).value


def _wire_console_streams() -> bool:
    """Point std streams at the attached console so output reaches the terminal.

    When the launcher already provided real standard handles (e.g. a shell
    redirected ``> out.txt``), those are reused instead of CONOUT$/CONIN$.
    """
    kernel32 = ctypes.windll.kernel32
    try:
        if _valid_handle(kernel32.GetStdHandle(-11)):  # STD_OUTPUT_HANDLE
            sys.stdout = os.fdopen(1, "w", encoding="utf-8", errors="replace", buffering=1)
            if _valid_handle(kernel32.GetStdHandle(-12)):  # STD_ERROR_HANDLE
                sys.stderr = os.fdopen(2, "w", encoding="utf-8", errors="replace", buffering=1)
            else:
                sys.stderr = _NullStream()
            if _valid_handle(kernel32.GetStdHandle(-10)):  # STD_INPUT_HANDLE
                sys.stdin = os.fdopen(0, "r", encoding="utf-8", errors="replace")
            else:
                sys.stdin = _NullStream()
            return True
    except OSError:
        pass
    for name, mode in ((1, os.O_WRONLY), (2, os.O_WRONLY)):
        try:
            fd = os.open("CONOUT$", mode)
            os.dup2(fd, name)
            os.close(fd)
        except OSError:
            return False
    try:
        sys.stdout = os.fdopen(1, "w", encoding="utf-8", errors="replace", buffering=1)
        sys.stderr = os.fdopen(2, "w", encoding="utf-8", errors="replace", buffering=1)
        try:
            fd = os.open("CONIN$", os.O_RDONLY)
            os.dup2(fd, 0)
            os.close(fd)
            sys.stdin = os.fdopen(0, "r", encoding="utf-8", errors="replace")
        except OSError:
            sys.stdin = _NullStream()
        return True
    except OSError:
        return False


def _std_handle_state() -> str:
    """Classify our stdout handle: ``missing``, ``console`` or ``redirected``.

    Uses the real ``GetFileType`` values: ``FILE_TYPE_DISK`` (1) and
    ``FILE_TYPE_PIPE`` (3) are caller-provided redirects, ``FILE_TYPE_CHAR``
    (2) is a console buffer (or the NUL device), anything else is missing.
    Console handles are only usable while attached to that console.
    """
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        if not _valid_handle(handle):
            dbg("state: stdout handle invalid")
            return "missing"
        file_type = kernel32.GetFileType(handle)
        hin = kernel32.GetStdHandle(-10)
        htype_in = kernel32.GetFileType(hin) if _valid_handle(hin) else -1
        herr = kernel32.GetStdHandle(-12)
        type_err = kernel32.GetFileType(herr) if _valid_handle(herr) else -1
        dbg(
            f"state: out=0x{handle & 0xFFFFFFFFFFFFFFFF:x}/0x{file_type:x} "
            f"in=0x{hin & 0xFFFFFFFFFFFFFFFF:x}/0x{htype_in & 0xFFFFFFFF:x} "
            f"err=0x{herr & 0xFFFFFFFFFFFFFFFF:x}/0x{type_err & 0xFFFFFFFF:x} "
            f"conwin={kernel32.GetConsoleWindow() & 0xFFFFFFFFFFFFFFFF:x} "
            f"cp={kernel32.GetConsoleCP()}"
        )
        if file_type in (0x0001, 0x0003):  # FILE_TYPE_DISK / FILE_TYPE_PIPE
            return "redirected"
        if file_type == 0x0002:  # FILE_TYPE_CHAR (console buffer / NUL)
            return "console"
        return "missing"  # FILE_TYPE_UNKNOWN
    except Exception:
        return "missing"


def _std_handles_redirected() -> bool:
    """True when the launcher redirected stdout to a pipe or file.

    In that case output must be kept even without a terminal attached:
    the caller explicitly asked for it (e.g. ``> out.txt`` or
    ``Start-Process -RedirectStandardOutput``).
    """
    return _std_handle_state() == "redirected"


def _force_rewire_console() -> bool:
    """Replace the current std handles with this console's real handles.

    Needed after attaching when the launcher passed in foreign console
    handles: those are valid handle values but unusable in this process.
    """
    try:
        for fd in (1, 2):
            h = os.open("CONOUT$", os.O_WRONLY)
            os.dup2(h, fd)
            os.close(h)
    except OSError:
        return False
    try:
        sys.stdout = os.fdopen(1, "w", encoding="utf-8", errors="replace", buffering=1)
        sys.stderr = os.fdopen(2, "w", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        return False
    try:
        h = os.open("CONIN$", os.O_RDONLY)
        os.dup2(h, 0)
        os.close(h)
        sys.stdin = os.fdopen(0, "r", encoding="utf-8", errors="replace")
    except OSError:
        sys.stdin = _NullStream()
    return True


def setup_console_streams(writeback_child: ChildWriteback | None = None) -> None:
    """Route console output: terminal when launched from one, silent otherwise.

    - Launcher-provided pipes/files are kept untouched (``> out.txt``).
    - When our console is shared with a real terminal shell, keep everything.
    - Windowed builds (no console) attach to the launching terminal's console
      via the CLI shim, or go silent when there is none.
    - Any console window we own but no terminal uses it: hide it so nothing
      pops up (Explorer / task scheduler / UAC launches).
    """
    state = _std_handle_state()
    terminal = _launched_from_terminal()
    dbg(f"setup: state={state} terminal={terminal} wb={writeback_child is not None}")

    if state == "redirected":
        # Caller-provided pipe/file: always keep it; hide any console we own.
        if not terminal:
            _hide_console_window()
        dbg("setup: branch=redirected")
        return

    if state == "console":
        if terminal:
            dbg("setup: branch=terminal-console")
            return  # console shared with a real shell: leave everything alone
        _hide_console_window()
        if writeback_child is not None:
            dbg("setup: branch=console-writeback")
            return  # elevated relay: stdout/stderr are already sockets
        if _attach_to_parent_console():
            # Handles may be foreign: rebuild them from the attached console.
            rewired = _force_rewire_console()
            dbg(f"setup: branch=console-attach ok={rewired}")
            return
        _null_streams()
        dbg("setup: branch=console-null")
        return

    # state == "missing": no usable stdout handle.
    if terminal:
        rewired = _force_rewire_console()
        dbg(f"setup: branch=terminal-rewire ok={rewired}")
        return
    _hide_console_window()
    if writeback_child is not None:
        dbg("setup: branch=missing-writeback")
        return  # elevated relay: stdout/stderr are already sockets
    if _attach_to_parent_console():
        wired = _wire_console_streams()
        dbg(f"setup: branch=attach-wire ok={wired}")
        return
    _null_streams()
    dbg("setup: branch=null-streams")


def run_writeback_parent(launch, args: list[str]) -> int:
    """Host a writeback socket while ``launch`` starts the elevated child.

    ``launch`` receives the full argument list (``args`` plus the writeback
    flag and port) and must return True when the child was started.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
    except OSError:
        return 1

    srv.settimeout(_CONNECT_TIMEOUT)
    try:
        launched = bool(launch(args + [FLAG, str(port)]))
    except Exception:
        launched = False

    if not launched:
        srv.close()
        _print_to(sys.stderr, "Elevation could not be started.")
        return 1

    try:
        conn, _ = srv.accept()
    except OSError:
        srv.close()
        _print_to(sys.stderr, "Elevated process did not connect.")
        return 1
    srv.close()

    _send(conn, {"type": "args", "args": args})
    conn.settimeout(None)
    code = 0
    buf = ""
    try:
        while True:
            data = conn.recv(65536)
            if not data:
                code = 1
                break
            buf += data.decode("utf-8", "replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("type") == "output":
                    target = sys.stderr if msg.get("stream") == "stderr" else sys.stdout
                    if target is not None:
                        target.write(msg["data"])
                        target.flush()
                elif msg.get("type") == "finished":
                    code = int(msg.get("code", 0))
                    return code
    except OSError:
        code = 1
    finally:
        with contextlib.suppress(OSError):
            conn.close()
    return code


def _print_to(stream, msg: str) -> None:
    if stream is not None:
        try:
            stream.write(msg + "\n")
            stream.flush()
        except (AttributeError, OSError):
            pass
