"""Tests for CLI flag parsing, build functions, and end-to-end config flow."""

import subprocess
import tempfile

from src.cli import (
    build_file_flags,
    build_folder_flags,
    parse_admin_opts,
    parse_flags,
    validate_args,
    validate_path,
)
from src.config import Config
from src.pathresolver import to_unc_path

# ── parse_flags: basic operations ──


def test_file_symlink():
    """/f → file_flags=["/f"], folder_flags=[]"""
    r = parse_flags(["/f"])
    assert r["file_flags"] == ["/f"]
    assert r["folder_flags"] == []


def test_dir_symlink():
    """/d → file_flags=[], folder_flags=["/d"]"""
    r = parse_flags(["/d"])
    assert r["file_flags"] == []
    assert r["folder_flags"] == ["/d"]


def test_file_hardlink():
    """/h → file_flags=["/h"], folder_flags=[]"""
    r = parse_flags(["/h"])
    assert r["file_flags"] == ["/h"]
    assert r["folder_flags"] == []


def test_dir_junction():
    """/j → file_flags=[], folder_flags=["/j"]"""
    r = parse_flags(["/j"])
    assert r["file_flags"] == []
    assert r["folder_flags"] == ["/j"]


def test_multiple_operations():
    """/f /h /d /j → all operations present."""
    r = parse_flags(["/f", "/h", "/d", "/j"])
    assert r["file_flags"] == ["/f", "/h"]
    assert r["folder_flags"] == ["/d", "/j"]


# ── parse_flags: special flags ──


def test_wildcard_on():
    r = parse_flags(["/f", "/w"])
    assert r["wildcard"] is True


def test_wildcard_off():
    r = parse_flags(["/f", "/m"])
    assert r["wildcard"] is False


def test_wildcard_none():
    r = parse_flags(["/f"])
    assert r["wildcard"] is None


def test_install_uninstall():
    r = parse_flags(["/u"])
    assert r["install_mode"] is True
    r2 = parse_flags(["/i"])
    assert r2["install_mode"] is False


# ── build_file_flags / build_folder_flags ──


def test_build_file_flags_symlink():
    """/f (file symlink) → "" (mklink default)."""
    r = parse_flags(["/f"])
    assert build_file_flags(r) == ""


def test_build_file_flags_hardlink():
    """/h (file hardlink) → "/h"."""
    r = parse_flags(["/h"])
    assert build_file_flags(r) == "/h"


def test_build_file_flags_both():
    """/f /h → "/h" (hardlink wins since /f maps to nothing)."""
    r = parse_flags(["/f", "/h"])
    assert build_file_flags(r) == "/h"


def test_build_folder_flags_junction():
    """/j → "/j"."""
    r = parse_flags(["/j"])
    assert build_folder_flags(r) == "/j"


def test_build_folder_flags_symlink():
    """/d → "/d"."""
    r = parse_flags(["/d"])
    assert build_folder_flags(r) == "/d"


def test_build_folder_flags_both():
    """/d /j → "/j" (junction wins)."""
    r = parse_flags(["/d", "/j"])
    assert build_folder_flags(r) == "/j"


def test_build_folder_flags_empty():
    """No folder flags → "/d" (default dir symlink)."""
    r = parse_flags(["/f"])
    assert build_folder_flags(r) == "/d"


# ── parse_admin_opts ──


def test_parse_admin_opts():
    """Admin opts are operation flags: /f, /h, /d, /j."""
    assert parse_admin_opts("/f /h") == ["/f", "/h"]
    assert parse_admin_opts("/d") == ["/d"]
    assert parse_admin_opts("/j") == ["/j"]


def test_parse_admin_opts_empty():
    assert parse_admin_opts("") == []
    assert parse_admin_opts("/w") == []


# ── End-to-end: config save → load → parse → build → mklink command ──


def test_config_roundtrip_file_symlink():
    """Config: /f + /d → mklink for files, mklink /d for folders."""
    file_opts = "/f"
    folder_opts = "/d"

    combined = f"{file_opts} {folder_opts}".strip().split()
    normal = parse_flags(combined)

    file_flags = build_file_flags(normal)
    folder_flags = build_folder_flags(normal)

    # mklink "dest" "src" (file symlink)
    assert file_flags == ""
    # mklink /d "dest" "src" (dir symlink)
    assert folder_flags == "/d"


def test_config_roundtrip_dir_symlink_only():
    """Config: /f + /d → mklink for files, mklink /d for folders."""
    file_opts = "/f"
    folder_opts = "/d"

    combined = f"{file_opts} {folder_opts}".strip().split()
    normal = parse_flags(combined)

    file_flags = build_file_flags(normal)
    folder_flags = build_folder_flags(normal)

    assert file_flags == ""
    assert folder_flags == "/d"


