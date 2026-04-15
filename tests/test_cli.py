"""Integration tests for ``bin/platxa-memory``.

Every subcommand must respond to ``--help`` (the spec's verification
criterion), and each command's happy-path behaviour is exercised end-to-end
via ``subprocess`` so the shebang, argparse wiring, and import semantics are
all validated together. Pure helpers are imported directly for unit testing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

CLI_PATH = Path(__file__).resolve().parent.parent / "bin" / "platxa-memory"


# --- load the CLI as a module so pure helpers are directly testable ---------


def _load_cli_module():
    # The CLI has no .py suffix, so the default finder can't classify it.
    # Use SourceFileLoader explicitly to force Python-source loading.
    from importlib.machinery import SourceFileLoader

    loader = SourceFileLoader("platxa_memory_cli", str(CLI_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


cli = _load_cli_module()


# --- helpers ----------------------------------------------------------------


def _run(
    *args: str,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    full_env = {**os.environ}
    full_env.pop("CLAUDE_PROJECT_DIR", None)
    full_env.pop("PLATXA_MEMORY_AUTO_DIR", None)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(CLI_PATH), *args],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(cwd) if cwd else None,
        timeout=30,
    )


# --- --help for every subcommand (spec verification criterion) --------------

SUBCOMMANDS = (
    "detect-stack",
    "health",
    "search",
    "export",
    "import",
    "prune",
    "restore",
    "migrate",
)


@pytest.mark.parametrize("sub", SUBCOMMANDS)
def test_each_subcommand_has_help(sub: str) -> None:
    result = _run(sub, "--help")
    assert result.returncode == 0, f"{sub} --help failed: {result.stderr}"
    assert "usage:" in result.stdout.lower()


def test_top_level_help_lists_all_subcommands() -> None:
    result = _run("--help")
    assert result.returncode == 0
    for sub in SUBCOMMANDS:
        assert sub in result.stdout, f"{sub} missing from top-level --help"


def test_missing_subcommand_exits_nonzero() -> None:
    result = _run()
    assert result.returncode != 0
    assert "usage" in result.stderr.lower() or "usage" in result.stdout.lower()


# --- detect-stack ----------------------------------------------------------


def test_detect_stack_python(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    result = _run("detect-stack", "--project", str(tmp_path))
    assert result.returncode == 0
    assert result.stdout.strip() == "python"


def test_detect_stack_generic(tmp_path: Path) -> None:
    result = _run("detect-stack", "--project", str(tmp_path))
    assert result.returncode == 0
    assert result.stdout.strip() == "generic"


def test_detect_stack_json(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module x\n")
    result = _run("detect-stack", "--project", str(tmp_path), "--format", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["stack"] == "go"


def test_detect_stack_helper_direct(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\n")
    assert cli._detect_stack(tmp_path) == "rust"


# --- health ----------------------------------------------------------------


def test_health_uninitialized(tmp_path: Path) -> None:
    # Force an empty auto-dir hint so no machine-level state leaks in.
    empty = tmp_path / "empty-memory"
    empty.mkdir()
    result = _run(
        "health",
        "--project",
        str(tmp_path),
        "--auto-dir",
        str(empty),
    )
    assert result.returncode == 1  # uninitialized → exit 1
    assert "missing" in result.stdout
    assert "uninitialized" in result.stdout


def test_health_ok_json(tmp_path: Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "MEMORY.md").write_text("# index\n- [x](x.md)\n")
    (mem / "x.md").write_text("body")
    result = _run(
        "health",
        "--project",
        str(tmp_path),
        "--auto-dir",
        str(mem),
        "--format",
        "json",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["memory_md_present"] is True
    assert payload["topic_files"] == 1


# --- search ----------------------------------------------------------------


def test_search_finds_pattern(tmp_path: Path) -> None:
    claude = tmp_path / ".claude" / "rules"
    claude.mkdir(parents=True)
    (claude / "example.md").write_text("secret-marker present here\n")
    result = _run(
        "search",
        "secret-marker",
        "--project",
        str(tmp_path),
        "--scope",
        "project",
    )
    assert result.returncode == 0
    assert "secret-marker" in result.stdout
    assert "example.md" in result.stdout


def test_search_no_hits_exits_nonzero(tmp_path: Path) -> None:
    # Also pass a non-existent --auto-dir so user-scope search has nothing.
    result = _run(
        "search",
        "will-not-match-xyz-qqq",
        "--project",
        str(tmp_path),
        "--scope",
        "all",
        "--auto-dir",
        str(tmp_path / "nonexistent"),
    )
    assert result.returncode == 1


# --- export / import round-trip --------------------------------------------


def test_export_import_round_trip(tmp_path: Path) -> None:
    src_mem = tmp_path / "memory"
    src_mem.mkdir()
    (src_mem / "MEMORY.md").write_text("# idx\n")
    (src_mem / "feedback_x.md").write_text("rule body\n")

    archive = tmp_path / "backup.tar.gz"
    result = _run("export", str(archive), "--auto-dir", str(src_mem))
    assert result.returncode == 0, result.stderr
    assert archive.is_file()

    # Simulate a fresh target dir that already contains the auto-memory path.
    target_root = tmp_path / "restored"
    target_root.mkdir()
    target_mem = target_root / "memory"
    # Pre-create so the directory exists and we exercise --force.
    target_mem.mkdir()
    (target_mem / "stale.md").write_text("stale")

    # Without --force, import must refuse.
    result = _run("import", str(archive), "--auto-dir", str(target_mem))
    assert result.returncode == 2
    assert (target_mem / "stale.md").is_file()

    # With --force, import overwrites.
    result = _run("import", str(archive), "--auto-dir", str(target_mem), "--force")
    assert result.returncode == 0, result.stderr
    assert not (target_mem / "stale.md").exists()
    assert (target_mem / "MEMORY.md").is_file()
    assert (target_mem / "feedback_x.md").is_file()


def test_import_refuses_unsafe_archive(tmp_path: Path) -> None:
    # Build a tarball that tries to escape the target dir.
    archive = tmp_path / "evil.tar.gz"
    escape = tmp_path / "evil"
    escape.mkdir()
    (escape / "ok.md").write_text("ok")
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo(name="../../etc/evil")
        info.size = 0
        tf.addfile(info, fileobj=None)
        tf.add(escape / "ok.md", arcname="memory/ok.md")

    target = tmp_path / "restored" / "memory"
    target.parent.mkdir()
    result = _run("import", str(archive), "--auto-dir", str(target), "--force")
    assert result.returncode == 1
    assert "unsafe" in result.stderr


def test_import_refuses_symlink_escape(tmp_path: Path) -> None:
    # A symlink member whose linkname escapes the extract root must be rejected
    # even though the member's own name is benign.
    archive = tmp_path / "symlink-evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        benign = tarfile.TarInfo(name="memory/MEMORY.md")
        benign.size = 0
        tf.addfile(benign, fileobj=None)
        bad_link = tarfile.TarInfo(name="memory/escape")
        bad_link.type = tarfile.SYMTYPE
        bad_link.linkname = "../../../../etc/passwd"
        tf.addfile(bad_link)

    target = tmp_path / "restored" / "memory"
    target.parent.mkdir()
    result = _run("import", str(archive), "--auto-dir", str(target), "--force")
    assert result.returncode == 1
    assert "unsafe link" in result.stderr


def test_import_refuses_non_regular_member(tmp_path: Path) -> None:
    # Device / fifo / char-special members should be rejected.
    archive = tmp_path / "device.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        dev = tarfile.TarInfo(name="memory/node")
        dev.type = tarfile.CHRTYPE
        dev.devmajor = 1
        dev.devminor = 3
        tf.addfile(dev)

    target = tmp_path / "restored" / "memory"
    target.parent.mkdir()
    result = _run("import", str(archive), "--auto-dir", str(target), "--force")
    assert result.returncode == 1
    assert "non-regular" in result.stderr


def test_import_preserves_target_on_corrupt_archive(tmp_path: Path) -> None:
    # A corrupt / unreadable archive passed with --force must NOT destroy
    # the existing target directory.
    target = tmp_path / "memory"
    target.mkdir()
    (target / "MEMORY.md").write_text("precious content\n")
    (target / "keep.md").write_text("keep me\n")

    bogus = tmp_path / "not-a-tarball.tar.gz"
    bogus.write_bytes(b"this is not gzip data")

    result = _run("import", str(bogus), "--auto-dir", str(target), "--force")
    assert result.returncode == 1
    assert (target / "MEMORY.md").read_text() == "precious content\n"
    assert (target / "keep.md").is_file()


def test_search_accepts_dashed_pattern(tmp_path: Path) -> None:
    # Patterns starting with "-" must not be interpreted as rg flags once they
    # reach the subprocess. argparse itself requires "--" to stop option
    # parsing at the CLI level; downstream, we pass "--" to rg so the pattern
    # isn't re-interpreted as a flag there.
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "note.md").write_text("there is a -dashed-token here\n")

    result = _run(
        "search",
        "--project",
        str(tmp_path),
        "--scope",
        "project",
        "--",
        "-dashed-token",
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "-dashed-token" in result.stdout


# --- prune -----------------------------------------------------------------


def test_prune_removes_old_markers(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir()
    old = claude / ".memory-synthesized-old"
    young = claude / ".memory-synthesized-young"
    old.write_text("1")
    young.write_text("1")
    # Backdate old marker by 30 days.
    ancient = 1_700_000_000  # 2023-11-14 — well past any sane threshold
    os.utime(old, (ancient, ancient))

    result = _run("prune", "--project", str(tmp_path), "--days", "7")
    assert result.returncode == 0
    assert not old.exists()
    assert young.exists()
    assert "removed" in result.stdout


def test_prune_dry_run_does_not_delete(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir()
    marker = claude / ".memory-synthesized-old"
    marker.write_text("1")
    os.utime(marker, (1_700_000_000, 1_700_000_000))

    result = _run("prune", "--project", str(tmp_path), "--days", "7", "--dry-run")
    assert result.returncode == 0
    assert marker.exists()
    assert "would remove" in result.stdout


# --- restore ---------------------------------------------------------------


def test_restore_is_import_with_force(tmp_path: Path) -> None:
    src_mem = tmp_path / "memory"
    src_mem.mkdir()
    (src_mem / "MEMORY.md").write_text("# idx\n")
    archive = tmp_path / "snapshot.tar.gz"
    _run("export", str(archive), "--auto-dir", str(src_mem))

    # Target pre-exists with junk — restore must overwrite without --force.
    target = tmp_path / "other" / "memory"
    target.mkdir(parents=True)
    (target / "junk.md").write_text("junk")

    result = _run("restore", str(archive), "--auto-dir", str(target))
    assert result.returncode == 0, result.stderr
    assert not (target / "junk.md").exists()
    assert (target / "MEMORY.md").is_file()


# --- migrate ---------------------------------------------------------------


def test_migrate_no_op(tmp_path: Path) -> None:
    result = _run("migrate", "--project", str(tmp_path), "--format", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "up-to-date"
    assert payload["migrations_applied"] == []
