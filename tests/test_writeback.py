"""Tests for JSON-socket writeback between parent and elevated child."""

import json
import socket
import sys
import threading

from src import writeback


class _LineReader:
    """Reads newline-delimited JSON messages, buffering across recv calls."""

    def __init__(self, sock):
        self._sock = sock
        self._buf = ""

    def read(self):
        while "\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                return None
            self._buf += chunk.decode("utf-8", "replace")
        line, self._buf = self._buf.split("\n", 1)
        return json.loads(line)


def test_extract_from_args_removes_pair():
    args = ["/f", "/d", writeback.FLAG, "54321", "dest"]
    port = writeback._extract_from_args(args)
    assert port == 54321
    assert args == ["/f", "/d", "dest"]


def test_extract_from_args_no_flag():
    args = ["/f", "dest"]
    assert writeback._extract_from_args(args) is None
    assert args == ["/f", "dest"]


def test_port_from_file(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    (tmp_path / "mklinktool.port").write_text("65432\n", encoding="utf-8")
    assert writeback._port_from_file("mklinktool") == 65432


def test_port_from_file_missing_or_garbage(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    assert writeback._port_from_file("mklinktool") is None
    (tmp_path / "mklinktool.port").write_text("not-a-port\n", encoding="utf-8")
    assert writeback._port_from_file("mklinktool") is None


def test_socket_stream_and_finish_send_messages():
    child_sock, parent_sock = socket.socketpair()
    reader = _LineReader(parent_sock)
    stream = writeback._SocketStream(child_sock, "stdout")
    stream.write("hello\n")
    handle = writeback.ChildWriteback(child_sock)
    handle.finish(0)
    child_sock.close()

    assert reader.read() == {"type": "output", "stream": "stdout", "data": "hello\n"}
    assert reader.read() == {"type": "finished", "code": 0}
    parent_sock.close()


def test_activate_child_redirects_and_finishes(monkeypatch):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    monkeypatch.setattr(sys, "argv", ["mklinktool", "/f", writeback.FLAG, str(port)])
    handle = writeback.activate_child("mklinktool")
    assert handle is not None
    assert sys.argv == ["mklinktool", "/f"]
    assert isinstance(sys.stdout, writeback._SocketStream)

    conn, _ = srv.accept()
    reader = _LineReader(conn)
    assert reader.read()["type"] == "start"
    handle.finish(7)
    assert reader.read() == {"type": "finished", "code": 7}
    conn.close()
    srv.close()


def test_activate_child_returns_none_without_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["mklinktool", "/f", "dest"])
    assert writeback.activate_child("mklinktool") is None


def test_activate_child_receives_args_from_port_file(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    (tmp_path / "mklinktool.port").write_text(f"{port}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["mklinktool"])
    writeback._child_args = None

    def server():
        conn, _ = srv.accept()
        reader = _LineReader(conn)
        assert reader.read()["type"] == "start"
        conn.sendall(b'{"type":"args","args":["/f","dest"]}\n')
        assert reader.read()["type"] == "finished"
        conn.close()

    t = threading.Thread(target=server, daemon=True)
    t.start()

    handle = writeback.activate_child("mklinktool")
    assert handle is not None
    assert writeback.child_args() == ["/f", "dest"]
    assert isinstance(sys.stdout, writeback._SocketStream)
    handle.finish(0)
    t.join(5)
    srv.close()
    writeback._child_args = None


def test_activate_child_does_not_read_args_from_argv(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    monkeypatch.setattr(sys, "argv", ["mklinktool", "/f", writeback.FLAG, str(port)])
    writeback._child_args = None

    handle = writeback.activate_child("mklinktool")
    assert handle is not None
    assert writeback.child_args() is None
    assert sys.argv == ["mklinktool", "/f"]

    conn, _ = srv.accept()
    reader = _LineReader(conn)
    assert reader.read()["type"] == "start"
    handle.finish(0)
    assert reader.read()["type"] == "finished"
    conn.close()
    srv.close()


def test_run_writeback_parent_sends_args(capsys):
    received = {}

    def launch(full):
        port = int(full[-1])

        def client():
            s = socket.create_connection(("127.0.0.1", port))
            received["args"] = _LineReader(s).read()
            s.sendall(b'{"type":"finished","code":0}\n')
            s.shutdown(socket.SHUT_WR)
            s.close()

        threading.Thread(target=client, daemon=True).start()
        return True

    code = writeback.run_writeback_parent(launch, ["/f", "dest path"])
    assert code == 0
    assert received["args"] == {"type": "args", "args": ["/f", "dest path"]}


def test_run_writeback_parent_relays_output_and_code(capsys):
    def launch(full):
        port = int(full[-1])

        def client():
            s = socket.create_connection(("127.0.0.1", port))
            s.sendall(b'{"type":"output","stream":"stdout","data":"created\\n"}\n')
            s.sendall(b'{"type":"output","stream":"stderr","data":"warn\\n"}\n')
            s.sendall(b'{"type":"finished","code":3}\n')
            s.shutdown(socket.SHUT_WR)
            s.close()

        threading.Thread(target=client, daemon=True).start()
        return True

    code = writeback.run_writeback_parent(launch, ["/f", "dest"])
    out, err = capsys.readouterr()
    assert code == 3
    assert "created" in out
    assert "warn" in err


def test_run_writeback_parent_launch_failure(capsys):
    code = writeback.run_writeback_parent(lambda full: False, ["/f"])
    assert code == 1
    assert "could not be started" in capsys.readouterr().err


def test_run_writeback_parent_connect_timeout(capsys, monkeypatch):
    monkeypatch.setattr(writeback, "_CONNECT_TIMEOUT", 0.2)
    code = writeback.run_writeback_parent(lambda full: True, ["/f"])
    assert code == 1
    assert "did not connect" in capsys.readouterr().err


def test_should_relay_true_with_terminal(monkeypatch):
    monkeypatch.setattr(writeback, "_silent", False)
    assert writeback.should_relay() is True


def test_null_streams_are_silent(monkeypatch):
    monkeypatch.setattr(writeback, "_silent", False)
    writeback._null_streams()
    assert writeback._silent is True
    assert isinstance(sys.stdout, writeback._NullStream)
    assert writeback.should_relay() is False
    assert sys.stdout.readline() == ""


def test_setup_console_streams_keeps_socket_streams(monkeypatch):
    child_sock, _ = socket.socketpair()
    stream = writeback._SocketStream(child_sock, "stdout")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(writeback, "_std_handle_state", lambda: "redirected")
    monkeypatch.setattr(writeback, "_launched_from_terminal", lambda: False)
    monkeypatch.setattr(writeback, "_hide_console_window", lambda: None)
    writeback.setup_console_streams(writeback_child="handle")
    assert sys.stdout is stream
    child_sock.close()


def test_setup_console_streams_nulls_when_not_child(monkeypatch):
    monkeypatch.setattr(sys, "stdout", sys.__stdout__)
    monkeypatch.setattr(sys, "stderr", sys.__stderr__)
    monkeypatch.setattr(writeback, "_silent", False)
    monkeypatch.setattr(writeback, "_std_handle_state", lambda: "missing")
    monkeypatch.setattr(writeback, "_launched_from_terminal", lambda: False)
    monkeypatch.setattr(writeback, "_hide_console_window", lambda: True)
    monkeypatch.setattr(writeback, "_attach_to_parent_console", lambda: False)
    writeback.setup_console_streams(writeback_child=None)
    assert writeback._silent is True
    assert isinstance(sys.stdout, writeback._NullStream)
    assert writeback.should_relay() is False


def test_setup_console_streams_keeps_redirected_handles_when_hidden(monkeypatch):
    monkeypatch.setattr(sys, "stdout", sys.__stdout__)
    monkeypatch.setattr(sys, "stderr", sys.__stderr__)
    monkeypatch.setattr(writeback, "_silent", False)
    monkeypatch.setattr(writeback, "_std_handle_state", lambda: "redirected")
    monkeypatch.setattr(writeback, "_launched_from_terminal", lambda: False)
    monkeypatch.setattr(writeback, "_hide_console_window", lambda: True)
    writeback.setup_console_streams(writeback_child=None)
    assert writeback._silent is False
    assert sys.stdout is sys.__stdout__


def test_setup_console_streams_keeps_redirected_streams(monkeypatch):
    monkeypatch.setattr(sys, "stdout", sys.__stdout__)
    monkeypatch.setattr(sys, "stderr", sys.__stderr__)
    monkeypatch.setattr(writeback, "_launched_from_terminal", lambda: False)
    monkeypatch.setattr(writeback, "_hide_console_window", lambda: False)
    writeback.setup_console_streams(writeback_child=None)
    assert sys.stdout is sys.__stdout__
    assert writeback._silent is False


def test_setup_console_streams_shim_attach_wires_console(monkeypatch):
    """CLI shim: no terminal of our own -> attach to the parent's console."""
    monkeypatch.setattr(writeback, "_silent", False)
    monkeypatch.setattr(writeback, "_std_handle_state", lambda: "missing")
    monkeypatch.setattr(writeback, "_launched_from_terminal", lambda: False)
    monkeypatch.setattr(writeback, "_hide_console_window", lambda: True)
    monkeypatch.setattr(writeback, "_attach_to_parent_console", lambda: True)
    wired = {}
    monkeypatch.setattr(writeback, "_wire_console_streams", lambda: wired.setdefault("ok", True))
    writeback.setup_console_streams(writeback_child=None)
    assert wired.get("ok")
    assert writeback._silent is False


def test_setup_console_streams_foreign_console_handles_rewired(monkeypatch):
    """Inherited-but-foreign console handles: attach then force a rewire."""
    monkeypatch.setattr(writeback, "_silent", False)
    monkeypatch.setattr(writeback, "_std_handle_state", lambda: "console")
    monkeypatch.setattr(writeback, "_launched_from_terminal", lambda: False)
    monkeypatch.setattr(writeback, "_hide_console_window", lambda: False)
    monkeypatch.setattr(writeback, "_attach_to_parent_console", lambda: True)
    calls = []
    monkeypatch.setattr(writeback, "_force_rewire_console", lambda: calls.append("rewire"))
    writeback.setup_console_streams(writeback_child=None)
    assert calls == ["rewire"]
    assert writeback._silent is False


def test_setup_console_streams_terminal_console_untouched(monkeypatch):
    """Launched from a terminal with our own console: leave everything alone."""
    monkeypatch.setattr(sys, "stdout", sys.__stdout__)
    monkeypatch.setattr(writeback, "_std_handle_state", lambda: "console")
    monkeypatch.setattr(writeback, "_launched_from_terminal", lambda: True)
    monkeypatch.setattr(writeback, "_hide_console_window", lambda: True)
    writeback.setup_console_streams(writeback_child=None)
    assert sys.stdout is sys.__stdout__


def test_setup_console_streams_writeback_child_never_nulled(monkeypatch):
    """Elevated relay keeps its socket streams even without a console."""
    child_sock, _ = socket.socketpair()
    stream = writeback._SocketStream(child_sock, "stdout")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(writeback, "_silent", False)
    monkeypatch.setattr(writeback, "_std_handle_state", lambda: "missing")
    monkeypatch.setattr(writeback, "_launched_from_terminal", lambda: False)
    monkeypatch.setattr(writeback, "_hide_console_window", lambda: True)
    monkeypatch.setattr(writeback, "_attach_to_parent_console", lambda: True)
    writeback.setup_console_streams(writeback_child="handle")
    assert sys.stdout is stream
    assert writeback._silent is False
    child_sock.close()


def test_std_handle_state_pipe_and_disk_are_redirected(monkeypatch):
    """Real GetFileType values: DISK=1 and PIPE=3 are caller redirects."""
    k32 = writeback.ctypes.windll.kernel32
    monkeypatch.setattr(k32, "GetStdHandle", lambda which: 0x100)
    monkeypatch.setattr(k32, "GetFileType", lambda h: 0x0003)  # FILE_TYPE_PIPE
    assert writeback._std_handle_state() == "redirected"
    monkeypatch.setattr(k32, "GetFileType", lambda h: 0x0001)  # FILE_TYPE_DISK
    assert writeback._std_handle_state() == "redirected"


def test_std_handle_state_char_is_console(monkeypatch):
    """FILE_TYPE_CHAR (2) is a console buffer, not a redirect."""
    k32 = writeback.ctypes.windll.kernel32
    monkeypatch.setattr(k32, "GetStdHandle", lambda which: 0x100)
    monkeypatch.setattr(k32, "GetFileType", lambda h: 0x0002)  # FILE_TYPE_CHAR
    assert writeback._std_handle_state() == "console"


def test_std_handle_state_invalid_or_unknown_is_missing(monkeypatch):
    k32 = writeback.ctypes.windll.kernel32
    monkeypatch.setattr(k32, "GetStdHandle", lambda which: 0)
    assert writeback._std_handle_state() == "missing"
    monkeypatch.setattr(k32, "GetStdHandle", lambda which: 0x100)
    monkeypatch.setattr(k32, "GetFileType", lambda h: 0x0000)  # FILE_TYPE_UNKNOWN
    assert writeback._std_handle_state() == "missing"


def test_setup_console_streams_terminal_missing_rewired(monkeypatch):
    """In a terminal with broken handles: rebuild them from the console."""
    monkeypatch.setattr(writeback, "_std_handle_state", lambda: "missing")
    monkeypatch.setattr(writeback, "_launched_from_terminal", lambda: True)
    calls = []
    monkeypatch.setattr(writeback, "_force_rewire_console", lambda: calls.append("rewire"))
    writeback.setup_console_streams(writeback_child=None)
    assert calls == ["rewire"]
    assert writeback._silent is False