def test_mklink_command_construction():
    """Verify mklink commands via subprocess.list2cmdline (proper escaping)."""
    source = "C:\\source\\file.txt"
    dest = "C:\\dest\\file.txt"

    cmd = subprocess.list2cmdline(["cmd", "/c", "mklink", dest, source])
    assert cmd == "cmd /c mklink C:\\dest\\file.txt C:\\source\\file.txt"

    cmd = subprocess.list2cmdline(["cmd", "/c", "mklink", "/j", dest, source])
    assert cmd == "cmd /c mklink /j C:\\dest\\file.txt C:\\source\\file.txt"

    cmd = subprocess.list2cmdline(["cmd", "/c", "mklink", "/d", dest, source])
    assert cmd == "cmd /c mklink /d C:\\dest\\file.txt C:\\source\\file.txt"

    cmd = subprocess.list2cmdline(["cmd", "/c", "mklink", "C:\\My Folder\\link.txt", source])
    assert cmd == 'cmd /c mklink "C:\\My Folder\\link.txt" C:\\source\\file.txt'

    cmd = subprocess.list2cmdline(["cmd", "/c", "mklink", "C:\\test&calc\\link.txt", source])
    assert "test&calc" in cmd


def test_admin_elevation_detection():
    """Admin detection: config admin opts vs runtime flags."""
    # Config admin opts: /f /h for files, /d for folders
    admin_ff = parse_admin_opts("/f /h")
    admin_df = parse_admin_opts("/d")

    # Runtime: /f → file symlink → /f in raw file_flags → needs admin
    runtime = parse_flags(["/f"])
    assert any(flag in runtime["file_flags"] for flag in admin_ff)

    # Runtime: /h → file hardlink → /h in raw file_flags → needs admin
    runtime = parse_flags(["/h"])
    assert any(flag in runtime["file_flags"] for flag in admin_ff)

    # Runtime: /j → junction → /j not in admin folder flags → no elevation
    runtime = parse_flags(["/j"])
    assert not any(flag in runtime["folder_flags"] for flag in admin_df)

    # Runtime: /d → dir symlink → /d in raw folder_flags → needs elevation
    runtime = parse_flags(["/d"])
    assert any(flag in runtime["folder_flags"] for flag in admin_df)


def test_invalid_flags_ignored():
    r = parse_flags(["/f", "/z", "/x"])
    assert r["file_flags"] == ["/f"]
    assert r["folder_flags"] == []


def test_empty_args():
    r = parse_flags([])
    assert r["file_flags"] == []
    assert r["folder_flags"] == []
    assert r["wildcard"] is None
    assert r["install_mode"] is None


# ── validate_path ──


def test_validate_path_normal():
    assert validate_path("C:\\Users\\test\\file.txt") == "C:\\Users\\test\\file.txt"
    assert validate_path("\\\\server\\share\\file.txt") == "\\\\server\\share\\file.txt"
    assert validate_path("D:\\folder (x86)\\app") == "D:\\folder (x86)\\app"


def test_validate_path_empty():
    assert validate_path("") is None


def test_validate_path_shell_injection():
    assert validate_path("C:\\test|notepad\\file.txt") is None
    assert validate_path("C:\\test^calc\\file.txt") is None
    assert validate_path('C:\\test"quote\\file.txt') is None
    assert validate_path("C:\\test>redirect\\file.txt") is None
    assert validate_path("C:\\test<less\\file.txt") is None


def test_validate_path_allows_ampersand_and_backtick():
    """`&` and backtick are inert inside quoted cmd args and valid filename chars."""
    assert validate_path("C:\\test&calc\\file.txt") == "C:\\test&calc\\file.txt"
    assert validate_path("C:\\test`whoami\\file.txt") == "C:\\test`whoami\\file.txt"


def test_validate_path_control_chars():
    assert validate_path("C:\\test\x00file.txt") is None
    assert validate_path("C:\\test\nfile.txt") is None
    assert validate_path("C:\\test\rfile.txt") is None


# ── validate_args ──


def test_validate_args_separates_flags_and_paths():
    flags, paths = validate_args(["/f", "C:\\dest", "/d", "C:\\source"])
    assert flags == ["/f", "/d"]
    assert paths == ["C:\\dest", "C:\\source"]


def test_validate_args_drops_injection():
    flags, paths = validate_args(["/f", "C:\\safe", "C:\\evil|calc"])
    assert flags == ["/f"]
    assert "C:\\evil|calc" not in paths
    assert "C:\\safe" in paths


def test_validate_args_drops_invalid_flags():
    flags, paths = validate_args(["/f", "/z", "/x"])
    assert flags == ["/f"]
    assert paths == []


# ── Config roundtrip ──


