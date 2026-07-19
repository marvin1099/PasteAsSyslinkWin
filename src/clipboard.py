"""Clipboard handling for text paths and HDROP (file drop) data."""

import ctypes
import ctypes.wintypes as wintypes
from ctypes import c_void_p, c_wchar_p, windll

CF_HDROP = 15
CF_UNICODETEXT = 13
GHND = 0x0042

user32 = windll.user32
kernel32 = windll.kernel32
shell32 = windll.shell32

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL

shell32.DragQueryFileW.argtypes = [c_void_p, wintypes.UINT, c_wchar_p, wintypes.UINT]
shell32.DragQueryFileW.restype = wintypes.UINT


def get_clipboard_files() -> list[str]:
    """Extract file paths from HDROP clipboard data (Ctrl+C in Explorer)."""
    files = []
    if not user32.OpenClipboard(0):
        return files
    try:
        if not user32.IsClipboardFormatAvailable(CF_HDROP):
            return files
        h_data = windll.user32.GetClipboardData(CF_HDROP)
        if not h_data:
            return files
        file_count = shell32.DragQueryFileW(h_data, 0xFFFFFFFF, None, 0)
        for i in range(file_count):
            buf_size = shell32.DragQueryFileW(h_data, i, None, 0) + 1
            buf = ctypes.create_unicode_buffer(buf_size)
            shell32.DragQueryFileW(h_data, i, buf, buf_size)
            files.append(buf.value)
    finally:
        user32.CloseClipboard()
    return files


def get_clipboard_text() -> list[str]:
    """Extract text lines from clipboard (text copy of paths)."""
    lines = []
    if not user32.OpenClipboard(0):
        return lines
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return lines
        h_data = windll.user32.GetClipboardData(CF_UNICODETEXT)
        if not h_data:
            return lines
        ptr = kernel32.GlobalLock(h_data)
        if not ptr:
            return lines
        try:
            text = c_wchar_p(ptr).value
            if text:
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        lines.append(line)
        finally:
            kernel32.GlobalUnlock(h_data)
    finally:
        user32.CloseClipboard()
    return lines


def get_clipboard_paths() -> list[str]:
    """Get all paths from clipboard, trying HDROP first, then text."""
    files = get_clipboard_files()
    if files:
        return files
    return get_clipboard_text()
