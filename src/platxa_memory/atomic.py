"""Atomic file write helpers.

Writes are staged into a sibling temp file (same directory, same
filesystem, so :func:`os.replace` is atomic), then fsync'd and renamed
over the target. On POSIX the parent directory is fsync'd after the
rename so the new directory entry survives an immediate power loss.

Why this module exists
----------------------
`platxa-memory` persists cross-session state (MEMORY.md index, topic
files, stop-hook markers, synthesizer output). A crash during a
non-atomic write can leave a truncated file that downstream hooks will
happily read on the next session, corrupting memory. Every mutation of
a durable file should go through these helpers.

Guarantees
~~~~~~~~~~
- On **success**: the target file contains exactly the provided bytes.
  The rename is atomic on same-filesystem POSIX platforms; on Windows
  :func:`os.replace` also provides atomic-replace semantics.
- On **any failure mid-write** (exception raised before rename): the
  target file is unchanged and no ``*.tmp`` file is left behind.
- On **power loss after rename**: the new content survives because the
  parent directory was fsync'd.

Hard constraint (see CLAUDE.md): stdlib only — no SDK, no API, no LLM.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, AnyStr, Union

PathLike = Union[str, "os.PathLike[str]"]


def _fsync_dir(directory: Path) -> None:
    """Fsync a directory so the rename persists across a crash.

    Windows has no POSIX-style directory fsync, and some filesystems
    (e.g. NFS, network overlays) either reject the call or don't support
    it meaningfully. Swallow those specific failures — the durability
    guarantee degrades to "rename is atomic but rename record might not
    survive an immediate power loss," which is still strictly better
    than the non-atomic baseline.
    """
    if sys.platform == "win32":
        return
    try:
        flags = os.O_RDONLY
        # O_DIRECTORY is Linux/BSD; guard for platforms that lack it.
        flags |= getattr(os, "O_DIRECTORY", 0)
        fd = os.open(str(directory), flags)
    except OSError:
        return
    try:
        try:
            os.fsync(fd)
        except OSError:
            # Some filesystems (e.g. certain NFS mounts) refuse directory
            # fsync. The rename itself already happened; move on.
            pass
    finally:
        os.close(fd)


def _existing_mode(path: Path) -> int | None:
    """Return the permission bits of ``path`` if it exists, else ``None``."""
    try:
        return path.stat().st_mode & 0o777
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError:
        return None


def _cleanup(tmp_path: Path) -> None:
    """Best-effort temp-file removal during failure paths."""
    try:
        tmp_path.unlink(missing_ok=True)
    except OSError:
        pass


def atomic_write_bytes(target: PathLike, data: bytes) -> None:
    """Atomically replace ``target`` with ``data``.

    If ``target`` exists its permission bits are preserved on the new file.
    Creates intermediate parent directories. Raises :class:`OSError` on
    unrecoverable failures; in every failure path the target is left
    unchanged and the staging temp file is removed.
    """
    target_path = Path(target)
    parent = target_path.parent
    parent.mkdir(parents=True, exist_ok=True)

    existing_mode = _existing_mode(target_path)

    # prefix=<name>. + suffix=.tmp makes failed-cleanup orphans visually
    # attributable to the target they were staging for.
    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        delete=False,
        dir=str(parent),
        prefix=f"{target_path.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp.name)
    try:
        try:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()

        if existing_mode is not None:
            try:
                os.chmod(tmp_path, existing_mode)
            except OSError:
                pass

        os.replace(tmp_path, target_path)
        _fsync_dir(parent)
    except BaseException:
        _cleanup(tmp_path)
        raise


def atomic_write_text(target: PathLike, text: str, *, encoding: str = "utf-8") -> None:
    """Atomically replace ``target`` with ``text`` encoded as ``encoding``."""
    atomic_write_bytes(target, text.encode(encoding))


@contextmanager
def atomic_write(
    target: PathLike,
    *,
    binary: bool = False,
    encoding: str | None = "utf-8",
) -> Iterator[IO[AnyStr]]:
    """Context manager that yields a file handle staged over ``target``.

    Usage::

        with atomic_write(Path("memory.md")) as fh:
            fh.write("content")

    On normal exit the temp file is fsync'd, renamed over ``target``, and
    the parent directory is fsync'd (POSIX). If the ``with`` block raises
    — or the caller ``raise``-s inside it — the temp file is removed and
    ``target`` is left unchanged.

    Parameters
    ----------
    target:
        Destination path.
    binary:
        Pass ``True`` to open the temp file in binary mode. When ``True``
        ``encoding`` is ignored.
    encoding:
        Text encoding for the temp file. Ignored when ``binary=True``.
    """
    target_path = Path(target)
    parent = target_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    existing_mode = _existing_mode(target_path)

    tmp = tempfile.NamedTemporaryFile(
        mode="wb" if binary else "w",
        encoding=None if binary else encoding,
        delete=False,
        dir=str(parent),
        prefix=f"{target_path.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp.name)

    try:
        yield tmp  # type: ignore[misc]
    except BaseException:
        try:
            tmp.close()
        except Exception:
            pass
        _cleanup(tmp_path)
        raise

    # Normal-exit path: fsync + swap + fsync parent. Any failure here also
    # cleans up so we never leave a half-written target.
    try:
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        if existing_mode is not None:
            try:
                os.chmod(tmp_path, existing_mode)
            except OSError:
                pass
        os.replace(tmp_path, target_path)
        _fsync_dir(parent)
    except BaseException:
        _cleanup(tmp_path)
        raise


__all__ = ("atomic_write", "atomic_write_bytes", "atomic_write_text")