def test_config_defaults():
    """Config class defaults match expected values."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(tmp, "test")
        assert cfg.task is True
        assert cfg.wildcard_loops is False
        assert cfg.script_default_file_opts == "/f"
        assert cfg.script_default_folder_opts == "/j"
        assert cfg.admin_free is False
        assert cfg.all_users is False
        assert cfg.admin_file_opts == "/f /h"
        assert cfg.admin_folder_opts == "/d"


def test_config_save_load_roundtrip():
    """Save config then load it back, values should match."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(tmp, "test")
        cfg.task = False
        cfg.wildcard_loops = True
        cfg.script_default_file_opts = "/h"
        cfg.script_default_folder_opts = "/d"
        cfg.admin_file_opts = "/h"
        cfg.admin_folder_opts = "/d"
        cfg.admin_free = True
        cfg.all_users = True
        cfg.save()

        cfg2 = Config(tmp, "test")
        assert cfg2.exists()
        assert cfg2.load() is True
        assert cfg2.task is False
        assert cfg2.wildcard_loops is True
        assert cfg2.script_default_file_opts == "/h"
        assert cfg2.script_default_folder_opts == "/d"
        assert cfg2.admin_file_opts == "/h"
        assert cfg2.admin_folder_opts == "/d"
        assert cfg2.admin_free is True
        assert cfg2.all_users is True


def test_config_delete():
    """Config delete removes the file."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(tmp, "test")
        cfg.save()
        assert cfg.exists()
        cfg.delete()
        assert not cfg.exists()


# ── parse_flags edge cases ──


def test_parse_flags_duplicate_flags():
    """Duplicate flags accumulate."""
    r = parse_flags(["/f", "/f"])
    assert r["file_flags"] == ["/f", "/f"]


def test_parse_flags_junction_standalone():
    """/j alone goes to folder_flags."""
    r = parse_flags(["/j"])
    assert r["folder_flags"] == ["/j"]
    assert r["file_flags"] == []


def test_build_folder_flags_junction_with_dir_symlink():
    """/d /j → /j (junction wins)."""
    r = parse_flags(["/d", "/j"])
    assert build_folder_flags(r) == "/j"


# ── validate_path edge cases ──


def test_validate_path_trailing_backslash():
    assert validate_path("C:\\folder\\") == "C:\\folder\\"


def test_validate_path_unc():
    assert validate_path("\\\\server\\share") == "\\\\server\\share"


def test_validate_path_forward_slash_unc():
    assert validate_path("//server/share/file.txt") == "//server/share/file.txt"


def test_validate_args_forward_slash_unc_is_path():
    """Forward-slash UNC must be treated as a path, not a flag."""
    flags, paths = validate_args(["/f", "//server/share/file.txt"])
    assert flags == ["/f"]
    assert paths == ["//server/share/file.txt"]


def test_validate_path_relative():
    assert validate_path("relative\\path\\file.txt") == "relative\\path\\file.txt"


# ── validate_args edge cases ──


def test_validate_args_empty_list():
    flags, paths = validate_args([])
    assert flags == []
    assert paths == []


def test_validate_args_whitespace_only():
    flags, paths = validate_args(["  ", "", "  "])
    assert flags == []
    assert paths == []


def test_validate_args_mixed_case_flags():
    """Flags are case-insensitive."""
    flags, paths = validate_args(["/F", "/H", "/D"])
    assert flags == ["/F", "/H", "/D"]


# ── parse_flags: /clip and /noclip ──


def test_parse_flags_clip():
    """/clip sets clip=True."""
    r = parse_flags(["/clip"])
    assert r["clip"] is True


def test_parse_flags_noclip():
    """/noclip sets clip=False."""
    r = parse_flags(["/noclip"])
    assert r["clip"] is False


def test_parse_flags_clip_default():
    """No clip/noclip flag → clip=None."""
    r = parse_flags(["/f"])
    assert r["clip"] is None


def test_validate_args_clip():
    """/clip and /noclip pass through validate_args."""
    flags, paths = validate_args(["/clip", "/noclip", "/f"])
    assert "/clip" in flags
    assert "/noclip" in flags
    assert "/f" in flags


# ── parse_flags: install/uninstall long form ──


def test_parse_flags_uninstall_long():
    """/uninstall sets install_mode=True."""
    r = parse_flags(["/uninstall"])
    assert r["install_mode"] is True


def test_parse_flags_install_long():
    """/install sets install_mode=False."""
    r = parse_flags(["/install"])
    assert r["install_mode"] is False


# ── to_unc_path ──


def test_to_unc_path_non_drive_path_unchanged():
    """Paths without a drive letter pass through unchanged."""
    assert to_unc_path(r"\\server\share\file.txt") == r"\\server\share\file.txt"
    assert to_unc_path(r"relative\path") == r"relative\path"


def test_to_unc_path_unmapped_drive_unchanged():
    """A drive letter that is not a network mapping passes through unchanged."""
    result = to_unc_path(r"X:\definitely_not_mapped\file.txt")
    assert result == r"X:\definitely_not_mapped\file.txt"


def test_to_unc_path_mapped_drive():
    """A mapped network drive resolves to its UNC form."""
    result = to_unc_path(r"Z:\Standart-Festplatte\Marvin\file.txt")
    assert result.startswith("\\\\")
    assert result.endswith(r"\Standart-Festplatte\Marvin\file.txt")
