"""Unit tests for :mod:`platxa_memory.atomic`.

Spec verification criterion for feature #37:
    "Simulated crash mid-write leaves target unchanged; no .tmp litter"

Tests are split into three buckets:

1. Happy-path round-trip for each entrypoint
   (``atomic_write_bytes``, ``atomic_write_text``, ``atomic_write``).
2. Crash-simulation: an exception is raised from within the write path;
   target must remain untouched and the parent directory must contain
   no leftover ``*.tmp`` staging files.
3. Durability plumbing: fsync is called on the temp file and on the
   parent directory (POSIX), permissions are preserved when
   overwriting, and intermediate parent dirs are created on demand.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from platxa_memory import atomic  # noqa: E402
from platxa_memory.atomic import (  # noqa: E402
    atomic_write,
    atomic_write_bytes,
    atomic_write_text,
)

# --- helpers ---------------------------------------------------------------


def _tmp_files(parent: Path) -> list[Path]:
    return sorted(p for p in parent.iterdir() if p.name.endswith(".tmp"))


# --- happy path -----------------------------------------------------------


def test_atomic_write_bytes_creates_target(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    atomic_write_bytes(target, b"hello\x00world")
    assert target.read_bytes() == b"hello\x00world"
    assert _tmp_files(tmp_path) == []


def test_atomic_write_text_creates_target(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    atomic_write_text(target, "# hello\n")
    assert target.read_text() == "# hello\n"
    assert _tmp_files(tmp_path) == []


def test_atomic_write_text_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    target.write_text("old content\n")
    atomic_write_text(target, "new content\n")
    assert target.read_text() == "new content\n"


def test_atomic_write_context_manager_writes_target(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    with atomic_write(target) as fh:
        fh.write("line 1\n")
        fh.write("line 2\n")
    assert target.read_text() == "line 1\nline 2\n"
    assert _tmp_files(tmp_path) == []


def test_atomic_write_binary_context_manager(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    with atomic_write(target, binary=True) as fh:
        fh.write(b"\x01\x02\x03")
    assert target.read_bytes() == b"\x01\x02\x03"


def test_creates_missing_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c.md"
    atomic_write_text(target, "deep\n")
    assert target.read_text() == "deep\n"


# --- crash / exception paths (SPEC VERIFICATION CRITERION) ------------------


def test_exception_mid_write_leaves_target_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    target.write_text("precious content\n")

    with pytest.raises(RuntimeError, match="simulated crash"):
        with atomic_write(target) as fh:
            fh.write("partial\n")
            raise RuntimeError("simulated crash")

    assert target.read_text() == "precious content\n"
    assert _tmp_files(tmp_path) == []


def test_exception_on_missing_target_leaves_no_target(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    with pytest.raises(RuntimeError, match="simulated crash"):
        with atomic_write(target) as fh:
            fh.write("partial\n")
            raise RuntimeError("simulated crash")

    assert not target.exists()
    assert _tmp_files(tmp_path) == []


def test_exception_inside_atomic_write_bytes_cleans_up(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    target.write_text("original\n")

    # Patch os.replace to fail AFTER the temp file has been written + fsync'd
    # — simulates a filesystem-level rename failure (e.g. target on a
    # different mount). The helper must still clean up the temp file.
    with mock.patch.object(atomic.os, "replace", side_effect=OSError("EXDEV")):
        with pytest.raises(OSError, match="EXDEV"):
            atomic_write_bytes(target, b"new content")

    assert target.read_text() == "original\n"
    assert _tmp_files(tmp_path) == []


def test_keyboard_interrupt_inside_atomic_write_cleans_up(tmp_path: Path) -> None:
    # BaseException (not Exception) — KeyboardInterrupt must also trigger
    # cleanup. Regression guard: a bare `except Exception` would miss this.
    target = tmp_path / "out.md"
    target.write_text("preserved\n")

    with pytest.raises(KeyboardInterrupt):
        with atomic_write(target) as fh:
            fh.write("partial\n")
            raise KeyboardInterrupt()

    assert target.read_text() == "preserved\n"
    assert _tmp_files(tmp_path) == []


# --- durability plumbing --------------------------------------------------


def test_file_fsync_is_called(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    calls: list[int] = []

    real_fsync = atomic.os.fsync

    def tracking_fsync(fd: int) -> None:
        calls.append(fd)
        return real_fsync(fd)

    with mock.patch.object(atomic.os, "fsync", side_effect=tracking_fsync):
        atomic_write_text(target, "body\n")

    # At least one fsync on the temp file (fd is a file descriptor int,
    # not a dir descriptor; dir fsync is exercised in its own test).
    assert len(calls) >= 1


@pytest.mark.skipif(sys.platform == "win32", reason="parent-dir fsync is POSIX-only")
def test_parent_dir_fsync_on_posix(tmp_path: Path) -> None:
    # The helper should fsync the parent directory. We verify by watching
    # os.open + os.fsync for a dir-flavoured fd.
    opened: list[str] = []
    real_open = atomic.os.open

    def tracking_open(path: str, flags: int, *args: object, **kwargs: object) -> int:
        opened.append(str(path))
        return real_open(path, flags, *args, **kwargs)

    with mock.patch.object(atomic.os, "open", side_effect=tracking_open):
        atomic_write_text(tmp_path / "out.md", "body\n")

    # The parent dir should appear in the opened paths (the helper opens
    # it to call fsync on the dir descriptor).
    assert str(tmp_path) in opened


def test_permissions_preserved_when_overwriting(tmp_path: Path) -> None:
    # NamedTemporaryFile creates a 0600 file; the helper must re-apply
    # the target's original mode so we don't silently downgrade perms.
    target = tmp_path / "out.md"
    target.write_text("initial\n")
    os.chmod(target, 0o644)

    atomic_write_text(target, "updated\n")

    assert target.stat().st_mode & 0o777 == 0o644
    assert target.read_text() == "updated\n"


def test_no_tmp_file_visible_after_success(tmp_path: Path) -> None:
    # Reinforces the "no .tmp litter" half of the spec criterion.
    target = tmp_path / "out.md"
    for body in ("a", "b", "c"):
        atomic_write_text(target, body)
        assert _tmp_files(tmp_path) == []
        assert target.read_text() == body


# --- edge cases ------------------------------------------------------------


def test_atomic_write_accepts_string_path(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    atomic_write_text(str(target), "stringy\n")
    assert target.read_text() == "stringy\n"


def test_empty_write_produces_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    atomic_write_bytes(target, b"")
    assert target.read_bytes() == b""
    assert target.is_file()


def test_large_write_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "big.bin"
    data = os.urandom(1 << 20)  # 1 MiB
    atomic_write_bytes(target, data)
    assert target.read_bytes() == data
