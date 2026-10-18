"""Tests for clipboard reads: HDROP + text paths, transient-failure retry."""

import ctypes

import pytest

from src import clipboard


class FakeUser32:
    def __init__(self, open_results=(), hdrop=True, text=True, hdrop_data=1, text_data=1):
        self.open_results = list(open_results)
        self.open_calls = 0
        self.close_calls = 0
        self.hdrop = hdrop
        self.text = text
        self.hdrop_data = hdrop_data
        self.text_data = text_data

    def OpenClipboard(self, hwnd):
        self.open_calls += 1
        if self.open_results:
            return self.open_results.pop(0)
        return 1

    def CloseClipboard(self):
        self.close_calls += 1
        return 1

    def IsClipboardFormatAvailable(self, fmt):
        if fmt == clipboard.CF_HDROP:
            return self.hdrop
        if fmt == clipboard.CF_UNICODETEXT:
            return self.text
        return 0

    def GetClipboardData(self, fmt):
        if fmt == clipboard.CF_HDROP:
            return self.hdrop_data
        return self.text_data


class FakeShell32:
    def __init__(self, files):
        self.files = files

    def DragQueryFileW(self, h, idx, buf, size):
        if idx == 0xFFFFFFFF:
            return len(self.files)
        path = self.files[idx]
        if buf is None:
            return len(path)
        buf.value = path
        return len(path)


class FakeKernel32:
    def __init__(self, text):
        self._buf = ctypes.create_unicode_buffer(text)

    def GlobalLock(self, h):
        return ctypes.addressof(self._buf)

    def GlobalUnlock(self, h):
        return 1


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(clipboard.time, "sleep", lambda _s: None)


def _install(monkeypatch, user32, shell32=None, kernel32=None):
    monkeypatch.setattr(clipboard, "user32", user32)
    monkeypatch.setattr(clipboard, "shell32", shell32 or FakeShell32([]))
    monkeypatch.setattr(clipboard, "kernel32", kernel32 or FakeKernel32(""))


def test_hdrop_files_after_transient_open_failures(monkeypatch):
    user32 = FakeUser32(open_results=[0, 0, 1])
    _install(monkeypatch, user32, FakeShell32([r"C:\a.txt", r"C:\b.txt"]))
    assert clipboard.get_clipboard_files() == [r"C:\a.txt", r"C:\b.txt"]
    assert user32.open_calls == 3
    assert user32.close_calls == 1


def test_open_always_failing_returns_empty(monkeypatch):
    class AlwaysFail(FakeUser32):
        def OpenClipboard(self, hwnd):
            self.open_calls += 1
            return 0

    user32 = AlwaysFail()
    _install(monkeypatch, user32, FakeShell32([r"C:\a.txt"]))
    assert clipboard.get_clipboard_files() == []
    assert user32.open_calls == clipboard._OPEN_ATTEMPTS * clipboard._READ_ATTEMPTS
    assert user32.close_calls == 0


def test_hdrop_absent_is_not_retried(monkeypatch):
    user32 = FakeUser32(hdrop=False)
    _install(monkeypatch, user32, FakeShell32([r"C:\a.txt"]))
    assert clipboard.get_clipboard_files() == []
    assert user32.open_calls == 1  # no format = final answer, not an error


def test_render_null_is_retried_then_empty(monkeypatch):
    user32 = FakeUser32(hdrop_data=0)
    _install(monkeypatch, user32, FakeShell32([r"C:\a.txt"]))
    assert clipboard.get_clipboard_files() == []
    assert user32.open_calls == clipboard._READ_ATTEMPTS
    assert user32.close_calls == clipboard._READ_ATTEMPTS


def test_paths_prefers_files_over_text(monkeypatch):
    user32 = FakeUser32()
    _install(
        monkeypatch,
        user32,
        FakeShell32([r"C:\from-files.txt"]),
        FakeKernel32(r"C:\from-text.txt"),
    )
    assert clipboard.get_clipboard_paths() == [r"C:\from-files.txt"]


def test_paths_falls_back_to_text_lines(monkeypatch):
    text = '"C:\\dir with space\\a"\n\nC:\\b\n'
    user32 = FakeUser32(hdrop=False)
    _install(monkeypatch, user32, FakeShell32([]), FakeKernel32(text))
    assert clipboard.get_clipboard_paths() == [r"C:\dir with space\a", r"C:\b"]


def test_text_read_after_hdrop_and_text_absent(monkeypatch):
    user32 = FakeUser32(hdrop=False, text=False)
    _install(monkeypatch, user32, FakeShell32([]), FakeKernel32(""))
    assert clipboard.get_clipboard_paths() == []
