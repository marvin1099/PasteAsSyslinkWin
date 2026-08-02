"""Tests for symlink operation helpers."""

import os

from src.symlink_ops import (
    PROBE_PREFIX,
    PROBE_SUFFIX,
    create_write_probe,
    remove_probe_files,
    verify_write_probe,
)


def test_create_write_probe_writable_dir(tmp_path):
    probe = create_write_probe(str(tmp_path))
    assert probe is not None
    assert os.path.isfile(probe)
    name = os.path.basename(probe)
    assert name.startswith(PROBE_PREFIX)
    assert name.endswith(PROBE_SUFFIX)


def test_create_write_probe_missing_dir(tmp_path):
    assert create_write_probe(str(tmp_path / "missing")) is None


def test_create_write_probe_file_as_dir(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    assert create_write_probe(str(f)) is None


def test_verify_valid_probe(tmp_path):
    probe = create_write_probe(str(tmp_path))
    assert probe is not None
    assert verify_write_probe(str(tmp_path), probe) is True
    assert not os.path.exists(probe)


def test_verify_removes_probe(tmp_path):
    probe = create_write_probe(str(tmp_path))
    assert probe is not None
    verify_write_probe(str(tmp_path), probe)
    assert not os.path.exists(probe)


def test_verify_probe_outside_dest_dir(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    probe = create_write_probe(str(other))
    assert probe is not None
    assert verify_write_probe(str(tmp_path), probe) is False
    assert os.path.exists(probe)


def test_verify_wrong_token(tmp_path):
    probe = create_write_probe(str(tmp_path))
    assert probe is not None
    with open(probe, "w", encoding="utf-8") as f:
        f.write("not-the-token")
    assert verify_write_probe(str(tmp_path), probe) is False


def test_verify_wrong_name_shape(tmp_path):
    fake = tmp_path / "some_other_file.txt"
    fake.write_text("x")
    assert verify_write_probe(str(tmp_path), str(fake)) is False


def test_verify_missing_probe(tmp_path):
    probe = str(tmp_path / "missing_probe.tmp")
    assert verify_write_probe(str(tmp_path), probe) is False


def test_verify_no_probe_path(tmp_path):
    assert verify_write_probe(str(tmp_path), "") is False


def test_remove_probe_files_cleans_up(tmp_path):
    create_write_probe(str(tmp_path))
    create_write_probe(str(tmp_path))
    assert remove_probe_files(str(tmp_path)) == 2
    assert os.listdir(tmp_path) == []


def test_remove_probe_files_keeps_other_files(tmp_path):
    create_write_probe(str(tmp_path))
    (tmp_path / "normal.txt").write_text("x")
    assert remove_probe_files(str(tmp_path)) == 1
    assert os.listdir(tmp_path) == ["normal.txt"]
