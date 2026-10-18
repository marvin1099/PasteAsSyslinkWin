"""Clipboard handling for text paths and HDROP (file drop) data.

Two distinct sources are supported: files copied in Explorer (CF_HDROP)
and paths copied as text (CF_UNICODETEXT, possibly multiple quoted lines).
OpenClipboard fails transiently while another process holds the clipboard,
and GetClipboardData can return NULL while a delayed render by the owner
fails - both are retried briefly instead of reporting an empty clipboard.
"""

import ctypes
import ctypes.wintypes as wintypes
import time
from ctypes import c_void_p, c_wchar_p, windll

from src import writeback

CF_HDROP = 15
CF_UNICODETEXT = 13

_OPEN_ATTEMPTS = 8
_OPEN_DELAY = 0.03
_READ_ATTEMPTS = 3

user32 = windll.user32
kernel32 = windll.kernel32
shell32 = windll.shell32

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = c_void_p

kernel32.GlobalLock.argtypes = [c_void_p]
kernel32.GlobalLock.restype = c_void_p
kernel32.GlobalUnlock.argtypes = [c_void_p]
kernel32.GlobalUnlock.restype = wintypes.BOOL

shell32.DragQueryFileW.argtypes = [c_void_p, wintypes.UINT, c_wchar_p, wintypes.UINT]
shell32.DragQueryFileW.restype = wintypes.UINT


def _open() -> bool:
    """Open the clipboard, retrying while another process holds it."""
    for _ in range(_OPEN_ATTEMPTS):
        if user32.OpenClipboard(0):
            return True
        time.sleep(_OPEN_DELAY)
    writeback.dbg(f"clipboard open-failed attempts={_OPEN_ATTEMPTS}")
    return False


def _read_files_once() -> tuple[list[str], bool]:
    """One HDROP read; second element True when the failure is retryable."""
    if not _open():
        return [], True
    try:
        if not user32.IsClipboardFormatAvailable(CF_HDROP):
            return [], False  # no file data present - not an error
        h_data = user32.GetClipboardData(CF_HDROP)
        if not h_data:
            writeback.dbg("clipboard hdrop render-null")
            return [], True
        files = []
        file_count = shell32.DragQueryFileW(h_data, 0xFFFFFFFF, None, 0)
        for i in range(file_count):
            buf_size = shell32.DragQueryFileW(h_data, i, None, 0) + 1
            buf = ctypes.create_unicode_buffer(buf_size)
            shell32.DragQueryFileW(h_data, i, buf, buf_size)
            files.append(buf.value)
        return files, False
    finally:
        user32.CloseClipboard()


def get_clipboard_files() -> list[str]:
    """Extract file paths from HDROP clipboard data (Ctrl+C in Explorer)."""
    for _ in range(_READ_ATTEMPTS):
        files, retry = _read_files_once()
        if not retry:
            return files
        time.sleep(_OPEN_DELAY)
    writeback.dbg(f"clipboard hdrop failed attempts={_READ_ATTEMPTS}")
    return []


def _read_text_once() -> tuple[list[str], bool]:
    """One CF_UNICODETEXT read; second element True when retryable."""
    if not _open():
        return [], True
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return [], False  # no text present - not an error
        h_data = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_data:
            writeback.dbg("clipboard text render-null")
            return [], True
        ptr = kernel32.GlobalLock(h_data)
        if not ptr:
            writeback.dbg("clipboard text lock-null")
            return [], True
        try:
            text = c_wchar_p(ptr).value
            lines = []
            if text:
                for line in text.splitlines():
                    line = line.strip().strip('"').strip("'")
                    if line:
                        lines.append(line)
            return lines, False
        finally:
            kernel32.GlobalUnlock(h_data)
    finally:
        user32.CloseClipboard()


def get_clipboard_text() -> list[str]:
    """Extract text lines from clipboard (text copy of paths).

    Strips surrounding quotes and filters empty lines.
    """
    for _ in range(_READ_ATTEMPTS):
        lines, retry = _read_text_once()
        if not retry:
            return lines
        time.sleep(_OPEN_DELAY)
    writeback.dbg(f"clipboard text failed attempts={_READ_ATTEMPTS}")
    return []


def get_clipboard_paths() -> list[str]:
    """Get all paths from clipboard, trying HDROP first, then text."""
    files = get_clipboard_files()
    if files:
        writeback.dbg(f"clipboard paths source=files n={len(files)}")
        return files
    paths = get_clipboard_text()
    writeback.dbg(f"clipboard paths source={'text' if paths else 'none'} n={len(paths)}")
    return paths
